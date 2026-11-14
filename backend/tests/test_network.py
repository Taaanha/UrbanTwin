import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services import flood, network
from tests.test_flood import _sloping_dem

client = TestClient(app)


def test_fill_depressions_raises_a_closed_pit_to_its_lowest_exit_and_leaves_slopes_alone():
    elev = np.full((9, 9), 5.0, dtype=np.float32)
    elev[3:6, 3:6] = 2.0  # closed pit inside a flat rim
    depth = network.fill_depressions(elev) - elev
    assert depth[4, 4] == 3.0 and depth[0, 0] == 0.0
    slope = np.tile(np.arange(9, dtype=np.float32), (9, 1))
    assert float((network.fill_depressions(slope) - slope).max()) == 0.0
    open_pit = elev.copy()
    open_pit[4, 0:4] = 2.0  # a channel to the window edge drains the pit
    assert float((network.fill_depressions(open_pit) - open_pit)[4, 4]) == 0.0


def test_ponding_endpoint_flags_pits_and_is_honest_about_limits(monkeypatch, tmp_path):
    elev = _sloping_dem(monkeypatch, tmp_path)
    rows, cols = elev.shape
    path = tmp_path / "dem.npz"
    dem = flood.load_dem(path)
    pit = elev.copy()
    pit[rows // 2 - 3 : rows // 2 + 3, cols // 2 - 3 : cols // 2 + 3] -= 5.0
    flood.save_dem(pit, dem["px0"], dem["py0"], source="synthetic pit", path=path)
    body = client.get("/api/simulation/drainage/ponding", params={"min_depth_m": 1}).json()
    assert body["cells_in_zones_pct"] > 0 and body["zones"]["features"]
    assert not any("whole metres" in line for line in body["limits"])  # decimal elevations: no rounding warning
    flood.save_dem(np.round(pit), dem["px0"], dem["py0"], source="synthetic whole metres", path=path)
    rounded = client.get("/api/simulation/drainage/ponding", params={"min_depth_m": 1}).json()
    assert any("whole metres" in line for line in rounded["limits"])
    assert body["drain_context"]["usable_for_gap_analysis"] is False and body["drain_context"]["osm_drain_features"] == 0
    assert len(body["per_ward"]) == 9 and "ranking aid" in body["disclaimer"]
    assert client.get("/api/simulation/drainage/ponding", params={"min_depth_m": 99}).status_code == 400


def test_road_exposure_rises_with_water_level_and_lists_worst_roads(monkeypatch, tmp_path):
    _sloping_dem(monkeypatch, tmp_path)
    low = client.get("/api/simulation/roads", params={"level_m": 1.0}).json()
    high = client.get("/api/simulation/roads", params={"level_m": 6.0}).json()
    assert low["roads_analysed"] == 2  # the two roads seeded by conftest
    assert high["exposed_km"]["central"] > low["exposed_km"]["central"] >= 0
    assert high["most_exposed"] and high["most_exposed"][0]["exposed_pct"] > 0
    assert any("Culverts" in line for line in high["limits"]) and "Connectivity" in " ".join(high["not_modelled"])
    feature = high["roads"]["features"][0]["properties"]
    assert set(feature) == {"name", "highway", "length_m", "exposed_pct", "possible_pct"}
    assert client.get("/api/simulation/roads", params={"level_m": 99}).status_code == 400


def test_network_endpoints_report_missing_elevation(monkeypatch, tmp_path):
    monkeypatch.setattr(flood, "DEM_PATH", tmp_path / "missing.npz")
    assert client.get("/api/simulation/roads", params={"level_m": 1}).status_code == 409
    assert client.get("/api/simulation/drainage/ponding").status_code == 409
