# Signal model: methodology and results

> Educational tool, not financial advice. Numbers below come from `docs/metrics_h1.json` and `docs/metrics_h5.json`, written by `python -m app.ml.train --horizon N`.

## Summary

Daily and weekly stock direction is close to unpredictable from price and volume history. The model beats trivial baselines by a **small** margin, mostly in log-loss and macro-F1, and it is too weak to trade on by itself. The product presents it as decision support with its probabilities and a "low conviction" flag, not as a prediction.

## Data and target

- 30 large-cap US stocks, daily split/dividend-adjusted OHLCV from yfinance, 2019-09 to 2026-11, 54k labelled rows pooled into one model.
- Target: forward N-day return in three classes. "Flat" is within ±0.5 × (20-day volatility) × √N, so the band adapts to each stock's own noise and uses only information known at day t.
- Class balance (N=5): down 26%, flat 40%, up 34%.
- Shipped horizon: **5 days** (`SIGNAL_HORIZON`). The 1-day model is trained and evaluated but not served.

## Features (17, all computed from data up to the close of day t)

RSI(14), MACD line/signal/histogram (price-normalised), momentum 5/10/20d, volume spike vs 20d average, price/SMA20, SMA20/SMA50, SMA50/SMA200, 20d volatility, 5d/20d volatility ratio, daily range, three return lags. Sentiment is deliberately not a feature yet: free news history is too short to train on (see PLAN.md, D2).

One function (`app/ml/features.py`) builds features for both training and serving. Tests check that changing future prices never changes earlier features, and that serving on a truncated 500-row history reproduces full-history features.

## Validation protocol

1. The last 252 trading days are a **holdout** that is never used to choose anything.
2. Hyper-parameters (8 configs) are selected by expanding-window **walk-forward CV** on earlier data only: 7 folds, 3-year minimum training window, 6-month test windows, and an embargo of max(N, 5) trading days between train and test so label windows cannot overlap.
3. The chosen config is compared with baselines in CV and once on the holdout.
4. The shipped model is refit on all data.

Baselines: majority class (train priors), persistence (classify the trailing N-day return with the same band), and logistic regression on the same features.

## Results

### 5-day horizon (shipped)

| Model | CV accuracy | CV macro-F1 | CV log-loss | Holdout accuracy | Holdout macro-F1 | Holdout log-loss |
|---|---|---|---|---|---|---|
| LightGBM | 0.414 | 0.313 | 1.0723 | 0.408 | 0.298 | 1.0808 |
| Logistic regression | 0.410 | 0.303 | 1.0739 | 0.406 | 0.299 | 1.0790 |
| Majority class | 0.395 | 0.189 | 1.0846 | 0.389 | 0.187 | 1.0911 |
| Persistence | 0.347 | 0.339 | n/a | 0.341 | 0.334 | n/a |

### 1-day horizon (not served)

| Model | CV accuracy | CV log-loss | Holdout accuracy | Holdout log-loss |
|---|---|---|---|---|
| LightGBM | 0.440 | 1.0580 | 0.425 | 1.0726 |
| Logistic regression | 0.436 | 1.0606 | 0.426 | 1.0732 |
| Majority class | 0.438 | 1.0737 | 0.424 | 1.0811 |

### Reading these honestly

- **The edge is small.** At 5 days LightGBM is ~2 points above the majority class in accuracy and ~0.01 lower in log-loss, consistently across CV and holdout. At 1 day its accuracy is indistinguishable from always guessing "flat".
- **Gradient boosting adds almost nothing over logistic regression.** Whatever signal exists is mostly linear and weak.
- **Statistical caveat.** 5-day labels overlap, so rows are strongly autocorrelated; the effective sample size is much smaller than the 7,559 holdout rows, and a 2-point gap is plausibly within noise.
- **Persistence has the highest macro-F1** only because it makes many down and up calls, not because it is accurate (accuracy 0.34). It is reported to show the "same as before" rule does not work here.
- **The model rarely says "down".** In the 5-day holdout it predicted down 15 times out of 7,559 (precision 13%); it mostly separates "up" (precision 38% vs a ~33% base rate) from "flat". Do not read "hold" as "avoid selling".
- **Calibration is good.** Holdout top-label ECE is 0.014 (5-day) and 0.017 (1-day), so the displayed probabilities are roughly honest, and they are low (typically 35-50%).
- **1-day backtest sanity check** (long when "up", flat otherwise, 5 bps cost per trade, equal-weighted, holdout year): the strategy was invested only 8% of the time, returned +0.5% vs +11.1% for buy-and-hold, with Sharpe 0.24 vs 0.97. The holdout year was a rising market, so a mostly-in-cash strategy lags; the point is that the model does not generate tradable alpha.

## Forecast baseline

`GET /stocks/{ticker}/forecast` shows a damped-trend exponential smoothing forecast next to the naive "tomorrow = today" forecast and the one-step-ahead error of each over the last 60 days (smoothing parameters are frozen from before that window, so the comparison uses no future information). On NVDA the smoothing model was 0.6% *worse* than naive, which is the expected outcome for a near random-walk series, and the UI says so.

## Limitations

- **Survivorship bias:** the universe is today's large caps, which did well enough to be large caps.
- **Single regime sample:** ~7 years including a strong bull run; no guarantee about other regimes.
- **Costs and liquidity** are only crudely modelled (flat 5 bps) and only in the 1-day backtest.
- **Adjusted prices** change slightly when dividends are paid, so the cached history is refreshed over the most recent days on each update.
- **Pooled model** assumes the same relationships hold across sectors.

## Reproduce

```bash
cd backend
python -m app.ml.train --horizon 5     # writes app/ml/artifacts/ and docs/metrics_h5.json
python -m app.jobs signals             # stores today's signal for every ticker
```
