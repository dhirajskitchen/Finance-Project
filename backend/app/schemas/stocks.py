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


class SignalOut(BaseModel):
    ticker: str
    date: date  # date of the price bar the signal was computed from
    horizon_days: int
    prediction: str  # down | flat | up
    action: str  # sell | hold | buy
    probability: float  # probability of the predicted class
    probabilities: dict[str, float]
    model_version: str
    disclaimer: str = "Decision support from a statistical model with a small edge. Not financial advice."


class ForecastPoint(BaseModel):
    date: date
    ets: float
    naive: float


class ModelError(BaseModel):
    mae: float
    mape: float
    direction_accuracy: float | None


class ForecastEval(BaseModel):
    window_days: int
    naive: ModelError
    ets: ModelError
    ets_beats_naive: bool
    mae_improvement_pct: float


class ForecastOut(BaseModel):
    ticker: str
    last_close: float
    last_date: date
    forecast: list[ForecastPoint]
    evaluation: ForecastEval
    note: str


class TickerOut(BaseModel):
    symbol: str
    name: str
    sector: str

    model_config = {"from_attributes": True}
