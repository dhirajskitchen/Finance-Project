"""Train and evaluate the signal classifier.

    python -m app.ml.train --horizon 1

Protocol (everything time-ordered, nothing shuffled):
  1. The last HOLDOUT_DAYS trading days are never used for model selection.
  2. Hyper-parameters are chosen by walk-forward CV on the earlier data only.
  3. The chosen config is compared with baselines in CV and, once, on the holdout.
  4. The shipped model is then refit on all labelled data.
"""

import argparse
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.dataset import build_dataset, load_prices
from app.ml.evaluate import classification_metrics, expected_calibration_error, long_flat_backtest
from app.ml.features import CLASSES, FEATURES
from app.ml.validation import walk_forward_splits

ARTIFACT_DIR = Path(__file__).parent / "artifacts"
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"
HOLDOUT_DAYS = 252
SEED = 42

BASE_PARAMS = dict(
    objective="multiclass",
    num_class=3,
    learning_rate=0.03,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    reg_lambda=10.0,
    random_state=SEED,
    deterministic=True,
    force_row_wise=True,
    n_jobs=4,
    verbose=-1,
)
GRID = {
    "num_leaves": [7, 15],
    "min_child_samples": [200, 800],
    "n_estimators": [100, 300],
}


def fit_lgbm(X: pd.DataFrame, y: np.ndarray, cfg: dict) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**BASE_PARAMS, **cfg).fit(X, y)


def fit_logreg(X: pd.DataFrame, y: np.ndarray):
    return make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=500, C=0.1)
    ).fit(X, y)


def persistence_pred(df: pd.DataFrame, horizon: int, k: float) -> np.ndarray:
    """'Same as before': classify the *trailing* horizon-day return with the same flat band."""
    trailing = df["ret_lag_1"] if horizon == 1 else df["mom_5"] if horizon == 5 else df[f"mom_{horizon}"]
    band = k * df["volatility_20"] * np.sqrt(horizon)
    return np.where(trailing > band, 2, np.where(trailing < -band, 0, 1))


def prior_proba(y_train: np.ndarray, n: int) -> np.ndarray:
    p = np.bincount(y_train, minlength=3) / len(y_train)
    return np.tile(p, (n, 1))


def evaluate_models(train: pd.DataFrame, test: pd.DataFrame, cfg: dict, horizon: int, k: float):
    """Fit every model on `train`, score on `test`. Returns (metrics per model, predictions)."""
    X_tr, y_tr = train[FEATURES], train["label"].to_numpy()
    X_te, y_te = test[FEATURES], test["label"].to_numpy()

    gbm_p = fit_lgbm(X_tr, y_tr, cfg).predict_proba(X_te)
    lr_p = fit_logreg(X_tr, y_tr).predict_proba(X_te)
    maj_p = prior_proba(y_tr, len(test))
    pers = persistence_pred(test, horizon, k)

    metrics = {
        "lightgbm": classification_metrics(y_te, gbm_p.argmax(1), gbm_p),
        "logistic_regression": classification_metrics(y_te, lr_p.argmax(1), lr_p),
        "majority_class": classification_metrics(y_te, maj_p.argmax(1), maj_p),
        "persistence": classification_metrics(y_te, pers),
    }
    return metrics, {"lightgbm": gbm_p, "logreg": lr_p}


def pool(fold_metrics: list[dict]) -> dict:
    """Average per-fold metrics (weighted by fold size) for a compact summary."""
    out = {}
    for model in fold_metrics[0]:
        n = np.array([f[model]["n"] for f in fold_metrics], dtype=float)
        row = {}
        for key in ("accuracy", "macro_f1", "log_loss"):
            if key in fold_metrics[0][model]:
                row[key] = float(np.average([f[model][key] for f in fold_metrics], weights=n))
        out[model] = row
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--k", type=float, default=0.5, help="flat band = k * vol20 * sqrt(horizon)")
    ap.add_argument("--no-save", action="store_true", help="evaluate only; do not write artifacts")
    args = ap.parse_args()
    horizon, k = args.horizon, args.k
    embargo = max(horizon, 5)

    prices = load_prices()
    df = build_dataset(prices, horizon, k)
    days = np.sort(df["date"].unique())
    holdout_start = days[-HOLDOUT_DAYS]
    print(f"{len(df):,} rows, {df['ticker'].nunique()} tickers, {str(days[0])[:10]} -> {str(days[-1])[:10]}")
    print("class balance:", dict(zip(CLASSES, np.round(np.bincount(df["label"]) / len(df), 3))))

    # --- model selection: walk-forward CV on pre-holdout data only
    tune = df[df["date"] < holdout_start].reset_index(drop=True)
    n_tune_days = tune["date"].nunique()
    folds = list(walk_forward_splits(tune["date"], embargo=embargo, end=n_tune_days))
    print(f"walk-forward folds: {len(folds)}")

    best_cfg, best_ll, grid_log = None, np.inf, []
    for values in itertools.product(*GRID.values()):
        cfg = dict(zip(GRID, values))
        lls = []
        for tr, te in folds:
            p = fit_lgbm(tune.loc[tr, FEATURES], tune.loc[tr, "label"].to_numpy(), cfg).predict_proba(
                tune.loc[te, FEATURES]
            )
            y = tune.loc[te, "label"].to_numpy()
            lls.append(classification_metrics(y, p.argmax(1), p)["log_loss"])
        mean_ll = float(np.mean(lls))
        grid_log.append({**cfg, "cv_log_loss": mean_ll})
        print(f"  {cfg} cv log-loss {mean_ll:.4f}")
        if mean_ll < best_ll:
            best_cfg, best_ll = cfg, mean_ll
    print("best config:", best_cfg)

    # --- CV comparison with baselines using the chosen config
    fold_metrics, oof_y, oof_p = [], [], []
    for tr, te in folds:
        m, preds = evaluate_models(tune.loc[tr], tune.loc[te], best_cfg, horizon, k)
        fold_metrics.append(m)
        oof_y.append(tune.loc[te, "label"].to_numpy())
        oof_p.append(preds["lightgbm"])
    cv_summary = pool(fold_metrics)

    # --- one-shot holdout: train on everything before the (embargoed) holdout
    hold_idx = np.flatnonzero(df["date"] >= holdout_start)
    gap_day = days[np.searchsorted(days, holdout_start) - embargo]
    train_idx = np.flatnonzero(df["date"] < gap_day)
    hold_metrics, hold_preds = evaluate_models(df.loc[train_idx], df.loc[hold_idx], best_cfg, horizon, k)
    y_hold = df.loc[hold_idx, "label"].to_numpy()
    calibration = expected_calibration_error(y_hold, hold_preds["lightgbm"])

    report = {
        "horizon_days": horizon,
        "flat_band_k": k,
        "data": {
            "rows": len(df),
            "tickers": int(df["ticker"].nunique()),
            "start": str(days[0])[:10],
            "end": str(days[-1])[:10],
            "holdout_start": str(holdout_start)[:10],
            "class_balance": dict(zip(CLASSES, np.round(np.bincount(df["label"]) / len(df), 4).tolist())),
        },
        "grid": grid_log,
        "best_params": best_cfg,
        "cv": {"folds": len(folds), "mean_metrics": cv_summary},
        "holdout": hold_metrics,
        "calibration_holdout": calibration,
    }
    if horizon == 1:
        report["backtest_holdout"] = long_flat_backtest(
            df.loc[hold_idx].reset_index(drop=True), hold_preds["lightgbm"].argmax(1)
        )

    print("\nCV (mean over folds):")
    for name, row in cv_summary.items():
        print(f"  {name:20s}", {k_: round(v, 4) for k_, v in row.items()})
    print("Holdout:")
    for name, row in hold_metrics.items():
        print(
            f"  {name:20s} acc={row['accuracy']:.4f} f1={row['macro_f1']:.4f}"
            + (f" logloss={row['log_loss']:.4f}" if "log_loss" in row else "")
        )
    print(f"Calibration ECE (holdout): {calibration['ece']:.4f}")
    if "backtest_holdout" in report:
        bt = report["backtest_holdout"]
        print("Backtest holdout: strategy", {k_: round(v, 3) for k_, v in bt["strategy"].items()})
        print("                  buy&hold", {k_: round(v, 3) for k_, v in bt["buy_and_hold"].items()})

    if args.no_save:
        return

    # --- ship: refit on all labelled data
    final = fit_lgbm(df[FEATURES], df["label"].to_numpy(), best_cfg)
    ARTIFACT_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    final.booster_.save_model(str(ARTIFACT_DIR / f"model_h{horizon}.txt"))
    meta = {
        "version": f"lgbm-h{horizon}-{datetime.now(timezone.utc):%Y%m%d}",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizon_days": horizon,
        "flat_band_k": k,
        "features": FEATURES,
        "classes": CLASSES,
        "params": {**BASE_PARAMS, **best_cfg},
        "data_end": report["data"]["end"],
        "holdout_accuracy": hold_metrics["lightgbm"]["accuracy"],
    }
    (ARTIFACT_DIR / f"meta_h{horizon}.json").write_text(json.dumps(meta, indent=2))
    (DOCS_DIR / f"metrics_h{horizon}.json").write_text(json.dumps(report, indent=2))
    print(f"saved model + metadata to {ARTIFACT_DIR} and report to {DOCS_DIR}")


if __name__ == "__main__":
    main()
