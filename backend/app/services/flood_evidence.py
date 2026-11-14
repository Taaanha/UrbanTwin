"""Flood evidence register: import a CSV of reports and data-source pointers, and describe it honestly.

The register is a catalogue. It never creates map points or flood polygons: rows without supplied
coordinates stay unplotted, and rows that only point at a dataset are not observations of flooding.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.flood_evidence import FloodEvidence

BUNDLED_CSV = Path(__file__).resolve().parents[3] / "datasets" / "flood_evidence" / "noakhali_flood_evidence_2026-11.csv"
MAX_BYTES = 512_000
COLUMNS = (
    "record_id", "record_type", "event_date", "publication_date", "location", "district", "description",
    "evidence_type", "source_name", "source_url", "latitude", "longitude", "coordinate_status",
    "verification_status", "notes",
)

# record_type -> (group, plain label). Unknown types land in "other" and are still listed.
GROUPS: dict[str, tuple[str, str]] = {
    "waterlogging_report": ("reported_event", "Reported waterlogging"),
    "drainage_problem": ("reported_event", "Reported drainage problem"),
    "weather_warning": ("context", "Weather warning (context only)"),
    "satellite_data_source": ("observed_source", "Satellite data to obtain"),
    "historical_inundation_dataset": ("historical_source", "Historical dataset to obtain"),
    "modelled_inundation_source": ("modelled_source", "Modelled flood map (not observed)"),
    "monitoring_status": ("monitoring", "Monitoring result"),
}
GROUP_TITLES = {
    "reported_event": ("Reported events", "News reports. Reported, not measured: no flood extent or depth."),
    "context": ("Weather context", "A warning does not prove that waterlogging happened."),
    "observed_source": ("Satellite sources (observed, download needed)", "These point at imagery or flood-extent products. The GIS files are not loaded here yet."),
    "historical_source": ("Historical baselines", "Long-term datasets. They do not establish a recent incident."),
    "modelled_source": ("Modelled inundation sources", "Model output, kept separate from observed flooding."),
    "monitoring": ("Monitoring results", "A search finding, not a physical observation. No report is not proof of no flood."),
    "other": ("Other records", "Unrecognised record type."),
}
RULES = [
    "Records without supplied coordinates are not plotted and must not be drawn as precise incident points.",
    "Reported events are not independently measured flood extents.",
    "Source records identify datasets; they are not themselves flood polygons.",
    "Modelled inundation stays separate from observed inundation.",
    "A monitoring result is a search finding. Absence of a report is not evidence that flooding did not occur.",
]


def group_of(record_type: str) -> str:
    return GROUPS.get(record_type, ("other", record_type))[0]


def _date(value: str, field: str, problems: list[str], rid: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        problems.append(f"{rid}: {field} '{value[:20]}' is not a YYYY-MM-DD date; left empty.")
        return None


def _coord(value: str, low: float, high: float, field: str, problems: list[str], rid: str) -> float | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        number = float("nan")
    if not low <= number <= high:
        problems.append(f"{rid}: {field} '{value[:20]}' is not a valid coordinate; left empty.")
        return None
    return number


def parse_csv(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (valid rows, problems). A row with the wrong number of columns is skipped and reported, never guessed at."""
    problems: list[str] = []
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return [], ["The file is empty."]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        return [], [f"Missing columns: {', '.join(missing)}."]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        if len(raw) != len(header):
            problems.append(f"Line {number}: expected {len(header)} columns but found {len(raw)}; row skipped.")
            continue
        r = {h: c.strip() for h, c in zip(header, raw)}
        rid = r["record_id"][:32]
        if not rid or not r["record_type"] or not r["description"]:
            problems.append(f"Line {number}: record_id, record_type and description are required; row skipped.")
            continue
        if rid in seen:
            problems.append(f"{rid}: duplicate record_id in the file; later row skipped.")
            continue
        seen.add(rid)
        lat = _coord(r["latitude"], -90, 90, "latitude", problems, rid)
        lon = _coord(r["longitude"], -180, 180, "longitude", problems, rid)
        if (lat is None) != (lon is None):
            problems.append(f"{rid}: only one of latitude/longitude is usable; both left empty.")
            lat = lon = None
        url = r["source_url"] if r["source_url"].lower().startswith(("http://", "https://")) else ""
        if r["source_url"] and not url:
            problems.append(f"{rid}: source_url is not an http(s) link; left empty.")
        rows.append(
            {
                "record_id": rid,
                "record_type": r["record_type"][:48],
                "event_date": _date(r["event_date"], "event_date", problems, rid),
                "publication_date": _date(r["publication_date"], "publication_date", problems, rid),
                "location": r["location"] or None,
                "district": r["district"][:128] or None,
                "description": r["description"],
                "evidence_type": r["evidence_type"][:64] or None,
                "source_name": r["source_name"][:160] or None,
                "source_url": url or None,
                "latitude": lat,
                "longitude": lon,
                "coordinate_status": r["coordinate_status"][:64] or None,
                "verification_status": r["verification_status"][:64] or None,
                "notes": r["notes"] or None,
            }
        )
    return rows, problems


def import_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    existing = {r.record_id: r for r in db.scalars(select(FloodEvidence)).all()}
    added = updated = 0
    for row in rows:
        hit = existing.get(row["record_id"])
        if hit is None:
            db.add(FloodEvidence(**row))
            added += 1
        else:
            for key, value in row.items():
                setattr(hit, key, value)
            updated += 1
    db.flush()
    return {"added": added, "updated": updated}


def import_text(db: Session, text: str) -> dict[str, Any]:
    rows, problems = parse_csv(text)
    counts = import_rows(db, rows) if rows else {"added": 0, "updated": 0}
    return {**counts, "skipped_or_adjusted": len(problems), "problems": problems[:50]}


def serialize(row: FloodEvidence) -> dict[str, Any]:
    group, label = GROUPS.get(row.record_type, ("other", row.record_type))
    return {
        "record_id": row.record_id,
        "record_type": row.record_type,
        "group": group,
        "label": label,
        "event_date": row.event_date.isoformat() if row.event_date else None,
        "publication_date": row.publication_date.isoformat() if row.publication_date else None,
        "location": row.location,
        "district": row.district,
        "description": row.description,
        "evidence_type": row.evidence_type,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "has_coordinates": row.latitude is not None and row.longitude is not None,
        "coordinate_status": row.coordinate_status,
        "verification_status": row.verification_status,
        "notes": row.notes,
    }


def register(db: Session) -> dict[str, Any]:
    rows = db.scalars(select(FloodEvidence).order_by(FloodEvidence.record_id)).all()
    items = [serialize(r) for r in rows]
    groups = []
    for key, (title, note) in GROUP_TITLES.items():
        members = [i for i in items if i["group"] == key]
        if members:
            groups.append({"group": key, "title": title, "note": note, "items": members})
    with_coords = sum(1 for i in items if i["has_coordinates"])
    return {
        "rules": RULES,
        "total": len(items),
        "with_coordinates": with_coords,
        "plottable_events": sum(1 for i in items if i["has_coordinates"] and i["group"] == "reported_event"),
        "summary_note": (
            "No record carries verified coordinates, so nothing here can be used as a located flood observation yet. "
            "The next step is to download the satellite flood-extent files listed under Satellite sources."
            if with_coords == 0 and items
            else None
        ),
        "groups": groups,
    }
