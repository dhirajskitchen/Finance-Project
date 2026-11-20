import numpy as np
import pandas as pd

from app.ml.dataset import build_dataset
from app.ml.features import FEATURES, MIN_HISTORY, compute_features, make_target
from app.ml.validation import walk_forward_splits


def _prices(n=400, seed=0, ticker=None):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    df = pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-01", periods=n),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000, 5_000, n).astype(float),
        }
    )
    if ticker:
        df["ticker"] = ticker
    return df


def test_features_have_expected_columns_and_warmup():
    f = compute_features(_prices())
    assert list(f.columns) == FEATURES
    assert f.iloc[: MIN_HISTORY - 1].isna().all().all()
    assert f.iloc[MIN_HISTORY + 5].notna().all()
    assert not np.isinf(f.to_numpy(dtype=float)).any()


def test_features_do_not_use_future_data():
    """Changing prices after day t must not change any feature at or before t."""
    p = _prices()
    cut = 300
    altered = p.copy()
    altered.loc[cut + 1 :, ["high", "low", "close", "volume"]] *= 3.7
    a = compute_features(p).iloc[: cut + 1]
    b = compute_features(altered).iloc[: cut + 1]
    pd.testing.assert_frame_equal(a, b)


def test_features_are_independent_of_row_order():
    p = _prices()
    pd.testing.assert_frame_equal(compute_features(p), compute_features(p.sample(frac=1, random_state=1)))


def test_rsi_bounds_and_extremes():
    f = compute_features(_prices())
    rsi = f["rsi_14"].dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()

    rising = _prices()
    rising["close"] = np.linspace(100, 300, len(rising))
    rising["high"], rising["low"] = rising["close"] * 1.001, rising["close"] * 0.999
    assert compute_features(rising)["rsi_14"].dropna().iloc[-1] > 99


def test_zero_volume_does_not_produce_inf():
    p = _prices()
    p["volume"] = 0.0
    f = compute_features(p)
    assert not np.isinf(f.to_numpy(dtype=float)).any()
    assert f["vol_spike"].isna().all()


def test_target_forward_return_and_classes():
    p = _prices(300)
    f = compute_features(p)
    fwd, label = make_target(p, f, horizon=5, k=0.5)
    close = p.set_index("date")["close"]
    assert np.isclose(fwd.iloc[250], close.iloc[255] / close.iloc[250] - 1)
    assert fwd.iloc[-5:].isna().all() and label.iloc[-5:].isna().all()  # no full forward window
    assert label.iloc[: MIN_HISTORY - 1].isna().all()  # no band without history
    band = 0.5 * f["volatility_20"] * np.sqrt(5)
    row = 250
    expected = 2 if fwd.iloc[row] > band.iloc[row] else 0 if fwd.iloc[row] < -band.iloc[row] else 1
    assert label.iloc[row] == expected
    assert set(label.dropna().unique()) <= {0, 1, 2}


def test_dataset_drops_unlabelled_rows_and_pools_tickers():
    prices = pd.concat([_prices(seed=1, ticker="AAA"), _prices(seed=2, ticker="BBB")])
    ds = build_dataset(prices, horizon=1)
    assert set(ds["ticker"]) == {"AAA", "BBB"}
    assert ds["label"].isin([0, 1, 2]).all()
    assert ds["date"].max() < prices["date"].max()  # last day has no forward return
    assert ds["date"].is_monotonic_increasing


def test_walk_forward_splits_are_time_ordered_embargoed_and_expanding():
    dates = pd.Series(np.repeat(pd.bdate_range("2015-01-01", periods=2000), 3))  # 3 tickers per day
    horizon = 5
    folds = list(walk_forward_splits(dates, min_train_days=500, test_days=250, embargo=horizon))
    assert len(folds) >= 4
    prev_train = 0
    unique_days = pd.DatetimeIndex(np.sort(dates.unique()))
    for train, test in folds:
        assert set(train).isdisjoint(test)
        t_max, s_min = dates.iloc[train].max(), dates.iloc[test].min()
        assert t_max < s_min
        gap = unique_days.searchsorted(s_min) - unique_days.searchsorted(t_max) - 1
        assert gap >= horizon  # label windows of late training rows cannot reach the test period
        assert len(train) > prev_train  # expanding window
        prev_train = len(train)
    test_ranges = [(dates.iloc[t].min(), dates.iloc[t].max()) for _, t in folds]
    assert all(a[1] < b[0] for a, b in zip(test_ranges, test_ranges[1:]))  # test windows never overlap


def test_walk_forward_end_caps_data():
    dates = pd.Series(pd.bdate_range("2015-01-01", periods=1500))
    cap = 1000
    for _, test in walk_forward_splits(dates, min_train_days=500, test_days=100, embargo=5, end=cap):
        assert test.max() < cap
