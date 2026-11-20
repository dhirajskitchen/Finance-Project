from datetime import date

from pydantic import BaseModel


class PriceBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None

    model_config = {"from_attributes": True}


class PriceSeries(BaseModel):
    ticker: str
    prices: list[PriceBar]
    last_updated: date | None


class TickerOut(BaseModel):
    symbol: str
    name: str
    sector: str

    model_config = {"from_attributes": True}
