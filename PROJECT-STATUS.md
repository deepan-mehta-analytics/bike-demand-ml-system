# Project Status — Bike Demand ML System

## Current Stage

Phase 2 multi-city: Seoul (RMSE 173.21) and London (RMSE 228.58) trained and live on `main`
(as of 2026-05-07). Per-city routing wired in the API and service layer. NYC model pending —
data fetch script not yet written. Cross-repo sync gap identified in R Shiny companion repo
(missing city field in FastAPI POST body).

This repo is the **Python backend** in a two-repo portfolio ecosystem:
- **This repo** — FastAPI inference service, GCP data pipeline (Pub/Sub + Dataflow), ML training
- **Companion repo** — R Shiny dashboard that calls `/predict` via `httr::POST`

Re-entry command for new sessions: `"resume bike-demand-ml-system project"`

---

## ✅ Completed

### Phase 1 — Data & Features
* Seoul Bike Sharing dataset (UCI, 8,760 hourly rows) ingested
* Datetime parsing handled (DD/MM format, `dayfirst=True`)
* Feature extraction: `year`, `month`, `day`, `dayofweek`
* One-hot encoding applied to categorical features (`SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`)

### Phase 2 — Model Training
* Baseline Linear Regression implemented and superseded
* Random Forest Regressor (`n_estimators=100`, `random_state=42`)
* Evaluation:
  * MSE: 30,002.93
  * RMSE: **173.21** (target units)
* Feature importance reporting in train script (top contributors: TEMPERATURE, HOUR, SOLAR_RADIATION)

### Phase 3 — Model Persistence
* Saved artifacts (gitignored):
  * `models/random_forest_model.pkl`
  * `models/feature_columns.pkl`
* Feature schema persisted at training time for inference-time alignment (no train/serve skew)

### Phase 4 — Inference Pipeline
* `models/predict.py` implemented
* Loads artifacts via `load_artifacts()`
* Re-applies the shared feature pipeline from `models/features.py`
* Aligns to saved schema with `reindex(fill_value=0)` (no dependency on training data)
* Returns numpy predictions

### Phase 5 — Service Layer
* `services/predictor.py` created
* Lazy-loaded singleton: artifacts loaded on first call, cached for process lifetime
* Decouples API layer from ML logic — hook point for future logging / monitoring / A/B testing
* Tolerates missing artifacts at import time (no module-load crash)

### Phase 6 — API Layer (FastAPI)
* `api/app.py` implemented with FastAPI
* Health-check endpoint (`GET /`)
* Prediction endpoint (`POST /predict`) with batch support
* Pydantic v2 input validation (`BikePredictionInput`, `PredictionRequest`)
* Auto-generated Swagger UI at `/docs`

### Phase 7 — Cleanup pass (2026-05-05)
* Fixed undefined `BikeData` NameError + class ordering bug in `api/app.py`
* Removed dead/duplicate imports (`urllib.request`, `pandas`, `joblib`, repeated `BaseModel`)
* Removed `StandardScaler` from training and inference (RF is scale-invariant)
* Resolved scaler filename mismatch by removing the scaler entirely
* Lazy-loaded artifacts in service layer to avoid import-time crash
* README rewritten in recruiter-grade Data/AI Engineering format

### Phase 8 — Retrain + Verification (2026-05-05)
* Retrained on scaler-free pipeline → RMSE 173.21 (matches pre-cleanup; confirms scaler was inert)
* API booted via `uvicorn api.app:app` on port 8765
* Smoke tests:
  * Single record (winter 8 AM): 605.6 bikes
  * Batch (summer 18:00): 3028.01 bikes
  * Batch (summer 03:00): 435.64 bikes
  * Malformed input (`HOUR="not-an-int"`): HTTP 422 (Pydantic rejected)

### Foundation Infrastructure — Phase 1 (2026-05-07)
* `requirements.txt` — 10 packages pinned (fastapi, uvicorn[standard], scikit-learn, pandas,
  joblib, pydantic, pytest, httpx, ruff, anyio)
* `pytest.ini` — `pythonpath = .` so project root is on sys.path for test imports
* `api/__init__.py` + `services/__init__.py` — make packages importable
* `tests/conftest.py` — anyio asyncio backend fixture for `@pytest.mark.anyio`
* `tests/test_features.py` — 9 unit tests: temporal extraction, one-hot encoding, schema alignment
* `tests/test_api.py` — 5 integration tests via `httpx.AsyncClient`; `predict_service` mocked so
  CI doesn't need pre-trained artifacts at import time (pytest job trains model before running tests)
* `Dockerfile` — `python:3.11-slim`, non-root `appuser`, stdlib health check on `GET /`
* `.dockerignore` — excludes `venv/`, `.git/`, `*.pkl`, `.claude/` from build context
* `docker-compose.yml` — fastapi service, port 8000, `./models:/app/models` volume, `USE_PUBSUB=false`
* `.github/workflows/ci.yml` — ruff → pytest (trains model first) → docker build
* `README.md` — CI + Docker badges, Compose run option, Tests table, ticked Known Limitations

---

## 🧠 Key Learnings

* Separation of training and inference pipelines through a shared feature module
* Reproducible feature-schema persistence prevents train/serve skew
* Service-layer pattern decouples API from ML internals (testable, swappable)
* Lazy singleton loading avoids import-time crashes when artifacts are missing
* Tree-model awareness — Random Forest is invariant to monotonic feature scaling
* Pydantic v2 boundary validation rejects malformed input before it reaches the model
* Importance of an honest, recruiter-grade README as a portfolio surface

---

## ⚠️ Known Limitations

* ~~No `requirements.txt` / `pyproject.toml` yet~~ — added (Phase 7, 10 packages pinned)
* ~~No automated test suite~~ — 14 tests: 9 unit + 5 integration (Phase 7)
* ~~No CI/CD pipeline~~ — GitHub Actions: ruff → pytest → docker build (Phase 7)
* ~~No containerised deployment~~ — Dockerfile + docker-compose.yml (Phase 7)
* No hyperparameter tuning (single fixed RF configuration)
* No experiment tracking (no MLflow / W&B integration)
* No request authentication or rate-limiting on the API
* No structured logging or observability hooks in the service layer
* No drift monitoring on inference inputs
* **Service layer crashes for untrained cities** — Paris and Chicago have no model artifacts;
  need a fallback to Seoul (pending)
* **R Shiny city routing broken** — `predict_bike_demand_fastapi()` sends no `city` field;
  all 5 dashboard cities silently get Seoul model predictions (pending fix in R Shiny repo)

---

## 🔜 Roadmap

### Phase 2 — Multi-City Training [IN PROGRESS]
* ~~Extend `models/train.py` to accept `--city` CLI arg~~ — done (bb9cbaa)
* ~~Add `city: str = "Seoul"` to `PredictRequest`; per-city service cache~~ — done (bb9cbaa)
* ~~London data prepared (Kaggle london_merged.csv) + model trained — RMSE 228.58~~ — done
* ~~Seoul retrained with new CLI infrastructure — RMSE 173.21~~ — done
* NYC data: `bq query` using `nyc_bigquery_sql()` → `data/raw/nyc_trips_hourly.csv`,
  then Open-Meteo weather API → join → `prepare_nyc_from_joined()` ← **next**
  (requires `gcloud auth login`; `bigquery-public-data` is free to query)
* Add fallback in `services/predictor.py` for cities without trained artifacts → use Seoul
* Fix R Shiny: add `city` arg to `predict_bike_demand_fastapi()` + per-city `group_modify()`
  in `generate_city_weather_bike_data()` (companion repo: `shiny_app/model_prediction.R`)
* README: populate NYC row in multi-city RMSE table

### Phase 3 — Cloud Run Deployment
* `cloudbuild.yaml` or GH Actions step — build → push to Artifact Registry
* `config/cloud_run.yaml` — memory 512Mi, concurrency 80, env vars
* Shiny repo `FASTAPI_URL` env var: `http://fastapi:8000` (local) vs Cloud Run URL (GCP)

### Phase 4 — Pub/Sub + Dataflow Pipeline
* `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB` env var switches local vs GCP
* `pipeline/dataflow_job.py` — Apache Beam: Pub/Sub → 5-min window → BigQuery / DuckDB
* `config/gcp_config.yaml` — project ID, topic, BQ dataset, staging bucket, region
* (Companion Shiny repo Phase 7F also triggers off this phase)

### Phase 5 — Vertex AI + Experiment Tracking
* MLflow `autolog()` in `models/train.py`; register model if RMSE improves
* `pipeline/retrain_job.py` — BigQuery → feature engineering → retrain → log → register

### Phase 6 — Observability
* Structured JSON logging in `services/predictor.py` — city, inputs hash, prediction, latency_ms
* `/metrics` endpoint via `prometheus-fastapi-instrumentator`

---

## 🚀 Next Step

**Phase 2 — NYC model.** Authenticate with `! gcloud auth login`, export BigQuery trips via
`nyc_bigquery_sql()`, fetch Open-Meteo weather, join, train, then fix R Shiny city routing.
Resume with: `"resume bike-demand-ml-system project"`
