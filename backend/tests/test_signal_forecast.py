from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.ml.features import compute_features
from app.models import Signal
from app.services import market_data, signal_service
from app.services.market_data import upsert_prices


def _seed(db, ticker="AAPL", n=700, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, n)))
    end = date(2026, 11, 18)
    dates = [end - timedelta(days=n - 1 - i) for i in range(n)]
    df = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        }
    )
    upsert_prices(db, ticker, df[market_data.COLUMNS])
    return df


def test_signal_endpoint_shape(client, db):
    _seed(db)
    r = client.get("/stocks/aapl/signal")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL" and body["date"] == "2026-11-18"
    assert body["horizon_days"] == settings.signal_horizon
    assert body["action"] == {"down": "sell", "flat": "hold", "up": "buy"}[body["prediction"]]
    assert set(body["probabilities"]) == {"down", "flat", "up"}
    assert sum(body["probabilities"].values()) == pytest.approx(1.0, abs=1e-6)
    assert body["probability"] == pytest.approx(max(body["probabilities"].values()))
    assert "not financial advice" in body["disclaimer"].lower()


def test_signal_404s(client, db):
    assert client.get("/stocks/ZZZZ/signal").status_code == 404  # unsupported
    assert client.get("/stocks/MSFT/signal").status_code == 404  # no prices cached
    _seed(db, "KO", n=100)  # too little history for the 200-day features
    assert client.get("/stocks/KO/signal").status_code == 404


def test_truncated_lookback_gives_same_features_as_full_history(db):
    """Serving only loads the last ~260 rows; features must equal those computed over the whole history."""
    full = _seed(db, n=1500)
    serving = signal_service.recent_price_frame(db, "AAPL")
    assert len(serving) < len(full)
    a = compute_features(full.assign(date=pd.to_datetime(full["date"]))).iloc[-1]
    b = compute_features(serving.assign(date=pd.to_datetime(serving["date"]))).iloc[-1]
    pd.testing.assert_series_equal(a, b, check_names=False, rtol=1e-6)


def test_stored_signal_is_served_and_stale_version_is_recomputed(client, db):
    _seed(db)
    sig = signal_service.compute_signal(db, "AAPL")
    signal_service.store_signal(db, sig)
    signal_service.store_signal(db, sig)  # idempotent upsert
    assert db.query(Signal).count() == 1

    row = db.query(Signal).one()
    row.probability = 0.123  # marker proving the endpoint reads the stored row
    db.commit()
    assert client.get("/stocks/AAPL/signal").json()["probability"] == 0.123

    row.model_version = "old-model"
    db.commit()
    assert client.get("/stocks/AAPL/signal").json()["probability"] != 0.123  # recomputed


def test_signal_job_stores_all_with_history(db):
    from app.jobs import compute_signals

    _seed(db, "AAPL")
    _seed(db, "KO", n=100)
    compute_signals(db, ["AAPL", "KO", "MSFT"])
    assert [s.ticker for s in db.query(Signal).all()] == ["AAPL"]


def test_forecast_endpoint(client, db):
    _seed(db)
    r = client.get("/stocks/AAPL/forecast")
    assert r.status_code == 200
    body = r.json()
    assert len(body["forecast"]) == settings.signal_horizon
    assert all(p["naive"] == body["last_close"] for p in body["forecast"])
    ev = body["evaluation"]
    assert ev["window_days"] == 60 and ev["ets"]["mae"] > 0 and ev["naive"]["mae"] > 0
    assert ev["naive"]["direction_accuracy"] is None
    assert 0 <= ev["ets"]["direction_accuracy"] <= 1
    assert ev["ets_beats_naive"] == (ev["ets"]["mae"] < ev["naive"]["mae"])
    dates = [p["date"] for p in body["forecast"]]
    assert dates == sorted(dates) and dates[0] > body["last_date"]


def test_forecast_needs_history(client, db):
    _seed(db, "KO", n=50)
    assert client.get("/stocks/KO/forecast").status_code == 404
    assert client.get("/stocks/ZZZZ/forecast").status_code == 404


def test_shipped_model_artifacts_are_consistent():
    m = signal_service.load_model(settings.signal_horizon)
    from app.ml.features import CLASSES, FEATURES

    assert m.meta["features"] == FEATURES and m.meta["classes"] == CLASSES
    assert m.booster.num_feature() == len(FEATURES)
