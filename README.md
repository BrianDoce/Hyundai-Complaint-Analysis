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
| 4 | Spike detector on model/component complaint rates | Done at system, subsystem and text-topic level (`src/detect_spikes.py` -> `spikes`); thresholds re-tuned on system + topic series (`src/tune.py`); sales normalization still to do |
| 5 | Backtest on past recalls, all five brands: how early would it have fired? | Done (`src/backtest.py` -> `backtest`); result is weak, see Result |
| 6 | Recall latency (first clustering -> recall date) by brand and component | First version done (`src/latency.py` -> `recall_latency`): detector warning lead + investigation-to-recall time; brand differences are within noise |
| 7 | Weekly GitHub Action refresh | TODO |
| 8 | Tableau Public dashboard + one-page recommendation | Recommendation drafted (`docs/recommendation.md`); dashboard TODO |

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
python src/latency.py data/recall_radar.db
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

> Data as of 2026-11-01, thresholds tuned on pre-2021 recalls (system + topic series). Recall: system + topic series flag 217 of 2,242 eligible recall events (9.7%; 10.2% in 2021+), a median of 30 weeks before announcement (adding subsystem: 227, 10%). Precision, the share of clean spike episodes followed by a same-series recall within 12 months, beats each level's own no-skill rate: system 16.4% vs 5.7%, topic 38.5% vs 14.1% (2021+ only: 15.8% vs 7.4% and 40.0% vs 19.3%, the topic figure on just 50 episodes); subsystem is 4.5% vs 1.9% and is not recommended. Topic series catch 57 recalls that system series miss. Overall the detector is a modest early warning: it finds about 1 in 10 recalls, mostly high-volume defects, with 2-3x better-than-chance precision. Re-tuning raised the training objective from 0.076 to 0.123 but the held-out (2021+) objective only from 0.106 to 0.114, which is within noise, so treat the thresholds as reasonable rather than optimal.

## Recall latency

> Of 1,129 testable recall campaigns, the detector warned on 158 (14%), a median of 35 weeks early. By brand the warned share ranges 9-24% (Tesla 24%, Genesis 19% on 16 campaigns, Honda 16%, Hyundai 14%, Toyota 13%, Kia 9%) and median lead 32-40 weeks (Tesla 40, Honda 35, Kia 34, Toyota 34, Genesis 33, Hyundai 32); the lead ranges overlap, and the warned share mostly reflects how many complaints each model draws, not how fast the manufacturer acts, so no brand is shown to be faster. Official path: for the 140 recalls NHTSA links to an investigation, the median time from investigation opening to recall is 22 weeks (Hyundai 20, Toyota 23, Honda 24, Kia 31; Tesla has 1 linked case).

A first attempt measured weeks since 5 complaints arrived within 90 days. It was dropped: on dates with no recall it gave nearly the same answer (cluster found for 19% of non-recall dates vs 23% of recalls), because busy series always have such clusters. It measures complaint volume, not warning time.

## Recommendation

Draft in [docs/recommendation.md](docs/recommendation.md): use complaint spikes as a weekly triage watch list, not a forecast; they catch about 1 in 10 recalls, 7 to 9 months early, with 3 to 3.5x better-than-chance precision at the component level and 2.5x at the topic level; no defensible brand speed ranking yet.
