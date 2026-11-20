from datetime import date, timedelta

import pandas as pd

from app.services import market_data
from app.services.market_data import upsert_prices


def _seed(db, ticker="AAPL", days=400):
    end = date.today()
    rows = [
        {"date": end - timedelta(days=i), "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}
        for i in range(days)
    ]
    upsert_prices(db, ticker, pd.DataFrame(rows, columns=market_data.COLUMNS))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_tickers(client):
    data = client.get("/stocks").json()
    assert len(data) == 30
    assert {"symbol", "name", "sector"} <= data[0].keys()


def test_prices_range_filters_and_orders(client, db):
    _seed(db)
    r = client.get("/stocks/aapl/prices?range=1m")
    body = r.json()
    assert r.status_code == 200 and body["ticker"] == "AAPL"
    dates = [p["date"] for p in body["prices"]]
    assert dates == sorted(dates) and 28 <= len(dates) <= 32
    assert len(client.get("/stocks/AAPL/prices?range=max").json()["prices"]) == 400


def test_prices_empty_cache_returns_empty_series(client):
    body = client.get("/stocks/MSFT/prices").json()
    assert body["prices"] == [] and body["last_updated"] is None


def test_unsupported_ticker_404_and_bad_range_422(client):
    assert client.get("/stocks/ZZZZ/prices").status_code == 404
    assert client.get("/stocks/AAPL/prices?range=10y").status_code == 422
