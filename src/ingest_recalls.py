"""Load NHTSA recalls for the backtest brands into SQLite.

Reads FLAT_RCL_POST_2010.txt and FLAT_RCL_PRE_2010.txt (tab-delimited, 29
fields, layout from NHTSA's RCL.txt documentation) and fills `recalls`
(see sql/schema.sql). One row per (campaign, make, model, year), the NHTSA
grain: count recalls with COUNT(DISTINCT campno). Re-running replaces the
table, so it is safe for the weekly refresh.

report_date is RCDATE, the date the manufacturer's report was received by
NHTSA. ODATE (owner notification) is later and is not used for latency.

Usage:
    python src/ingest_recalls.py data/raw/nhtsa/2026-11-01 data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

from ingest_complaints import MAKES, to_date, to_int

FILES = ("FLAT_RCL_PRE_2010.txt", "FLAT_RCL_POST_2010.txt")
N_FIELDS = 29

# 0-based positions in the flat file.
CAMPNO, MAKETXT, MODELTXT, YEARTXT, COMPNAME, RCDATE, DESC_DEFECT = 1, 2, 3, 4, 6, 15, 19

INSERT = "INSERT INTO recalls VALUES (?,?,?,?,?,?,?)"


def iter_rows(path):
    with open(path, encoding="latin-1", newline="") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != N_FIELDS:
                raise ValueError(f"{path}:{line_no}: {len(parts)} fields, expected {N_FIELDS}")
            yield parts


def main(raw_dir, db_path):
    paths = [Path(raw_dir) / name for name in FILES]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        sys.exit(f"missing in {raw_dir}: {', '.join(missing)}")
    schema = (Path(__file__).parent.parent / "sql" / "schema.sql").read_text()

    con = sqlite3.connect(db_path)
    con.executescript(schema)
    con.execute("DELETE FROM recalls")
    scanned = kept = 0
    for p in paths:
        batch = []
        for r in iter_rows(p):
            scanned += 1
            if r[MAKETXT].upper() not in MAKES:
                continue
            kept += 1
            batch.append((
                r[CAMPNO], r[MAKETXT].upper(), r[MODELTXT].upper(),
                to_int(r[YEARTXT]), r[COMPNAME], to_date(r[RCDATE]), r[DESC_DEFECT],
            ))
        con.executemany(INSERT, batch)
    con.commit()
    print(f"scanned {scanned:,} rows, kept {kept:,} -> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
