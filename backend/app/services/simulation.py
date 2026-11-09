"""Green-space coverage and accessibility scenarios (transparent geometry only)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, pi, radians, sqrt
from typing import Any

import numpy as np
import shapely
from shapely import wkb
from shapely.geometry import Point
from shapely.ops import transform, unary_union
from shapely.prepared import prep
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.geo_constants import STUDY_CENTER
from app.models.geo import Building, Ward
from app.models.planner import UnitRate
from app.models.simulation import GreenSpace, Scenario
from app.simulation_constants import (
    ACCESS_RADIUS_M,
    ASSUMPTIONS,
    CANOPY_RADIUS_M,
    DISCLAIMER,
    MAX_CANDIDATES,
    MAX_SITES,
    SAMPLE_SEED,
    TREES_PER_SITE,
)

LON0, LAT0 = STUDY_CENTER
KX = 111_320.0 * cos(radians(LAT0))
KY = 110_574.0


def to_m(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def to_deg(x: float, y: float) -> tuple[float, float]:
    return (x / KX + LON0, y / KY + LAT0)


def _proj(geom):
    return transform(lambda x, y, z=None: ((np.asarray(x) - LON0) * KX, (np.asarray(y) - LAT0) * KY), geom)


@dataclass
class Layers:
    wards: list[dict[str, Any]]  # id, name, poly(projected), prepared
    centroids: np.ndarray  # shape (n, 2) metres
    building_ward: np.ndarray  # ward index per building, -1 outside
    greens: list[Any]  # projected polygons
    green_is_demo: bool


def load_layers(db: Session) -> Layers:
    wards = []
    for ward_id, name, number, geom in db.execute(
        select(Ward.id, Ward.name, Ward.ward_number, func.ST_AsBinary(Ward.geom)).order_by(Ward.ward_number)
    ):
        poly = _proj(wkb.loads(bytes(geom)))
        wards.append({"id": ward_id, "name": name, "number": number, "poly": poly, "prep": prep(poly)})

    rows = db.execute(
        select(func.ST_X(func.ST_Centroid(Building.geom)), func.ST_Y(func.ST_Centroid(Building.geom))).order_by(Building.id)
    ).all()
    coords = np.array([to_m(float(x), float(y)) for x, y in rows], dtype=float) if rows else np.zeros((0, 2))
    building_ward = np.full(len(coords), -1, dtype=int)
    for j, ward in enumerate(wards):  # first matching ward wins, as before
        if len(coords):
            hit = shapely.contains_xy(ward["poly"], coords[:, 0], coords[:, 1]) & (building_ward == -1)
            building_ward[hit] = j

    greens = []
    demo_flags = []
    for geom, is_demo in db.execute(select(func.ST_AsBinary(GreenSpace.geom), GreenSpace.is_demo)):
        shape = wkb.loads(bytes(geom))
        if not shape.is_valid:
            shape = shape.buffer(0)
        greens.append(_proj(shape))
        demo_flags.append(bool(is_demo))
    return Layers(wards, coords, building_ward, greens, bool(demo_flags) and all(demo_flags))


def _disc(x: float, y: float, trees: int):
    radius = sqrt(trees * pi * CANOPY_RADIUS_M**2 / pi)  # area = trees * pi r^2 -> disc radius
    return Point(x, y).buffer(radius, 16)


def _metrics(layers: Layers, green_union, access_radius: float) -> dict[str, Any]:
    zone = green_union.buffer(access_radius) if green_union is not None and not green_union.is_empty else None
    covered = np.zeros(len(layers.centroids), dtype=bool)
    if zone is not None and len(layers.centroids):
        covered = np.asarray(shapely.contains_xy(zone, layers.centroids[:, 0], layers.centroids[:, 1]), dtype=bool)
    per_ward = []
    for j, ward in enumerate(layers.wards):
        mask = layers.building_ward == j
        total = int(mask.sum())
        ok = int((covered & mask).sum())
        area = ward["poly"].area
        green_area = 0.0
        if green_union is not None and not green_union.is_empty:
            green_area = ward["poly"].intersection(green_union).area
        per_ward.append(
            {
                "ward_id": ward["id"],
                "ward": ward["name"],
                "area_km2": round(area / 1e6, 3),
                "green_m2": round(green_area, 1),
                "green_pct": round(100 * green_area / area, 2) if area else 0.0,
                "buildings": total,
                "buildings_with_access": ok,
                "access_pct": round(100 * ok / total, 1) if total else None,
            }
        )
    total_b = len(layers.centroids)
    return {
        "per_ward": per_ward,
        "city": {
            "buildings": total_b,
            "buildings_with_access": int(covered.sum()),
            "access_pct": round(100 * covered.sum() / total_b, 1) if total_b else None,
            "green_m2": round(sum(w["green_m2"] for w in per_ward), 1),
        },
        "_covered": covered,
    }


def _green_union(layers: Layers, extra=()):
    parts = list(layers.greens) + list(extra)
    return unary_union(parts) if parts else None


def baseline(db: Session, access_radius: float = ACCESS_RADIUS_M) -> dict[str, Any]:
    layers = load_layers(db)
    result = _metrics(layers, _green_union(layers), access_radius)
    result.pop("_covered")
    return {
        "disclaimer": DISCLAIMER,
        "assumptions": ASSUMPTIONS,
        "access_radius_m": access_radius,
        "green_features": len(layers.greens),
        "green_is_demo": layers.green_is_demo,
        "data_warning": (
            "No green-space polygons are loaded. Import OSM green spaces or run the demo seed; "
            "results below only reflect missing data."
            if not layers.greens
            else None
        ),
        **result,
    }


def _gap_fill_sites(layers: Layers, count: int, trees: int, access_radius: float, ward_id: int | None, base_union):
    """Greedy maximum-coverage: each pick covers the most still-uncovered buildings."""
    metrics = _metrics(layers, base_union, access_radius)
    covered = metrics["_covered"].copy()
    allowed = np.ones(len(covered), dtype=bool)
    if ward_id is not None:
        idx = [j for j, w in enumerate(layers.wards) if w["id"] == ward_id]
        if not idx:
            raise ValueError("Unknown ward_id.")
        allowed = layers.building_ward == idx[0]
    uncovered_idx = np.where(~covered & allowed)[0]
    if len(uncovered_idx) == 0:
        return []
    rng = random.Random(SAMPLE_SEED)
    cand_idx = list(uncovered_idx)
    if len(cand_idx) > MAX_CANDIDATES:
        cand_idx = rng.sample(cand_idx, MAX_CANDIDATES)
    candidates = layers.centroids[cand_idx]
    targets_idx = np.where(~covered)[0]
    targets = layers.centroids[targets_idx]
    reach = access_radius
    dx = candidates[:, None, 0] - targets[None, :, 0]
    dy = candidates[:, None, 1] - targets[None, :, 1]
    within = (dx * dx + dy * dy) <= reach * reach  # (cand, targets)
    alive = np.ones(len(targets), dtype=bool)
    sites = []
    for _ in range(count):
        gains = (within & alive[None, :]).sum(axis=1)
        best = int(gains.argmax())
        if gains[best] <= 0:
            break
        x, y = candidates[best]
        alive &= ~within[best]
        sites.append({"x": float(x), "y": float(y), "newly_covered": int(gains[best])})
    return sites


def tree_rate(db: Session) -> tuple[float | None, str]:
    row = db.scalar(select(UnitRate).where(UnitRate.action_code == "tree_planting"))
    if row is None:
        return None, "No tree_planting unit rate loaded yet (open City Planner once to seed rates)."
    return row.amount_bdt, "Lab placeholder rate from City Planner, not an official price."


RADIUS_FACTORS = (0.75, 1.0, 1.25)  # walking routes are longer than straight lines; a few metres of slack the other way


def _sensitivity(layers: Layers, discs, radius: float) -> dict[str, Any]:
    """Re-run the same coverage rule at other access distances to show how much the answer depends on that assumption."""
    rows = []
    for factor in RADIUS_FACTORS:
        r = radius * factor
        before = _metrics(layers, _green_union(layers), r)["city"]["access_pct"]
        after = _metrics(layers, _green_union(layers, discs), r)["city"]["access_pct"]
        rows.append(
            {
                "factor": factor,
                "access_radius_m": round(r),
                "access_before_pct": before,
                "access_after_pct": after,
                "gain_points": round(after - before, 1) if before is not None and after is not None else None,
            }
        )
    afters = [r["access_after_pct"] for r in rows if r["access_after_pct"] is not None]
    gains = [r["gain_points"] for r in rows if r["gain_points"] is not None]
    central = next((r for r in rows if r["factor"] == 1.0), None)
    return {
        "basis": (
            "Same coverage rule re-run with the access distance scaled by 0.75x, 1x and 1.25x, "
            "because the straight-line distance used here understates real walking distance."
        ),
        "access_after_pct": {
            "low": min(afters) if afters else None,
            "central": central["access_after_pct"] if central else None,
            "high": max(afters) if afters else None,
        },
        "gain_points": {"low": min(gains) if gains else None, "high": max(gains) if gains else None},
        "rows": rows,
        "not_modelled": [
            "Tree survival and canopy growth",
            "Whether a proposed site is actually available land",
            "Walking routes, walls, ponds and roads",
            "Errors in the building and green-space layers themselves",
        ],
    }


def run_green_scenario(
    db: Session,
    *,
    name: str,
    strategy: str,
    sites_count: int,
    trees_per_site: int = TREES_PER_SITE,
    access_radius: float = ACCESS_RADIUS_M,
    ward_id: int | None = None,
    manual_sites: list[tuple[float, float]] | None = None,
    actor: str = "staff",
) -> Scenario:
    layers = load_layers(db)
    base_union = _green_union(layers)
    before = _metrics(layers, base_union, access_radius)

    if strategy == "manual":
        chosen = [dict(zip(("x", "y"), to_m(lon, lat)), newly_covered=None) for lon, lat in (manual_sites or [])]
    elif strategy == "gap_fill":
        chosen = _gap_fill_sites(layers, min(sites_count, MAX_SITES), trees_per_site, access_radius, ward_id, base_union)
    else:
        raise ValueError("strategy must be gap_fill or manual")

    discs = [_disc(s["x"], s["y"], trees_per_site) for s in chosen]
    after = _metrics(layers, _green_union(layers, discs), access_radius)
    uncertainty = _sensitivity(layers, discs, access_radius)

    site_rows = []
    for s in chosen:
        lon, lat = to_deg(s["x"], s["y"])
        ward = next((w["name"] for w in layers.wards if w["prep"].contains(Point(s["x"], s["y"]))), "outside wards")
        site_rows.append(
            {"longitude": round(lon, 6), "latitude": round(lat, 6), "ward": ward, "trees": trees_per_site, "newly_covered_buildings": s["newly_covered"]}
        )

    total_trees = trees_per_site * len(chosen)
    rate, rate_note = tree_rate(db)
    wards = []
    for b, a in zip(before["per_ward"], after["per_ward"]):
        wards.append(
            {
                "ward_id": b["ward_id"],
                "ward": b["ward"],
                "green_pct_before": b["green_pct"],
                "green_pct_after": a["green_pct"],
                "access_pct_before": b["access_pct"],
                "access_pct_after": a["access_pct"],
                "buildings": b["buildings"],
            }
        )
    result = {
        "disclaimer": DISCLAIMER,
        "strategy": strategy,
        "sites": site_rows,
        "canopy_radius_m": CANOPY_RADIUS_M,
        "total_trees": total_trees,
        "indicative_planting_cost_bdt": round(total_trees * rate, 2) if rate is not None else None,
        "cost_note": rate_note,
        "city_before": before["city"],
        "city_after": after["city"],
        "access_gain_points": (
            round(after["city"]["access_pct"] - before["city"]["access_pct"], 1)
            if before["city"]["access_pct"] is not None
            else None
        ),
        "wards": wards,
        "uncertainty": uncertainty,
        "data_warning": None if layers.greens else "No green-space polygons loaded; baseline coverage is zero by default.",
        "green_is_demo": layers.green_is_demo,
    }
    scenario = Scenario(
        public_id=f"SCN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f')}",
        name=name[:128],
        kind="green",
        params={
            "strategy": strategy,
            "sites": sites_count,
            "trees_per_site": trees_per_site,
            "access_radius_m": access_radius,
            "ward_id": ward_id,
        },
        result=result,
        assumptions=" ".join(ASSUMPTIONS),
        created_by=actor,
    )
    db.add(scenario)
    db.flush()
    return scenario


def scenario_buildings(db: Session, scenario: Scenario) -> dict[str, Any]:
    """Building footprints with whether each is within reach of green space before and after the scenario.

    Recomputed from the stored sites with the same rules as the run, so the counts match the saved result.
    """
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    from app.building_height import building_height

    layers = load_layers(db)
    params = scenario.params
    radius = float(params["access_radius_m"])
    trees = int(params["trees_per_site"])
    discs = [_disc(*to_m(s["longitude"], s["latitude"]), trees) for s in scenario.result["sites"]]
    before = _metrics(layers, _green_union(layers), radius)["_covered"]
    after = _metrics(layers, _green_union(layers, discs), radius)["_covered"]
    rows = db.execute(select(Building.geom, Building.properties).order_by(Building.id)).all()
    features = []
    for i, (geom, props) in enumerate(rows):
        height, source = building_height(props)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(geom)),
                "properties": {
                    "height_m": height,
                    "height_source": source,
                    "access_before": bool(before[i]),
                    "access_after": bool(after[i]),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
