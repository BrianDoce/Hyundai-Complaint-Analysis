"""Load NHTSA complaints for the backtest brands into SQLite.

Reads the COMPLAINTS_RECEIVED_*.zip files directly and fills `complaints`
(see sql/schema.sql). Re-running replaces the table, so it is safe for the
weekly refresh.

Usage:
    python src/ingest_complaints.py data/raw/nhtsa/2026-10-24 data/recall_radar.db
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from filter_complaints import iter_rows

# Backtest brands from the project plan, plus Genesis (Hyundai Motor Group).
MAKES = {"HYUNDAI", "KIA", "GENESIS", "TOYOTA", "HONDA", "TESLA"}

INSERT = "INSERT INTO complaints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"


def to_date(s):
    """NHTSA dates are YYYYMMDD; blank or malformed -> NULL."""
    try:
        return datetime.strptime(s, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def to_int(s):
    try:
        return int(s)
    except ValueError:
        return None


def main(raw_dir, db_path):
    zips = sorted(Path(raw_dir).glob("COMPLAINTS_RECEIVED_*.zip"))
    if not zips:
        sys.exit(f"no COMPLAINTS_RECEIVED_*.zip in {raw_dir}")
    schema = (Path(__file__).parent.parent / "sql" / "schema.sql").read_text()

    con = sqlite3.connect(db_path)
    con.executescript(schema)
    con.execute("DELETE FROM complaints")
    scanned = kept = 0
    for z in zips:
        batch = []
        for r in iter_rows(z):
            scanned += 1
            if r["MAKETXT"].upper() not in MAKES:
                continue
            kept += 1
            batch.append((
                r["ODINO"], r["MAKETXT"].upper(), r["MODELTXT"].upper(),
                to_int(r["YEARTXT"]), to_date(r["LDATE"]), to_date(r["FAILDATE"]),
                r["COMPDESC"], r["CRASH"], r["FIRE"], to_int(r["INJURED"]),
                to_int(r["DEATHS"]), to_int(r["MILES"]), r["CDESCR"], z.name,
            ))
        con.executemany(INSERT, batch)
    con.commit()
    print(f"scanned {scanned:,} rows, kept {kept:,} -> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
