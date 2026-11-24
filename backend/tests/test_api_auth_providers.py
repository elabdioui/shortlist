# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for authentication, CSRF protection, rate limiting, RBAC, and provider/key APIs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from shortlist.api.app import create_app
from shortlist.config import Settings
from shortlist.db.base import Base
from shortlist.db.session import create_db_engine, get_session_factory


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a TestClient backed by an isolated SQLite database."""
    monkeypatch.setenv("SHORTLIST_FAKE_LLM", "1")
    db_path = tmp_path / "test_auth.db"
    settings = Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{db_path}",
        secret_key="test-secret-key-for-auth-suite-32bytes",
        environment="test",
    )
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = get_session_factory(engine)
    app = create_app(settings_override=settings, session_factory=factory)
    return TestClient(app)


def test_setup_login_csrf_rate_limit_and_rbac(api_client: TestClient) -> None:
    # 1. Initial setup status
    res = api_client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json() == {"needs_setup": True}

    # 2. First admin setup
    res = api_client.post(
        "/api/auth/setup",
        json={"email": "admin@example.com", "password": "StrongPassword123!", "locale": "fr"},
    )
    assert res.status_code == 201
    admin_csrf = res.json()["csrf_token"]
    assert res.json()["user"]["role"] == "admin"

    # Second setup must fail with 409
    res = api_client.post(
        "/api/auth/setup",
        json={"email": "admin2@example.com", "password": "StrongPassword123!", "locale": "fr"},
    )
    assert res.status_code == 409

    # Status is now needs_setup=False
    assert api_client.get("/api/auth/status").json() == {"needs_setup": False}

    # 3. CSRF enforcement on state-changing routes
    res = api_client.post(
        "/api/users",
        json={"email": "recruiter@example.com", "password": "Password123!", "role": "recruiter"},
    )
    assert res.status_code == 403

    # With valid CSRF header, admin creates recruiter and reader
    res = api_client.post(
        "/api/users",
        headers={"X-CSRF-Token": admin_csrf},
        json={"email": "recruiter@example.com", "password": "Password123!", "role": "recruiter"},
    )
    assert res.status_code == 201

    res = api_client.post(
        "/api/users",
        headers={"X-CSRF-Token": admin_csrf},
        json={"email": "reader@example.com", "password": "Password123!", "role": "reader"},
    )
    assert res.status_code == 201

    # Logout
    res = api_client.post("/api/auth/logout", headers={"X-CSRF-Token": admin_csrf})
    assert res.status_code == 204
    assert api_client.get("/api/auth/me").status_code == 401

    # 4. Login rate limiting (5 failed attempts -> 429)
    for _ in range(5):
        bad = api_client.post(
            "/api/auth/login",
            json={"email": "reader@example.com", "password": "wrong-password"},
        )
        assert bad.status_code == 401
    blocked = api_client.post(
        "/api/auth/login",
        json={"email": "reader@example.com", "password": "Password123!"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    # 5. Recruiter login & RBAC check (cannot create users)
    login_res = api_client.post(
        "/api/auth/login",
        json={"email": "recruiter@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    rec_csrf = login_res.json()["csrf_token"]
    assert (
        api_client.post(
            "/api/users",
            headers={"X-CSRF-Token": rec_csrf},
            json={"email": "other@example.com", "password": "Password123!"},
        ).status_code
        == 403
    )


def test_providers_encrypted_keys_masking_and_test_endpoint(api_client: TestClient) -> None:
    setup = api_client.post(
        "/api/auth/setup",
        json={"email": "admin@example.com", "password": "StrongPassword123!"},
    )
    csrf = setup.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    prov = api_client.post(
        "/api/providers",
        headers=headers,
        json={"type": "openai", "active": True},
    )
    assert prov.status_code == 201
    provider_id = prov.json()["id"]

    raw_secret = "sk-test-secret-value-998877"
    key_res = api_client.post(
        "/api/keys",
        headers=headers,
        json={
            "provider_id": provider_id,
            "label": "OpenAI Primary",
            "secret": raw_secret,
            "allowed_models": ["gpt-4o-mini"],
            "priority": 1,
            "tier": "paid",
        },
    )
    assert key_res.status_code == 201
    key_data = key_res.json()
    assert raw_secret not in str(key_data)
    assert key_data["masked_secret"] == "sk-t...8877"

    # Test key in fake LLM mode
    test_res = api_client.post(f"/api/keys/{key_data['id']}/test", headers=headers)
    assert test_res.status_code == 200
    assert test_res.json()["ok"] is True

    # Create model profile
    prof = api_client.post(
        "/api/profiles",
        headers=headers,
        json={
            "name": "economique",
            "strategy": "priority",
            "models": [{"provider": "openai", "model": "gpt-4o-mini"}],
        },
    )
    assert prof.status_code == 201
    assert prof.json()["name"] == "economique"

    # Audit logs should contain setup, provider.create, key.create, key.test, profile.create
    audit = api_client.get("/api/audit-logs")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert {"auth.setup", "provider.create", "key.create", "key.test"}.issubset(actions)
