# Build Plan & Checklist: Explainable Portfolio Risk & Signal Dashboard

> Educational tool, not financial advice. Tick boxes as you go. Each phase ends with a **Done when** gate; don't start the next phase until it passes.

---

## 0. Feasibility Decisions (changes vs. the original summary)

The original scope is good, but several items break on free hosting or have data problems. These decisions make it buildable and deployable. **Confirm them before Phase 1.**

| # | Issue in original | Decision |
|---|---|---|
| D1 | FinBERT (~440 MB + torch) won't fit a free 512 MB API host and is slow on CPU | **Never run FinBERT in the web API.** Score headlines in an offline/scheduled job (GitHub Actions or local), write results to the DB. Optional: ONNX-quantized FinBERT or HF Inference API. Fallback: VADER if FinBERT is cut. |
| D2 | Free news APIs only return recent headlines (days to ~1 yr), so a sentiment *feature* has no deep history, and training on it would be leaky or sparse | Core classifier trains **without** sentiment on years of prices. Sentiment is an **overlay** first. A second "price + sentiment" model is trained only on the window where headlines exist, and compared honestly against the core model. Start collecting headlines daily from Week 1. |
| D3 | Prophet/LSTM are heavy (Prophet build pain, LSTM needs torch/TF) | Baseline forecast = **naive (tomorrow = today)** plus **statsmodels ETS/ARIMA**. Show forecast error vs. naive. No LSTM/Prophet. |
| D4 | Training "per ticker" on thin data overfits | One **pooled model over a fixed universe (~30 liquid tickers, e.g. S&P large caps)** with ticker-agnostic features. Users may add holdings only from the supported universe. |
| D5 | yfinance is unofficial and often blocked from cloud IPs | **Finnhub chosen** for news and quotes. Its historical candle endpoint has been paywalled and `/quote` has no volume, so **Phase 1 starts with a 1-hour spike** testing which Finnhub free endpoints work. Plan: yfinance for bulk history + daily OHLCV inside the GitHub Actions job (not the API), Finnhub `/quote` as a cross-check/fallback, Twelve Data as backup if both fail. |
| D6 | APScheduler inside a free web dyno sleeps with it | Run refresh/scoring/signal jobs as **scheduled GitHub Actions** (or Render cron) calling a CLI or a token-protected `/internal/jobs/*` endpoint. Drop in-process APScheduler. |
| D7 | Render free Postgres expires; SQLite is lost on redeploy | **Neon or Supabase free Postgres**. SQLite for local dev/tests only. |
| D8 | Vercel (frontend) and Render (API) are different sites, so cookie auth breaks | Use a **custom domain with a shared parent** (`app.x.com`, `api.x.com`) with `SameSite=Lax` httpOnly cookies, **or** an OAuth callback that sets the refresh cookie on the API domain plus a short-lived access token in memory. Decide in Phase 2. |
| D9 | SHAP on every request is slow | **Precompute** signal + SHAP once per ticker per day in the daily job; store in `signals.shap_json`. API just reads. |
| D10 | Free API hosts cold-start (~30-60 s) | Add a keep-warm ping (GitHub Actions cron) and a frontend loading state. Mention in README. |
| D12 | LLM provider is Gemini | Use the Gemini API (free tier, e.g. a Flash model; confirm current model name) behind an `LLMProvider` interface. Same number-validator and template fallback apply. |
| D11 | Scoped tokens, HMM regimes, stress tests, drift, conformal | **Out of MVP.** Pick at most one stretch item after Phase 8 (stress tests are cheapest). |

**MVP definition:** login, portfolio CRUD, prices chart + naive/ETS forecast, daily signal + SHAP, sentiment overlay, risk metrics, LLM summary, deployed, tested, documented.

---

## Phase 1: Foundation & Data (Week 1)

### 1.1 Repo & tooling
- [x] `git init`, `.gitignore` (venv, node_modules, `.env`, model caches, `*.db`)
- [x] Monorepo layout: `backend/`, `frontend/`, `docker-compose.yml`, `README.md`, `.env.example`
- [x] Python 3.11 venv; pin deps in `requirements.txt` (separate `requirements-ml.txt` for training-only deps: torch, transformers, shap, notebooks)
- [x] Lint/format: ruff + black (backend), eslint + prettier (frontend); pre-commit
- [x] GitHub repo + Actions CI skeleton (lint + tests)

### 1.2 Backend skeleton
- [x] FastAPI app factory, `/health` endpoint, structured logging
- [x] Settings via `pydantic-settings` (all secrets from env; no defaults for secrets)
- [x] SQLAlchemy 2.x + Alembic; initial migration
- [x] Models: `users`, `portfolios`, `holdings`, `prices`, `headlines`, `signals`
  - [ ] Unique constraints: `prices(ticker,date)`, `signals(ticker,date)`, `headlines(ticker,published_at,text-hash)`
  - [ ] Indexes on `(ticker,date)`, `holdings.portfolio_id`, `portfolios.user_id`
  - [ ] Add `refresh_tokens` table (hashed token, user_id, family_id, expires_at, revoked_at)
  - [ ] Add `tickers` table (symbol, name, sector) for the supported universe and sector exposure
- [ ] `docker-compose.yml`: Postgres + backend (+ frontend dev)

### 1.3 Market data service
- [x] **Spike (1 hr):** test Finnhub free endpoints (quote, company-news, candles) and record what works; get key; write a `MarketDataProvider` interface so providers are swappable
- [x] Fetch daily OHLCV, upsert into `prices` (idempotent)
- [x] Cache-first reads: serve from DB, refresh only if stale; respect rate limits (client-side throttle + retry/backoff)
- [x] Define the ~30-ticker universe + sector map; seed script
- [x] Offline bulk backfill script (yfinance, 5-10 yrs) -> DB
- [x] `GET /stocks/{ticker}/prices?range=` endpoint (validates ticker against universe)

### 1.4 Frontend skeleton
- [x] Vite + React + **TypeScript (strict)**, React Router, TanStack Query, Recharts (or Plotly)
- [x] API client module with base URL from env
- [x] Basic `PriceChart` on a StockDetail page (unauthenticated for now)

**Done when:** `docker compose up` shows a price chart for any universe ticker from cached DB data; tests for the provider (mocked) pass.

---

## Phase 2: Auth & Portfolios (Week 2)

### 2.1 OAuth2 + sessions
- [ ] Register Google OAuth app (dev + prod redirect URIs); (GitHub optional)
- [ ] Authlib login/callback; upsert user by `(provider, provider_sub)`; validate `state`
- [ ] Decide token transport (D8) and implement
- [ ] Short-lived JWT access token (~15 min) + **refresh-token rotation**: store hash, rotate on use, revoke family on reuse detection
- [ ] `/auth/logout`, `/auth/refresh`, `GET /me`
- [ ] `get_current_user` dependency used by every protected route

### 2.2 Portfolios & holdings
- [ ] CRUD: portfolios, holdings (add/update/delete); validate ticker in universe, quantity > 0, avg_price >= 0
- [ ] **Per-user isolation:** every query filters by `user_id`; return 404 (not 403) for others' resources
- [ ] Tests: user A cannot read/modify user B's portfolio (IDOR tests)
- [ ] Limits: max portfolios/holdings per user

### 2.3 Frontend
- [ ] Login page, auth context, protected routes, silent refresh
- [ ] Dashboard (portfolio list) and Portfolio page (holdings table + add/edit/delete forms)

**Done when:** log in with Google, create a portfolio, add holdings, log out; isolation tests green.

---

## Phase 3: Features, Model & Signals (Week 3)

### 3.1 Feature engineering (`ml/features.py`)
- [ ] RSI, MACD (+signal/hist), momentum (5/10/20d), volume spike (vs 20d avg), MA ratios (price/SMA20, SMA20/SMA50), rolling volatility, returns lags
- [ ] Use only data available at close of day *t* to predict *t+1..t+N*; assert no look-ahead (unit test: shifting future data doesn't change features)
- [ ] Single shared function used by both training and serving (prevents train/serve skew)

### 3.2 Target & validation
- [ ] Target: N-day forward return bucketed into down / flat / up (threshold e.g. ±0.5%, or per-ticker volatility-scaled); choose N (start 1 day, test 5)
- [ ] Walk-forward (expanding window) CV with a **gap/embargo** of N days; no shuffling
- [ ] Metrics: accuracy, macro-F1, log-loss, per-class precision, confusion matrix
- [ ] **Baselines to beat:** majority class, "same as yesterday", logistic regression on same features
- [ ] Optional backtest: simple long/flat strategy vs buy-and-hold net of a cost assumption (report honestly even if it doesn't win)

### 3.3 Train & package
- [ ] XGBoost or LightGBM (pick one); light hyperparameter search inside walk-forward folds only
- [ ] Probability calibration check (reliability curve; isotonic if needed)
- [ ] Save model + feature list + version + training date + metrics as artifacts (small; commit or store in repo/release)
- [ ] Training notebook/script with a fixed random seed (deliverable)

### 3.4 Serving
- [ ] `signal_service`: load model once at startup; compute latest features from DB prices
- [ ] Daily job: for each ticker, compute signal, probability, store in `signals`
- [ ] `GET /stocks/{ticker}/signal` (reads the stored row; falls back to compute if missing)
- [ ] Forecast baseline: naive + ETS; `GET /stocks/{ticker}/forecast` with naive-vs-model error stats

**Done when:** signal endpoint returns a class + probability; walk-forward report exists in `docs/`; leakage test passes; results compared to baselines (even if the edge is small).

---

## Phase 4: Explainability & Risk (Week 4)

### 4.1 SHAP
- [ ] `TreeExplainer` once at training time, saved/loaded with the model
- [ ] Handle multiclass output shape (per-class SHAP arrays) correctly; explain the **predicted** class
- [ ] Store top-K feature contributions + base value in `signals.shap_json`
- [ ] `GET /stocks/{ticker}/explain` (local); global importance (mean |SHAP|) saved as a static JSON artifact from training
- [ ] Frontend `ShapChart` (bar/waterfall, color by push toward buy/sell) + global importance view + plain-language feature labels

### 4.2 Portfolio risk (`risk_service`, pure functions, heavily unit-tested)
- [ ] Align return series across holdings; handle short history/missing days
- [ ] Portfolio weights from `quantity × latest close`
- [ ] Volatility (annualized), correlation matrix
- [ ] Historical VaR (95%/99%, 1-day) and CVaR; Monte Carlo VaR (Cholesky or bootstrap, fixed seed)
- [ ] Concentration: largest position %, top-3 %, HHI, sector exposure
- [ ] Risk contributors: marginal/component contribution to volatility per holding
- [ ] `GET /portfolios/{id}/risk` (owner-only); cache result by portfolio+latest price date
- [ ] Verify numerics against a hand-computed small example in tests
- [ ] Frontend `RiskCards`, correlation heatmap, contributor bar chart

**Done when:** explanation chart renders for a signal; risk numbers match test fixtures; frontend shows both.

---

## Phase 5: News & Sentiment (Week 5)

- [ ] Choose news source (Finnhub company-news or NewsAPI; check free-tier history window and ToS)
- [ ] Headline ingestion job: fetch per ticker, dedupe (hash), store in `headlines`; **start running daily ASAP** (see D2)
- [ ] FinBERT scoring script (`ProsusAI/finbert`): batch, CPU-friendly batch size, writes `sentiment_label` + `sentiment_score` (e.g. P(pos) − P(neg)); runs in GitHub Actions / locally, **not in API**
- [ ] Daily aggregation per ticker (mean score, headline count; handle days with no news as NaN/neutral and carry the count)
- [ ] `GET /stocks/{ticker}/sentiment` (daily series + recent headlines with labels)
- [ ] Frontend `SentimentLine` aligned with `PriceChart` (shared x-axis, dual axis or stacked panel)
- [ ] Sentiment-as-feature experiment: train price+sentiment model on the available window; compare to core model with the same walk-forward protocol; **ship only if it helps, otherwise document the negative result**
- [ ] Guard: serving path must tolerate missing sentiment (feature = NaN, which tree models handle)

**Done when:** a sentiment line shows beside price for universe tickers with fresh headlines; scoring job runs unattended.

---

## Phase 6: LLM Summary & Hardening (Week 6a)

### 6.1 Summary
- [ ] `llm_service`: build a structured JSON of **code-computed** metrics (weights, VaR, vol, concentration, top contributors, signals summary)
- [ ] Prompt: narrate only supplied figures, no advice, no outside facts, include disclaimer; low temperature
- [ ] **Number validator:** extract numbers from the output; every number must match an input value (tolerance for rounding/percent formatting); on failure retry once, then fall back to a deterministic template summary
- [ ] `POST /portfolios/{id}/summary` (owner-only), cache by metrics hash, timeout + error handling
- [ ] Provider: Gemini API (Flash-class model, via `google-genai`); key server-side only; `LLMProvider` interface; per-user daily cap to control cost
- [ ] Frontend `SummaryPanel` with "Explain my portfolio" button, loading/error states, disclaimer

### 6.2 Security hardening
- [ ] `slowapi` per-user (fallback per-IP) limits; stricter on `/summary` and auth routes
- [ ] CORS locked to the frontend origin(s); security headers; HTTPS only in prod; cookie flags (`HttpOnly`, `Secure`, `SameSite`)
- [ ] Input validation everywhere (Pydantic); ticker whitelist; request size limits
- [ ] Token-protect `/internal/jobs/*` with a secret; never expose in OpenAPI docs in prod
- [ ] Secrets only in env/host secret stores; rotate any key ever committed; add secret scanning (gitleaks) to CI
- [ ] `pip-audit` / `npm audit` in CI
- [ ] Run a self security review (auth flows, IDOR, SSRF, prompt injection via headline text — headlines are **not** fed to the summary LLM, or are sanitized if they are)

### 6.3 Tests
- [ ] Backend: unit (features, risk, validator), API (auth, isolation, CRUD), mocked external APIs; coverage target ~70% on services
- [ ] Frontend: a few component tests + one end-to-end happy path (Playwright) against docker-compose
- [ ] CI runs all on every PR

**Done when:** summary passes the validator on real portfolios; rate limiting verified; CI green.

---

## Phase 7: Deployment (Week 6b)

### 7.1 Containers
- [ ] Backend Dockerfile: slim Python image, non-root user, **no torch/transformers/shap training deps** in the runtime image (SHAP is precomputed; target image well under free-tier memory)
- [ ] Verify runtime memory < ~400 MB under load
- [ ] Frontend built as static assets (Vite) for Vercel

### 7.2 Infrastructure
- [ ] Postgres on Neon/Supabase; run `alembic upgrade head` as a release step; seed universe + backfill history
- [ ] API on Render/Railway/Fly; env vars set; health check path; CORS + OAuth redirect URIs updated to prod URLs
- [ ] Frontend on Vercel with `VITE_API_URL`; SPA rewrite rule
- [ ] Custom domain / shared parent domain if using cookie auth (D8)
- [ ] GitHub Actions cron jobs: daily price refresh -> news ingest -> FinBERT scoring -> signal + SHAP compute; keep-warm ping
- [ ] Job failure alerts (Actions email or a Slack/Discord webhook); jobs are idempotent and re-runnable
- [ ] Backups: confirm provider's backup policy; export a seed dump

### 7.3 Smoke test in prod
- [ ] Login with a real Google account, create portfolio, view risk, signal, explanation, sentiment, summary
- [ ] Check logs for secrets/PII leaks; confirm `/docs` and job endpoints are locked down

**Done when:** a public URL works end-to-end from a fresh browser and jobs ran on schedule for at least 2-3 consecutive days.

---

## Phase 8: Docs, Report & Demo (Week 6c)

- [ ] README: overview, architecture diagram, screenshots, local setup (`.env.example`), deploy steps, job schedule, **limitations & disclaimer**
- [ ] `docs/report.md` (short report): methodology, data, features, validation scheme, results vs baselines, SHAP findings, sentiment experiment result, risk-method assumptions, limitations (survivorship bias, transaction costs, regime change, small universe)
- [ ] Model card: training window, metrics, intended use, known failure modes
- [ ] API docs: OpenAPI exported
- [ ] 2-3 min demo video/GIF + live link in README
- [ ] Final deliverables check against section 11 of the original summary

---

## Phase 9: Optional Stretch (pick ONE, only after MVP is live)

- [ ] Historical stress tests (2008, COVID-19 replays on current weights): cheapest, most valuable
- [ ] Conformal prediction intervals on the ETS forecast
- [ ] Price alerts / drift monitoring
- [ ] HMM market regime tag
- [ ] Scoped tokens (read-only vs. full)

---

## Cross-Cutting Risk Register

| Risk | Mitigation | Owner phase |
|---|---|---|
| API rate limits / quota exhaustion | DB cache, scheduled refresh only, throttle + backoff, tiny universe | 1, 7 |
| Look-ahead leakage | Shared feature fn, embargo gap, leakage unit test | 3 |
| Weak predictive power | Baseline comparison, calibrated probabilities, "decision support" framing, publish honest metrics | 3, 8 |
| Sentiment history too short | Overlay first; separate experiment; start collecting day 1 | 5 |
| FinBERT too heavy | Offline scoring only | 5, 7 |
| LLM hallucinated numbers | Code-computed JSON, validator, template fallback | 6 |
| LLM cost abuse | Per-user cap, cache, rate limit | 6 |
| Cold starts / free-tier sleep | Keep-warm ping, loading UI | 7 |
| Cross-domain auth failure | Decide D8 early; test on prod domain in Phase 2 | 2, 7 |
| Data licensing / ToS | Check each API's terms before public deploy; show attribution | 1, 5 |
| Scope creep | MVP definition above; one stretch item max | all |

---

## Suggested Order of Work Inside Each Week

1. Write the interface/schema and a failing test
2. Implement the backend piece
3. Wire the frontend piece
4. Update docs/README as you go (don't leave it for the end)
5. Commit small and often; CI must stay green

## Decisions Log

1. Market data/news: **Finnhub** (see D5 for caveats)
2. LLM: **Gemini API** (D12)
3. Auth: **Google only**
4. Frontend: **TypeScript**
5. Hosting (API/DB provider, custom domain): **deferred until Phase 7**; keep code host-agnostic (env-driven config, Dockerfile, D8 decision revisited in Phase 2)
