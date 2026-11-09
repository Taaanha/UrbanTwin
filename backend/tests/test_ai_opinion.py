import json

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from tests.helpers import submit_report

client = TestClient(app)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _gemini_ok(text):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


@pytest.fixture()
def keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "SECRET-GEMINI")
    monkeypatch.setattr(s, "hf_api_token", "SECRET-HF")
    monkeypatch.setattr(s, "hf_model", "someone/vision-model")
    monkeypatch.setattr("app.services.ai_opinion.time.sleep", lambda seconds: None)  # no real waiting between retries


@pytest.fixture()
def ollama(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ollama_url", "http://localhost:11434")
    monkeypatch.setattr(s, "ollama_model", "some-vision-model")


def _post(tracking_id, provider="gemini"):
    return client.post(f"/api/investigator/reports/{tracking_id}/ai-opinion", json={"provider": provider})


def test_unconfigured_providers_return_503_and_listing_hides_keys():
    report = submit_report(client, "Pothole for AI second opinion test.")
    assert _post(report["tracking_id"]).status_code == 503
    assert _post(report["tracking_id"], "huggingface").status_code == 503
    listing = client.get("/api/investigator/ai-providers").json()
    assert listing["providers"]["gemini"]["configured"] is False
    assert "SECRET" not in json.dumps(listing)


def test_gemini_answer_is_sanitised_and_marked_unverified(keys, monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update(url=url, headers=headers, body=json)
        injected = {
            "is_road_or_public_infrastructure_problem": True,
            "category": "pothole",
            "severity": "catastrophic",  # not allowed -> dropped
            "confidence": 7,  # clamped to 1
            "boxes": [{"label": "hole", "x": 0.9, "y": 0.9, "w": 0.5, "h": 0.5}, {"bad": 1}],
            "summary": "Deep hole. " + "x" * 1000,
            "status": "verified",  # must be ignored
        }
        return _gemini_ok(__import__("json").dumps(injected))

    monkeypatch.setattr(requests, "post", fake_post)
    report = submit_report(client, "Pothole for AI second opinion test.")
    response = _post(report["tracking_id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ai_candidate_unverified" and "not verified" in body["warning"]
    assert body["category"] == "pothole" and body["severity"] is None and body["confidence"] == 1.0
    assert len(body["summary"]) == 300
    assert len(body["boxes"]) == 1 and body["boxes"][0]["w"] == pytest.approx(0.1)
    assert sent["headers"]["x-goog-api-key"] == "SECRET-GEMINI" and "SECRET" not in sent["url"]
    assert sent["body"]["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/jpeg"
    # report untouched, action audited without the image or key
    tracked = client.get(f"/api/reports/track/{report['tracking_id']}").json()
    assert tracked["status"] == "submitted"
    log = client.get("/api/audit").json()["items"]
    entry = next(row for row in log if row["action"] == "ai.second_opinion")
    assert "SECRET" not in json.dumps(entry) and entry["detail"]["provider"] == "gemini"


def test_huggingface_vision_answer_is_sanitised(keys, monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update(url=url, headers=headers, body=json)
        text = "Here is the result:\n```json\n" + __import__("json").dumps(
            {"is_road_or_public_infrastructure_problem": True, "category": "pothole", "severity": "high", "confidence": 0.8, "summary": "Hole", "status": "verified"}
        ) + "\n```"
        return FakeResponse(200, {"choices": [{"message": {"content": text}}]})

    monkeypatch.setattr(requests, "post", fake_post)
    report = submit_report(client, "Pothole for AI second opinion test.")
    body = _post(report["tracking_id"], "huggingface").json()
    assert body["provider"] == "huggingface" and body["category"] == "pothole" and body["confidence"] == 0.8
    assert body["status"] == "ai_candidate_unverified"
    assert sent["url"].endswith("/chat/completions") and sent["headers"]["Authorization"] == "Bearer SECRET-HF"
    assert sent["body"]["model"] == "someone/vision-model"
    assert sent["body"]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_huggingface_token_rejected_gives_a_clear_hint(keys, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(403, {}))
    report = submit_report(client, "Pothole for AI second opinion test.")
    response = _post(report["tracking_id"], "huggingface")
    assert response.status_code == 502 and "Inference Providers" in response.text and "SECRET" not in response.text


@pytest.mark.parametrize("status,expected", [(429, 502), (500, 502)])
def test_upstream_failures_are_reported_without_leaking_keys(keys, monkeypatch, status, expected):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(status, {}))
    report = submit_report(client, "Pothole for AI second opinion test.")
    response = _post(report["tracking_id"])
    assert response.status_code == expected and "SECRET" not in response.text


def test_network_error_and_garbage_answers(keys, monkeypatch):
    report = submit_report(client, "Pothole for AI second opinion test.")

    def boom(*a, **k):
        raise requests.ConnectionError("secret url")

    monkeypatch.setattr(requests, "post", boom)
    assert _post(report["tracking_id"]).status_code == 502
    monkeypatch.setattr(requests, "post", lambda *a, **k: _gemini_ok("not json"))
    assert _post(report["tracking_id"]).status_code == 502


def test_requires_staff_token_and_a_photo(staff_auth, keys):
    report = submit_report(client, "Pothole for AI second opinion test.")
    url = f"/api/investigator/reports/{report['tracking_id']}/ai-opinion"
    assert client.post(url, json={"provider": "gemini"}).status_code == 401
    assert client.post(url, json={"provider": "nope"}, headers=staff_auth).status_code == 400
    plain = client.post(
        "/api/reports",
        data={"category": "pothole", "severity": "low", "description": "No photo on this one.", "latitude": "22.87", "longitude": "91.1"},
    ).json()
    none = client.post(f"/api/investigator/reports/{plain['tracking_id']}/ai-opinion", json={"provider": "gemini"}, headers=staff_auth)
    assert none.status_code == 409


def _ollama_ok(payload):
    return FakeResponse(200, {"message": {"content": json.dumps(payload)}})


def test_ollama_is_off_by_default_and_local_when_on(ollama, monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update(url=url, body=json)
        return _ollama_ok({"is_road_or_public_infrastructure_problem": True, "category": "garbage", "severity": "low", "confidence": 0.6, "summary": "Rubbish pile."})

    monkeypatch.setattr(requests, "post", fake_post)
    report = submit_report(client, "Garbage pile for the local model test.")
    body = _post(report["tracking_id"], "ollama").json()
    assert body["provider"] == "ollama" and body["local"] is True and body["category"] == "garbage"
    assert sent["url"].endswith("/api/chat") and sent["body"]["messages"][0]["images"]
    entry = next(row for row in client.get("/api/audit").json()["items"] if row["action"] == "ai.second_opinion")
    assert "local model" in entry["note"]


def test_ollama_missing_model_gives_a_pull_hint(ollama, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(404, {}))
    report = submit_report(client, "Garbage pile for the local model test.")
    response = _post(report["tracking_id"], "ollama")
    assert response.status_code == 502 and "ollama pull" in response.text


def test_auto_falls_back_and_says_what_failed(keys, ollama, monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        if "generativelanguage" in url:
            return FakeResponse(503, {})
        return _ollama_ok({"is_road_or_public_infrastructure_problem": True, "category": "pothole", "severity": "medium", "confidence": 0.7, "summary": "Hole."})

    monkeypatch.setattr(requests, "post", fake_post)
    report = submit_report(client, "Pothole for the fallback test here.")
    body = _post(report["tracking_id"], "auto").json()
    assert body["provider"] == "ollama" and body["status"] == "ai_candidate_unverified"
    assert len(body["fallback_from"]) == 1 and body["fallback_from"][0].startswith("gemini")


def test_auto_reports_when_everything_fails_or_nothing_is_configured(keys, monkeypatch):
    report = submit_report(client, "Pothole for the fallback test here.")
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(503, {}))
    failed = _post(report["tracking_id"], "auto")
    assert failed.status_code == 502 and "gemini" in failed.text and "huggingface" in failed.text and "SECRET" not in failed.text
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "")
    monkeypatch.setattr(s, "hf_api_token", "")
    assert _post(report["tracking_id"], "auto").status_code == 503
