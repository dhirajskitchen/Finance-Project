from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./dev.db"
    frontend_origin: str = "http://localhost:5173"

    finnhub_api_key: str = ""
    gemini_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    jwt_secret: str = ""
    internal_job_token: str = ""

    # Public URL of this API; the OAuth redirect URI is built from it so it never depends on the Host header
    api_base_url: str = "http://localhost:8000"
    # Cross-site hosting (Vercel + Render) needs samesite=none and secure=true; same-site setups can use lax
    cookie_samesite: str = "lax"
    cookie_secure: bool = False
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    max_portfolios: int = 10
    max_holdings: int = 50

    # Re-fetch prices if the newest cached row is older than this many days
    price_stale_days: int = 1


settings = Settings()
