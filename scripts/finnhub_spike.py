"""Phase 1 spike: which Finnhub free-tier endpoints work with our key? Prints status only, never the key."""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import settings  # noqa: E402

BASE = "https://finnhub.io/api/v1"
key = settings.finnhub_api_key
if not key:
    sys.exit("FINNHUB_API_KEY is empty in .env")

now = int(time.time())
today = date.today()
tests = {
    "quote": ("/quote", {"symbol": "AAPL"}),
    "candle (daily, 1y)": ("/stock/candle", {"symbol": "AAPL", "resolution": "D", "from": now - 365 * 86400, "to": now}),
    "company-news (7d)": ("/company-news", {"symbol": "AAPL", "from": str(today - timedelta(days=7)), "to": str(today)}),
    "company-news (1y ago, 7d)": ("/company-news", {"symbol": "AAPL", "from": str(today - timedelta(days=372)), "to": str(today - timedelta(days=365))}),
    "profile2": ("/stock/profile2", {"symbol": "AAPL"}),
}
for name, (path, params) in tests.items():
    r = httpx.get(BASE + path, params={**params, "token": key}, timeout=20)
    body = r.text[:160].replace("\n", " ")
    extra = ""
    if r.status_code == 200:
        j = r.json()
        extra = f" items={len(j)}" if isinstance(j, list) else f" keys={list(j)[:8]}"
    print(f"{name:28s} HTTP {r.status_code}{extra}" + ("" if r.status_code == 200 else f" :: {body}"))
