from datetime import timedelta

import jwt
import pytest

from app.api import auth as auth_api
from app.core import security
from app.core.config import settings
from app.models import RefreshToken, User
from app.services import auth as auth_service

ORIGIN = {"Origin": settings.frontend_origin}


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret-123")


def _login(client, monkeypatch, sub="g-1", email="a@example.com", verified=True):
    async def fake_token(request):
        return {"userinfo": {"sub": sub, "email": email, "email_verified": verified}}

    monkeypatch.setattr(auth_api.oauth.google, "authorize_access_token", fake_token)
    return client.get("/auth/callback", follow_redirects=False)


def test_callback_creates_user_sets_httponly_cookie_and_redirects(client, db, monkeypatch):
    r = _login(client, monkeypatch)
    assert r.status_code == 307 and r.headers["location"].endswith("/auth/done")
    set_cookie = r.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie and "httponly" in set_cookie and "path=/auth" in set_cookie
    assert db.query(User).count() == 1


def test_callback_same_google_account_reuses_user(client, db, monkeypatch):
    _login(client, monkeypatch)
    _login(client, monkeypatch, email="new@example.com")
    users = db.query(User).all()
    assert len(users) == 1 and users[0].email == "new@example.com"


def test_unverified_email_is_rejected(client, db, monkeypatch):
    r = _login(client, monkeypatch, verified=False)
    assert "error=email" in r.headers["location"] and db.query(User).count() == 0


def test_login_redirects_to_google_with_configured_redirect_uri(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cid")

    async def fake_redirect(request, redirect_uri):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(f"https://accounts.google.com/?redirect_uri={redirect_uri}")

    monkeypatch.setattr(auth_api.oauth.google, "authorize_redirect", fake_redirect)
    r = client.get("/auth/login", follow_redirects=False)
    assert r.headers["location"].endswith(f"{settings.api_base_url}/auth/callback")


def test_refresh_issues_access_token_and_rotates_cookie(client, monkeypatch):
    _login(client, monkeypatch)
    old = client.cookies.get("refresh_token")
    r = client.post("/auth/refresh", headers=ORIGIN)
    assert r.status_code == 200
    assert client.cookies.get("refresh_token") != old
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "a@example.com"


def test_reused_refresh_token_revokes_whole_family(client, db, monkeypatch):
    _login(client, monkeypatch)
    stolen = client.cookies.get("refresh_token")
    assert client.post("/auth/refresh", headers=ORIGIN).status_code == 200  # legit rotation
    client.cookies.clear()
    client.cookies.set("refresh_token", stolen, path="/auth")
    assert client.post("/auth/refresh", headers=ORIGIN).status_code == 401  # replay detected
    assert all(t.revoked_at is not None for t in db.query(RefreshToken).all())


def test_refresh_rejects_missing_cookie_and_bad_origin(client, monkeypatch):
    assert client.post("/auth/refresh", headers=ORIGIN).status_code == 401
    _login(client, monkeypatch)
    assert client.post("/auth/refresh").status_code == 403
    assert client.post("/auth/refresh", headers={"Origin": "http://evil.example"}).status_code == 403


def test_expired_refresh_token_is_rejected(client, db, monkeypatch):
    _login(client, monkeypatch)
    row = db.query(RefreshToken).one()
    row.expires_at = security.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/auth/refresh", headers=ORIGIN).status_code == 401


def test_logout_revokes_session(client, monkeypatch):
    _login(client, monkeypatch)
    token = client.cookies.get("refresh_token")
    assert client.post("/auth/logout", headers=ORIGIN).status_code == 204
    client.cookies.set("refresh_token", token, path="/auth")
    assert client.post("/auth/refresh", headers=ORIGIN).status_code == 401


def test_refresh_tokens_are_stored_hashed(client, db, monkeypatch):
    _login(client, monkeypatch)
    assert db.query(RefreshToken).one().token_hash != client.cookies.get("refresh_token")


def test_access_token_validation():
    good = security.create_access_token(7)
    assert security.decode_access_token(good) == 7
    assert security.decode_access_token("garbage") is None
    wrong_key = jwt.encode(
        {"sub": "7", "iss": security.ISSUER, "type": "access", "exp": 9999999999}, "x" * 40
    )
    assert security.decode_access_token(wrong_key) is None
    refresh_like = jwt.encode(
        {"sub": "7", "iss": security.ISSUER, "type": "refresh", "exp": 9999999999},
        settings.jwt_secret,
    )
    assert security.decode_access_token(refresh_like) is None
    expired = jwt.encode(
        {"sub": "7", "iss": security.ISSUER, "type": "access", "exp": 1}, settings.jwt_secret
    )
    assert security.decode_access_token(expired) is None


def test_protected_routes_require_bearer(client):
    for path in ("/auth/me", "/portfolios"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_rotate_unknown_token_returns_none(db):
    assert auth_service.rotate(db, "nope") is None
