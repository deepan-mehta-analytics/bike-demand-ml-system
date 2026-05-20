# v4.2.0 — Seoul Training-Data Refresh Design

**Date:** 2026-05-20
**Repo:** bike-demand-ml-system (Python ML repo)
**Cross-repo impact:** bike-demand-prediction (Shiny repo) — README prose only
**Author:** Deepan Mehta
**Status:** Design approved 2026-05-20. Ready for implementation plan via `superpowers:writing-plans`.

---

## 1. Problem Statement

The Seoul Random Forest model is the only city in the 6-city portfolio still trained on
pre-aggregated, externally-sourced data: the UCI Bike Sharing dataset (`Jan 2017 – Nov 2018`,
8,760 hourly rows) at `data/raw/seoul/seoul_bike_sharing.csv`. Every other city
(London / NYC / DC / Paris / Chicago) is trained on fresh public-source data aggregated by
this repo's own pipeline. The UCI Seoul data is 8-9 years stale, which is the single largest
data-quality gap in the portfolio.

The Seoul Metropolitan Government publishes the canonical Seoul 따릉이 (Tareungi) Public
Bicycle Rental History dataset as **OA-15182** at `data.seoul.go.kr`. The dataset is open,
keyless, and updated semi-annually with annual ZIP attachments back to 2015. Replacing the
UCI source with OA-15182 (years 2022 + 2023 + 2024) closes the staleness gap and makes
Seoul structurally consistent with the other five cities.

This spec covers the data pipeline, the schema-normalisation step, sprint shape with
explicit token-management session boundaries, and the cross-repo Shiny README edits.

---

## 2. Scope

### In scope

- `data/fetch_seoul_weather.py` — new — per-trip aggregation + Open-Meteo weather join
- `data/prepare_city_data.py` — new function `prepare_seoul_from_joined()` appended
- `.gitignore` — additions for raw OA-15182 ZIPs and extracted year CSVs
- `models/artifacts/seoul/model.pkl` + `feature_schema.json` — regenerated
- `data/raw/seoul/seoul_bike_sharing.csv` (UCI legacy) — removed
- `data/raw/seoul/{seoul_trips_hourly,seoul_weather,seoul_joined}.csv` — new intermediates, committed (DC/Paris pattern)
- `data/processed/seoul_bike_sharing.csv` — new — final 14-col training file
- `tests/test_model_accuracy.py` — Seoul threshold updated post-train
- `Dockerfile` — Seoul training command `--data` path updated
- `README.md` (Python) — Datasets table, Quick Summary, per-city RMSE table, v4.2.0 roadmap block
- `PROJECT-STATUS.md` (Python) — v4.2.0 entry, commit hash, RMSE
- Shiny repo `README.md` — Quick Summary + Project Overview + Business Problem prose refresh
- Shiny repo `PROJECT-STATUS.md` — Python row hash + v4.2.0 entry
- GitHub release `v4.2.0` on Python repo

### Out of scope

- Live station feed upgrade (`bikeList` OpenAPI endpoint) — Shiny Priority 6, unrelated; two different Seoul data sources. Do not conflate.
- South Korean public-holiday encoding — `HOLIDAY` defaults to `"No Holiday"` (consistent with all other non-Seoul cities). The signal loss vs UCI's tagged holidays is accepted as part of the consistency contract.
- 2025 partial-year data — skip; reassess at `v4.3+` once a full year is published.
- Vertex AI re-promotion — Seoul stays in MLflow Production registry. The v4.2.0 retrain is local + free; only the registered artifact updates, no new Vertex CustomJob.
- Hyperparameter tuning — same defaults as all other cities (`n_estimators=100`, seed `42`).
- Changes to `api/app.py`, `services/predictor.py`, `models/train.py`, `models/predict.py`, `models/features.py` — no code changes needed.

---

## 3. Data Sources

### Seoul OA-15182

| Property | Value |
|---|---|
| Source | Seoul Metropolitan Government — Seoul Public Data Plaza |
| URL | `https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do` |
| Coverage | Annual ZIPs 2015 → 2025 (last updated 2026-04-22) |
| Format | ZIP archives containing CSV or XLS trip records |
| Sizes | 3.43 MB (2015) up to **2,055 MB (2023)** — single year can be 2 GB |
| Grain | Per-trip records (`rental_id, start_time, station_id, bike_id, …`) — **not** pre-aggregated hourly |
| Update cadence | Semi-annual (반기) |
| Auth | **None** — direct download, no key, no portal account |
| Licence | 공공누리 Type 1 (Public License Type 1) — commercial use allowed, attribution required |
| Manual step | User downloads 2022 + 2023 + 2024 ZIPs → extracts CSVs into `data/raw/seoul/` |

### Open-Meteo (Seoul weather)

| Property | Value |
|---|---|
| Endpoint | `https://archive-api.open-meteo.com/v1/archive` |
| Coords | `lat=37.5665`, `lon=126.9780` (Seoul city centre) |
| Variables | `temperature_2m, relative_humidity_2m, wind_speed_10m, precipitation, snowfall, cloud_cover, dew_point_2m, shortwave_radiation` |
| Auth | None |
| Date range | Derived dynamically from trips_hourly min/max DATE (no hardcoded window) |

---

## 4. Architecture & File Manifest

### New files (Python repo)

```
data/fetch_seoul_weather.py                        ← new module — mirrors fetch_paris_weather.py
data/raw/seoul/seoul_trips_hourly.csv              ← intermediate, committed
data/raw/seoul/seoul_weather.csv                   ← intermediate, committed
data/raw/seoul/seoul_joined.csv                    ← intermediate, committed
data/processed/seoul_bike_sharing.csv              ← final 14-col training file, committed
models/artifacts/seoul/model.pkl                   ← regenerated (overwrites)
models/artifacts/seoul/feature_schema.json         ← regenerated (overwrites)
```

### Modified files (Python repo)

```
data/prepare_city_data.py     ← +prepare_seoul_from_joined() ~50 lines
.gitignore                    ← +data/raw/seoul/[0-9][0-9][0-9][0-9]*.zip
                                +data/raw/seoul/[0-9][0-9][0-9][0-9]_*.csv
tests/test_model_accuracy.py  ← Seoul threshold 450 → new_RMSE × 1.4 (post-train)
Dockerfile                    ← Seoul train --data path updated
README.md                     ← Datasets table, Quick Summary, RMSE table, v4.2.0 roadmap
PROJECT-STATUS.md             ← v4.2.0 entry, commit hash, RMSE
```

### Deleted (Python repo)

```
data/raw/seoul/seoul_bike_sharing.csv  ← UCI legacy; removed in Sprint 2 retrain commit
```

### Modified files (Shiny repo, Sprint 3 cross-repo edit)

```
README.md          ← Quick Summary + Project Overview + Business Problem prose updated
PROJECT-STATUS.md  ← Python repo row hash + v4.2.0 entry
```

### Files NOT touched (deliberate, listed to forestall scope creep)

- `models/train.py` — already polymorphic via `--city` flag.
- `services/predictor.py` — per-city lazy cache slot already exists.
- `api/app.py` — Seoul routing already works.
- `data/raw/seoul/` directory — kept; role retitled from "UCI source" to "OA-15182 raw + intermediates".

---

## 5. Data Flow

```
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 1 — User downloads (manual, Sprint 2 prerequisite)                    │
│   3 annual ZIPs from OA-15182 → extract → place all *.csv into             │
│   data/raw/seoul/                                                          │
│   Filenames typically: 2022_bike_rental.csv, 2023_bike_rental.csv, ...     │
│   Each row = one trip (rental_id, start_time, station_id, bike_id, …)      │
└────────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 2 — fetch_seoul_weather.py::load_and_aggregate_trips()                │
│   For each *.csv in data/raw/seoul/[0-9]{4}*.csv:                          │
│     _open_seoul_csv(path) — try utf-8-sig → utf-8 → cp949                  │
│     read in chunks (chunksize=500_000)                                     │
│     parse start_time → tz-naive → localise Asia/Seoul → convert UTC        │
│     floor to hour → groupby(DATE, HOUR).size() → "RENTED_BIKE_COUNT"       │
│   Concat per-year aggregates → data/raw/seoul/seoul_trips_hourly.csv       │
│   Schema: DATE (YYYY-MM-DD), HOUR (0-23), RENTED_BIKE_COUNT (int)          │
└────────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 3 — fetch_seoul_weather.py::fetch_weather()                           │
│   Open-Meteo archive API call with retry (3 attempts, 2s/4s/8s backoff)    │
│   Date range derived from trips_hourly min/max DATE                        │
│   Apply shortwave_radiation W/m² × 0.0036 → SOLAR_RADIATION MJ/m²          │
│   Apply VISIBILITY = 2000 (constant; Open-Meteo no equivalent)             │
│   → data/raw/seoul/seoul_weather.csv                                       │
│   Schema: DATE, HOUR, TEMPERATURE, HUMIDITY, WIND_SPEED, VISIBILITY,       │
│           DEW_POINT_TEMPERATURE, SOLAR_RADIATION, RAINFALL, SNOWFALL       │
└────────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 4 — Inner-join trips_hourly + weather on (DATE, HOUR)                 │
│   → data/raw/seoul/seoul_joined.csv                                        │
│   Drops edge hours where weather is missing (rare; accepted)               │
└────────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 5 — prepare_seoul_from_joined() in prepare_city_data.py               │
│   SEASONS from month: Mar-May→Spring, Jun-Aug→Summer, Sep-Nov→Autumn,      │
│                       Dec-Feb→Winter                                       │
│   HOLIDAY = "No Holiday" (constant)                                        │
│   FUNCTIONING_DAY = "Yes" (constant — Seoul 따릉이 operates year-round)    │
│   Select canonical 14 cols                                                 │
│   → data/processed/seoul_bike_sharing.csv                                  │
└────────────────────────────────────────────────────────────────────────────┘
                                  ↓
┌────────────────────────────────────────────────────────────────────────────┐
│ STEP 6 — python -m models.train --city seoul                                │
│           --data data/processed/seoul_bike_sharing.csv                     │
│   80/20 chronological split → RF n_estimators=100 seed 42 → RMSE           │
│   → models/artifacts/seoul/{model.pkl, feature_schema.json}                │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Final Training Schema (14 columns)

Matches all 5 sister cities exactly.

| Column | Type | Source |
|---|---|---|
| `DATE` | str `DD/MM/YYYY` | derived from joined DATE |
| `HOUR` | int 0-23 | derived from joined HOUR |
| `RENTED_BIKE_COUNT` | int | trip-count aggregation |
| `TEMPERATURE` | float °C | Open-Meteo `temperature_2m` |
| `HUMIDITY` | int % | Open-Meteo `relative_humidity_2m` |
| `WIND_SPEED` | float m/s | Open-Meteo `wind_speed_10m` |
| `VISIBILITY` | int (constant 2000) | default — Open-Meteo no equivalent |
| `DEW_POINT_TEMPERATURE` | float °C | Open-Meteo `dew_point_2m` |
| `SOLAR_RADIATION` | float MJ/m² | Open-Meteo `shortwave_radiation × 0.0036` |
| `RAINFALL` | float mm | Open-Meteo `precipitation` |
| `SNOWFALL` | float cm | Open-Meteo `snowfall` |
| `SEASONS` | str Spring/Summer/Autumn/Winter | derived from month |
| `HOLIDAY` | str `"No Holiday"` (constant) | default |
| `FUNCTIONING_DAY` | str `"Yes"` (constant) | default |

---

## 7. Error Handling, Encoding, and OOM Mitigation

### 7.1 Korean text encoding

OA-15182 CSVs may be encoded as `utf-8-sig`, plain `utf-8`, or `cp949` (legacy Korean
Windows). The fetch script tries each in order and raises with a clear message if all fail.

```python
def _open_seoul_csv(path: Path) -> pd.DataFrame:
    """Try encodings in order; raise with file path if all fail."""
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, usecols=_USECOLS, chunksize=500_000)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Could not decode {path} as utf-8-sig, utf-8, or cp949")
```

Schema probe lives inside Sprint 2 Task T5's first run — if a real downloaded CSV breaks
the cascade, fix the script in the same sprint then re-run. Sprint 1 ships the defensive
code; Sprint 2 surfaces the real-world quirks.

### 7.2 OOM mitigation for the 2 GB 2023 ZIP

Do not load whole-year CSVs into one DataFrame. Aggregate per-file before concat:

```python
def _aggregate_one_year(path: Path) -> pd.DataFrame:
    """Read CSV in chunks; aggregate to hourly inside the loop; return small DF."""
    chunks = []
    for chunk in pd.read_csv(path, chunksize=500_000, usecols=_USECOLS, encoding=_enc):
        chunk["start_time"] = pd.to_datetime(chunk["start_time"], errors="coerce")
        chunk = chunk.dropna(subset=["start_time"])
        chunk["DATE"] = chunk["start_time"].dt.date
        chunk["HOUR"] = chunk["start_time"].dt.hour
        chunks.append(
            chunk.groupby(["DATE", "HOUR"]).size().reset_index(name="RENTED_BIKE_COUNT")
        )
    yearly = (
        pd.concat(chunks)
          .groupby(["DATE", "HOUR"], as_index=False)["RENTED_BIKE_COUNT"]
          .sum()
    )
    return yearly  # ~8,760 rows, ~1 MB
```

Peak memory: one 500k-row chunk (~50-80 MB) + accumulating small aggregates. Safe on a
16 GB dev machine and a 4 GB training container.

### 7.3 Per-year column-name drift

Paris precedent: 2022 CSVs had timezone-naive timestamps, 2023+ were timezone-aware.
Likely analogous for Seoul (Korean vs romanised column names per year). Mitigation:

- `_USECOLS` declared as a candidate-name dict; cascade through alternatives per file.
- After read, assert canonical columns exist; raise naming both file and missing column.
- Per-file normalisation — do not concat raw frames; normalise → aggregate → then concat.

### 7.4 Open-Meteo failure modes

| Failure | Mitigation |
|---|---|
| HTTP 5xx (transient) | 3 attempts, exponential backoff 2s/4s/8s |
| HTTP 4xx | Fail loudly — coding error in date/coords, not transient |
| Network timeout | Wrapped in `requests.get(..., timeout=30)` |
| Partial response | Validate row count vs expected `(end_date - start_date) × 24`; raise on mismatch |

### 7.5 Timezone handling (Asia/Seoul → UTC)

```python
ts = pd.to_datetime(df["start_time"], errors="coerce")
if ts.dt.tz is None:
    ts = ts.dt.tz_localize("Asia/Seoul", ambiguous="infer", nonexistent="shift_forward")
ts = ts.dt.tz_convert("UTC")
```

Korea has no DST → `ambiguous="infer"` is safe. Output `DATE`/`HOUR` derived from UTC `ts`
so the Open-Meteo (UTC) join is exact.

### 7.6 SOLAR_RADIATION unit conversion

Open-Meteo `shortwave_radiation` is W/m². Multiply by `0.0036` to get MJ/m² to match the
UCI Seoul scale. Apply inside `fetch_weather()` before writing `seoul_weather.csv` so
`prepare_seoul_from_joined()` stays schema-pure.

### 7.7 Edge-of-range missing weather

Open-Meteo returns full days. If trip data starts mid-day (e.g. `2022-01-01 06:42`),
weather covers `00:00-23:00`. Inner-join drops the few unmatched edge rows. Accepted.

### 7.8 VISIBILITY default

Constant `2000` (UCI scale: 10m units → ~20 km, "good visibility"). RF sees zero variance
on this feature → effectively ignored. Documented in `fetch_seoul_weather.py` docstring.

### 7.9 Failure summary table

| Failure | Where | Mitigation | Fallback |
|---|---|---|---|
| CSV encoding mismatch | `_open_seoul_csv` cascade | Try 3 encodings | Raise with file path |
| OOM on 2023 ZIP | `_aggregate_one_year` chunked reads | 500k chunksize, per-file aggregate | Lower chunksize manually |
| Column name drift | `_USECOLS` candidate-name dict | Per-file normalisation | Fail with named column |
| Open-Meteo 5xx | `fetch_weather()` retry | 3 attempts, exp backoff | Manual re-run |
| Timezone DST | Korea has no DST; `ambiguous="infer"` | N/A | N/A |
| Edge missing weather | join | inner-merge drop | accepted |

---

## 8. Sprint Shape & Token-Management Session Boundaries

### Multi-session shape (canonical pattern; see [[session-shape-token-efficiency]])

| Session | Work | Cold-restart artifact |
|---|---|---|
| **S1** (now, 2026-05-20) | Brainstorm → spec → commit → `/clear` | This file |
| **S2** | `superpowers:writing-plans` → plan → commit → `/clear` | `docs/superpowers/plans/2026-05-20-seoul-data-refresh.md` |
| **S3** | Sprint 1 execute (2 commits) → `/clear` | plan + `workflow_status.md` |
| **S4** | Sprint 2 execute (download + train + commit) → `/clear` | `workflow_status.md` |
| **S5** | Sprint 3 execute (verify + cross-repo docs + release) | `workflow_status.md` |

Each session re-enters cold with ≤30% of context budget burned. The artifact column lists
what the next session reads first to restore state.

### Sprint 1 — Code foundation (no data dependency)

**Goal:** ship code that can lie in main without doing anything until Sprint 2 supplies data.

- **T1** — `data/fetch_seoul_weather.py`
  - Defensive encoding cascade (`_open_seoul_csv`)
  - `_aggregate_one_year(path)` chunked per-year aggregation
  - `fetch_weather()` Open-Meteo call with 3-attempt retry
  - `shortwave_radiation × 0.0036` SOLAR conversion
  - `VISIBILITY = 2000` constant
  - Asia/Seoul → UTC tz handling
  - `main()` driver: glob `[0-9]{4}*.csv` → aggregate → fetch weather → join → call `prepare_seoul_from_joined` → write processed CSV
- **T2** — `prepare_seoul_from_joined()` in `data/prepare_city_data.py` — mirror `prepare_paris_from_joined`
- **T3** — `.gitignore` — add raw ZIP + extracted year CSV patterns

**Commits:**
1. `feat(seoul): OA-15182 weather + per-trip aggregation fetch script` (just T1)
2. `feat(seoul): prepare_seoul_from_joined + gitignore raw ZIPs` (T2 + T3)

### Sprint 2 — Data processing + training

**Goal:** turn raw OA-15182 data into a trained Seoul artifact.

- **T4** — User downloads 2022 + 2023 + 2024 annual ZIPs from OA-15182, extracts CSVs into `data/raw/seoul/`. Disk: ~4-6 GB raw; ZIPs deleted after extraction.
- **T5** — `python -m data.fetch_seoul_weather`. Produces 4 intermediate CSVs. **Schema probe lives here** — if encoding or column-drift bugs surface, fix Sprint 1 code, re-run.
- **T6** — `python -m models.train --city seoul --data data/processed/seoul_bike_sharing.csv`. Record new RMSE. Delete `data/raw/seoul/seoul_bike_sharing.csv` (UCI legacy).

**Commit:** `feat(seoul): replace UCI 2017-2018 with OA-15182 2022-2024 (RMSE <X.XX> bikes/hr)` — stages intermediates + processed CSV + new artefacts; removes UCI file.

### Sprint 3 — Verify + ship

**Goal:** prove the new model serves correctly; align docs across both repos; release.

- **T7** — FastAPI smoke
  - `uvicorn api.app:app` locally
  - `POST /predict` with `"city": "seoul"`, sanity-check prediction is a positive number in expected range
  - Assert no Seoul-fallback warning in `services/predictor.py` stdout
  - Update `tests/test_model_accuracy.py` Seoul threshold to `new_RMSE × 1.4`
  - `pytest tests/test_model_accuracy.py -k seoul` passes
  - Update `Dockerfile` Seoul train line `--data` path
- **T8** — Python repo docs
  - `README.md`: Datasets table Seoul row, Quick Summary prose, per-city RMSE table, v4.2.0 roadmap block
  - `PROJECT-STATUS.md`: v4.2.0 row, commit hash, RMSE
- **T9** — Shiny repo cross-edit
  - `README.md`: Quick Summary + Project Overview + Business Problem all rewrite the "8,760 hourly observations Jan 2017 – Nov 2018" framing to OA-15182 2022-2024
  - `PROJECT-STATUS.md`: Python row hash + v4.2.0 entry
- **T10** — GitHub release v4.2.0 + workflow_status.md sync in both repos

**Commits:**
- Python: `test+build(seoul): update accuracy threshold and Dockerfile after OA-15182 refresh`, `docs: sync README + PROJECT-STATUS for v4.2.0`
- Shiny: `docs: refresh Seoul dataset framing for v4.2.0`

### Estimated active work

Sprint 1 ~1 hr; Sprint 2 ~30 min download + 15 min processing + 5 min train; Sprint 3 ~1 hr docs + release. Net ~3 hours active work across S3 + S4 + S5.

---

## 9. Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Korean CSV encoding breaks `pd.read_csv` | Medium | Low | 3-encoding cascade in `_open_seoul_csv`; surface during S4 T5 probe |
| R2 | 2 GB 2023 ZIP OOMs the training container | Medium | Medium | Chunked reads in `_aggregate_one_year`; peak memory ≤100 MB |
| R3 | Per-year column-name drift | Medium | Low | Candidate-name `_USECOLS` dict; per-file normalisation; fail loudly with file path |
| R4 | Open-Meteo transient 5xx | Low | Low | 3-attempt retry with backoff |
| R5 | New RMSE much worse than UCI's 328.84 | Low | Low | Threshold is post-train `× 1.4`; accept honest figure; Paris precedent (Chicago RMSE was higher than UCI Seoul too, accepted as fact) |
| R6 | Sprint 1 lands but user never downloads ZIPs | Low | Low | Sprint 1 code is inert without data; safe to live in main |
| R7 | Shiny README edits miss a "8,760 hourly" reference somewhere else in repo | Low | Low | Sprint 3 grep before commit: `grep -ri "8,760 hourly\|Jan 2017\|Nov 2018" .` in Shiny repo |
| R8 | OA-15182 file format is XLS not CSV for some years | Low | Medium | If XLS — user converts via Excel/LibreOffice before extracting to `data/raw/seoul/`; document in fetch script docstring |
| R9 | `models.train --city seoul` still reads old UCI path by default | Low | High | Sprint 3 T7 Dockerfile update + verify Sprint 2 T6 explicitly passes `--data data/processed/seoul_bike_sharing.csv` |
| R10 | MLflow Production registry doesn't auto-update on local retrain | Low | Low | Manual `mlflow.register_model` post-training if needed; document in Sprint 2 T6; acceptable to defer to v4.2.1 if it adds session overhead |

---

## 10. Success Criteria (binary)

After Sprint 3:

1. `data/processed/seoul_bike_sharing.csv` exists with canonical 14-col schema, ≥25,000 rows.
2. `python -m models.train --city seoul --data data/processed/seoul_bike_sharing.csv` completes; new RMSE recorded.
3. `tests/test_model_accuracy.py` Seoul threshold updated to `new_RMSE × 1.4`; test passes.
4. `POST /predict` with `"city": "seoul"` returns prediction from `models/artifacts/seoul/model.pkl`; no Seoul-fallback log line.
5. `data/raw/seoul/seoul_bike_sharing.csv` (UCI) absent from git tree.
6. Shiny `README.md` Quick Summary + Project Overview + Business Problem no longer reference "8,760 hourly observations Jan 2017 – Nov 2018".
7. GitHub release `v4.2.0` published on `deepan-mehta-analytics/bike-demand-ml-system`.

---

## 11. References

- [[seoul-dataset-oa-15182]] — full dataset facts and pipeline rationale (`memory/project_seoul_dataset.md`)
- [[session-shape-token-efficiency]] — multi-session shape pattern (`memory/feedback_session_shape_token_efficiency.md`)
- Paris v1.4.0 spec — `docs/superpowers/specs/2026-05-18-v1.4.0-paris-chicago-rf-design.md`
- Reference scripts — `data/fetch_paris_weather.py`, `data/fetch_chicago_weather.py`, `data/prepare_city_data.py::prepare_paris_from_joined`
- Pytest threshold convention — `tests/test_model_accuracy.py` (Phase 7, threshold = RMSE × 1.4)

---

## 12. Spec Self-Review Checklist

- [x] **Placeholders:** No "TBD" or "TODO" — the only unfilled value is the post-train RMSE itself, which Sprint 2 T6 fills in.
- [x] **Internal consistency:** Sprint shape (S8) matches success criteria (S10); file manifest (S4) matches data flow (S5).
- [x] **Scope:** Single Seoul refresh; cross-repo Shiny edits are doc-only, no R code touched. Not over-scoped.
- [x] **Ambiguity:** SOLAR_RADIATION conversion factor explicit (0.0036); VISIBILITY default explicit (2000); HOLIDAY/FUNCTIONING_DAY constants explicit; encoding cascade order explicit.
