# Seed catalog

## What it does

`seeds/products.csv` is the tracked product catalog: one row per product with
`category`, `source`, and `url`. `scripts/seed_products.py` syncs it into the
`products` table before every scrape. The sync is additive and idempotent:

- a URL that is not in the database is inserted as active;
- an existing URL only has its category updated;
- titles, prices, statuses, and manual `is_active` changes are preserved.

The catalog is deliberately finite: a curated set of products plus user-submitted
URLs later, not a full marketplace crawl.

`scripts/collect_seed_urls.py` is a one-off curation helper. It fetches one public
Flipkart search page per category, extracts product links, canonicalizes them, and
merges new candidates into the CSV. It is not part of the scheduled pipeline and
never writes to the database.

## How it fits

```
seeds/products.csv -> seed_products.py -> products (active)
                                      -> scrape_all.py -> price_history
```

The catalog is the cold-start fix: the scraper has products to watch from day 1,
so history accumulates before the model exists. The scheduled workflow only runs
the sync and scraper; the collector is a manual tool for growing the catalog.

## Current catalog

As of 2026-11-13: **103 rows** — 100 new candidates plus the 3 original products.

| Category | Rows | Notes |
|---|---:|---|
| `smartphones` | 21 | budget and flagship; some colour/storage variants |
| `laptops` | 21 | budget Chromebooks through MacBook/Surface |
| `audio` | 20 | mostly budget earbuds/neckbands |
| `wearables` | 21 | Apple/Noise/Fastrack/Realme plus marketplace brands |
| `tv` | 20 | 32–85 inch; LG/Samsung-heavy |

The first full scrape of this catalog produced 99 `ok`, 3 `unchanged`, 1
`unavailable`, and 0 `blocked`/`parse_failed`. The unavailable product (Vivo T5
Lite) stayed unavailable on retry, so it is a real stock state, not a parser
failure.

## Key decisions

1. **CSV in the repo, not an admin UI.** The list is reviewable in a diff,
   versioned with the code, and needs no extra service. *Alternative:* manage the
   catalog directly in Postgres — fewer files, but changes become invisible and
   unreviewable.
2. **Additive sync, never delete on absence.** Removing a row from the CSV does
   not deactivate the product; this avoids an accidental mass-deactivation when a
   file is truncated. *Trade-off:* deactivation is a deliberate manual/DB step.
3. **Search pages plus slug dedupe for collection.** Five public search requests
   are enough to seed 100 products and are kinder than crawling category pages
   and pagination. Dedupe by the path before `/p/` because the same listing can
   appear with different Flipkart `pid`s. *Alternative:* a full category crawl —
   more coverage, more requests, more junk.
4. **100 now, grow later.** At the current 2.5–5.5s jitter, 100 products take
   roughly 8–10 minutes, comfortably inside the 30-minute workflow timeout.
   ~200–500 products need a shorter delay or sharded runs.

## What would break it

- **Search-page markup changes.** The one-off collector returns no candidates;
  the scheduled scraper is unaffected because it never uses search pages.
- **Bad curation.** A wrong category or an accessory in the CSV still parses, but
  pollutes the catalog. That is why the CSV is reviewed before seeding.
- **Duplicate PIDs/slugs.** `seed_products.py` rejects duplicate canonical URLs;
  the collector dedupes by product slug.
- **Removed products.** The sync does not deactivate absent rows; a stale product
  keeps being scraped until `is_active` is set false.
- **Out of stock.** Recorded as `unavailable`, with no price row — a real gap, not
  a fabricated observation.

## Tests

`tests/test_discovery.py` covers relative/absolute links, HTML-escaped URLs,
tracking-parameter canonicalization, duplicate PIDs for the same slug, and
non-Flipkart links. `pytest -q` and `ruff check` are the gate.

## Likely interview questions

1. **Why a seeded catalog instead of only user submissions?** Predictions need
   history; a fixed seed gives the scraper something to watch from day 1 and
   avoids a cold start.
2. **Why keep the catalog in a CSV?** It is small, diffable, and versioned with
   the code. A database table would be more flexible but hides changes.
3. **What happens if you remove a product from the CSV?** Nothing; the sync is
   additive. Deactivation is explicit so a truncated file cannot wipe the catalog.
4. **Why dedupe by slug rather than URL?** Flipkart can serve the same listing
   with different `pid`s; the slug before `/p/` is the stable product identity.
5. **Why not crawl all of Flipkart?** Scope and politeness. This is a seeded
   tracker, not a marketplace mirror; the catalog grows deliberately.
