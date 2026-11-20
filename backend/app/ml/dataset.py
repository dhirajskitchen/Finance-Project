import pandas as pd
from sqlalchemy import select

from app.core.db import SessionLocal
from app.ml.features import compute_features, make_target
from app.models import Price


def load_prices(tickers: list[str] | None = None) -> pd.DataFrame:
    q = select(Price.ticker, Price.date, Price.high, Price.low, Price.close, Price.volume)
    if tickers:
        q = q.where(Price.ticker.in_(tickers))
    with SessionLocal() as db:
        df = pd.read_sql(q.order_by(Price.ticker, Price.date), db.connection())
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_dataset(prices: pd.DataFrame, horizon: int, k: float = 0.5) -> pd.DataFrame:
    """Pooled feature table for all tickers: one row per (ticker, date) with features, forward return, label.
    Rows whose label can't be computed (the last `horizon` days) are dropped."""
    parts = []
    for ticker, g in prices.groupby("ticker"):
        feats = compute_features(g)
        fwd, label = make_target(g, feats, horizon, k)
        part = feats.assign(ticker=ticker, fwd_ret=fwd, label=label)
        parts.append(part.dropna(subset=["label"] + list(feats.columns[:1])))
    out = pd.concat(parts).reset_index().rename(columns={"index": "date"})
    out["label"] = out["label"].astype(int)
    return out.sort_values(["date", "ticker"]).reset_index(drop=True)
