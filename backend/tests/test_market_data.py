from datetime import date, timedelta

import httpx
import pandas as pd
import respx

from app.services import market_data
from app.services.market_data import FinnhubClient, refresh_ticker, upsert_prices


def _bars(start: date, n: int, close: float = 100.0) -> pd.DataFrame:
    rows = [
        {
            "date": start + timedelta(days=i),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close + i,
            "volume": 1000.0 + i,
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows, columns=market_data.COLUMNS)


class FakeProvider:
    def __init__(self, df):
        self.df, self.calls = df, []

    def daily_ohlcv(self, ticker, start, end=None):
        self.calls.append(start)
        return self.df[self.df["date"] >= start]


def test_upsert_is_idempotent_and_updates(db):
    df = _bars(date(2024, 1, 1), 5)
    assert upsert_prices(db, "AAPL", df) == 5
    upsert_prices(db, "AAPL", df)
    assert len(market_data.get_prices(db, "AAPL")) == 5

    df.loc[0, "close"] = 999.0
    upsert_prices(db, "AAPL", df)
    assert market_data.get_prices(db, "AAPL")[0].close == 999.0


def test_upsert_empty_and_missing_volume(db):
    assert upsert_prices(db, "AAPL", pd.DataFrame(columns=market_data.COLUMNS)) == 0
    df = _bars(date(2024, 1, 1), 1)
    df["volume"] = float("nan")
    upsert_prices(db, "AAPL", df)
    assert market_data.get_prices(db, "AAPL")[0].volume is None


def test_refresh_only_fetches_missing_range(db):
    df = _bars(date(2024, 1, 1), 30)
    p = FakeProvider(df)
    refresh_ticker(db, p, "MSFT")  # nothing cached: full backfill
    assert p.calls[0] < date(2024, 1, 1)

    refresh_ticker(db, p, "MSFT")  # cached: starts shortly before the newest row
    assert p.calls[1] == market_data.latest_price_date(db, "MSFT") - timedelta(days=5)


@respx.mock
def test_finnhub_client_sends_token_and_params():
    route = respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"c": 1.0})
    )
    assert FinnhubClient(api_key="k").quote("AAPL") == {"c": 1.0}
    assert route.calls[0].request.url.params["token"] == "k"
    assert route.calls[0].request.url.params["symbol"] == "AAPL"


@respx.mock
def test_finnhub_client_raises_on_http_error():
    respx.get("https://finnhub.io/api/v1/quote").mock(return_value=httpx.Response(429))
    try:
        FinnhubClient(api_key="k").quote("AAPL")
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected HTTPStatusError")
