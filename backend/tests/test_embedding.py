from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import image_embedding
from app.services.duplicates import image_points_embedding

client = TestClient(app)


class StubEmbedder:
    """Maps a photo's top-left pixel colour to a fixed vector, so 'same scene' = same colour."""

    model_name = "stub-dino"

    def embed(self, path):
        with Image.open(path) as img:
            r, g, b = img.convert("RGB").getpixel((0, 0))
        return [1.0, 0.0, 0.0] if r > 128 else [0.0, 1.0, 0.0]


@pytest.fixture()
def stub():
    image_embedding.set_embedder_for_tests(StubEmbedder())
    yield
    image_embedding.set_embedder_for_tests(None, active=False)


def _png(color):
    buf = BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, "PNG")
    return buf.getvalue()


def _report(text, color):
    r = client.post(
        "/api/reports",
        data={"category": "pothole", "severity": "high", "description": text, "latitude": "22.8692", "longitude": "91.099"},
        files={"files": ("p.png", BytesIO(_png(color)), "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()["tracking_id"]


def _image_note(tracking_id):
    body = client.get(f"/api/investigator/reports/{tracking_id}").json()
    return body["matches"][0]["breakdown"]["image"], " ".join(body["matches"][0]["reasons"])


def test_similar_photos_score_through_embeddings(stub):
    a = _report("Pothole near the market gate.", (250, 10, 10))
    b = _report("Pothole near the market gate again.", (240, 20, 20))
    points, notes = _image_note(b)
    assert points == 15 and "stub-dino cosine 1.00" in notes
    assert a  # first report exists


def test_different_photos_get_no_image_points(stub):
    _report("Pothole near the market gate.", (250, 10, 10))
    b = _report("Pothole near the market gate again.", (10, 250, 10))
    points, notes = _image_note(b)
    assert points == 0 and "look different" in notes


def test_falls_back_to_average_hash_without_a_model():
    image_embedding.set_embedder_for_tests(None)  # forced: no model available
    try:
        _report("Pothole near the market gate.", (250, 10, 10))
        b = _report("Pothole near the market gate again.", (250, 10, 10))
        _, notes = _image_note(b)
        assert "hash distance" in notes
    finally:
        image_embedding.set_embedder_for_tests(None, active=False)


def test_threshold_bands():
    assert image_points_embedding(0.9, "m")[0] == 15
    assert image_points_embedding(0.75, "m")[0] == 6
    assert image_points_embedding(0.3, "m")[0] == 0
    assert image_points_embedding(None, "m")[0] == 0
