"""Choose detector thresholds with a time split, then report held-out results.

Only the `system` and `topic` levels are tuned and scored: subsystem series
were nearly useless (2.8% precision vs a 1.9% chance rate) and diluted the
pooled numbers when levels were mixed.

Train: recalls announced before CUTOFF (and episode onsets early enough that
their 12-month outcome is also before CUTOFF). Test: recalls and onsets from
CUTOFF onward. Thresholds are picked on train only; the CSV also records test
numbers for every config, but nothing is selected on them.

Every level has a different chance rate (a random topic series-month is far
more likely to see a recall than a random system one), so precision is
judged against each level's own no-skill baseline:

  recall      share of eligible recalls with a clean flag in the 12 months before
  precision   clean episode onsets followed by a same-series recall within 12 months
  net_prec    (hits - sum over levels of onsets * that level's chance rate) / onsets,
              i.e. precision above chance, pooled across levels
  objective   F0.5 of recall and net_prec (precision counts more than recall,
              because a detector that flags everything catches every recall)

Usage:
    python src/tune.py data/recall_radar.db       # ~6 min, writes reports/tuning_results_system_topic.csv
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
from detect_spikes import PARAMS, detect, load_data

TUNE_LEVELS = ("system", "topic")
CUTOFF = pd.Timestamp("2021-01-01")
BETA = 0.5
GRID = dict(window=[2, 3, 6], base_months=[12, 24], min_ratio=[2.0, 3.0, 5.0],
            alpha=[1e-2, 1e-3, 1e-4], min_count=[5])
TRAIN_ONSET_END = CUTOFF - pd.Timedelta(days=HORIZON_DAYS)
PERIODS = {"train": (None, TRAIN_ONSET_END), "test": (CUTOFF, None)}


def fbeta(p, r, beta=BETA):
    return 0.0 if p + r == 0 else (1 + beta**2) * p * r / (beta**2 * p + r)


def baseline_precision(data, events, elig, start, end, level="system", makes=None):
    """No-skill precision: clean eligible series-months at `level` followed by a recall in 12 months."""
    rec = _recall_index(events, level)
    data_end = events["report_date"].max()
    hits = total = 0
    for key, first in elig[level].items():
        if makes is not None and key[0] not in makes:
            continue
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


def run_config(data, events, elig, params, baselines):
    spikes = pd.concat([detect(data, lv, params) for lv in TUNE_LEVELS], ignore_index=True)
    res = score_events(events, spikes, elig, levels=TUNE_LEVELS)
    e_all = res[res["eligible"] == 1]
    out = {}
    for name, (lo_on, hi_on) in PERIODS.items():
        d = pd.to_datetime(e_all["report_date"])
        e = e_all[(d < CUTOFF) if name == "train" else (d >= CUTOFF)]
        recall = e["first_flag"].notna().mean()
        hits = onsets = 0
        expected = 0.0
        for lv in TUNE_LEVELS:
            h, t = onset_precision(events, spikes, (lv,), start=lo_on, end=hi_on)
            hits, onsets, expected = hits + h, onsets + t, expected + t * baselines[lv][name]
        prec = hits / onsets if onsets else 0.0
        net = (hits - expected) / onsets if onsets else 0.0
        out[name] = dict(events=len(e), recall=recall, onsets=onsets, precision=prec,
                         net_prec=net, objective=fbeta(max(net, 0.0), recall), lead=e["lead_weeks"].median())
    return out


def main(db_path, out_csv):
    con = sqlite3.connect(db_path)
    events = load_events(con)
    data = load_data(con)
    elig = eligible_keys(data)

    print("no-skill baselines (share of series-months followed by a recall within 12 months):", flush=True)
    baselines = {lv: {name: baseline_precision(data, events, elig, lo, hi, lv)
                      for name, (lo, hi) in PERIODS.items()} for lv in TUNE_LEVELS}
    for lv, b in baselines.items():
        print(f"   {lv:>7}: train {b['train']:.1%}, test {b['test']:.1%}", flush=True)

    keys = list(GRID)
    total = int(np.prod([len(v) for v in GRID.values()]))
    rows = []
    for i, vals in enumerate(itertools.product(*GRID.values()), 1):
        t0 = time.time()
        r = run_config(data, events, elig, {**PARAMS, **dict(zip(keys, vals))}, baselines)
        rows.append({**dict(zip(keys, vals)), **{f"{s}_{k}": v for s, d in r.items() for k, v in d.items()}})
        print(f"[{i}/{total}] {dict(zip(keys, vals))} train recall {r['train']['recall']:.1%} "
              f"net_prec {r['train']['net_prec']:+.1%} obj {r['train']['objective']:.3f} ({time.time() - t0:.0f}s)",
              flush=True)
        if i % 10 == 0:
            pd.DataFrame(rows).to_csv(out_csv, index=False)
    df = pd.DataFrame(rows).sort_values("train_objective", ascending=False)
    Path(out_csv).parent.mkdir(exist_ok=True)
    df.to_csv(out_csv, index=False)

    d = PARAMS
    defaults = df[(df.window == d["window"]) & (df.base_months == d["base_months"])
                  & (df.min_ratio == d["min_ratio"]) & (df.alpha == d["alpha"])
                  & (df.min_count == d["min_count"])].iloc[0]
    print("\nTop 5 on train (selection uses train only):")
    for _, row in df.head(5).iterrows():
        print(f"   {dict((k, row[k]) for k in keys)}  train obj {row['train_objective']:.3f}  "
              f"test obj {row['test_objective']:.3f}")
    for label, row in (("best on train", df.iloc[0]), ("current defaults", defaults)):
        print(f"\n{label}: {dict((k, row[k]) for k in keys)}")
        for s in ("train", "test"):
            print(f"   {s}: recall {row[s + '_recall']:.1%} of {int(row[s + '_events'])} events; "
                  f"precision {row[s + '_precision']:.1%} ({row[s + '_net_prec']:+.1%} vs chance) "
                  f"of {int(row[s + '_onsets'])} onsets; median lead {row[s + '_lead']:.1f} wk")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1], Path(__file__).parent.parent / "reports" / "tuning_results_system_topic.csv")
