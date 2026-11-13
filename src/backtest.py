"""Backtest the spike detector against past recalls.

Recall events are (campaign x make x model x subsystem). For each one we ask
whether the detector flagged that series in the LOOKBACK_MONTHS before the
announcement (report_date), at the system level or the subsystem level, and
how many weeks early. A flag counts from the end of its month, so lead time is
never overstated.

"Clean" flags exclude any flag within 6 months after another recall in the
same series: a recall announcement itself triggers a complaint surge, which
would make a second recall look predicted. Clean is the headline.

Only eligible events count in the denominator: at least one level's series
needs >= min_total complaints and enough history for the detector to have run.
Recalls on parts nobody complains about can't be predicted from complaints;
they are reported separately.

Two scores, used by src/tune.py and printed here:
  recall     share of eligible events with a clean flag before the recall
  precision  share of clean episode onsets followed by a recall in the same
             series within 12 months (onsets near the end of the data are
             dropped because their outcome isn't known yet)

Run after detect_spikes.py.

Usage:
    python src/backtest.py data/recall_radar.db
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from detect_spikes import LEVELS, PARAMS

LOOKBACK_DAYS = 365
CONTAM_DAYS = 183
HORIZON_DAYS = 365


def load_events(con):
    """One row per (campno, make, model, subsystem) with its announcement date."""
    ev = pd.read_sql_query(
        """SELECT r.campno, r.make, r.model, m.system, m.subsystem, MIN(r.report_date) AS report_date
           FROM recalls r JOIN component_map m ON m.raw_component = COALESCE(r.component, '')
           WHERE r.report_date IS NOT NULL
           GROUP BY 1, 2, 3, 4, 5""", con)
    ev["report_date"] = pd.to_datetime(ev["report_date"])
    return ev


def _recall_index(events, level):
    """key -> (sorted dates array, matching campnos) of recalls in that series."""
    col = "system" if level == "system" else "subsystem"
    idx = {}
    for key, g in events.drop_duplicates(["campno", "make", "model", col]).groupby(["make", "model", col]):
        g = g.sort_values("report_date")
        idx[key] = (g["report_date"].to_numpy(), g["campno"].to_numpy())
    return idx


def _flag_index(spikes, level):
    s = spikes[spikes["level"] == level].copy()
    s["flag_date"] = pd.PeriodIndex(s["month"], freq="M").end_time.normalize()
    idx = {}
    for key, g in s.groupby(["make", "model", "series"]):
        g = g.sort_values("flag_date")
        idx[key] = (g["flag_date"].to_numpy(), g["month"].to_numpy(), g["onset"].to_numpy())
    return idx, s


def _contaminated(rec, fd, own_camp):
    """True if a recall other than own_camp hit this series in the CONTAM_DAYS up to fd."""
    if rec is None:
        return False
    dates, camps = rec
    lo = np.searchsorted(dates, fd - np.timedelta64(CONTAM_DAYS, "D"), side="left")
    hi = np.searchsorted(dates, fd, side="right")
    return any(camps[i] != own_camp for i in range(lo, hi))


def eligible_keys(data, params=PARAMS):
    """Series the detector could have fired on, per level -> {key: first testable date}."""
    out = {}
    first_ok = {k: (pd.Period(v, "M") + (params["window"] - 1 + params["min_history"])).start_time
                for k, v in data["start"].items()}
    for level in LEVELS:
        c = data["counts"][level]
        tot = c.groupby(["make", "model", "series"])["n"].sum()
        out[level] = {k: first_ok[(k[0], k[1])] for k, n in tot.items() if n >= params["min_total"]}
    return out


def score_events(events, spikes, elig, levels=LEVELS, clean_only=True):
    """Per-event result. Flag search uses only `levels`; eligibility always uses both."""
    rec_idx = {lv: _recall_index(events, lv) for lv in LEVELS}
    flag_idx = {lv: _flag_index(spikes, lv)[0] for lv in LEVELS}
    rows = []
    for r in events.itertuples():
        keys = {"system": (r.make, r.model, r.system), "subsystem": (r.make, r.model, r.subsystem)}
        eligible = any(keys[lv] in elig[lv] and r.report_date >= elig[lv][keys[lv]] for lv in LEVELS)
        best = None  # (lead_days, level, month, clean)
        if eligible:
            lo = np.datetime64(r.report_date - pd.Timedelta(days=LOOKBACK_DAYS))
            hi = np.datetime64(r.report_date)
            for lv in levels:
                f = flag_idx[lv].get(keys[lv])
                if f is None:
                    continue
                dates, months, _ = f
                for i in range(np.searchsorted(dates, lo, side="left"), np.searchsorted(dates, hi, side="left")):
                    clean = not _contaminated(rec_idx[lv].get(keys[lv]), dates[i], r.campno)
                    if clean_only and not clean:
                        continue
                    lead = (np.datetime64(r.report_date) - dates[i]) / np.timedelta64(1, "D")
                    if best is None or lead > best[0]:
                        best = (lead, lv, months[i], int(clean))
                    break  # earliest qualifying flag in this level
        rows.append((r.campno, r.make, r.model, r.system, r.subsystem,
                     r.report_date.date().isoformat(), int(eligible),
                     best[1] if best else None, best[2] if best else None,
                     best[0] / 7 if best else None, best[3] if best else None))
    return pd.DataFrame(rows, columns=["campno", "make", "model", "system", "subsystem", "report_date",
                                       "eligible", "level", "first_flag", "lead_weeks", "clean"])


def onset_precision(events, spikes, levels, start=None, end=None):
    """(hits, total) of clean onsets whose series saw a recall within HORIZON_DAYS."""
    data_end = events["report_date"].max()
    hits = total = 0
    for lv in levels:
        rec = _recall_index(events, lv)
        s = spikes[(spikes["level"] == lv) & (spikes["onset"] == 1)]
        fd_all = pd.PeriodIndex(s["month"], freq="M").end_time.normalize()
        for (make, model, series), fd in zip(zip(s["make"], s["model"], s["series"]), fd_all):
            if start is not None and fd < start:
                continue
            if end is not None and fd >= end:
                continue
            if fd > data_end - pd.Timedelta(days=HORIZON_DAYS):
                continue
            r = rec.get((make, model, series))
            if _contaminated(r, np.datetime64(fd), None):
                continue
            total += 1
            if r is not None:
                d = r[0]
                a = np.searchsorted(d, np.datetime64(fd), side="right")
                b = np.searchsorted(d, np.datetime64(fd + pd.Timedelta(days=HORIZON_DAYS)), side="right")
                hits += int(b > a)
    return hits, total


def summarize(res, label=""):
    e = res[res["eligible"] == 1]
    f = e[e["first_flag"].notna()]
    print(f"{label}{len(res):,} recall events; {len(e):,} eligible; flagged {len(f):,} "
          f"({len(f) / max(len(e), 1):.0%}); median lead {f['lead_weeks'].median():.1f} wk")
    by = e.groupby("make").agg(events=("campno", "size"), flagged=("first_flag", "count"),
                               median_lead_wk=("lead_weeks", "median"))
    by["rate"] = (by["flagged"] / by["events"]).round(2)
    print(by.to_string())


def main(db_path):
    from detect_spikes import load_data
    con = sqlite3.connect(db_path)
    events = load_events(con)
    spikes = pd.read_sql_query("SELECT * FROM spikes", con)
    data = load_data(con)
    elig = eligible_keys(data)
    res = score_events(events, spikes, elig)
    for lv in (("system",), ("subsystem",)):
        r = score_events(events, spikes, elig, levels=lv)
        e = r[r["eligible"] == 1]
        print(f"{lv[0]:>9} only: flagged {e['first_flag'].notna().sum():,} of {len(e):,} "
              f"({e['first_flag'].notna().mean():.0%})")
    print()
    summarize(res, "both levels: ")
    h, t = onset_precision(events, spikes, LEVELS)
    print(f"onset precision: {h:,} of {t:,} clean episodes followed by a same-series recall within 12 months ({h / t:.0%})")
    con.execute("DROP TABLE IF EXISTS backtest")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    con.executemany("INSERT INTO backtest VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [tuple(None if pd.isna(v) else v for v in row) for row in res.itertuples(index=False)])
    con.commit()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
