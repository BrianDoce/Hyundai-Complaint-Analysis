# US sales data: sources, coverage and caveats

`data/sales/us_sales.csv` holds US calendar-year unit sales by model (427 rows, 71 models). Load it with
`python src/ingest_sales.py data/recall_radar.db`. Every row carries the page it came from in `source_url`.

## Source and method

Tables were read from best-selling-cars.com year-end pages (a third-party aggregator of manufacturer
sales reports). The README originally planned manufacturer press releases; the aggregator was chosen
for coverage and speed. Each page shows two years. Before a page's rows were accepted, the model rows
were summed and compared with the page's printed total.

## Coverage

| Brand | Years with model-level rows | Notes |
|---|---|---|
| Hyundai | 2018-2025 | Genesis brand not collected (about 800 complaints) |
| Kia | 2018-2025 | |
| Toyota | 2018-2025 | Toyota-division models only (Lexus excluded) |
| Honda | 2018-2025 | Honda-division models only (Acura excluded) |
| Tesla | none | Tesla does not report by model; any figures must be estimates (`is_estimate = 1`) |

Toyota 2018-2021 and Honda 2018-2023 were added later. On those pages the model tables are images of the
manufacturers' own year-end sales summaries, so the numbers were read from the images by eye and each year
was checked against the printed Toyota Division / Honda Division total (below). Image sources:
Toyota 2020-2021 `.../2021-full-year-usa-toyota-and-lexus-sales-by-model/`, Toyota 2018-2019
`.../2019-full-year-usa-toyota-and-lexus-sales/`, Honda 2018-2019 `.../2019-full-year-usa-honda-and-acura-brand-sales/`,
Honda 2020-2021 `.../2021-full-year-usa-honda-and-acura-sales-by-model/`, Honda 2022
`.../2022-full-year-usa-honda-and-acura-sales-by-model/`, Honda 2023 (page already used for 2024).
Remaining gap: 2026 (no year-end data yet) and Genesis/Tesla.

## Reconciliation (model rows vs printed total)

Exact match except these, all with the printed total higher than the listed models, so the page omits a
model or rounds. Nothing was filled in from memory.

| Brand / year | Rows sum | Printed total | Diff |
|---|---|---|---|
| Hyundai 2018 | 667,005 | 667,634 | -629 (0.09%) |
| Kia 2022 | 693,548 | 693,549 | -1 |
| Kia 2024 | 794,571 | 796,488 | -1,917 (0.24%) |
| Toyota 2024 | 1,986,939 | 1,986,954 | -15 |
| Toyota 2025 | 2,147,805 | 2,147,811 | -6 |
| Toyota 2018 | 2,128,358 | 2,128,363 | -5 (2 are Scion tC, not stored) |
| Toyota 2019 | 2,085,234 | 2,085,235 | -1 |
| Honda 2023 | 1,162,530 | 1,162,531 | -1 |

Toyota 2020, 2021 and Honda 2018-2022 match their printed division totals exactly.

Other things seen on the source pages: Hyundai Accent 2023 is listed as 31 units (vs 17,823 in 2022) and
is kept as printed (the row sum still matches the page total); the Kia 2022 Stinger was printed as
"7.809" and read as 7,809.

## Naming conventions

Toyota's 86 (GR86 from 2022) is stored as `86` for 2018-2021 and `GR86` for 2022 on, and both map to family
`86` (as does FR-S). Yaris iA maps to YARIS, Clarity Fuel Cell to CLARITY. Single-digit rows (FJ Cruiser 1,
Venza 9 in 2018-2019) are kept as printed.

Model names are NHTSA's spelling, upper-case. Where the source combines a renamed model in one row,
the row is stored under the older NHTSA name: `K5/Optima` -> OPTIMA (2020, 2021), `K4/Forte` -> FORTE
(2024, 2025), `Carnival/Sedona` -> SEDONA (2020, 2021). Later years use the new name (K5, CARNIVAL).
Sales are per model family, whereas complaints also carry variants (SANTA FE SPORT, SONATA HYBRID,
PRIUS PRIME, ...). A model-family alias map is needed before dividing complaints by sales.

## Known data issues to keep in mind

- These are manufacturer-reported sales (deliveries or retail, depending on the brand and year), not
  vehicles in operation; fleet size lags and sums several model years.
- Sales are per calendar year while complaints are tagged by the model, not model year, so older
  vehicles still draw complaints long after they stop selling.
