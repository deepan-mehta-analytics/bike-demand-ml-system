# Project Status — Bike Demand ML System (Python Backend)

> Re-entry command: `"resume bike-demand-ml-system project"`
> Companion repo: `D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction`

---

## 🌐 Ecosystem Snapshot

Both repos form a single portfolio system. Track them together here.

| Repo | Role | Current Phase | Status | Last Commit |
|------|------|--------------|--------|-------------|
| **bike-demand-ml-system** (this repo) | Python FastAPI + ML training | Phase 4 complete — GBFS→Pub/Sub→Dataflow→BigQuery end-to-end verified (v3.0.0) | ✅ Done | `7ef3aad` |
| **bike_demand_prediction** | R Shiny dashboard | Phase 7F complete — GCP Stream tab live (v1.2.0); end-to-end verified 2026-05-16 | ✅ Done | `6dbe149` |

### Trained City Models

| City | Dataset | Rows | RMSE | Top Feature | Artifacts |
|------|---------|------|------|-------------|-----------|
| Seoul | UCI Seoul Bike Sharing | 8,760 | **173.21** | TEMPERATURE (0.34) | `models/artifacts/seoul/` |
| London | Kaggle london_merged.csv | 17,414 | **228.58** | HOUR (0.71) | `models/artifacts/london/` |
| NYC | BigQuery citibike_trips (2014–2018) + Open-Meteo | 34,187 | **345.69** | HOUR (0.52) | `models/artifacts/nyc/` |
| Washington DC | Capital Bikeshare CSVs (2014–2018) + Open-Meteo | 37,663 | **97.47** | HOUR (0.61) | `models/artifacts/dc/` ✅ |

### Next Milestones (Both Repos) — Priority Ordered

| Priority | Repo | Phase | Target Version | Dependency |
|----------|------|-------|---------------|------------|
| ~~1~~ | bike-demand-ml-system | ~~Phase 6 — Observability~~ | ~~v2.1.0~~ | **✅ Shipped** |
| ~~1~~ | bike-demand-ml-system | ~~Phase 4 — Pub/Sub + Dataflow~~ | ~~v3.0.0~~ | **✅ Shipped** |
| ~~1~~ | bike_demand_prediction | ~~Phase 7F — GCP Streaming Dashboard~~ | ~~v1.2.0~~ | **✅ Shipped (2026-05-16)** |
| **3** | bike-demand-ml-system | Phase 5 — Vertex AI + MLflow | v4.0.0 | Best after streaming data exists |
| **4** | bike_demand_prediction | Backlog — Paris/Chicago models | v1.3.0 | Data sourcing required |
| **5** | Both | Backlog — testthat / pytest | — | None |
| **6** | bike_demand_prediction | Backlog — Seoul GBFS | — | External API key |
| **7** | bike_demand_prediction | Backlog — City expansion (SF/Amsterdam) | — | Data sourcing required |

---

## ✅ Completed

### ML Pipeline
* Seoul Bike Sharing dataset (UCI, 8,760 hourly rows) ingested; DD/MM datetime parsing
* Feature engineering: `year`, `month`, `day`, `dayofweek` + one-hot (`SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`)
* Random Forest baseline: RMSE **173.21** bikes/hr (Seoul); scaler removed (RF is scale-invariant)
* Feature schema persisted at training time — no train/serve skew at inference

### API + Service Layer
* `api/app.py` — FastAPI: `GET /` health, `POST /predict` batch endpoint, Pydantic v2 validation
* `services/predictor.py` — per-city lazy-load singleton cache; Seoul fallback for untrained cities
* `models/predict.py` — schema-aligned inference via `reindex(fill_value=0)`

### Multi-City Training (Phase 2)
* `--city` CLI arg in `models/train.py`; per-city artifacts at `models/artifacts/<city>/`
* `city: str = "Seoul"` field on `PredictionRequest`; service layer routes to correct artifact
* **London**: Kaggle CSV prepared via `prepare_london()`; RMSE **228.58**; HOUR dominates (0.71)
* **NYC**: BigQuery `new_york_citibike` (2014–2018) + Open-Meteo via `data/fetch_nyc_weather.py`; RMSE **345.69**; HOUR (0.52) + year growth trend (0.12)
* `services/predictor.py`: fallback to Seoul for cities without trained artifacts; city slug map routes "new york" → nyc, "washington dc" → dc
* `data/prepare_city_data.py`: `prepare_london()`, `nyc_bigquery_sql()`, `prepare_nyc_from_joined()`, `prepare_dc_from_joined()`
* `data/fetch_dc_weather.py`: Capital Bikeshare trip aggregation + Open-Meteo join + Seoul-schema prepare for DC
* **Washington DC**: Capital Bikeshare CSVs (2014–2018) + Open-Meteo join via `data/fetch_dc_weather.py`; RMSE **97.47** bikes/hr; HOUR dominates (0.61); 37,663 hourly rows
* `data/raw/` restructured: per-city subfolders (`seoul/`, `london/`, `nyc/`, `dc/trips/`); `requests` added to `requirements.txt`

### Infrastructure (containerisation + CI)
* `requirements.txt` — 10 packages pinned; `pytest.ini` — `pythonpath = .`
* 15 tests: 9 unit (feature engineering) + 5 integration (API) + 1 city default test
* `Dockerfile` — `python:3.11-slim`, non-root `appuser`, stdlib health check; inline comments moved to standalone lines (Docker parse fix, commit `1ae284f`)
* `docker-compose.yml` — fastapi service, port 8000, `USE_PUBSUB=false`; volume mount removed (artifacts baked into image)
* `.github/workflows/ci.yml` — ruff lint → pytest (trains Seoul model) → docker build → push to GHCR; all 4 jobs green on push to main

---

## ⚠️ Known Limitations

* No hyperparameter tuning — single fixed RF config (`n_estimators=100`, `random_state=42`)
* No experiment tracking — no MLflow / Vertex AI integration
* No API authentication or rate-limiting
* No drift monitoring on inference inputs
* Paris and Chicago have no trained models — service falls back to Seoul (proxy only)
* NYC RMSE (345.69) is higher due to larger absolute trip volumes; adding weather data beyond
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

### Phase 5 — Vertex AI + Experiment Tracking ← Priority 4 (v4.0.0)
* MLflow `autolog()` in `models/train.py`; register model if RMSE improves vs current baseline
* `pipeline/retrain_job.py` — BigQuery → feature engineering → retrain → log → register best model
* Sequenced after Phase 4 — retrain pipeline benefits from streaming data produced by Dataflow

---

## 🚀 Next Step

**v1.2.0 shipped in companion Shiny repo (2026-05-16) — Phase 7F complete.** The GCP Stream tab is live: `bigrquery` queries `bike_demand.station_snapshots` from the Shiny app, displaying 5-min windowed avg/min/max availability for NYC, DC, London, and Chicago.

**Next priority (Python repo):** Phase 5 — Vertex AI + MLflow experiment tracking (v4.0.0). Or backlog: train Paris/Chicago RF models to replace Seoul proxy in the Shiny dashboard.

*Phase 4 (Pub/Sub + Dataflow) complete — v3.0.0 shipped on 2026-05-15. Shiny v1.2.0 shipped 2026-05-16.*

Resume with: `"resume bike-demand-ml-system — check workflow_status.md and pick up from the next pending action"`
