import json

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import new_issue, png_file

client = TestClient(app)


def _project(budget=50_000):
    _, verified = new_issue(client, "Large pothole on Station Road that needs patching.")
    intervention = client.post("/api/planner/interventions/generate").json()["items"][0]
    created = client.post(
        "/api/accountability/projects",
        json={
            "intervention_public_id": intervention["public_id"],
            "approved_budget_bdt": budget,
            "specification": "Cut and patch 4 m2 with bituminous mix, compact, seal edges.",
            "contractor_name": "Demo Contractor Ltd",
        },
    )
    assert created.status_code == 200, created.text
    return verified["issue_public_id"], created.json()["public_id"]


def test_full_project_lifecycle_and_state_rules():
    issue_id, pid = _project()

    update = client.post(
        f"/api/accountability/projects/{pid}/updates",
        data={"progress_pct": "40", "expenditure_bdt": "10000", "note": "Excavation done."},
    )
    assert update.status_code == 200, update.text
    assert update.json()["status"] == "in_progress"

    backwards = client.post(
        f"/api/accountability/projects/{pid}/updates",
        data={"progress_pct": "20", "expenditure_bdt": "0", "note": "Oops."},
    )
    assert backwards.status_code == 400

    no_evidence = client.post(f"/api/accountability/projects/{pid}/complete", data={"note": "All done."})
    assert no_evidence.status_code == 400

    premature = client.post(
        f"/api/accountability/projects/{pid}/inspections",
        data={"inspector": "A. Inspector", "outcome": "meets_specification", "notes": "Looks fine.", "independent": "true"},
    )
    assert premature.status_code == 409

    done = client.post(
        f"/api/accountability/projects/{pid}/complete",
        data={"note": "Patch compacted and sealed."},
        files=[png_file("after.png")],
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"

    again = client.post(
        f"/api/accountability/projects/{pid}/complete", data={"note": "Again."}, files=[png_file()]
    )
    assert again.status_code == 409

    inspected = client.post(
        f"/api/accountability/projects/{pid}/inspections",
        data={
            "inspector": "Independent Engineer",
            "independent": "true",
            "outcome": "meets_specification",
            "condition_score": "5",
            "notes": "Surface flush, edges sealed.",
        },
        files=[png_file("inspection.png")],
    )
    assert inspected.status_code == 200, inspected.text

    detail = client.get(f"/api/accountability/projects/{pid}").json()
    stages = [step["stage"] for step in detail["lifecycle"]]
    for expected in ("verified_issue", "proposed_intervention", "approved_project", "progress_update", "completion_reported", "inspection"):
        assert expected in stages
    assert detail["issue_status"] == "resolved_verified"
    assert {e["kind"] for e in detail["evidence"]} == {"completion", "inspection"}
    assert detail["findings"]["review_flag"] == "none"

    download = client.get(detail["evidence"][0]["url"])
    assert download.status_code == 200 and download.headers["content-type"] == "image/png"

    duplicate = client.post(
        "/api/accountability/projects",
        json={"intervention_public_id": detail["intervention_public_id"], "approved_budget_bdt": 1, "specification": "A second project."},
    )
    assert duplicate.status_code == 409
    summary = client.get("/api/accountability/summary").json()
    assert summary["projects"] == 1 and summary["by_status"]["completed"] == 1


def test_fast_recurrence_is_flagged_for_review_without_any_allegation():
    issue_id, pid = _project()
    client.post(
        f"/api/accountability/projects/{pid}/complete",
        data={"note": "Patched.", "completed_on": _days_ago(20)},
        files=[png_file()],
    )
    _, second = new_issue(client, "Pothole again in the same place on Station Road.")
    hits = second["follows_completed_projects"]
    assert hits and hits[0]["project_public_id"] == pid
    assert hits[0]["faster_than_threshold"] is True

    screen = client.get("/api/accountability/recurrence").json()
    row = next(item for item in screen["items"] if item["project"]["public_id"] == pid)
    assert row["review_flag"] == "worth_independent_review"
    assert any("days after completion" in reason for reason in row["reasons"])
    assert "rainfall" in screen["context_limitations"].lower()

    text = json.dumps(screen).lower()
    assert "corrupt" not in text and "fraud" not in text
    assert "not findings of fault" in screen["disclaimer"].lower()


def test_missing_completion_evidence_and_overspend_are_documentation_flags():
    _, pid = _project(budget=10_000)
    client.post(
        f"/api/accountability/projects/{pid}/updates",
        data={"progress_pct": "50", "expenditure_bdt": "20000", "note": "Materials bought."},
    )
    detail = client.get(f"/api/accountability/projects/{pid}").json()
    assert detail["spent_bdt"] == 20000
    client.post(f"/api/accountability/projects/{pid}/complete", data={"note": "Done."}, files=[png_file()])
    findings = client.get(f"/api/accountability/projects/{pid}").json()["findings"]
    checks = {c["check"]: c["status"] for c in findings["checks"]}
    assert checks["expenditure_vs_budget"] == "concern"
    assert checks["independent_inspection"] == "unknown"
    assert findings["review_flag"] == "worth_independent_review"


def _days_ago(n):
    from datetime import date, timedelta

    return (date.today() - timedelta(days=n)).isoformat()
