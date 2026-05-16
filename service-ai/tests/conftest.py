"""
tests/conftest.py
──────────────────
Shared pytest fixtures for the entire service-ai test suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


API_KEY = "super-secret-key"
API_HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(scope="session")
def app():
    from app.main import app as _app
    return _app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(app):
    with TestClient(app, headers=API_HEADERS) as c:
        yield c
