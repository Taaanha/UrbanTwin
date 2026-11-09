from fastapi.testclient import TestClient

from app.building_height import building_height
from app.main import app
from tests.test_simulation import _seed_buildings, _seed_green

client = TestClient(app)


def test_height_prefers_osm_values_and_labels_estimates():
    assert building_height({"height": "12 m"}) == (12.0, "osm_height")
    assert building_height({"levels": "3"}) == (9.6, "osm_levels")
    assert building_height({"building": "apartments"}) == (15.0, "estimate")
    assert building_height({"building": "yes"}) == (6.0, "estimate")
    assert building_height(None) == (6.0, "estimate")
    assert building_height({"height": "9999"})[1] == "estimate"  # absurd values are ignored
    assert building_height({"height": "tall"})[1] == "estimate"


def test_buildings_endpoint_exposes_height_and_its_source():
    _seed_buildings()
    features = client.get("/api/geo/buildings").json()["features"]
    assert features
    assert all(f["properties"]["height_source"] == "estimate" for f in features)
    assert all(f["properties"]["height_m"] > 0 for f in features)


def test_scenario_buildings_match_the_saved_result():
    _seed_buildings()
    _seed_green()
    run = client.post(
        "/api/simulation/green",
        json={"name": "t", "strategy": "gap_fill", "sites": 3, "trees_per_site": 25, "access_radius_m": 400},
    ).json()
    assert run["result"]["canopy_radius_m"] == 3.0
    data = client.get(f"/api/simulation/scenarios/{run['public_id']}/buildings").json()
    feats = data["features"]
    assert len(feats) == run["result"]["city_before"]["buildings"]
    assert sum(f["properties"]["access_before"] for f in feats) == run["result"]["city_before"]["buildings_with_access"]
    assert sum(f["properties"]["access_after"] for f in feats) == run["result"]["city_after"]["buildings_with_access"]
    assert client.get("/api/simulation/scenarios/NOPE/buildings").status_code == 404
