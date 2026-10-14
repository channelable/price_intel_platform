# Price Tracker — Implementation Plan (v2)

## What changed from v1

1. **Seeded catalog instead of submission-only.** v1 grew the catalog only from user-submitted URLs, which gives a cold-start problem (no history = no predictions). v2 scrapes a fixed seed set from day 1; user-submitted URLs become a bonus feature.
2. **Model development starts on public data.** A Kaggle pricing dataset is used to build and debug features + training while live data accumulates.
3. **The agent writes the code; I learn by reading.** Clean code plus a short explainer doc per piece, instead of hand-writing everything or doing quizzes and exercises (see "Learning approach").
4. **Compressed schedule.** Roughly 7 focused build days, with live data accumulating in parallel from day 1. Live predictions only become meaningful after ~2+ weeks of history.

---

## Goal

A BuyHatke-style price-tracking web app, built as an end-to-end ML pipeline portfolio project.

**Primary purpose: understanding.** I want to be able to explain and defend every part: scraping, storage design, feature engineering, modeling decisions, serving, caching, deployment. The agent writes the code; I make sure I understand the parts that matter, without spending much time writing or quizzing.

---

## Learning approach

Full working rules for the agent are in `AGENTS.md`. In short:

- **Code** is simple, readable, and production-level, with comments only where the *why* isn't obvious.
- **Each piece gets an explainer** at `docs/<piece>.md`: what it does, how it fits the pipeline, key decisions and trade-offs, failure modes, and a few interview questions with short answers.
- **Depth goes where it counts.** The ML and design pieces (features, labels and splits, metrics, model choice, anomaly flag, caching) get detailed explainers and one short check question. Scraping, Docker, UI, and deployment get short explainers I can skim.
- **Explain on demand.** "Why this?" about any part gets a plain answer.

---

## Tech stack

- **Language:** Python 3.11+
- **Ingestion:** plain HTTP scrapers with per-host adapters (Amazon/Flipkart), Playwright fallback for JS-rendered pages; Celery + Celery Beat for scheduling
- **Storage:** PostgreSQL (products, price_history, predictions, alerts), Redis (cache + Celery broker)
- **ML:** scikit-learn / XGBoost; MLflow with local file store; optional PyTorch LSTM only if it beats the simple model
- **Serving:** FastAPI + SQLAlchemy; background worker for prediction jobs and alert evaluation
- **Frontend:** minimal single-page UI (plain HTML/JS), kept thin
- **Deploy:** Docker + Docker Compose, single AWS EC2 instance; GitHub Actions CI; email via Resend/SendGrid

---

## Core features (MVP)

1. **Tracked catalog** — a seeded set of a few hundred products across 4-5 categories, scraped from day 1. Include categories that see frequent sales so there are enough price-drop examples.
2. **Price history view** — chart per product with lowest/highest/average marked.
3. **Price-drop prediction** — likelihood of a price drop in the next 7 days. Products with too little history show an explicit "insufficient data — need N more days" state, never a fabricated prediction.
4. **Fake-discount flag** — flags when the listed MRP looks inflated relative to real historical pricing.
5. **Price alerts** — user sets a target price; email when hit.
6. **Product list view** — all tracked products with current price and prediction badge.
7. **Submit a URL (bonus)** — user adds a product; it is scraped immediately and joins the tracked set.

**Stretch (only after core is solid):** cross-site product matching, a small LLM-written plain-English summary of prediction + flag (kept minor so the project stays primarily traditional ML), category seasonality, Telegram notifications.

**Out of scope:** auto-coupons, cashback, spend analytics, browser extension, mobile app.

---

## Data strategy

- **Seed catalog:** pick ~200-500 products up front (a mix of categories and price ranges) and store the list in the repo. Scraping starts on day 1 because live history cannot be sped up later.
- **Cadence:** every tracked product re-scraped every 6 hours, jittered, with polite per-host rate limits.
- **Kaggle dataset:** used to build the feature + training pipeline from day 1, loaded into the same schema. Live data gradually replaces it. Retrain once live history clears the minimum-history gate.
- **Sale periods:** if a major sale is running, that is a good window to be collecting data (real discounts and inflated ones), but expect heavier anti-bot measures.
- **Scraping ethics:** Amazon and Flipkart terms prohibit automated scraping. Keep volume low, use public data only, no login bypass, and state in the README that this is for educational/personal use.

---

## Pipeline

**1. Ingestion.** Every scrape writes a `scrape_status` (`ok` / `parse_failed` / `blocked` / `unchanged`). Only `ok` and `unchanged` write a price row (`unchanged` reuses the last price), so `price_history` stays clean. Parse tests run against saved HTML fixtures so layout changes fail loudly in CI. Store both the selling price and the listed MRP.

**2. Storage.** Postgres tables: `products` (metadata + last scrape status), `price_history`, `predictions`, `alerts`. Redis caches hot reads (latest price, recent prediction).

**3. Features.** Rolling features per product: 7-day average, 30-day min/max, volatility, days-since-last-drop. Computed in one shared function so training and live prediction use identical logic. **Minimum-history gate:** at least 14 days and ~14 price points; younger products are `insufficient_data` and excluded from training.

**4. Modeling (offline).**
- A scheduled worker computes features, runs the trained model, and writes to `predictions`. `/predict/{id}` only reads the stored row.
- Label: "will the next-7-day minimum price be at least 5% below the current price?"
- Start with XGBoost (or logistic regression) against a naive persistence baseline ("no drop").
- Chronological split with a global cutoff date (never random splits); leave-one-product-out evaluation for generalization.
- Headline metric is PR-AUC plus precision at a reviewable threshold, not accuracy (drops are rare).
- Move to an LSTM only if it demonstrably beats the simpler model.
- Fake-discount model: a robust statistical comparison of listed MRP against the product's real price distribution. Evaluate on ~30 hand-labeled inflated-discount examples and report precision.
- MLflow logs every training run from the first one.

**5. Serving.** FastAPI: `GET /products`, `POST /products`, `GET /history/{id}`, `GET /predict/{id}`, `/alerts`. Cache checked before Postgres.

**6. Alerts.** A scheduled job every few minutes compares the latest price to active targets; on match, send email, set `notified=true`, deactivate. A unique constraint makes it idempotent (one email, even after a crash). Budget time for SPF/DKIM/reverse-DNS on EC2 or mail lands in spam.

**7. Frontend.** Submit a product, view history chart, prediction (or "insufficient data"), anomaly flag, manage alerts.

**8. Deployment.** Docker Compose locally; one EC2 instance publicly (Postgres, Redis, API, worker, beat, frontend). Single shared login via env-var credentials so the public box isn't an open scraper. CI: lint + parse-fixture tests + smoke `docker compose up`.

---

## Schedule

Live data collection starts on Day 1 and runs for the whole project. Each piece also gets its explainer doc (`docs/<piece>.md`) before moving on.

| Day | Build | Done when |
|---|---|---|
| 1 | Seed list, Postgres schema, first scraper, Celery Beat re-scraping | Scraper runs on a schedule and rows are landing in `price_history` |
| 2 | `scrape_status`, HTML fixture tests, Playwright fallback if needed; load Kaggle data into the schema; feature code | Tests pass; features computed on Kaggle data |
| 3 | XGBoost vs baseline, splits, PR-AUC, MLflow logging | One trained model beats (or honestly fails to beat) the baseline |
| 4 | FastAPI, Redis caching, prediction job, alert job | API serves stored predictions; injected price triggers exactly one email |
| 5 | MRP-based fake-discount model + hand-labeled gold set (~30 examples, labeled by me) | Precision reported on the gold set |
| 6 | Frontend + Dockerize everything | `docker compose up` gives a working UI |
| 7 | EC2 deploy, CI, email deliverability, README | Live and documented |
| Later | After ~2+ weeks of live data: retrain on live data, re-evaluate, optional LSTM | Real predictions on live products |

**Biggest schedule risk:** scraping (layout changes, blocks). Budget slack there, not in modeling. A hard block costs hours, not the project.

---

## Evaluation criteria

| Component | Bar for "works" |
|---|---|
| Price-drop model | Beats persistence baseline on PR-AUC under chronological + leave-one-product-out splits |
| Fake-discount flag | Precision reported on ~30 hand-labeled examples |
| Scrapers | Fixture tests pass; `scrape_status` visible per product; zero `parse_failed` rows in price history |
| Alerts | Injected price leads to exactly one email |
| Pipeline | Fresh clone, `docker compose up`, working UI |
| Understanding | I can explain the ML pieces from the explainer docs and answer their check questions |

---

## Honest scope note

**Demonstrates:** full pipeline thinking, handling messy scraped data, deliberate trade-offs (XGBoost before LSTM, EC2 not EKS), honest evaluation (baselines, leakage-safe splits, small gold set).

**Doesn't cover:** deep learning research depth, large-scale systems, or LLM/agentic systems.

**When describing this project (README, resume, interviews):** say plainly what I built, what the AI wrote, and what I verified myself. The data is a seeded set, not a full marketplace crawl; early live predictions are sparse by design.
