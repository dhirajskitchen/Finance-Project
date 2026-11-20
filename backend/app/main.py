from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, portfolios, stocks
from app.core.config import settings

app = FastAPI(
    title="Portfolio Risk & Signal Dashboard",
    docs_url=None if settings.env == "prod" else "/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
# Short-lived signed cookie that only carries the OAuth state/nonce during login
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.jwt_secret or "dev-only-insecure",
    max_age=600,
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.include_router(stocks.router)
app.include_router(auth.router)
app.include_router(portfolios.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
