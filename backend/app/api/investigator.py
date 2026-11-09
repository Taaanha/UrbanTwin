from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape, to_shape
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_staff
from app.database import get_db
from app.models.investigator import Issue, IssueReport, Verification
from app.models.reports import Report
from app.services.duplicates import SEARCH_RADIUS_M, score_pair
from app.services.accountability import recurrences_for_new_issue
from app.services import ai_opinion
from app.services.audit import audit
from app.services.image_embedding import cosine, embed_file
from app.services.image_hash import average_hash
from app.services.intelligence import refresh_issue
from app.services.uploads import upload_dir

router = APIRouter(prefix="/api/investigator", tags=["investigator"], dependencies=[Depends(require_staff)])

DECISIONS = {
    "new_candidate_issue",
    "possible_duplicate",
    "existing_issue",
    "insufficient_evidence",
    "evidence_mismatch",
    "possibly_resolved",
}


class VerifyBody(BaseModel):
    tracking_id: str
    decision: str
    related_tracking_id: str | None = None
    related_issue_id: int | None = None
    notes: str | None = None
    score: int | None = None
    reasons: dict[str, Any] = Field(default_factory=dict)


def _hours_apart(a: datetime | None, b: datetime | None) -> float:
    if not a or not b:
        return 0.0
    return abs((a - b).total_seconds()) / 3600.0


def _first_image(report: Report):
    return upload_dir() / report.evidence[0].stored_name if report.evidence else None


def _image_signal(origin: Report, other: Report) -> dict[str, Any]:
    """Embedding similarity if a model is available for both photos, else hash fallback."""
    path_a, path_b = _first_image(origin), _first_image(other)
    if path_a is None or path_b is None:
        return {"image_hash1": None, "image_hash2": None}
    emb_a, emb_b = embed_file(path_a), embed_file(path_b)
    if emb_a and emb_b and emb_a[0] == emb_b[0]:
        return {"image_similarity": cosine(emb_a[1], emb_b[1]), "image_model": emb_a[0]}
    return {"image_hash1": average_hash(path_a), "image_hash2": average_hash(path_b)}


def _report_brief(report: Report) -> dict[str, Any]:
    point = to_shape(report.geom)
    return {
        "id": report.id,
        "tracking_id": report.tracking_id,
        "category": report.category,
        "severity": report.severity,
        "description": report.description,
        "status": report.status,
        "longitude": point.x,
        "latitude": point.y,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "evidence": [
            {
                "id": item.id,
                "url": f"/api/reports/track/{report.tracking_id}/evidence/{item.id}",
            }
            for item in report.evidence
        ],
    }


def _matches_for(
    report: Report,
    others: list[Report],
    issues: list[Issue],
    include_images: bool = True,
) -> list[dict[str, Any]]:
    origin = to_shape(report.geom)
    results: list[dict[str, Any]] = []
    for other in others:
        if other.id == report.id:
            continue
        point = to_shape(other.geom)
        reasons = score_pair(
            lon1=origin.x,
            lat1=origin.y,
            lon2=point.x,
            lat2=point.y,
            category1=report.category,
            category2=other.category,
            text1=report.description,
            text2=other.description,
            hours_apart=_hours_apart(report.created_at, other.created_at),
            **(_image_signal(report, other) if include_images else {}),
        )
        if reasons.distance_m > SEARCH_RADIUS_M:
            continue
        results.append(
            {
                "kind": "report",
                "tracking_id": other.tracking_id,
                "score": reasons.total,
                "suggested_label": reasons.suggested_label(),
                "distance_m": reasons.distance_m,
                "reasons": reasons.notes,
                "breakdown": {
                    "distance": reasons.distance_points,
                    "category": reasons.category_points,
                    "text": reasons.text_points,
                    "recency": reasons.recency_points,
                    "image": reasons.image_points,
                },
                "candidate": _report_brief(other),
            }
        )
    for issue in issues:
        point = to_shape(issue.geom)
        reasons = score_pair(
            lon1=origin.x,
            lat1=origin.y,
            lon2=point.x,
            lat2=point.y,
            category1=report.category,
            category2=issue.category,
            text1=report.description,
            text2=issue.title,
            hours_apart=_hours_apart(report.created_at, issue.created_at),
        )
        if reasons.distance_m > SEARCH_RADIUS_M:
            continue
        results.append(
            {
                "kind": "issue",
                "issue_id": issue.id,
                "public_id": issue.public_id,
                "score": reasons.total,
                "suggested_label": reasons.suggested_label(),
                "distance_m": reasons.distance_m,
                "reasons": reasons.notes,
                "candidate": {
                    "public_id": issue.public_id,
                    "title": issue.title,
                    "category": issue.category,
                    "severity": issue.severity,
                    "status": issue.status,
                    "longitude": point.x,
                    "latitude": point.y,
                },
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:8]


def _verified_ids(db: Session) -> set[int]:
    rows = db.scalars(select(Verification.report_id)).all()
    return set(rows)


@router.get("/queue")
def investigation_queue(db: Session = Depends(get_db)) -> dict[str, Any]:
    reports = db.scalars(select(Report).options(selectinload(Report.evidence)).order_by(Report.created_at.desc())).all()
    issues = db.scalars(select(Issue)).all()
    done = _verified_ids(db)
    pending = []
    for report in reports:
        matches = _matches_for(report, list(reports), list(issues), include_images=False)
        pending.append(
            {
                **_report_brief(report),
                "has_verification": report.id in done,
                "top_score": matches[0]["score"] if matches else 0,
                "top_label": matches[0]["suggested_label"] if matches else "new",
                "match_count": len(matches),
            }
        )
    pending.sort(key=lambda item: (item["has_verification"], -item["top_score"]))
    return {
        "note": "Scores are suggestions only. Reports are never merged automatically.",
        "items": pending,
    }


@router.get("/reports/{tracking_id}")
def inspect_report(tracking_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    report = db.scalar(
        select(Report).options(selectinload(Report.evidence)).where(Report.tracking_id == tracking_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")
    reports = db.scalars(select(Report).options(selectinload(Report.evidence))).all()
    issues = db.scalars(select(Issue)).all()
    history = db.scalars(
        select(Verification).where(Verification.report_id == report.id).order_by(Verification.decided_at.desc())
    ).all()
    return {
        "report": _report_brief(report),
        "matches": _matches_for(report, list(reports), list(issues)),
        "verifications": [
            {
                "id": row.id,
                "decision": row.decision,
                "related_report_id": row.related_report_id,
                "related_issue_id": row.related_issue_id,
                "score": row.score,
                "reasons": row.reasons,
                "notes": row.notes,
                "decided_by": row.decided_by,
                "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            }
            for row in history
        ],
        "policy": [
            "Original citizen reports are preserved.",
            "Nearby defects are not merged automatically.",
            "Uncertain reports are not rejected automatically.",
        ],
    }


class AiOpinionBody(BaseModel):
    provider: str


@router.get("/ai-providers")
def ai_providers() -> dict[str, Any]:
    return {"providers": ai_opinion.available_providers(), "warning": ai_opinion.WARNING}


@router.post("/reports/{tracking_id}/ai-opinion")
def ai_second_opinion(
    tracking_id: str,
    body: AiOpinionBody,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Staff-triggered. Sends ONE re-encoded photo to the chosen provider. Changes nothing else."""
    if body.provider != ai_opinion.AUTO and body.provider not in ai_opinion.PROVIDERS:
        raise HTTPException(status_code=400, detail="provider must be auto, gemini, ollama or huggingface.")
    report = db.scalar(
        select(Report).options(selectinload(Report.evidence)).where(Report.tracking_id == tracking_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")
    path = _first_image(report)
    if path is None or not path.exists():
        raise HTTPException(status_code=409, detail="This report has no photo to analyse.")
    try:
        result = ai_opinion.second_opinion(body.provider, path)
    except ai_opinion.ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ai_opinion.ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    audit(
        db,
        actor=actor,
        action="ai.second_opinion",
        entity_type="report",
        entity_id=report.tracking_id,
        detail={
            **{k: result[k] for k in ("provider", "model", "is_problem", "category", "severity", "confidence")},
            **({"fallback_from": result["fallback_from"]} if result.get("fallback_from") else {}),
        },
        note=(
            "Photo (EXIF removed) was processed by a local model on this machine."
            if result.get("local")
            else "Photo (EXIF removed) was sent to a third-party AI service."
        ),
    )
    db.commit()
    return result


@router.get("/issues")
def list_issues(db: Session = Depends(get_db)) -> dict[str, Any]:
    issues = db.scalars(select(Issue)).all()
    features = []
    items = []
    for issue in issues:
        point = to_shape(issue.geom)
        items.append(
            {
                "id": issue.id,
                "public_id": issue.public_id,
                "title": issue.title,
                "category": issue.category,
                "severity": issue.severity,
                "status": issue.status,
                "longitude": point.x,
                "latitude": point.y,
            }
        )
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(point),
                "properties": {
                    "public_id": issue.public_id,
                    "status": issue.status,
                    "record_type": "verified_issue",
                },
            }
        )
    return {
        "count": len(items),
        "items": items,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


@router.post("/verify")
def verify(
    body: VerifyBody,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.decision not in DECISIONS:
        raise HTTPException(status_code=400, detail="Unknown decision.")
    report = db.scalar(select(Report).where(Report.tracking_id == body.tracking_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")

    related_report = None
    related_issue = None
    if body.related_tracking_id:
        related_report = db.scalar(select(Report).where(Report.tracking_id == body.related_tracking_id))
        if related_report is None:
            raise HTTPException(status_code=404, detail="Related tracking ID not found.")
        link = db.scalar(select(IssueReport).where(IssueReport.report_id == related_report.id))
        if link:
            related_issue = db.get(Issue, link.issue_id)
    if body.related_issue_id:
        related_issue = db.get(Issue, body.related_issue_id)
        if related_issue is None:
            raise HTTPException(status_code=404, detail="Related issue not found.")

    created_issue = None
    point = to_shape(report.geom)

    if body.decision == "new_candidate_issue":
        already = db.scalar(select(IssueReport).where(IssueReport.report_id == report.id))
        if already is not None:
            raise HTTPException(
                status_code=409,
                detail="This report is already linked to a verified issue. Record a different decision instead.",
            )
        public_id = f"ISS-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f')}"
        created_issue = Issue(
            public_id=public_id,
            title=report.description[:240],
            category=report.category,
            severity=report.severity,
            status="open",
            geom=from_shape(Point(point.x, point.y), srid=4326),
            notes=body.notes,
        )
        db.add(created_issue)
        db.flush()
        db.add(IssueReport(issue_id=created_issue.id, report_id=report.id, role="source"))
        related_issue = created_issue
        report.status = "acknowledged"
    elif body.decision in {"possible_duplicate", "existing_issue"}:
        if related_issue is None and related_report is None:
            raise HTTPException(
                status_code=400,
                detail="Choose a related report or issue. Nearby items are never merged automatically.",
            )
        if related_issue is not None:
            existing_link = db.scalar(select(IssueReport).where(IssueReport.report_id == report.id))
            if existing_link is None:
                db.add(IssueReport(issue_id=related_issue.id, report_id=report.id, role="duplicate_candidate"))
        report.status = "under_review"
    elif body.decision == "insufficient_evidence":
        report.status = "insufficient_evidence"
    elif body.decision == "evidence_mismatch":
        report.status = "under_review"
    elif body.decision == "possibly_resolved":
        report.status = "resolved_unverified"
        if related_issue is not None:
            related_issue.status = "possibly_resolved"

    verification = Verification(
        report_id=report.id,
        decision=body.decision,
        related_report_id=related_report.id if related_report else None,
        related_issue_id=related_issue.id if related_issue else None,
        score=body.score,
        reasons=body.reasons,
        notes=body.notes,
        decided_by=actor,
    )
    db.add(verification)
    audit(
        db,
        actor=actor,
        action=f"verification.{body.decision}",
        entity_type="report",
        entity_id=report.tracking_id,
        detail={
            "related_report": body.related_tracking_id,
            "related_issue_id": related_issue.id if related_issue else None,
            "score": body.score,
        },
        note=body.notes,
    )
    if related_issue is not None:
        refresh_issue(db, related_issue.id)
    recurrence_hits = []
    if created_issue is not None:
        db.flush()
        db.refresh(created_issue)
        recurrence_hits = recurrences_for_new_issue(db, created_issue)
        if recurrence_hits:
            audit(
                db,
                actor=actor,
                action="issue.follows_completed_project",
                entity_type="issue",
                entity_id=created_issue.public_id,
                detail={"projects": recurrence_hits},
            )
    db.commit()
    return {
        "ok": True,
        "decision": body.decision,
        "follows_completed_projects": recurrence_hits,
        "tracking_id": report.tracking_id,
        "issue_public_id": created_issue.public_id if created_issue else (related_issue.public_id if related_issue else None),
        "reports_preserved": True,
    }
