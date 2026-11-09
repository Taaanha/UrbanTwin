"""Building heights for the 3D view.

OSM rarely carries height data for Bangladeshi towns, so most heights here are ESTIMATES by building type.
Every height is labelled with where it came from so the 3D view never presents a guess as a measurement.
"""
import re
from typing import Any

LEVEL_HEIGHT_M = 3.2
DEFAULT_HEIGHT_M = 6.0
ESTIMATE_BY_TYPE_M = {
    "house": 5.0,
    "detached": 5.0,
    "residential": 6.0,
    "hut": 3.0,
    "shed": 3.0,
    "garage": 3.0,
    "roof": 3.5,
    "retail": 6.0,
    "commercial": 9.0,
    "apartments": 15.0,
    "school": 9.0,
    "hospital": 12.0,
    "mosque": 10.0,
    "industrial": 8.0,
    "warehouse": 7.0,
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value))
    if not match:
        return None
    number = float(match.group(1))
    return number if 0 < number <= 400 else None


def building_height(properties: dict | None) -> tuple[float, str]:
    """Return (height in metres, source) where source is osm_height, osm_levels or estimate."""
    props = properties or {}
    height = _number(props.get("height"))
    if height is not None:
        return round(height, 1), "osm_height"
    levels = _number(props.get("levels"))
    if levels is not None:
        return round(levels * LEVEL_HEIGHT_M, 1), "osm_levels"
    return ESTIMATE_BY_TYPE_M.get(str(props.get("building") or "").lower(), DEFAULT_HEIGHT_M), "estimate"
