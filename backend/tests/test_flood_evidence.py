from fastapi.testclient import TestClient

from app.main import app
from app.services import flood_evidence as svc

client = TestClient(app)
HEADER = ",".join(svc.COLUMNS)


def _row(rid="X1", rtype="waterlogging_report", lat="", lon="", url="https://example.org/a", date="2026-11-07"):
    return f'{rid},{rtype},{date},{date},"Somewhere, Noakhali",Noakhali,"A report.",News report,Src,{url},{lat},{lon},Not supplied,Reported,note'


def test_bundled_register_imports_cleanly_and_is_not_plotted():
    first = client.post("/api/flood-evidence/import")
    assert first.status_code == 200
    body = first.json()
    assert body["added"] == 28 and body["updated"] == 0 and body["skipped_or_adjusted"] == 0
    again = client.post("/api/flood-evidence/import").json()
    assert again["added"] == 0 and again["updated"] == 28  # idempotent by record_id
    reg = client.get("/api/flood-evidence").json()
    assert reg["total"] == 28 and reg["with_coordinates"] == 0 and reg["plottable_events"] == 0
    assert "nothing here can be used as a located flood observation" in reg["summary_note"]
    groups = {g["group"]: g for g in reg["groups"]}
    reported = [i["record_id"] for i in groups["reported_event"]["items"]]
    assert reported[:2] == ["NW001", "NW002"] and "NW011" in reported and "NW027" in reported and len(reported) == 19
    assert groups["survey_map"]["items"][0]["record_id"] == "NW028"
    assert groups["modelled_source"]["items"][0]["record_id"] == "NW007"
    assert groups["monitoring"]["items"][0]["record_id"] == "NW010"
    assert any("Modelled inundation stays separate" in r for r in reg["rules"])


def test_bad_rows_are_reported_not_guessed():
    text = "\n".join(
        [
            HEADER,
            _row("A1"),
            _row("A2", lat="22.87", lon=""),  # half a coordinate pair
            _row("A3", lat="95", lon="91.1"),  # impossible latitude
            _row("A4", url="javascript:alert(1)"),
            _row("A5", date="07/11/2026"),
            "B1,too,few,columns",
            _row("A1"),  # duplicate id
            _row("A6", lat="22.87", lon="91.1"),
        ]
    )
    rows, problems = svc.parse_csv(text)
    by_id = {r["record_id"]: r for r in rows}
    assert sorted(by_id) == ["A1", "A2", "A3", "A4", "A5", "A6"]
    assert by_id["A2"]["latitude"] is None and by_id["A3"]["latitude"] is None
    assert by_id["A4"]["source_url"] is None and by_id["A5"]["event_date"] is None
    assert by_id["A6"]["latitude"] == 22.87
    joined = " ".join(problems)
    assert "expected 15 columns but found 4" in joined and "duplicate record_id" in joined and "javascript" not in joined.replace("http(s)", "")


def test_upload_and_validation_errors():
    ok = client.post("/api/flood-evidence/import", files={"file": ("e.csv", (HEADER + "\n" + _row()).encode(), "text/csv")})
    assert ok.status_code == 200 and ok.json()["added"] == 1
    assert client.post("/api/flood-evidence/import", files={"file": ("e.csv", b"a,b\n1,2", "text/csv")}).status_code == 422
    assert client.post("/api/flood-evidence/import", files={"file": ("e.csv", b"\xff\xfe\x00bad", "text/csv")}).status_code == 422
    assert client.post("/api/flood-evidence/import", files={"file": ("e.csv", b"x" * 600_000, "text/csv")}).status_code == 413


def test_register_requires_staff_login_when_enabled(staff_auth):
    assert client.get("/api/flood-evidence").status_code == 401
    assert client.post("/api/flood-evidence/import").status_code == 401
    assert client.get("/api/flood-evidence", headers=staff_auth).status_code == 200
