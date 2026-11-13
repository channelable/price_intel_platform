# Scraping

## What it does

Turns a product URL into rows, once per run:

```
fetch_html(url)  ->  parse_product(html)  ->  ScrapedProduct  ->  store
```

- `flipkart.py` fetches the page and parses two machine-readable blocks:
  - **JSON-LD** (`@type: Product`) → title, SKU, selling price, currency, stock status.
  - **`__INITIAL_STATE__` → `"ppd"`** → the listed MRP, which JSON-LD does not include.
- `runner.py` upserts the product, compares the new price to the last stored price, writes one `price_history` row, and sets `products.last_scrape_status`.

No JavaScript execution and no browser are needed for these pages; the data ships inside the HTML.

## How it fits

This is the **only** way data enters the system. There is no historical feed to download, so every scheduled run appends one observation per product. Failed attempts never write to `price_history` — they only update the product's status.

## Key decisions

1. **Parse embedded JSON, not CSS selectors.** Flipkart's class names are generated and churn; JSON-LD is a public, documented shape used for SEO and rarely changes. *Alternative:* BeautifulSoup over DOM classes — faster to write, breaks more often. Playwright is the fallback if the JSON ever disappears, but it is much heavier than one HTTP request.
2. **Record flat prices as `unchanged`, don't skip them.** A 7-day average computed only over change-days is biased toward exactly the volatile days. Regular observations keep rolling features honest. *Cost:* a few thousand extra rows — irrelevant.
3. **A status per attempt: `ok` / `unchanged` / `parse_failed` / `blocked` / `unavailable`.** The first four are in the plan; `unavailable` was added because an out-of-stock page is not a broken layout, and treating it as `parse_failed` would send us chasing bugs that don't exist.
4. **Canonical URL.** Tracking parameters are stripped but Flipkart's `pid` is kept, so the same product copied from different searches still matches the `UNIQUE (url)` constraint.
5. **Be polite.** Browser user-agent, `Accept-Language: en-IN`, 2.5–5.5s jitter between products, retries with backoff on 429/5xx, and `403/429` map to `blocked` rather than pretending to succeed.

## What would break it

- **Layout/schema change.** If Flipkart changes the JSON-LD or `ppd` shape, we get `ParseError` → `parse_failed`, and **no bad price row**. The fixture test then needs a refreshed fixture. This is the intended failure mode: loud, not silent.
- **The MRP regex is the weakest link.** It reads `"ppd":{...}` from the inline state. If that moves, MRP becomes `NULL` while price still parses; the fake-discount model must tolerate missing MRP.
- **Anti-bot.** 403/429/captcha → `blocked`. If it persists, the plan's Playwright fallback becomes necessary.
- **Pincode / personalized pricing.** Flipkart can vary price by location; a fixed location and user-agent reduce noise but don't remove it.
- **Out of stock.** `unavailable`, no price row — a deliberate gap in the series, not a fabricated price.
- **Duplicate writes.** Prevented by `UNIQUE (product_id, scraped_at)` plus `ON CONFLICT DO NOTHING`.

## Tests

`tests/test_flipkart_parser.py` parses one fixture per supported category
(`tests/fixtures/flipkart/`), rejects a page with no JSON-LD, and checks URL
canonicalization. The smartphone fixture is a full real page; the laptop, audio,
wearable, and TV fixtures are minimized to the real Product JSON-LD fields and
MRP block the parser uses. That keeps the repo small and avoids committing page
nonces or review text, while the full-page case stays covered. Run with
`pytest -q`.

## Likely interview questions

1. **Where does the price history come from?** Only from scheduled scrapes going forward. Nothing can backfill it; the series starts the day the scraper starts.
2. **Why JSON-LD instead of HTML classes?** It is structured, stable, and designed for machines; class names are generated and change without notice.
3. **Why store unchanged prices?** Rolling features need a regular series; skipping flat days biases averages toward volatile ones.
4. **What happens when the page layout changes?** Parsing raises, status becomes `parse_failed`, and no row is written — so history stays clean. The fixture test is the early-warning system.
5. **How are duplicate price points prevented?** A unique `(product_id, scraped_at)` constraint and `ON CONFLICT DO NOTHING`.
