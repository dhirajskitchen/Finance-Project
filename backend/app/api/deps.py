from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    user_id = decode_access_token(token) if scheme.lower() == "bearer" and token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user
