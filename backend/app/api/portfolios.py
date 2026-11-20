from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models import Holding, Portfolio, Ticker, User
from app.schemas.portfolio import HoldingIn, HoldingOut, HoldingUpdate, PortfolioIn, PortfolioOut

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def _owned_portfolio(db: Session, user: User, portfolio_id: int) -> Portfolio:
    """Every lookup is scoped to the caller; someone else's id is indistinguishable from a missing one."""
    p = db.scalar(select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id))
    if p is None:
        raise HTTPException(404, "Portfolio not found")
    return p


def _owned_holding(db: Session, portfolio: Portfolio, holding_id: int) -> Holding:
    h = db.scalar(select(Holding).where(Holding.id == holding_id, Holding.portfolio_id == portfolio.id))
    if h is None:
        raise HTTPException(404, "Holding not found")
    return h


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)))


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    body: PortfolioIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    count = db.scalar(select(func.count()).select_from(Portfolio).where(Portfolio.user_id == user.id))
    if count >= settings.max_portfolios:
        raise HTTPException(409, f"Portfolio limit reached ({settings.max_portfolios})")
    p = Portfolio(user_id=user.id, name=body.name)
    db.add(p)
    db.commit()
    return p


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _owned_portfolio(db, user, portfolio_id)


@router.put("/{portfolio_id}", response_model=PortfolioOut)
def rename_portfolio(
    portfolio_id: int,
    body: PortfolioIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = _owned_portfolio(db, user, portfolio_id)
    p.name = body.name
    db.commit()
    return p


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    db.delete(_owned_portfolio(db, user, portfolio_id))
    db.commit()


@router.post("/{portfolio_id}/holdings", response_model=HoldingOut, status_code=201)
def add_holding(
    portfolio_id: int, body: HoldingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    p = _owned_portfolio(db, user, portfolio_id)
    if db.get(Ticker, body.ticker) is None:
        raise HTTPException(422, "Ticker is not in the supported universe")
    if len(p.holdings) >= settings.max_holdings:
        raise HTTPException(409, f"Holding limit reached ({settings.max_holdings})")
    if any(h.ticker == body.ticker for h in p.holdings):
        raise HTTPException(409, "Ticker already in this portfolio; update the existing holding")
    h = Holding(portfolio_id=p.id, ticker=body.ticker, quantity=body.quantity, avg_price=body.avg_price)
    db.add(h)
    db.commit()
    return h


@router.put("/{portfolio_id}/holdings/{holding_id}", response_model=HoldingOut)
def update_holding(
    portfolio_id: int,
    holding_id: int,
    body: HoldingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    h = _owned_holding(db, _owned_portfolio(db, user, portfolio_id), holding_id)
    h.quantity, h.avg_price = body.quantity, body.avg_price
    db.commit()
    return h


@router.delete("/{portfolio_id}/holdings/{holding_id}", status_code=204)
def delete_holding(
    portfolio_id: int, holding_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    db.delete(_owned_holding(db, _owned_portfolio(db, user, portfolio_id), holding_id))
    db.commit()
