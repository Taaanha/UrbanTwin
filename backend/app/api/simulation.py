from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.models.simulation import GreenSpace, Scenario
from app.services import flood
from app.services import simulation as sim
from app.services.audit import audit
from app.services.planner import _candidates, evaluate_methods, generate_interventions
from app.simulation_constants import ACCESS_RADIUS_M, ASSUMPTIONS, DISCLAIMER, MAX_SITES, TREES_PER_SITE

router = APIRouter(prefix="/api/simulation", tags=["simulation"], dependencies=[Depends(require_staff)])


class GreenBody(BaseModel):
    name: str = Field(default="Green scenario", max_length=128)
    strategy: str = Field(default="gap_fill", pattern="^(gap_fill|manual)$")
    sites: int = Field(default=10, ge=1, le=MAX_SITES)
    trees_per_site: int = Field(default=TREES_PER_SITE, ge=1, le=500)
    access_radius_m: float = Field(default=ACCESS_RADIUS_M, ge=50, le=2000)
    ward_id: int | None = None
    manual_sites: list[tuple[float, float]] = Field(default_factory=list, max_length=MAX_SITES)  # (lon, lat)


class BudgetBody(BaseModel):
    budgets_bdt: list[float] = Field(min_length=1, max_length=6)


def _serialize(row: Scenario, full: bool = True) -> dict[str, Any]:
    payload = {
        "public_id": row.public_id,
        "name": row.name,
        "kind": row.kind,
        "params": row.params,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if full:
        payload["result"] = row.result
        payload["assumptions"] = row.assumptions
    return payload


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "assumptions": ASSUMPTIONS,
        "green_features": db.query(GreenSpace).count(),
        "demo_green_features": db.query(GreenSpace).filter(GreenSpace.is_demo.is_(True)).count(),
        "scenarios": db.query(Scenario).count(),
    }


@router.get("/green/baseline")
def green_baseline(access_radius_m: float = ACCESS_RADIUS_M, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not 50 <= access_radius_m <= 2000:
        raise HTTPException(status_code=400, detail="access_radius_m must be between 50 and 2000.")
    return sim.baseline(db, access_radius_m)


@router.get("/green/geojson")
def green_geojson(db: Session = Depends(get_db)) -> dict[str, Any]:
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    rows = db.scalars(select(GreenSpace)).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(to_shape(r.geom)),
                "properties": {"name": r.name, "kind": r.kind, "is_demo": r.is_demo},
            }
            for r in rows
        ],
    }


@router.post("/green")
def run_green(
    body: GreenBody,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.strategy == "manual" and not body.manual_sites:
        raise HTTPException(status_code=400, detail="manual strategy needs manual_sites as [lon, lat] pairs.")
    for lon, lat in body.manual_sites:
        if not (88.0 <= lon <= 92.8 and 20.5 <= lat <= 26.8):
            raise HTTPException(status_code=400, detail="Manual site is outside Bangladesh.")
    try:
        scenario = sim.run_green_scenario(
            db,
            name=body.name,
            strategy=body.strategy,
            sites_count=body.sites,
            trees_per_site=body.trees_per_site,
            access_radius=body.access_radius_m,
            ward_id=body.ward_id,
            manual_sites=body.manual_sites,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(db, actor=actor, action="simulation.green_run", entity_type="scenario", entity_id=scenario.public_id, detail=scenario.params)
    db.commit()
    return _serialize(scenario)


@router.post("/budget")
def budget_scenarios(body: BudgetBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Compare repair-priority methods at several budgets. Nothing is saved or approved."""
    if any(b <= 0 or b > 1_000_000_000 for b in body.budgets_bdt):
        raise HTTPException(status_code=400, detail="Budgets must be between 1 and 1,000,000,000 BDT.")
    generate_interventions(db)
    items = _candidates(db)
    db.commit()
    runs = [{"budget_bdt": b, "methods": evaluate_methods(items, b)} for b in body.budgets_bdt]
    return {
        "disclaimer": "Costs are lab placeholders and priority scores are lab heuristics. Selecting items here does not approve any project.",
        "interventions_considered": len(items),
        "runs": runs,
    }


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Scenario).order_by(Scenario.id.desc())).all()
    return {"items": [_serialize(r, full=False) for r in rows]}


@router.get("/scenarios/{public_id}")
def get_scenario(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.scalar(select(Scenario).where(Scenario.public_id == public_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return _serialize(row)


@router.get("/scenarios/{public_id}/buildings")
def scenario_buildings(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.scalar(select(Scenario).where(Scenario.public_id == public_id))
    if row is None or row.kind != "green":
        raise HTTPException(status_code=404, detail="Green scenario not found.")
    return sim.scenario_buildings(db, row)


@router.get("/flood/status")
def flood_status() -> dict[str, Any]:
    return flood.status()


@router.post("/flood/dem")
def flood_fetch_dem(actor: str = Depends(require_staff), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Download and cache the elevation tiles. Needs internet on the machine running the API."""
    try:
        flood.fetch_dem()
    except flood.DemUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    audit(db, actor=actor, action="simulation.dem_fetch", entity_type="dem", entity_id="terrarium", detail={"zoom": flood.ZOOM})
    db.commit()
    return flood.status()


@router.get("/flood")
def flood_what_if(level_m: float, connected_only: bool = True, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return flood.run(db, level_m, connected_only)
    except flood.DemUnavailable as exc:
        raise HTTPException(status_code=409, detail=f"{exc} Download the elevation data first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/roads")
def road_exposure(level_m: float, connected_only: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Road length at or below a water level in the elevation model (screening, not a forecast)."""
    from app.services import network

    try:
        return network.road_exposure(db, level_m, connected_only)
    except flood.DemUnavailable as exc:
        raise HTTPException(status_code=409, detail=f"{exc} Download the elevation data first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/drainage/ponding")
def drainage_ponding(min_depth_m: float = 1.0, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Where rain would collect in the elevation model if it could only leave through the window edge."""
    from app.services import network

    try:
        return network.ponding(db, min_depth_m)
    except flood.DemUnavailable as exc:
        raise HTTPException(status_code=409, detail=f"{exc} Download the elevation data first.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
