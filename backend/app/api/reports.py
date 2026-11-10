from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_staff
from app.database import get_db
from app.models.reports import EvidenceFile, Report
from app.report_constants import CATEGORIES, REPORT_STATUSES, SEVERITIES
from app.services.audit import audit
from app.services.uploads import save_images, upload_dir
from pydantic import BaseModel

router = APIRouter(prefix="/api/reports", tags=["reports"])


class StatusBody(BaseModel):
    status: str

BANGLADESH_BOUNDS = (88.0, 20.5, 92.8, 26.8)


def _tracking_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")[-6:].upper()
    return f"UT-{stamp}-{suffix}"


def _validate_location(lon: float, lat: float) -> None:
    west, south, east, north = BANGLADESH_BOUNDS
    if not (west <= lon <= east and south <= lat <= north):
        raise HTTPException(
            status_code=400,
            detail="Coordinates must be inside Bangladesh (check GPS / map pin).",
        )


def _public_report(report: Report, include_contact: bool = False) -> dict[str, Any]:
    point = to_shape(report.geom)
    payload = {
        "id": report.id,
        "tracking_id": report.tracking_id,
        "category": report.category,
        "severity": report.severity,
        "description": report.description,
        "location_text": report.location_text,
        "language": report.language,
        "status": report.status,
        "record_type": "citizen_report",
        "is_verified_issue": False,
        "is_demo": report.is_demo,
        "longitude": point.x,
        "latitude": point.y,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        "evidence": [
            {
                "id": item.id,
                "original_name": item.original_name,
                "content_type": item.content_type,
                "url": f"/api/reports/track/{report.tracking_id}/evidence/{item.id}",
            }
            for item in report.evidence
        ],
    }
    if include_contact:
        payload["reporter_name"] = report.reporter_name
    return payload


@router.get("/meta")
def report_meta() -> dict[str, Any]:
    return {
        "categories": CATEGORIES,
        "severities": list(SEVERITIES),
        "statuses": list(REPORT_STATUSES),
        "note": "A report is a submission, not a verified municipal issue.",
    }


@router.post("")
async def create_report(
    category: str = Form(),
    severity: str = Form(),
    description: str = Form(),
    latitude: float = Form(),
    longitude: float = Form(),
    language: str = Form("en"),
    reporter_name: str | None = Form(None),
    location_text: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category.")
    if severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Unknown severity.")
    if language not in {"en", "bn"}:
        raise HTTPException(status_code=400, detail="language must be en or bn.")
    text = description.strip()
    if len(text) < 8:
        raise HTTPException(status_code=400, detail="Please describe the problem (at least 8 characters).")
    _validate_location(longitude, latitude)
    place = " ".join((location_text or "").split())
    if len(place) > 200:
        raise HTTPException(status_code=400, detail="The place name or landmark is too long (200 characters at most).")

    saved = await save_images(files)
    tracking_id = _tracking_id()
    while db.scalar(select(Report.id).where(Report.tracking_id == tracking_id)):
        tracking_id = _tracking_id()

    report = Report(
        tracking_id=tracking_id,
        category=category,
        severity=severity,
        description=text,
        language=language,
        reporter_name=(reporter_name or "").strip() or None,
        location_text=place or None,
        geom=from_shape(Point(longitude, latitude), srid=4326),
        status="submitted",
    )
    for item in saved:
        report.evidence.append(EvidenceFile(**item))
    db.add(report)
    db.commit()
    db.refresh(report)
    db.refresh(report, attribute_names=["evidence"])
    return _public_report(report)


@router.get("/track/{tracking_id}")
def get_report(tracking_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    report = db.scalar(
        select(Report).options(selectinload(Report.evidence)).where(Report.tracking_id == tracking_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")
    return _public_report(report)


@router.get("")
def list_reports(
    _actor: str = Depends(require_staff),
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    since: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = select(Report).options(selectinload(Report.evidence)).order_by(Report.created_at.desc())
    if category:
        query = query.where(Report.category == category)
    if severity:
        query = query.where(Report.severity == severity)
    if status:
        query = query.where(Report.status == status)
    if since:
        query = query.where(Report.created_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc))
    rows = db.scalars(query).all()
    return {
        "note": "These are citizen reports, not verified issues.",
        "count": len(rows),
        "items": [_public_report(row) for row in rows],
    }


@router.get("/geojson")
def reports_geojson(
    _actor: str = Depends(require_staff),
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = select(Report)
    if category:
        query = query.where(Report.category == category)
    if severity:
        query = query.where(Report.severity == severity)
    if status:
        query = query.where(Report.status == status)
    rows = db.scalars(query).all()
    features = []
    for report in rows:
        point = to_shape(report.geom)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(point),
                "properties": {
                    "tracking_id": report.tracking_id,
                    "category": report.category,
                    "severity": report.severity,
                    "status": report.status,
                    "record_type": "citizen_report",
                    "is_verified_issue": False,
                    "is_demo": report.is_demo,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


@router.patch("/track/{tracking_id}/status")
def update_status(
    tracking_id: str,
    payload: StatusBody,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    status = payload.status
    if status not in REPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    report = db.scalar(
        select(Report).options(selectinload(Report.evidence)).where(Report.tracking_id == tracking_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")
    previous = report.status
    report.status = status
    audit(
        db,
        actor=actor,
        action="report.status_changed",
        entity_type="report",
        entity_id=report.tracking_id,
        detail={"from": previous, "to": status},
    )
    db.commit()
    db.refresh(report)
    return _public_report(report)


@router.get("/track/{tracking_id}/evidence/{file_id}")
def download_evidence(tracking_id: str, file_id: int, db: Session = Depends(get_db)):
    report = db.scalar(select(Report).where(Report.tracking_id == tracking_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found.")
    item = db.scalar(
        select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.report_id == report.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence file not found.")
    path = upload_dir() / item.stored_name
    if not path.exists() or not path.resolve().is_relative_to(upload_dir().resolve()):
        raise HTTPException(status_code=404, detail="File missing.")
    return FileResponse(path, media_type=item.content_type, filename=item.original_name)
