"""Build `component_map` from the component strings already loaded into SQLite.

Run after the three ingest scripts. Every distinct raw string found in
complaints, recalls and investigations gets a row, so joins on
component_map never silently drop rows. Rules are first-match-wins and live
in this file so the mapping is reviewable; re-running rebuilds the table.

NHTSA component strings are "SYSTEM:SUBSYSTEM:PART" and differ by table
(complaints say ENGINE, recalls say ENGINE AND ENGINE COOLING), so `system`
normalizes the first level and `component_group` assigns the topic bucket.

Usage:
    python src/build_component_map.py data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

# Level-1 names that mean the same thing across tables -> normalized system.
SYSTEM_ALIASES = {
    "ENGINE AND ENGINE COOLING": "ENGINE",
    "ELECTRONIC STABILITY CONTROL (ESC)": "ELECTRONIC STABILITY CONTROL",
    "VISIBILITY/WIPER": "VISIBILITY",
    "COMMUNICATIONS": "COMMUNICATION",
    "FUEL/PROPULSION SYSTEM": "FUEL SYSTEM",
    "FUEL SYSTEM, GASOLINE": "FUEL SYSTEM",
    "FUEL SYSTEM, DIESEL": "FUEL SYSTEM",
    "FUEL SYSTEM, OTHER": "FUEL SYSTEM",
    "SERVICE BRAKES, AIR": "SERVICE BRAKES",
    "SERVICE BRAKES, ELECTRIC": "SERVICE BRAKES",
    "SERVICE BRAKES, HYDRAULIC": "SERVICE BRAKES",
}

# Child-seat free-text entries and junk that complainants typed in.
CHILD_SEAT_L1 = {"CARRY HANDLE, SHELL, BASE", "CHEST CLIP, BUCKLE, HARNESS", "INSERT, PADDING",
                 "TETHER, LOWER ANCHOR (ON CAR SEAT OR VEHICLE)"}
JUNK_L1 = {"", "NONE", "OTHER", "OTHER/I AM NOT SURE", "UNKNOWN OR OTHER", "FIRERELATED",
           "I SUSPECT THE CAR SEAT IS COUNTERFEIT"}

# Topic bucket by normalized system (default: other).
GROUP_BY_SYSTEM = {
    "ENGINE": "powertrain", "POWER TRAIN": "powertrain", "FUEL SYSTEM": "powertrain",
    "HYBRID PROPULSION SYSTEM": "powertrain", "VEHICLE SPEED CONTROL": "powertrain",
    "ELECTRICAL SYSTEM": "electrical", "EXTERIOR LIGHTING": "electrical",
    "INTERIOR LIGHTING": "electrical",
    "COMMUNICATION": "infotainment",
    "FORWARD COLLISION AVOIDANCE": "driver_assistance", "LANE DEPARTURE": "driver_assistance",
    "BACK OVER PREVENTION": "driver_assistance", "ELECTRONIC STABILITY CONTROL": "driver_assistance",
    "TRACTION CONTROL SYSTEM": "driver_assistance",
}

# (system, level-2 name) overrides, checked before GROUP_BY_SYSTEM.
GROUP_BY_SUBSYSTEM = {
    ("ELECTRICAL SYSTEM", "INSTRUMENT CLUSTER/PANEL"): "infotainment",
    ("ELECTRICAL SYSTEM", "INSTRUMENT PANEL"): "infotainment",
    ("BACK OVER PREVENTION", "DISPLAY FUNCTION"): "infotainment",
    ("ELECTRICAL SYSTEM", "ADAS"): "driver_assistance",
    ("ELECTRICAL SYSTEM", "PROPULSION SYSTEM"): "powertrain",
}


def classify(raw):
    parts = [p.strip().upper() for p in (raw or "").split(":")]
    l1 = parts[0]
    l2 = parts[1] if len(parts) > 1 else ""
    if l1 in CHILD_SEAT_L1:
        return "CHILD SEAT", "other"
    if l1 in JUNK_L1:
        return "OTHER", "other"
    system = SYSTEM_ALIASES.get(l1, l1)
    if system.startswith("SERVICE BRAKES"):  # incl. one free-text "...; AUTOHOLD..." variant
        system = "SERVICE BRAKES"
    group = GROUP_BY_SUBSYSTEM.get((system, l2)) or GROUP_BY_SYSTEM.get(system, "other")
    return system, group


def main(db_path):
    con = sqlite3.connect(db_path)
    # Drop first so a table created from an older schema picks up new columns.
    con.execute("DROP TABLE IF EXISTS component_map")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    raws = set()
    for table in ("complaints", "recalls", "investigations"):
        raws.update(r for (r,) in con.execute(f"SELECT DISTINCT component FROM {table}"))
    raws = {r if r is not None else "" for r in raws}
    con.executemany("INSERT INTO component_map VALUES (?,?,?)",
                    [(r, *classify(r)) for r in sorted(raws)])
    con.commit()
    print(f"{len(raws):,} distinct raw components -> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
