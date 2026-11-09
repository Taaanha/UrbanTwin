from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.spa import mount_frontend


def _site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>UrbanTwin app</html>")
    (tmp_path / "logo.svg").write_text("<svg/>")
    api = FastAPI()

    @api.get("/api/ping")
    def ping():
        return {"ok": True}

    assert mount_frontend(api, str(tmp_path)) is True
    return TestClient(api)


def test_spa_serves_pages_assets_and_keeps_api_routes(tmp_path):
    client = _site(tmp_path)
    assert client.get("/api/ping").json() == {"ok": True}
    assert "UrbanTwin app" in client.get("/").text
    assert "UrbanTwin app" in client.get("/simulation").text  # client-side route falls back to index.html
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/logo.svg").text == "<svg/>"


def test_unknown_api_paths_stay_404_and_traversal_is_blocked(tmp_path):
    client = _site(tmp_path)
    assert client.get("/api/nope").status_code == 404
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("TOP SECRET")
    body = client.get("/..%2fsecret.txt").text
    assert "TOP SECRET" not in body


def test_nothing_is_mounted_without_a_build(tmp_path):
    api = FastAPI()
    assert mount_frontend(api, "") is False
    assert mount_frontend(api, str(tmp_path / "missing")) is False


def test_hosted_database_urls_get_the_psycopg_driver():
    for raw in ("postgres://u:p@host/db?sslmode=require", "postgresql://u:p@host/db"):
        assert Settings(database_url=raw).database_url.startswith("postgresql+psycopg://u:p@host/db")
    assert Settings(database_url="postgresql+psycopg://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
