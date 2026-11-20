from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Ticker
from app.schemas.stocks import PriceSeries, TickerOut
from app.services import market_data

router = APIRouter(prefix="/stocks", tags=["stocks"])

RANGES = {"1m": 31, "3m": 93, "6m": 186, "1y": 366, "5y": 366 * 5, "max": None}


@router.get("", response_model=list[TickerOut])
def list_tickers(db: Session = Depends(get_db)):
    return list(db.scalars(select(Ticker).order_by(Ticker.symbol)))


@router.get("/{ticker}/prices", response_model=PriceSeries)
def prices(
    ticker: str,
    range: Literal["1m", "3m", "6m", "1y", "5y", "max"] = Query("1y"),
    db: Session = Depends(get_db),
):
    ticker = ticker.upper()
    if db.get(Ticker, ticker) is None:
        raise HTTPException(404, "Ticker not supported")
    days = RANGES[range]
    start = date.today() - timedelta(days=days) if days else None
    return PriceSeries(
        ticker=ticker,
        prices=market_data.get_prices(db, ticker, start),
        last_updated=market_data.latest_price_date(db, ticker),
    )
