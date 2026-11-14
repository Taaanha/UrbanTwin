from datetime import datetime, timedelta, timezone
from io import BytesIO
from base64 import b64decode

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.investigator import Issue

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


def _new_issue(description: str, lon: str = "91.099", lat: str = "22.869") -> str:
    report = _submit(description, lon, lat)
    verify = client.post(
        "/api/investigator/verify",
        json={
            "tracking_id": report["tracking_id"],
            "decision": "new_candidate_issue",
            "notes": "Lab verification for intelligence tests.",
        },
    )
    assert verify.status_code == 200, verify.text
    public_id = verify.json()["issue_public_id"]
    assert public_id.startswith("ISS-")
    return public_id


def test_intelligence_links_issue_to_osm_road_without_claiming_cause():
    public_id = _new_issue("Pothole near Maijdee Court for road snap test.")
    refreshed = client.post("/api/intelligence/refresh")
    assert refreshed.status_code == 200
    body = client.get(f"/api/intelligence/issues/{public_id}").json()
    assert "not proof of cause" in body["disclaimer"].lower()
    kinds = {item["kind"] for item in body["assets"]}
    roads = client.get("/api/geo/summary").json()["roads"]
    if roads:
        assert "road" in kinds
        road = next(item for item in body["assets"] if item["kind"] == "road")
        assert road["distance_m"] <= 60
        assert "correlation" in road["notes"].lower()
    drains = client.get("/api/geo/summary").json()["drains"]
    if drains == 0:
        assert "drain" not in kinds
        assert "may be missing" in body["drain_limitation"].lower()


def test_possible_recurrence_is_a_time_gap_flag_not_a_failure_verdict():
    first = _new_issue("Older pothole on the same stretch of Station Road.")
    second = _new_issue("Later pothole on the same stretch of Station Road.")
    with SessionLocal() as db:
        issue = db.scalar(select(Issue).where(Issue.public_id == first))
        assert issue is not None
        issue.created_at = datetime.now(timezone.utc) - timedelta(days=21)
        db.commit()
    client.post("/api/intelligence/refresh")
    body = client.get("/api/intelligence/recurrence").json()
    assert "not a confirmed repair failure" in body["note"].lower()
    pairs = {(item["from_public_id"], item["to_public_id"], item["relation_type"]) for item in body["items"]}
    assert (first, second, "possible_recurrence") in pairs
    graph = client.get("/api/intelligence/graph").json()
    assert graph["counts"]["issues"] >= 2
    geojson = client.get("/api/intelligence/geojson").json()
    assert geojson["type"] == "FeatureCollection"
    issue_points = [
        feature for feature in geojson["features"] if feature["properties"]["record_type"] == "verified_issue"
    ]
    assert any(feature["properties"]["public_id"] == second for feature in issue_points)
