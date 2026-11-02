from fastapi.testclient import TestClient

from app.main import app


def test_health_liveness():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "pmi-quant"


def test_ready_unconfigured_dependencies(monkeypatch):
    # The Settings object is lru_cached at import — clear the dependency URLs on
    # it directly so this test is isolated from ambient .env values.
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "database_url", None, raising=False)
    monkeypatch.setattr(main_module.settings, "redis_url", None, raising=False)
    # No DATABASE_URL / REDIS_URL set for this test run -> unconfigured passes.
    with TestClient(app) as client:
        res = client.get("/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["postgres"]["status"] == "unconfigured"
    assert body["dependencies"]["redis"]["status"] == "unconfigured"
