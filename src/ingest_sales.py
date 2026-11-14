"""Load hand-collected US unit sales by model into the `sales` table.

Reads data/sales/us_sales.csv (make, model, calendar_year, units_sold,
source_url, is_estimate). Model names are matched to NHTSA's spelling by
upper-casing, so write them as NHTSA does (SANTA FE, IONIQ 5). Every row needs
a source_url; Tesla rows (no model-level reporting) must set is_estimate=1.
Re-running replaces the table.

Checks, printed as warnings (rows are still loaded):
  - sales models with no complaints, and models with >= 100 complaints and no
    sales rows (a coverage to-do list)
When collecting, verify that a source page's model rows sum to its printed
total before adding them; a misread row silently skews complaints per sale.

Usage:
    python src/ingest_sales.py data/recall_radar.db [data/sales/us_sales.csv]
"""
import csv
import sqlite3
import sys
from pathlib import Path

from ingest_complaints import MAKES

DEFAULT_CSV = Path(__file__).parent.parent / "data" / "sales" / "us_sales.csv"


def read_rows(path):
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8") as f:
        for n, r in enumerate(csv.DictReader(f), 2):
            make, model = r["make"].strip().upper(), r["model"].strip().upper()
            year, units = int(r["calendar_year"]), int(r["units_sold"])
            est = int(r["is_estimate"] or 0)
            if make not in MAKES:
                raise ValueError(f"{path}:{n}: unknown make {make!r}")
            if not r["source_url"].strip():
                raise ValueError(f"{path}:{n}: {make} {model} {year} has no source_url")
            if make == "TESLA" and not est:
                raise ValueError(f"{path}:{n}: Tesla rows must have is_estimate=1")
            if units < 0 or not 1980 <= year <= 2100:
                raise ValueError(f"{path}:{n}: implausible year/units")
            if (make, model, year) in seen:
                raise ValueError(f"{path}:{n}: duplicate {make} {model} {year}")
            seen.add((make, model, year))
            rows.append((make, model, year, units, r["source_url"].strip(), est))
    return rows


def main(db_path, csv_path=DEFAULT_CSV):
    rows = read_rows(csv_path)
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS sales")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    print(f"{len(rows):,} sales rows ({len({r[:2] for r in rows})} models, "
          f"{min(r[2] for r in rows)}-{max(r[2] for r in rows)}) -> {db_path}")

    have = {r[:2] for r in rows}
    cm = {(m, mo) for m, mo, n in con.execute(
        "SELECT make, model, COUNT(DISTINCT odino) FROM complaints GROUP BY 1, 2 HAVING COUNT(DISTINCT odino) >= 100")}
    makes_loaded = {m for m, _ in have}
    missing = sorted(k for k in cm if k not in have and k[0] in makes_loaded)
    unmatched = sorted(k for k in have if k not in {(m, mo) for m, mo in con.execute("SELECT DISTINCT make, model FROM complaints")})
    print(f"models with >= 100 complaints and no sales rows (brands loaded so far): {len(missing)}")
    if unmatched:
        print("sales models that match no complaint model (check spelling):", unmatched)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(*sys.argv[1:])
