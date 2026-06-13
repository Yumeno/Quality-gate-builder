"""Tests for the demo API using httpx TestClient (no server startup)."""

from demo_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_greet_returns_message():
    r = client.get("/greet/world")
    assert r.status_code == 200
    assert r.json()["message"] == "Hello, world!"
