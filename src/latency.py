"""Recall latency: how long from first warning signs to a recall, by brand and component.

One row per recall campaign (campno x make) in `recall_latency`, with two
measures:

1. Warning lead (from the spike detector). Weeks from the earliest clean spike
   flag (src/backtest.py: system, subsystem or topic series for that recall,
   within 12 months before the announcement) to the announcement. Only
   recalls the detector catches have a lead; the rest are "no warning" and are
   counted, not dropped, because dropping them would make every brand look
   faster. So read it as "when a recall is detectable at all, how early".

2. Investigation latency (official path). For recalls NHTSA links to an
   investigation (investigations.campno), weeks from the investigation's open
   date to the announcement. Small sample, real dates.

Why not "weeks since K complaints piled up"? It was tried first and rejected:
a placebo test on dates with no recall gave almost the same answer (cluster
found before 19% of non-recall dates vs 23% of recalls, median 101 vs 88
weeks), because busy series always have 5 complaints in 90 days. It measures
complaint volume, not warning time, and brand differences in it are mostly
volume differences.

Run after backtest.py.

Usage:
    python src/latency.py data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

MIN_CAMPAIGNS = 15   # don't print group stats on fewer campaigns than this


def build(con):
    bt = pd.read_sql_query("SELECT * FROM backtest", con)
    grp = pd.read_sql_query("SELECT system, component_group, COUNT(*) n FROM component_map GROUP BY 1, 2", con)
    grp = grp.sort_values("n").drop_duplicates("system", keep="last").set_index("system")["component_group"]
    bt["component_group"] = bt["system"].map(grp).fillna("other")

    rows = []
    for (campno, make), g in bt.groupby(["campno", "make"]):
        flagged = g[g["first_flag"].notna()]
        best = flagged.sort_values("lead_weeks", ascending=False).iloc[0] if len(flagged) else None
        pick = best if best is not None else g.iloc[0]
        group = pick["component_group"] if best is not None else g["component_group"].mode().iloc[0]
        rows.append((campno, make, g["report_date"].min(), group, int(g["eligible"].max()),
                     int(best is not None), None if best is None else float(best["lead_weeks"])))
    df = pd.DataFrame(rows, columns=["campno", "make", "report_date", "component_group",
                                     "eligible", "flagged", "lead_weeks"])

    inv = pd.read_sql_query(
        """SELECT i.campno, i.make, MIN(i.open_date) AS inv_open FROM investigations i
           WHERE i.campno IS NOT NULL GROUP BY 1, 2""", con)
    df = df.merge(inv, on=["campno", "make"], how="left")
    df["inv_latency_wk"] = (pd.to_datetime(df["report_date"]) - pd.to_datetime(df["inv_open"])).dt.days / 7
    return df.drop(columns="inv_open")


def summarize(df):
    e = df[df["eligible"] == 1]
    print(f"{len(df):,} recall campaigns; {len(e):,} testable (enough complaints for the detector to fire); "
          f"detector warned on {int(e['flagged'].sum()):,} ({e['flagged'].mean():.0%}), "
          f"median lead {e['lead_weeks'].median():.0f} wk")
    for by in ("make", "component_group"):
        g = e.groupby(by).agg(campaigns=("campno", "size"), warned=("flagged", "mean"),
                              median_lead_wk=("lead_weeks", "median"),
                              p25=("lead_weeks", lambda s: s.quantile(.25)),
                              p75=("lead_weeks", lambda s: s.quantile(.75)),
                              n_warned=("flagged", "sum"))
        g = g[g["campaigns"] >= MIN_CAMPAIGNS].round(2)
        print(f"\nwarning lead by {by} (testable campaigns, groups with >= {MIN_CAMPAIGNS}):")
        print(g.to_string())
    inv = df.dropna(subset=["inv_latency_wk"])
    print(f"\ninvestigation -> recall: {len(inv)} linked campaigns, median {inv['inv_latency_wk'].median():.0f} wk "
          f"({int((inv['inv_latency_wk'] < 0).sum())} with the recall before the investigation opened)")
    print(inv.groupby("make")["inv_latency_wk"].agg(["count", "median"]).round(1).to_string())


def main(db_path):
    con = sqlite3.connect(db_path)
    df = build(con)
    con.execute("DROP TABLE IF EXISTS recall_latency")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO recall_latency VALUES (?,?,?,?,?,?,?,?)",
                    [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False)])
    con.commit()
    summarize(df)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
