import json

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.helpers import submit_report
from tests.test_ai_opinion import FakeResponse

client = TestClient(app)
URL = "/api/advisor/chat"


def _ask(text="Where should we focus?", **extra):
    return client.post(URL, json={"messages": [{"role": "user", "content": text}], **extra})


def _call(name, args):
    return FakeResponse(200, {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}, "thoughtSignature": "SIG"}]}}]})


def _text(text, grounding=None):
    cand = {"content": {"role": "model", "parts": [{"text": text}]}}
    if grounding:
        cand["groundingMetadata"] = grounding
    return FakeResponse(200, {"candidates": [cand]})


@pytest.fixture()
def gemini(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "SECRET-GEMINI")
    monkeypatch.setattr("app.services.ai_text.time.sleep", lambda seconds: None)


def _script(monkeypatch, replies, sent):
    queue = list(replies)

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.append(json)
        return queue.pop(0)

    monkeypatch.setattr(requests, "post", fake_post)


def test_advisor_runs_tools_and_returns_checkable_draft(gemini, monkeypatch):
    for _ in range(2):
        submit_report(client, "Drain blocked here", category="blocked_drainage")
    sent: list = []
    _script(
        monkeypatch,
        [_call("query_reports", {"intent": "count", "categories": ["blocked_drainage", "bogus"], "days": 9999}), _text("DATA: 2 drain reports. INFERENCE: check drains first.")],
        sent,
    )
    body = _ask().json()
    assert body["status"] == "ai_draft_unverified" and "must check" in body["warning"] and body["provider"] == "gemini"
    assert body["answer"].startswith("DATA: 2 drain reports")
    call = body["tool_calls"][0]
    assert call["tool"] == "query_reports" and call["result"]["filters"]["categories"] == ["blocked_drainage"]
    assert call["result"]["rows"][0]["reports"] >= 2
    # the model's own turn (with its signature) is echoed back, followed by the tool result
    second = sent[1]["contents"]
    assert second[-2]["parts"][0]["thoughtSignature"] == "SIG"
    assert second[-1]["parts"][0]["functionResponse"]["name"] == "query_reports"
    assert "SECRET" not in json.dumps(body)
    assert sent[0]["tools"][0]["functionDeclarations"] and "never decide" in sent[0]["systemInstruction"]["parts"][0]["text"]


def test_tool_errors_go_back_to_the_model_not_to_the_user(gemini, monkeypatch):
    sent: list = []
    _script(
        monkeypatch,
        [_call("issue_context", {"public_id": "ISS-NOPE"}), _call("drop_database", {}), _call("flood_what_if", {"level_m": "high"}), _text("I could not find that issue.")],
        sent,
    )
    body = _ask().json()
    results = [c["result"] for c in body["tool_calls"]]
    assert results[0] == {"error": "No such issue."}
    assert "Unknown tool" in results[1]["error"] and "number" in results[2]["error"]
    assert body["answer"] == "I could not find that issue."


def test_read_only_tools_work_on_real_data(gemini, monkeypatch):
    submit_report(client, "Pothole in the road", category="pothole")
    sent: list = []
    _script(
        monkeypatch,
        [_call("data_quality", {}), _call("list_verified_issues", {}), _call("green_space_access", {}), _call("compare_budget_plans", {"budget_bdt": 100000}), _call("flood_what_if", {"level_m": 3}), _text("ok")],
        sent,
    )
    body = _ask().json()
    by_tool = {c["tool"]: c["result"] for c in body["tool_calls"]}
    assert by_tool["data_quality"]["reports"]["total"] >= 1
    assert "issues" in by_tool["list_verified_issues"] and "per_ward" in by_tool["green_space_access"]
    assert "error" not in by_tool["compare_budget_plans"]
    assert "flooded_buildings" in by_tool["flood_what_if"] or "unavailable" in by_tool["flood_what_if"]


def test_search_notes_and_sources_are_kept_apart_from_city_data(gemini, monkeypatch):
    sent: list = []
    grounding = {"groundingChunks": [{"web": {"uri": "https://example.org/drainage", "title": "Drainage guide"}}, {"web": {"uri": "javascript:alert(1)", "title": "bad"}}]}
    _script(monkeypatch, [_text("General drainage background.", grounding), _text("GENERAL KNOWLEDGE: desilt drains before monsoon.")], sent)
    body = _ask("How do cities handle waterlogging?", search=True).json()
    assert sent[0]["tools"] == [{"google_search": {}}]  # search call carries no database tools
    assert "functionDeclarations" in sent[1]["tools"][0]  # the answering call carries no search
    assert "WEB BACKGROUND NOTES" in sent[1]["contents"][-1]["parts"][1]["text"]
    assert body["web_sources"] == [{"title": "Drainage guide", "url": "https://example.org/drainage"}]
    assert body["web_search"] == {"requested": True, "used": True}


def test_search_failure_does_not_block_the_answer(gemini, monkeypatch):
    sent: list = []
    _script(monkeypatch, [FakeResponse(403, {}), _text("Answer without web.")], sent)
    body = _ask(search=True).json()
    assert body["answer"] == "Answer without web." and body["web_search"] == {"requested": True, "used": False}


def test_step_limit_and_errors(gemini, monkeypatch):
    sent: list = []
    _script(monkeypatch, [_call("data_quality", {}) for _ in range(6)] + [_text("Final after tools were withdrawn.")], sent)
    assert _ask().json()["answer"].startswith("Final after")
    assert "tools" not in sent[-1]  # last round forces a written answer
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(503, {}))
    assert _ask().status_code == 502
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, {"candidates": []}))
    assert _ask().status_code == 502


def test_validation_and_unconfigured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "")
    assert _ask().status_code == 503
    assert client.post(URL, json={"messages": []}).status_code == 422
    assert client.post(URL, json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 422
    assert client.post(URL, json={"messages": [{"role": "system", "content": "x"}]}).status_code == 422


def test_advisor_requires_staff_login_when_enabled(staff_auth):
    body = {"messages": [{"role": "user", "content": "hello"}]}
    assert client.post(URL, json=body).status_code == 401
