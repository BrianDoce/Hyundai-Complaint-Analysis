# Recall Radar

An early-warning system for vehicle defects.

**Business question:** Can public NHTSA complaint data flag an emerging defect before it becomes a recall, and how long does each brand take to go from first warning signs to a recall?

Backtest brands: Hyundai (incl. Genesis), Kia, Toyota, Honda, Tesla.

## Status

| # | Plan item | Status |
|---|-----------|--------|
| 1 | SQL database linking complaints, recalls, investigations (make/model/year/component) | Schema in `sql/schema.sql`; complaints ingest done (`src/ingest_complaints.py`); recalls ingest done (`src/ingest_recalls.py`); investigations ingest done (`src/ingest_investigations.py`); `component_map` built (`src/build_component_map.py`) |
| 2 | Sales by model from press releases (complaints per vehicle sold) | TODO (`sales` table) |
| 3 | Text mining: topics (powertrain, electrical, infotainment, driver assistance) + sentiment | TODO |
| 4 | Spike detector on model/component complaint rates | Done at system + subsystem level (`src/detect_spikes.py` -> `spikes`); time-split tuning (`src/tune.py`) found no better thresholds; sales normalization still to do |
| 5 | Backtest on past recalls, all five brands: how early would it have fired? | Done (`src/backtest.py` -> `backtest`); result is weak, see Result |
| 6 | Recall latency (first clustering -> recall date) by brand and component | TODO |
| 7 | Weekly GitHub Action refresh | TODO |
| 8 | Tableau Public dashboard + one-page recommendation | TODO |

`src/filter_complaints.py` is the original case study: the ICCU-recalled vs. non-recalled E-GMP models (Ioniq 5/6, EV6, GV60...). It is the Hyundai worked example for the backtest, not the whole project.

## Setup

```
pip install -r requirements.txt
python src/ingest_complaints.py data/raw/nhtsa/<date> data/recall_radar.db
python src/ingest_recalls.py data/raw/nhtsa/<date> data/recall_radar.db
python src/ingest_investigations.py data/raw/nhtsa/<date> data/recall_radar.db
python src/build_component_map.py data/recall_radar.db   # after the three ingests
python src/detect_spikes.py data/recall_radar.db
python src/backtest.py data/recall_radar.db
python src/tune.py data/recall_radar.db        # optional, ~6 min, writes reports/tuning_results.csv
```

Raw NHTSA flat files go in `data/raw/` (git-ignored).

## Data notes

- Complaints are one row per (complaint, component). Count `DISTINCT odino`.
- NHTSA component strings differ between complaints and recalls; joining needs the `component_map` table, so expect fuzzy matches and document them.
- Recalls are one row per (campaign, make, model, year); count `DISTINCT campno`. `report_date` is RCDATE (manufacturer report received by NHTSA).
- Investigations are one row per (investigation, make, model, year, campaign): count `DISTINCT nhtsa_id`. `campno` links an investigation to the recall(s) it led to (`recalls.campno`); one investigation can link to many campaigns, and most have none.
- `component_map` covers every raw component string in all three tables (`system` = level-1 name made consistent, e.g. ENGINE AND ENGINE COOLING -> ENGINE; `component_group` = topic bucket). NHTSA has no infotainment category, so that bucket is a proxy (instrument cluster, rear-camera display, communication) and a few large recall campaigns dominate it; refine with text mining. Rules are in the script; review them before trusting group-level results.
- `spikes` flags (make, model, system, month) when the trailing 3-month complaint count is >=3x a model-scaled 24-month baseline (Poisson p<0.001, >=5 complaints). `onset=1` marks the first month of an episode; the backtest should use onset rows that precede a recall. Parameters are constants at the top of the script. No fleet-size adjustment yet, and complaints surge after recall announcements.
- `backtest` scores each recall event (campaign x make x model x system) against `spikes` in the 12 months before `report_date`. Headline uses "clean" flags (not within 6 months after another recall in the same series, since recalls trigger complaint surges). Eligible = series with >=30 complaints and enough history.
- `component_map.subsystem` keeps NHTSA's second level (e.g. ELECTRICAL SYSTEM:SOFTWARE); many complaints only have level 1, so subsystem series are thin. Model year is still pooled.
- `tune.py` uses a time split (cutoff 2021-01-01) and F0.5 of recall and episode precision, with a no-skill baseline. The baseline is all eligible series-months, which understates the chance rate for busy series (they get more recalls), so the true lift is, if anything, smaller.
- NHTSA make `GENESIS` also covers pre-2015 non-Hyundai items (e.g. 1993 equipment recalls); filter to 2015+ for the Genesis brand.
- Tesla does not publish sales by model; any figures are estimates and must be labeled as such.

## Result (fill in once the backtest exists)

> Data as of 2026-11-01, threshold search on pre-2021 recalls, scored on 2021+. At the default thresholds the detector flagged 185 of 2,096 eligible recalls (9%) a median of 30 weeks before announcement (system and subsystem series combined; subsystem alone adds little). But precision is close to chance: 8% of clean spike episodes were followed by a recall in the same series within 12 months, versus 7% for a randomly chosen series-month in the 2021+ test period (5% vs 7% in train/test splits of the baseline). Tuning did not help: the best train thresholds gave 10% precision in train and 8% in test. Recall rises with complaint volume (earlier cut: 0% with <5 prior-year complaints, 31% with 50+). Complaint spikes alone are a weak recall predictor; see Recommendation.

## Recommendation

TODO
