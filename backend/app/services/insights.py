"""Data-quality summary, report time-lapse and the rule-based "ask the city" box.

"Ask the city" maps a question onto a small set of fixed, parameterised SQL templates, so the answer
always comes with the exact query that produced it. Rules read the question first; when they cannot
(and use_ai is on) an AI model only fills in the template's intent and filters from a fixed vocabulary.
The model never writes SQL and never sees the data.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.building_height import building_height
from app.models.geo import Building, DataSource, Ward
from app.models.investigator import IssueReport, Verification
from app.models.reports import EvidenceFile, Report
from app.report_constants import CATEGORIES, SEVERITIES

THIN_WARD_REPORTS = 3  # fewer reports than this in a ward = thin coverage
STALE_OPEN_DAYS = 14
RESOLVED = ("resolved_unverified",)
TIMELAPSE_MAX = 5000


def _age_days(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return round((now - moment).total_seconds() / 86400, 2)


def quality(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    total = db.scalar(select(func.count()).select_from(Report)) or 0
    demo = db.scalar(select(func.count()).select_from(Report).where(Report.is_demo.is_(True))) or 0
    reviewed = db.scalar(select(func.count(func.distinct(Verification.report_id)))) or 0
    linked = db.scalar(select(func.count(func.distinct(IssueReport.report_id)))) or 0
    with_evidence = db.scalar(select(func.count(func.distinct(EvidenceFile.report_id)))) or 0

    created = [row[0] for row in db.execute(select(Report.created_at)).all() if row[0] is not None]
    ages = [a for a in (_age_days(c, now) for c in created) if a is not None]
    stale_cutoff = now - timedelta(days=STALE_OPEN_DAYS)
    stale_open = db.scalar(
        select(func.count())
        .select_from(Report)
        .where(Report.status.in_(("submitted", "acknowledged")), Report.created_at < stale_cutoff)
    ) or 0

    ward_rows = db.execute(
        select(Ward.id, Ward.name, Ward.ward_number, func.count(Report.id))
        .select_from(Ward)
        .outerjoin(Report, func.ST_Contains(Ward.geom, Report.geom))
        .group_by(Ward.id, Ward.name, Ward.ward_number)
        .order_by(Ward.ward_number)
    ).all()
    wards = [
        {"ward": name, "number": number, "reports": int(count), "thin": int(count) < THIN_WARD_REPORTS}
        for _id, name, number, count in ward_rows
    ]
    in_wards = sum(w["reports"] for w in wards)

    buildings = db.execute(select(Building.properties)).all()
    sources: dict[str, int] = {}
    for (props,) in buildings:
        _h, source = building_height(props)
        sources[source] = sources.get(source, 0) + 1
    measured = sum(n for k, n in sources.items() if k != "estimate")

    layers = db.scalars(select(DataSource).order_by(DataSource.layer)).all()
    demo_layers = [r.layer for r in layers if r.is_demo]

    def pct(part: int, whole: int) -> float | None:
        return round(100 * part / whole, 1) if whole else None

    warnings: list[str] = []
    if total == 0:
        warnings.append("No reports yet: every dashboard figure is empty, not zero-risk.")
    if total and demo == total:
        warnings.append("All reports are demonstration records.")
    elif demo:
        warnings.append(f"{demo} of {total} reports are demonstration records and are counted with the real ones.")
    if total and reviewed < total:
        warnings.append(f"{total - reviewed} of {total} reports have not been reviewed by a person yet; AI output on them is a candidate only.")
    if total and with_evidence < total:
        warnings.append(f"{total - with_evidence} reports have no photo evidence.")
    if stale_open:
        warnings.append(f"{stale_open} reports have waited more than {STALE_OPEN_DAYS} days without review.")
    thin = [w["ward"] for w in wards if w["thin"]]
    if thin:
        warnings.append(f"Thin report coverage (<{THIN_WARD_REPORTS} reports) in {len(thin)} of {len(wards)} wards: absence of reports is not absence of problems.")
    if buildings and measured < len(buildings):
        warnings.append(f"Heights for {len(buildings) - measured} of {len(buildings)} buildings are estimates by building type.")
    if demo_layers:
        warnings.append("Demonstration layers in use: " + ", ".join(demo_layers) + ".")

    return {
        "generated_at": now.isoformat(),
        "reports": {
            "total": total,
            "demo": demo,
            "reviewed_by_person": reviewed,
            "reviewed_pct": pct(reviewed, total),
            "linked_to_verified_issue": linked,
            "with_photo_evidence": with_evidence,
            "evidence_pct": pct(with_evidence, total),
            "stale_open": stale_open,
            "stale_after_days": STALE_OPEN_DAYS,
        },
        "freshness": {
            "newest_report_age_days": min(ages) if ages else None,
            "oldest_report_age_days": max(ages) if ages else None,
            "median_report_age_days": round(median(ages), 2) if ages else None,
        },
        "coverage": {
            "wards": wards,
            "reports_outside_wards": max(total - in_wards, 0),
            "thin_wards": len(thin),
            "ward_note": "Ward polygons are a demonstration grid unless official boundaries are loaded.",
        },
        "layers": {
            "demo_layers": demo_layers,
            "building_height_sources": sources,
            "buildings": len(buildings),
            "buildings_with_measured_height": measured,
        },
        "warnings": warnings,
    }


def timelapse(db: Session, days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    rows = db.execute(
        select(
            Report.tracking_id,
            Report.category,
            Report.severity,
            Report.status,
            Report.is_demo,
            Report.created_at,
            func.ST_X(Report.geom),
            func.ST_Y(Report.geom),
        )
        .where(Report.created_at >= start)
        .order_by(Report.created_at)
        .limit(TIMELAPSE_MAX + 1)
    ).all()
    truncated = len(rows) > TIMELAPSE_MAX
    items = [
        {
            "tracking_id": t,
            "category": c,
            "severity": s,
            "status": st,
            "is_demo": bool(d),
            "created_at": at.isoformat(),
            "longitude": float(x),
            "latitude": float(y),
        }
        for t, c, s, st, d, at, x, y in rows[:TIMELAPSE_MAX]
    ]
    return {
        "start": start.isoformat(),
        "end": now.isoformat(),
        "days": days,
        "count": len(items),
        "truncated": truncated,
        "note": "Each point is a citizen report at the time it was received, not a verified issue.",
        "items": items,
    }


# ------------------------------------------------------------------ ask the city

CATEGORY_WORDS = {
    "blocked_drainage": ["drain", "drainage", "nala", "নর্দমা", "ড্রেন"],
    "pothole": ["pothole", "গর্ত"],
    "damaged_road": ["damaged road", "broken road", "road damage"],
    "broken_sidewalk": ["sidewalk", "footpath", "pavement", "ফুটপাত"],
    "waterlogging": ["waterlog", "water log", "জলাবদ্ধ"],
    "illegal_waste": ["illegal waste", "illegal dump", "dumping"],
    "garbage": ["garbage", "trash", "rubbish", "litter", "আবর্জনা"],
    "damaged_infrastructure": ["infrastructure", "streetlight", "bridge", "culvert"],
    "vegetation_loss": ["vegetation", "tree", "green cover"],
    "flooding": ["flood"],
}
UNRESOLVED_WORDS = ("unresolved", "open", "pending", "not resolved", "outstanding")

SUPPORTED_QUESTIONS = [
    "Which ward has the most unresolved drain reports?",
    "How many high severity reports in the last 7 days?",
    "What is the most common problem?",
    "Show the oldest unresolved reports.",
    "Show the latest critical reports.",
    "How many verified issues are open?",
]


def _detect_categories(q: str) -> list[str]:
    found: list[str] = []
    for key, words in CATEGORY_WORDS.items():
        if any(w in q for w in words):
            found.append(key)
    # "illegal waste" should not also match plain garbage via the word "waste"
    return [k for k in found if k in CATEGORIES]


def _detect_severities(q: str) -> list[str]:
    if "critical" in q:
        return ["critical"]
    if "high severity" in q or "severe" in q or "serious" in q or "urgent" in q:
        return ["high", "critical"]
    for sev in SEVERITIES:
        if f"{sev} severity" in q:
            return [sev]
    return []


def _detect_days(q: str) -> int | None:
    m = re.search(r"(?:last|past)\s+(\d{1,3})\s+(day|week|month)s?", q)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return min(n * {"day": 1, "week": 7, "month": 30}[unit], 365)
    if "today" in q:
        return 1
    if "this week" in q or "last week" in q:
        return 7
    if "this month" in q or "last month" in q:
        return 30
    return None


def _filters(categories: list[str], severities: list[str], unresolved: bool, days: int | None):
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if categories:
        clauses.append("r.category = ANY(:categories)")
        params["categories"] = categories
    if severities:
        clauses.append("r.severity = ANY(:severities)")
        params["severities"] = severities
    if unresolved:
        clauses.append("r.status <> ALL(:resolved)")
        params["resolved"] = list(RESOLVED)
    if days:
        clauses.append("r.created_at >= now() - make_interval(days => :days)")
        params["days"] = days
    return clauses, params


def _describe(categories, severities, unresolved, days) -> str:
    bits = []
    if unresolved:
        bits.append("unresolved")
    if severities:
        bits.append("/".join(severities) + "-severity")
    if categories:
        bits.append(", ".join(CATEGORIES[c]["en"].lower() for c in categories))
    bits.append("reports")
    out = " ".join(bits)
    if days:
        out += f" in the last {days} day{'s' if days != 1 else ''}"
    return out


def _run(db: Session, sql: str, params: dict[str, Any]):
    result = db.execute(text(sql), params)
    columns = list(result.keys())
    rows = [dict(zip(columns, row)) for row in result.fetchall()]
    for row in rows:
        for k, v in list(row.items()):
            if isinstance(v, datetime):
                row[k] = v.isoformat()
    return columns, rows


INTENTS = ("top_wards", "top_categories", "issues_by_status", "oldest_open", "latest", "count")


def _rule_intent(q: str) -> str | None:
    if "ward" in q and any(w in q for w in ("most", "highest", "top", "worst", "more")):
        return "top_wards"
    if any(w in q for w in ("most common", "common problem", "common category", "what kind", "what type", "which category")):
        return "top_categories"
    if "verified issue" in q or ("issue" in q and "open" in q) or "how many issues" in q:
        return "issues_by_status"
    if "oldest" in q or "longest" in q or "waiting" in q:
        return "oldest_open"
    if any(w in q for w in ("latest", "newest", "recent", "show")):
        return "latest"
    if any(w in q for w in ("how many", "count", "number of", "total")):
        return "count"
    return None


def ai_parse(question: str) -> dict[str, Any]:
    """Ask the model to pick a template and filters. Returns validated fields only, plus provider info; raises on failure."""
    from app.services import ai_text

    prompt = (
        "Turn the officer's question about citizen reports into a query plan. Return JSON with keys: "
        f"intent (one of {list(INTENTS)}, or null if none fits), "
        f"categories (list, each one of {sorted(CATEGORIES)}), severities (list, each one of {list(SEVERITIES)}), "
        "unresolved (true/false), days (integer 1-365 or null). "
        "intent meanings: top_wards = which wards have the most reports; top_categories = most common problem types; "
        "issues_by_status = verified issues by status; oldest_open = oldest waiting reports; latest = most recent reports; "
        "count = how many reports match. The question may be in English or Bangla. Do not invent filters the question does not imply.\n"
        f"QUESTION: {ai_text.clean_text(question, 300)}"
    )
    raw, meta = ai_text.ask_json(prompt)
    days = raw.get("days")
    cats, sevs = raw.get("categories"), raw.get("severities")
    return {
        "intent": raw.get("intent") if raw.get("intent") in INTENTS else None,
        "categories": [c for c in cats if c in CATEGORIES] if isinstance(cats, list) else [],
        "severities": [x for x in sevs if x in SEVERITIES] if isinstance(sevs, list) else [],
        "unresolved": raw.get("unresolved") is True,
        "days": min(days, 365) if isinstance(days, int) and not isinstance(days, bool) and days >= 1 else None,
        "meta": meta,
    }


def ask(db: Session, question: str, use_ai: bool = False, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """plan (used by the advisor's tools) supplies already-validated intent and filters, skipping keyword reading."""
    q = " ".join(question.lower().split())
    categories, severities, days = _detect_categories(q), _detect_severities(q), _detect_days(q)
    unresolved = any(w in q for w in UNRESOLVED_WORDS)
    intent = _rule_intent(q)
    if plan is not None:
        intent, categories, severities, unresolved, days = (
            plan["intent"], plan["categories"], plan["severities"], plan["unresolved"], plan["days"],
        )
    caveats = [
        "Counts include demonstration records when present.",
        "Reports are citizen submissions, not verified issues.",
    ]
    parsed_by: dict[str, Any] = {"method": "rules"}
    if intent is None and use_ai:
        try:
            plan = ai_parse(question)
        except Exception as exc:  # nothing configured, upstream failure or bad output: fall back to "did not guess"
            parsed_by = {"method": "rules", "ai_note": f"AI parsing unavailable: {str(exc)[:200]}"}
        else:
            if plan["intent"]:
                intent, categories, severities, unresolved, days = (
                    plan["intent"], plan["categories"], plan["severities"], plan["unresolved"], plan["days"],
                )
                parsed_by = {"method": "ai", **plan["meta"]}
                caveats.append(
                    "An AI model read the question and chose the filters shown above. The answer itself comes from the fixed query below, so check the filters."
                )
            else:
                parsed_by = {"method": "rules", "ai_note": "The AI model also found no matching question template."}
    base = {
        "question": question,
        "filters": {"categories": categories, "severities": severities, "unresolved": unresolved, "days": days},
        "caveats": caveats,
        "parsed_by": parsed_by,
    }

    where, params = _filters(categories, severities, unresolved, days)
    where_sql = (" AND " + " AND ".join(where)) if where else ""
    subject = _describe(categories, severities, unresolved, days)

    if intent == "top_wards":
        sql = (
            "SELECT w.name AS ward, count(r.id) AS reports\n"
            "FROM wards w JOIN reports r ON ST_Contains(w.geom, r.geom)\n"
            f"WHERE true{where_sql}\n"
            "GROUP BY w.name ORDER BY reports DESC, w.name LIMIT 5"
        )
        columns, rows = _run(db, sql, params)
        caveats.append("Ward polygons are a demonstration grid unless official boundaries are loaded.")
        answer = (
            f"{rows[0]['ward']} has the most {subject} ({rows[0]['reports']})." if rows else f"No {subject} fall inside any ward."
        )
        return {**base, "understood": True, "intent": "top_wards", "answer": answer, "sql": sql, "params": params, "columns": columns, "rows": rows}

    if intent == "top_categories":
        sql = (
            "SELECT r.category AS category, count(*) AS reports\n"
            f"FROM reports r WHERE true{where_sql}\n"
            "GROUP BY r.category ORDER BY reports DESC, r.category LIMIT 5"
        )
        columns, rows = _run(db, sql, params)
        answer = (
            f"The most common category among {subject} is {CATEGORIES.get(rows[0]['category'], {}).get('en', rows[0]['category'])} ({rows[0]['reports']})."
            if rows
            else f"There are no {subject}."
        )
        return {**base, "understood": True, "intent": "top_categories", "answer": answer, "sql": sql, "params": params, "columns": columns, "rows": rows}

    if intent == "issues_by_status":
        sql = "SELECT i.status AS status, count(*) AS issues FROM issues i GROUP BY i.status ORDER BY issues DESC"
        columns, rows = _run(db, sql, {})
        open_n = sum(r["issues"] for r in rows if r["status"] == "open")
        total = sum(r["issues"] for r in rows)
        caveats.append("An issue is a human-verified problem record; its status is set by staff.")
        return {**base, "understood": True, "intent": "issues_by_status", "answer": f"{open_n} of {total} verified issues are open.", "sql": sql, "params": {}, "columns": columns, "rows": rows}

    if intent == "oldest_open":
        clauses = list(where)
        p = dict(params)
        if not unresolved:
            clauses.append("r.status <> ALL(:resolved)")
            p["resolved"] = list(RESOLVED)
        sql = (
            "SELECT r.tracking_id, r.category, r.severity, r.status, r.created_at\n"
            f"FROM reports r WHERE true{(' AND ' + ' AND '.join(clauses)) if clauses else ''}\n"
            "ORDER BY r.created_at ASC LIMIT 5"
        )
        columns, rows = _run(db, sql, p)
        answer = f"The oldest unresolved report is {rows[0]['tracking_id']} (received {rows[0]['created_at'][:10]})." if rows else "No unresolved reports."
        return {**base, "understood": True, "intent": "oldest_open", "answer": answer, "sql": sql, "params": p, "columns": columns, "rows": rows}

    if intent == "latest":
        sql = (
            "SELECT r.tracking_id, r.category, r.severity, r.status, r.created_at\n"
            f"FROM reports r WHERE true{where_sql}\n"
            "ORDER BY r.created_at DESC LIMIT 5"
        )
        columns, rows = _run(db, sql, params)
        answer = f"Showing the {len(rows)} most recent {subject}." if rows else f"There are no {subject}."
        return {**base, "understood": True, "intent": "latest", "answer": answer, "sql": sql, "params": params, "columns": columns, "rows": rows}

    if intent == "count":
        sql = f"SELECT count(*) AS reports FROM reports r WHERE true{where_sql}"
        columns, rows = _run(db, sql, params)
        return {**base, "understood": True, "intent": "count", "answer": f"{rows[0]['reports']} {subject}.", "sql": sql, "params": params, "columns": columns, "rows": rows}

    return {
        **base,
        "understood": False,
        "intent": None,
        "answer": "I can only answer questions that map onto a fixed set of checkable queries. I did not guess.",
        "sql": None,
        "params": {},
        "columns": [],
        "rows": [],
        "examples": SUPPORTED_QUESTIONS,
    }


# ------------------------------------------------------------------ live alerts

ALERT_SEVERITIES = ("high", "critical")


def max_report_id(db: Session) -> int:
    return int(db.scalar(select(func.max(Report.id))) or 0)


def alerts_since(db: Session, since_id: int, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Report.id, Report.tracking_id, Report.category, Report.severity, Report.created_at, Report.is_demo)
        .where(Report.id > since_id, Report.severity.in_(ALERT_SEVERITIES))
        .order_by(Report.id)
        .limit(limit)
    ).all()
    return [
        {
            "id": i,
            "tracking_id": t,
            "category": c,
            "severity": s,
            "created_at": at.isoformat() if at else None,
            "is_demo": bool(d),
            "note": "New citizen report, not yet reviewed.",
        }
        for i, t, c, s, at, d in rows
    ]
