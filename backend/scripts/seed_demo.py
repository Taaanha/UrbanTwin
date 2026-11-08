"""Create clearly labelled DEMONSTRATION data so every module has something to show.

Run from D:\\Urbantwin\\backend (after `alembic upgrade head` and the OSM import):

    .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py            # first time
    .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py --reset    # wipe demo rows and recreate

Everything created here has is_demo = true. Reports, issues, projects, drains and
green spaces are synthetic. They are NOT municipal records and NOT real incidents.
Real OSM roads/buildings are only used as positions to attach the demo items to.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geoalchemy2.shape import from_shape, to_shape  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from shapely.geometry import LineString, Point, box  # noqa: E402
from sqlalchemy import delete, func, select, text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.accountability import Inspection, Project, ProjectEvidence, ProjectUpdate  # noqa: E402
from app.models.geo import DataSource, Drain, Road  # noqa: E402
from app.models.investigator import Issue, IssueReport, Verification  # noqa: E402
from app.models.planner import Intervention  # noqa: E402
from app.models.reports import EvidenceFile, Report  # noqa: E402
from app.models.simulation import GreenSpace  # noqa: E402
from app.services.audit import audit  # noqa: E402
from app.services.intelligence import refresh_all  # noqa: E402
from app.services.planner import generate_interventions  # noqa: E402
from app.services.uploads import upload_dir  # noqa: E402

NOW = datetime.now(timezone.utc)
ACTOR = "demo-seed"
_counter = {"n": 0}


def demo_image(label: str) -> dict:
    """A plain placeholder picture that says DEMO, so nobody mistakes it for evidence."""
    import uuid

    img = Image.new("RGB", (480, 320), (70, 80, 95))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "UrbanTwin DEMO IMAGE", fill=(255, 255, 255))
    draw.text((20, 50), label[:60], fill=(255, 210, 120))
    name = f"{uuid.uuid4().hex}.png"
    path = upload_dir() / name
    img.save(path)
    return {"stored_name": name, "original_name": f"demo-{label[:20].replace(' ', '-')}.png", "content_type": "image/png", "size_bytes": path.stat().st_size}


def reset(db) -> None:
    demo_issue_ids = select(Issue.id).where(Issue.is_demo.is_(True))
    demo_report_ids = select(Report.id).where(Report.is_demo.is_(True))
    demo_project_ids = select(Project.id).where(Project.is_demo.is_(True))
    for model in (ProjectEvidence, ProjectUpdate, Inspection):
        db.execute(delete(model).where(model.project_id.in_(demo_project_ids)))
    db.execute(delete(Project).where(Project.is_demo.is_(True)))
    demo_intervention_ids = select(Intervention.id).where(Intervention.issue_id.in_(demo_issue_ids))
    db.execute(text("DELETE FROM plan_items WHERE intervention_id IN (SELECT id FROM interventions WHERE issue_id IN (SELECT id FROM issues WHERE is_demo))"))
    db.execute(text("DELETE FROM cost_estimates WHERE intervention_id IN (SELECT id FROM interventions WHERE issue_id IN (SELECT id FROM issues WHERE is_demo))"))
    db.execute(delete(Intervention).where(Intervention.id.in_(demo_intervention_ids)))
    db.execute(text("DELETE FROM audit_logs WHERE actor = 'demo-seed'"))
    db.execute(text("DELETE FROM issue_assets WHERE issue_id IN (SELECT id FROM issues WHERE is_demo)"))
    db.execute(text("DELETE FROM issue_relations WHERE from_issue_id IN (SELECT id FROM issues WHERE is_demo) OR to_issue_id IN (SELECT id FROM issues WHERE is_demo)"))
    db.execute(delete(Verification).where(Verification.report_id.in_(demo_report_ids)))
    db.execute(delete(IssueReport).where(IssueReport.report_id.in_(demo_report_ids)))
    db.execute(delete(Issue).where(Issue.is_demo.is_(True)))
    db.execute(delete(EvidenceFile).where(EvidenceFile.report_id.in_(demo_report_ids)))
    db.execute(delete(Report).where(Report.is_demo.is_(True)))
    db.execute(delete(Drain).where(Drain.is_demo.is_(True)))
    db.execute(delete(GreenSpace).where(GreenSpace.is_demo.is_(True)))
    db.flush()


def pick_roads(db, n: int):
    """Longest OSM roads (by degree length, fine for choosing demo anchor points)."""
    rows = db.scalars(select(Road).where(Road.is_demo.is_(False))).all()
    shapes = sorted((to_shape(r.geom) for r in rows), key=lambda g: g.length, reverse=True)
    return shapes[:n], [None] * min(n, len(shapes))


def point_on(line: LineString, fraction: float) -> Point:
    return line.interpolate(fraction, normalized=True)


def _next_tracking_id() -> str:
    _counter["n"] += 1
    return f"UT-DEMO-{NOW:%Y%m%d%H%M%S}-{_counter['n']:03d}"


def make_report(db, *, pt: Point, category, severity, text_, days_ago, with_image=True) -> Report:
    created = NOW - timedelta(days=days_ago)
    report = Report(
        tracking_id=_next_tracking_id(),
        category=category,
        severity=severity,
        description=f"[DEMO] {text_}",
        language="en",
        reporter_name=None,
        geom=from_shape(Point(pt.x, pt.y), srid=4326),
        status="submitted",
        is_demo=True,
        created_at=created,
    )
    if with_image:
        report.evidence.append(EvidenceFile(**demo_image(f"{category} {severity}")))
    db.add(report)
    db.flush()
    return report


def verify_as_issue(db, report: Report, days_ago: float, notes: str) -> Issue:
    pt = to_shape(report.geom)
    issue = Issue(
        public_id=f"ISS-DEMO-{report.id:04d}",
        title=report.description[:240],
        category=report.category,
        severity=report.severity,
        status="open",
        geom=from_shape(Point(pt.x, pt.y), srid=4326),
        notes=notes,
        is_demo=True,
        created_at=NOW - timedelta(days=days_ago),
    )
    db.add(issue)
    db.flush()
    db.add(IssueReport(issue_id=issue.id, report_id=report.id, role="source"))
    db.add(
        Verification(
            report_id=report.id,
            decision="new_candidate_issue",
            related_issue_id=issue.id,
            notes=notes,
            decided_by=ACTOR,
            reasons={"demo": True},
            decided_at=NOW - timedelta(days=days_ago),
        )
    )
    report.status = "acknowledged"
    audit(db, actor=ACTOR, action="verification.new_candidate_issue", entity_type="report", entity_id=report.tracking_id, detail={"demo": True})
    return issue


def seed(db) -> None:
    roads, names = pick_roads(db, 6)
    if not roads:
        raise SystemExit("No roads in the database. Run scripts/import_osm_noakhali.py first.")
    while len(roads) < 6:
        roads.append(roads[0])

    # 1) Demo drains alongside three roads (OSM has no drains for this area).
    for line in roads[:3]:
        offset = line.parallel_offset(0.00008, "left")
        if offset.geom_type == "MultiLineString":
            offset = max(offset.geoms, key=lambda g: g.length)
        if offset.is_empty or offset.geom_type != "LineString":
            continue
        db.add(Drain(name="DEMO drain (synthetic)", waterway="drain", osm_id=None, geom=from_shape(offset, srid=4326), properties={"demo": True}, is_demo=True))
    db.add(
        DataSource(
            layer="demo_drains",
            source_name="UrbanTwin synthetic demonstration",
            license="Not official municipal data",
            crs="EPSG:4326",
            limitations="Synthetic lines offset from real OSM roads so City Intelligence has something to link. NOT a drainage inventory.",
            processing_steps="Parallel offset (~9 m) of three OSM roads.",
            is_demo=True,
        )
    )

    # 2) Demo green spaces near the study centre.
    cx, cy = 91.099, 22.869
    for k, (dx, dy, w) in enumerate([(-0.012, 0.010, 0.0016), (0.010, 0.006, 0.0014), (-0.004, -0.010, 0.0018), (0.015, -0.012, 0.0012)]):
        db.add(GreenSpace(name=f"DEMO green patch {k + 1}", kind="demo_park", geom=from_shape(box(cx + dx, cy + dy, cx + dx + w, cy + dy + w * 0.8), srid=4326), is_demo=True, properties={"demo": True}))
    db.add(DataSource(layer="demo_green_spaces", source_name="UrbanTwin synthetic demonstration", license="Not official municipal data", crs="EPSG:4326", limitations="Four invented rectangles for the simulation demo. Not real parks.", processing_steps="Hand-placed boxes around the study centre.", is_demo=True))

    # 3) Reports and verified issues (all synthetic).
    r0, r1, r2, r3, r4, r5 = roads
    a = make_report(db, pt=point_on(r0, 0.30), category="pothole", severity="high", text_="Deep pothole on the main road near the market.", days_ago=60)
    issue_a = verify_as_issue(db, a, 58, "Demo: verified from photo.")
    b = make_report(db, pt=point_on(r0, 0.30), category="pothole", severity="high", text_="Same pothole again, water collects here.", days_ago=3)  # same spot, later
    c = make_report(db, pt=point_on(r1, 0.50), category="blocked_drainage", severity="critical", text_="Drain choked with plastic after rain.", days_ago=12)
    issue_c = verify_as_issue(db, c, 11, "Demo: confirmed on site visit.")
    d = make_report(db, pt=point_on(r2, 0.40), category="waterlogging", severity="high", text_="Road waterlogged for two days.", days_ago=9)
    issue_d = verify_as_issue(db, d, 8, "Demo.")
    e = make_report(db, pt=point_on(r3, 0.60), category="garbage", severity="medium", text_="Garbage pile growing beside the road.", days_ago=7)
    issue_e = verify_as_issue(db, e, 6, "Demo.")
    f = make_report(db, pt=point_on(r4, 0.50), category="damaged_road", severity="medium", text_="Surface breaking up along the edge.", days_ago=45)
    issue_f = verify_as_issue(db, f, 44, "Demo.")
    g = make_report(db, pt=point_on(r5, 0.50), category="broken_sidewalk", severity="low", text_="Cracked footpath slabs.", days_ago=5)
    # two unverified near-duplicates left in the queue for the Investigator demo
    make_report(db, pt=point_on(r3, 0.60), category="garbage", severity="medium", text_="Rubbish heap beside the road, getting bigger.", days_ago=1)
    make_report(db, pt=Point(point_on(r5, 0.50).x + 0.00002, point_on(r5, 0.50).y), category="broken_sidewalk", severity="low", text_="Footpath slabs cracked and loose.", days_ago=0.5)

    # 4) A completed repair of issue A (30 days ago) and the later recurrence report B (3 days ago).
    refresh_all(db)
    generate_interventions(db)
    db.flush()
    verify_b = verify_as_issue(db, b, 3, "Demo: appears to be the same spot as ISS-A, after repair.")
    refresh_all(db)
    generate_interventions(db)
    db.flush()

    def start_project(issue, budget, spec, contractor):
        intervention = db.scalar(select(Intervention).where(Intervention.issue_id == issue.id))
        project = Project(
            public_id=f"PRJ-DEMO-{issue.id:04d}",
            intervention_id=intervention.id,
            issue_id=issue.id,
            title=intervention.title,
            status="approved",
            approved_budget_bdt=budget,
            specification=spec,
            contractor_name=contractor,
            start_date=(NOW - timedelta(days=40)).date(),
            planned_end_date=(NOW - timedelta(days=32)).date(),
            is_demo=True,
            created_by=ACTOR,
        )
        db.add(project)
        intervention.status = "approved_project"
        db.flush()
        audit(db, actor=ACTOR, action="project.created", entity_type="project", entity_id=project.public_id, detail={"demo": True})
        return project

    p1 = start_project(issue_a, 12_000, "DEMO spec: cut, clean and patch 4 m2 with bituminous mix; compact; seal edges.", "DEMO Contractor Ltd (fictional)")
    db.add(ProjectUpdate(project_id=p1.id, progress_pct=50, expenditure_bdt=6_000, note="Demo: excavation and cleaning done.", author=ACTOR, created_at=NOW - timedelta(days=36)))
    db.add(ProjectUpdate(project_id=p1.id, progress_pct=100, expenditure_bdt=6_500, note="Demo: patch laid and compacted.", author=ACTOR, created_at=NOW - timedelta(days=31)))
    p1.status, p1.completed_at = "completed", NOW - timedelta(days=30)
    db.add(ProjectEvidence(project_id=p1.id, kind="completion", uploaded_by=ACTOR, **demo_image("completion PRJ-A")))
    db.add(Inspection(project_id=p1.id, inspector="DEMO Inspector (fictional)", independent=False, outcome="meets_specification", condition_score=4, notes="Demo: internal sign-off.", inspected_at=NOW - timedelta(days=29)))
    issue_a.status = "repair_reported"
    intervention_a = db.get(Intervention, p1.intervention_id)
    intervention_a.status = "completed"

    p2 = start_project(issue_f, 55_000, "DEMO spec: 10 m x 3 m surface repair, 40 mm overlay.", None)
    db.add(ProjectUpdate(project_id=p2.id, progress_pct=35, expenditure_bdt=18_000, note="Demo: edge reinstatement started.", author=ACTOR, created_at=NOW - timedelta(days=4)))
    p2.status = "in_progress"
    generate_interventions(db)
    db.flush()


def main() -> None:
    do_reset = "--reset" in sys.argv
    db = SessionLocal()
    try:
        exists = db.scalar(select(func.count()).select_from(Report).where(Report.is_demo.is_(True)))
        if exists and not do_reset:
            print(f"{exists} demo reports already exist. Use --reset to recreate them.")
            return
        if exists:
            reset(db)
            db.execute(delete(DataSource).where(DataSource.layer.in_(["demo_drains", "demo_green_spaces"])))
        seed(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print("Demo data created (all rows flagged is_demo). Open the dashboard with your staff token.")


if __name__ == "__main__":
    main()
