"""Does dividing by sales help the spike detector? Compare growth adjustments on the brands with sales data.

Runs the detector three ways with the current thresholds and scores each on the
same recalls and spike episodes from START onward (sales exist
from 2018 and need 12 months of history, so earlier periods can't use them):

  others  baseline scaled by growth of the model's other complaints (the default)
  sales   baseline scaled by growth of the model's trailing-12-month sales
  none    no adjustment

Precision is judged against the chance rate for the same makes and period, per
level, as in src/tune.py. Samples are small; the counts are printed so the
differences can be judged against noise.

Usage:
    python src/sales_experiment.py data/recall_radar.db
"""
import sqlite3
import sys

import pandas as pd

from backtest import eligible_keys, load_events, onset_precision, score_events
from detect_spikes import PARAMS, detect, load_data
from tune import baseline_precision

MAKES = {"HYUNDAI", "KIA", "TOYOTA", "HONDA"}
START = pd.Timestamp("2020-01-01")
LEVELS = ("system", "topic")
MODES = ("others", "sales", "none")


def main(db_path):
    con = sqlite3.connect(db_path)
    events = load_events(con)
    data = load_data(con)
    elig = eligible_keys(data)
    base = {lv: baseline_precision(data, events, elig, START, None, lv, MAKES) for lv in LEVELS}
    print(f"{", ".join(sorted(MAKES))}, {START.year} onward. Chance rate (series-month followed by a recall in 12 months): "
          + ", ".join(f"{lv} {b:.1%}" for lv, b in base.items()))

    rows = []
    for mode in MODES:
        params = {**PARAMS, "scale_mode": mode}
        spikes = pd.concat([detect(data, lv, params) for lv in LEVELS], ignore_index=True)
        spikes = spikes[spikes["make"].isin(MAKES)]
        res = score_events(events, spikes, elig, levels=LEVELS)
        e = res[(res["eligible"] == 1) & res["make"].isin(MAKES)
                & (pd.to_datetime(res["report_date"]) >= START)]
        hits = onsets = 0
        expected = 0.0
        per = {}
        for lv in LEVELS:
            h, t = onset_precision(events, spikes, (lv,), start=START)
            per[lv] = (h, t)
            hits, onsets, expected = hits + h, onsets + t, expected + t * base[lv]
        rows.append(dict(mode=mode, events=len(e), recalls_flagged=int(e["first_flag"].notna().sum()),
                         recall=e["first_flag"].notna().mean(), median_lead_wk=e["lead_weeks"].median(),
                         onsets=onsets, hits=hits, precision=hits / onsets if onsets else float("nan"),
                         above_chance=(hits - expected) / onsets if onsets else float("nan"),
                         system=f"{per['system'][0]}/{per['system'][1]}", topic=f"{per['topic'][0]}/{per['topic'][1]}"))
    out = pd.DataFrame(rows).set_index("mode")
    pd.options.display.float_format = "{:.3f}".format
    print(out.to_string())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
