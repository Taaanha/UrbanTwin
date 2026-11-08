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
    monkeypatch.setattr(s, "hf_detection_model", "someone/road-damage-model")


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


def test_huggingface_boxes_are_normalised(keys, monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        assert "someone/road-damage-model" in url and headers["Authorization"] == "Bearer SECRET-HF"
        return FakeResponse(200, [{"label": "D40", "score": 0.8, "box": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1}}])

    monkeypatch.setattr(requests, "post", fake_post)
    report = submit_report(client, "Pothole for AI second opinion test.")
    body = _post(report["tracking_id"], "huggingface").json()
    assert body["is_problem"] is True and body["confidence"] == 0.8
    assert body["boxes"][0]["w"] == 1.0 and body["status"] == "ai_candidate_unverified"


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
