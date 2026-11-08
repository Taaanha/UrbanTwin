"""Spatial correlation for verified issues. Never claims drainage caused a pothole."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import LineString, mapping, Point
from shapely.ops import nearest_points
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.geo import Drain, Road, Ward, WaterBody
from app.models.intelligence import IssueAsset, IssueRelation
from app.models.investigator import Issue, IssueReport, Verification
from app.models.reports import Report
from app.services.duplicates import RELATED_CATEGORIES, haversine_m

ROAD_SNAP_M = 60.0
DRAIN_SNAP_M = 80.0
WATER_CONTEXT_M = 80.0
NEARBY_ISSUE_M = 80.0
RECURRENCE_M = 40.0
RECURRENCE_GAP_DAYS = 14.0

DISCLAIMER = (
    "These links are spatial correlations from OSM geometry and verified issue "
    "locations. They are not proof of cause, municipal ownership, or drainage failure."
)

DRAIN_NOTE = (
    "OSM drain features in this study envelope may be missing. Absence of a drain "
    "link is not evidence that Noakhali Paurashava has no drainage."
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _days_apart(a: datetime | None, b: datetime | None) -> float | None:
    left, right = _aware(a), _aware(b)
    if not left or not right:
        return None
    return abs((left - right).total_seconds()) / 86400.0


def _related(a: str, b: str) -> bool:
    if a == b:
        return True
    pair = frozenset({a, b})
    return any(pair <= group for group in RELATED_CATEGORIES)


def _point(issue: Issue) -> Point:
    return to_shape(issue.geom)


def _nearest_road(db: Session, issue: Issue) -> IssueAsset | None:
    distance = func.ST_DistanceSphere(Road.geom, issue.geom)
    row = db.execute(select(Road, distance.label("d")).order_by(distance).limit(1)).first()
    if row is None:
        return None
    road, metres = row
    metres = float(metres or 0)
    if metres > ROAD_SNAP_M:
        return None
    origin = _point(issue)
    _, snap = nearest_points(origin, to_shape(road.geom))
    name = road.name or (f"OSM {road.highway}" if road.highway else f"OSM way {road.osm_id}")
    return IssueAsset(
        issue_id=issue.id,
        asset_kind="road",
        asset_id=road.id,
        asset_name=name,
        distance_m=round(metres, 1),
        snap_lon=snap.x,
        snap_lat=snap.y,
        generated_by="spatial",
        notes=f"Nearest OSM road within {ROAD_SNAP_M:.0f} m ({metres:.1f} m). Correlation only.",
    )


def _nearest_drain(db: Session, issue: Issue) -> IssueAsset | None:
    if db.scalar(select(func.count()).select_from(Drain)) == 0:
        return None
    distance = func.ST_DistanceSphere(Drain.geom, issue.geom)
    row = db.execute(select(Drain, distance.label("d")).order_by(distance).limit(1)).first()
    if row is None:
        return None
    drain, metres = row
    metres = float(metres or 0)
    if metres > DRAIN_SNAP_M:
        return None
    origin = _point(issue)
    _, snap = nearest_points(origin, to_shape(drain.geom))
    name = drain.name or drain.waterway or f"OSM drain {drain.osm_id}"
    return IssueAsset(
        issue_id=issue.id,
        asset_kind="drain",
        asset_id=drain.id,
        asset_name=name,
        distance_m=round(metres, 1),
        snap_lon=snap.x,
        snap_lat=snap.y,
        generated_by="spatial",
        notes=f"Nearest OSM drain/ditch within {DRAIN_SNAP_M:.0f} m. Not a municipal inventory.",
    )


def _nearest_water(db: Session, issue: Issue) -> IssueAsset | None:
    distance = func.ST_DistanceSphere(WaterBody.geom, issue.geom)
    row = db.execute(select(WaterBody, distance.label("d")).order_by(distance).limit(1)).first()
    if row is None:
        return None
    water, metres = row
    metres = float(metres or 0)
    if metres > WATER_CONTEXT_M:
        return None
    origin = _point(issue)
    _, snap = nearest_points(origin, to_shape(water.geom))
    name = water.name or water.waterway or f"OSM water {water.osm_id}"
    return IssueAsset(
        issue_id=issue.id,
        asset_kind="water",
        asset_id=water.id,
        asset_name=name,
        distance_m=round(metres, 1),
        snap_lon=snap.x,
        snap_lat=snap.y,
        generated_by="spatial",
        notes="Nearby OSM water body. This is not a mapped municipal drain.",
    )


def _containing_ward(db: Session, issue: Issue) -> IssueAsset | None:
    ward = db.scalar(select(Ward).where(func.ST_Contains(Ward.geom, issue.geom)).limit(1))
    if ward is None:
        return None
    return IssueAsset(
        issue_id=issue.id,
        asset_kind="ward",
        asset_id=ward.id,
        asset_name=ward.name,
        distance_m=0.0,
        generated_by="spatial",
        notes="Falls inside a demonstration 3×3 ward grid, not an official Paurashava ward.",
    )


def attach_assets(db: Session, issue: Issue) -> list[IssueAsset]:
    db.execute(
        delete(IssueAsset).where(IssueAsset.issue_id == issue.id, IssueAsset.generated_by == "spatial")
    )
    created = []
    for builder in (_containing_ward, _nearest_road, _nearest_drain, _nearest_water):
        asset = builder(db, issue)
        if asset is not None:
            db.add(asset)
            created.append(asset)
    db.flush()
    return created


def _asset_map(assets: list[IssueAsset], kind: str) -> dict[int, int]:
    return {row.issue_id: row.asset_id for row in assets if row.asset_kind == kind}


def rebuild_relations(db: Session, issues: list[Issue], assets: list[IssueAsset]) -> list[IssueRelation]:
    db.execute(delete(IssueRelation).where(IssueRelation.generated_by == "spatial"))
    roads = _asset_map(assets, "road")
    drains = _asset_map(assets, "drain")
    created: list[IssueRelation] = []
    for i, left in enumerate(issues):
        origin = _point(left)
        for right in issues[i + 1 :]:
            other = _point(right)
            metres = round(haversine_m(origin.x, origin.y, other.x, other.y), 1)
            days = _days_apart(left.created_at, right.created_at)
            if days is not None:
                days = round(days, 1)
            earlier, later = (left, right)
            if _aware(right.created_at) and _aware(left.created_at) and right.created_at < left.created_at:
                earlier, later = right, left
            if metres <= NEARBY_ISSUE_M and _related(left.category, right.category):
                created.append(
                    IssueRelation(
                        from_issue_id=earlier.id,
                        to_issue_id=later.id,
                        relation_type="nearby",
                        distance_m=metres,
                        days_apart=days,
                        generated_by="spatial",
                        notes="Nearby verified issues with the same or related category. Not merged.",
                    )
                )
            if roads.get(left.id) and roads.get(left.id) == roads.get(right.id):
                created.append(
                    IssueRelation(
                        from_issue_id=earlier.id,
                        to_issue_id=later.id,
                        relation_type="same_road",
                        distance_m=metres,
                        days_apart=days,
                        generated_by="spatial",
                        notes="Both issues snapped to the same OSM road segment. Correlation only.",
                    )
                )
            if drains.get(left.id) and drains.get(left.id) == drains.get(right.id):
                created.append(
                    IssueRelation(
                        from_issue_id=earlier.id,
                        to_issue_id=later.id,
                        relation_type="same_drain",
                        distance_m=metres,
                        days_apart=days,
                        generated_by="spatial",
                        notes="Both issues snapped to the same OSM drain feature. Not a cause.",
                    )
                )
            if (
                metres <= RECURRENCE_M
                and _related(left.category, right.category)
                and days is not None
                and days >= RECURRENCE_GAP_DAYS
            ):
                created.append(
                    IssueRelation(
                        from_issue_id=earlier.id,
                        to_issue_id=later.id,
                        relation_type="possible_recurrence",
                        distance_m=metres,
                        days_apart=round(days, 1),
                        generated_by="spatial",
                        notes=(
                            f"Same or related category within {RECURRENCE_M:.0f} m after "
                            f"{days:.0f} days. Possible recurrence, not confirmed failure."
                        ),
                    )
                )
    for row in created:
        db.add(row)
    db.flush()
    return created


def refresh_all(db: Session) -> dict[str, int]:
    issues = db.scalars(select(Issue)).all()
    assets: list[IssueAsset] = []
    for issue in issues:
        assets.extend(attach_assets(db, issue))
    relations = rebuild_relations(db, list(issues), assets)
    return {"issues": len(issues), "assets": len(assets), "relations": len(relations)}


def refresh_issue(db: Session, issue_id: int) -> None:
    refresh_all(db)


def _serialize_asset(row: IssueAsset) -> dict[str, Any]:
    return {
        "kind": row.asset_kind,
        "asset_id": row.asset_id,
        "name": row.asset_name,
        "distance_m": row.distance_m,
        "snap_lon": row.snap_lon,
        "snap_lat": row.snap_lat,
        "notes": row.notes,
    }


def _serialize_relation(row: IssueRelation, issues: dict[int, Issue]) -> dict[str, Any]:
    source = issues.get(row.from_issue_id)
    target = issues.get(row.to_issue_id)
    return {
        "id": row.id,
        "relation_type": row.relation_type,
        "distance_m": row.distance_m,
        "days_apart": row.days_apart,
        "notes": row.notes,
        "from_public_id": source.public_id if source else None,
        "to_public_id": target.public_id if target else None,
        "from_category": source.category if source else None,
        "to_category": target.category if target else None,
    }


def issue_history(db: Session, issue: Issue) -> list[dict[str, Any]]:
    links = db.scalars(
        select(IssueReport).where(IssueReport.issue_id == issue.id).order_by(IssueReport.created_at)
    ).all()
    events: list[dict[str, Any]] = []
    events.append(
        {
            "at": issue.created_at.isoformat() if issue.created_at else None,
            "kind": "issue_opened",
            "summary": f"Verified candidate issue {issue.public_id} ({issue.category}).",
        }
    )
    for link in links:
        report = db.get(Report, link.report_id)
        if report is None:
            continue
        events.append(
            {
                "at": report.created_at.isoformat() if report.created_at else None,
                "kind": "linked_report",
                "summary": f"Citizen report {report.tracking_id} linked as {link.role}.",
                "tracking_id": report.tracking_id,
            }
        )
        verifications = db.scalars(
            select(Verification)
            .where(Verification.report_id == report.id)
            .order_by(Verification.decided_at)
        ).all()
        for row in verifications:
            events.append(
                {
                    "at": row.decided_at.isoformat() if row.decided_at else None,
                    "kind": "verification",
                    "summary": f"{row.decision} by {row.decided_by}.",
                }
            )
    events.sort(key=lambda item: item.get("at") or "")
    return events


def issue_brief(issue: Issue) -> dict[str, Any]:
    point = to_shape(issue.geom)
    return {
        "id": issue.id,
        "public_id": issue.public_id,
        "title": issue.title,
        "category": issue.category,
        "severity": issue.severity,
        "status": issue.status,
        "longitude": point.x,
        "latitude": point.y,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
    }


def snapshot_for(db: Session, issue: Issue) -> dict[str, Any]:
    assets = db.scalars(select(IssueAsset).where(IssueAsset.issue_id == issue.id)).all()
    relations = db.scalars(
        select(IssueRelation).where(
            (IssueRelation.from_issue_id == issue.id) | (IssueRelation.to_issue_id == issue.id)
        )
    ).all()
    issues = {row.id: row for row in db.scalars(select(Issue)).all()}
    drain_count = db.scalar(select(func.count()).select_from(Drain)) or 0
    return {
        "disclaimer": DISCLAIMER,
        "drain_limitation": DRAIN_NOTE,
        "osm_drain_features": drain_count,
        "issue": issue_brief(issue),
        "assets": [_serialize_asset(row) for row in assets],
        "relations": [_serialize_relation(row, issues) for row in relations],
        "history": issue_history(db, issue),
    }


def graph_payload(db: Session) -> dict[str, Any]:
    issues = db.scalars(select(Issue)).all()
    assets = db.scalars(select(IssueAsset)).all()
    relations = db.scalars(select(IssueRelation)).all()
    nodes = []
    for issue in issues:
        point = to_shape(issue.geom)
        nodes.append(
            {
                "id": f"issue:{issue.public_id}",
                "kind": "issue",
                "label": issue.public_id,
                "category": issue.category,
                "longitude": point.x,
                "latitude": point.y,
            }
        )
    seen_assets: set[tuple[str, int]] = set()
    for asset in assets:
        key = (asset.asset_kind, asset.asset_id)
        if key in seen_assets:
            continue
        seen_assets.add(key)
        nodes.append(
            {
                "id": f"{asset.asset_kind}:{asset.asset_id}",
                "kind": asset.asset_kind,
                "label": asset.asset_name,
            }
        )
    issue_index = {row.id: row for row in issues}
    edges = []
    for asset in assets:
        issue = issue_index.get(asset.issue_id)
        if issue is None:
            continue
        edges.append(
            {
                "from": f"issue:{issue.public_id}",
                "to": f"{asset.asset_kind}:{asset.asset_id}",
                "relation_type": f"on_{asset.asset_kind}",
                "distance_m": asset.distance_m,
                "notes": asset.notes,
            }
        )
    for row in relations:
        source = issue_index.get(row.from_issue_id)
        target = issue_index.get(row.to_issue_id)
        if source is None or target is None:
            continue
        edges.append(
            {
                "from": f"issue:{source.public_id}",
                "to": f"issue:{target.public_id}",
                "relation_type": row.relation_type,
                "distance_m": row.distance_m,
                "days_apart": row.days_apart,
                "notes": row.notes,
            }
        )
    return {
        "disclaimer": DISCLAIMER,
        "nodes": nodes,
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges), "issues": len(issues)},
    }


def geojson_payload(db: Session) -> dict[str, Any]:
    issues = db.scalars(select(Issue)).all()
    assets = db.scalars(select(IssueAsset)).all()
    features = []
    for issue in issues:
        point = to_shape(issue.geom)
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(point),
                "properties": {
                    "record_type": "verified_issue",
                    "public_id": issue.public_id,
                    "category": issue.category,
                    "severity": issue.severity,
                    "status": issue.status,
                },
            }
        )
    issue_index = {row.id: row for row in issues}
    for asset in assets:
        issue = issue_index.get(asset.issue_id)
        if issue is None or asset.snap_lon is None or asset.snap_lat is None:
            continue
        origin = to_shape(issue.geom)
        line = LineString([(origin.x, origin.y), (asset.snap_lon, asset.snap_lat)])
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "record_type": "asset_link",
                    "asset_kind": asset.asset_kind,
                    "public_id": issue.public_id,
                    "name": asset.asset_name,
                    "distance_m": asset.distance_m,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
        "disclaimer": DISCLAIMER,
    }
