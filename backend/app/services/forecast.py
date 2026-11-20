"""Baseline price forecast: exponential smoothing shown next to the naive 'tomorrow = today' forecast.

Daily prices are close to a random walk, so the honest expectation is that ETS barely beats (or loses to)
naive. The evaluation block makes that visible to the user instead of hiding it.
"""

import warnings

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.services.market_data import get_prices

FIT_ROWS = 500
EVAL_DAYS = 60
MIN_ROWS = EVAL_DAYS + 60


def _ets(series: pd.Series, **fixed):
    # 'heuristic' initialisation uses only the first observations, so it never looks at later data
    model = ExponentialSmoothing(
        series.to_numpy(), trend="add", damped_trend=True, initialization_method="heuristic"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return model.fit(**fixed)


def one_step_errors(close: pd.Series) -> dict:
    """Rolling one-step-ahead comparison on the last EVAL_DAYS bars.

    The smoothing parameters are estimated once on data before the evaluation window, then frozen and run
    over the full series; the fitted values are then genuine one-step-ahead forecasts that only used past
    observations.
    """
    train, test = close.iloc[:-EVAL_DAYS], close.iloc[-EVAL_DAYS:]
    p = _ets(train).params
    frozen = _ets(
        close,
        smoothing_level=p["smoothing_level"],
        smoothing_trend=p["smoothing_trend"],
        damping_trend=p["damping_trend"],
        optimized=False,
    )
    ets_pred = np.asarray(frozen.fittedvalues)[-EVAL_DAYS:]
    actual = test.to_numpy()
    naive_pred = close.shift(1).iloc[-EVAL_DAYS:].to_numpy()
    prev = naive_pred

    def stats(pred: np.ndarray) -> dict:
        err = pred - actual
        return {
            "mae": float(np.abs(err).mean()),
            "mape": float((np.abs(err) / actual).mean()),
            "direction_accuracy": float((np.sign(pred - prev) == np.sign(actual - prev)).mean()),
        }

    ets, naive = stats(ets_pred), stats(naive_pred)
    naive["direction_accuracy"] = None  # naive predicts "no change", so it has no direction call
    return {
        "window_days": EVAL_DAYS,
        "naive": naive,
        "ets": ets,
        "ets_beats_naive": ets["mae"] < naive["mae"],
        "mae_improvement_pct": float((naive["mae"] - ets["mae"]) / naive["mae"] * 100),
    }


def build_forecast(db: Session, ticker: str, horizon: int = 5) -> dict | None:
    rows = get_prices(db, ticker)[-FIT_ROWS:]
    if len(rows) < MIN_ROWS:
        return None
    close = pd.Series([r.close for r in rows], index=pd.to_datetime([r.date for r in rows]))
    res = _ets(close)
    ets_values = np.asarray(res.forecast(horizon))
    future = pd.bdate_range(close.index[-1] + pd.Timedelta(days=1), periods=horizon)
    last = float(close.iloc[-1])
    return {
        "ticker": ticker,
        "last_close": last,
        "last_date": close.index[-1].date(),
        "forecast": [{"date": d.date(), "ets": float(e), "naive": last} for d, e in zip(future, ets_values)],
        "evaluation": one_step_errors(close),
        "note": "Statistical baseline, not a prediction you should trade on. Compare it with the naive forecast.",
    }
