import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

ALGORITHM = "HS256"
ISSUER = "portfolio-dashboard"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    return settings.jwt_secret


def create_access_token(user_id: int) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iss": ISSUER,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Returns the user id, or None for any invalid/expired/wrong-type token."""
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
        if payload.get("type") != "access":
            return None
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
