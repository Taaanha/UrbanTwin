"""Water-level "what if" on ground height from a public elevation model (DEM).

This is NOT a flood forecast. It answers one geometric question: if water stood at height H metres
(in the DEM's datum), which ground cells and which buildings lie at or below H?
Stated limits (also returned to the UI):
- Terrain comes from the keyless AWS "Terrarium" tiles (SRTM-derived). In flat deltas such as
  Noakhali the vertical error can be as large as the relief itself, so every result carries a range.
- No rainfall, drainage, tides, embankments, culverts or buildings-as-obstacles are modelled.
- With connected_only the water has to reach a cell from the edge of the study window through
  neighbouring low cells; otherwise isolated low spots are counted too (a rain-pooling reading).
"""

from __future__ import annotations

import io
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from geoalchemy2.shape import to_shape
from shapely.geometry import box, mapping
from shapely.ops import unary_union
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.building_height import building_height
from app.geo_constants import STUDY_BBOX
from app.models.geo import Building

ZOOM = 13  # roughly 19 m per pixel at this latitude; the source data is coarser (about 30 m)
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MARGIN_DEG = 0.006
DEM_VERTICAL_ERROR_M = 2.0  # assumed, not measured here: used for the low/high range
LEVEL_MIN_M, LEVEL_MAX_M = -5.0, 30.0
DEM_PATH = Path(__file__).resolve().parents[2] / "data" / "dem_noakhali.npz"
SOURCE = "AWS Terrain Tiles (Terrarium, SRTM-derived), open data"

LIMITS = [
    "Terrain heights come from a coarse global model (about 30 m cells); vertical error in flat delta land is often 1-4 m.",
    f"The low/high range assumes a vertical error of +/-{DEM_VERTICAL_ERROR_M:g} m. That figure is an assumption, not a measurement for Noakhali.",
    "This is a surface model: tree canopy and roofs raise the readings by several metres in Bangladeshi towns, so absolute heights are NOT bare-ground heights. Judge the water rise above the low-lying ground, not the absolute level. A bare-earth model (for example FABDEM) or a local survey is needed for real planning.",
    "No rainfall, drainage network, tides, embankments or culverts are modelled. This is a water-level what-if, not a forecast.",
    "Ground height is sampled at each building centre; floor level and plinth height are unknown.",
]


class DemUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------- geometry of the tile grid

def _world_px(lon: float, lat: float, z: int = ZOOM) -> tuple[float, float]:
    scale = 256 * 2**z
    x = (lon + 180.0) / 360.0 * scale
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale
    return x, y


def _px_lonlat(px: float, py: float, z: int = ZOOM) -> tuple[float, float]:
    scale = 256 * 2**z
    lon = px / scale * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / scale))))
    return lon, lat


def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    return r * 256.0 + g + b / 256.0 - 32768.0


def padded_bbox() -> tuple[float, float, float, float]:
    w, s, e, n = STUDY_BBOX
    return w - MARGIN_DEG, s - MARGIN_DEG, e + MARGIN_DEG, n + MARGIN_DEG


# --------------------------------------------------------------- storage

def save_dem(elev: np.ndarray, px0: int, py0: int, *, source: str = SOURCE, path: Path | None = None) -> None:
    target = path or DEM_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        target,
        elev=elev.astype(np.float32),
        px0=np.int64(px0),
        py0=np.int64(py0),
        zoom=np.int64(ZOOM),
        source=np.array(source),
        fetched_at=np.array(datetime.now(timezone.utc).isoformat()),
    )


def load_dem(path: Path | None = None) -> dict[str, Any]:
    target = path or DEM_PATH
    if not target.exists():
        raise DemUnavailable("No elevation data downloaded yet.")
    with np.load(target, allow_pickle=False) as data:
        return {
            "elev": data["elev"],
            "px0": int(data["px0"]),
            "py0": int(data["py0"]),
            "zoom": int(data["zoom"]),
            "source": str(data["source"]),
            "fetched_at": str(data["fetched_at"]),
        }


def fetch_dem(path: Path | None = None, timeout: float = 20.0, prefer: str = "copernicus") -> dict[str, Any]:
    """Download elevation for the study window and cache it. Copernicus GLO-30 first (decimal precision); Terrarium if that fails."""
    if prefer == "copernicus":
        from app.services import copernicus

        try:
            elev, px0, py0 = copernicus.fetch(padded_bbox(), ZOOM, _world_px, _px_lonlat, timeout=max(timeout, 30.0))
        except (copernicus.CopernicusError, ValueError, OSError):
            pass  # fall back to the older source below rather than leave the page without elevation
        else:
            save_dem(elev, px0, py0, source=copernicus.SOURCE, path=path)
            return load_dem(path)
    return fetch_terrarium(path, timeout)


def fetch_terrarium(path: Path | None = None, timeout: float = 20.0) -> dict[str, Any]:
    """Download the Terrarium tiles that cover the study window and cache them as one array."""
    import requests
    from PIL import Image

    west, south, east, north = padded_bbox()
    x0, y0 = _world_px(west, north)
    x1, y1 = _world_px(east, south)
    px0, py0, px1, py1 = int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1))
    tx0, ty0, tx1, ty1 = px0 // 256, py0 // 256, px1 // 256, py1 // 256
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float32)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            url = TILE_URL.format(z=ZOOM, x=tx, y=ty)
            try:
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                rgb = np.array(Image.open(io.BytesIO(response.content)).convert("RGB"))
            except Exception as exc:  # network, HTTP or image decoding problems
                raise DemUnavailable(f"Could not download elevation tile {tx}/{ty}: {exc}") from exc
            mosaic[(ty - ty0) * 256 : (ty - ty0 + 1) * 256, (tx - tx0) * 256 : (tx - tx0 + 1) * 256] = decode_terrarium(rgb)
    elev = mosaic[py0 - ty0 * 256 : py1 - ty0 * 256, px0 - tx0 * 256 : px1 - tx0 * 256]
    save_dem(elev, px0, py0, path=path)
    return load_dem(path)


def status(path: Path | None = None) -> dict[str, Any]:
    try:
        dem = load_dem(path)
    except DemUnavailable:
        return {
            "available": False,
            "message": "No elevation data yet. Use 'Download elevation' (needs internet on the machine running the API) or run: python -m scripts.fetch_dem",
            "limits": LIMITS,
        }
    elev = dem["elev"]
    return {
        "available": True,
        "source": dem["source"],
        "fetched_at": dem["fetched_at"],
        "cells": int(elev.size),
        "ground_min_m": round(float(elev.min()), 1),
        "ground_max_m": round(float(elev.max()), 1),
        "ground_median_m": round(float(np.median(elev)), 1),
        "ground_p5_m": round(float(np.percentile(elev, 5)), 1),
        "ground_p25_m": round(float(np.percentile(elev, 25)), 1),
        "ground_p95_m": round(float(np.percentile(elev, 95)), 1),
        "baseline_note": "Rise is measured from the 5th-percentile height of this window (the typical low-lying ground in this surface model), not from sea level.",
        "vertical_error_assumed_m": DEM_VERTICAL_ERROR_M,
        "attribution": attribution_for(dem["source"]),
        "limits": LIMITS,
    }


def attribution_for(source: str) -> str | None:
    if "Copernicus" in source:
        from app.services import copernicus

        return copernicus.ATTRIBUTION
    return None


# --------------------------------------------------------------- the what-if

def _flooded_mask(elev: np.ndarray, level: float, connected_only: bool) -> np.ndarray:
    low = elev <= level
    if not connected_only:
        return low
    rows, cols = low.shape
    reached = np.zeros_like(low)
    queue: deque[tuple[int, int]] = deque()
    for r in range(rows):
        for c in (0, cols - 1):
            if low[r, c] and not reached[r, c]:
                reached[r, c] = True
                queue.append((r, c))
    for c in range(cols):
        for r in (0, rows - 1):
            if low[r, c] and not reached[r, c]:
                reached[r, c] = True
                queue.append((r, c))
    while queue:
        r, c = queue.popleft()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and low[nr, nc] and not reached[nr, nc]:
                    reached[nr, nc] = True
                    queue.append((nr, nc))
    return reached


def _water_polygons(dem: dict[str, Any], mask: np.ndarray):
    """Merge runs of flooded cells into rectangles, then union and simplify."""
    z, px0, py0 = dem["zoom"], dem["px0"], dem["py0"]
    rects = []
    for r in range(mask.shape[0]):
        c = 0
        row = mask[r]
        while c < mask.shape[1]:
            if row[c]:
                start = c
                while c < mask.shape[1] and row[c]:
                    c += 1
                west, north = _px_lonlat(px0 + start, py0 + r, z)
                east, south = _px_lonlat(px0 + c, py0 + r + 1, z)
                rects.append(box(west, south, east, north))
            else:
                c += 1
    if not rects:
        return None
    return unary_union(rects).simplify(0.000008)


_CACHE: dict[str, Any] = {}


def _building_cache(db: Session, dem: dict[str, Any]) -> dict[str, Any]:
    """Footprints, heights and ground height per building. Built once per elevation file and building set."""
    n, top, osm = db.execute(select(func.count(Building.id), func.max(Building.id), func.sum(Building.osm_id))).one()
    key = (dem["fetched_at"], dem["source"], n, top, osm)
    hit = _CACHE.get("buildings")
    if hit and hit["key"] == key:
        return hit
    elev = dem["elev"]
    height_rows, width_cols = elev.shape
    geoms, heights, sources, rows_idx, cols_idx = [], [], [], [], []
    for geom, props in db.execute(select(Building.geom, Building.properties).order_by(Building.id)):
        shape = to_shape(geom)
        c = shape.centroid
        x, y = _world_px(c.x, c.y, dem["zoom"])
        cols_idx.append(int(math.floor(x - dem["px0"])))
        rows_idx.append(int(math.floor(y - dem["py0"])))
        height, source = building_height(props)
        geoms.append(mapping(shape))
        heights.append(height)
        sources.append(source)
    rr, cc = np.array(rows_idx, dtype=int), np.array(cols_idx, dtype=int)
    inside = (rr >= 0) & (rr < height_rows) & (cc >= 0) & (cc < width_cols)
    rr, cc = np.where(inside, rr, 0), np.where(inside, cc, 0)
    ground = np.where(inside, elev[rr, cc], np.nan) if len(rr) else np.array([])
    hit = {"key": key, "geoms": geoms, "heights": heights, "sources": sources, "rr": rr, "cc": cc, "inside": inside, "ground": ground}
    _CACHE["buildings"] = hit
    return hit


def run(db: Session, level_m: float, connected_only: bool = True, path: Path | None = None) -> dict[str, Any]:
    if not LEVEL_MIN_M <= level_m <= LEVEL_MAX_M:
        raise ValueError(f"Water level must be between {LEVEL_MIN_M:g} and {LEVEL_MAX_M:g} m.")
    dem = load_dem(path)
    elev = dem["elev"]
    err = DEM_VERTICAL_ERROR_M

    masks = {
        "low": _flooded_mask(elev, level_m - err, connected_only),
        "central": _flooded_mask(elev, level_m, connected_only),
        "high": _flooded_mask(elev, level_m + err, connected_only),
    }
    cache = _building_cache(db, dem)
    inside, rr, cc, ground = cache["inside"], cache["rr"], cache["cc"], cache["ground"]
    flags = {k: (m[rr, cc] & inside) if len(rr) else np.array([], dtype=bool) for k, m in masks.items()}
    counts = {k: int(v.sum()) for k, v in flags.items()}
    total = len(cache["geoms"])
    outside = int((~inside).sum()) if total else 0

    features = []
    for i in range(total):
        g = None if not inside[i] else float(ground[i])
        features.append(
            {
                "type": "Feature",
                "geometry": cache["geoms"][i],
                "properties": {
                    "height_m": cache["heights"][i],
                    "height_source": cache["sources"][i],
                    "ground_m": None if g is None else round(g, 1),
                    "depth_m": None if g is None else round(max(level_m - g, 0.0), 2),
                    "flooded": bool(flags["central"][i]),
                    "flooded_possible": bool(flags["high"][i]),
                },
            }
        )

    cell_area_m2 = ((256 * 2**dem["zoom"]) ** -1 * 360.0 * 111_320.0 * math.cos(math.radians(22.87))) ** 2
    water = _water_polygons(dem, masks["central"])
    cells = {k: int(m.sum()) for k, m in masks.items()}
    return {
        "level_m": level_m,
        "connected_only": connected_only,
        "source": dem["source"],
        "attribution": attribution_for(dem["source"]),
        "fetched_at": dem["fetched_at"],
        "vertical_error_assumed_m": err,
        "disclaimer": "Water-level what-if on a coarse elevation model. Not a flood forecast and not a measured flood extent.",
        "limits": LIMITS,
        "buildings_total": total,
        "buildings_without_elevation": outside,
        "flooded_buildings": {"low": counts["low"], "central": counts["central"], "high": counts["high"]},
        "flooded_pct": {k: (round(100 * v / total, 1) if total else None) for k, v in counts.items()},
        "flooded_area_km2": {k: round(v * cell_area_m2 / 1e6, 3) for k, v in cells.items()},
        "water": {
            "type": "FeatureCollection",
            "features": [] if water is None else [{"type": "Feature", "geometry": mapping(water), "properties": {}}],
        },
        "buildings": {"type": "FeatureCollection", "features": features},
    }
