# Project Status — Bike Demand ML System (Python Backend)

> Re-entry command: `"resume bike-demand-ml-system project"`
> Companion repo: `D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction`

---

## 🌐 Ecosystem Snapshot

Both repos form a single portfolio system. Track them together here.

| Repo | Role | Current Phase | Status | Last Commit |
|------|------|--------------|--------|-------------|
| **bike-demand-ml-system** (this repo) | Python FastAPI + ML training | v4.2.0 — Seoul training data refresh (OA-15182 + Open-Meteo, 2022-2024) | ✅ Done | `64ac1d2` |
| **bike_demand_prediction** | R Shiny dashboard | v1.5.0 shipped — testthat suite (36 tests / 62 assertions) + GitHub Actions CI | ✅ Done | `9da4a6d` |

### Trained City Models

| City | Dataset | Rows | RMSE | Top Feature | Artifacts |
|------|---------|------|------|-------------|-----------|
| Seoul | OA-15182 + Open-Meteo (2022-2024) | 26,303 | **1,503.52** | HOUR (0.468) | `models/artifacts/seoul/` |
| London | Kaggle london_merged.csv | 17,414 | **316.56** | HOUR (0.71) | `models/artifacts/london/` |
| NYC | BigQuery citibike_trips (2014–2018) + Open-Meteo | 34,187 | **470.76** | HOUR (0.52) | `models/artifacts/nyc/` |
| Washington DC | Capital Bikeshare CSVs (2014–2018) + Open-Meteo | 37,663 | **119.31** | HOUR (0.62) | `models/artifacts/dc/` |
| Paris | opendata.paris.fr counter ZIPs (2022–2024) + Open-Meteo | 26,297 | **23.30** | HOUR (0.634) | `models/artifacts/paris/` ✅ |
| Chicago | Divvy quarterly CSVs (2019–2022) + Open-Meteo | 32,720 | **202.99** | HOUR + TEMPERATURE (0.39 each) | `models/artifacts/chicago/` ✅ |

### Next Milestones (Both Repos) — Priority Ordered

| Priority | Repo | Phase | Target Version | Dependency |
|----------|------|-------|---------------|------------|
| ~~1~~ | bike-demand-ml-system | ~~Phase 6 — Observability~~ | ~~v2.1.0~~ | **✅ Shipped** |
| ~~1~~ | bike-demand-ml-system | ~~Phase 4 — Pub/Sub + Dataflow~~ | ~~v3.0.0~~ | **✅ Shipped** |
| ~~1~~ | bike_demand_prediction | ~~Phase 7F — GCP Streaming Dashboard~~ | ~~v1.2.0~~ | **✅ Shipped (2026-05-16)** |
| ~~3~~ | bike-demand-ml-system | ~~Phase 5 — Vertex AI + MLflow~~ | ~~v4.0.0~~ | **✅ Shipped (2026-05-17)** |
| ~~3~~ | bike_demand_prediction | ~~Feed Health Alerting — GBFS feed status panel~~ | ~~v1.3.0~~ | **✅ Shipped (2026-05-17)** |
| ~~4~~ | bike_demand_prediction | ~~Backlog — Paris/Chicago models~~ | ~~v1.4.0~~ | **✅ Shipped (2026-05-18)** |
| ~~5~~ | bike-demand-ml-system | ~~Phase 7 — Automated Test Suite (pytest)~~ | ~~—~~ | **✅ Shipped (2026-05-18)** |
| ~~5.5~~ | bike-demand-ml-system | ~~Phase 13 — Seoul training data refresh (OA-15182 + Open-Meteo)~~ | ~~v4.2.0~~ | **✅ Shipped (2026-05-21)** |
| **6** | bike-demand-ml-system | 4-city analogous timezone bug fix (Paris/Chicago/NYC/DC) | v4.3.0 | — |
| **7** | bike_demand_prediction | Backlog — Seoul GBFS | — | External API key |
| **8** | bike_demand_prediction | Backlog — City expansion (SF/Amsterdam) | — | Data sourcing required |

---

## ✅ Completed

### ML Pipeline
* Seoul training data refreshed (v4.2.0): OA-15182 (Seoul Open Data Plaza, 2022-2024) + Open-Meteo, 26,303 hourly rows after join; DD/MM datetime parsing
* Feature engineering: `year`, `month`, `day`, `dayofweek` + one-hot (`SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`)
* Random Forest baseline: RMSE **1,503.52** bikes/hr (Seoul, chronological 80/20 split, 21,042 train / 5,261 test); scaler removed (RF is scale-invariant)
* Feature schema persisted at training time — no train/serve skew at inference

### API + Service Layer
* `api/app.py` — FastAPI: `GET /` health, `POST /predict` batch endpoint, Pydantic v2 validation
* `services/predictor.py` — per-city lazy-load singleton cache; Seoul fallback for untrained cities
* `models/predict.py` — schema-aligned inference via `reindex(fill_value=0)`

### Multi-City Training (Phase 2)
* `--city` CLI arg in `models/train.py`; per-city artifacts at `models/artifacts/<city>/`
* `city: str = "Seoul"` field on `PredictionRequest`; service layer routes to correct artifact
* **London**: Kaggle CSV prepared via `prepare_london()`; RMSE **316.56** (chronological split); HOUR dominates (0.71)
* **NYC**: BigQuery `new_york_citibike` (2014–2018) + Open-Meteo via `data/fetch_nyc_weather.py`; RMSE **470.76** (chronological split); HOUR (0.52) + year growth trend (0.12)
* `services/predictor.py`: fallback to Seoul for cities without trained artifacts; city slug map routes "new york" → nyc, "washington dc" → dc
* `data/prepare_city_data.py`: `prepare_london()`, `nyc_bigquery_sql()`, `prepare_nyc_from_joined()`, `prepare_dc_from_joined()`
* `data/fetch_dc_weather.py`: Capital Bikeshare trip aggregation + Open-Meteo join + Seoul-schema prepare for DC
* **Washington DC**: Capital Bikeshare CSVs (2014–2018) + Open-Meteo join via `data/fetch_dc_weather.py`; RMSE **119.31** bikes/hr (chronological split); HOUR dominates (0.62); 37,663 hourly rows
* `data/raw/` restructured: per-city subfolders (`seoul/`, `london/`, `nyc/`, `dc/trips/`); `requests` added to `requirements.txt`

### Infrastructure (containerisation + CI)
* `requirements.txt` — 10 packages pinned; `pytest.ini` — `pythonpath = .`
* 27 tests: 9 unit (features) + 5 API integration + 1 city default + 6 RMSE gates (`-m slow`) + 5 routing + 1 schema frozen-set guard
* `Dockerfile` — `python:3.11-slim`, non-root `appuser`, stdlib health check; inline comments moved to standalone lines (Docker parse fix, commit `1ae284f`)
* `docker-compose.yml` — fastapi service, port 8000, `USE_PUBSUB=false`; volume mount removed (artifacts baked into image)
* `.github/workflows/ci.yml` — ruff lint → pytest (trains Seoul model) → docker build → push to GHCR; all 4 jobs green on push to main

---

## ⚠️ Known Limitations

* No API authentication or rate-limiting
* No drift monitoring on inference inputs — feature importances are logged to MLflow each run but no automated alert threshold
* Paris RMSE (23.30) reflects counter MEAN normalisation (~50–500/hr scale), not raw station volume — correct behaviour
* NYC RMSE (470.76) is higher due to larger absolute trip volumes; adding weather data beyond
  temperature/humidity (e.g. actual visibility, not Open-Meteo zeros) would likely reduce it
* Dataflow streaming pipeline has **no always-free tier** (~$0.05/hr on e2-medium) — run only for demos; cancel after verification

---

## 🔜 Roadmap

### Phase 3 — Cloud Run Deployment ✅ DONE
* [x] All 4 city models baked into Docker image at build time — no volume mount required
* [x] `docker-compose.yml` — volume section removed; image is self-contained
* [x] CI publish job — `docker/build-push-action` pushes `ghcr.io/deepan-mehta-analytics/bike-demand-ml-system:{latest,sha}` to GHCR on merge to main; uses auto-injected `GITHUB_TOKEN` (no manual secrets required)
* [x] CI Job 5 (`publish-gar`) added — builds and pushes to GAR + redeploys Cloud Run on every merge to main; requires `GCP_SA_KEY` GitHub secret
* [x] README — Option 3 (GHCR pull) + Option 4 (Cloud Run gcloud deploy) documented
* [x] GitHub release `v1.0.0` published on both repos (2026-05-08)
* [x] NotebookLM PKB audit complete — 5 documents in `notebooklm/` (gitignored)
* [x] Cloud Run live: **https://bike-demand-api-246440913351.us-central1.run.app** (2026-05-15) — health check returns `{"message":"Bike Demand Prediction API is running"}`
* [x] Shiny repo `model_prediction.R` — Cloud Run URL documented in `FASTAPI_URL` comment; env var already wired, no code change required
* [x] `GCP_SA_KEY` GitHub secret added — service account `github-ci-sa` (roles/run.developer + roles/artifactregistry.writer + roles/iam.serviceAccountUser); CI Job 5 is fully active

### Phase 6 — Observability ✅ Done (v2.1.0 — commit c6fd1d0)
* [x] Structured JSON logging in `services/predictor.py` — city, inputs_hash, n_records, latency_ms → Cloud Logging (stdout, free)
* [x] `/metrics` Prometheus endpoint via `prometheus-fastapi-instrumentator==7.1.0` — pure HTTP, no GCP cost
* [x] GitHub release v2.1.0 published

### Phase 4 — Pub/Sub + Dataflow Pipeline ✅ Done (v3.0.0 — commit 2f60acb)
* [x] `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB=false` → stdout; TFL adapter for London; 1 JSON array msg per city (4 msgs/cycle)
* [x] `pipeline/dataflow_job.py` — Apache Beam: ParseMessage → 5-min FixedWindows → WindowedAgg → BigQuery sink; WindowsPath pickle fix; worker_zone rename
* [x] `config/gcp_config.yaml` — project ID, Pub/Sub topic/sub, BQ dataset/table, Dataflow config (e2-medium, us-central1-f), GBFS city URLs
* [x] `requirements-pipeline.txt` — apache-beam[gcp]==2.62.0, google-cloud-pubsub==2.26.1, pyyaml==6.0.2
* [x] `tests/test_pipeline.py` — 5 tests (GBFS/TFL schema, ParseMessage, DirectRunner e2e); auto-skipped in CI
* [x] GCP provisioning — Pub/Sub `gbfs-bike-stations` + sub, BigQuery dataset `bike_demand`, GCS bucket `gs://bike-demand-staging`, IAM roles for `github-ci-sa` (2026-05-15)
* [x] End-to-end verify — `bike_demand.station_snapshots`: nyc 6,624 rows, first_window 2026-05-15 13:05:00 UTC ✅ (2026-05-15)
* [x] GitHub release v3.0.0 published (2026-05-15)
* Unlocks R Shiny Phase 7F ✅ — BigQuery table live

### Phase 7 — Automated Test Suite ✅ Done (2026-05-18 — commit ca05b35)
* Spec: `docs/superpowers/specs/2026-05-18-pytest-suite-design.md`
* `pytest.ini` — `slow` marker registered; fast tests (`-m not slow`) run in every CI push; RMSE gates run only on push to main
* `tests/test_features.py` — `test_feature_schema_is_frozen`: frozenset of 21 columns; actionable failure message names all 6 cities + Vertex AI container retrain steps
* `tests/test_model_accuracy.py` — 6 `@pytest.mark.slow` parametrised RMSE gate tests; chronological 80/20 split matches `train.py` exactly
* `tests/test_routing.py` — 5 no-fallback routing tests (paris→paris, chicago→chicago, "new york"→nyc, "washington dc"→dc, unknown→seoul fallback); real sklearn RF + monkeypatch
* `.github/workflows/ci.yml` Job 7 (`accuracy`) — parallel to Job 2, push to main only; ~5 min wall time
* All 7 CI jobs green on push to main ✅

### Phase 13 — Seoul Training Data Refresh ✅ Done (v4.2.0 — commit 64ac1d2)
* **Replaces stale UCI 2017-2018 Seoul training set** with OA-15182 (Seoul 따릉이 rental history, 2022-2024) joined to Open-Meteo historical weather; 26,303 hourly rows; mirrors v1.4.0 Paris pattern
* `data/fetch_seoul_weather.py` — aggregates 36 monthly CSVs (cp949-encoded, ~23 GB) to hourly trip counts; joins to Open-Meteo archive (lat=37.57, lng=126.98, timezone=Asia/Seoul); writes `data/processed/seoul_bike_sharing.csv`
* `data/prepare_city_data.py::prepare_seoul_from_joined()` — Seoul-schema normaliser for the joined CSV
* **Timezone bug caught + fixed mid-sprint (commit `176e182`)** — removed `tz_convert("UTC")` on trips before joining with Asia/Seoul weather; restored proper diurnal signal (HOUR=18 mean RBC 11,716 vs HOUR=4 mean 625)
* **RMSE 1,503.52 bikes/hr** (Seoul, chronological split) vs UCI baseline 328.84 — honest figure on ~7× scale + 3-year window; HOUR feature importance climbed to 0.468 (vs 0.287 UCI)
* `tests/test_model_accuracy.py` — Seoul threshold raised 450 → 2,200 (~46% headroom); 5 path references rewired from `data/raw/seoul/seoul_bike_sharing.csv` → `data/processed/seoul_bike_sharing.csv` (tests, Dockerfile, Dockerfile.training, gcp_config.yaml, models/train.py, data/processed/README.md)
* `Dockerfile.training` — removed standalone `COPY data/raw/seoul/` directive (was about to copy 23 GB raw monthly CSVs into image)
* README + data/raw/README.md staleness sweep — zero remaining "UCI Seoul / 8,760 / 328.84" references outside `docs/superpowers/` historical specs
* 23 GB raw monthly CSVs deleted locally post-train (re-fetchable from data.seoul.go.kr); `.gitignore` updated to catch year-prefixed CSVs
* GitHub release v4.2.0 published

### Phase 5 — Vertex AI + Experiment Tracking ✅ Done (v4.0.0 — commit d5c2a54)
* **Code shipped 2026-05-16** — spec: `docs/superpowers/specs/2026-05-16-phase5-vertex-mlflow-design.md`
* `pipeline/retrain_job.py` — 6-combo hyperparameter sweep per city; SQLite+GCS MLflow tracking; RMSE gate (0.97); DRY_RUN mode
* `pipeline/vertex_trigger.py` — Cloud Run HTTP handler; `aiplatform_v1.JobServiceClient` with proto; server-side billing cap `scheduling.timeout: 1800s`
* `Dockerfile.training` — training + trigger container; `python -m pipeline.retrain_job` CMD (sys.path fix); bakes all 4 city CSVs
* `requirements-vertex.txt` — google-cloud-aiplatform, mlflow (pandas<3 constraint resolved), gcsfs for artifact store
* `models/train.py` — chronological 80/20 split (correctness fix); MAE added to evaluation
* `ci.yml` Job 6 — builds + pushes `bike-demand-training` image to GAR on merge to main — ✅ green (run 25970193112)
* **GCP provisioned (2026-05-17):**
  - Vertex AI API enabled; `vertex-sa` SA with `roles/aiplatform.user` + GCS objectAdmin; Vertex AI service agent granted `roles/artifactregistry.reader`
  - `bike-demand-trigger` Cloud Run deployed at `https://bike-demand-trigger-246440913351.us-central1.run.app`
  - Cloud Scheduler job `bike-demand-weekly-retrain` — every Sunday 02:00 UTC
  - Cloud Monitoring: email channel `deepanmehta@live.com`; log-based alerts for job failure + running state
* **Verification complete (2026-05-17):** Vertex AI job ran ~10 min; all 4 cities registered in MLflow Production; `gs://bike-demand-staging/mlflow/mlflow.db` uploaded; `gs://bike-demand-staging/mlflow/artifacts/` has 47 model.pkl files across 4 city dirs
* GitHub release v4.0.0 published (2026-05-17)
* **Post-first-job:** Add `roles/artifactregistry.reader` to Vertex AI service agent `service-246440913351@gcp-sa-aiplatform.iam.gserviceaccount.com`

---

## 🚀 Next Step

**v4.2.0 shipped (2026-05-21) — Seoul training data refresh (OA-15182 + Open-Meteo, 2022-2024).** 3 commits: `176e182` (timezone bug fix), `b17751c` (data refresh + README rewrite), `64ac1d2` (test threshold + 5 path rewires). New Seoul RMSE 1,503.52 bikes/hr on 26,303 hourly rows (vs UCI baseline 328.84 on 8,760 rows). All 7 CI jobs green; FastAPI smoke test verified 3 README predictions to float-exact match.

**Next priority (lead candidate): 4-city analogous timezone bug fix (v4.3.0).** `fetch_paris_weather.py`, `fetch_chicago_weather.py`, `fetch_nyc_weather.py`, and `fetch_dc_weather.py` all use the same `tz_localize → tz_convert("UTC")` pattern paired with Open-Meteo `timezone=<local>` — predictions are time-biased by 1-6 hours depending on the city. Existing models pass tests but the diurnal signal is shifted. Estimated 2-3 sessions (S6-S8) — 4-city re-fetch + retrain + threshold updates + README per-city table updates.

**Alternatives:** (a) Cosmetic train.py stdout sweep (`Training RF model �` cp1252 char in `train.py`); (b) MAE rows in NYC/DC RF tables for cross-city alignment (Seoul has MAE post-v4.2.0); (c) Shiny Phase 8 / v1.7 — `shinytest2` browser harness; (d) verify/trigger Paris + Chicago promotion in MLflow Production registry (only 4 of 6 cities registered at v4.0.0 cut-off); (e) Shiny Priority 6 — upgrade Seoul **live station** feed from the 5-station `sample` key to a registered key.

*v4.2.0 Seoul refresh shipped 2026-05-21 — commit 64ac1d2. Phase 7 complete 2026-05-18 — commit 8bcdb4c. v1.4.0 Paris + Chicago shipped 2026-05-18 — commit d8ee4e0. Phase 5 (Vertex AI + MLflow) complete — v4.0.0 shipped 2026-05-17.*

Resume with: `"resume bike-demand-ml-system — check workflow_status.md and pick up from the next pending action"`
