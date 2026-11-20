from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import TokenOut, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "refresh_token"
COOKIE_PATH = "/auth"

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path=COOKIE_PATH,
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path=COOKIE_PATH)


def _require_frontend_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated POSTs: browsers always send Origin on cross-site POSTs."""
    if request.headers.get("origin") != settings.frontend_origin:
        raise HTTPException(403, "Bad origin")


@router.get("/login")
async def login(request: Request):
    if not settings.google_client_id:
        raise HTTPException(503, "Google login is not configured")
    return await oauth.google.authorize_redirect(request, f"{settings.api_base_url}/auth/callback")


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{settings.frontend_origin}/login?error=oauth")
    info = token.get("userinfo") or {}
    if not info.get("sub") or not info.get("email") or not info.get("email_verified", False):
        return RedirectResponse(f"{settings.frontend_origin}/login?error=email")
    user = auth_service.upsert_user(db, "google", info["sub"], info["email"])
    response = RedirectResponse(f"{settings.frontend_origin}/auth/done")
    _set_cookie(response, auth_service.start_session(db, user.id))
    request.session.clear()
    return response


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    _require_frontend_origin(request)
    presented = request.cookies.get(COOKIE)
    result = auth_service.rotate(db, presented) if presented else None
    if result is None:
        _clear_cookie(response)
        raise HTTPException(401, "Session expired")
    user_id, new_token = result
    _set_cookie(response, new_token)
    return TokenOut(access_token=create_access_token(user_id))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    _require_frontend_origin(request)
    presented = request.cookies.get(COOKIE)
    if presented:
        auth_service.logout(db, presented)
    _clear_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
