"""CLI entrypoint for scheduled jobs: python -m app.jobs <seed|prices|signals> [--tickers A,B]"""

import argparse
import logging
import time

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.universe import SYMBOLS, UNIVERSE
from app.models import Ticker
from app.services.market_data import YFinanceProvider, refresh_ticker

log = logging.getLogger("jobs")


def seed_universe(db: Session) -> None:
    for symbol, name, sector in UNIVERSE:
        db.merge(Ticker(symbol=symbol, name=name, sector=sector))
    db.commit()


def refresh_prices(db: Session, tickers: list[str]) -> None:
    provider = YFinanceProvider()
    for t in tickers:
        try:
            log.info("%s: %d rows", t, refresh_ticker(db, provider, t))
        except Exception:
            db.rollback()
            log.exception("%s: refresh failed", t)
        time.sleep(0.5)


def compute_signals(db: Session, tickers: list[str]) -> None:
    from app.services import signal_service

    for t in tickers:
        try:
            sig = signal_service.compute_signal(db, t)
            if sig is None:
                log.warning("%s: not enough history for a signal", t)
                continue
            signal_service.store_signal(db, sig)
            log.info("%s: %s (%.2f) as of %s", t, sig["action"], sig["probability"], sig["date"])
        except Exception:
            db.rollback()
            log.exception("%s: signal failed", t)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["seed", "prices", "signals"])
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or sorted(SYMBOLS)
    with SessionLocal() as db:
        seed_universe(db)
        if args.job == "prices":
            refresh_prices(db, tickers)
        elif args.job == "signals":
            compute_signals(db, tickers)


if __name__ == "__main__":
    main()
