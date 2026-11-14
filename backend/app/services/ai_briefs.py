"""AI-written plain-language briefs over results the rule-based services already computed.

The model only re-words the facts passed in. It does not score, rank, cost or link anything, and
the result is always labelled as an AI draft for a person to check.
"""

from __future__ import annotations

from typing import Any

from app.services import ai_text

LABEL = "AI draft - written from the figures below. It adds no new data. A staff member must check it."


def _wrap(raw: dict[str, Any], meta: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "ai_draft_unverified", "warning": LABEL, **meta}
    for name in fields:
        value = raw.get(name)
        out[name] = ai_text.clean_list(value) if isinstance(value, list) else ai_text.clean_text(value)
    return out


def planner_brief(comparison: dict[str, Any]) -> dict[str, Any]:
    """Explain a budget comparison to a non-specialist officer."""
    facts = {
        "budget_bdt": comparison["budget_bdt"],
        "limitations": comparison["limitations"],
        "methods": [
            {
                "method": p["method"],
                "what_it_does": p["notes"],
                "spent_bdt": p["spent_bdt"],
                "remaining_bdt": p["remaining_bdt"],
                "included": p["included_count"],
                "deferred": p["deferred_count"],
                "included_items": [
                    {"id": i["public_id"], "category": i["category"], "severity": i["severity"], "ward": i["ward"], "cost_mid_bdt": i["cost"]["total_mid_bdt"]}
                    for i in p["included"][:15]
                ],
            }
            for p in comparison["plans"]
        ],
    }
    prompt = (
        "Write a short brief comparing these budget plans for a municipal officer. Return JSON with keys: "
        "summary (2-3 sentences), differences (list of up to 4 short points on how the methods differ in what they fund), "
        "tradeoffs (list of up to 3 short points), caveats (list of up to 3 points drawn from the limitations). "
        "Quote only numbers that appear in the facts. Do not pick a winner as if it were certain; costs are lab placeholders.\n"
        f"FACTS: {ai_text.dumps(facts)}"
    )
    raw, meta = ai_text.ask_json(prompt)
    return _wrap(raw, meta, ("summary", "differences", "tradeoffs", "caveats"))


def issue_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Summarise one verified issue and its spatial links without claiming cause."""
    facts = {
        "issue": snapshot["issue"],
        "assets": snapshot["assets"],
        "relations": snapshot["relations"],
        "history": snapshot["history"],
        "osm_drain_features": snapshot["osm_drain_features"],
        "rules": [snapshot["disclaimer"], snapshot["drain_limitation"]],
    }
    prompt = (
        "Summarise this verified municipal issue for a field supervisor. Return JSON with keys: "
        "summary (2-3 sentences: what it is, where, how long it has been open), "
        "context (list of up to 4 short points about nearby roads, drains, water and related issues), "
        "suggested_checks (list of up to 3 things a person could inspect on site). "
        "Spatial links are correlations only: never say drainage or anything else caused the problem, and never say a drain is missing. "
        "Use only the facts given.\n"
        f"FACTS: {ai_text.dumps(facts)}"
    )
    raw, meta = ai_text.ask_json(prompt)
    return _wrap(raw, meta, ("summary", "context", "suggested_checks"))
