from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

from base64 import b64decode

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _submit(**overrides):
    data = {
        "category": "pothole",
        "severity": "high",
        "location_text": "near the market", "description": "Large pothole on Station Road near the court.",
        "latitude": "22.869",
        "longitude": "91.099",
        "language": "en",
        "reporter_name": "Lab tester",
    }
    data.update(overrides)
    files = {"files": ("hole.png", BytesIO(PNG), "image/png")}
    return client.post("/api/reports", data=data, files=files)


def test_submit_report_returns_tracking_id():
    response = _submit()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tracking_id"].startswith("UT-")
    assert body["record_type"] == "citizen_report"
    assert body["is_verified_issue"] is False
    assert body["status"] == "submitted"
    assert len(body["evidence"]) == 1


def test_reject_non_image_upload():
    data = {
        "category": "pothole",
        "severity": "low",
        "location_text": "near the market", "description": "Not an image should be rejected.",
        "latitude": "22.869",
        "longitude": "91.099",
    }
    files = {"files": ("notes.txt", BytesIO(b"hello world"), "text/plain")}
    response = client.post("/api/reports", data=data, files=files)
    assert response.status_code == 400


def test_track_and_filter_and_status_update():
    created = _submit(severity="critical").json()
    tracking_id = created["tracking_id"]

    tracked = client.get(f"/api/reports/track/{tracking_id}")
    assert tracked.status_code == 200
    assert tracked.json()["tracking_id"] == tracking_id

    geo = client.get("/api/reports/geojson", params={"severity": "critical"})
    assert geo.status_code == 200
    ids = [f["properties"]["tracking_id"] for f in geo.json()["features"]]
    assert tracking_id in ids

    patched = client.patch(
        f"/api/reports/track/{tracking_id}/status",
        json={"status": "acknowledged"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "acknowledged"
    assert patched.json()["is_verified_issue"] is False
