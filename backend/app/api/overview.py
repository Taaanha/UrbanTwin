from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.models.accountability import Project
from app.models.audit import AuditLog
from app.models.geo import DataSource
from app.models.intelligence import IssueRelation
from app.models.investigator import Issue
from app.models.planner import Intervention
from app.models.reports import Report

router = APIRouter(prefix="/api", tags=["overview"], dependencies=[Depends(require_staff)])


def _counts(db: Session, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(key): int(count) for key, count in rows}


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Every figure is a live count from the database; demo rows are counted separately."""
    projects = db.scalars(select(Project)).all()
    return {
        "note": "All numbers are live database counts. Demo records are labelled and counted separately.",
        "reports": {
            "total": db.scalar(select(func.count()).select_from(Report)) or 0,
            "demo": db.scalar(select(func.count()).select_from(Report).where(Report.is_demo.is_(True))) or 0,
            "by_status": _counts(db, Report.status),
            "by_severity": _counts(db, Report.severity),
            "by_category": _counts(db, Report.category),
        },
        "issues": {
            "total": db.scalar(select(func.count()).select_from(Issue)) or 0,
            "by_status": _counts(db, Issue.status),
        },
        "intelligence": {
            "possible_recurrence_flags": db.scalar(
                select(func.count()).select_from(IssueRelation).where(IssueRelation.relation_type == "possible_recurrence")
            )
            or 0,
        },
        "planner": {
            "interventions": db.scalar(select(func.count()).select_from(Intervention)) or 0,
            "by_status": _counts(db, Intervention.status),
        },
        "accountability": {
            "projects": len(projects),
            "by_status": _counts(db, Project.status),
            "approved_budget_bdt": round(sum(p.approved_budget_bdt for p in projects), 2),
        },
        "audit_entries": db.scalar(select(func.count()).select_from(AuditLog)) or 0,
    }


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": r.id,
                "at": r.created_at.isoformat() if r.created_at else None,
                "actor": r.actor,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "detail": r.detail,
                "note": r.note,
            }
            for r in rows
        ]
    }


@router.get("/data-sources")
def data_sources(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(DataSource).order_by(DataSource.layer)).all()
    return {
        "items": [
            {
                "layer": r.layer,
                "source": r.source_name,
                "license": r.license,
                "crs": r.crs,
                "acquired_at": r.acquired_at.isoformat() if r.acquired_at else None,
                "processing_steps": r.processing_steps,
                "limitations": r.limitations,
                "is_demo": r.is_demo,
            }
            for r in rows
        ]
    }
