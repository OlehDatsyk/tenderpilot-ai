from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import User
from tests.conftest import PASSWORD, Account, register


def test_health_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert client.get("/api/openapi.json").status_code == 200


def test_register_login_me(client):
    acct = register(client, "Carol@Example.com", "Carol Ltd")
    me = acct.me
    assert me["email"] == "carol@example.com"
    assert me["organization"]["name"] == "Carol Ltd"
    assert me["role"] == "owner"
    r = client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert {"access_token", "refresh_token", "expires_in"} <= r.json().keys()


def test_password_is_hashed_with_argon2(client):
    register(client, "hash@example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "hash@example.com"))
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash


def test_login_rejects_bad_credentials(client):
    register(client, "dave@example.com")
    for body in ({"email": "dave@example.com", "password": "wrong-password-1"}, {"email": "nobody@example.com", "password": PASSWORD}):
        r = client.post("/api/v1/auth/login", json=body)
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password."


def test_weak_password_and_duplicate_email(client):
    r = client.post("/api/v1/auth/register", json={"email": "w@example.com", "password": "short", "full_name": "W"})
    assert r.status_code == 422
    r = client.post("/api/v1/auth/register", json={"email": "w@example.com", "password": "onlyletterslong", "full_name": "W"})
    assert r.status_code == 422
    register(client, "dup@example.com")
    r = client.post("/api/v1/auth/register", json={"email": "DUP@example.com", "password": PASSWORD, "full_name": "X"})
    assert r.status_code == 409


def test_validation_errors_do_not_echo_password(client):
    r = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "MySecretValue123", "full_name": "X"})
    assert r.status_code == 422
    assert "MySecretValue123" not in r.text


def test_protected_endpoints_require_auth(client):
    for method, url in [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/tenders"),
        ("get", "/api/v1/dashboard"),
        ("post", "/api/v1/tenders"),
        ("get", "/api/v1/tasks"),
        ("get", "/api/v1/analytics"),
    ]:
        assert getattr(client, method)(url).status_code == 401, url
    r = client.get("/api/v1/tenders", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    acct = register(client)
    old = acct.tokens["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r.status_code == 200
    new = r.json()["refresh_token"]
    assert new != old
    # Reusing the rotated token is treated as theft: the whole family is revoked.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new}).status_code == 401


def test_logout_revokes_refresh_token(client):
    acct = register(client)
    assert client.post("/api/v1/auth/logout", json={"refresh_token": acct.tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": acct.tokens["refresh_token"]}).status_code == 401


def test_change_password_invalidates_old_tokens(client):
    acct = register(client)
    r = acct.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "An0ther-strong-pass"})
    assert r.status_code == 200
    assert acct.get("/api/v1/auth/me").status_code == 401  # old access token is dead
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": acct.tokens["refresh_token"]}).status_code == 401
    acct.tokens = r.json()
    assert acct.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": acct.email, "password": "An0ther-strong-pass"}).status_code == 200


def test_change_password_requires_current(client):
    acct = register(client)
    r = acct.post("/api/v1/auth/change-password", json={"current_password": "wrong-pass-123", "new_password": "An0ther-strong-pass"})
    assert r.status_code == 400


def test_update_profile(client):
    acct = register(client)
    r = acct.patch("/api/v1/auth/me", json={"full_name": "New Name", "job_title": "Bid Manager"})
    assert r.status_code == 200
    assert r.json()["full_name"] == "New Name" and r.json()["job_title"] == "Bid Manager"


def test_rate_limit_on_login(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 3)
    codes = [client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever-123"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    r = client.options("/api/v1/tenders", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") is None
    r = client.options("/api/v1/tenders", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_invitation_flow_and_roles(client):
    owner = register(client, "owner@example.com", "Team Org")
    r = owner.post("/api/v1/organization/invitations", json={"email": "member@example.com", "role": "member"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert client.get(f"/api/v1/auth/invitations/{token}").json()["organization_name"] == "Team Org"
    # Wrong email cannot use the invitation
    bad = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": PASSWORD, "full_name": "O", "invitation_token": token})
    assert bad.status_code == 400
    member = register(client, "member@example.com", invitation_token=token)
    assert member.me["organization"]["name"] == "Team Org"
    assert member.me["role"] == "member"
    # Invitation cannot be reused
    assert client.get(f"/api/v1/auth/invitations/{token}").status_code == 404
    # Members cannot manage the organisation
    assert member.post("/api/v1/organization/invitations", json={"email": "x@example.com"}).status_code == 403
    assert member.patch("/api/v1/organization", json={"name": "Hijack"}).status_code == 403
    assert member.put("/api/v1/organization/ai-settings", json={"provider": "demo"}).status_code == 403
    members = owner.get("/api/v1/organization/members").json()
    assert {m["email"] for m in members} == {"owner@example.com", "member@example.com"}
    # Shared tenders are visible to both members of the same organisation
    t = owner.post("/api/v1/tenders", json={"title": "Shared"}).json()
    assert member.get(f"/api/v1/tenders/{t['id']}").status_code == 200


def test_removed_member_loses_access(client):
    owner = register(client, "o2@example.com", "Org2")
    token = owner.post("/api/v1/organization/invitations", json={"email": "m2@example.com"}).json()["token"]
    member = register(client, "m2@example.com", invitation_token=token)
    t = owner.post("/api/v1/tenders", json={"title": "Secret"}).json()
    assert member.get(f"/api/v1/tenders/{t['id']}").status_code == 200
    assert owner.delete(f"/api/v1/organization/members/{member.me['id']}").status_code == 204
    assert member.get(f"/api/v1/tenders/{t['id']}").status_code == 401
    relogin = client.post("/api/v1/auth/login", json={"email": "m2@example.com", "password": PASSWORD}).json()
    again = Account(client, "m2@example.com", relogin)
    assert again.get(f"/api/v1/tenders/{t['id']}").status_code == 403


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "registration_enabled", False)
    r = client.post("/api/v1/auth/register", json={"email": "n@example.com", "password": PASSWORD, "full_name": "N"})
    assert r.status_code == 403


def test_rate_limit_uses_proxy_appended_ip(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 2)
    monkeypatch.setattr(get_settings(), "trusted_proxy_headers", True)
    codes = []
    for i in range(4):
        # Attacker rotates a fake left-most IP; the proxy-appended right-most IP stays the same.
        headers = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}
        codes.append(client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever-123"}, headers=headers).status_code)
    assert codes[2] == 429
