from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import PNG

client = TestClient(app)


def _post(photo=True, **extra):
    data = {
        "location_text": "near the market",
        "category": "pothole",
        "severity": "medium",
        "description": "A deep hole in the road here.",
        "latitude": "22.8692",
        "longitude": "91.099",
        **extra,
    }
    files = {"files": ("photo.png", BytesIO(PNG), "image/png")} if photo else None
    return client.post("/api/reports", data=data, files=files)


def test_place_text_is_saved_cleaned_and_returned():
    response = _post(location_text="  near Shonapur   Zero Point,\n in front of the market ")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["location_text"] == "near Shonapur Zero Point, in front of the market"
    tracked = client.get(f"/api/reports/track/{body['tracking_id']}").json()
    assert tracked["location_text"] == body["location_text"]


def test_place_text_is_required():
    assert _post(location_text="   ").status_code == 400
    assert _post(location_text="").status_code == 400


def test_known_landmark_is_used_when_no_pin_is_dropped():
    body = _post(location_text="near Sonapur zero point", pin_set="false").json()
    assert round(body["latitude"], 5) == 22.82556 and round(body["longitude"], 5) == 91.10139


def test_pin_wins_over_landmark_when_the_pin_was_set():
    body = _post(location_text="Shonapur Zero Point", pin_set="true").json()
    assert round(body["latitude"], 4) == 22.8692


def test_unknown_place_without_pin_keeps_the_sent_coordinates():
    body = _post(location_text="Somewhere unlisted", pin_set="false").json()
    assert round(body["latitude"], 4) == 22.8692


def test_a_photo_is_required():
    response = _post(photo=False)
    assert response.status_code == 400 and "photo" in response.text


def test_overlong_place_text_is_rejected():
    response = _post(location_text="x" * 201)
    assert response.status_code == 400 and "too long" in response.text


def test_place_text_is_not_executed_as_html_by_the_api():
    body = _post(location_text="<script>alert(1)</script> near school").json()
    # stored as plain text; the React screens render text, not HTML
    assert body["location_text"] == "<script>alert(1)</script> near school"
