"""Feature engineering shared by training and serving.

Every feature at row t uses only data up to and including the close of day t. Targets look forward and are
built separately in `make_target`; nothing here may use shift(-k).
"""

import numpy as np
import pandas as pd

FEATURES = [
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "mom_5",
    "mom_10",
    "mom_20",
    "vol_spike",
    "ma_ratio_20",
    "ma_ratio_20_50",
    "ma_ratio_50_200",
    "volatility_20",
    "vol_ratio_5_20",
    "range_pct",
    "ret_lag_1",
    "ret_lag_2",
    "ret_lag_3",
]

CLASSES = ["down", "flat", "up"]  # integer label = index in this list
MIN_HISTORY = 200  # longest lookback (SMA200); rows before this are NaN

PRICE_COLS = ["date", "high", "low", "close", "volume"]


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.where(loss != 0, 100.0)  # no losses in the window: RSI is 100 by definition


def compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    """prices: columns date, high, low, close, volume for ONE ticker. Returns FEATURES indexed by date."""
    df = prices.sort_values("date").set_index("date")
    close, high, low = df["close"], df["high"], df["low"]
    volume = df["volume"].astype(float)
    ret1 = close.pct_change()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_raw = ema12 - ema26
    macd_signal_raw = macd_raw.ewm(span=9, adjust=False).mean()
    sma20, sma50, sma200 = (close.rolling(n).mean() for n in (20, 50, 200))

    vol_avg = volume.rolling(20).mean()
    vol20 = ret1.rolling(20).std()

    out = pd.DataFrame(
        {
            "rsi_14": _rsi(close),
            # MACD is price-scaled; normalise by price so it is comparable across tickers
            "macd": macd_raw / close,
            "macd_signal": macd_signal_raw / close,
            "macd_hist": (macd_raw - macd_signal_raw) / close,
            "mom_5": close / close.shift(5) - 1,
            "mom_10": close / close.shift(10) - 1,
            "mom_20": close / close.shift(20) - 1,
            "vol_spike": volume / vol_avg.replace(0, np.nan),
            "ma_ratio_20": close / sma20 - 1,
            "ma_ratio_20_50": sma20 / sma50 - 1,
            "ma_ratio_50_200": sma50 / sma200 - 1,
            "volatility_20": vol20,
            "vol_ratio_5_20": ret1.rolling(5).std() / vol20.replace(0, np.nan),
            "range_pct": (high - low) / close,
            "ret_lag_1": ret1,
            "ret_lag_2": ret1.shift(1),
            "ret_lag_3": ret1.shift(2),
        },
        index=df.index,
    )
    out = out.replace([np.inf, -np.inf], np.nan)
    out.iloc[: MIN_HISTORY - 1] = np.nan
    return out[FEATURES]


def make_target(
    prices: pd.DataFrame, features: pd.DataFrame, horizon: int, k: float = 0.5
) -> tuple[pd.Series, pd.Series]:
    """Forward `horizon`-day return and its class.

    The flat band is +/- k * volatility_20 * sqrt(horizon), where volatility_20 is known at day t, so the band
    adapts to each stock's own noise without peeking at the future. Rows without a full forward window are NaN.
    """
    close = prices.sort_values("date").set_index("date")["close"]
    fwd = close.shift(-horizon) / close - 1
    band = k * features["volatility_20"] * np.sqrt(horizon)
    label = pd.Series(np.nan, index=fwd.index)
    valid = fwd.notna() & band.notna()
    label[valid & (fwd < -band)] = 0
    label[valid & (fwd.abs() <= band)] = 1
    label[valid & (fwd > band)] = 2
    return fwd, label
