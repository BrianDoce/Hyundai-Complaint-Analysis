# Recall Radar

An early-warning system for vehicle defects.

**Business question:** Can public NHTSA complaint data flag an emerging defect before it becomes a recall, and how long does each brand take to go from first warning signs to a recall?

Backtest brands: Hyundai (incl. Genesis), Kia, Toyota, Honda, Tesla.

## Status

| # | Plan item | Status |
|---|-----------|--------|
| 1 | SQL database linking complaints, recalls, investigations (make/model/year/component) | Schema in `sql/schema.sql`; complaints ingest done (`src/ingest_complaints.py`); recalls ingest done (`src/ingest_recalls.py`); investigations ingest done (`src/ingest_investigations.py`); `component_map` built (`src/build_component_map.py`) |
| 2 | Sales by model from press releases (complaints per vehicle sold) | TODO (`sales` table) |
| 3 | Text mining: topics (powertrain, electrical, infotainment, driver assistance) + sentiment | Tagging done (`src/mine_text.py`, lexicon in `src/topics.py` -> `complaint_text`, `recall_text`) and used as a third spike-detector level; sentiment computed but not yet used |
| 4 | Spike detector on model/component complaint rates | Done at system, subsystem and text-topic level (`src/detect_spikes.py` -> `spikes`); thresholds not retuned since topics were added; sales normalization still to do |
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
python src/mine_text.py data/recall_radar.db   # ~3 min; --audit shows lexicon term counts
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
- `topic` spikes use the keyword tags in `complaint_text` (a complaint can be in several topics); recalls are matched through the same tags on the defect text (`recall_text`). Topic tags mean "mentions", so topic series are broad (powertrain is 31% of complaints) and their chance rate is high; always compare precision with `tune.baseline_precision` for the same level.
- NHTSA make `GENESIS` also covers pre-2015 non-Hyundai items (e.g. 1993 equipment recalls); filter to 2015+ for the Genesis brand.
- Tesla does not publish sales by model; any figures are estimates and must be labeled as such.

## Result (fill in once the backtest exists)

> Data as of 2026-11-01, default thresholds. Recall: system + topic series flag 220 of 2,239 eligible recalls (9.8%), a median of 32 weeks before announcement (adding subsystem: 10.3%). Precision, the share of clean spike episodes followed by a same-series recall within 12 months, beats each level's own no-skill rate: system 14.0% vs 5.7%, topic 24.8% vs 14.1% (2021+ only: 18.6% vs 7.4% and 27.3% vs 19.3%, the topic figure on just 55 episodes), subsystem 2.8% vs 1.9% (barely). Topic series catch 45 recalls that system series miss. Overall the detector is a modest, noisy early warning: it finds about 1 in 10 recalls, mostly high-volume defects, with 2-3x better-than-chance precision. An earlier version of this note said precision was near chance; that compared pooled precision against a system-only baseline and was wrong. Thresholds were tuned before topics existed and should be re-tuned on system + topic.

## Recommendation

TODO
