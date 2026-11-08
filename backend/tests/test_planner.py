from io import BytesIO
from base64 import b64decode

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _issue(description: str = "Pothole for planner costing.") -> str:
    data = {
        "category": "pothole",
        "severity": "high",
        "description": description,
        "latitude": "22.869",
        "longitude": "91.099",
        "language": "en",
    }
    files = {"files": ("hole.png", BytesIO(PNG), "image/png")}
    report = client.post("/api/reports", data=data, files=files)
    assert report.status_code == 200, report.text
    verify = client.post(
        "/api/investigator/verify",
        json={"tracking_id": report.json()["tracking_id"], "decision": "new_candidate_issue"},
    )
    assert verify.status_code == 200, verify.text
    return verify.json()["issue_public_id"]


def test_unit_rates_are_labelled_demo_placeholders():
    body = client.get("/api/planner/rates").json()
    assert "not official" in body["disclaimer"].lower()
    assert body["items"]
    for row in body["items"]:
        assert row["is_demo"] is True
        assert row["currency"] == "BDT"
        assert row["amount_bdt"] > 0


def test_indicative_cost_and_budget_pack_do_not_claim_official_figures():
    public_id = _issue()
    generated = client.post("/api/planner/interventions/generate")
    assert generated.status_code == 200, generated.text
    items = generated.json()["items"]
    match = next(item for item in items if item["issue_public_id"] == public_id)
    assert match["cost"]["is_indicative"] is True
    assert match["cost"]["total_low_bdt"] < match["cost"]["total_mid_bdt"] < match["cost"]["total_high_bdt"]
    assert "placeholder" in match["assumptions"].lower() or "not" in match["assumptions"].lower()

    small = client.post("/api/planner/compare", json={"budget_bdt": 1})
    large = client.post("/api/planner/compare", json={"budget_bdt": 10_000_000})
    assert small.status_code == 200, small.text
    assert large.status_code == 200, large.text
    assert "indicative" in small.json()["disclaimer"].lower()
    assert small.json()["plans"][0]["included_count"] == 0
    assert large.json()["plans"][0]["included_count"] >= 1
    methods = {plan["method"] for plan in large.json()["plans"]}
    assert methods == {"greedy_value", "greedy_severity", "greedy_equity", "optimal_knapsack"}
