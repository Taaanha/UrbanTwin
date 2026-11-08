from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.accountability_constants import (
    CONTEXT_LIMITATIONS,
    DISCLAIMER,
    FAST_RECURRENCE_DAYS,
    INSPECTION_OUTCOMES,
    PROJECT_STATUSES,
)
from app.auth import require_staff
from app.database import get_db
from app.models.accountability import Inspection, Project, ProjectEvidence, ProjectUpdate
from app.models.investigator import Issue
from app.models.planner import Intervention
from app.services.accountability import (
    findings_for,
    indicative_estimate_for,
    lifecycle,
    progress_to_date,
    project_brief,
    spent_to_date,
)
from app.services.audit import audit
from app.services.uploads import save_images, upload_dir

router = APIRouter(prefix="/api/accountability", tags=["accountability"], dependencies=[Depends(require_staff)])


def _load(db: Session, public_id: str) -> Project:
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.updates), selectinload(Project.inspections), selectinload(Project.evidence))
        .where(Project.public_id == public_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _public_id() -> str:
    return f"PRJ-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%f')}"


async def _store(
    db: Session,
    project: Project,
    files: list[UploadFile],
    *,
    kind: str,
    actor: str,
    update: ProjectUpdate | None = None,
    inspection: Inspection | None = None,
) -> int:
    saved = await save_images(files)
    for item in saved:
        db.add(
            ProjectEvidence(
                project_id=project.id,
                update_id=update.id if update else None,
                inspection_id=inspection.id if inspection else None,
                kind=kind,
                uploaded_by=actor,
                **item,
            )
        )
    return len(saved)


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    projects = db.scalars(select(Project).options(selectinload(Project.updates), selectinload(Project.inspections), selectinload(Project.evidence))).all()
    by_status = {status: 0 for status in PROJECT_STATUSES}
    flagged = 0
    for project in projects:
        by_status[project.status] = by_status.get(project.status, 0) + 1
        if project.completed_at is not None and findings_for(db, project)["review_flag"] != "none":
            flagged += 1
    return {
        "disclaimer": DISCLAIMER,
        "projects": len(projects),
        "by_status": by_status,
        "approved_budget_bdt": round(sum(p.approved_budget_bdt for p in projects), 2),
        "spent_bdt": round(sum(spent_to_date(p) for p in projects), 2),
        "flagged_for_review": flagged,
        "demo_projects": sum(1 for p in projects if p.is_demo),
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> dict[str, Any]:
    projects = db.scalars(
        select(Project)
        .options(selectinload(Project.updates), selectinload(Project.inspections), selectinload(Project.evidence))
        .order_by(Project.created_at.desc())
    ).all()
    return {"disclaimer": DISCLAIMER, "items": [project_brief(db, p) for p in projects]}


@router.get("/eligible-interventions")
def eligible(db: Session = Depends(get_db)) -> dict[str, Any]:
    taken = set(db.scalars(select(Project.intervention_id)).all())
    rows = db.scalars(select(Intervention).order_by(Intervention.priority_score.desc())).all()
    items = []
    for row in rows:
        if row.id in taken:
            continue
        issue = db.get(Issue, row.issue_id)
        items.append(
            {
                "public_id": row.public_id,
                "title": row.title,
                "issue_public_id": issue.public_id if issue else None,
                "priority_score": row.priority_score,
                "indicative_mid_bdt": indicative_estimate_for(db, row.id),
            }
        )
    return {"items": items}


class ProjectCreate(BaseModel):
    intervention_public_id: str
    approved_budget_bdt: float = Field(gt=0, le=1_000_000_000)
    specification: str = Field(min_length=10, max_length=4000)
    contractor_name: str | None = Field(default=None, max_length=256)
    start_date: date | None = None
    planned_end_date: date | None = None
    title: str | None = Field(default=None, max_length=256)


@router.post("/projects")
def create_project(
    body: ProjectCreate,
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    intervention = db.scalar(select(Intervention).where(Intervention.public_id == body.intervention_public_id))
    if intervention is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    if db.scalar(select(Project.id).where(Project.intervention_id == intervention.id)):
        raise HTTPException(status_code=409, detail="This intervention already has a project.")
    if body.start_date and body.planned_end_date and body.planned_end_date < body.start_date:
        raise HTTPException(status_code=400, detail="planned_end_date is before start_date.")
    issue = db.get(Issue, intervention.issue_id)
    project = Project(
        public_id=_public_id(),
        intervention_id=intervention.id,
        issue_id=intervention.issue_id,
        title=(body.title or intervention.title)[:256],
        status="approved",
        approved_budget_bdt=body.approved_budget_bdt,
        specification=body.specification.strip(),
        contractor_name=(body.contractor_name or "").strip() or None,
        start_date=body.start_date,
        planned_end_date=body.planned_end_date,
        is_demo=bool(issue and issue.is_demo),
        created_by=actor,
    )
    db.add(project)
    intervention.status = "approved_project"
    db.flush()
    audit(
        db,
        actor=actor,
        action="project.created",
        entity_type="project",
        entity_id=project.public_id,
        detail={"intervention": intervention.public_id, "approved_budget_bdt": body.approved_budget_bdt},
    )
    db.commit()
    return project_brief(db, _load(db, project.public_id))


@router.get("/projects/{public_id}")
def project_detail(public_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = _load(db, public_id)
    return {
        **project_brief(db, project),
        "specification": project.specification,
        "updates": [
            {
                "id": u.id,
                "progress_pct": u.progress_pct,
                "expenditure_bdt": u.expenditure_bdt,
                "note": u.note,
                "author": u.author,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in project.updates
        ],
        "inspections": [
            {
                "id": i.id,
                "inspector": i.inspector,
                "independent": i.independent,
                "outcome": i.outcome,
                "condition_score": i.condition_score,
                "notes": i.notes,
                "inspected_at": i.inspected_at.isoformat() if i.inspected_at else None,
            }
            for i in project.inspections
        ],
        "evidence": [
            {
                "id": e.id,
                "kind": e.kind,
                "original_name": e.original_name,
                "uploaded_by": e.uploaded_by,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "url": f"/api/accountability/projects/{project.public_id}/evidence/{e.id}",
            }
            for e in project.evidence
        ],
        "lifecycle": lifecycle(db, project),
        "findings": findings_for(db, project) if project.completed_at else None,
    }


@router.post("/projects/{public_id}/updates")
async def add_update(
    public_id: str,
    progress_pct: int = Form(ge=0, le=100),
    expenditure_bdt: float = Form(0.0, ge=0),
    note: str = Form(min_length=3),
    files: list[UploadFile] = File(default=[]),
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = _load(db, public_id)
    if project.status in {"completed", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Project is {project.status}; progress cannot be added.")
    previous = progress_to_date(project)
    if progress_pct < previous:
        raise HTTPException(status_code=400, detail=f"Progress cannot go down (last recorded {previous}%).")
    update = ProjectUpdate(
        project_id=project.id,
        progress_pct=progress_pct,
        expenditure_bdt=expenditure_bdt,
        note=note.strip(),
        author=actor,
    )
    db.add(update)
    db.flush()
    await _store(db, project, files, kind="progress", actor=actor, update=update)
    if progress_pct > 0:
        project.status = "in_progress"
    audit(
        db,
        actor=actor,
        action="project.progress",
        entity_type="project",
        entity_id=project.public_id,
        detail={"progress_pct": progress_pct, "expenditure_bdt": expenditure_bdt},
    )
    db.commit()
    return project_brief(db, _load(db, public_id))


@router.post("/projects/{public_id}/complete")
async def complete_project(
    public_id: str,
    note: str = Form(min_length=3),
    completed_on: date | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = _load(db, public_id)
    if project.status == "completed":
        raise HTTPException(status_code=409, detail="Project is already marked complete.")
    if project.status == "cancelled":
        raise HTTPException(status_code=409, detail="Project is cancelled.")
    if completed_on and completed_on > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="completed_on cannot be in the future.")
    real_files = [f for f in files if f.filename]
    if not real_files:
        raise HTTPException(status_code=400, detail="Upload at least one completion photo as evidence.")
    when = (
        datetime.combine(completed_on, time(12, 0), tzinfo=timezone.utc)
        if completed_on
        else datetime.now(timezone.utc)
    )
    update = ProjectUpdate(project_id=project.id, progress_pct=100, expenditure_bdt=0.0, note=note.strip(), author=actor)
    db.add(update)
    db.flush()
    await _store(db, project, real_files, kind="completion", actor=actor, update=update)
    project.status = "completed"
    project.completed_at = when
    intervention = db.get(Intervention, project.intervention_id)
    if intervention:
        intervention.status = "completed"
    issue = db.get(Issue, project.issue_id)
    if issue:
        issue.status = "repair_reported"
    audit(
        db,
        actor=actor,
        action="project.completed",
        entity_type="project",
        entity_id=project.public_id,
        detail={"completed_at": when.isoformat()},
        note=note,
    )
    db.commit()
    return project_brief(db, _load(db, public_id))


@router.post("/projects/{public_id}/inspections")
async def add_inspection(
    public_id: str,
    inspector: str = Form(min_length=2, max_length=128),
    outcome: str = Form(),
    notes: str = Form(min_length=3),
    independent: bool = Form(False),
    condition_score: int | None = Form(None, ge=1, le=5),
    files: list[UploadFile] = File(default=[]),
    actor: str = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if outcome not in INSPECTION_OUTCOMES:
        raise HTTPException(status_code=400, detail="Unknown inspection outcome.")
    project = _load(db, public_id)
    if project.completed_at is None:
        raise HTTPException(status_code=409, detail="Inspect after completion has been reported.")
    inspection = Inspection(
        project_id=project.id,
        inspector=inspector.strip(),
        independent=independent,
        outcome=outcome,
        condition_score=condition_score,
        notes=notes.strip(),
    )
    db.add(inspection)
    db.flush()
    await _store(db, project, files, kind="inspection", actor=actor, inspection=inspection)
    issue = db.get(Issue, project.issue_id)
    if issue is not None and independent:
        issue.status = "resolved_verified" if outcome == "meets_specification" else "repair_disputed"
    audit(
        db,
        actor=actor,
        action="project.inspected",
        entity_type="project",
        entity_id=project.public_id,
        detail={"outcome": outcome, "independent": independent, "condition_score": condition_score},
    )
    db.commit()
    return project_brief(db, _load(db, public_id))


@router.get("/projects/{public_id}/evidence/{evidence_id}")
def download_evidence(public_id: str, evidence_id: int, db: Session = Depends(get_db)):
    project = _load(db, public_id)
    item = next((e for e in project.evidence if e.id == evidence_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    path = upload_dir() / item.stored_name
    if not path.exists() or not path.resolve().is_relative_to(upload_dir().resolve()):
        raise HTTPException(status_code=404, detail="File missing.")
    return FileResponse(path, media_type=item.content_type, filename=item.original_name)


@router.get("/recurrence")
def recurrence_screen(db: Session = Depends(get_db)) -> dict[str, Any]:
    projects = db.scalars(
        select(Project)
        .options(selectinload(Project.updates), selectinload(Project.inspections), selectinload(Project.evidence))
        .where(Project.completed_at.is_not(None))
    ).all()
    items = []
    for project in projects:
        findings = findings_for(db, project)
        items.append(
            {
                "project": project_brief(db, project),
                "review_flag": findings["review_flag"],
                "reasons": findings["reasons"],
                "recurrence": findings["recurrence"],
            }
        )
    items.sort(key=lambda row: (row["review_flag"] == "none", row["project"]["public_id"]))
    return {
        "disclaimer": DISCLAIMER,
        "context_limitations": CONTEXT_LIMITATIONS,
        "screening_threshold_days": FAST_RECURRENCE_DAYS,
        "items": items,
    }


@router.get("/geojson")
def geojson(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(
        select(Project).options(selectinload(Project.updates), selectinload(Project.inspections), selectinload(Project.evidence))
    ).all()
    features = []
    for project in rows:
        issue = db.get(Issue, project.issue_id)
        if issue is None:
            continue
        brief = project_brief(db, project)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(issue.geom)),
                "properties": {
                    "public_id": project.public_id,
                    "status": project.status,
                    "issue_status": issue.status,
                    "review_flag": brief["review_flag"],
                    "record_type": "approved_project",
                    "is_demo": project.is_demo,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
