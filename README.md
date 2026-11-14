# Recall Radar

An early-warning system for vehicle defects.

**Business question:** Can public NHTSA complaint data flag an emerging defect before it becomes a recall, and how long does each brand take to go from first warning signs to a recall?

Backtest brands: Hyundai (incl. Genesis), Kia, Toyota, Honda, Tesla.

## Status

| # | Plan item | Status |
|---|-----------|--------|
| 1 | SQL database linking complaints, recalls, investigations (make/model/year/component) | Schema in `sql/schema.sql`; complaints ingest done (`src/ingest_complaints.py`); recalls ingest done (`src/ingest_recalls.py`); investigations ingest done (`src/ingest_investigations.py`); `component_map` built (`src/build_component_map.py`) |
| 2 | Sales by model (complaints per vehicle sold) | Partial: Hyundai and Kia 2018-2025, Toyota 2022-2025, Honda 2024-2025 loaded (`data/sales/us_sales.csv`, `src/ingest_sales.py`, see `docs/sales_sources.md`); Tesla, Genesis and older years missing; `model_family` alias map built (`src/build_model_family.py`); tested in the detector on Hyundai + Kia (`src/sales_experiment.py`, `scale_mode="sales"`): no clear gain over the default, so the default is unchanged |
| 3 | Text mining: topics (powertrain, electrical, infotainment, driver assistance) + sentiment | Tagging done (`src/mine_text.py`, lexicon in `src/topics.py` -> `complaint_text`, `recall_text`) and used as a third spike-detector level; sentiment computed but not yet used |
| 4 | Spike detector on model/component complaint rates | Done at system, subsystem and text-topic level (`src/detect_spikes.py` -> `spikes`); thresholds re-tuned on system + topic series (`src/tune.py`); sales normalization still to do |
| 5 | Backtest on past recalls, all five brands: how early would it have fired? | Done (`src/backtest.py` -> `backtest`); result is weak, see Result |
| 6 | Recall latency (first clustering -> recall date) by brand and component | First version done (`src/latency.py` -> `recall_latency`): detector warning lead + investigation-to-recall time; brand differences are within noise |
| 7 | Weekly GitHub Action refresh | Written and tested locally end to end (`.github/workflows/weekly-refresh.yml`, `src/refresh.py`, `src/export_reports.py`); not yet run on GitHub |
| 8 | Tableau Public dashboard + one-page recommendation | Recommendation drafted (`docs/recommendation.md`); dashboard built as a Claude artifact (https://claude.ai/artifact/B1j2qwqLQDiu9LLgEeawVd) from `reports/latest`; Tableau Public version not done |

`src/filter_complaints.py` is the original case study: the ICCU-recalled vs. non-recalled E-GMP models (Ioniq 5/6, EV6, GV60...). It is the Hyundai worked example for the backtest, not the whole project.

## Setup

```
pip install -r requirements.txt
python src/ingest_complaints.py data/raw/nhtsa/<date> data/recall_radar.db
python src/ingest_recalls.py data/raw/nhtsa/<date> data/recall_radar.db
python src/ingest_investigations.py data/raw/nhtsa/<date> data/recall_radar.db
python src/build_component_map.py data/recall_radar.db   # after the three ingests
python src/ingest_sales.py data/recall_radar.db   # sales by model, hand-collected CSV
python src/build_model_family.py data/recall_radar.db   # variants/renames -> families, after the ingests
python src/detect_spikes.py data/recall_radar.db
python src/backtest.py data/recall_radar.db
python src/mine_text.py data/recall_radar.db   # ~3 min; --audit shows lexicon term counts
python src/latency.py data/recall_radar.db
python src/tune.py data/recall_radar.db        # optional, ~6 min, writes reports/tuning_results.csv
```

Raw NHTSA flat files go in `data/raw/` (git-ignored).

## Weekly refresh

`.github/workflows/weekly-refresh.yml` runs Mondays 12:00 UTC (and on demand from the Actions tab): it downloads the NHTSA flat files, rebuilds the database with `python src/refresh.py --download`, and commits the small files in `reports/latest/` (`alerts.csv` = new spike alerts this week, `spikes.csv`, `backtest.csv`, `recall_latency.csv`, `summary.json`). The database is not committed. A sanity gate fails the run, before any report is overwritten, if complaint, recall or investigation counts drop more than 2% from the last run.

## Data notes

- Complaints are one row per (complaint, component). Count `DISTINCT odino`.
- NHTSA component strings differ between complaints and recalls; joining needs the `component_map` table, so expect fuzzy matches and document them.
- Recalls are one row per (campaign, make, model, year); count `DISTINCT campno`. `report_date` is RCDATE (manufacturer report received by NHTSA).
- Investigations are one row per (investigation, make, model, year, campaign): count `DISTINCT nhtsa_id`. `campno` links an investigation to the recall(s) it led to (`recalls.campno`); one investigation can link to many campaigns, and most have none.
- `component_map` covers every raw component string in all three tables (`system` = level-1 name made consistent, e.g. ENGINE AND ENGINE COOLING -> ENGINE; `component_group` = topic bucket). NHTSA has no infotainment category, so that bucket is a proxy (instrument cluster, rear-camera display, communication) and a few large recall campaigns dominate it; refine with text mining. Rules are in the script; review them before trusting group-level results.
- `spikes` flags (make, model, system, month) when the trailing 3-month complaint count is >=3x a model-scaled 24-month baseline (Poisson p<0.001, >=5 complaints). `onset=1` marks the first month of an episode; the backtest should use onset rows that precede a recall. Parameters are constants at the top of the script. No fleet-size adjustment yet, and complaints surge after recall announcements.
- `backtest` scores each recall event (campaign x make x model x system) against `spikes` in the 12 months before `report_date`. Headline uses "clean" flags (not within 6 months after another recall in the same series, since recalls trigger complaint surges). Eligible = series with >=30 complaints and enough history.
- `component_map.subsystem` keeps NHTSA's second level (e.g. ELECTRICAL SYSTEM:SOFTWARE); many complaints only have level 1, so subsystem series are thin. Model year is pooled on purpose: splitting by model year was tested and did worse (see below).
- `tune.py` uses a time split (cutoff 2021-01-01) and F0.5 of recall and episode precision, with a no-skill baseline. The baseline is all eligible series-months, which understates the chance rate for busy series (they get more recalls), so the true lift is, if anything, smaller.
- `topic` spikes use the keyword tags in `complaint_text` (a complaint can be in several topics); recalls are matched through the same tags on the defect text (`recall_text`). Topic tags mean "mentions", so topic series are broad (powertrain is 31% of complaints) and their chance rate is high; always compare precision with `tune.baseline_precision` for the same level.
- `model_family` maps complaint variants (SANTA FE SPORT, PRIUS PRIME, ...) and renamed models (K5 -> OPTIMA, CARNIVAL -> SEDONA) to the family names sales use; `sales_by_family` is the sales view to join on. Rules are in the script; 95-99% of 2018+ complaints for the four brands with sales fall in a family that has sales rows (sales cover 2018-2025 for Hyundai, Kia, Toyota and Honda; Genesis and Tesla have none).
- Sales normalization test (Hyundai, Kia, Toyota, Honda, 2020+, 706 recall events, 172-326 spike episodes per variant): the default "others" scaling flagged 62 recalls (8.8%) on 172 episodes at 19.8% precision (+10.2 points above chance); scaling by trailing-12-month sales flagged 79 (11.2%) on 258 episodes at 19.0% (+9.6); no scaling flagged 102 (14.4%) on 326 episodes at 18.7% (+9.2). Precision above chance is the same within noise, and the sales variant only adds alerts, so sales scaling is a workload trade-off, not an accuracy gain. The default stays. (Earlier Hyundai + Kia-only run: 28 / 36 / 43 flagged, same conclusion.)
- Model-year test (`src/model_year_experiment.py`, system level, each make/model/model year its own series with its own baseline and clock, recalls expanded to the model years they cover): only 435 of 1,111 testable campaigns still had a model-year series with >= 30 complaints, and on those 435 the pooled detector warned 90 (20.7%) vs 59 (13.6%) for model-year series, median lead 32.5 vs 29.9 weeks. Precision above chance fell from +10.7 to +8.7 points overall and from +8.4 to +4.7 from 2021 on (6.6% precision on 196 episodes). The model-year series caught 13 campaigns the pooled one missed, so using both would warn 12.6% of campaigns instead of 11.4% at the cost of 962 extra episodes. Not adopted: model year stays pooled.
- NHTSA make `GENESIS` also covers pre-2015 non-Hyundai items (e.g. 1993 equipment recalls); filter to 2015+ for the Genesis brand.
- Tesla does not publish sales by model; any figures are estimates and must be labeled as such.

## Result (fill in once the backtest exists)

> Data as of 2026-11-01, thresholds tuned on pre-2021 recalls (system + topic series). Recall: system + topic series flag 217 of 2,242 eligible recall events (9.7%; 10.2% in 2021+), a median of 30 weeks before announcement (adding subsystem: 227, 10%). Precision, the share of clean spike episodes followed by a same-series recall within 12 months, beats each level's own no-skill rate: system 16.4% vs 5.7%, topic 38.5% vs 14.1% (2021+ only: 15.8% vs 7.4% and 40.0% vs 19.3%, the topic figure on just 50 episodes); subsystem is 4.5% vs 1.9% and is not recommended. Topic series catch 57 recalls that system series miss. Overall the detector is a modest early warning: it finds about 1 in 10 recalls, mostly high-volume defects, with 2-3x better-than-chance precision. Re-tuning raised the training objective from 0.076 to 0.123 but the held-out (2021+) objective only from 0.106 to 0.114, which is within noise, so treat the thresholds as reasonable rather than optimal.

## Recall latency

> Of 1,129 testable recall campaigns, the detector warned on 158 (14%), a median of 35 weeks early. By brand the warned share ranges 9-24% (Tesla 24%, Genesis 19% on 16 campaigns, Honda 16%, Hyundai 14%, Toyota 13%, Kia 9%) and median lead 32-40 weeks (Tesla 40, Honda 35, Kia 34, Toyota 34, Genesis 33, Hyundai 32); the lead ranges overlap, and the warned share mostly reflects how many complaints each model draws, not how fast the manufacturer acts, so no brand is shown to be faster. Official path: for the 140 recalls NHTSA links to an investigation, the median time from investigation opening to recall is 22 weeks (Hyundai 20, Toyota 23, Honda 24, Kia 31; Tesla has 1 linked case).

A first attempt measured weeks since 5 complaints arrived within 90 days. It was dropped: on dates with no recall it gave nearly the same answer (cluster found for 19% of non-recall dates vs 23% of recalls), because busy series always have such clusters. It measures complaint volume, not warning time.

## Recommendation

Draft in [docs/recommendation.md](docs/recommendation.md): use complaint spikes as a weekly triage watch list, not a forecast; they catch about 1 in 10 recalls, 7 to 9 months early, with 3 to 3.5x better-than-chance precision at the component level and 2.5x at the topic level; no defensible brand speed ranking yet.
