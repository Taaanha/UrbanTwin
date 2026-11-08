"""Project lifecycle helpers and the recurring-deterioration screen."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accountability_constants import (
    BUDGET_OVERRUN_PCT,
    CONTEXT_LIMITATIONS,
    DISCLAIMER,
    FAST_RECURRENCE_DAYS,
    RECURRENCE_RADIUS_M,
)
from app.models.accountability import Project
from app.models.intelligence import IssueAsset
from app.models.investigator import Issue
from app.models.planner import CostEstimate, Intervention
from app.services.duplicates import RELATED_CATEGORIES, haversine_m


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _related(a: str, b: str) -> bool:
    if a == b:
        return True
    pair = frozenset({a, b})
    return any(pair <= group for group in RELATED_CATEGORIES)


def spent_to_date(project: Project) -> float:
    return round(sum(update.expenditure_bdt for update in project.updates), 2)


def progress_to_date(project: Project) -> int:
    return max((update.progress_pct for update in project.updates), default=0)


def recurrences_for_project(db: Session, project: Project) -> list[dict[str, Any]]:
    """Issues verified AFTER completion, close to the repaired issue and in a related category."""
    completed = _aware(project.completed_at)
    if completed is None:
        return []
    origin_issue = db.get(Issue, project.issue_id)
    if origin_issue is None:
        return []
    origin = to_shape(origin_issue.geom)
    hits = []
    for issue in db.scalars(select(Issue).where(Issue.id != origin_issue.id)).all():
        created = _aware(issue.created_at)
        if created is None or created <= completed:
            continue
        point = to_shape(issue.geom)
        metres = haversine_m(origin.x, origin.y, point.x, point.y)
        if metres > RECURRENCE_RADIUS_M or not _related(origin_issue.category, issue.category):
            continue
        days = (created - completed).total_seconds() / 86400.0
        hits.append(
            {
                "issue_public_id": issue.public_id,
                "category": issue.category,
                "distance_m": round(metres, 1),
                "days_after_completion": round(days, 1),
                "faster_than_threshold": days < FAST_RECURRENCE_DAYS,
            }
        )
    hits.sort(key=lambda item: item["days_after_completion"])
    return hits


def recurrences_for_new_issue(db: Session, issue: Issue) -> list[dict[str, Any]]:
    """Which completed projects does this newly verified issue appear to follow?"""
    point = to_shape(issue.geom)
    created = _aware(issue.created_at) or datetime.now(timezone.utc)
    out = []
    for project in db.scalars(select(Project).where(Project.completed_at.is_not(None))).all():
        origin_issue = db.get(Issue, project.issue_id)
        completed = _aware(project.completed_at)
        if origin_issue is None or origin_issue.id == issue.id or completed is None or created <= completed:
            continue
        origin = to_shape(origin_issue.geom)
        metres = haversine_m(origin.x, origin.y, point.x, point.y)
        if metres <= RECURRENCE_RADIUS_M and _related(origin_issue.category, issue.category):
            days = (created - completed).total_seconds() / 86400.0
            out.append(
                {
                    "project_public_id": project.public_id,
                    "days_after_completion": round(days, 1),
                    "distance_m": round(metres, 1),
                    "faster_than_threshold": days < FAST_RECURRENCE_DAYS,
                }
            )
    return out


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def findings_for(db: Session, project: Project) -> dict[str, Any]:
    """Documentation checks plus recurrence. 'unknown' means no record, not a failure."""
    checks: list[dict[str, str]] = []
    reasons: list[str] = []
    spent = spent_to_date(project)
    progress = progress_to_date(project)

    checks.append(
        _check(
            "specification_recorded",
            "ok" if len(project.specification.strip()) >= 10 else "gap",
            "Specification text is on file." if len(project.specification.strip()) >= 10 else "Specification is missing or too short.",
        )
    )

    completion_files = [e for e in project.evidence if e.kind == "completion"]
    if project.completed_at is not None:
        if completion_files:
            checks.append(_check("completion_evidence", "ok", f"{len(completion_files)} completion file(s) uploaded."))
        else:
            checks.append(_check("completion_evidence", "gap", "Marked complete but no completion evidence is on file."))
            reasons.append("Completion evidence is missing.")

    independent = [i for i in project.inspections if i.independent]
    if project.completed_at is not None:
        if independent:
            latest = independent[-1]
            status = "ok" if latest.outcome == "meets_specification" else "concern"
            checks.append(_check("independent_inspection", status, f"Latest independent outcome: {latest.outcome}."))
            if latest.outcome in {"does_not_meet", "partially_meets"}:
                reasons.append(f"Independent inspection recorded '{latest.outcome}'.")
        else:
            checks.append(_check("independent_inspection", "unknown", "No independent inspection has been recorded yet."))

    limit = project.approved_budget_bdt * (1 + BUDGET_OVERRUN_PCT)
    if spent > limit:
        checks.append(
            _check("expenditure_vs_budget", "concern", f"Recorded spending {spent:,.0f} BDT exceeds approved {project.approved_budget_bdt:,.0f} BDT by more than {BUDGET_OVERRUN_PCT:.0%}.")
        )
        reasons.append("Recorded expenditure exceeds the approved budget.")
    else:
        checks.append(_check("expenditure_vs_budget", "ok", f"Recorded spending {spent:,.0f} of {project.approved_budget_bdt:,.0f} BDT approved."))

    if project.completed_at is not None and progress < 100:
        checks.append(_check("progress_record", "gap", f"Marked complete but last progress update was {progress}%."))
        reasons.append("Completion date and progress records disagree.")

    recurrence = recurrences_for_project(db, project)
    fast = [item for item in recurrence if item["faster_than_threshold"]]
    if fast:
        reasons.append(
            f"A related problem was verified {fast[0]['days_after_completion']:.0f} days after completion "
            f"(screening threshold {FAST_RECURRENCE_DAYS} days)."
        )

    return {
        "disclaimer": DISCLAIMER,
        "context_limitations": CONTEXT_LIMITATIONS,
        "checks": checks,
        "recurrence": recurrence,
        "review_flag": "worth_independent_review" if reasons else "none",
        "reasons": reasons,
    }


def project_brief(db: Session, project: Project) -> dict[str, Any]:
    issue = db.get(Issue, project.issue_id)
    intervention = db.get(Intervention, project.intervention_id)
    point = to_shape(issue.geom) if issue else None
    findings = findings_for(db, project) if project.completed_at is not None else None
    return {
        "public_id": project.public_id,
        "title": project.title,
        "status": project.status,
        "is_demo": project.is_demo,
        "issue_public_id": issue.public_id if issue else None,
        "issue_status": issue.status if issue else None,
        "category": issue.category if issue else None,
        "intervention_public_id": intervention.public_id if intervention else None,
        "approved_budget_bdt": project.approved_budget_bdt,
        "spent_bdt": spent_to_date(project),
        "progress_pct": progress_to_date(project),
        "contractor_name": project.contractor_name,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "planned_end_date": project.planned_end_date.isoformat() if project.planned_end_date else None,
        "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        "inspection_count": len(project.inspections),
        "review_flag": findings["review_flag"] if findings else "not_applicable",
        "longitude": point.x if point else None,
        "latitude": point.y if point else None,
    }


def indicative_estimate_for(db: Session, intervention_id: int) -> float | None:
    est = db.scalar(
        select(CostEstimate).where(CostEstimate.intervention_id == intervention_id).order_by(CostEstimate.id.desc())
    )
    return est.total_mid_bdt if est else None


def lifecycle(db: Session, project: Project) -> list[dict[str, Any]]:
    """Ordered chain from the original problem to the latest recurrence check."""
    issue = db.get(Issue, project.issue_id)
    steps: list[dict[str, Any]] = []
    if issue:
        steps.append({"stage": "verified_issue", "ref": issue.public_id, "at": issue.created_at.isoformat() if issue.created_at else None, "detail": issue.title})
        for asset in db.scalars(select(IssueAsset).where(IssueAsset.issue_id == issue.id, IssueAsset.asset_kind.in_(["road", "drain"]))).all():
            steps.append({"stage": "linked_asset", "ref": f"{asset.asset_kind}:{asset.asset_name}", "at": None, "detail": f"{asset.distance_m} m (correlation only)"})
    intervention = db.get(Intervention, project.intervention_id)
    if intervention:
        steps.append({"stage": "proposed_intervention", "ref": intervention.public_id, "at": intervention.created_at.isoformat() if intervention.created_at else None, "detail": intervention.title})
    steps.append({"stage": "approved_project", "ref": project.public_id, "at": project.created_at.isoformat() if project.created_at else None, "detail": f"Approved budget {project.approved_budget_bdt:,.0f} BDT"})
    for update in project.updates:
        steps.append({"stage": "progress_update", "ref": f"{update.progress_pct}%", "at": update.created_at.isoformat() if update.created_at else None, "detail": update.note})
    if project.completed_at:
        steps.append({"stage": "completion_reported", "ref": project.public_id, "at": project.completed_at.isoformat(), "detail": "Completion reported by staff"})
    for inspection in project.inspections:
        steps.append({"stage": "inspection", "ref": inspection.outcome, "at": inspection.inspected_at.isoformat() if inspection.inspected_at else None, "detail": f"{'Independent' if inspection.independent else 'Internal'} inspection by {inspection.inspector}"})
    for hit in recurrences_for_project(db, project):
        steps.append({"stage": "later_related_issue", "ref": hit["issue_public_id"], "at": None, "detail": f"{hit['days_after_completion']:.0f} days after completion, {hit['distance_m']} m away"})
    return steps
