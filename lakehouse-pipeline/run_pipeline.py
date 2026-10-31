"""One entrypoint for the whole pipeline: generate/land raw -> dbt build -> data-quality report.

    python run_pipeline.py            # full run
    python run_pipeline.py --skip-raw # reuse the existing raw layer

Exit code is non-zero if any dbt model or test fails, so any scheduler (cron, GitHub Actions, Databricks
Workflows, Airflow) can treat it as a task.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DBT = ROOT / "dbt_project"
DB = ROOT / "data" / "lakehouse.duckdb"
sys.path.insert(0, str(ROOT / "ingest"))


_DBT_SNIPPET = "import sys; from dbt.cli.main import dbtRunner; sys.exit(0 if dbtRunner().invoke(sys.argv[1:]).success else 1)"


def run_dbt(*args: str) -> bool:
    # Subprocess, run from dbt_project/ (profiles.yml paths are relative to it). Isolating dbt also releases its
    # DuckDB file lock before the data-quality report opens the database.
    env = {**os.environ, "LAKEHOUSE_DB": str(DB), "LAKE_DIR": str(ROOT / "data" / "lake")}
    return subprocess.run([sys.executable, "-c", _DBT_SNIPPET, *args, "--profiles-dir", "."], cwd=DBT, env=env).returncode == 0


def dq_report() -> dict:
    con = duckdb.connect(str(DB), read_only=True)
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    report = {
        "raw_order_rows": q("select count(*) from raw.orders")[0][0],
        "distinct_orders": q("select count(distinct order_id) from raw.orders")[0][0],
        "accepted_orders": q("select count(*) from main_staging.stg_orders")[0][0],
        "quarantined_orders": dict(q("select reject_reason, count(*) from main_staging.quarantine_orders group by 1 order by 1")),
        "quarantined_lines": q("select count(*) from main_staging.quarantine_order_lines")[0][0],
        "fact_rows": q("select count(*) from main_marts.fct_sales")[0][0],
        "fact_revenue": float(q("select round(sum(revenue), 2) from main_marts.fct_sales")[0][0]),
    }
    con.close()
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-raw", action="store_true")
    a = p.parse_args()
    t0 = time.time()
    (ROOT / "data" / "lake").mkdir(parents=True, exist_ok=True)
    if not a.skip_raw:
        import load_raw
        import make_raw
        defects = make_raw.main()
        print(f"[raw] generated extracts; injected defects: {json.dumps({k: v for k, v in defects.items() if 'source' not in k})}")
        print(f"[raw] landed: {load_raw.main()}")
    ok = run_dbt("build")
    if not ok:
        print("[dbt] FAILED", file=sys.stderr)
        return 1
    rep = dq_report()
    (ROOT / "data" / "dq_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"[dq] {json.dumps(rep, indent=2)}\n[done] {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
