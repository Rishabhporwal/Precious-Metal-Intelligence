from fastapi.testclient import TestClient

from app.main import app


def test_health_liveness():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "pmi-quant"


def test_ready_unconfigured_dependencies():
    # No DATABASE_URL / REDIS_URL set for this test run -> unconfigured passes.
    with TestClient(app) as client:
        res = client.get("/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["postgres"]["status"] == "unconfigured"
    assert body["dependencies"]["redis"]["status"] == "unconfigured"
