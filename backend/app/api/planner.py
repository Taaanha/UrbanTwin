from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.services.audit import audit
from app.models.planner import Intervention, Plan, UnitRate
from app.planner_constants import DISCLAIMER
from app.services.planner import (
    compare_plans,
    generate_interventions,
    list_interventions,
    seed_rates,
    serialize_rate,
)

router = APIRouter(prefix="/api/planner", tags=["planner"], dependencies=[Depends(require_staff)])


class RatePatch(BaseModel):
    amount_bdt: float = Field(gt=0)
    notes: str | None = None


class CompareBody(BaseModel):
    budget_bdt: float = Field(gt=0, le=1_000_000_000)


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "rates": db.scalar(select(func.count()).select_from(UnitRate)) or 0,
        "interventions": db.scalar(select(func.count()).select_from(Intervention)) or 0,
        "plans": db.scalar(select(func.count()).select_from(Plan)) or 0,
    }


@router.get("/rates")
def rates(db: Session = Depends(get_db)) -> dict[str, Any]:
    seed_rates(db)
    db.commit()
    rows = db.scalars(select(UnitRate).order_by(UnitRate.category, UnitRate.action_code)).all()
    return {
        "disclaimer": DISCLAIMER,
        "items": [serialize_rate(row) for row in rows],
    }


@router.patch("/rates/{rate_id}")
def update_rate(
    rate_id: int,
    body: RatePatch,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(UnitRate, rate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unit rate not found.")
    previous = row.amount_bdt
    row.amount_bdt = body.amount_bdt
    row.is_demo = True
    if body.notes:
        row.notes = body.notes
    audit(
        db,
        actor=actor,
        action="planner.rate_changed",
        entity_type="unit_rate",
        entity_id=row.id,
        detail={"from": previous, "to": body.amount_bdt, "action_code": row.action_code, "category": row.category},
    )
    db.commit()
    db.refresh(row)
    return {"ok": True, "disclaimer": DISCLAIMER, "item": serialize_rate(row)}


@router.post("/interventions/generate")
def generate(db: Session = Depends(get_db)) -> dict[str, Any]:
    counts = generate_interventions(db)
    db.commit()
    return {"ok": True, "disclaimer": DISCLAIMER, **counts, "items": list_interventions(db)}


@router.get("/interventions")
def interventions(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"disclaimer": DISCLAIMER, "items": list_interventions(db)}


@router.post("/compare")
def compare(body: CompareBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    payload = compare_plans(db, body.budget_bdt)
    db.commit()
    return payload
