# Scheduling (temporary)

## What it does

Every 6 hours, Windows Task Scheduler runs `scripts/run_scrape.ps1`:

```
run_scrape.ps1
  -> dev_db.py       ensures the local Postgres is up (idempotent)
  -> scrape_all.py   queries active products, scrapes each with 2.5-5.5s jitter
  -> data/scrape.log one line per product, plus run start/end
```

`scrape_all.py` reads `products` (only `is_active = true`), dispatches to the right host adapter, and writes one observation per product. Duplicate timestamps are harmless (`ON CONFLICT DO NOTHING`).

## Why it is temporary

The plan calls for **Celery + Celery Beat + Redis**. Redis is not available without Docker, and Docker needs a reboot. This bridge starts the data clock *now*; replacing it later changes only the **trigger**, not the scraper or the data.

## Task settings (and why)

| Setting | Why |
|---|---|
| Every 6 hours | Plan cadence; frequent enough for a 7-day prediction horizon |
| Start when available | Catches up after sleep/reboot instead of silently skipping |
| Allow / don't stop on battery | Laptop may be unplugged |
| Wake the computer | Best-effort wake from sleep (not from shutdown) |
| Ignore new instances | No overlapping runs |
| 60-minute limit | A hung request can't block forever |
| Current-user context | No admin needed; **but it only runs while you are logged on** |

## Failure modes

- **Laptop off, hibernated, or logged off** → no run. The next run catches up once, not four times. The series gets a gap with real timestamps — honest, but rolling features get noisier.
- **No internet** → `blocked`, no price row.
- **Postgres down** → the wrapper starts it; `dev_db.py` clears a stale `postmaster.pid` left by a crash or reboot.
- **Flipkart blocks** → `blocked`. Repeated blocks would justify the Playwright fallback.
- **This is not a true 6-hour heartbeat.** It is best-effort on a laptop. For 24/7, move it to an always-on host.

## Inspect / remove

```powershell
Get-ScheduledTaskInfo -TaskName "PriceIntelScrape"
Get-Content data\scrape.log -Tail 20
Unregister-ScheduledTask -TaskName "PriceIntelScrape" -Confirm:$false
```

## Migrating to EC2 (or any always-on host)

1. `pg_dump` the local database, restore it on the server.
2. Run the same Docker Compose stack (Postgres, Redis, API, worker, beat).
3. Delete this scheduled task; Celery Beat takes over the trigger.
4. Scraper code and schema do not change.

## Likely interview questions

1. **Why a scheduled task instead of Celery?** It is a temporary trigger on a machine without Docker/Redis. The scraping logic is already separated, so swapping the trigger is a small change.
2. **What happens if the machine is off for a day?** That run is missed; the series gets a gap with real timestamps. Nothing is fabricated, and the next run resumes.
3. **How do you keep the data honest?** Every row is a real observation at a real timestamp; failures update status only and never write a price.
4. **How would you productionize it?** Celery Beat + Redis in Docker on an always-on host, with the database migrated via `pg_dump`/restore and monitoring on run outcomes.
