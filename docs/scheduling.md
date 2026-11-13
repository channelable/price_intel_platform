# Scheduling and monitoring

## What runs now

GitHub Actions runs `.github/workflows/scrape.yml` every 6 hours (UTC):

```
cron: "23 */6 * * *"

1. init_db             idempotent schema ensure
2. seed_products.py    add missing products from seeds/products.csv
3. scrape_all.py       scrape active products, 2.5-5.5s jitter
4. check_freshness.py  fail if the run produced stale/unusable data
5. upload scrape.log   artifact for debugging
6. Healthchecks ping   success, or /fail on failure
```

`workflow_dispatch` stays on for manual runs; `concurrency` prevents overlap.
`seed_products.py` is additive and idempotent: existing products keep their
title, price, and active flag; only the category can change.

The Windows Scheduled Task is disabled and local Postgres is stopped. This is
the only scheduler now.

## Why Actions + Neon

- No always-on machine; the laptop can sleep.
- Neon is real Postgres, free, no card, and does not pause on inactivity.
  Supabase pauses after 7 days idle; Render's free Postgres expires after 30
  days; Railway's trial volumes are deleted.
- The scraper and schema do not change. Only the trigger and DB host moved.
- Exit path: `pg_dump` Neon, restore into the Compose Postgres on EC2. No
  application rewrite.

Use the direct `DATABASE_URL` (host without `-pooler`). Pooling is for
serverless clients; this is one small batch job.

## Two monitoring layers

**Liveness — Healthchecks dead-man's switch.** The workflow pings on success
and `/fail` on failure. Check period 6h, grace 1h. A missing ping means the
workflow did not run (disabled schedule, Actions outage), not just that it
failed. Requires the `HEALTHCHECKS_PING_URL` secret; without it the pings are
no-ops. Alerts are one-shot, not per run. Use a channel you will actually see;
GitHub failure emails alone cannot report a run that never started.

**Data quality — `scripts/check_freshness.py`.** Runs after the scrape. Fails
if any active product was not attempted in the last hour, is
`blocked`/`parse_failed`, or if no active product has a current price. The 1h
threshold checks run completeness; the API `/health` will reuse
`get_freshness()` with the 8h default (6h cadence + 2h buffer) for user-facing
freshness. This is what makes a green run mean "fresh data", not just "the
cron fired".

## What breaks it

- GitHub's scheduler is best-effort: the 18:23 slot did not run; the next
  runs were 20 and 35 minutes late. Healthchecks catches a missed slot; the
  freshness check catches a run that wrote nothing useful.
- GitHub disables scheduled workflows after 60 days of repo inactivity on
  public repos. The external check catches that too.
- Flipkart blocks or changes layout → `blocked`/`parse_failed`; the job fails
  and no price row is written.
- All products unavailable → `with_price = 0`; the job fails. `unavailable` is
  a legitimate state and is kept separate from `parse_failed`.
- Neon outage or a bad secret → the job fails; Healthchecks sees `/fail` or a
  missing ping.

## Run it manually

- Actions tab → "Scrape prices" → Run workflow.
- Local: `python scripts/scrape_all.py`, then
  `python scripts/check_freshness.py --max-age-hours 1`.

## Moving to the VM later

1. `pg_dump` Neon; restore into Postgres on EC2.
2. Run the Compose stack: Postgres, Redis, API, worker, Celery Beat.
3. Celery Beat replaces the Actions cron; scraper and schema stay the same.
4. Keep the external Healthchecks check. The pinger moves into the Celery task
   or a systemd timer. Monitoring stays outside the machine it monitors.

## Likely interview questions

1. **Why Actions + Neon instead of a VM now?** No always-on machine, zero
   cost, real Postgres; scraper and schema unchanged. Migration is dump/restore
   plus a scheduler swap.
2. **What are the failure modes of Actions cron?** Best-effort delays and
   disabled schedules after 60 days of repo inactivity. Hence the external
   dead-man's switch.
3. **How do you know the data is fresh?** `check_freshness.py` fails on
   stale/blocked/no-price; `/health` will expose the same summary. Healthchecks
   covers "never ran".
4. **Why not GitHub failure emails?** They only cover runs that failed; they
   say nothing when the schedule is disabled.
5. **What changes at 100 products?** Keep run-completeness, switch to a
   failure-rate threshold, add per-product staleness to `/health`, keep the
   external check.
