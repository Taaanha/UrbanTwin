import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models.investigator import Issue
from app.models.reports import Report

client = TestClient(app)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_green_space_tag_filter():
    green = importlib.import_module("import_osm_green")
    assert green.green_kind({"leisure": "park"}) == "leisure=park"
    assert green.green_kind({"landuse": "forest"}) == "landuse=forest"
    assert green.green_kind({"natural": "wood"}) == "natural=wood"
    assert green.green_kind({"landuse": "farmland"}) is None  # farmland is not urban green
    assert green.green_kind({"building": "yes"}) is None


def test_demo_seed_labels_everything_and_connects_the_modules():
    seed = importlib.import_module("seed_demo")
    sys.argv = ["seed_demo.py"]
    seed.main()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Report).where(Report.is_demo.is_(False))) == 0
        assert db.scalar(select(func.count()).select_from(Issue).where(Issue.is_demo.is_(False))) == 0
    over = client.get("/api/overview").json()
    assert over["reports"]["demo"] == over["reports"]["total"] > 0
    flagged = [i for i in client.get("/api/accountability/recurrence").json()["items"] if i["review_flag"] != "none"]
    assert flagged, "seed should include a completed repair followed by a related issue"
    assert client.get("/api/geo/drains").json()["features"], "demo drains should exist"
    queue = client.get("/api/investigator/queue").json()["items"]
    assert any(item["top_label"] == "possible_duplicate" for item in queue)
    sources = {s["layer"]: s["is_demo"] for s in client.get("/api/data-sources").json()["items"]}
    assert sources["demo_drains"] is True
    # idempotent: running again without --reset changes nothing
    before = client.get("/api/overview").json()["reports"]["total"]
    seed.main()
    assert client.get("/api/overview").json()["reports"]["total"] == before
