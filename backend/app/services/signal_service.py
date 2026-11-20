import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.features import CLASSES, MIN_HISTORY, compute_features
from app.models import Price, Signal

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "ml" / "artifacts"
ACTION = {"down": "sell", "flat": "hold", "up": "buy"}
# Longest lookback plus warm-up for the recursive indicators (EMA/Wilder RSI): their memory decays below ~1e-9
# after ~300 rows, so serving features match those computed over the full history used in training
LOOKBACK_ROWS = MIN_HISTORY + 300


@dataclass(frozen=True)
class LoadedModel:
    booster: lgb.Booster
    meta: dict


@lru_cache(maxsize=4)
def load_model(horizon: int) -> LoadedModel:
    meta = json.loads((ARTIFACT_DIR / f"meta_h{horizon}.json").read_text())
    booster = lgb.Booster(model_file=str(ARTIFACT_DIR / f"model_h{horizon}.txt"))
    return LoadedModel(booster, meta)


def recent_price_frame(db: Session, ticker: str) -> pd.DataFrame:
    rows = db.execute(
        select(Price.date, Price.high, Price.low, Price.close, Price.volume)
        .where(Price.ticker == ticker)
        .order_by(Price.date.desc())
        .limit(LOOKBACK_ROWS)
    ).all()
    df = pd.DataFrame(rows, columns=["date", "high", "low", "close", "volume"])
    return df.sort_values("date").reset_index(drop=True)


def compute_signal(db: Session, ticker: str, horizon: int | None = None) -> dict | None:
    """Score the latest cached bar. Returns None when there isn't enough history for the features."""
    horizon = horizon or settings.signal_horizon
    prices = recent_price_frame(db, ticker)
    if len(prices) < MIN_HISTORY + 1:
        return None
    model = load_model(horizon)
    feats = compute_features(prices)
    last = feats.iloc[[-1]]
    if last["rsi_14"].isna().any():
        return None
    proba = model.booster.predict(last[model.meta["features"]])[0]
    k = int(np.argmax(proba))
    cls = CLASSES[k]
    return {
        "ticker": ticker,
        "date": prices["date"].iloc[-1],
        "horizon_days": horizon,
        "prediction": cls,
        "action": ACTION[cls],
        "probability": float(proba[k]),
        "probabilities": {c: float(p) for c, p in zip(CLASSES, proba)},
        "model_version": model.meta["version"],
    }


def store_signal(db: Session, sig: dict) -> None:
    """Upsert one signal row; SHAP values (Phase 4) are filled in separately, so keep any existing ones."""
    insert = (postgresql if db.bind.dialect.name == "postgresql" else sqlite).insert
    values = {
        "ticker": sig["ticker"],
        "date": sig["date"],
        "prediction": sig["prediction"],
        "probability": sig["probability"],
        "probabilities": sig["probabilities"],
        "model_version": sig["model_version"],
    }
    stmt = insert(Signal).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={k: getattr(stmt.excluded, k) for k in values if k not in ("ticker", "date")},
    )
    db.execute(stmt)
    db.commit()


def latest_signal(db: Session, ticker: str) -> dict | None:
    """Prefer the row the daily job stored; fall back to scoring on the fly if none matches the newest bar."""
    last_bar: date | None = db.scalar(
        select(Price.date).where(Price.ticker == ticker).order_by(Price.date.desc()).limit(1)
    )
    if last_bar is None:
        return None
    row = db.scalar(select(Signal).where(Signal.ticker == ticker, Signal.date == last_bar))
    model_version = load_model(settings.signal_horizon).meta["version"]
    if row is not None and row.probabilities and row.model_version == model_version:
        return {
            "ticker": ticker,
            "date": row.date,
            "horizon_days": settings.signal_horizon,
            "prediction": row.prediction,
            "action": ACTION[row.prediction],
            "probability": row.probability,
            "probabilities": row.probabilities,
            "model_version": row.model_version,
        }
    return compute_signal(db, ticker)
