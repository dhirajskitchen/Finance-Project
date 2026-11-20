from pydantic import BaseModel, Field, field_validator


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    avg_price: float = Field(ge=0, le=1e9, allow_inf_nan=False)

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class HoldingUpdate(BaseModel):
    quantity: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    avg_price: float = Field(ge=0, le=1e9, allow_inf_nan=False)


class HoldingOut(BaseModel):
    id: int
    ticker: str
    quantity: float
    avg_price: float

    model_config = {"from_attributes": True}


class PortfolioOut(BaseModel):
    id: int
    name: str
    holdings: list[HoldingOut]

    model_config = {"from_attributes": True}
