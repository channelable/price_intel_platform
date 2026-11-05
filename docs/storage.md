# Storage

## What it does

Postgres is the system of record. Four tables:

| Table | Holds | Written by |
|---|---|---|
| `products` | The tracked catalog: URL, source, title, category, last scrape status | Seed loader, scraper |
| `price_history` | One row per successful scrape: selling price + listed MRP + timestamp | Scraper |
| `predictions` | Model output per product: probability, label, model version, and an explicit `insufficient_data` state | Prediction job |
| `alerts` | User target prices and whether they were notified | API, alert job |

`src/price_intel/db/models.py` defines them as SQLAlchemy classes; `python -m price_intel.db.init_db` creates them. Redis (Day 4) sits *in front* as a cache; Postgres stays the source of truth.

## Key decisions

1. **Money is `NUMERIC(12,2)`, never `FLOAT`.** Floats can't represent 0.1 exactly, so round-trips drift. The alternative — storing integer paise — is also exact but makes every query and fixture noisier. Numeric is the conventional middle ground.
2. **`UNIQUE (product_id, scraped_at)` on `price_history`.** A re-run, retry, or crash mid-batch must not create a duplicate price point. Doing this in the app is racy; the database is the only place that can enforce it atomically. The scraper will use `INSERT ... ON CONFLICT DO NOTHING`.
3. **MRP lives on each price row, not on `products`.** Listed MRP changes over time, and the fake-discount flag is exactly about comparing today's MRP to *past* real prices. One MRP per product would destroy that history.
4. **`native_enum=False` (VARCHAR + CHECK) instead of Postgres `ENUM`.** Native enums require `ALTER TYPE` to add a value, which is awkward mid-migration. The check constraint is easy to evolve and keeps the schema portable.
5. **"Not enough data" is a first-class state.** `predictions.status` is `ok` or `insufficient_data`, with `days_of_history` recorded. This makes it structurally impossible to serve a fabricated probability for a new product.
6. **`price_at_prediction` is snapshotted on the prediction row.** Evaluation later shouldn't have to reconstruct "what was the price when we predicted?" from history and risk getting it wrong.

## What would break it

- **Schema drift.** `create_all()` creates missing tables but will **not alter existing ones**. Until we add Alembic (before deploy, or once the schema settles), changing a column means recreating the dev database. This is the main known limitation.
- **`scraped_at` collisions.** Two writes in the same instant hit the unique constraint. The scraper must handle that as "already recorded", not crash.
- **Timezone bugs.** All timestamps are `TIMESTAMPTZ`; inserting naive datetimes silently assumes the server's timezone. Always use `datetime.now(UTC)`.
- **Cascade deletes are permanent.** `ON DELETE CASCADE` means deleting a product erases its entire price history. Intentional, but it means `products` must never be deleted casually.
- **This dev database is not the real deployment.** `pgserver` is a no-admin stand-in; the deployed system uses the Docker Postgres, and only that path is exercised by CI.

## Local dev (temporary, no Docker)

Until Docker is installed:

```powershell
.\.venv\Scripts\python.exe scripts\dev_db.py   # prints a DATABASE_URL and leaves Postgres running
$env:DATABASE_URL = "<that url>"
.\.venv\Scripts\python.exe -m price_intel.db.init_db
```

Data persists in `data/pgdata` (gitignored). Delete that folder to start clean.

## Likely interview questions

1. **Why Postgres rather than SQLite?** SQLite would handle this data size, but the app has concurrent writers (API, workers, beat) and is deployed across processes on EC2. Postgres gives proper concurrent writes, real constraints, and a deployment story.
2. **How do you stop duplicate price points?** A unique constraint on `(product_id, scraped_at)`, with the scraper using `ON CONFLICT DO NOTHING`; the database enforces it even under retries.
3. **Why keep MRP per row?** It changes over time, and the fake-discount flag compares current MRP to historical real prices.
4. **How is "insufficient data" handled?** A `status` column plus `days_of_history`; the API returns that state instead of inventing a prediction.
5. **What's missing before production?** Migrations (Alembic) and the Docker Postgres path. The current `create_all` approach cannot evolve a live schema.
