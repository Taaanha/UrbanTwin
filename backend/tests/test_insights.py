from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from tests.helpers import new_issue, submit_report
from tests.test_simulation import _seed_buildings

client = TestClient(app)

WEST = dict(lon="91.0800", lat="22.8850")  # ward 1 of the test grid
EAST = dict(lon="91.1200", lat="22.8500")  # ward 9 area


def _age(tracking_id: str, days: float) -> None:
    with SessionLocal() as db:
        db.execute(
            text("UPDATE reports SET created_at = :t WHERE tracking_id = :id"),
            {"t": datetime.now(timezone.utc) - timedelta(days=days), "id": tracking_id},
        )
        db.commit()


def test_quality_is_honest_about_empty_and_thin_data():
    empty = client.get("/api/insights/quality").json()
    assert empty["reports"]["total"] == 0
    assert any("No reports yet" in w for w in empty["warnings"])

    r1 = submit_report(client, "Drain blocked near the market", category="blocked_drainage", **WEST)
    submit_report(client, "Pothole outside school", **WEST)
    _age(r1["tracking_id"], 20)
    body = client.get("/api/insights/quality").json()
    assert body["reports"]["total"] == 2
    assert body["reports"]["reviewed_by_person"] == 0
    assert body["reports"]["with_photo_evidence"] == 2
    assert body["reports"]["stale_open"] == 1
    assert body["coverage"]["thin_wards"] == 9  # no ward reaches 3 reports
    assert body["freshness"]["oldest_report_age_days"] >= 19.9
    assert any("not been reviewed" in w for w in body["warnings"])
    assert any("Thin report coverage" in w for w in body["warnings"])


def test_quality_counts_reviewed_reports_and_building_height_estimates():
    _seed_buildings()
    new_issue(client, "Large pothole on Station Road")
    body = client.get("/api/insights/quality").json()
    assert body["reports"]["reviewed_by_person"] == 1
    assert body["reports"]["linked_to_verified_issue"] == 1
    assert body["layers"]["buildings"] == 100
    assert body["layers"]["building_height_sources"]["estimate"] == 100
    assert any("estimates by building type" in w for w in body["warnings"])


def test_timelapse_returns_dated_points_inside_the_window_only():
    old = submit_report(client, "Old report", **WEST)
    new = submit_report(client, "New report", **EAST)
    _age(old["tracking_id"], 45)
    body = client.get("/api/insights/timelapse", params={"days": 30}).json()
    ids = [i["tracking_id"] for i in body["items"]]
    assert ids == [new["tracking_id"]]
    assert body["items"][0]["created_at"] and body["count"] == 1 and body["truncated"] is False
    assert "not a verified issue" in body["note"]
    assert client.get("/api/insights/timelapse", params={"days": 500}).status_code == 422


def test_ask_top_ward_shows_its_query_and_filters():
    for _ in range(3):
        submit_report(client, "Drain blocked", category="blocked_drainage", **WEST)
    submit_report(client, "Drain blocked", category="blocked_drainage", **EAST)
    submit_report(client, "Pothole", category="pothole", **EAST)
    body = client.post("/api/insights/ask", json={"question": "Which ward has the most unresolved drain reports?"}).json()
    assert body["understood"] is True and body["intent"] == "top_wards"
    assert body["filters"]["categories"] == ["blocked_drainage"] and body["filters"]["unresolved"] is True
    assert "Ward 1" in body["answer"] and "(3)" in body["answer"]
    assert "FROM wards w JOIN reports r" in body["sql"] and "ST_Contains" in body["sql"]
    assert body["params"]["categories"] == ["blocked_drainage"]
    assert body["rows"][0]["reports"] == 3
    assert any("demonstration grid" in c for c in body["caveats"])


def test_ask_counts_with_severity_and_time_window():
    old = submit_report(client, "old", severity="critical", **WEST)
    submit_report(client, "recent critical", severity="critical", **WEST)
    submit_report(client, "recent low", severity="low", **WEST)
    _age(old["tracking_id"], 10)
    body = client.post("/api/insights/ask", json={"question": "How many critical reports in the last 7 days?"}).json()
    assert body["intent"] == "count" and body["rows"][0]["reports"] == 1
    assert body["params"]["days"] == 7 and body["params"]["severities"] == ["critical"]


def test_ask_refuses_to_guess_and_is_not_injectable():
    body = client.post("/api/insights/ask", json={"question": "Is the mayor corrupt?"}).json()
    assert body["understood"] is False and body["sql"] is None and body["examples"]
    attack = client.post("/api/insights/ask", json={"question": "how many reports'; DROP TABLE reports; --"})
    assert attack.status_code == 200
    assert client.get("/api/insights/quality").status_code == 200  # tables still there


def test_alerts_only_report_high_severity_newer_than_the_marker():
    start = client.get("/api/insights/alerts").json()["latest_id"]
    submit_report(client, "minor", severity="low", **WEST)
    hot = submit_report(client, "dangerous hole", severity="critical", **WEST)
    body = client.get("/api/insights/alerts", params={"since_id": start}).json()
    assert [i["tracking_id"] for i in body["items"]] == [hot["tracking_id"]]
    assert body["items"][0]["severity"] == "critical" and "not yet reviewed" in body["items"][0]["note"]
    again = client.get("/api/insights/alerts", params={"since_id": body["latest_id"]}).json()
    assert again["items"] == []


def test_alert_stream_sends_ready_then_new_alerts():
    start = client.get("/api/insights/alerts").json()["latest_id"]
    hot = submit_report(client, "flooded junction", severity="high", category="waterlogging", **WEST)
    with client.stream("GET", "/api/insights/alerts/stream", params={"since_id": start, "max_polls": 1}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        payload = "".join(response.iter_text())
    assert "event: ready" in payload and "event: alert" in payload and hot["tracking_id"] in payload


def test_insights_require_staff_login_when_enabled(staff_auth):
    assert client.get("/api/insights/quality").status_code == 401
    assert client.get("/api/insights/quality", headers=staff_auth).status_code == 200
    assert client.get("/api/insights/alerts/stream", params={"max_polls": 1}).status_code == 401
