"""End-to-end checks against an *independent oracle*: the original clean Chinook SQLite file.

dbt's own tests prove internal consistency; these prove the cleaned data equals the truth the mess was derived from.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "Chinook_Sqlite.sqlite"
DB = ROOT / "data" / "lakehouse.duckdb"


@pytest.fixture(scope="session")
def built():
    r = subprocess.run([sys.executable, str(ROOT / "run_pipeline.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    con = duckdb.connect(str(DB), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def truth():
    return sqlite3.connect(SRC)


def test_pipeline_succeeds_and_dbt_tests_ran(built):
    assert built.execute("select count(*) from main_marts.fct_sales").fetchone()[0] > 2000


def test_dates_parse_to_the_true_dates(built, truth):
    """DD/MM/YYYY vs ISO vs 'Mon D, YYYY' must all resolve to the original invoice date."""
    want = {i: d[:10] for i, d in truth.execute("select InvoiceId, InvoiceDate from Invoice")}
    got = {i: str(d) for i, d in built.execute("select order_id, order_date from main_staging.stg_orders").fetchall()}
    assert got and all(want[i] == d for i, d in got.items())


def test_totals_and_countries_match_truth(built, truth):
    want = {i: (round(t, 2), c) for i, t, c in truth.execute("select InvoiceId, Total, BillingCountry from Invoice")}
    for oid, total, country in built.execute("select order_id, total, billing_country from main_staging.stg_orders").fetchall():
        assert (float(total), country) == want[oid], oid


def test_every_order_is_accounted_for_and_dupes_removed(built, truth):
    n_true = truth.execute("select count(*) from Invoice").fetchone()[0]
    acc = built.execute("select count(*) from main_staging.stg_orders").fetchone()[0]
    quar = built.execute("select count(*) from main_staging.quarantine_orders").fetchone()[0]
    assert acc + quar == n_true
    assert built.execute("select count(*) - count(distinct order_id) from main_staging.stg_orders").fetchone()[0] == 0


def _blank(x):  # DuckDB's CSV reader turns empty fields into NULL
    return x is None or x.strip() == ""


def test_quarantine_is_exactly_the_defective_orders_with_the_right_reason(built):
    """Set equality against an independent definition of 'defective', so neither misses nor false alarms pass."""
    quarantined = dict(built.execute("select order_id, reject_reason from main_staging.quarantine_orders").fetchall())
    defective = {}
    for oid, cust, date, total in built.execute("select cast(order_id as int), customer_id, order_date, total from raw.orders").fetchall():
        reason = ("missing_customer" if _blank(cust) else "unparseable_date" if date in ("N/A", "unknown", "00/00/0000")
                  else "future_date" if date.startswith("2099") else "missing_total" if _blank(total) else None)
        if reason:
            defective[oid] = reason
    assert len(defective) >= 20, "oracle is vacuous: expected the seeded defects to be present"
    assert quarantined == defective


def test_fact_revenue_equals_truth_for_accepted_orders_excluding_orphans(built, truth):
    ids = [r[0] for r in built.execute("select order_id from main_staging.stg_orders").fetchall()]
    orphans = {r[0] for r in built.execute("select line_id from main_staging.quarantine_order_lines").fetchall()}
    want = sum(price * qty for lid, oid, price, qty in truth.execute("select InvoiceLineId, InvoiceId, UnitPrice, Quantity from InvoiceLine")
               if oid in set(ids) and lid not in orphans)
    got = float(built.execute("select sum(revenue) from main_marts.fct_sales").fetchone()[0])
    assert got == pytest.approx(want, abs=0.01)


def test_pii_is_not_ingested(built):
    cols = {r[0] for r in built.execute("select column_name from information_schema.columns").fetchall()}
    assert not cols & {"email", "phone", "fax", "address", "postal_code"}


def test_marts_are_written_as_parquet():
    files = {p.name for p in (ROOT / "data" / "lake").glob("*.parquet")}
    assert {"fct_sales.parquet", "dim_customer.parquet", "dim_track.parquet", "dim_date.parquet"} <= files


def test_pipeline_is_idempotent(built):
    before = built.execute("select count(*), round(sum(revenue), 2) from main_marts.fct_sales").fetchone()
    built.close()
    assert subprocess.run([sys.executable, str(ROOT / "run_pipeline.py")], capture_output=True).returncode == 0
    con = duckdb.connect(str(DB), read_only=True)
    assert con.execute("select count(*), round(sum(revenue), 2) from main_marts.fct_sales").fetchone() == before
    con.close()
