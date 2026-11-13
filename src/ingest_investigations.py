"""Load NHTSA investigations for the backtest brands into SQLite.

Reads FLAT_INV.txt (tab-delimited, 11 fields, layout from NHTSA's INV.txt
documentation) and fills `investigations` (see sql/schema.sql). One row per
(investigation, make, model, year): count with COUNT(DISTINCT nhtsa_id).
Re-running replaces the table, so it is safe for the weekly refresh.

open_date is ODATE and close_date is CDATE. campno, when present, is the
recall campaign the investigation led to and joins to recalls.campno.

Usage:
    python src/ingest_investigations.py data/raw/nhtsa/2026-11-01 data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

from ingest_complaints import MAKES, to_date, to_int

N_FIELDS = 11

# 0-based positions in the flat file.
NHTSA_ID, MAKE, MODEL, YEAR, COMPNAME, ODATE, CDATE, CAMPNO, SUBJECT = 0, 1, 2, 3, 4, 6, 7, 8, 9

INSERT = "INSERT INTO investigations VALUES (?,?,?,?,?,?,?,?,?)"


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
    path = Path(raw_dir) / "FLAT_INV.txt"
    if not path.exists():
        sys.exit(f"no FLAT_INV.txt in {raw_dir}")
    schema = (Path(__file__).parent.parent / "sql" / "schema.sql").read_text()

    con = sqlite3.connect(db_path)
    # Drop first so a table created from an older schema picks up new columns.
    con.execute("DROP TABLE IF EXISTS investigations")
    con.executescript(schema)
    scanned = 0
    batch = []
    for r in iter_rows(path):
        scanned += 1
        if r[MAKE].upper() not in MAKES:
            continue
        batch.append((
            r[NHTSA_ID], r[MAKE].upper(), r[MODEL].upper(), to_int(r[YEAR]),
            r[COMPNAME].strip(), to_date(r[ODATE]), to_date(r[CDATE]),
            r[CAMPNO] or None, r[SUBJECT],
        ))
    con.executemany(INSERT, batch)
    con.commit()
    print(f"scanned {scanned:,} rows, kept {len(batch):,} -> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2 + 1:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
