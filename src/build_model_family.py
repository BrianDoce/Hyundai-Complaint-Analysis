"""Build `model_family`: map NHTSA model strings and sales model names to one family name.

Complaints carry variants (SANTA FE SPORT, SONATA HYBRID, PRIUS PRIME) while
sales report families, so complaints per vehicle sold needs both sides on the
same name. Two kinds of rule, both in this file so they are reviewable:

  OVERRIDES   explicit renames and variants (K5 -> OPTIMA, SANTA FE SPORT -> SANTA FE)
  SUFFIXES    trailing words stripped (HYBRID, PRIME, ELECTRIC...), but only when the
              stripped name is a known family, so an unrelated model that merely ends
              in one of these words is left alone

Renamed models share a family named after the older NHTSA name, matching the
convention in data/sales/us_sales.csv. Everything else is its own family.
Re-running rebuilds the table. Run after the ingest scripts and ingest_sales.py.

Usage:
    python src/build_model_family.py data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

OVERRIDES = {
    ("KIA", "K5"): "OPTIMA", ("KIA", "K4"): "FORTE", ("KIA", "CARNIVAL"): "SEDONA",
    ("KIA", "SEDONA EX"): "SEDONA",
    ("HYUNDAI", "SANTA FE SPORT"): "SANTA FE", ("HYUNDAI", "SANTA FE XL"): "SANTA FE",
    ("HYUNDAI", "ELANTRA GT"): "ELANTRA", ("HYUNDAI", "ELANTRA TOURING"): "ELANTRA",
    ("HYUNDAI", "IONIQ HYBRID"): "IONIQ", ("HYUNDAI", "IONIQ ELECTRIC"): "IONIQ",
    ("TOYOTA", "4 RUNNER"): "4RUNNER", ("TOYOTA", "PRIUS V"): "PRIUS", ("TOYOTA", "PRIUS C"): "PRIUS",
    ("TOYOTA", "PRIUS PRIME"): "PRIUS", ("TOYOTA", "PRIUS PLUG-IN HYBRID"): "PRIUS",
    ("TOYOTA", "COROLLA MATRIX"): "COROLLA", ("TOYOTA", "SEQUOIA SR5"): "SEQUOIA",
    ("TOYOTA", "REDUNDANT SIENNA"): "SIENNA",
    ("HONDA", "CIVIC SI"): "CIVIC", ("HONDA", "CLARITY FUEL CELL"): "CLARITY",
    ("TOYOTA", "GR86"): "86", ("TOYOTA", "FR-S"): "86", ("TOYOTA", "YARIS IA"): "YARIS",
}
SUFFIXES = (" PLUG-IN HYBRID", " HYBRID", " PRIME", " ELECTRIC", " EV", " BEV", " H/B")


def families(models_by_make, sales_models):
    """-> {(make, model): family}."""
    known = {(m, s) for m, s in sales_models} | {(m, f) for (m, _), f in OVERRIDES.items()}
    out = {}
    for make, model in sorted(models_by_make):
        fam = OVERRIDES.get((make, model))
        cur = model
        while fam is None:
            hit = next((cur[: -len(s)] for s in SUFFIXES if cur.endswith(s) and len(cur) > len(s)), None)
            if hit is None:
                break
            if (make, hit) in known:
                fam = OVERRIDES.get((make, hit), hit)
            cur = hit
        out[(make, model)] = fam or model
    return out


def main(db_path):
    con = sqlite3.connect(db_path)
    seen = set()
    for table in ("complaints", "recalls", "investigations", "sales"):
        seen.update(con.execute(f"SELECT DISTINCT make, model FROM {table}"))
    sales_models = set(con.execute("SELECT DISTINCT make, model FROM sales"))
    fam = families(seen, sales_models)
    con.execute("DROP TABLE IF EXISTS model_family")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO model_family VALUES (?,?,?)", [(m, mo, f) for (m, mo), f in fam.items()])
    con.commit()
    print(f"{len(fam):,} models -> {len(set(fam.values())):,} families "
          f"({sum(1 for (m, mo), f in fam.items() if f != mo):,} models mapped to a different name) -> {db_path}")

    print("\nmodels with >= 100 complaints mapped to another family:")
    for make, model, n in con.execute(
            """SELECT c.make, c.model, COUNT(DISTINCT c.odino) n FROM complaints c GROUP BY 1, 2 HAVING n >= 100
               ORDER BY n DESC"""):
        f = fam.get((make, model))
        if f != model:
            print(f"   {make} {model} -> {f}  ({n:,})")

    print("\nshare of 2018+ complaints in families that have sales rows, by make:")
    have = {(m, fam[(m, mo)]) for m, mo in sales_models}
    for make in sorted({m for m, _ in have}):
        tot = hit = 0
        for model, n in con.execute(
                """SELECT model, COUNT(DISTINCT odino) FROM complaints
                   WHERE make = ? AND received >= '2018-01-01' GROUP BY 1""", (make,)):
            tot += n
            hit += n if (make, fam.get((make, model), model)) in have else 0
        print(f"   {make:8} {hit:,} of {tot:,} ({hit / tot:.0%})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
