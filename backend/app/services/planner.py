"""Indicative intervention costing and greedy budget packs. Not a tender."""

from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.intelligence import IssueAsset, IssueRelation
from app.models.investigator import Issue
from app.models.planner import CostEstimate, Intervention, Plan, PlanItem, UnitRate
from app.planner_constants import (
    CONTINGENCY_PCT,
    DEFAULT_RATES,
    DISCLAIMER,
    QUANTITIES,
    RANGE_PCT,
    RATE_SOURCE,
    SAFETY_POINTS,
    SEVERITY_POINTS,
    SHARE_EQUIPMENT,
    SHARE_LABOUR,
    SHARE_MATERIALS,
)


def seed_rates(db: Session) -> list[UnitRate]:
    existing = {(row.action_code, row.category) for row in db.scalars(select(UnitRate)).all()}
    created = []
    for action, category, unit, amount, notes in DEFAULT_RATES:
        if (action, category) in existing:
            continue
        row = UnitRate(
            action_code=action,
            category=category,
            unit=unit,
            amount_bdt=amount,
            is_demo=True,
            source=RATE_SOURCE,
            notes=notes,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def _rate_for(db: Session, category: str, action_code: str) -> UnitRate | None:
    return db.scalar(
        select(UnitRate).where(UnitRate.category == category, UnitRate.action_code == action_code)
    )


def _recurrence_bonus(db: Session, issue_id: int) -> tuple[int, str]:
    row = db.scalar(
        select(IssueRelation).where(
            IssueRelation.relation_type == "possible_recurrence",
            (IssueRelation.from_issue_id == issue_id) | (IssueRelation.to_issue_id == issue_id),
        )
    )
    if row is None:
        return 0, "No recurrence flag"
    return 12, "Possible recurrence flag (time + proximity), not confirmed failure"


def _same_road_bonus(db: Session, issue_id: int) -> tuple[int, str]:
    count = 0
    for row in db.scalars(
        select(IssueRelation).where(
            IssueRelation.relation_type == "same_road",
            (IssueRelation.from_issue_id == issue_id) | (IssueRelation.to_issue_id == issue_id),
        )
    ):
        count += 1
    points = min(count, 5) * 2
    return points, f"Same OSM road cluster size {count} (correlation only)"


def priority_score(db: Session, issue: Issue) -> tuple[int, list[str]]:
    notes = []
    sev = SEVERITY_POINTS.get(issue.severity, 8)
    notes.append(f"Severity {issue.severity}: {sev}")
    safety = SAFETY_POINTS.get(issue.category, 5)
    notes.append(f"Category weight {issue.category}: {safety}")
    rec_pts, rec_note = _recurrence_bonus(db, issue.id)
    notes.append(rec_note)
    road_pts, road_note = _same_road_bonus(db, issue.id)
    notes.append(road_note)
    notes.append("Population affected is not modelled (no census layer).")
    notes.append("Root cause is not scored. Drainage links remain correlation only.")
    return sev + safety + rec_pts + road_pts, notes


def _estimate(quantity: float, rate: float) -> dict[str, float]:
    subtotal = quantity * rate
    labour = round(subtotal * SHARE_LABOUR, 2)
    materials = round(subtotal * SHARE_MATERIALS, 2)
    equipment = round(subtotal * SHARE_EQUIPMENT, 2)
    contingency = round(subtotal * CONTINGENCY_PCT, 2)
    mid = round(subtotal + contingency, 2)
    return {
        "labour_bdt": labour,
        "materials_bdt": materials,
        "equipment_bdt": equipment,
        "contingency_bdt": contingency,
        "total_low_bdt": round(mid * (1 - RANGE_PCT), 2),
        "total_mid_bdt": mid,
        "total_high_bdt": round(mid * (1 + RANGE_PCT), 2),
    }


def upsert_intervention(db: Session, issue: Issue) -> Intervention:
    qty, unit, action, qty_note = QUANTITIES.get(issue.category, QUANTITIES["other"])
    score, score_notes = priority_score(db, issue)
    rate = _rate_for(db, issue.category, action)
    amount = rate.amount_bdt if rate else 15000
    unit = rate.unit if rate else unit
    money = _estimate(qty, amount)
    assumptions = " ".join(
        [
            qty_note,
            RATE_SOURCE,
            f"Unit rate {amount:.0f} BDT/{unit}.",
            f"Contingency {CONTINGENCY_PCT:.0%} and ±{RANGE_PCT:.0%} band are lab defaults.",
            *score_notes,
        ]
    )
    existing = db.scalar(select(Intervention).where(Intervention.issue_id == issue.id))
    title = f"{action.replace('_', ' ')} for {issue.public_id}"
    if existing is None:
        existing = Intervention(
            public_id=f"INT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f')}",
            issue_id=issue.id,
            action_code=action,
            title=title,
            quantity=qty,
            unit=unit,
            priority_score=score,
            status="draft",
            assumptions=assumptions,
        )
        db.add(existing)
        db.flush()
    else:
        existing.action_code = action
        existing.title = title
        existing.quantity = qty
        existing.unit = unit
        existing.priority_score = score
        existing.assumptions = assumptions
        db.execute(delete(CostEstimate).where(CostEstimate.intervention_id == existing.id))
    db.add(
        CostEstimate(
            intervention_id=existing.id,
            is_indicative=True,
            assumptions=assumptions,
            **money,
        )
    )
    db.flush()
    return existing


def generate_interventions(db: Session) -> dict[str, int]:
    seed_rates(db)
    issues = db.scalars(select(Issue).where(Issue.status.in_(["open", "possibly_resolved"]))).all()
    for issue in issues:
        upsert_intervention(db, issue)
    return {"issues": len(issues), "interventions": len(issues)}


def _latest_estimate(db: Session, intervention_id: int) -> CostEstimate | None:
    return db.scalar(
        select(CostEstimate)
        .where(CostEstimate.intervention_id == intervention_id)
        .order_by(CostEstimate.created_at.desc())
    )


def _ward_name(db: Session, issue_id: int) -> str:
    row = db.scalar(
        select(IssueAsset).where(IssueAsset.issue_id == issue_id, IssueAsset.asset_kind == "ward")
    )
    return row.asset_name if row and row.asset_name else "unassigned"


def _candidates(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(Intervention).options(selectinload(Intervention.estimates))).all()
    issues = {item.id: item for item in db.scalars(select(Issue)).all()}
    out = []
    for row in rows:
        estimate = max(row.estimates, key=lambda item: item.id) if row.estimates else _latest_estimate(db, row.id)
        issue = issues.get(row.issue_id)
        if estimate is None or issue is None:
            continue
        point = to_shape(issue.geom)
        out.append(
            {
                "intervention": row,
                "estimate": estimate,
                "issue": issue,
                "ward": _ward_name(db, issue.id),
                "longitude": point.x,
                "latitude": point.y,
                "value": row.priority_score / max(estimate.total_mid_bdt, 1.0),
            }
        )
    return out


def _pack(ordered: list[dict[str, Any]], budget: float) -> tuple[list[dict[str, Any]], float]:
    remaining = budget
    spent = 0.0
    ranked = []
    for index, item in enumerate(ordered, start=1):
        cost = item["estimate"].total_mid_bdt
        include = cost <= remaining
        ranked.append({**item, "included": include, "rank": index})
        if include:
            remaining -= cost
            spent += cost
    return ranked, spent


def greedy_value(items: list[dict[str, Any]], budget: float) -> tuple[list[dict[str, Any]], float]:
    ordered = sorted(items, key=lambda item: (-item["value"], item["estimate"].total_mid_bdt))
    return _pack(ordered, budget)


def greedy_severity(items: list[dict[str, Any]], budget: float) -> tuple[list[dict[str, Any]], float]:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(
        items,
        key=lambda item: (
            rank.get(item["issue"].severity, 9),
            -item["intervention"].priority_score,
            item["estimate"].total_mid_bdt,
        ),
    )
    return _pack(ordered, budget)


def greedy_equity(items: list[dict[str, Any]], budget: float) -> tuple[list[dict[str, Any]], float]:
    remaining = budget
    spent = 0.0
    selected_by_ward: dict[str, int] = {}
    leftover = list(items)
    chosen: list[dict[str, Any]] = []
    rank = 1
    while leftover:
        leftover.sort(
            key=lambda item: (
                selected_by_ward.get(item["ward"], 0),
                -item["intervention"].priority_score,
                item["estimate"].total_mid_bdt,
            )
        )
        nxt = leftover.pop(0)
        cost = nxt["estimate"].total_mid_bdt
        include = cost <= remaining
        chosen.append({**nxt, "included": include, "rank": rank})
        rank += 1
        if include:
            remaining -= cost
            spent += cost
            selected_by_ward[nxt["ward"]] = selected_by_ward.get(nxt["ward"], 0) + 1
    return chosen, spent


def optimal_knapsack(items: list[dict[str, Any]], budget: float) -> tuple[list[dict[str, Any]], float]:
    """Exact 0/1 knapsack with OR-Tools CP-SAT: maximise total priority score within budget.

    Falls back to greedy_value if OR-Tools is not installed or no solution is found.
    """
    if not items:
        return [], 0.0
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return greedy_value(items, budget)
    costs = [int(ceil(item["estimate"].total_mid_bdt)) for item in items]
    scores = [int(item["intervention"].priority_score) for item in items]
    model = cp_model.CpModel()
    picks = [model.NewBoolVar(f"pick_{k}") for k in range(len(items))]
    model.Add(sum(c * v for c, v in zip(costs, picks)) <= int(budget))
    model.Maximize(sum(s * v for s, v in zip(scores, picks)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return greedy_value(items, budget)
    chosen = {k for k, v in enumerate(picks) if solver.Value(v)}
    order = sorted(range(len(items)), key=lambda k: (k not in chosen, -scores[k], costs[k]))
    ranked = [{**items[k], "included": k in chosen, "rank": rank} for rank, k in enumerate(order, start=1)]
    spent = float(sum(items[k]["estimate"].total_mid_bdt for k in chosen))
    return ranked, spent


METHODS = {
    "greedy_value": (
        greedy_value,
        "Pack highest priority-score per BDT first. Lab heuristic, not an optimiser certificate.",
    ),
    "greedy_severity": (
        greedy_severity,
        "Pack highest severity first. Does not model population or official risk.",
    ),
    "greedy_equity": (
        greedy_equity,
        "Prefer wards that have fewer selected items so one demo ward does not take the whole budget.",
    ),
    "optimal_knapsack": (
        optimal_knapsack,
        "OR-Tools CP-SAT: provably maximises total priority score within the budget (costs are indicative lab figures).",
    ),
}


def evaluate_methods(items: list[dict[str, Any]], budget: float) -> dict[str, dict[str, Any]]:
    """Run every method without saving anything. Used by scenario comparison."""
    out = {}
    for method, (fn, notes) in METHODS.items():
        ranked, spent = fn(items, budget)
        included = [row for row in ranked if row["included"]]
        out[method] = {
            "method": method,
            "notes": notes,
            "budget_bdt": budget,
            "spent_bdt": round(spent, 2),
            "remaining_bdt": round(budget - spent, 2),
            "included_count": len(included),
            "total_priority_score": int(sum(row["intervention"].priority_score for row in included)),
            "wards_served": len({row["ward"] for row in included}),
            "included_ids": [row["intervention"].public_id for row in included],
        }
    return out


def _serialize_intervention(item: dict[str, Any]) -> dict[str, Any]:
    row: Intervention = item["intervention"]
    estimate: CostEstimate = item["estimate"]
    issue: Issue = item["issue"]
    return {
        "public_id": row.public_id,
        "issue_public_id": issue.public_id,
        "title": row.title,
        "action_code": row.action_code,
        "category": issue.category,
        "severity": issue.severity,
        "quantity": row.quantity,
        "unit": row.unit,
        "priority_score": row.priority_score,
        "status": row.status,
        "ward": item.get("ward"),
        "longitude": item.get("longitude"),
        "latitude": item.get("latitude"),
        "assumptions": row.assumptions,
        "cost": {
            "is_indicative": estimate.is_indicative,
            "labour_bdt": estimate.labour_bdt,
            "materials_bdt": estimate.materials_bdt,
            "equipment_bdt": estimate.equipment_bdt,
            "contingency_bdt": estimate.contingency_bdt,
            "total_low_bdt": estimate.total_low_bdt,
            "total_mid_bdt": estimate.total_mid_bdt,
            "total_high_bdt": estimate.total_high_bdt,
            "currency": "BDT",
        },
        "included": item.get("included"),
        "rank": item.get("rank"),
    }


def save_plan(
    db: Session,
    *,
    name: str,
    method: str,
    budget: float,
    ranked: list[dict[str, Any]],
    spent: float,
    notes: str,
) -> Plan:
    existing = db.scalar(select(Plan).where(Plan.name == name, Plan.generated_by == "compare"))
    if existing is not None:
        db.execute(delete(PlanItem).where(PlanItem.plan_id == existing.id))
        db.delete(existing)
        db.flush()
    plan = Plan(
        name=name,
        method=method,
        budget_bdt=budget,
        spent_bdt=round(spent, 2),
        generated_by="compare",
        notes=notes,
    )
    db.add(plan)
    db.flush()
    for item in ranked:
        db.add(
            PlanItem(
                plan_id=plan.id,
                intervention_id=item["intervention"].id,
                included=item["included"],
                rank=item["rank"],
                score_used=item["intervention"].priority_score,
                cost_mid_bdt=item["estimate"].total_mid_bdt,
            )
        )
    db.flush()
    return plan


def compare_plans(db: Session, budget_bdt: float) -> dict[str, Any]:
    generate_interventions(db)
    items = _candidates(db)
    plans = []
    for method, (fn, notes) in METHODS.items():
        ranked, spent = fn(items, budget_bdt)
        plan = save_plan(
            db,
            name=f"compare:{method}",
            method=method,
            budget=budget_bdt,
            ranked=ranked,
            spent=spent,
            notes=notes,
        )
        included = [row for row in ranked if row["included"]]
        deferred = [row for row in ranked if not row["included"]]
        plans.append(
            {
                "id": plan.id,
                "name": plan.name,
                "method": method,
                "notes": notes,
                "budget_bdt": budget_bdt,
                "spent_bdt": round(spent, 2),
                "remaining_bdt": round(budget_bdt - spent, 2),
                "included_count": len(included),
                "deferred_count": len(deferred),
                "included": [_serialize_intervention(row) for row in included],
                "deferred": [_serialize_intervention(row) for row in deferred],
            }
        )
    return {
        "disclaimer": DISCLAIMER,
        "budget_bdt": budget_bdt,
        "currency": "BDT",
        "limitations": [
            "Greedy methods are heuristics; optimal_knapsack (OR-Tools) is exact for the stated scores and costs, but the scores and costs are lab approximations.",
            "Population, official unit rates, and surveyed quantities are unavailable.",
            "Selecting an intervention does not create an approved municipal project.",
        ],
        "plans": plans,
    }


def serialize_rate(row: UnitRate) -> dict[str, Any]:
    return {
        "id": row.id,
        "action_code": row.action_code,
        "category": row.category,
        "unit": row.unit,
        "amount_bdt": row.amount_bdt,
        "currency": row.currency,
        "is_demo": row.is_demo,
        "source": row.source,
        "notes": row.notes,
    }


def list_interventions(db: Session) -> list[dict[str, Any]]:
    return [_serialize_intervention(item) for item in _candidates(db)]
