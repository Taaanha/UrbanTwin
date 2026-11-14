"""Copernicus GLO-30 elevation for the study window, read straight from the public AWS tile (no extra libraries).

The tile is a Cloud-Optimised GeoTIFF of 32-bit floats. This reads only its header and the few internal tiles that
cover the study window (a fraction of the 33 MB file), then resamples onto the same web-map pixel grid the rest of the
flood code uses, so nothing downstream changes.

Copernicus GLO-30 is a surface model (roofs and tree canopy are included) like the SRTM-based tiles it replaces, but it
has decimal precision instead of whole metres and is more accurate. It is not a bare-earth model.
"""

from __future__ import annotations

import math
import struct
import zlib
from typing import Any

import numpy as np
import requests

TILE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"
SOURCE = "Copernicus GLO-30 DSM (ESA), AWS Open Data"
ATTRIBUTION = (
    "Produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018, "
    "provided under COPERNICUS by the European Union and ESA; all rights reserved."
)
HEADER_BYTES = 262_144

# TIFF tag ids and field sizes used below
_T = {"width": 256, "height": 257, "compression": 259, "tile_w": 322, "tile_h": 323, "offsets": 324, "counts": 325, "predictor": 317, "bits": 258, "format": 339, "scale": 33550, "tie": 33922, "nodata": 42113}
_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8}
_FMT = {1: "B", 3: "H", 4: "I", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q"}


class CopernicusError(RuntimeError):
    pass


def _range(url: str, start: int, end: int, timeout: float) -> bytes:
    try:
        r = requests.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=timeout)
    except requests.RequestException as exc:
        raise CopernicusError(f"Could not reach the Copernicus tile ({type(exc).__name__}).") from exc
    if r.status_code not in (200, 206):
        raise CopernicusError(f"The Copernicus tile request returned HTTP {r.status_code}.")
    return r.content if r.status_code == 206 else r.content[start : end + 1]


def parse_header(blob: bytes, url: str, timeout: float = 30.0) -> dict[str, Any]:
    """Parse the first IFD of a classic little-endian TIFF. Anything else is refused rather than guessed at."""
    if blob[:4] != b"II*\x00":
        raise CopernicusError("The tile is not a classic little-endian GeoTIFF; this reader does not support it.")
    ifd = struct.unpack_from("<I", blob, 4)[0]
    cache = {"blob": blob}

    def get(offset: int, size: int) -> bytes:
        if offset + size <= len(cache["blob"]):
            return cache["blob"][offset : offset + size]
        return _range(url, offset, offset + size - 1, timeout)

    n = struct.unpack("<H", get(ifd, 2))[0]
    entries = get(ifd + 2, 12 * n)
    tags: dict[int, Any] = {}
    for i in range(n):
        tag, typ, count, raw = struct.unpack_from("<HHI4s", entries, 12 * i)
        if typ not in _FMT:
            continue
        size = _SIZES[typ] * count
        data = raw[:size] if size <= 4 else get(struct.unpack("<I", raw)[0], size)
        tags[tag] = struct.unpack("<" + _FMT[typ] * count, data)
    try:
        info = {
            "width": tags[_T["width"]][0],
            "height": tags[_T["height"]][0],
            "compression": tags[_T["compression"]][0],
            "predictor": tags.get(_T["predictor"], (1,))[0],
            "tile_w": tags[_T["tile_w"]][0],
            "tile_h": tags[_T["tile_h"]][0],
            "offsets": tags[_T["offsets"]],
            "counts": tags[_T["counts"]],
            "bits": tags.get(_T["bits"], (32,))[0],
            "sample_format": tags.get(_T["format"], (3,))[0],
            "scale": tags[_T["scale"]],
            "tie": tags[_T["tie"]],
        }
    except KeyError as exc:
        raise CopernicusError("The tile header is missing a field this reader needs.") from exc
    if info["compression"] not in (8, 32946, 1) or info["bits"] != 32 or info["sample_format"] != 3:
        raise CopernicusError("The tile is not 32-bit float with deflate or no compression; this reader does not support it.")
    if info["predictor"] not in (1, 3):
        raise CopernicusError("Unsupported TIFF predictor.")
    return info


def decode_tile(raw: bytes, info: dict[str, Any]) -> np.ndarray:
    data = zlib.decompress(raw) if info["compression"] in (8, 32946) else raw
    w, h = info["tile_w"], info["tile_h"]
    if len(data) != w * h * 4:
        raise CopernicusError("A tile decoded to an unexpected size.")
    if info["predictor"] == 3:
        rows = np.frombuffer(data, dtype=np.uint8).reshape(h, w * 4)
        acc = np.cumsum(rows, axis=1, dtype=np.uint8)  # byte-wise running sum, wraps at 256 as the format requires
        planes = acc.reshape(h, 4, w)  # most significant byte plane first
        little = np.ascontiguousarray(planes[:, ::-1, :].transpose(0, 2, 1))
        return little.view("<f4").reshape(h, w).astype(np.float32)
    return np.frombuffer(data, dtype="<f4").reshape(h, w).astype(np.float32)


def _window(url: str, info: dict[str, Any], west: float, south: float, east: float, north: float, timeout: float) -> tuple[np.ndarray, float, float]:
    """Mosaic of the internal tiles covering the box. Returns (array, lon of left edge, lat of top edge) in pixel-corner terms."""
    sx, sy = info["scale"][0], info["scale"][1]
    x0, y0 = info["tie"][3], info["tie"][4]  # lon/lat of the top-left corner of pixel (0, 0)
    c0 = max(int(math.floor((west - x0) / sx)) - 2, 0)
    c1 = min(int(math.ceil((east - x0) / sx)) + 2, info["width"] - 1)
    r0 = max(int(math.floor((y0 - north) / sy)) - 2, 0)
    r1 = min(int(math.ceil((y0 - south) / sy)) + 2, info["height"] - 1)
    if c1 <= c0 or r1 <= r0:
        raise CopernicusError("The study window is outside this tile.")
    tw, th = info["tile_w"], info["tile_h"]
    across = math.ceil(info["width"] / tw)
    ty0, ty1, tx0, tx1 = r0 // th, r1 // th, c0 // tw, c1 // tw
    mosaic = np.zeros(((ty1 - ty0 + 1) * th, (tx1 - tx0 + 1) * tw), dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            index = ty * across + tx
            start, length = info["offsets"][index], info["counts"][index]
            tile = decode_tile(_range(url, start, start + length - 1, timeout), info)
            mosaic[(ty - ty0) * th : (ty - ty0 + 1) * th, (tx - tx0) * tw : (tx - tx0 + 1) * tw] = tile
    return mosaic, x0 + tx0 * tw * sx, y0 - ty0 * th * sy


def sample_bilinear(grid: np.ndarray, left: float, top: float, sx: float, sy: float, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    fx = (lon - left) / sx - 0.5  # cell centres sit half a pixel in from the corner
    fy = (top - lat) / sy - 0.5
    if fx.min() < 0 or fy.min() < 0 or fx.max() >= grid.shape[1] - 1 or fy.max() >= grid.shape[0] - 1:
        raise CopernicusError("The downloaded window does not cover the whole study area.")
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - ix, fy - iy
    a, b = grid[iy, ix], grid[iy, ix + 1]
    c, d = grid[iy + 1, ix], grid[iy + 1, ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fetch(bbox: tuple[float, float, float, float], zoom: int, world_px, px_lonlat, timeout: float = 30.0) -> tuple[np.ndarray, int, int]:
    """Download and resample the window onto the web-map pixel grid. Returns (elevation, px0, py0)."""
    west, south, east, north = bbox
    if int(west) != int(east) or int(south) != int(north):
        raise CopernicusError("The study window spans more than one 1-degree tile; this reader handles one.")
    url = TILE_URL.format(lat=int(math.floor(south)), lon=int(math.floor(west)))
    info = parse_header(_range(url, 0, HEADER_BYTES - 1, timeout), url, timeout)
    mosaic, left, top = _window(url, info, west, south, east, north, timeout)
    x0, y0 = world_px(west, north)
    x1, y1 = world_px(east, south)
    px0, py0, px1, py1 = int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))
    cols = np.arange(px0, px1) + 0.5
    rows = np.arange(py0, py1) + 0.5
    lon = np.array([px_lonlat(c, py0, zoom)[0] for c in cols])
    lat = np.array([px_lonlat(px0, r, zoom)[1] for r in rows])
    lon_grid, lat_grid = np.meshgrid(lon, lat)
    elev = sample_bilinear(mosaic, left, top, info["scale"][0], info["scale"][1], lon_grid, lat_grid)
    return elev.astype(np.float32), px0, py0
