import json

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.helpers import new_issue, submit_report
from tests.test_ai_opinion import FakeResponse, _gemini_ok

client = TestClient(app)


@pytest.fixture()
def gemini(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "SECRET-GEMINI")
    monkeypatch.setattr(s, "hf_api_token", "")
    monkeypatch.setattr(s, "ollama_url", "")
    monkeypatch.setattr("app.services.ai_text.time.sleep", lambda seconds: None)


@pytest.fixture()
def no_provider(monkeypatch):
    s = get_settings()
    for field in ("gemini_api_key", "hf_api_token", "ollama_url"):
        monkeypatch.setattr(s, field, "")


def _reply(monkeypatch, payload, sent=None):
    def fake_post(url, json=None, headers=None, timeout=None):
        if sent is not None:
            sent.update(url=url, body=json, headers=headers)
        return _gemini_ok(__import__("json").dumps(payload) if not isinstance(payload, str) else payload)

    monkeypatch.setattr(requests, "post", fake_post)


def test_ask_uses_ai_only_when_rules_cannot_read_the_question(gemini, monkeypatch):
    submit_report(client, "Drain blocked here", category="blocked_drainage")
    sent: dict = {}
    _reply(monkeypatch, {"intent": "count", "categories": ["blocked_drainage", "made_up"], "severities": ["extreme"], "unresolved": True, "days": 9999}, sent)
    body = client.post("/api/insights/ask", json={"question": "নর্দমা নিয়ে কতগুলো অভিযোগ আছে খোলা?"}).json()
    assert body["understood"] is True and body["parsed_by"]["method"] == "ai" and body["parsed_by"]["provider"] == "gemini"
    assert body["filters"]["categories"] == ["blocked_drainage"] and body["filters"]["severities"] == []  # invented values dropped
    assert body["params"]["days"] == 365  # capped
    assert body["sql"].startswith("SELECT count(*)")  # the SQL is a fixed template, never model text
    assert "SECRET" not in json.dumps(body) and sent["headers"]["x-goog-api-key"] == "SECRET-GEMINI"
    assert any("AI model" in c for c in body["caveats"])


def test_ask_does_not_call_ai_when_rules_understand(gemini, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(requests, "post", boom)
    body = client.post("/api/insights/ask", json={"question": "How many critical reports?"}).json()
    assert body["parsed_by"] == {"method": "rules"} and body["intent"] == "count"


def test_ask_falls_back_to_not_guessing_when_ai_is_unavailable_or_unhelpful(no_provider, gemini, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "")
    body = client.post("/api/insights/ask", json={"question": "Is the mayor corrupt?"}).json()
    assert body["understood"] is False and "unavailable" in body["parsed_by"]["ai_note"]
    monkeypatch.setattr(s, "gemini_api_key", "SECRET-GEMINI")
    _reply(monkeypatch, {"intent": "drop_everything", "categories": []})
    body = client.post("/api/insights/ask", json={"question": "Is the mayor corrupt?"}).json()
    assert body["understood"] is False and body["sql"] is None
    _reply(monkeypatch, "not json at all")
    assert client.post("/api/insights/ask", json={"question": "Is the mayor corrupt?"}).json()["understood"] is False


def test_planner_brief_is_labelled_draft_and_sanitised(gemini, monkeypatch):
    new_issue(client, "Large pothole on the main road", severity="high")
    _reply(monkeypatch, {"summary": "Plans differ.  " + "x" * 2000, "differences": ["a", "b", "c", "d", "e", "f"], "tradeoffs": "not a list", "caveats": ["Placeholder costs."], "extra": "ignored"})
    response = client.post("/api/planner/compare/brief", json={"budget_bdt": 500000})
    assert response.status_code == 200
    brief = response.json()["brief"]
    assert brief["status"] == "ai_draft_unverified" and "must check" in brief["warning"]
    assert len(brief["summary"]) <= 600 and len(brief["differences"]) == 5 and isinstance(brief["tradeoffs"], str)
    assert "extra" not in brief and response.json()["comparison"]["plans"]


def test_issue_brief_and_error_codes(gemini, monkeypatch):
    _, verified = new_issue(client, "Pothole near the market")
    public_id = verified["issue_public_id"]
    sent: dict = {}
    _reply(monkeypatch, {"summary": "Open pothole.", "context": ["Near a road."], "suggested_checks": ["Inspect depth."]}, sent)
    ok = client.get(f"/api/intelligence/issues/{public_id}/brief")
    assert ok.status_code == 200 and ok.json()["brief"]["summary"] == "Open pothole."
    assert "correlations only" in sent["body"]["contents"][0]["parts"][0]["text"]
    assert client.get("/api/intelligence/issues/NOPE/brief").status_code == 404
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(503, {}))
    assert client.get(f"/api/intelligence/issues/{public_id}/brief").status_code == 502
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "")
    unavailable = client.get(f"/api/intelligence/issues/{public_id}/brief")
    assert unavailable.status_code == 503
