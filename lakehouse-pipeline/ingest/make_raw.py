"""Produce *messy* raw CSV extracts from the Chinook dataset.

Chinook itself is clean, so realistic defects are injected with a fixed seed (reproducible) and counted into
`data/raw/defects.json`. That manifest is the ground truth the pipeline's quarantine/tests are checked against.

Injected defects
  orders       duplicates (re-delivered rows), 4 date formats + unparseable + future dates, "$1,234.56" totals,
               missing totals, null customer_id, country casing/whitespace/aliases
  order_lines  "$"-prefixed prices, orphan track_ids
  tracks       flattened album/artist/genre extract, null genre, duration as "m:ss" strings
  customers    padded names, messy country
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import random
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "Chinook_Sqlite.sqlite"
RAW = ROOT / "data" / "raw"
URL = "https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
USA_VARIANTS = ["usa", "U.S.A.", "United States", " USA ", "Usa"]


def messy_country(rng: random.Random, c: str, counts: dict) -> str:
    if c == "USA" and rng.random() < 0.5:
        counts["country_alias"] += 1
        return rng.choice(USA_VARIANTS)
    r = rng.random()
    if r < 0.06:
        counts["country_case_ws"] += 1
        return f"  {c.upper()}"
    if r < 0.10:
        counts["country_case_ws"] += 1
        return c.lower() + " "
    return c


def messy_date(rng: random.Random, ts: str, counts: dict) -> str:
    d = dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    r = rng.random()
    if r < 0.60:
        return ts
    if r < 0.80:
        counts["date_dmy"] += 1
        return d.strftime("%d/%m/%Y")
    if r < 0.95:
        counts["date_mon"] += 1
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    counts["date_garbage"] += 1
    return rng.choice(["N/A", "unknown", "00/00/0000"])


def main() -> dict:
    rng = random.Random(42)
    RAW.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        SRC.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, SRC)
    con = sqlite3.connect(SRC)
    counts: dict[str, int] = {k: 0 for k in [
        "orders_source", "order_dupes", "date_dmy", "date_mon", "date_garbage", "date_future", "total_dollar",
        "total_missing", "customer_null", "country_alias", "country_case_ws", "lines_source", "price_dollar",
        "orphan_track_lines", "tracks_source", "genre_null", "duration_mmss", "customers_source"]}

    # ---- orders
    orders = con.execute("select InvoiceId, CustomerId, InvoiceDate, BillingCountry, Total from Invoice order by InvoiceId").fetchall()
    counts["orders_source"] = len(orders)
    out, future_budget = [], 3
    for oid, cid, ts, country, total in orders:
        date = messy_date(rng, ts, counts)
        if future_budget and rng.random() < 0.02:
            date, future_budget = "2099-01-01 00:00:00", future_budget - 1
            counts["date_future"] += 1
        t = f"{total:.2f}"
        r = rng.random()
        if r < 0.25:
            t, counts["total_dollar"] = f"${total:,.2f}", counts["total_dollar"] + 1
        elif r < 0.28:
            t, counts["total_missing"] = "", counts["total_missing"] + 1
        c = "" if rng.random() < 0.02 else cid
        counts["customer_null"] += c == ""
        row = [oid, c, date, messy_country(rng, country, counts), t, "2025-12-31T00:00:00"]
        out.append(row)
        if rng.random() < 0.04:  # re-delivered row, loaded later
            counts["order_dupes"] += 1
            out.append(row[:5] + ["2026-01-01T00:00:00"])
    rng.shuffle(out)
    _write("orders.csv", ["order_id", "customer_id", "order_date", "billing_country", "total", "loaded_at"], out)

    # ---- order lines
    lines = con.execute("select InvoiceLineId, InvoiceId, TrackId, UnitPrice, Quantity from InvoiceLine").fetchall()
    counts["lines_source"] = len(lines)
    out = []
    for lid, oid, tid, price, qty in lines:
        p = f"{price:.2f}"
        if rng.random() < 0.10:
            p, counts["price_dollar"] = f"${price:.2f}", counts["price_dollar"] + 1
        if rng.random() < 0.01:
            tid, counts["orphan_track_lines"] = 999999, counts["orphan_track_lines"] + 1
        out.append([lid, oid, tid, p, qty])
    _write("order_lines.csv", ["line_id", "order_id", "track_id", "unit_price", "quantity"], out)

    # ---- tracks (denormalised extract)
    tracks = con.execute("""select t.TrackId, t.Name, al.Title, ar.Name, g.Name, mt.Name, t.Milliseconds, t.UnitPrice
        from Track t left join Album al on al.AlbumId=t.AlbumId left join Artist ar on ar.ArtistId=al.ArtistId
        left join Genre g on g.GenreId=t.GenreId left join MediaType mt on mt.MediaTypeId=t.MediaTypeId order by t.TrackId""").fetchall()
    counts["tracks_source"] = len(tracks)
    out = []
    for tid, name, album, artist, genre, media, ms, price in tracks:
        if rng.random() < 0.03:
            genre = None
        counts["genre_null"] += genre is None
        dur = str(ms)
        if rng.random() < 0.05:
            dur, counts["duration_mmss"] = f"{ms // 60000}:{(ms // 1000) % 60:02d}", counts["duration_mmss"] + 1
        out.append([tid, name, album, artist, genre or "", media, dur, f"{price:.2f}"])
    _write("tracks.csv", ["track_id", "track_name", "album_title", "artist_name", "genre", "media_type", "duration", "unit_price"], out)

    # ---- customers (no email/phone/address: PII is deliberately not ingested)
    cust = con.execute("select CustomerId, FirstName, LastName, City, Country from Customer order by CustomerId").fetchall()
    counts["customers_source"] = len(cust)
    out = [[cid, f" {fn}", f"{ln}  " if rng.random() < 0.3 else ln, city, messy_country(rng, country, counts)] for cid, fn, ln, city, country in cust]
    _write("customers.csv", ["customer_id", "first_name", "last_name", "city", "country"], out)

    (RAW / "defects.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


def _write(name: str, header: list[str], rows: list[list]) -> None:
    with (RAW / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
