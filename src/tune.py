"""Choose detector thresholds with a time split, then report held-out results.

Train: recalls announced before CUTOFF (and episode onsets early enough that
their 12-month outcome is also before CUTOFF). Test: recalls and onsets from
CUTOFF onward. Thresholds are picked on train only; test is scored once for
the winner and for the current defaults, so nothing is tuned on test.

Objective (train): F0.5 of recall and onset precision (see backtest.py), i.e.
precision counts more than recall, because a detector that flags everything
catches every recall and is useless. Recall is "share of eligible recalls with
a clean flag in the 12 months before"; precision is "share of clean episode
onsets followed by a same-series recall within 12 months".

Also prints a no-skill baseline for precision: the share of clean series-months
(system level, eligible series) followed by a recall within 12 months. A
detector is only useful if its precision is well above that.

Usage:
    python src/tune.py data/recall_radar.db            # full grid, writes reports/tuning_results.csv
"""
import itertools
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import (HORIZON_DAYS, _contaminated, _recall_index, eligible_keys, load_events,
                      onset_precision, score_events)
from detect_spikes import LEVELS, PARAMS, detect, load_data

CUTOFF = pd.Timestamp("2021-01-01")
BETA = 0.5
GRID = dict(window=[2, 3, 6], min_ratio=[2.0, 3.0, 5.0], alpha=[1e-2, 1e-3, 1e-4], min_count=[3, 5])


def fbeta(p, r, beta=BETA):
    return 0.0 if p + r == 0 else (1 + beta**2) * p * r / (beta**2 * p + r)


def run_config(data, events, elig, params):
    spikes = pd.concat([detect(data, lv, params) for lv in LEVELS], ignore_index=True)
    res = score_events(events, spikes, elig)
    out = {}
    for name, lo_ev, hi_ev, lo_on, hi_on in (
        ("train", None, CUTOFF, None, CUTOFF - pd.Timedelta(days=HORIZON_DAYS)),
        ("test", CUTOFF, None, CUTOFF, None),
    ):
        e = res[res["eligible"] == 1]
        d = pd.to_datetime(e["report_date"])
        m = pd.Series(True, index=e.index)
        if lo_ev is not None:
            m &= d >= lo_ev
        if hi_ev is not None:
            m &= d < hi_ev
        e = e[m]
        recall = e["first_flag"].notna().mean()
        h, t = onset_precision(events, spikes, LEVELS, start=lo_on, end=hi_on)
        prec = h / t if t else 0.0
        out[name] = dict(events=len(e), recall=recall, onsets=t, precision=prec, f=fbeta(prec, recall),
                         lead=e["lead_weeks"].median())
    return out


def baseline_precision(data, events, elig, start, end):
    """No-skill precision: clean eligible system-level series-months followed by a recall in 12 months."""
    rec = _recall_index(events, "system")
    data_end = events["report_date"].max()
    hits = total = 0
    for key, first in elig["system"].items():
        r = rec.get(key)
        for m in pd.period_range(first, pd.Period(data["last"], "M"), freq="M"):
            fd = m.end_time.normalize()
            if (start is not None and fd < start) or (end is not None and fd >= end):
                continue
            if fd > data_end - pd.Timedelta(days=HORIZON_DAYS) or _contaminated(r, np.datetime64(fd), None):
                continue
            total += 1
            if r is not None:
                d = r[0]
                a = np.searchsorted(d, np.datetime64(fd), side="right")
                b = np.searchsorted(d, np.datetime64(fd + pd.Timedelta(days=HORIZON_DAYS)), side="right")
                hits += int(b > a)
    return hits / total if total else float("nan")


def main(db_path, out_csv):
    con = sqlite3.connect(db_path)
    events = load_events(con)
    data = load_data(con)
    elig = eligible_keys(data)
    keys = list(GRID)
    rows = []
    for i, vals in enumerate(itertools.product(*GRID.values()), 1):
        t0 = time.time()
        params = {**PARAMS, **dict(zip(keys, vals))}
        r = run_config(data, events, elig, params)
        rows.append({**dict(zip(keys, vals)),
                     **{f"{s}_{k}": v for s, d in r.items() for k, v in d.items()}})
        print(f"[{i}/{np.prod([len(v) for v in GRID.values()])}] {dict(zip(keys, vals))} "
              f"train recall {r['train']['recall']:.1%} prec {r['train']['precision']:.1%} "
              f"F {r['train']['f']:.3f} ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows).sort_values("train_f", ascending=False)
    Path(out_csv).parent.mkdir(exist_ok=True)
    df.to_csv(out_csv, index=False)

    best = df.iloc[0]
    defaults = df[(df.window == PARAMS["window"]) & (df.min_ratio == PARAMS["min_ratio"])
                  & (df.alpha == PARAMS["alpha"]) & (df.min_count == PARAMS["min_count"])].iloc[0]
    print("\nno-skill precision (train / test):",
          f"{baseline_precision(data, events, elig, None, CUTOFF - pd.Timedelta(days=HORIZON_DAYS)):.1%} /",
          f"{baseline_precision(data, events, elig, CUTOFF, None):.1%}")
    for label, row in (("best on train", best), ("current defaults", defaults)):
        print(f"{label}: {dict((k, row[k]) for k in keys)}")
        for s in ("train", "test"):
            print(f"   {s}: recall {row[s + '_recall']:.1%} of {int(row[s + '_events'])} events, "
                  f"precision {row[s + '_precision']:.1%} of {int(row[s + '_onsets'])} onsets, "
                  f"median lead {row[s + '_lead']:.1f} wk")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1], Path(__file__).parent.parent / "reports" / "tuning_results.csv")
