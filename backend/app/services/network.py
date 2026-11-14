"""Road exposure and ponding (surface drainage) analyses on the same elevation model as the flood what-if.

Both are screening tools, not hydraulic models:
* Road exposure: how much road length sits at or below a water level in the elevation model.
* Ponding: where rain water would collect if it cannot leave, found by filling depressions in the elevation model.
Neither knows about drain pipes, culverts, pumps or blockages, and both inherit the elevation model's
vertical error (see flood.LIMITS). Results are for ranking areas, not for stating depths.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.geo import Drain, Road
from app.services import flood
from app.services import simulation as sim

SAMPLE_STEP_M = 20.0
MIN_DEPTH_RANGE = (0.1, 3.0)
ROAD_LIMITS = [
    "Exposure is read from the elevation model along each road. Culverts, raised embankments and bridges are not modelled, so a road shown as exposed may in fact be raised.",
    "Roads come from OpenStreetMap: coverage and classification are incomplete, and surface type (pucca or katcha) is not in the data.",
    "No traffic, no network connectivity and no detours are modelled, so this cannot say which places are cut off.",
]
PONDING_LIMITS = [
    "A depression in a 30 m elevation model is not a measured pond. Roofs, trees and the +/-2 m vertical error create and hide low spots, so use zones to rank areas, not to quote depths.",
    "The model assumes the only exits are the edges of the study window. Real outfalls (khals, drains, pumps) are not modelled, so ponding is probably overstated near working drains and understated near blocked ones.",
    "Drainage data in the database is very thin, so no drain-capacity or drain-gap result is possible yet.",
]
WHOLE_METRES = "The elevation values in use are whole metres (the source rounds to 1 m), so depressions come out as 1 m, 2 m, 3 m steps and flat ground is poorly resolved. Large low basins, including river channels, are flagged; treat this as a broad low-lying-area screen, not a pond map."
NOT_MODELLED = ["Rainfall intensity and duration", "Drain, culvert and khal capacity", "Blockages and encroachment", "Tides and river levels", "Pumping"]

_CACHE: dict[str, Any] = {}


# ------------------------------------------------------------------ roads

def _road_samples(db: Session, dem: dict[str, Any]) -> list[dict[str, Any]]:
    """Per road: geometry, length in metres and the DEM cell of each sample point. Cached per DEM file and road set."""
    n, top = db.execute(select(func.count(Road.id), func.max(Road.id))).one()
    key = (dem["fetched_at"], n, top)
    hit = _CACHE.get("roads")
    if hit and hit["key"] == key:
        return hit["rows"]
    rows = []
    height, width = dem["elev"].shape
    for road_id, name, highway, geom in db.execute(select(Road.id, Road.name, Road.highway, Road.geom)).all():
        line = to_shape(geom)
        if line.is_empty or line.geom_type != "LineString":
            continue
        projected = sim._proj(line)
        length = float(projected.length)
        if length <= 0:
            continue
        count = max(2, int(length // SAMPLE_STEP_M) + 1)
        rr, cc = [], []
        for i in range(count):
            p = projected.interpolate(i / (count - 1), normalized=True)
            lon, lat = sim.to_deg(p.x, p.y)
            x, y = flood._world_px(lon, lat, dem["zoom"])
            cc.append(int(math.floor(x - dem["px0"])))
            rr.append(int(math.floor(y - dem["py0"])))
        rr_a, cc_a = np.array(rr), np.array(cc)
        inside = (rr_a >= 0) & (rr_a < height) & (cc_a >= 0) & (cc_a < width)
        rows.append(
            {
                "id": road_id,
                "name": name,
                "highway": highway or "unclassified",
                "geometry": mapping(line),
                "length_m": length,
                "rr": np.where(inside, rr_a, 0),
                "cc": np.where(inside, cc_a, 0),
                "inside": inside,
            }
        )
    _CACHE["roads"] = {"key": key, "rows": rows}
    return rows


def road_exposure(db: Session, level_m: float, connected_only: bool = True) -> dict[str, Any]:
    if not flood.LEVEL_MIN_M <= level_m <= flood.LEVEL_MAX_M:
        raise ValueError(f"Water level must be between {flood.LEVEL_MIN_M:g} and {flood.LEVEL_MAX_M:g} m.")
    dem = flood.load_dem()
    err = flood.DEM_VERTICAL_ERROR_M
    central = flood._flooded_mask(dem["elev"], level_m, connected_only)
    high = flood._flooded_mask(dem["elev"], level_m + err, connected_only)
    features, by_class = [], {}
    outside = 0
    for road in _road_samples(db, dem):
        inside = road["inside"]
        if not inside.any():
            outside += 1
            continue
        hit_c = central[road["rr"], road["cc"]] & inside
        hit_h = high[road["rr"], road["cc"]] & inside
        denom = int(inside.sum())
        pct_c, pct_h = hit_c.sum() / denom, hit_h.sum() / denom
        km = road["length_m"] / 1000.0
        agg = by_class.setdefault(road["highway"], {"highway": road["highway"], "roads": 0, "km": 0.0, "exposed_km": 0.0, "possible_km": 0.0})
        agg["roads"] += 1
        agg["km"] += km
        agg["exposed_km"] += float(km * pct_c)
        agg["possible_km"] += float(km * pct_h)
        features.append(
            {
                "type": "Feature",
                "geometry": road["geometry"],
                "properties": {
                    "name": road["name"],
                    "highway": road["highway"],
                    "length_m": round(road["length_m"]),
                    "exposed_pct": round(100 * pct_c),
                    "possible_pct": round(100 * pct_h),
                },
            }
        )
    classes = sorted(({**c, "km": round(c["km"], 2), "exposed_km": round(c["exposed_km"], 2), "possible_km": round(c["possible_km"], 2)} for c in by_class.values()), key=lambda c: -c["km"])
    total = sum(c["km"] for c in classes)
    ranked = sorted((f["properties"] for f in features), key=lambda p: -(p["length_m"] * p["exposed_pct"]))
    return {
        "level_m": level_m,
        "connected_only": connected_only,
        "source": dem["source"],
        "vertical_error_assumed_m": err,
        "disclaimer": "Screening of road length below a water level in a coarse elevation model. Not a flood forecast and not a survey of road condition.",
        "limits": ROAD_LIMITS + flood.LIMITS,
        "not_modelled": NOT_MODELLED + ["Culverts, bridges and road raising", "Connectivity and detours", "Road surface condition"],
        "roads_analysed": len(features),
        "roads_outside_elevation_window": outside,
        "total_km": round(total, 2),
        "exposed_km": {"central": round(float(sum(c["exposed_km"] for c in classes)), 2), "possible": round(float(sum(c["possible_km"] for c in classes)), 2)},
        "by_class": classes,
        "most_exposed": [p for p in ranked if p["exposed_pct"] > 0][:10],
        "roads": {"type": "FeatureCollection", "features": features},
    }


# ------------------------------------------------------------------ ponding

def fill_depressions(elev: np.ndarray) -> np.ndarray:
    """Priority-flood fill (Barnes et al.): raise every closed depression to the level of its lowest exit on the window edge."""
    rows, cols = elev.shape
    filled = elev.astype(np.float64).copy()
    closed = np.zeros(elev.shape, dtype=bool)
    heap: list[tuple[float, int, int]] = []
    for r in range(rows):
        for c in (0, cols - 1):
            if not closed[r, c]:
                closed[r, c] = True
                heapq.heappush(heap, (filled[r, c], r, c))
    for c in range(cols):
        for r in (0, rows - 1):
            if not closed[r, c]:
                closed[r, c] = True
                heapq.heappush(heap, (filled[r, c], r, c))
    while heap:
        z, r, c = heapq.heappop(heap)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if (dr or dc) and 0 <= nr < rows and 0 <= nc < cols and not closed[nr, nc]:
                    closed[nr, nc] = True
                    if filled[nr, nc] < z:
                        filled[nr, nc] = z
                    heapq.heappush(heap, (filled[nr, nc], nr, nc))
    return filled


def _depth(dem: dict[str, Any]) -> np.ndarray:
    key = dem["fetched_at"]
    hit = _CACHE.get("depth")
    if hit and hit["key"] == key:
        return hit["depth"]
    depth = (fill_depressions(dem["elev"]) - dem["elev"]).astype(np.float32)
    _CACHE["depth"] = {"key": key, "depth": depth}
    return depth


def ponding(db: Session, min_depth_m: float = 1.0) -> dict[str, Any]:
    if not MIN_DEPTH_RANGE[0] <= min_depth_m <= MIN_DEPTH_RANGE[1]:
        raise ValueError(f"min_depth_m must be between {MIN_DEPTH_RANGE[0]:g} and {MIN_DEPTH_RANGE[1]:g}.")
    dem = flood.load_dem()
    depth = _depth(dem)
    mask = depth >= min_depth_m
    cache = flood._building_cache(db, dem)
    layers = sim.load_layers(db)
    inside, rr, cc = cache["inside"], cache["rr"], cache["cc"]
    flagged = (mask[rr, cc] & inside) if len(rr) else np.array([], dtype=bool)
    total = len(cache["geoms"])
    per_ward = []
    for j, ward in enumerate(layers.wards):
        members = layers.building_ward == j if len(layers.building_ward) == len(flagged) else np.zeros(len(flagged), dtype=bool)
        n = int(members.sum())
        k = int((flagged & members).sum())
        per_ward.append({"ward": ward["name"], "buildings": n, "in_ponding_zones": k, "pct": round(100 * k / n, 1) if n else None})
    water = flood._water_polygons(dem, mask)
    drains = db.scalar(select(func.count()).select_from(Drain)) or 0
    positive = depth[depth > 0]
    return {
        "min_depth_m": min_depth_m,
        "source": dem["source"],
        "vertical_error_assumed_m": flood.DEM_VERTICAL_ERROR_M,
        "disclaimer": "Where rain would collect in a coarse elevation model if it could only leave through the window edge. A ranking aid, not a map of real ponds or flood depths.",
        "limits": ([WHOLE_METRES] if bool(np.allclose(dem["elev"], np.round(dem["elev"]))) else []) + PONDING_LIMITS + flood.LIMITS,
        "not_modelled": NOT_MODELLED,
        "cells_in_zones_pct": round(100 * float(mask.mean()), 2),
        "depression_cells_pct": round(100 * float((depth > 0).mean()), 2),
        "depth_p95_m": round(float(np.percentile(positive, 95)), 2) if positive.size else 0.0,
        "buildings": {"total": total, "in_zones": int(flagged.sum()), "pct": round(100 * float(flagged.sum()) / total, 1) if total else None, "without_elevation": int((~inside).sum()) if total else 0},
        "per_ward": per_ward,
        "drain_context": {
            "osm_drain_features": drains,
            "usable_for_gap_analysis": drains >= 20,
            "note": "Too few drain features are loaded to say where drains are missing. The 2011 Noakhali Pourashava field-survey map shows the drain network and obstructions but has not been digitized yet.",
        },
        "zones": {"type": "FeatureCollection", "features": [] if water is None else [{"type": "Feature", "geometry": mapping(water), "properties": {}}]},
    }
