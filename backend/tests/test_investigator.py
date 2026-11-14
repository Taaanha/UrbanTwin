from io import BytesIO
from base64 import b64decode

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _submit(description: str, lon: str = "91.099", lat: str = "22.869"):
    data = {
        "category": "pothole",
        "severity": "high",
        "location_text": "near the market", "description": description,
        "latitude": lat,
        "longitude": lon,
        "language": "en",
    }
    files = {"files": ("hole.png", BytesIO(PNG), "image/png")}
    response = client.post("/api/reports", data=data, files=files)
    assert response.status_code == 200, response.text
    return response.json()


def test_investigator_finds_nearby_duplicate_and_human_creates_issue():
    first = _submit("Large pothole on Station Road near Maijdee Court.")
    second = _submit("Big pothole on Station Road by Maijdee Court.")

    inspect = client.get(f"/api/investigator/reports/{second['tracking_id']}")
    assert inspect.status_code == 200
    matches = inspect.json()["matches"]
    ids = [item.get("tracking_id") for item in matches]
    assert first["tracking_id"] in ids
    top = next(item for item in matches if item.get("tracking_id") == first["tracking_id"])
    assert top["suggested_label"] in {"possible_duplicate", "uncertain"}
    assert top["score"] >= 40

    verify = client.post(
        "/api/investigator/verify",
        json={
            "tracking_id": first["tracking_id"],
            "decision": "new_candidate_issue",
            "notes": "Officer confirmed a new pothole issue.",
        },
    )
    assert verify.status_code == 200
    assert verify.json()["reports_preserved"] is True
    issue_id = verify.json()["issue_public_id"]
    assert issue_id.startswith("ISS-")

    still_there = client.get(f"/api/reports/track/{first['tracking_id']}")
    assert still_there.status_code == 200
    assert still_there.json()["record_type"] == "citizen_report"

    link = client.post(
        "/api/investigator/verify",
        json={
            "tracking_id": second["tracking_id"],
            "decision": "possible_duplicate",
            "related_tracking_id": first["tracking_id"],
            "score": top["score"],
            "reasons": {"notes": top["reasons"]},
        },
    )
    assert link.status_code == 200
    assert link.json()["reports_preserved"] is True

    both = client.get("/api/reports").json()["items"]
    tracking = {item["tracking_id"] for item in both}
    assert first["tracking_id"] in tracking
    assert second["tracking_id"] in tracking
