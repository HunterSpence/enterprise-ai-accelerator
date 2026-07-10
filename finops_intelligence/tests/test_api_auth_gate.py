"""
Tests for finops_intelligence/api.py — P0-01 shared auth gate mount.

Run with:
  python -m pytest finops_intelligence/tests/test_api_auth_gate.py -q

The shared gate (core/api_key_auth.py) uses HTTPConnection for its dependency
parameter and binds its FastAPI imports at module scope, so it resolves for
both HTTP and WebSocket routes. These tests exercise it end-to-end.
"""
from __future__ import annotations

import os

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from core.api_key_auth import api_key_dependency
import finops_intelligence.api as api_mod


class TestAuthGateMounted:
    def test_app_mounts_api_key_dependency(self):
        """Structural check: the gate is wired as an app-level dependency —
        independent of whether core/api_key_auth.py's Request-resolution bug
        is fixed yet."""
        mounted = [d.dependency for d in api_mod.app.router.dependencies]
        assert api_key_dependency in [
            getattr(fn, "__wrapped__", fn) for fn in mounted
        ] or any(
            fn.__qualname__.startswith("api_key_dependency") for fn in mounted
        ), "api_key_dependency() is not mounted as an app-level dependency"


class TestAuthGateEndToEnd:
    def test_health_open_without_any_key(self, monkeypatch):
        monkeypatch.delenv("EAA_API_KEY", raising=False)
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        with TestClient(api_mod.app) as client:
            r = client.get("/health")
            assert r.status_code == 200

    def test_business_route_503s_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("EAA_API_KEY", raising=False)
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        with TestClient(api_mod.app) as client:
            r = client.get("/ingest/stats")
            assert r.status_code == 503

    def test_business_route_open_in_dev_mode(self, monkeypatch):
        monkeypatch.setenv("EAA_DEV_MODE", "true")
        monkeypatch.delenv("EAA_API_KEY", raising=False)
        with TestClient(api_mod.app) as client:
            r = client.get("/ingest/stats")
            assert r.status_code == 200

    def test_business_route_requires_correct_key(self, monkeypatch):
        monkeypatch.setenv("EAA_API_KEY", "secret123")
        monkeypatch.delenv("EAA_DEV_MODE", raising=False)
        with TestClient(api_mod.app) as client:
            r = client.get("/ingest/stats")
            assert r.status_code == 401
            r = client.get("/ingest/stats", headers={"X-API-Key": "secret123"})
            assert r.status_code == 200
