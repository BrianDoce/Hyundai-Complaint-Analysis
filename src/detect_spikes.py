"""Flag complaint spikes per (make, model, system) and store them in `spikes`.

Series: monthly count of DISTINCT complaints (by `received` month) for each
make/model and component_map.system, with model years pooled. A month is
flagged when the trailing 3-month count is far above the series' own
baseline:

  baseline rate = mean monthly count over the up-to-24 months before the window
                  (needs >= 12 months of history since the model's first
                  complaint, floored at MIN_RATE so quiet series can't divide by ~0)
  expected      = 3 * baseline rate * model scale
  model scale   = growth of the model's complaints that touch NOT this system
                  (window rate / baseline rate, floored at 1), so model-wide
                  surges (a launch ramp, a publicized issue, a bulk upload)
                  don't flag every system at once
  flag          = count >= MIN_COUNT and count / expected >= MIN_RATIO
                  and Poisson upper-tail p < ALPHA

The ratio and count guards matter: complaint counts are burstier than Poisson,
so p alone over-flags busy series. Known limits: no fleet-size adjustment yet
(sales data will replace the model scale), and complaints surge after a recall is announced, so the backtest must only
count flags that precede the recall.

Run after ingest_complaints.py and build_component_map.py.

Usage:
    python src/detect_spikes.py data/recall_radar.db
"""
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW = 3          # months in the trailing window
BASE_MONTHS = 24    # max baseline length
MIN_HISTORY = 12    # min baseline months before a series can be flagged
MIN_RATE = 0.25     # floor on baseline complaints per month
MIN_COUNT = 5       # min complaints in the window
MIN_RATIO = 3.0     # min count / expected
ALPHA = 1e-3
MIN_TOTAL = 30      # skip series with fewer total complaints


def poisson_sf(k, lam):
    """P(X >= k) for X ~ Poisson(lam)."""
    cdf = 0.0
    for i in range(k):
        cdf += math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1))
    return max(0.0, 1.0 - cdf)


def load_counts(con):
    df = pd.read_sql_query(
        """SELECT x.make, x.model, m.system, substr(x.received, 1, 7) AS month,
                  COUNT(DISTINCT x.odino) AS n
           FROM complaints x JOIN component_map m ON m.raw_component = COALESCE(x.component, '')
           WHERE x.received IS NOT NULL
           GROUP BY 1, 2, 3, 4""", con)
    totals = pd.read_sql_query(
        """SELECT make, model, substr(received, 1, 7) AS month, COUNT(DISTINCT odino) AS total
           FROM complaints WHERE received IS NOT NULL GROUP BY 1, 2, 3""", con
    ).set_index(["make", "model", "month"])["total"]
    # A model's clock starts at its first complaint in any system, so a system
    # with no complaints yet counts as zeros rather than as missing history.
    start = df.groupby(["make", "model"])["month"].min().rename("start")
    return df, start, totals


def detect(df, start, totals):
    last = pd.Period(df["month"].max(), "M")
    totals_by_model = {k: g.droplevel([0, 1]) for k, g in totals.groupby(level=[0, 1])}
    out = []
    for (make, model, system), g in df.groupby(["make", "model", "system"]):
        if g["n"].sum() < MIN_TOTAL:
            continue
        idx = pd.period_range(start[(make, model)], last, freq="M")
        s = g.set_index(pd.PeriodIndex(g["month"], freq="M"))["n"].reindex(idx, fill_value=0)
        counts = s.to_numpy(dtype=float)
        # Complaints in this model that touch no component in this system.
        tot = totals_by_model[(make, model)].reindex(idx.astype(str), fill_value=0).to_numpy(dtype=float)
        others = tot - counts
        owin = pd.Series(others).rolling(WINDOW).sum().to_numpy() / WINDOW
        win = pd.Series(counts).rolling(WINDOW).sum().to_numpy()
        for t in range(WINDOW - 1 + MIN_HISTORY, len(counts)):
            k = int(win[t])
            if k < MIN_COUNT:
                continue
            base = counts[max(0, t - WINDOW + 1 - BASE_MONTHS): t - WINDOW + 1]
            obase = others[max(0, t - WINDOW + 1 - BASE_MONTHS): t - WINDOW + 1].mean()
            scale = max(1.0, owin[t] / max(obase, MIN_RATE))
            expected = WINDOW * max(base.mean(), MIN_RATE) * scale
            ratio = k / expected
            if ratio < MIN_RATIO:
                continue
            p = poisson_sf(k, expected)
            if p < ALPHA:
                prev = out[-1] if out else None
                onset = int(not (prev and prev[:3] == (make, model, system)
                                 and pd.Period(prev[3], "M") == idx[t] - 1))
                out.append((make, model, system, str(idx[t]), k, expected, ratio, p, onset))
    return out


def main(db_path):
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS spikes")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    df, start, totals = load_counts(con)
    rows = detect(df, start, totals)
    con.executemany("INSERT INTO spikes VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    series = df.groupby(["make", "model", "system"]).ngroups
    print(f"{len(rows):,} flagged months, {sum(r[8] for r in rows):,} episodes, "
          f"{len({r[:3] for r in rows}):,} series flagged (of {series:,}) -> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
