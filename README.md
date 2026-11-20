# Explainable Portfolio Risk & Signal Dashboard

Stock signals, SHAP explanations, sentiment overlay and portfolio risk analytics. See [PLAN.md](PLAN.md) for the build checklist.

> Educational tool, not financial advice.

## Local setup

```bash
cp .env.example .env        # fill in FINNHUB_API_KEY, GEMINI_API_KEY (Google OAuth values are needed from Phase 2)

# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.jobs prices                            # seeds the 30-ticker universe and backfills ~8y of daily prices
uvicorn app.main:app --reload                        # http://localhost:8000/docs

# frontend
cd frontend
cp .env.example .env.local
npm install && npm run dev                           # http://localhost:5173
```

Signal model (details and honest results in [docs/model_report.md](docs/model_report.md)):

```bash
cd backend
python -m app.ml.train --horizon 5   # walk-forward CV + holdout, writes app/ml/artifacts/ and docs/metrics_h5.json
python -m app.jobs signals           # score every ticker and store today's signal
```

Tests: `cd backend && pytest -q`. Or run API + Postgres with `docker compose up --build`.

## Data sources (verified on the free tier)

| Need | Source | Notes |
|---|---|---|
| Daily OHLCV | yfinance, scheduled jobs only | Finnhub candles return 403 on the free plan; `/quote` has no volume |
| News headlines | Finnhub `company-news` | History reaches back roughly 9 months |
| Live quote | Finnhub `/quote` | Cross-check only |

The API serves prices from the database and never calls a market-data provider per request.
