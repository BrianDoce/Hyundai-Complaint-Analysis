"""Export small, dashboard-ready CSVs and a run summary from the finished database.

Writes to the output directory (default reports/latest):
  alerts.csv          spike onsets (system and topic series) in the last two months of data:
                      what an analyst should look at this week
  spikes.csv          every flagged month at all levels, for trend charts
  backtest.csv        one row per recall event with the detector's lead time
  recall_latency.csv  one row per recall campaign
  summary.json        run date, data-through date, row counts and headline backtest numbers

The database itself is large and not committed; these files are small enough to be.
The weekly GitHub Action commits them.

Usage:
    python src/export_reports.py data/recall_radar.db [reports/latest]
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from detect_spikes import PARAMS

ALERT_LEVELS = ("system", "topic")   # subsystem series are not recommended (see README)
ALERT_MONTHS = 2


def counts(con):
    return dict(
        complaints=con.execute("SELECT COUNT(DISTINCT odino) FROM complaints").fetchone()[0],
        recall_campaigns=con.execute("SELECT COUNT(DISTINCT campno) FROM recalls").fetchone()[0],
        investigations=con.execute("SELECT COUNT(DISTINCT nhtsa_id) FROM investigations").fetchone()[0],
    )


def export(db_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)

    data_through = con.execute("SELECT MAX(received) FROM complaints").fetchone()[0]
    spikes = pd.read_sql_query("SELECT * FROM spikes ORDER BY level, make, model, series, month", con)
    last = pd.Period(data_through[:7], "M")
    recent = [str(last - i) for i in range(ALERT_MONTHS)]
    alerts = spikes[(spikes["onset"] == 1) & spikes["level"].isin(ALERT_LEVELS)
                    & spikes["month"].isin(recent)].sort_values(["ratio"], ascending=False)

    bt = pd.read_sql_query("SELECT * FROM backtest ORDER BY report_date, campno", con)
    lat = pd.read_sql_query("SELECT * FROM recall_latency ORDER BY report_date, campno", con)
    elig = bt[bt["eligible"] == 1]
    flagged = elig[elig["first_flag"].notna()]

    alerts.to_csv(out / "alerts.csv", index=False)
    spikes.to_csv(out / "spikes.csv", index=False)
    bt.to_csv(out / "backtest.csv", index=False)
    lat.to_csv(out / "recall_latency.csv", index=False)

    summary = dict(
        run_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        data_through=data_through,
        **counts(con),
        alert_months=recent,
        n_alerts=int(len(alerts)),
        backtest=dict(recall_events=int(len(bt)), eligible_events=int(len(elig)),
                      flagged_events=int(len(flagged)),
                      flagged_share=round(len(flagged) / max(len(elig), 1), 4),
                      median_lead_weeks=None if flagged.empty else round(float(flagged["lead_weeks"].median()), 1)),
        thresholds={k: PARAMS[k] for k in ("window", "base_months", "min_ratio", "alpha", "min_count", "scale_mode")},
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {len(alerts)} alerts for {', '.join(recent)}; data through {data_through} -> {out}")
    return summary


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    export(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else "reports/latest")
