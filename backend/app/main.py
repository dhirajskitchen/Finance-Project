from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import stocks
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
app.include_router(stocks.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
