from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.models.geo import Drain
from app.models.intelligence import IssueAsset, IssueRelation
from app.models.investigator import Issue
from app.services.intelligence import (
    DISCLAIMER,
    DRAIN_NOTE,
    geojson_payload,
    graph_payload,
    issue_brief,
    refresh_all,
    snapshot_for,
    _serialize_asset,
    _serialize_relation,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"], dependencies=[Depends(require_staff)])


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "drain_limitation": DRAIN_NOTE,
        "issues": db.scalar(select(func.count()).select_from(Issue)) or 0,
        "assets": db.scalar(select(func.count()).select_from(IssueAsset)) or 0,
        "relations": db.scalar(select(func.count()).select_from(IssueRelation)) or 0,
        "osm_drain_features": db.scalar(select(func.count()).select_from(Drain)) or 0,
        "recurrence_flags": db.scalar(
            select(func.count()).select_from(IssueRelation).where(
                IssueRelation.relation_type == "possible_recurrence"
            )
        )
        or 0,
    }


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)) -> dict[str, Any]:
    counts = refresh_all(db)
    db.commit()
    return {"ok": True, "disclaimer": DISCLAIMER, **counts}


@router.get("/issues")
def list_issues(db: Session = Depends(get_db)) -> dict[str, Any]:
    issues = db.scalars(select(Issue).order_by(Issue.created_at.desc())).all()
    assets = db.scalars(select(IssueAsset)).all()
    by_issue: dict[int, list[IssueAsset]] = {}
    for row in assets:
        by_issue.setdefault(row.issue_id, []).append(row)
    items = []
    for issue in issues:
        linked = by_issue.get(issue.id, [])
        road = next((row for row in linked if row.asset_kind == "road"), None)
        drain = next((row for row in linked if row.asset_kind == "drain"), None)
        ward = next((row for row in linked if row.asset_kind == "ward"), None)
        items.append(
            {
                **issue_brief(issue),
                "road": road.asset_name if road else None,
                "road_distance_m": road.distance_m if road else None,
                "drain": drain.asset_name if drain else None,
                "ward": ward.asset_name if ward else None,
            }
        )
    return {"disclaimer": DISCLAIMER, "count": len(items), "items": items}


@router.get("/issues/{public_id}")
def issue_intelligence(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    issue = db.scalar(select(Issue).where(Issue.public_id == public_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    return snapshot_for(db, issue)


@router.get("/recurrence")
def recurrence(db: Session = Depends(get_db)) -> dict[str, Any]:
    issues = {row.id: row for row in db.scalars(select(Issue)).all()}
    rows = db.scalars(
        select(IssueRelation)
        .where(IssueRelation.relation_type.in_(["possible_recurrence", "same_road", "nearby"]))
        .order_by(IssueRelation.relation_type, IssueRelation.distance_m)
    ).all()
    return {
        "disclaimer": DISCLAIMER,
        "note": "Recurrence is a time-gap + proximity flag. It is not a confirmed repair failure.",
        "items": [_serialize_relation(row, issues) for row in rows],
    }


@router.get("/graph")
def graph(db: Session = Depends(get_db)) -> dict[str, Any]:
    return graph_payload(db)


@router.get("/geojson")
def geojson(db: Session = Depends(get_db)) -> dict[str, Any]:
    return geojson_payload(db)


@router.get("/issues/{public_id}/brief")
def issue_ai_brief(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """AI-written summary of one issue's spatial links. Correlation only, never a cause."""
    from app.services.ai_briefs import issue_brief as write_brief
    from app.services.ai_opinion import ProviderError, ProviderUnavailable

    issue = db.scalar(select(Issue).where(Issue.public_id == public_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    try:
        return {"brief": write_brief(snapshot_for(db, issue))}
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
