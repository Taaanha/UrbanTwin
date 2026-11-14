import struct
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import copernicus, flood

client = TestClient(app)
X0, Y0, STEP, SIZE, TILE = 91.06, 22.91, 0.0001, 1024, 256


def _truth(lon, lat):
    return 3.0 + 40.0 * (lon - 91.06) + 25.0 * (22.91 - lat)  # a smooth ramp in metres


def _encode(tile: np.ndarray, predictor: int) -> bytes:
    h, w = tile.shape
    if predictor == 1:
        return zlib.compress(tile.astype("<f4").tobytes())
    bytes_ = tile.astype("<f4").view(np.uint8).reshape(h, w, 4)
    planes = np.stack([bytes_[:, :, 3 - k] for k in range(4)], axis=1).reshape(h, 4 * w)  # most significant byte first
    diff = planes.copy()
    diff[:, 1:] = planes[:, 1:] - planes[:, :-1]  # uint8 arithmetic wraps like the format
    return zlib.compress(diff.tobytes())


def make_tiff(predictor: int = 3) -> bytes:
    cols = X0 + (np.arange(SIZE) + 0.5) * STEP
    rows = Y0 - (np.arange(SIZE) + 0.5) * STEP
    grid = _truth(cols[None, :], rows[:, None]).astype(np.float32)
    tiles = [_encode(grid[r : r + TILE, c : c + TILE], predictor) for r in range(0, SIZE, TILE) for c in range(0, SIZE, TILE)]
    n_tiles = len(tiles)
    entries = [  # (tag, type, count, values)
        (256, 4, 1, [SIZE]), (257, 4, 1, [SIZE]), (258, 3, 1, [32]), (259, 3, 1, [8]), (317, 3, 1, [predictor]),
        (322, 4, 1, [TILE]), (323, 4, 1, [TILE]), (324, 4, n_tiles, None), (325, 4, n_tiles, [len(t) for t in tiles]),
        (339, 3, 1, [3]), (33550, 12, 3, [STEP, STEP, 0.0]), (33922, 12, 6, [0.0, 0.0, 0.0, X0, Y0, 0.0]),
    ]
    ifd_size = 2 + 12 * len(entries) + 4
    extra_start = 8 + ifd_size
    blobs, cursor, spec = [], extra_start, {}
    for tag, typ, count, values in entries:
        size = {3: 2, 4: 4, 12: 8}[typ] * count
        if size > 4:
            spec[tag] = cursor
            cursor += size
            blobs.append((tag, typ, values))
    data_start = cursor
    offsets, pos = [], data_start
    for t in tiles:
        offsets.append(pos)
        pos += len(t)
    out = bytearray(b"II*\x00" + struct.pack("<I", 8))
    out += struct.pack("<H", len(entries))
    for tag, typ, count, values in entries:
        values = offsets if tag == 324 else values
        size = {3: 2, 4: 4, 12: 8}[typ] * count
        fmt = {3: "H", 4: "I", 12: "d"}[typ]
        if size > 4:
            out += struct.pack("<HHII", tag, typ, count, spec[tag])
        else:
            out += struct.pack("<HHI", tag, typ, count) + struct.pack("<" + fmt * count, *values).ljust(4, b"\x00")
    out += struct.pack("<I", 0)
    for tag, typ, values in blobs:
        values = offsets if tag == 324 else values
        out += struct.pack("<" + {3: "H", 4: "I", 12: "d"}[typ] * len(values), *values)
    for t in tiles:
        out += t
    return bytes(out)


@pytest.fixture()
def served(monkeypatch):
    def install(predictor=3):
        blob = make_tiff(predictor)
        fetched = []

        def fake_range(url, start, end, timeout):
            fetched.append((start, end))
            return blob[start : end + 1]

        monkeypatch.setattr(copernicus, "_range", fake_range)
        return blob, fetched

    return install


@pytest.mark.parametrize("predictor", [3, 1])
def test_reader_matches_the_known_surface_on_the_web_map_grid(served, predictor):
    blob, fetched = served(predictor)
    elev, px0, py0 = copernicus.fetch(flood.padded_bbox(), flood.ZOOM, flood._world_px, flood._px_lonlat)
    assert elev.dtype == np.float32 and elev.shape[0] > 300 and not np.allclose(elev, np.round(elev))
    # compare with the truth at the centre of a few grid pixels
    for r, c in [(0, 0), (150, 120), (elev.shape[0] - 1, elev.shape[1] - 1)]:
        lon, _ = flood._px_lonlat(px0 + c + 0.5, py0 + r + 0.5)
        _, lat = flood._px_lonlat(px0 + c + 0.5, py0 + r + 0.5)
        assert abs(float(elev[r, c]) - _truth(lon, lat)) < 0.01
    assert 1 < len(fetched) - 1 < (SIZE // TILE) ** 2  # the header plus only some of the 16 internal tiles


def test_unsupported_files_are_refused_not_guessed(served):
    with pytest.raises(copernicus.CopernicusError):
        copernicus.parse_header(b"MM\x00*" + b"\x00" * 100, "u")
    with pytest.raises(copernicus.CopernicusError):
        copernicus.fetch((91.9, 22.1, 92.1, 22.2), flood.ZOOM, flood._world_px, flood._px_lonlat)  # spans two tiles


def test_fetch_dem_prefers_copernicus_and_records_source_and_attribution(served, monkeypatch, tmp_path):
    served(3)
    path = tmp_path / "dem.npz"
    dem = flood.fetch_dem(path=path)
    assert dem["source"] == copernicus.SOURCE
    monkeypatch.setattr(flood, "DEM_PATH", path)
    status = flood.status()
    assert "Copernicus" in status["attribution"] and "WorldDEM-30" in status["attribution"]
    assert client.get("/api/simulation/flood/status").json()["available"] is True


def test_fetch_dem_falls_back_to_terrarium_when_copernicus_fails(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise copernicus.CopernicusError("offline")

    monkeypatch.setattr(copernicus, "fetch", boom)
    monkeypatch.setattr(flood, "fetch_terrarium", lambda path=None, timeout=20.0: {"source": "fallback used"})
    assert flood.fetch_dem(path=tmp_path / "x.npz")["source"] == "fallback used"
    assert flood.attribution_for(flood.SOURCE) is None
