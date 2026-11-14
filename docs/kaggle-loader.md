# Kaggle loader

## What it does

Loads a reproducible sample of the Kaggle *E-Commerce Product Price Tracker Dataset* into the existing `products` and `price_history` tables. It is a **development dataset**, not a production data source. Its job is to let us build and test features, labels, training, and evaluation while the live Flipkart history is still too short.

Dataset: <https://www.kaggle.com/datasets/amith1707/e-commerce-product-price-tracker-dataset>  
License: CC0-1.0.

## What was loaded

The full dataset is about 25.6M rows and 8.3 GB uncompressed. Downloading all of it is wasteful for pipeline work, so the loader uses the chronological **test split**:

- 2024-10-18 to 2024-12-30
- 74 daily observations per product/platform
- 2.6M rows, 9,980 products, 5 platforms
- no duplicate `(platform, product_id, date)` keys
- no missing prices

The default sample is **200 product IDs**, stratified across the 7 dataset categories with a fixed seed. Because one product can appear on several platforms, that becomes:

- **718 product listings** in `products`
- **53,132 price points** in `price_history`
- every listing has all 74 days

## How it maps into the schema

| Kaggle field | Our field |
|---|---|
| `product_id` + `platform` | `products.url = kaggle://<platform>/<product_id>` |
| `price` | `price_history.price` |
| `original_price` | `price_history.mrp` |
| `timestamp` | `price_history.scraped_at` (UTC) |
| — | `products.source = other` |
| — | `currency = USD` |
| — | `is_active = false` |

`source=other` plus the `kaggle://` URL prefix keeps synthetic rows clearly separated from live Amazon/Flipkart rows without a schema change.

`is_active=false` is important: the scraper selects active products. If Kaggle rows were active, the scheduled job would try to fetch `kaggle://` URLs and fail.

## Key decisions

1. **Sample, don't load everything.** 200 product IDs across 7 categories is enough to exercise the pipeline. Loading 25M rows would slow every experiment and add no value at this stage. The sample is deterministic (`--seed 42`), so results are reproducible.

2. **Mark rows inactive and tag them with a synthetic URL.** This prevents the live scraper from touching them and lets training code filter live vs Kaggle data. The alternative was adding a `KAGGLE` enum value or a separate table, which is a schema change for a temporary dataset.

3. **Ignore Kaggle's precomputed features and targets.** The dataset includes `price_7d_avg`, `target_price_7d`, `target_price_direction_7d`, etc. We compute our own features and labels so the definitions match the live pipeline and we control leakage. In particular, the target must be “≥5% drop within 7 days,” not “price 7 days ahead.”

## Commands

```bash
# One-time: install the Kaggle CLI extra
pip install -e ".[data]"

# Preview the sample without writing to Postgres
python scripts/load_kaggle.py --dry-run

# Load the default 200-product sample
python scripts/load_kaggle.py

# Change sample size or seed
python scripts/load_kaggle.py --products 500 --seed 7
```

The loader is idempotent. Re-running the same sample reports `0 inserted` because `products.url` is unique and `price_history` uses `ON CONFLICT (product_id, scraped_at) DO NOTHING`.

## What could break it

- The CSV column names or timestamp format change in a future dataset version.
- A sampled product has fewer than 14 days of history. The feature code must mark it `insufficient_data`.
- Prices are USD and synthetic; they do not reflect live Flipkart pricing, promotions, or stock behaviour.
- The split covers only ~2.5 months, so 30-day features have limited warm-up and seasonal coverage is narrow.

## Likely interview questions

**Why not train on the full Kaggle dataset?**  
The full file is 8.3 GB and 25.6M rows. A stratified 200-product sample is enough to validate the pipeline and keeps iteration fast. If we needed more data for a final development model, we could raise `--products` without changing code.

**Why not use the dataset's existing target column?**  
Its target is “price 7 days ahead,” which is a different task and could leak information if used carelessly. Our target is explicitly “at least a 5% drop at any point in the next 7 days,” computed from future prices only for the label, never for features.

**Why keep Kaggle products inactive?**  
The live scraper processes every active product. Synthetic `kaggle://` URLs are not fetchable, so activating them would create false scrape failures and pollute freshness monitoring.

**How do you avoid mixing Kaggle and live data?**  
Kaggle rows use `source=other` and a `kaggle://<platform>/<id>` URL. Training and evaluation can filter on that prefix. The final model is retrained on live data and evaluated on a live chronological holdout, not on Kaggle metrics.
