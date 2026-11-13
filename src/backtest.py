"""Backtest the spike detector against past recalls.

For every recall event (campaign x make x model x system) it asks whether
`spikes` flagged the same make/model/system in the LOOKBACK_MONTHS before the
announcement (report_date), and how many weeks early. A flag counts from the
end of its month, so lead time is never overstated.

Two views of "flagged":
  any   earliest flag in the lookback window
  clean earliest flag that is NOT within 6 months after another recall in the
        same series (a recall announcement itself triggers a complaint surge,
        which would make a second recall look predicted)
The clean view is the headline; `any` is shown for comparison.

Only eligible recalls count in the denominator: the series needs >= 30 total
complaints and enough history for the detector to have run. Recalls on parts
nobody complains about can't be predicted from complaints; they're reported
separately.

Run after detect_spikes.py.

Usage:
    python src/backtest.py data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from detect_spikes import MIN_HISTORY, MIN_TOTAL, WINDOW, load_counts

LOOKBACK_MONTHS = 12
CONTAMINATION_MONTHS = 6


def build(con):
    rec = pd.read_sql_query(
        """SELECT r.campno, r.make, r.model, m.system, MIN(r.report_date) AS report_date
           FROM recalls r JOIN component_map m ON m.raw_component = COALESCE(r.component, '')
           WHERE r.report_date IS NOT NULL
           GROUP BY 1, 2, 3, 4""", con)
    rec["report_date"] = pd.to_datetime(rec["report_date"])
    df, start, _ = load_counts(con)
    totals = df.groupby(["make", "model", "system"])["n"].sum()
    spikes = pd.read_sql_query("SELECT make, model, system, month FROM spikes", con)
    spikes["flag_date"] = pd.PeriodIndex(spikes["month"], freq="M").end_time.normalize()
    flags = {k: g.sort_values("flag_date") for k, g in spikes.groupby(["make", "model", "system"])}
    recalls_by_series = {k: g["report_date"].sort_values().tolist()
                         for k, g in rec.groupby(["make", "model", "system"])}

    out = []
    for r in rec.itertuples():
        key = (r.make, r.model, r.system)
        mstart = start.get((r.make, r.model))
        first_ok = (pd.Period(mstart, "M") + (WINDOW - 1 + MIN_HISTORY)).start_time if mstart else None
        eligible = int(totals.get(key, 0) >= MIN_TOTAL and first_ok is not None
                       and r.report_date >= first_ok)
        first_flag = lead = clean = None
        g = flags.get(key)
        if eligible and g is not None:
            lo = r.report_date - pd.DateOffset(months=LOOKBACK_MONTHS)
            cand = g[(g["flag_date"] < r.report_date) & (g["flag_date"] >= lo)]
            others = [d for d in recalls_by_series[key] if d != r.report_date]
            def contaminated(fd):
                return any(fd - pd.DateOffset(months=CONTAMINATION_MONTHS) <= d <= fd for d in others)
            if len(cand):
                first = cand.iloc[0]
                first_flag = first["month"]
                lead = (r.report_date - first["flag_date"]).days / 7
                clean = int(not contaminated(first["flag_date"]))
                # Prefer the earliest uncontaminated flag if the first one is contaminated.
                if not clean:
                    for _, c in cand.iterrows():
                        if not contaminated(c["flag_date"]):
                            first_flag, lead, clean = c["month"], (r.report_date - c["flag_date"]).days / 7, 1
                            break
        out.append((r.campno, r.make, r.model, r.system, r.report_date.date().isoformat(),
                    eligible, first_flag, lead, clean))
    return out


def summarize(rows):
    d = pd.DataFrame(rows, columns=["campno", "make", "model", "system", "report_date",
                                    "eligible", "first_flag", "lead_weeks", "clean"])
    d["any_flag"] = d["first_flag"].notna()
    d["clean_flag"] = d["clean"].fillna(0).astype(bool) & d["any_flag"]
    e = d[d["eligible"] == 1]
    print(f"{len(d):,} recall events; {len(e):,} eligible ({len(d) - len(e):,} on series too quiet for complaints to predict)")
    for label, mask in (("clean", e["clean_flag"]), ("any", e["any_flag"])):
        lead = e.loc[mask, "lead_weeks"]
        print(f"{label:>5}: flagged {mask.sum():,} of {len(e):,} ({mask.mean():.0%}); "
              f"median lead {lead.median():.1f} wk, mean {lead.mean():.1f} wk")
    by = e.groupby("make").agg(recalls=("campno", "size"), flagged=("clean_flag", "sum"),
                               median_lead_wk=("lead_weeks", lambda s: s[e.loc[s.index, "clean_flag"]].median()))
    by["rate"] = (by["flagged"] / by["recalls"]).round(2)
    print(by.to_string())


def main(db_path):
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS backtest")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    rows = build(con)
    con.executemany("INSERT INTO backtest VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    summarize(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
