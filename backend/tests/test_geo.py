from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_geo_summary_has_expected_layers():
    response = client.get("/api/geo/summary")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "study_areas",
        "admin_boundaries",
        "wards",
        "roads",
        "buildings",
        "water_bodies",
        "drains",
    ):
        assert key in body
        assert isinstance(body[key], int)


def test_wards_are_labelled_demonstration_data():
    response = client.get("/api/geo/wards")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["crs"]["properties"]["name"] == "EPSG:4326"
    assert len(body["features"]) == 9
    for feature in body["features"]:
        assert feature["properties"]["is_demo"] is True
        assert "demonstration" in feature["properties"]["name"].lower()


def test_study_area_is_not_an_official_boundary():
    response = client.get("/api/geo/study-area")
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 1
    notes = features[0]["properties"]["notes"].lower()
    assert "not an official" in notes
