"""
tests/contract/test_health.py  (T012)
──────────────────────────────────────
Contract tests for the health endpoints.

Validates the API contract (shape, status codes, required fields) without
requiring live external services. Uses FastAPI TestClient (sync) so no
async fixtures are needed at this layer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── /api/v1/health/live ───────────────────────────────────────────────────────

class TestLivenessContract:
    def test_returns_200(self):
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200

    def test_response_has_status_field(self):
        resp = client.get("/api/v1/health/live")
        body = resp.json()
        assert "status" in body

    def test_status_is_ok(self):
        resp = client.get("/api/v1/health/live")
        assert resp.json()["status"] == "ok"

    def test_response_has_service_field(self):
        resp = client.get("/api/v1/health/live")
        assert resp.json()["service"] == "service-ai"

    def test_content_type_is_json(self):
        resp = client.get("/api/v1/health/live")
        assert "application/json" in resp.headers["content-type"]


# ── /api/v1/health/ready ──────────────────────────────────────────────────────

class TestReadinessContract:
    def test_returns_2xx(self):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code in (200, 503)

    def test_response_has_required_fields(self):
        resp = client.get("/api/v1/health/ready")
        body = resp.json()
        for field in ("status", "service", "version", "env", "checks"):
            assert field in body, f"Missing field: {field}"

    def test_checks_has_config_and_memory(self):
        resp = client.get("/api/v1/health/ready")
        checks = resp.json()["checks"]
        assert "config" in checks
        assert "memory" in checks

    def test_memory_is_valid_enum(self):
        resp = client.get("/api/v1/health/ready")
        memory = resp.json()["checks"]["memory"]
        assert memory in ("local", "cloud")

    def test_status_is_valid_enum(self):
        resp = client.get("/api/v1/health/ready")
        assert resp.json()["status"] in ("ok", "degraded")

    def test_service_name_is_correct(self):
        resp = client.get("/api/v1/health/ready")
        assert resp.json()["service"] == "service-ai"

    def test_version_field_is_semver_like(self):
        resp = client.get("/api/v1/health/ready")
        version = resp.json()["version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Expected semver, got: {version}"


# ── /api/v1/health (summary) ──────────────────────────────────────────────────

class TestHealthSummaryContract:
    def test_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_matches_readiness_shape(self):
        """Summary endpoint must return the same schema as /ready."""
        ready = client.get("/api/v1/health/ready").json()
        summary = client.get("/api/v1/health").json()
        assert set(ready.keys()) == set(summary.keys())

    def test_no_mongodb_fields_in_response(self):
        """Constitution check: no MongoDB references must leak into health output."""
        body = str(client.get("/api/v1/health").json())
        for forbidden in ("mongo", "mongodb", "mongoose"):
            assert forbidden not in body.lower(), (
                f"Constitution violation: '{forbidden}' found in health response"
            )
