"""Filter NHTSA complaint flat files down to the E-GMP / ICCU vehicles.

Reads the COMPLAINTS_RECEIVED_*.zip files directly (no extraction) and writes
one CSV row per (complaint, component), matching the NHTSA grain. Count
complaints with DISTINCT odino, not rows.

Usage:
    python src/filter_complaints.py data/raw/nhtsa/2026-10-24 data/interim/complaints_egmp.csv
"""
import csv
import io
import sys
import zipfile
from pathlib import Path

# Field order from CMPL.txt (files have no header row).
FIELDS = [
    "CMPLID", "ODINO", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT", "CRASH",
    "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC", "CITY", "STATE", "VIN",
    "DATEA", "LDATE", "MILES", "OCCURENCES", "CDESCR", "CMPL_TYPE",
    "POLICE_RPT_YN", "PURCH_DT", "ORIG_OWNER_YN", "ANTI_BRAKES_YN",
    "CRUISE_CONT_YN", "NUM_CYLS", "DRIVE_TRAIN", "FUEL_SYS", "FUEL_TYPE",
    "TRANS_TYPE", "VEH_SPEED", "DOT", "TIRE_SIZE", "LOC_OF_TIRE",
    "TIRE_FAIL_TYPE", "ORIG_EQUIP_YN", "MANUF_DT", "SEAT_TYPE",
    "RESTRAINT_TYPE", "DEALER_NAME", "DEALER_TEL", "DEALER_CITY",
    "DEALER_STATE", "DEALER_ZIP", "PROD_TYPE", "REPAIRED_YN", "MEDICAL_ATTN",
    "VEHICLES_TOWED_YN", "STATE_OF_INCIDENT", "VEHICLE_OPERATOR",
]

# Columns kept. Drops personal data (operator name, city, dealer contact)
# and tire/child-seat fields that don't apply to this question.
KEEP = [
    "ODINO", "MAKETXT", "MODELTXT", "YEARTXT", "LDATE", "FAILDATE", "COMPDESC",
    "CRASH", "FIRE", "INJURED", "DEATHS", "MEDICAL_ATTN", "VEHICLES_TOWED_YN",
    "MILES", "VEH_SPEED", "STATE", "VIN", "PURCH_DT", "MANUF_DT", "CMPL_TYPE",
    "CDESCR",
]

# (make, model) as spelled in the complaint file -> group label.
# "iccu_recalled" models are the ones named in recalls 24V-200/204/867/868;
# "egmp_not_recalled" share the platform but were never in an ICCU recall,
# which makes them a comparison group.
MODELS = {
    ("HYUNDAI", "IONIQ 5"): "iccu_recalled",
    ("HYUNDAI", "IONIQ 6"): "iccu_recalled",
    ("KIA", "EV6"): "iccu_recalled",
    ("GENESIS", "GV60"): "iccu_recalled",
    ("GENESIS", "GV70 ELECTRIFIED"): "iccu_recalled",
    ("HYUNDAI", "IONIQ 5 N"): "egmp_not_recalled",
    ("HYUNDAI", "IONIQ 9"): "egmp_not_recalled",
    ("KIA", "EV9"): "egmp_not_recalled",
    ("GENESIS", "G80 ELECTRIFIED"): "other_ev_not_recalled",
}


def iter_rows(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        (name,) = zf.namelist()
        with io.TextIOWrapper(zf.open(name), encoding="latin-1", newline="") as f:
            for line_no, line in enumerate(f, 1):
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) != len(FIELDS):
                    raise ValueError(f"{zip_path}:{line_no}: {len(parts)} fields, expected {len(FIELDS)}")
                yield dict(zip(FIELDS, parts))


def main(raw_dir, out_path):
    zips = sorted(Path(raw_dir).glob("COMPLAINTS_RECEIVED_*.zip"))
    if not zips:
        sys.exit(f"no COMPLAINTS_RECEIVED_*.zip in {raw_dir}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scanned = kept = 0
    with open(out_path, "w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow([c.lower() for c in KEEP] + ["model_group", "source_file"])
        for z in zips:
            for row in iter_rows(z):
                scanned += 1
                group = MODELS.get((row["MAKETXT"].upper(), row["MODELTXT"].upper()))
                if group:
                    kept += 1
                    w.writerow([row[c].strip() for c in KEEP] + [group, z.name])
    print(f"scanned {scanned:,} rows, kept {kept:,} -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
