"""Run the whole Recall Radar pipeline end to end: download, load, analyze, export.

Steps, in order:
  1. download NHTSA flat files (complaints, recalls pre/post 2010, investigations)   [--download]
  2. load complaints, recalls, investigations, sales
  3. sanity gate: abort if the new data is clearly truncated compared with the last run
  4. component_map, model_family, text mining, spike detector, backtest, recall latency
  5. export small CSVs and summary.json to the reports directory

The gate protects the committed reports: if a download comes back short (NHTSA
hiccup, partial file), the run fails before anything is overwritten. It compares
the new row counts with the previous summary.json and fails on a drop of more
than GATE_DROP. Counts normally only grow.

Usage:
    python src/refresh.py --download                       # what the weekly GitHub Action runs
    python src/refresh.py --raw-dir data/raw/nhtsa/2026-11-01 --db data/recall_radar.db
Options: --db PATH (default data/recall_radar.db), --reports-dir PATH (default reports/latest)
"""
import argparse
import json
import sys
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
BASE = "https://static.nhtsa.gov/odi/ffdd"
FILES = {
    "FLAT_CMPL.zip": f"{BASE}/cmpl/FLAT_CMPL.zip",
    "FLAT_RCL_POST_2010.zip": f"{BASE}/rcl/FLAT_RCL_POST_2010.zip",
    "FLAT_RCL_PRE_2010.zip": f"{BASE}/rcl/FLAT_RCL_PRE_2010.zip",
    "FLAT_INV.zip": f"{BASE}/inv/FLAT_INV.zip",
}
GATE_DROP = 0.02   # fail if a count falls more than 2% below the previous run


def download(raw_dir, tries=3):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = raw_dir / name
        for attempt in range(1, tries + 1):
            try:
                print(f"downloading {url}", flush=True)
                urllib.request.urlretrieve(url, dest)
                with zipfile.ZipFile(dest) as zf:      # also validates the archive
                    zf.extractall(raw_dir)
                dest.unlink()
                break
            except Exception as e:                       # network error or corrupt zip
                if attempt == tries:
                    sys.exit(f"download failed for {url}: {e}")
                print(f"  attempt {attempt} failed ({e}); retrying", flush=True)
                time.sleep(10 * attempt)


def gate(current, previous_summary_path):
    """Raise SystemExit if any count dropped by more than GATE_DROP vs the previous summary."""
    if not previous_summary_path.exists():
        print("gate: no previous summary, skipping")
        return
    prev = json.loads(previous_summary_path.read_text())
    bad = [f"{k}: {current[k]:,} vs {prev[k]:,}" for k in ("complaints", "recall_campaigns", "investigations")
           if k in prev and current[k] < prev[k] * (1 - GATE_DROP)]
    if bad:
        sys.exit("gate failed, new data looks truncated: " + "; ".join(bad))
    print("gate ok:", {k: f"{current[k]:,} (was {prev.get(k, 0):,})" for k in current})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="fetch NHTSA flat files into --raw-dir first")
    ap.add_argument("--raw-dir", default=None, help="default: data/raw/nhtsa/<today>")
    ap.add_argument("--db", default=str(ROOT / "data" / "recall_radar.db"))
    ap.add_argument("--reports-dir", default=str(ROOT / "reports" / "latest"))
    a = ap.parse_args()
    raw = Path(a.raw_dir) if a.raw_dir else ROOT / "data" / "raw" / "nhtsa" / date.today().isoformat()
    reports = Path(a.reports_dir)

    if a.download:
        download(raw)

    # Imported here so --help works without the analysis dependencies installed.
    import sqlite3

    import backtest
    import build_component_map
    import build_model_family
    import detect_spikes
    import export_reports
    import ingest_complaints
    import ingest_investigations
    import ingest_recalls
    import ingest_sales
    import latency
    import mine_text

    ingest_complaints.main(str(raw), a.db)
    ingest_recalls.main(str(raw), a.db)
    ingest_investigations.main(str(raw), a.db)
    ingest_sales.main(a.db)

    con = sqlite3.connect(a.db)
    gate(export_reports.counts(con), reports / "summary.json")
    con.close()

    build_component_map.main(a.db)
    build_model_family.main(a.db)
    mine_text.main(a.db, False)
    detect_spikes.main(a.db)
    backtest.main(a.db)
    latency.main(a.db)
    export_reports.export(a.db, reports)


if __name__ == "__main__":
    main()
