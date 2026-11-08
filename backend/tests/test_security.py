from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import new_issue, submit_report

client = TestClient(app)

STAFF_ONLY = [
    ("get", "/api/reports"),
    ("get", "/api/reports/geojson"),
    ("get", "/api/investigator/queue"),
    ("get", "/api/intelligence/summary"),
    ("get", "/api/planner/summary"),
    ("get", "/api/accountability/summary"),
    ("get", "/api/overview"),
    ("get", "/api/audit"),
]


def test_staff_endpoints_need_the_token_but_citizen_flow_does_not(staff_auth):
    for method, url in STAFF_ONLY:
        assert getattr(client, method)(url).status_code == 401, url
        assert getattr(client, method)(url, headers={"X-Staff-Token": "wrong"}).status_code == 401, url
        assert getattr(client, method)(url, headers=staff_auth).status_code == 200, url

    report = submit_report(client, "Citizen can still report without logging in.")
    tracked = client.get(f"/api/reports/track/{report['tracking_id']}")
    assert tracked.status_code == 200
    assert "reporter_name" not in tracked.json()

    status = client.patch(f"/api/reports/track/{report['tracking_id']}/status", json={"status": "acknowledged"})
    assert status.status_code == 401


def test_health_reports_auth_mode(staff_auth):
    assert client.get("/api/health").json()["staff_auth"] == "enabled"


def test_staff_actions_are_audited_with_the_actor_name(staff_auth):
    report, verified = new_issue(client, "Audited pothole report on Station Road.", headers=staff_auth)
    client.patch(
        f"/api/reports/track/{report['tracking_id']}/status", json={"status": "under_review"}, headers=staff_auth
    )
    log = client.get("/api/audit", headers=staff_auth).json()["items"]
    actions = {(row["action"], row["actor"]) for row in log}
    assert ("verification.new_candidate_issue", "tester") in actions
    assert ("report.status_changed", "tester") in actions


def test_report_cannot_be_turned_into_two_issues():
    report, _ = new_issue(client, "Report that is verified twice by mistake.")
    again = client.post(
        "/api/investigator/verify", json={"tracking_id": report["tracking_id"], "decision": "new_candidate_issue"}
    )
    assert again.status_code == 409


def test_upload_validation_rejects_non_images_and_bad_coordinates():
    from io import BytesIO

    bad = client.post(
        "/api/reports",
        data={"category": "pothole", "severity": "low", "description": "Not an image upload here.", "latitude": "22.8", "longitude": "91.1"},
        files={"files": ("evil.png", BytesIO(b"<script>alert(1)</script>"), "image/png")},
    )
    assert bad.status_code == 400
    far = client.post(
        "/api/reports",
        data={"category": "pothole", "severity": "low", "description": "Pin dropped in the ocean.", "latitude": "0", "longitude": "0"},
    )
    assert far.status_code == 400
