from base64 import b64decode
from io import BytesIO

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def submit_report(client, description, *, lon="91.099", lat="22.8692", category="pothole", severity="high", headers=None):
    response = client.post(
        "/api/reports",
        data={
            "category": category,
            "severity": severity,
            "location_text": "near the market", "description": description,
            "latitude": lat,
            "longitude": lon,
            "language": "en",
        },
        files={"files": ("photo.png", BytesIO(PNG), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def new_issue(client, description, *, headers=None, **kwargs):
    report = submit_report(client, description, **kwargs)
    verify = client.post(
        "/api/investigator/verify",
        json={"tracking_id": report["tracking_id"], "decision": "new_candidate_issue"},
        headers=headers or {},
    )
    assert verify.status_code == 200, verify.text
    return report, verify.json()


def png_file(name="evidence.png"):
    return ("files", (name, BytesIO(PNG), "image/png"))
