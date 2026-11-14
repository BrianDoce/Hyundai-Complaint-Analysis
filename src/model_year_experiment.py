"""Does splitting complaint series by model year help the spike detector?

The production detector pools all model years of a model. A defect in one model
year (say the 2019 Santa Fe) is then diluted by every other year's complaints.
Here each (make, model, model year) is treated as its own "model" ("SANTA FE|2019"),
keeping the system-level series, and the same detector and backtest code runs on it:

  * the baseline, history requirement (12 months) and growth scale are per model year, and
    a model year's clock starts at its own first complaint, so a new model year's launch
    ramp is not a spike
  * recall events are expanded to one per model year the recall covers

Comparison with the pooled system-level detector, scored the same way (clean flags,
12-month lookback, onset precision judged against each version's own chance rate):

  * recall events are not comparable one-to-one (a campaign covering 4 model years
    becomes 4 events), so coverage is compared per campaign: a campaign counts as
    warned if any of its events had a clean flag
  * precision above chance, all years and 2021 onward (the held-out period used in tune.py)

Nothing is written to the database. Usage:
    python src/model_year_experiment.py data/recall_radar.db
"""
import sqlite3
import sys

import pandas as pd

from backtest import eligible_keys, load_events, onset_precision, score_events
from detect_spikes import PARAMS, detect, load_data
from tune import CUTOFF, baseline_precision

MY_MIN, MY_MAX = 1990, 2027


def load_my_data(con):
    raw = pd.read_sql_query(
        """SELECT DISTINCT x.odino, x.make, x.model || '|' || x.model_year AS model, m.system,
                  substr(x.received, 1, 7) AS month
           FROM complaints x JOIN component_map m ON m.raw_component = COALESCE(x.component, '')
           WHERE x.received IS NOT NULL AND x.model_year BETWEEN ? AND ?""", con, params=(MY_MIN, MY_MAX))
    d = raw.drop_duplicates(["odino", "make", "model", "system", "month"])
    system = (d.groupby(["make", "model", "system", "month"]).size().rename("n").reset_index()
              .rename(columns={"system": "series"}))
    empty = pd.DataFrame(columns=["make", "model", "series", "month", "n"])
    totals = raw.drop_duplicates("odino").groupby(["make", "model", "month"]).size().rename("total")
    start = totals.reset_index().groupby(["make", "model"])["month"].min()
    return dict(counts={"system": system, "subsystem": empty, "topic": empty}, start=start, totals=totals,
                last=raw["month"].max(), family={}, sales={})


def load_my_events(con):
    ev = pd.read_sql_query(
        """SELECT r.campno, r.make, r.model || '|' || r.model_year AS model, m.system, m.subsystem,
                  MIN(r.report_date) AS report_date
           FROM recalls r JOIN component_map m ON m.raw_component = COALESCE(r.component, '')
           WHERE r.report_date IS NOT NULL AND r.model_year BETWEEN ? AND ?
           GROUP BY 1, 2, 3, 4, 5""", con, params=(MY_MIN, MY_MAX))
    ev["report_date"] = pd.to_datetime(ev["report_date"])
    ev["topics"] = [[] for _ in range(len(ev))]
    return ev


def by_campaign(res):
    g = res.groupby("campno").agg(eligible=("eligible", "max"), flagged=("first_flag", lambda s: int(s.notna().any())),
                                  lead=("lead_weeks", "max"))
    return g


def precision_line(label, data, events, spikes, elig):
    out = {}
    for name, (lo, hi) in {"all": (None, None), "2021+": (CUTOFF, None)}.items():
        h, t = onset_precision(events, spikes, ("system",), start=lo, end=hi)
        b = baseline_precision(data, events, elig, lo, hi, "system")
        out[name] = (h, t, b)
    s = "; ".join(f"{k}: {h}/{t} = {h / max(t, 1):.1%} vs chance {b:.1%} ({h / max(t, 1) - b:+.1%})"
                  for k, (h, t, b) in out.items())
    print(f"  {label:<18}{s}")


def main(db_path):
    con = sqlite3.connect(db_path)
    data_p, ev_p = load_data(con), load_events(con)
    elig_p = eligible_keys(data_p)
    sp_p = pd.concat([detect(data_p, "system")], ignore_index=True)
    res_p = score_events(ev_p, sp_p, elig_p, levels=("system",))

    data_m, ev_m = load_my_data(con), load_my_events(con)
    elig_m = eligible_keys(data_m)
    print(f"model-year series: {len(elig_m['system']):,} testable (pooled: {len(elig_p['system']):,}); "
          f"{len(ev_m):,} model-year recall events vs {len(ev_p):,} pooled events", flush=True)
    sp_m = detect(data_m, "system")
    res_m = score_events(ev_m, sp_m, elig_m, levels=("system",))

    cp, cm = by_campaign(res_p), by_campaign(res_m)
    j = cp.join(cm, how="outer", lsuffix="_p", rsuffix="_m").fillna(0)
    e_any = j[(j.eligible_p == 1) | (j.eligible_m == 1)]
    e_both = j[(j.eligible_p == 1) & (j.eligible_m == 1)]
    print(f"\nCampaigns testable by pooled {int(j.eligible_p.sum())}, by model-year {int(j.eligible_m.sum())}, "
          f"by either {len(e_any)}, by both {len(e_both)}")
    for label, d in (("testable by either", e_any), ("testable by both", e_both)):
        p, m = d.flagged_p == 1, d.flagged_m == 1
        print(f"  {label} ({len(d)}): pooled warned {int(p.sum())} ({p.mean():.1%}), model-year {int(m.sum())} "
              f"({m.mean():.1%}), both {int((p & m).sum())}, either {int((p | m).sum())} ({(p | m).mean():.1%}), "
              f"only model-year {int((m & ~p).sum())}")
        print(f"     median lead: pooled {d.loc[p, 'lead_p'].median():.1f} wk, model-year {d.loc[m, 'lead_m'].median():.1f} wk")
    print("\nOnset precision, system level, clean episodes:")
    precision_line("pooled", data_p, ev_p, sp_p, elig_p)
    precision_line("by model year", data_m, ev_m, sp_m, elig_m)
    print(f"\nepisodes (onsets): pooled {int((sp_p['onset'] == 1).sum())}, model-year {int((sp_m['onset'] == 1).sum())}")
    print("recent model-year onsets (last 3 months of data):")
    last = pd.Period(data_m["last"], "M")
    recent = [str(last - i) for i in range(3)]
    print(sp_m[(sp_m["onset"] == 1) & sp_m["month"].isin(recent)][["make", "model", "series", "month", "window_n", "ratio"]]
          .sort_values("ratio", ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
