from collections.abc import Iterator

import numpy as np
import pandas as pd


def walk_forward_splits(
    dates: pd.Series,
    *,
    min_train_days: int = 756,
    test_days: int = 126,
    embargo: int = 5,
    end: int | None = None,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window splits over a pooled (many tickers) dataset, split on *dates* so no calendar day is
    ever in both train and test.

    Fold k trains on trading days [0, s) and tests on [s + embargo, s + embargo + test_days). The `embargo`
    gap exists because a training row at day t has a label built from prices up to t + horizon; without it
    the last training labels would overlap the test period. Pass embargo >= horizon.
    `end` (in trading days) caps the data used, e.g. to keep a final holdout untouched.
    Yields (train_row_idx, test_row_idx) as positional indices into `dates`.
    """
    d = pd.to_datetime(dates).reset_index(drop=True)
    days = np.sort(d.unique())
    last = len(days) if end is None else min(end, len(days))
    s = min_train_days
    while s + embargo < last:
        lo, hi = s + embargo, min(s + embargo + test_days, last)
        train = np.flatnonzero((d < days[s]).to_numpy())
        test = np.flatnonzero(((d >= days[lo]) & (d <= days[hi - 1])).to_numpy())
        if len(train) and len(test):
            yield train, test
        s += test_days
