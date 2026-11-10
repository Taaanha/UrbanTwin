from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _post(**extra):
    data = {
        "category": "pothole",
        "severity": "medium",
        "description": "A deep hole in the road here.",
        "latitude": "22.8692",
        "longitude": "91.099",
        **extra,
    }
    return client.post("/api/reports", data=data)


def test_place_text_is_saved_cleaned_and_returned():
    response = _post(location_text="  near Shonapur   Zero Point,\n in front of the market ")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["location_text"] == "near Shonapur Zero Point, in front of the market"
    tracked = client.get(f"/api/reports/track/{body['tracking_id']}").json()
    assert tracked["location_text"] == body["location_text"]


def test_place_text_is_optional_and_blank_becomes_none():
    assert _post().json()["location_text"] is None
    assert _post(location_text="   ").json()["location_text"] is None


def test_overlong_place_text_is_rejected():
    response = _post(location_text="x" * 201)
    assert response.status_code == 400 and "too long" in response.text


def test_place_text_is_not_executed_as_html_by_the_api():
    body = _post(location_text="<script>alert(1)</script> near school").json()
    # stored as plain text; the React screens render text, not HTML
    assert body["location_text"] == "<script>alert(1)</script> near school"
