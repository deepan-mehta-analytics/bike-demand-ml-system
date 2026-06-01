# 🚴 Bike Demand ML System

## ⚡ Quick Summary

This project started as the **Python ML backend** for a companion R Shiny capstone dashboard — a FastAPI service wrapping a Seoul Random Forest model. It didn't stop there. Across six shipped versions it grew into a multi-city ML platform: managed retraining on Vertex AI, MLflow experiment tracking, a GCS-backed model registry with RMSE promotion gates, a live GBFS station data pipeline, and a CI-enforced accuracy test suite. The origin is still visible in the architecture; the engineering layers built on top are the portfolio signal.

**What it became — across six shipped versions**

- **Multi-city Random Forest inference API** — per-city RF models for all 6 cities (Seoul, London, NYC, Washington DC, Paris, Chicago) served via a Pydantic-validated `/predict` endpoint on GCP Cloud Run; lazy-loaded singleton service layer decouples business logic from the API surface; train/serve feature schema persisted via `joblib` to prevent skew.
- **Vertex AI managed retraining** — a `bike-demand-trigger` Cloud Run service submits a 6-combo hyperparameter sweep to Vertex AI every Sunday; results tracked in SQLite + GCS-backed MLflow; a 3% RMSE gate enforces model quality before any city model is promoted to the Production registry.
- **Per-city data pipelines** — Open-Meteo historical API + GBFS open data fetchers for each city; Seoul rebuilt to a 3-year OA-15182 hourly scope (v4.2.0, 26,303 rows, RMSE 1,503.52); Paris re-aligned to wall-clock-local time with a 2022 anomaly data-quality drop (v4.3.0, RMSE 20.51).
- **CI-enforced accuracy gates** — 40-test pytest suite: schema guards, per-city RMSE gates, no-fallback routing guarantees, Dataflow pipeline contracts, and GBFS 5-min window aggregator unit tests; enforced on every push via GitHub Actions.

**Engineering choices that signal the skills**

Three decisions in the version history show judgment beyond "make it work":

*GCP pipeline right-sizing (v3.1.0):* The live station data pipeline shipped first as **Apache Beam / Dataflow** — managed streaming, Pub/Sub ingestion, windowed aggregations. After running it in production, it was rebuilt:

- **Why Dataflow was wrong** — designed for large-scale continuous streams; polling six GBFS endpoints every five minutes is a cron job, not a streaming problem. Dataflow was burning paid GCP resources on a workload that never needed its machinery.
- **What replaced it** — a **Cloud Run** service triggered by **Cloud Scheduler** (5-min cron, OIDC auth), writing station snapshots to a BigQuery 7-day partitioned table via load jobs — unconditionally free at this volume.
- **Outcome** — the same live data in the Shiny GCP Stream tab; zero always-free-tier cost; no Beam pipeline, no job monitoring.

*Data quality discipline (v4.3.0):* Paris 2022 training data was dropped as a data-quality gate after identifying anomalous ridership during the post-COVID re-opening period. RMSE improved from 23.30 → 20.51. Knowing when to *exclude* data — and being able to justify it against the metric — is a model engineering judgment the RMSE tables in this repo make explicit.

*Service-layer architecture:* Business logic lives in `services/predictor.py`, not in `api/app.py`. The API surface calls the service; the service calls the inference pipeline. This decoupling means logging, monitoring, A/B testing, or model versioning can be wired in without touching the API contract — a standard production ML engineering pattern that notebook-to-API migrations routinely skip.

### Capstone companion backend. Evolved into a production ML platform. The engineering layers are the portfolio.

---

## 🏷️ Project Badges

[![CI](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/ci.yml/badge.svg)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.8-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Inference_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![pandas](https://img.shields.io/badge/pandas-3.x-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-Validation-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Docker](https://img.shields.io/badge/Docker-Containerised-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Status](https://img.shields.io/badge/v3.0.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)
[![Status](https://img.shields.io/badge/v4.0.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)
[![Status](https://img.shields.io/badge/v4.1.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)
[![Status](https://img.shields.io/badge/v4.2.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/releases/tag/v4.2.0)
[![Status](https://img.shields.io/badge/v4.3.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/releases/tag/v4.3.0)
[![Status](https://img.shields.io/badge/v4.4.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/releases/tag/v4.4.0)
[![Status](https://img.shields.io/badge/v3.1.0-Released-success?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-Live-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://bike-demand-api-246440913351.us-central1.run.app)
[![GBFS Poller](https://img.shields.io/badge/GBFS_Poller-Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)
[![Prometheus](https://img.shields.io/badge/Prometheus-metrics-orange?style=for-the-badge&logo=prometheus&logoColor=white)](https://bike-demand-api-246440913351.us-central1.run.app/metrics)

---

## 📌 Project Overview
This project implements an **end-to-end machine learning system** for forecasting hourly bike-rental demand. It evolves from data analytics into a structured ML platform with a clean separation between training, persistence, business logic, and API delivery.

It trains across **six cities** (Seoul, London, NYC, Washington DC, Paris, Chicago) on a shared 14-column schema, demonstrating ML engineering patterns required to ship a model from notebook into a deployable multi-city API.

It implements:

- **Train / Inference separation** — independent pipelines that share a single feature engineering module to guarantee schema consistency
- **Model persistence** — trained model and feature schema serialised via `joblib` for reproducible deployment
- **Service-layer architecture** — business logic decoupled from the API surface, enabling future extensions (logging, monitoring, A/B testing) without touching API code
- **FastAPI inference API** — Pydantic-validated `/predict` endpoint with batch support and auto-generated Swagger UI
- **Lazy artifact loading** — singleton pattern that loads the model once per process and gracefully tolerates missing artifacts at import time
- **Reproducible feature schema** — feature columns persisted at training time and re-aligned at inference to prevent train/serve skew
- **Tree-aware pipeline** — no scaling overhead since Random Forest is invariant to monotonic feature transforms

---

## ⚙️ Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Language | Python 3.11+ | Implementation language |
| ML Framework | scikit-learn | Random Forest training, evaluation, feature pipelines |
| Data Processing | pandas + NumPy | DataFrame operations, datetime feature engineering |
| Model Persistence | joblib | Serialise model + feature schema to disk |
| API Framework | FastAPI | Inference endpoint with auto-generated OpenAPI documentation |
| Validation | Pydantic v2 | Strict request schema validation at the API boundary |
| ASGI Server | uvicorn | Production-grade ASGI server for FastAPI |
| Containerisation | Docker + Docker Compose | python:3.11-slim image; all 6 city models baked into image at build time |
| Testing | pytest + httpx + anyio | Schema guard, RMSE gates (6 cities), routing guarantee, async API tests |
| Linting / CI | ruff + GitHub Actions | Lint → test → docker build → RMSE accuracy gates (Job 6) on push to main |
| Experiment Tracking | MLflow *(v4.0.0)* | GCS-backed run tracking, model registry, RMSE gate |
| ML Platform | Vertex AI *(v4.0.0)* | Managed CustomJob for weekly hyperparameter sweep |

---

## 🎯 Business Problem

Public bike-share operators need to forecast hourly demand in order to balance fleet positioning, station rebalancing, and maintenance windows against highly variable weather and temporal effects. Under-supply costs revenue and rider trust; over-supply costs operations and capital.

> **How do we deliver an automated, reproducible ML system that converts weather and temporal signals into reliable hourly demand forecasts, served through a production-grade inference API ready for downstream consumption?**

---

## 🏗️ System Architecture

```
[Raw CSV]  ──►  [Feature Engineering]  ──►  [Train / Test Split]
     ──►  [Random Forest Training]  ──►  [Persist Model + Feature Schema]
                                                     │
                                                     ▼
[Client]  ──►  [FastAPI /predict]  ──►  [Service Layer]  ──►  [Inference Pipeline]  ──►  [Predictions]
```

| Component | Module | Responsibility |
|---|---|---|
| 📊 Features | `models/features.py` | Datetime parsing, temporal feature extraction, one-hot encoding |
| 🎓 Training | `models/train.py` | Train RF, evaluate (RMSE), persist artifacts, report feature importances |
| 🔮 Inference | `models/predict.py` | Load artifacts, transform input, align schema, generate predictions |
| 🧠 Service | `services/predictor.py` | Lazy-loaded singleton wrapping the inference pipeline |
| 🌐 API | `api/app.py` | FastAPI app: `/`, `/predict`, `/docs` with Pydantic schemas |

---

## 📁 Repository Structure

```
bike-demand-ml-system/
│
├── README.md
├── PROJECT-STATUS.md
├── requirements.txt                    ← pinned Python dependencies (inference API + tests)
├── requirements-pipeline.txt           ← Dataflow pipeline-only deps (apache-beam, pubsub, pyyaml) — not in Docker image
├── requirements-poller.txt             ← v3.1.0 GBFS poller deps (fastapi, uvicorn, google-cloud-bigquery, httpx)
├── requirements-vertex.txt             ← training container deps (google-cloud-aiplatform, mlflow, pandas<3)
├── Dockerfile                          ← inference API image: python:3.11-slim, non-root user, health check
├── Dockerfile.training                 ← training + trigger container; bakes 4 city CSVs (paris + chicago join in v4.5.0 S2); CMD runs retrain_job.py
├── Dockerfile.poller                   ← v3.1.0 slim image for `gbfs-poller` Cloud Run service (FastAPI + BigQuery client)
├── docker-compose.yml                  ← local dev orchestration; models baked into image
├── .dockerignore                       ← excludes venv/, .git/, *.pkl from build context
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── ci.yml                      ← ruff lint → pytest → docker build on every push
│
├── data/
│   ├── prepare_city_data.py            ← normalise city CSVs to Seoul schema
│   ├── fetch_nyc_weather.py            ← Open-Meteo historical fetch + join for NYC
│   ├── fetch_dc_weather.py             ← Capital Bikeshare trip aggregation + Open-Meteo join for DC
│   ├── fetch_paris_weather.py          ← Vélib' Métropole counter ZIPs + Open-Meteo join for Paris
│   ├── fetch_chicago_weather.py        ← Divvy quarterly CSVs + Open-Meteo join for Chicago
│   ├── raw/
│   │   ├── seoul/                          ← OA-15182 monthly per-trip CSVs (2022-2024, gitignored) + Open-Meteo weather + joined CSV
│   │   ├── london/london_merged.csv        ← Kaggle London dataset
│   │   ├── nyc/                            ← BigQuery export + Open-Meteo weather + joined CSV
│   │   ├── dc/                             ← Capital Bikeshare CSVs + Open-Meteo weather + joined CSV
│   │   │   └── trips/                      ← raw quarterly/annual Capital Bikeshare CSVs
│   │   ├── paris/                          ← Vélib' annual ZIPs (2023–2024; 2022 dropped) + Open-Meteo weather
│   │   └── chicago/                        ← Divvy quarterly CSVs (2019–2022) + Open-Meteo weather
│   └── processed/                      ← Seoul-schema CSVs ready for models/train.py
│
├── models/
│   ├── features.py                     ← shared feature pipeline (used by train + predict)
│   ├── train.py                        ← training CLI: --city, --data; saves to artifacts/<city>/
│   ├── predict.py                      ← inference pipeline: load_artifacts(city), predict()
│   ├── __init__.py
│   └── artifacts/                      ← per-city artifact directories (gitignored)
│       ├── seoul/                      ← random_forest_model.pkl + feature_columns.pkl
│       ├── london/                     ← random_forest_model.pkl + feature_columns.pkl
│       ├── nyc/                        ← random_forest_model.pkl + feature_columns.pkl
│       ├── dc/                         ← random_forest_model.pkl + feature_columns.pkl
│       ├── paris/                      ← random_forest_model.pkl + feature_columns.pkl
│       └── chicago/                    ← random_forest_model.pkl + feature_columns.pkl
│
├── services/
│   └── predictor.py                    ← service layer: lazy singleton, decouples API from ML
│
├── api/
│   └── app.py                          ← FastAPI app: /, /predict, /docs
│
├── tests/
│   ├── conftest.py                     ← anyio asyncio backend fixture for async tests
│   ├── test_features.py                ← unit tests: temporal extraction, one-hot, frozen schema guard
│   ├── test_api.py                     ← integration tests: 200/422 via httpx.AsyncClient
│   ├── test_model_accuracy.py          ← RMSE gate tests: per-city accuracy assertions (slow, CI Job 6)
│   ├── test_routing.py                 ← routing tests: no-fallback guarantee for Paris/Chicago/NYC/DC
│   ├── test_pipeline.py                ← Dataflow pipeline tests: DoFn unit + DirectRunner end-to-end (needs requirements-pipeline.txt)
│   ├── test_window_agg.py              ← v3.1.0 poller: 5-min window aggregator unit tests (avg/min/max, multi-city, rounding)
│   └── test_gbfs_poller_service.py     ← v3.1.0 poller: FastAPI service contract tests
│
├── config/
│   └── gcp_config.yaml                 ← GCP project, Pub/Sub topic, BigQuery, Dataflow, GBFS city URLs
│
├── pipeline/
│   ├── __init__.py                     ← marks pipeline/ as a Python package
│   ├── gbfs_to_pubsub.py               ← legacy: GBFS station poller → Pub/Sub topic (v3.0.0 Dataflow path; superseded by gbfs_poller_service.py in v3.1.0)
│   ├── dataflow_job.py                 ← legacy: Apache Beam Pub/Sub → 5-min FixedWindows → BigQuery (retained intact)
│   ├── gbfs_poller_service.py          ← v3.1.0 Cloud Run service: poll GBFS feeds → 5-min window agg → BigQuery direct insert (zero-cost replacement for Dataflow path)
│   ├── window_agg.py                   ← v3.1.0 pure-Python helper: group GBFS snapshots by (city, station) → avg/min/max bike counts per window
│   ├── retrain_job.py                  ← Vertex AI entry point: 6-combo sweep → MLflow → RMSE gate → Model Registry
│   └── vertex_trigger.py               ← Cloud Run HTTP handler: POST /trigger → submit CustomJob async
│
├── docs/
│   └── superpowers/
│       ├── specs/
│       │   ├── 2026-05-16-phase5-vertex-mlflow-design.md  ← Phase 5 approved design spec
│       │   └── 2026-05-18-pytest-suite-design.md          ← pytest three-tier suite design spec
│       └── plans/
│           └── 2026-05-18-pytest-suite.md                 ← pytest suite implementation plan
│
└── venv/                               ← virtual environment (gitignored)
```

---

## ▶️ How to Run

### 📌 Option 1 — Local (Recommended for development)

> Models for all 6 cities are trained and baked into the Docker image at build time — no pre-training step is needed before running the service.

#### 1. Clone the repository

```bash
git clone https://github.com/deepan-mehta-analytics/bike-demand-ml-system.git
cd bike-demand-ml-system
```

#### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Place the dataset

Download the Seoul 따릉이 per-trip ZIPs from [Seoul OpenData dataset OA-15182](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do) — annual ZIPs for 2022, 2023, and 2024 (~600 MB compressed; ~23 GB extracted). Extract each ZIP into `data/raw/seoul/` and rename every monthly CSV to `YYYY-MM.csv`:

```
data/raw/seoul/2022-01.csv
data/raw/seoul/2022-02.csv
…
data/raw/seoul/2024-12.csv
```

Then aggregate the per-trip logs to hourly counts and join Open-Meteo historical weather:

```bash
python -m data.fetch_seoul_weather
```

This produces `data/processed/seoul_bike_sharing.csv` (26,303 rows × 14 cols, Jan 2022 – Dec 2024). The raw monthly CSVs are gitignored — once `data/processed/seoul_bike_sharing.csv` exists you can delete them to reclaim ~23 GB; the fetch script is the durable artifact in git.

#### 5. Train the model

```bash
python -m models.train --city seoul --data data/processed/seoul_bike_sharing.csv
```

This produces:

- `models/artifacts/seoul/random_forest_model.pkl`
- `models/artifacts/seoul/feature_columns.pkl`

…and prints RMSE plus the top-10 feature importances to stdout.

#### 6. Start the inference API

```bash
uvicorn api.app:app --reload
```

The API is now live at `http://127.0.0.1:8000`. Open `http://127.0.0.1:8000/docs` for the interactive Swagger UI.

#### 7. Send a prediction request

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Seoul",
    "data": [{
      "DATE": "01/12/2024", "HOUR": 8,
      "TEMPERATURE": -5.2, "HUMIDITY": 37,
      "WIND_SPEED": 2.2, "VISIBILITY": 2000,
      "DEW_POINT_TEMPERATURE": -17.6, "SOLAR_RADIATION": 0.0,
      "RAINFALL": 0.0, "SNOWFALL": 0.0,
      "SEASONS": "Winter", "HOLIDAY": "No Holiday",
      "FUNCTIONING_DAY": "Yes"
    }]
  }'
```

Expected response: `{"predictions": [1570.26]}`

> **`city`** is optional — defaults to `"Seoul"` if omitted. Pass `"city": "London"`, `"city": "nyc"`, `"city": "Paris"`, `"city": "Chicago"`, or `"city": "Washington DC"` to route to per-city artifacts. Unknown cities fall back to Seoul.

---

### 🐳 Option 2 — Docker Compose

Model artifacts are baked into the image at build time — no local training step required.

```bash
# Build the image (trains all 6 city models during build) and start the container
docker compose up --build

# API is live at http://localhost:8000
```

---

### 📦 Option 3 — Pull from GitHub Container Registry

Pre-built image with all 6 city models baked in. Published automatically on every merge to `main` via GitHub Actions — no manual build required.

```bash
docker pull ghcr.io/deepan-mehta-analytics/bike-demand-ml-system:latest
docker run -p 8000:8000 ghcr.io/deepan-mehta-analytics/bike-demand-ml-system:latest
```

API is live at `http://localhost:8000`. Open `http://localhost:8000/docs` for the Swagger UI.

---

### ☁️ Option 4 — Cloud Run (GCP)

Deploy the GHCR image to Google Cloud Run. Requires the `gcloud` CLI authenticated to a GCP project with Cloud Run enabled.

```bash
gcloud run deploy bike-demand-api \
  --image ghcr.io/deepan-mehta-analytics/bike-demand-ml-system:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --concurrency 80 \
  --port 8000
```

Cloud Run returns a service URL on first deploy. Use that URL as `FASTAPI_URL` in the companion R Shiny dashboard.

---

### 📡 Option 5 — Pub/Sub + Dataflow Streaming Pipeline (v3.0.0 — superseded by v3.1.0 Cloud Run poller)

> **As of v3.1.0 (2026-05-25), the production streaming path is the Cloud Run `gbfs-poller` service driven by Cloud Scheduler every 5 minutes.** It writes directly to a BigQuery 7-day-partitioned `station_snapshots` table at zero always-free-tier cost. See `pipeline/gbfs_poller_service.py` + `Dockerfile.poller`. The Dataflow path below is retained for reference and remains runnable, but you should not need to launch it for the dashboard to receive live data.

The legacy streaming pipeline polls live GBFS bike-station feeds, publishes to Cloud Pub/Sub, and runs an Apache Beam job that aggregates 5-minute windows into BigQuery.

#### Step 1 — Install pipeline dependencies

```bash
pip install -r requirements-pipeline.txt
```

#### Step 2 — Run the GBFS poller locally (no GCP account required)

```bash
# USE_PUBSUB=false → prints station JSON to stdout instead of publishing to Pub/Sub
USE_PUBSUB=false python -m pipeline.gbfs_to_pubsub
```

Each poll round emits one JSON line per station across NYC, DC, London, and Chicago.

#### Step 3 — Run the Beam pipeline locally with DirectRunner (zero GCP cost)

```bash
# DirectRunner uses synthetic test messages — no Pub/Sub or BigQuery credentials needed
python -m pipeline.dataflow_job --runner Direct
```

#### Step 4 — One-time GCP provisioning (required before DataflowRunner)

Run these `gcloud` commands once to create the cloud resources:

```bash
# Enable required APIs
gcloud services enable pubsub.googleapis.com dataflow.googleapis.com \
  bigquery.googleapis.com storage.googleapis.com --project bike-demand-ml-system

# Create Pub/Sub topic and subscription
gcloud pubsub topics create gbfs-bike-stations --project bike-demand-ml-system
gcloud pubsub subscriptions create gbfs-bike-stations-sub \
  --topic gbfs-bike-stations --ack-deadline 60 --project bike-demand-ml-system

# Create BigQuery dataset and GCS staging bucket
bq mk --dataset --project_id bike-demand-ml-system --location US bike_demand
gsutil mb -p bike-demand-ml-system -l us-central1 gs://bike-demand-staging

# Grant service account the required Dataflow roles
for ROLE in roles/pubsub.subscriber roles/pubsub.publisher \
  roles/bigquery.dataEditor roles/dataflow.worker roles/storage.objectAdmin; do
  gcloud projects add-iam-policy-binding bike-demand-ml-system \
    --member="serviceAccount:github-ci-sa@bike-demand-ml-system.iam.gserviceaccount.com" \
    --role="$ROLE"
done
```

#### Step 5 — Run on GCP Dataflow (~$0.05/hr; tear down after demo)

```bash
# Start the poller publishing to Cloud Pub/Sub
USE_PUBSUB=true python -m pipeline.gbfs_to_pubsub &

# Launch the Dataflow streaming job (runs until cancelled)
python -m pipeline.dataflow_job --runner DataflowRunner

# When done — find the job ID and cancel to stop billing
gcloud dataflow jobs list --project bike-demand-ml-system
gcloud dataflow jobs cancel <job-id> --region us-central1
```

> **Cost guard:** All development and testing uses `DirectRunner` (zero cost). Run `DataflowRunner` only for a short demo window (1–2 hours ≈ $0.10 total), then cancel. Pub/Sub polling at 4 cities × 60s interval stays well under the 10 GiB/month free tier.

---

## 🧪 Tests

```bash
# Train model artefacts first (required for full integration run)
python models/train.py

# Run the full test suite
pytest tests/
```

The suite has eight modules (66 tests) across three tiers — 40 for the ML inference API and 26 for the `cost-audit` service:

| Module | Type | What it covers |
|---|---|---|
| `tests/test_features.py` | Unit | Temporal extraction, one-hot encoding, frozen schema guard (`test_feature_schema_is_frozen` — fails with retrain instructions if the column set changes) |
| `tests/test_api.py` | Integration | `httpx.AsyncClient` against the live ASGI app: 200 for single record, 200 for batch, 422 for wrong type, 422 for missing required field |
| `tests/test_routing.py` | Unit | No-fallback guarantee: Paris/Chicago/NYC/DC route to their own artifacts; unknown city falls back to Seoul |
| `tests/test_model_accuracy.py` | Accuracy | Per-city RMSE gates (6 cities): trains a fresh RF from the committed CSV, asserts RMSE < threshold. Marked `@pytest.mark.slow` — runs only in CI Job 6 |
| `tests/test_pipeline.py` | Unit + Pipeline | Legacy Dataflow path: GBFS/TFL snapshot schema, ParseMessage DoFn, DirectRunner end-to-end; auto-skipped unless `requirements-pipeline.txt` is installed |
| `tests/test_window_agg.py` | Unit | v3.1.0 poller: 5-minute window aggregator — empty input, single snapshot degenerate stats, multi-snapshot avg/min/max, multi-city/station keying, 2-decimal rounding parity with the Dataflow path |
| `tests/test_gbfs_poller_service.py` | Unit | v3.1.0 poller: FastAPI service contract — health endpoint, poller trigger response shape |
| `tests/test_cost_audit.py` | Unit + Integration | `cost-audit` service: `evaluate_thresholds` (11 tests across 9 check domains), `format_alert_message` + `send_alert` (4 tests), 7 resource-reading functions with mocked GCP clients (9 tests), `audit()` HTTP handler integration (2 tests — healthy silent, tripped Slack call) |

```bash
# Fast suite (schema, API, routing — excludes RMSE gates)
pytest tests/ -m "not slow"

# RMSE accuracy gates only (~5 min, 6 cities)
pytest -m slow tests/test_model_accuracy.py -v

# Pipeline tests (requires requirements-pipeline.txt)
pip install -r requirements-pipeline.txt
pytest tests/test_pipeline.py -v
```

CI runs lint → pytest (fast) → docker build → push to GHCR on every push to `main`. **Job 6 (RMSE accuracy gates)** runs in parallel with the fast pytest job on every push to `main`.

---

## 📊 Model Performance

### Per-City RMSE

Artifacts stored at `models/artifacts/<city>/` — train each city with `python -m models.train --city <name> --data <path>`.

All RMSEs use a chronological 80/20 split (oldest 80% → train, newest 20% → test), matching `train.py` exactly.

| City | Dataset | Rows | RMSE (bikes/hr) | Top Feature | Status |
|------|---------|------|-----------------|-------------|--------|
| Seoul | Seoul OA-15182 + Open-Meteo | 26,303 | **1,503.52** | HOUR (0.47) | ✅ Trained |
| London | Kaggle London Bike Sharing | 17,414 | **316.56** | HOUR (0.71) | ✅ Trained |
| NYC | BigQuery `new_york_citibike` + Open-Meteo | 34,187 | **470.76** | HOUR (0.52) | ✅ Trained |
| Washington DC | Capital Bikeshare CSVs + Open-Meteo | 37,663 | **119.31** | HOUR (0.62) | ✅ Trained |
| Paris | Vélib' Métropole open data (MEAN scale) + Open-Meteo | 17,539 | **20.51** | HOUR (0.71) | ✅ Trained |
| Chicago | Divvy Bikes CSVs + Open-Meteo | 32,720 | **202.99** | HOUR (0.39) | ✅ Trained |

NYC is the most hour-driven city after DC and Paris — HOUR accounts for 52% of feature importance, reflecting New York's dense commuter cycling pattern. Higher RMSE vs Seoul/London/DC reflects NYC's larger absolute trip volumes.

London's model is dominated by HOUR (0.71), reflecting London's strong commuter cycling pattern. Missing columns (VISIBILITY, DEW_POINT_TEMPERATURE, SOLAR_RADIATION) were zeroed — sourcing these would likely reduce RMSE further.

Washington DC's RMSE of 119.31 is among the lowest — Capital Bikeshare is a smaller system than NYC, so absolute hourly counts are lower. HOUR dominates (0.62), consistent with a strong commuter pattern.

Paris RMSE (20.51) is low because the Vélib' source data uses a normalised MEAN station counter (individual station average ~50–500 bikes/hr), not city-wide summed volume. The v4.3.0 timezone fix (mirroring the Seoul precedent) aligned trips to Paris-local wall-clock time so the join with Open-Meteo weather is hour-accurate; the same release dropped 2022 source data as a data-quality gate after the export was found to peak 2h later than 2023+2024 in both AM and PM rush across DST seasons (an intrinsic provider-side aggregation difference). HOUR dominance rose to 0.71 — the same family of commuter-driven patterns seen in London (0.71), DC (0.62), NYC (0.52), and Seoul (0.47).

See `data/prepare_city_data.py` for London column-mapping and NYC BigQuery SQL + `data/fetch_nyc_weather.py` / `data/fetch_dc_weather.py` for the Open-Meteo join scripts.

### Seoul — Random Forest Regressor

| Metric | Value |
|---|---|
| Algorithm | Random Forest Regressor (`n_estimators=100`, `random_state=42`) |
| RMSE | **1,503.52** |
| MAE | **828.77** |
| MSE | 2,260,563.09 |
| Train / Test split | Chronological 80/20 — oldest 80% → train, newest 20% → test |
| Train / Test rows | 21,042 / 5,261 |
| Data source | Seoul OpenData OA-15182 따릉이 per-trip log + Open-Meteo historical weather (Jan 2022 – Dec 2024) |
| Scaling | None (RF is scale-invariant — scaling removed from pipeline) |

### Top Feature Importances

| Rank | Feature | Importance |
|---|---|---|
| 1 | `HOUR` | 0.468 |
| 2 | `TEMPERATURE` | 0.152 |
| 3 | `RAINFALL` | 0.089 |
| 4 | `dayofweek` | 0.076 |
| 5 | `SOLAR_RADIATION` | 0.072 |
| 6 | `SEASONS_Winter` | 0.040 |
| 7 | `DEW_POINT_TEMPERATURE` | 0.025 |
| 8 | `WIND_SPEED` | 0.020 |
| 9 | `HUMIDITY` | 0.019 |
| 10 | `day` | 0.014 |

**Key insight surfaced by the model:** `HOUR` dominates the forecast (0.47), with `TEMPERATURE` (0.15) and `RAINFALL` (0.09) the strongest weather signals — a different shape from the prior UCI 2017–2018 baseline (TEMPERATURE 0.40, HOUR 0.29), which captured a single year of a then-young system. The new 3-year window (2022–2024) reflects a mature, commuter-driven Seoul fleet at ~7× the previous trip volume, so the hour-of-day signal dominates the same way it does in NYC (HOUR 0.52), DC (HOUR 0.62), and London (HOUR 0.71). `VISIBILITY` drops out of the top 10 because Open-Meteo returns a near-constant value (2000) for Seoul — the Random Forest correctly identifies it as non-informative.

### NYC — Random Forest Regressor

| Metric | Value |
|---|---|
| Algorithm | Random Forest Regressor (`n_estimators=100`, `random_state=42`) |
| RMSE | **470.76** |
| MAE | **246.02** |
| MSE | 221,610.72 |
| Train / Test split | Chronological 80/20 — oldest 80% → train, newest 20% → test |
| Train / Test rows | 27,349 / 6,838 |
| Data source | BigQuery `new_york_citibike.citibike_trips` (2014–2018) + Open-Meteo historical weather |
| Rows | 34,187 hourly observations |

### NYC Top Feature Importances

| Rank | Feature | Importance |
|---|---|---|
| 1 | `HOUR` | 0.517 |
| 2 | `TEMPERATURE` | 0.180 |
| 3 | `year` | 0.116 |
| 4 | `dayofweek` | 0.080 |
| 5 | `RAINFALL` | 0.030 |
| 6 | `HUMIDITY` | 0.022 |
| 7 | `month` | 0.013 |
| 8 | `WIND_SPEED` | 0.011 |
| 9 | `day` | 0.011 |
| 10 | `DEW_POINT_TEMPERATURE` | 0.011 |

**Key insight:** NYC's HOUR dominance (0.52 vs 0.29 for Seoul) reflects the intensity of New York's commuter cycling peaks. `year` ranks 3rd (0.12) — a strong growth trend as Citi Bike expanded from 2014 to 2018 — which Seoul and London don't show as prominently.

### Washington DC — Random Forest Regressor

| Metric | Value |
|---|---|
| Algorithm | Random Forest Regressor (`n_estimators=100`, `random_state=42`) |
| RMSE | **119.31** |
| MAE | **67.75** |
| MSE | 14,234.62 |
| Train / Test split | Chronological 80/20 — oldest 80% → train, newest 20% → test |
| Train / Test rows | 30,130 / 7,533 |
| Data source | Capital Bikeshare CSVs (2014–2018) + Open-Meteo historical weather |
| Rows | 37,663 hourly observations |

### Washington DC Top Feature Importances

| Rank | Feature | Importance |
|---|---|---|
| 1 | `HOUR` | 0.614 |
| 2 | `TEMPERATURE` | 0.165 |
| 3 | `dayofweek` | 0.070 |
| 4 | `HUMIDITY` | 0.038 |
| 5 | `month` | 0.024 |
| 6 | `RAINFALL` | 0.022 |
| 7 | `WIND_SPEED` | 0.015 |
| 8 | `year` | 0.014 |
| 9 | `DEW_POINT_TEMPERATURE` | 0.013 |
| 10 | `day` | 0.009 |

**Key insight:** DC's RMSE (119.31) is the lowest across all cities because Capital Bikeshare's hourly volumes are smaller than NYC's, making the absolute error lower. HOUR dominates even more strongly (0.62) — DC's commuter pattern is highly regular. `year` ranks 8th (0.01), unlike NYC's 3rd (0.12), because DC's system was already mature by 2014.

---

## 🧪 Smoke-Test Evidence

End-to-end verification against a freshly trained model running behind `uvicorn`:

| Scenario | Input | Predicted Demand |
|---|---|---|
| Single record — winter 8 AM | `TEMP=-5.2`, `HOUR=8`, `SEASONS=Winter` | **1570.26** bikes |
| Batch — summer rush hour | `HOUR=18`, `SEASONS=Summer`, `TEMP=24.3` | **16731.78** bikes |
| Batch — summer 03:00 | `HOUR=3`, `SEASONS=Summer`, `TEMP=18.2` | **1066.15** bikes |
| Malformed input | `HOUR="not-an-int"` | **HTTP 422** (Pydantic validation rejected) |

The ~16× spread between summer rush and middle-of-night confirms the model captures the strong hour-of-day signal seen in feature importances, and the Pydantic 422 confirms the API boundary rejects invalid types before they reach the model.

---

## 🧩 Key Concepts Implemented

- Train vs. inference separation with a shared feature pipeline
- Reproducible feature-schema persistence (no train/serve skew)
- Service-layer pattern (decouples API from ML logic)
- Lazy singleton artifact loading (no import-time crashes when artifacts are missing)
- Pydantic v2 input validation at the API boundary
- Tree-model awareness — no scaling overhead since RF is scale-invariant
- Honest, reproducible metric reporting (RMSE in target units)

---

## ⚠️ Known Limitations

- ~~No `requirements.txt` / `pyproject.toml` yet~~ — pinned in `requirements.txt` ✅
- ~~No automated test suite (unit / integration)~~ — `tests/` with pytest + httpx ✅
- ~~No CI/CD pipeline (GitHub Actions)~~ — lint → test → docker build on every push ✅
- ~~No Dockerfile or containerised deployment~~ — `Dockerfile` + `docker-compose.yml` ✅
- ~~No hyperparameter tuning (GridSearch / Optuna)~~ — **v4.0.0 shipped:** `pipeline/retrain_job.py` runs a 6-combo `n_estimators` × `max_depth` sweep per city weekly on Vertex AI with an RMSE gate before promoting to MLflow Production ✅ (GridSearch/Optuna not currently used; the sweep is sufficient at portfolio scale)
- ~~No experiment tracking (MLflow / Vertex AI)~~ — **v4.0.0 shipped:** `pipeline/retrain_job.py` weekly sweep + GCS-backed MLflow + RMSE gate; **4 of 6 cities** live in MLflow Production registry (Seoul / London / NYC / DC). Paris and Chicago train via the same Vertex AI job but have not yet been promoted to Production — tracked as an open candidate in [`PROJECT-STATUS.md`](PROJECT-STATUS.md) Next Step ✅
- **Paris 2022 source export dropped as a data-quality gate** — the 2022 export from opendata.paris.fr peaks 2h later than 2023+2024 in both AM and PM rush hours and is DST-consistent within 2022, ruling out timezone-encoding causes (the parser is correct; the source aggregation is anomalous). 33% of available Paris source rows filtered out in v4.3.0 via a single reversible block in `data/fetch_paris_weather.py`. Root cause is intrinsic to the provider's internal aggregation pipeline and not user-fixable; revisit if upstream ever publishes a correction.
- **No automated drift monitoring on inference inputs yet** — feature importances are logged to MLflow on every Vertex AI retrain, but there is no scheduled job that compares live weather distributions against the training baseline. Tracked in v4.5.0 design spec [`docs/superpowers/specs/2026-05-23-drift-monitoring-design.md`](docs/superpowers/specs/2026-05-23-drift-monitoring-design.md).
- No request authentication or rate-limiting on the API
- ~~No structured logging or observability hooks~~ — structured JSON → Cloud Logging + Prometheus `/metrics` shipped in v2.1.0 ✅
- ~~Dataflow streaming pipeline has no always-free tier (~$0.05/hr on e2-medium) — run only for demos~~ — **Superseded 2026-05-25 by v3.1.0:** Cloud Run `gbfs-poller` + Cloud Scheduler (every 5 min) + BigQuery 7-day partitioned `station_snapshots` table replaces the Dataflow path at zero always-free-tier cost ✅

These are tracked in [`PROJECT-STATUS.md`](PROJECT-STATUS.md).

---

## 📈 Scaling Considerations

The Seoul pipeline processes ~23 GB of raw per-trip CSVs (36 months × ~640 MB) into a 26,303-row hourly dataset via a single Python script that streams each month, aggregates in memory with pandas, and joins Open-Meteo weather. This is deliberate: at portfolio scale, a transparent script beats opaque infrastructure for showing the actual data work. The table below names the heavier alternatives I would reach for at each step-change in data volume or team size.

| Tier | Pattern | When to adopt | Currently in this repo |
|---|---|---|---|
| 1 | **Single-script aggregation** (download → pandas → CSV) | < ~100 GB raw, single contributor, single training window | ✅ Seoul, Paris, Chicago, DC |
| 2 | **DVC + cloud object store** (raw + processed versioned outside Git) | Raw approaching laptop disk capacity, or shared across machines | — |
| 3 | **Lakehouse format** (Iceberg / Delta on S3/GCS) | Multiple contributors, multiple training windows, time-travel needed | — |
| 4 | **Warehouse-native** (BigQuery / Snowflake; query in place, no raw materialisation) | Source data already lives in a warehouse | ✅ NYC (BigQuery `new_york_citibike`) |

For Seoul specifically, **Tier 4 isn't available** — Seoul's 따릉이 data is published as monthly per-trip ZIPs on data.seoul.go.kr, not as a warehouse-native dataset. Tier 1 (a script committed to git, raw ZIPs gitignored, the durable artifact is the code) is the right level of investment for this scale. Tier 2 (DVC) becomes worth the operational overhead when reproducibility crosses machines — at the point a second contributor joins or training kicks off on rented compute.

For NYC, the inverse logic applies — Citi Bike publishes a 17-year history into a BigQuery public dataset, so the script issues a SQL aggregation and only the result lands locally. The right tier is the one that matches the source's distribution model, not the one that looks most impressive on a diagram.

---

## 🔜 Roadmap

### ✅ Foundation — Complete

1. ~~Pin dependencies (`requirements.txt`)~~ ✅
2. ~~Automated tests + CI/CD via GitHub Actions~~ ✅
3. ~~`Dockerfile` + `docker-compose.yml`~~ ✅

### Phase 2 — Multi-City Training ✅ (infrastructure complete)

- [x] `models/train.py` — `--city` + `--data` CLI args; artifacts to `models/artifacts/<city>/`
- [x] `models/predict.py` — `load_artifacts(city)` reads from `models/artifacts/<city>/`
- [x] `services/predictor.py` — per-city lazy cache `Dict[str, tuple]`
- [x] `api/app.py` — `city: str = "Seoul"` field on `PredictionRequest`; lowercase routing
- [x] `data/prepare_city_data.py` — London column-map + NYC BigQuery SQL utility
- [x] README: multi-city RMSE table (Seoul trained; London + NYC pending data download)
- [x] Download London data (`london_merged.csv` from Kaggle) → `prepare_london()` → `data/processed/london_bike_sharing.csv`
- [x] Train London model — RMSE 316.56 bikes/hr (chronological split); artifacts at `models/artifacts/london/`
- [x] Build NYC joined dataset (BigQuery trips + Open-Meteo weather) and run `prepare_nyc_from_joined()`
- [x] Train NYC model; populate RMSE table entry
- [x] Add `prepare_dc_from_joined()` + `data/fetch_dc_weather.py` for Capital Bikeshare
- [x] City slug map in `services/predictor.py` — fixes "new york" → nyc routing + adds "washington dc" → dc
- [x] Download Capital Bikeshare CSVs (2014–2018) → `data/raw/dc/trips/` and run `python data/fetch_dc_weather.py`
- [x] Train DC model — RMSE **119.31** bikes/hr (chronological split); artifacts at `models/artifacts/dc/`
- [x] Populate Washington DC RMSE table entry

### Phase 3 — Cloud Run Deployment ✅ Done (v2.0.0)

- [x] Bake all 6 city model artifacts into Docker image at build time (no runtime volume mount) — `Dockerfile:28-33` runs `python -m models.train` once per city during the image build
- [x] `docker-compose.yml` — removed volume mount; image is self-contained
- [x] GitHub Actions Job 4 — builds and pushes to GHCR using `GITHUB_TOKEN` (no manual secrets required)
- [x] GitHub Actions Job 5 — builds and pushes to Artifact Registry (`us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/`) + redeploys Cloud Run on every merge to main; uses `GCP_SA_KEY` secret
- [x] `gcloud run deploy` executed — Cloud Run live at `https://bike-demand-api-246440913351.us-central1.run.app`
- [x] Health check confirmed: `{"message":"Bike Demand Prediction API is running"}`
- [x] Companion Shiny repo `model_prediction.R` updated with Cloud Run URL in `FASTAPI_URL` comment

### Phase 6 — Observability ✅ **(v2.1.0 — shipped)**

- [x] Structured JSON logging in `services/predictor.py` — city, inputs_hash, n_records, latency_ms → Cloud Logging (stdout, free)
- [x] `/metrics` endpoint via `prometheus-fastapi-instrumentator` — Prometheus text format, pure HTTP, no GCP cost

### Phase 4 — Pub/Sub + Dataflow Pipeline ✅ **Done (v3.0.0 — 2026-05-15)**

- [x] `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB=false` prints to stdout locally
- [x] `pipeline/dataflow_job.py` — Apache Beam: Pub/Sub → 5-min FixedWindows → BigQuery `station_snapshots`
- [x] `config/gcp_config.yaml` — project ID, topic, BQ dataset, Dataflow config (e2-medium, us-central1-f), GBFS city URLs
- [x] `requirements-pipeline.txt` — `apache-beam[gcp]`, `google-cloud-pubsub`, `pyyaml` (separate from inference image)
- [x] `tests/test_pipeline.py` — 5 tests: GBFS schema, TFL schema, ParseMessage (valid + invalid), DirectRunner end-to-end
- [x] GCP provisioning — Pub/Sub topic/sub, BigQuery dataset `bike_demand`, GCS bucket `gs://bike-demand-staging`, IAM roles
- [x] End-to-end verified — `bike_demand.station_snapshots`: nyc 6,624 rows, first_window 2026-05-15 13:05:00 UTC ✅
- Unlocks companion Shiny repo Phase 7F (v1.2.0) ✅

### Phase 5 — Vertex AI + Experiment Tracking ✅ **Done (v4.0.0 — 2026-05-17)**

Spec: [`docs/superpowers/specs/2026-05-16-phase5-vertex-mlflow-design.md`](docs/superpowers/specs/2026-05-16-phase5-vertex-mlflow-design.md)

- [x] `pipeline/retrain_job.py` — Vertex AI CustomJob: CSV → chronological split → 6-combo hyperparameter sweep → MLflow → RMSE gate (3% threshold) → Model Registry promotion
- [x] `pipeline/vertex_trigger.py` — Cloud Run HTTP endpoint: POST → submit CustomJob async; `aiplatform_v1.JobServiceClient` with `scheduling.timeout: 1800s` server-side billing cap
- [x] `Dockerfile.training` + `requirements-vertex.txt` — training container; `python -m pipeline.retrain_job` CMD; CI Job 6 green ✅
- [x] `config/gcp_config.yaml` — `vertex_ai:` (job_timeout_seconds: 1800, n1-highmem-2) + `mlflow:` + `retraining:` blocks
- [x] `models/train.py` — chronological 80/20 split (correctness fix); MAE metric added
- [x] `.github/workflows/ci.yml` — Job 6: build + push `bike-demand-training` to GAR on merge to main
- [x] GCP provisioned — Vertex AI API enabled; `vertex-sa` SA + IAM; `bike-demand-trigger` Cloud Run live; Cloud Scheduler (Sundays 02:00 UTC); Cloud Monitoring email alerts (log-based)
- [x] Task 9 verification — manual Vertex AI job ran ~10 min; 4 of 6 cities (Seoul / London / NYC / DC) in MLflow Production registry at v4.0.0 cut-off; `gs://bike-demand-staging/mlflow/mlflow.db` uploaded; 47 model artifacts in GCS. Paris and Chicago promotion is open candidate (b) in PROJECT-STATUS.md Next Step
- [x] GitHub release v4.0.0 published (2026-05-17)

### Phase 8 — Cloud Run GBFS Poller ✅ Done (v3.1.0 — 2026-05-25)

Replaces the paused Dataflow streaming path with a zero-always-free-tier Cloud Run service. Driven by Cloud Scheduler every 5 minutes; writes to a BigQuery 7-day partitioned `station_snapshots` table; consumed by the companion R Shiny dashboard's GCP Stream tab.

- [x] `requirements-poller.txt` — slim deps (fastapi, uvicorn, google-cloud-bigquery, httpx) separated from inference + Vertex training images
- [x] `pipeline/window_agg.py` — pure-Python helper: groups GBFS snapshots by (city, station_id, station_name) and computes avg/min/max bike counts + snapshot count per 5-minute window; mirrors the Dataflow `WindowedAgg` rounding behaviour (2 decimal places)
- [x] `pipeline/gbfs_poller_service.py` — FastAPI Cloud Run app: GET `/health`, POST `/poll` triggers a 5-minute window collection across all configured cities → window_agg → BigQuery direct insert
- [x] `Dockerfile.poller` — slim python:3.11-slim image; non-root user; only the poller's deps installed
- [x] `tests/test_window_agg.py` — 5 unit tests on the aggregator (empty input, single snapshot, multi-snapshot avg/min/max, multi-city/station keying, 2-decimal rounding parity)
- [x] `tests/test_gbfs_poller_service.py` — 3 tests on the FastAPI service contract
- [x] GCP provisioned — `gbfs-poller` Cloud Run service deployed to `us-central1`; `gbfs-poller-cron` Cloud Scheduler job (every 5 min); BigQuery `station_snapshots` table re-partitioned with a 7-day expiry; service account + IAM bindings
- [x] End-to-end verified — 6,032 rows / 5-minute window across NYC / DC / London / Chicago; GCP Stream tab in the companion R Shiny dashboard now streams within ~10 min of scheduler start
- [x] CI hotfix `7d43a81` — removed unused `import pytest` in `tests/test_window_agg.py` that gated Ruff lint for 4 commits running
- [x] Cost optimization (2026-05-28) — `/poll` now takes a **single snapshot per 5-minute window** (`POLL_ITERATIONS=1`), down from 5 polls with 4×60s in-request sleeps. Cloud Run billed the full ~248s/run on 1 vCPU (~$46/mo, over the always-free tier); each run is now ~4s. The dashboard's min/max ribbon is driven by cross-station spread (the Shiny query takes `MIN`/`MAX` across stations), not intra-window time samples, so a single snapshot per station is visually identical. `window_agg` is unchanged — it already returns degenerate avg=min=max stats for a one-sample window.

### Phase 9 — Automated Cost Audit ✅ Done (v4.4.0 — 2026-05-29)

Spec: [`docs/superpowers/specs/2026-05-28-cost-audit-design.md`](docs/superpowers/specs/2026-05-28-cost-audit-design.md)

A daily read-only audit that catches resource accumulation (registry bloat, forgotten VMs, growing BQ/GCS, unexpected services, Vertex endpoints) and month-to-date overspend early — built so the automation itself **cannot** add cost. Born from the Artifact Registry silently growing to ~38 GB / 140 image versions because CI pushed an image on every commit with nothing pruning them.

- [x] `cost-audit/thresholds.py` — pure `evaluate_thresholds(readings)`: tunable threshold config + per-domain alert logic; no GCP calls (trivially unit-testable)
- [x] `cost-audit/checks.py` — 7 read-only resource readers (Artifact Registry, Compute, Vertex via REST, BigQuery storage + MTD billing query, GCS, Cloud Run via REST); each independent so one failed read never aborts the scan
- [x] `cost-audit/notify.py` — `format_alert_message` (Slack mrkdwn) + `send_alert` (incoming-webhook POST)
- [x] `cost-audit/main.py` — functions-framework HTTP handler: runs all checks, evaluates, posts to Slack **only on breach** (silent on healthy days), always returns 200, `DRY_RUN` support
- [x] `tests/test_cost_audit.py` — 26 tests (11 threshold eval + 4 notify + 9 mocked check functions + 2 handler integration)
- [x] GCP provisioned — private `cost-audit` Cloud Run service (`maxScale=1`, read-only `cost-audit-sa`); `cost-audit-cron` Cloud Scheduler (daily 09:00 UTC, OIDC); Slack webhook URL in Secret Manager
- [x] Cost-safety — Scheduler-triggered (not Pub/Sub-push, structurally avoids the kill-switch retry-storm); all free-tier reads; no Cloud Monitoring custom-metric writes; ~450 vCPU-sec/month vs 180k free
- [x] End-to-end verified — live run tripped 2 real registry-bloat thresholds and delivered the alert to Slack; delivery switched email → Slack incoming webhook (Microsoft app passwords require 2FA + consumer Outlook SMTP basic-auth is deprecated)

### Phase 7 — Automated Test Suite ✅ Done (2026-05-18)

Spec: [`docs/superpowers/specs/2026-05-18-pytest-suite-design.md`](docs/superpowers/specs/2026-05-18-pytest-suite-design.md)

- [x] `pytest.ini` — register `slow` marker (`-m slow` excludes RMSE gate tests from fast CI job)
- [x] `tests/test_features.py` — `test_feature_schema_is_frozen`: frozen-set guard on 21 columns; failure message names all 6 cities + Vertex AI retrain steps
- [x] `tests/test_model_accuracy.py` — 6 `@pytest.mark.slow` RMSE gate tests (Seoul / London / NYC / DC / Paris / Chicago); chronological 80/20 split matches `train.py` exactly
- [x] `tests/test_routing.py` — 5 no-fallback routing tests: paris → paris, chicago → chicago, "new york" → nyc, "washington dc" → dc, unknown → seoul fallback; uses real sklearn RF + `tmp_path` to catch feature-alignment bugs
- [x] `.github/workflows/ci.yml` Job 6 (`accuracy`) — parallel to Job 2; runs `pytest -m slow` on push to main only; ~5 min wall time (6 RF training runs)

---

## 📂 Dataset

Six city datasets are normalised to a common 14-column Seoul schema before training. All processed files live in `data/processed/`.

| City | Source | Rows | Period | Notes |
|------|--------|------|--------|-------|
| **Seoul** | [Seoul OpenData OA-15182 따릉이 per-trip log](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do) + [Open-Meteo](https://open-meteo.com/) | 26,303 | Jan 2022 – Dec 2024 | Monthly per-trip CSVs aggregated to hourly counts; weather joined via `fetch_seoul_weather.py` |
| **London** | [Kaggle London Bike Sharing](https://www.kaggle.com/datasets/hmavrodiev/london-bike-sharing-dataset) | 17,414 | Jan 2015 – Jan 2017 | 3 meteorological columns absent (zeroed) |
| **NYC** | [BigQuery `new_york_citibike`](https://console.cloud.google.com/marketplace/product/city-of-new-york/nyc-citi-bike) + [Open-Meteo](https://open-meteo.com/) | 34,187 | Jan 2014 – Dec 2018 | Trip counts from BigQuery; weather joined via `fetch_nyc_weather.py` |
| **Washington DC** | [Capital Bikeshare system data](https://capitalbikeshare.com/system-data) + [Open-Meteo](https://open-meteo.com/) | 37,663 | Jan 2014 – Dec 2018 | Trip counts aggregated from quarterly CSVs; weather joined via `fetch_dc_weather.py` |
| **Paris** | [Paris OpenData Vélib' Métropole counter ZIPs](https://opendata.paris.fr) + [Open-Meteo](https://open-meteo.com/) | 17,539 | 2023–2024 | Annual historical ZIPs (2023+2024); MEAN station counter scale; joined via `fetch_paris_weather.py`. 2022 export dropped in v4.3.0 as a data-quality gate (peaked 2h later than 2023+2024 in both AM and PM rush across DST seasons — intrinsic to the provider's aggregation pipeline; reversible if root cause identified). |
| **Chicago** | [Divvy Bikes system data](https://divvybikes.com/system-data) + [Open-Meteo](https://open-meteo.com/) | 32,720 | 2019–2022 | Quarterly CSVs (37/38 quarters; Q2-2019 skipped — different schema); joined via `fetch_chicago_weather.py` |

**Shared schema (14 columns):** `DATE`, `HOUR`, `TEMPERATURE`, `HUMIDITY`, `WIND_SPEED`, `VISIBILITY`, `DEW_POINT_TEMPERATURE`, `SOLAR_RADIATION`, `RAINFALL`, `SNOWFALL`, `SEASONS`, `HOLIDAY`, `FUNCTIONING_DAY`, `RENTED_BIKE_COUNT`

---

## 👤 Author

**Deepan Mehta**

- Data Analytics → Data Engineering → AI/ML Engineering
- Focused on building end-to-end data and ML systems combining analytics, automation, and deployment
- Experience in ETL pipelines, predictive modelling, and analytical databases

🔗 GitHub: [deepan-mehta-analytics](https://github.com/deepan-mehta-analytics)
