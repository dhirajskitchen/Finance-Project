from datetime import date, timedelta
from typing import Protocol

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Price

COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class MarketDataProvider(Protocol):
    def daily_ohlcv(self, ticker: str, start: date, end: date | None = None) -> pd.DataFrame:
        """Return a DataFrame with COLUMNS; prices are split/dividend adjusted."""
        ...


class YFinanceProvider:
    """Used by offline/scheduled jobs only. Yahoo blocks many cloud IPs, so the API never calls this per request."""

    def daily_ohlcv(self, ticker: str, start: date, end: date | None = None) -> pd.DataFrame:
        import yfinance as yf

        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat() if end else None,
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=COLUMNS)
        df = df.reset_index().rename(columns=str.lower)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[COLUMNS].dropna(subset=["close"])


class FinnhubClient:
    """Finnhub free tier: quote + news only (candles are paywalled)."""

    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = api_key or settings.finnhub_api_key
        self.client = client or httpx.Client(timeout=20)

    def _get(self, path: str, **params):
        r = self.client.get(f"{self.BASE}{path}", params={**params, "token": self.api_key})
        r.raise_for_status()
        return r.json()

    def quote(self, ticker: str) -> dict:
        return self._get("/quote", symbol=ticker)

    def company_news(self, ticker: str, start: date, end: date) -> list[dict]:
        return self._get("/company-news", symbol=ticker, **{"from": start.isoformat(), "to": end.isoformat()})


def upsert_prices(db: Session, ticker: str, df: pd.DataFrame) -> int:
    """Idempotent insert-or-update of daily bars. Returns number of rows written."""
    if df.empty:
        return 0
    rows = [
        {
            "ticker": ticker,
            "date": r.date,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": None if pd.isna(r.volume) else float(r.volume),
        }
        for r in df.itertuples()
    ]
    insert = (postgresql if db.bind.dialect.name == "postgresql" else sqlite).insert
    stmt = insert(Price).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={c: getattr(stmt.excluded, c) for c in ("open", "high", "low", "close", "volume")},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def latest_price_date(db: Session, ticker: str) -> date | None:
    return db.scalar(select(Price.date).where(Price.ticker == ticker).order_by(Price.date.desc()).limit(1))


def get_prices(db: Session, ticker: str, start: date | None = None) -> list[Price]:
    q = select(Price).where(Price.ticker == ticker)
    if start:
        q = q.where(Price.date >= start)
    return list(db.scalars(q.order_by(Price.date)))


def refresh_ticker(db: Session, provider: MarketDataProvider, ticker: str, backfill_years: int = 8) -> int:
    """Fetch only what's missing (full backfill if nothing cached); called from jobs, not the request path."""
    last = latest_price_date(db, ticker)
    start = last - timedelta(days=5) if last else date.today() - timedelta(days=365 * backfill_years)
    return upsert_prices(db, ticker, provider.daily_ohlcv(ticker, start))
