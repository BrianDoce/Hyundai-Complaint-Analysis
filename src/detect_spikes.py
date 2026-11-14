"""Flag complaint spikes per (make, model, series) and store them in `spikes`.

Three kinds of series (`level`): 'system' (component_map.system, e.g. ELECTRICAL
SYSTEM), 'subsystem' (NHTSA's second level, e.g. ELECTRICAL SYSTEM:SOFTWARE) and
'topic' (keyword tags mined from the complaint text, src/mine_text.py; a
complaint can be in several topics and topics ignore NHTSA's component codes).
Series: monthly count of DISTINCT complaints (by `received` month), model years
pooled. A month is flagged when the trailing WINDOW-month count is far above
the series' own baseline:

  baseline rate = mean monthly count over the up-to-BASE_MONTHS months before
                  the window (needs >= MIN_HISTORY months of history since the
                  model's first complaint, floored at MIN_RATE)
  expected      = WINDOW * baseline rate * model scale
  model scale   = growth of the model's complaints that do NOT touch this
                  series (window rate / baseline rate, floored at 1), so
                  model-wide surges (a launch ramp, a publicized issue, a bulk
                  upload) don't flag every series at once
  flag          = count >= min_count and count / expected >= min_ratio
                  and Poisson upper-tail p < alpha

Thresholds live in PARAMS; src/tune.py chose them on pre-2021 recalls (system + topic
series; see reports/tuning_results_system_topic.csv). Subsystem series use the same
thresholds but were not tuned and are weak.
Known limits: no fleet-size adjustment yet (sales data will replace the model
scale), and complaints surge after a recall is announced, so the backtest must
only count flags that precede the recall.

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

LEVELS = ("system", "subsystem", "topic")
TOPIC_COLS = ("powertrain", "electrical", "infotainment", "driver_assistance")

PARAMS = dict(
    window=2,        # months in the trailing window
    base_months=24,  # max baseline length
    min_history=12,  # min baseline months before a series can be flagged
    min_rate=0.25,   # floor on baseline complaints per month
    min_count=5,     # min complaints in the window
    min_ratio=2.0,   # min count / expected
    alpha=1e-4,
    min_total=30,    # skip series with fewer total complaints
    scale_mode="others",  # how to adjust for a growing model: "others" | "sales" | "none" (see detect)
)


def poisson_sf(k, lam):
    """P(X >= k) for X ~ Poisson(lam)."""
    cdf = 0.0
    for i in range(k):
        cdf += math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1))
    return max(0.0, 1.0 - cdf)


def load_data(con):
    """Monthly distinct-complaint counts at both levels, model start months, model totals."""
    raw = pd.read_sql_query(
        """SELECT DISTINCT x.odino, x.make, x.model, m.system, m.subsystem,
                  substr(x.received, 1, 7) AS month
           FROM complaints x JOIN component_map m ON m.raw_component = COALESCE(x.component, '')
           WHERE x.received IS NOT NULL""", con)
    counts = {}
    for level in ("system", "subsystem"):
        d = raw.drop_duplicates(["odino", "make", "model", level, "month"])
        counts[level] = (d.groupby(["make", "model", level, "month"]).size()
                         .rename("n").reset_index().rename(columns={level: "series"}))
    txt = pd.read_sql_query(
        f"""SELECT x.make, x.model, x.month, t.* FROM complaint_text t JOIN
              (SELECT odino, MIN(make) AS make, MIN(model) AS model, MIN(substr(received, 1, 7)) AS month
               FROM complaints WHERE received IS NOT NULL GROUP BY odino) x USING (odino)""", con)
    long = txt.melt(id_vars=["make", "model", "month"], value_vars=list(TOPIC_COLS),
                    var_name="series", value_name="tag")
    long = long[long["tag"] == 1]
    counts["topic"] = long.groupby(["make", "model", "series", "month"]).size().rename("n").reset_index()
    totals = (raw.drop_duplicates("odino").groupby(["make", "model", "month"]).size()
              .rename("total"))
    start = totals.reset_index().groupby(["make", "model"])["month"].min()
    last = raw["month"].max()
    fam = dict(con.execute("SELECT make || '|' || model, family FROM model_family"))
    sales = {}
    for make, family, year, units in con.execute("SELECT make, family, calendar_year, units_sold FROM sales_by_family"):
        sales.setdefault((make, family), {})[year] = units
    return dict(counts=counts, start=start, totals=totals, last=last, family=fam, sales=sales)


def _trailing_mean(cs, lo, hi):
    """Mean of x[lo:hi] given cumulative sums with a leading zero; vectorized over arrays."""
    n = np.maximum(hi - lo, 1)
    return (cs[hi] - cs[lo]) / n


def exposure(idx, by_year):
    """Trailing-12-month sales for each month in idx (NaN until 12 months of sales are known).

    Annual sales are spread evenly over the year's months. Only a proxy for the
    in-service fleet: it ignores older vehicles still drawing complaints.
    """
    units = np.array([by_year.get(m.year, np.nan) / 12 for m in idx])
    return pd.Series(units).rolling(12).sum().to_numpy()


def sales_scale(E, hi, lo, t):
    """Growth in trailing-12-month sales from the baseline months to the window end; NaN if unknown."""
    known = ~np.isnan(E)
    cs = np.concatenate([[0.0], np.cumsum(np.where(known, E, 0.0))])
    cc = np.concatenate([[0], np.cumsum(known)])
    full = (cc[hi] - cc[lo]) == (hi - lo)
    base = np.where(full & (hi > lo), (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        return E[t] / base


def detect(data, level, params=PARAMS):
    """Return a DataFrame of flagged months for one level.

    scale_mode picks the growth adjustment applied to the baseline:
      others  growth of the model's other complaints (default; also catches publicity surges)
      sales   growth of the model's trailing-12-month sales, falling back to "others" where
              sales are unknown
      none    no adjustment
    """
    p = params
    W, B = p["window"], p["base_months"]
    last = pd.Period(data["last"], "M")
    totals_by_model = {k: g.droplevel([0, 1]) for k, g in data["totals"].groupby(level=[0, 1])}
    out = []
    for (make, model, series), g in data["counts"][level].groupby(["make", "model", "series"]):
        if g["n"].sum() < p["min_total"]:
            continue
        idx = pd.period_range(data["start"][(make, model)], last, freq="M")
        T = len(idx)
        t0 = W - 1 + p["min_history"]
        if T <= t0:
            continue
        c = (pd.Series(g["n"].to_numpy(float), index=pd.PeriodIndex(g["month"], freq="M"))
             .reindex(idx, fill_value=0).to_numpy())
        tot = totals_by_model[(make, model)].reindex(idx.astype(str), fill_value=0).to_numpy(float)
        oth = tot - c
        cs = np.concatenate([[0.0], np.cumsum(c)])
        cso = np.concatenate([[0.0], np.cumsum(oth)])
        t = np.arange(t0, T)
        k = cs[t + 1] - cs[t + 1 - W]
        hi = t + 1 - W
        lo = np.maximum(0, hi - B)
        base = _trailing_mean(cs, lo, hi)
        obase = _trailing_mean(cso, lo, hi)
        owin = (cso[t + 1] - cso[t + 1 - W]) / W
        others_scale = np.maximum(1.0, owin / np.maximum(obase, p["min_rate"]))
        mode = p.get("scale_mode", "others")
        if mode == "none":
            scale = np.ones(len(t))
        elif mode == "sales":
            fam = data["family"].get(f"{make}|{model}", model)
            by_year = data["sales"].get((make, fam))
            if by_year:
                ss = sales_scale(exposure(idx, by_year), hi, lo, t)
                scale = np.where(np.isnan(ss), others_scale, np.maximum(1.0, ss))
            else:
                scale = others_scale
        else:
            scale = others_scale
        expected = W * np.maximum(base, p["min_rate"]) * scale
        ratio = k / expected
        cand = np.flatnonzero((k >= p["min_count"]) & (ratio >= p["min_ratio"]))
        for j in cand:
            pv = poisson_sf(int(k[j]), expected[j])
            if pv < p["alpha"]:
                out.append((level, make, model, series, str(idx[t[j]]), int(k[j]),
                            float(expected[j]), float(ratio[j]), pv))
    df = pd.DataFrame(out, columns=["level", "make", "model", "series", "month",
                                    "window_n", "expected", "ratio", "p_value"])
    if df.empty:
        df["onset"] = []
        return df
    df = df.sort_values(["make", "model", "series", "month"]).reset_index(drop=True)
    per = pd.PeriodIndex(df["month"], freq="M")
    same = (df[["make", "model", "series"]].shift() == df[["make", "model", "series"]]).all(axis=1)
    prev_adjacent = same & (per.asi8 - pd.Series(per.asi8).shift().fillna(-99).to_numpy() == 1)
    df["onset"] = (~prev_adjacent).astype(int)
    return df


def main(db_path):
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS spikes")
    con.executescript((Path(__file__).parent.parent / "sql" / "schema.sql").read_text())
    data = load_data(con)
    for level in LEVELS:
        df = detect(data, level)
        con.executemany("INSERT INTO spikes VALUES (?,?,?,?,?,?,?,?,?,?)", df.itertuples(index=False))
        n_series = data["counts"][level].groupby(["make", "model", "series"]).ngroups
        print(f"{level:>9}: {len(df):,} flagged months, {int(df['onset'].sum()):,} episodes, "
              f"{df[['make', 'model', 'series']].drop_duplicates().shape[0]:,} series flagged "
              f"(of {n_series:,})")
    con.commit()
    print(f"-> {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
