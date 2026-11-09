import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import flood
from tests.test_simulation import _seed_buildings

client = TestClient(app)


def _sloping_dem(monkeypatch, tmp_path):
    """Synthetic terrain rising 0.02 m per pixel from west to east (about 1 m to 8 m across the window)."""
    west, south, east, north = flood.padded_bbox()
    x0, y0 = flood._world_px(west, north)
    x1, y1 = flood._world_px(east, south)
    px0, py0 = int(x0), int(y0)
    cols, rows = int(x1) - px0 + 1, int(y1) - py0 + 1
    elev = np.tile(1.0 + 0.02 * np.arange(cols, dtype=np.float32), (rows, 1))
    path = tmp_path / "dem.npz"
    flood.save_dem(elev, px0, py0, source="synthetic test terrain", path=path)
    monkeypatch.setattr(flood, "DEM_PATH", path)
    return elev


def test_status_and_what_if_say_so_when_no_elevation_data(monkeypatch, tmp_path):
    monkeypatch.setattr(flood, "DEM_PATH", tmp_path / "missing.npz")
    status = client.get("/api/simulation/flood/status").json()
    assert status["available"] is False and "fetch_dem" in status["message"]
    response = client.get("/api/simulation/flood", params={"level_m": 3})
    assert response.status_code == 409
    assert "Download the elevation data" in response.json()["detail"]


def test_status_reports_percentiles_and_the_surface_model_warning(monkeypatch, tmp_path):
    _sloping_dem(monkeypatch, tmp_path)
    status = client.get("/api/simulation/flood/status").json()
    assert status["available"] is True and status["source"] == "synthetic test terrain"
    assert status["ground_min_m"] <= status["ground_p5_m"] <= status["ground_p25_m"] <= status["ground_median_m"] <= status["ground_p95_m"] <= status["ground_max_m"]
    assert any("surface model" in text for text in status["limits"])


def test_rising_water_floods_more_buildings_and_reports_a_range(monkeypatch, tmp_path):
    _sloping_dem(monkeypatch, tmp_path)
    _seed_buildings()
    results = {lvl: client.get("/api/simulation/flood", params={"level_m": lvl}).json() for lvl in (-1, 3, 4.5, 30)}
    counts = {lvl: r["flooded_buildings"]["central"] for lvl, r in results.items()}
    assert counts[-1] == 0
    assert counts[30] == 100
    assert counts[-1] <= counts[3] <= counts[4.5] <= counts[30]
    mid = results[3]
    f = mid["flooded_buildings"]
    assert f["low"] <= f["central"] <= f["high"]
    assert f["low"] < f["high"]  # the +/-2 m assumption must widen the range on sloping ground
    assert mid["vertical_error_assumed_m"] == 2.0
    assert any("not a forecast" in text.lower() for text in mid["limits"] + [mid["disclaimer"]])
    feats = mid["buildings"]["features"]
    assert len(feats) == 100
    assert sum(x["properties"]["flooded"] for x in feats) == f["central"]
    assert all(x["properties"]["depth_m"] >= 0 for x in feats if x["properties"]["flooded"])
    assert mid["water"]["features"]  # some water polygon is returned


def test_connected_mode_ignores_isolated_pits_that_pooling_mode_counts():
    elev = np.full((20, 20), 10.0, dtype=np.float32)
    elev[8:10, 8:10] = 0.0  # a pit surrounded by high ground
    elev[:, 0] = 0.0  # low ground touching the window edge
    assert flood._flooded_mask(elev, 1.0, connected_only=False)[8, 8]
    connected = flood._flooded_mask(elev, 1.0, connected_only=True)
    assert not connected[8, 8]
    assert connected[5, 0]


def test_level_is_validated(monkeypatch, tmp_path):
    _sloping_dem(monkeypatch, tmp_path)
    assert client.get("/api/simulation/flood", params={"level_m": 99}).status_code == 400


def test_terrarium_decoding():
    # 100 m = 32868 -> R=128, G=100, B=0
    rgb = np.array([[[128, 100, 0]]], dtype=np.uint8)
    assert float(flood.decode_terrarium(rgb)[0, 0]) == pytest.approx(100.0)
