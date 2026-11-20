import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import as_utc, hash_token, new_refresh_token, utcnow
from app.models import RefreshToken, User


def upsert_user(db: Session, provider: str, sub: str, email: str) -> User:
    user = db.scalar(select(User).where(User.provider == provider, User.provider_sub == sub))
    if user is None:
        user = User(provider=provider, provider_sub=sub, email=email)
        db.add(user)
    elif user.email != email:
        user.email = email
    db.commit()
    return user


def _issue(db: Session, user_id: int, family_id: str) -> str:
    token = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(token),
            family_id=family_id,
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    return token


def start_session(db: Session, user_id: int) -> str:
    """New login: starts a fresh refresh-token family."""
    return _issue(db, user_id, str(uuid.uuid4()))


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()


def rotate(db: Session, presented: str) -> tuple[int, str] | None:
    """Exchange a refresh token for a new one. Returns (user_id, new_token) or None.

    Presenting an already-used token means it was likely stolen, so the whole family is revoked.
    """
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(presented)))
    if row is None:
        return None
    if row.revoked_at is not None:
        revoke_family(db, row.family_id)
        return None
    if as_utc(row.expires_at) <= utcnow():
        return None
    row.revoked_at = utcnow()
    db.commit()
    return row.user_id, _issue(db, row.user_id, row.family_id)


def logout(db: Session, presented: str) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(presented)))
    if row is not None:
        revoke_family(db, row.family_id)
