# Recall Radar

An early-warning system for vehicle defects.

**Business question:** Can public NHTSA complaint data flag an emerging defect before it becomes a recall, and how long does each brand take to go from first warning signs to a recall?

Backtest brands: Hyundai (incl. Genesis), Kia, Toyota, Honda, Tesla.

## Status

| # | Plan item | Status |
|---|-----------|--------|
| 1 | SQL database linking complaints, recalls, investigations (make/model/year/component) | Schema in `sql/schema.sql`; complaints ingest done (`src/ingest_complaints.py`); recalls ingest done (`src/ingest_recalls.py`); investigations loader TODO |
| 2 | Sales by model from press releases (complaints per vehicle sold) | TODO (`sales` table) |
| 3 | Text mining: topics (powertrain, electrical, infotainment, driver assistance) + sentiment | TODO |
| 4 | Spike detector on model/component complaint rates | TODO |
| 5 | Backtest on past recalls, all five brands: how early would it have fired? | TODO |
| 6 | Recall latency (first clustering -> recall date) by brand and component | TODO |
| 7 | Weekly GitHub Action refresh | TODO |
| 8 | Tableau Public dashboard + one-page recommendation | TODO |

`src/filter_complaints.py` is the original case study: the ICCU-recalled vs. non-recalled E-GMP models (Ioniq 5/6, EV6, GV60...). It is the Hyundai worked example for the backtest, not the whole project.

## Setup

```
pip install -r requirements.txt
python src/ingest_complaints.py data/raw/nhtsa/<date> data/recall_radar.db
python src/ingest_recalls.py data/raw/nhtsa/<date> data/recall_radar.db
```

Raw NHTSA flat files go in `data/raw/` (git-ignored).

## Data notes

- Complaints are one row per (complaint, component). Count `DISTINCT odino`.
- NHTSA component strings differ between complaints and recalls; joining needs the `component_map` table, so expect fuzzy matches and document them.
- Recalls are one row per (campaign, make, model, year); count `DISTINCT campno`. `report_date` is RCDATE (manufacturer report received by NHTSA).
- NHTSA make `GENESIS` also covers pre-2015 non-Hyundai items (e.g. 1993 equipment recalls); filter to 2015+ for the Genesis brand.
- Tesla does not publish sales by model; any figures are estimates and must be labeled as such.

## Result (fill in once the backtest exists)

> Flagged X of Y backtested recalls an average of Z weeks before announcement.

## Recommendation

TODO
