# lakehouse-pipeline

Messy data in → tested, dimensional, Parquet-backed marts out. **dbt + DuckDB**, data-quality gates, quarantine
instead of silent drops, scheduled in CI.

```
raw CSVs (messy)      bronze (all text)       silver (typed, deduped, validated)        gold (star schema, Parquet)
 orders.csv       ─►   raw.orders         ─►   orders_validated ─► stg_orders       ─►   fct_sales ──┬─ dim_customer
 order_lines.csv       raw.order_lines         │                   quarantine_orders        │       ├─ dim_track
 tracks.csv            raw.tracks              stg_order_lines ─► quarantine_order_lines    │       └─ dim_date
 customers.csv         raw.customers           stg_tracks, stg_customers                    └─ agg_revenue_monthly
```

```bash
pip install -r requirements.txt pytest
python run_pipeline.py        # ingest -> dbt build (52 nodes, 39 data tests) -> data-quality report
pytest                        # runs the pipeline, then checks results against the clean source (9 tests)
```

## The mess, and what the pipeline does about it

Chinook is clean, so defects are injected with a fixed seed ([ingest/make_raw.py](ingest/make_raw.py)). Because the
clean original exists, the pipeline's output can be checked against **ground truth**, not just against itself.

| Defect (count) | Handling |
|---|---|
| Re-delivered duplicate rows (13) | Dedup on `order_id`, latest `loaded_at` wins |
| 3 date formats + garbage (`N/A`…, 10) | Multi-format parse; unparseable → **quarantine**, never guessed |
| Future dates, `2099-…` (3) | Quarantine `future_date` |
| `"$1,234.56"` totals / `$` prices (104 / 216) | `parse_money` macro |
| Missing total (10), null customer (4) | Quarantine `missing_total` / `missing_customer` |
| Country aliases/case/whitespace (`U.S.A.`, ` USA `, `united states`…) | `country_aliases` seed + title-case |
| Orphan track ids (18 lines) | Kept in staging so order totals reconcile; excluded from the fact; reported in `quarantine_order_lines` |
| Null genre, `m:ss` durations | `Unknown`; normalised to ms |
| PII (email/phone/address) | Never ingested (tested) |

Result of the last run (`data/dq_report.json`): 425 raw rows → 412 distinct orders → **385 accepted + 27
quarantined** (3 future_date, 4 missing_customer, 10 missing_total, 10 unparseable_date); 2,038 fact rows, $2,095.62.

## Data modelling

Star schema, grain stated in `schema.yml`: `fct_sales` = one row per accepted order line with a known track.
Keys are the source integer ids (Type-1 dimensions, no history) — a deliberate simplification. `dim_date` is
generated; `agg_revenue_monthly` is a pre-aggregate. Marts are `external` models → real Parquet files in `data/lake/`.

## Data quality — three layers

1. **dbt generic tests** (not_null, unique, relationships to every dimension, accepted_values, custom
   `expression_is_true`) on every model.
2. **dbt singular tests** that encode invariants: every raw order id lands in *exactly one* of accepted/quarantine;
   cleaned order total = sum of cleaned lines; fact + quarantined revenue = staged revenue.
3. **Oracle tests** ([tests/test_pipeline.py](tests/test_pipeline.py)) against the original clean database: parsed dates
   equal true dates, totals/countries equal truth, quarantine set **equals** the independently computed defective set,
   fact revenue equals source revenue, pipeline is idempotent.

Tests were shown to fail: removing the `DD/MM/YYYY` parser turned the build red (dbt tests) and broke the oracle
comparison; restoring it returned to 9/9.

## Scheduling

[pipeline.yml](.github/workflows/pipeline.yml): runs on push/PR and **daily at 05:00 UTC**; fails the run if any model or
test fails; uploads Parquet + DQ report. `run_pipeline.py` exits non-zero on failure, so the same command works as a
Databricks Workflows / Airflow / cron task.

## What this is not (honest scope)

- **Not deployed to Databricks.** Community Edition has no SQL warehouse or API tokens, which `dbt-databricks`
  needs, so dbt can't target it. Porting means switching the adapter and swapping `strptime`/`regexp_replace` dialect
  bits on a paid/trial workspace; the model structure and tests carry over. Nothing here was run on Databricks.
- Not tested on a schedule yet: the cron is configured but this repo has not been pushed to GitHub, so no scheduled run
  has happened. Tests ran locally (Windows, Python 3.11, dbt 1.12, DuckDB).
- Messiness is synthetic (seeded injection into real data), which makes defects *known* but not necessarily
  representative. Chinook is small (≈2k lines); no performance claims.
- Full-refresh only: no incremental models, no SCD2, no late-arriving-data handling.
- Date format `DD/MM/YYYY` is assumed (a real source needs this confirmed; `01/02/2021` is ambiguous).
