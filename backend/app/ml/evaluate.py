import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss, precision_score

from app.ml.features import CLASSES

LABELS = [0, 1, 2]


def classification_metrics(y: np.ndarray, pred: np.ndarray, proba: np.ndarray | None = None) -> dict:
    out = {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", labels=LABELS, zero_division=0)),
        "precision": {
            c: float(v)
            for c, v in zip(CLASSES, precision_score(y, pred, labels=LABELS, average=None, zero_division=0))
        },
        "confusion_matrix": confusion_matrix(
            y, pred, labels=LABELS
        ).tolist(),  # rows = actual, cols = predicted
    }
    if proba is not None:
        out["log_loss"] = float(log_loss(y, np.clip(proba, 1e-6, 1), labels=LABELS))
    return out


def expected_calibration_error(y: np.ndarray, proba: np.ndarray, bins: int = 10) -> dict:
    """Top-label ECE plus a reliability table (confidence bin -> observed accuracy)."""
    conf = proba.max(axis=1)
    hit = (proba.argmax(axis=1) == y).astype(float)
    edges = np.linspace(conf.min(), conf.max() + 1e-9, bins + 1)
    idx = np.clip(np.digitize(conf, edges[1:-1]), 0, bins - 1)
    table, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        table.append(
            {"confidence": float(conf[m].mean()), "accuracy": float(hit[m].mean()), "n": int(m.sum())}
        )
        ece += m.mean() * abs(conf[m].mean() - hit[m].mean())
    return {"ece": float(ece), "reliability": table}


def long_flat_backtest(df: pd.DataFrame, pred: np.ndarray, cost_bps: float = 5.0) -> dict:
    """1-day-horizon sanity check: hold each ticker long when the model says 'up', else flat.

    df needs date, ticker, fwd_ret (return from this close to the next). Costs are charged per position
    change. Equal-weight across tickers, compared with equal-weight buy & hold over the same days.
    Overlap-free only for horizon 1, so callers should not use it for longer horizons.
    """
    d = df[["date", "ticker", "fwd_ret"]].copy()
    d["pos"] = (pred == 2).astype(float)
    d = d.sort_values(["ticker", "date"])
    d["turnover"] = d.groupby("ticker")["pos"].diff().abs().fillna(d["pos"])
    d["strat"] = d["pos"] * d["fwd_ret"] - d["turnover"] * cost_bps / 1e4
    daily = d.groupby("date").agg(strategy=("strat", "mean"), buy_hold=("fwd_ret", "mean"))
    return {
        "strategy": _perf(daily["strategy"]),
        "buy_and_hold": _perf(daily["buy_hold"]),
        "cost_bps_per_trade": cost_bps,
        "avg_fraction_invested": float(d["pos"].mean()),
    }


def _perf(daily: pd.Series) -> dict:
    equity = (1 + daily).cumprod()
    years = max(len(daily) / 252, 1e-9)
    vol = daily.std() * np.sqrt(252)
    return {
        "total_return": float(equity.iloc[-1] - 1),
        "annual_return": float(equity.iloc[-1] ** (1 / years) - 1),
        "annual_vol": float(vol),
        "sharpe": float(daily.mean() * 252 / vol) if vol > 0 else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
    }
