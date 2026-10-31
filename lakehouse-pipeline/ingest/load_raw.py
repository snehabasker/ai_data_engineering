"""Land raw CSVs into DuckDB schema `raw`, every column as text (no silent coercion at the bronze layer)."""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "lakehouse.duckdb"
TABLES = ["orders", "order_lines", "tracks", "customers"]


def main() -> dict[str, int]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("create schema if not exists raw")
    counts = {}
    for t in TABLES:
        path = (RAW / f"{t}.csv").as_posix()
        con.execute(f"create or replace table raw.{t} as select * from read_csv('{path}', all_varchar=true, header=true)")
        counts[t] = con.execute(f"select count(*) from raw.{t}").fetchone()[0]
    con.close()
    return counts


if __name__ == "__main__":
    print(main())
