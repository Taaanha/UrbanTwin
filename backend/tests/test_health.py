from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_connects_to_postgis():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "urbantwin-backend"
    assert body["database"] == "connected"
    assert "postgis" in body
