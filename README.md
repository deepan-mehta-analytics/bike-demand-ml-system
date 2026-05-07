# 🚴 Bike Demand ML System

## ⚡ Quick Summary
This project is the **Python ML backend** in a two-repo portfolio system. It forecasts hourly bike-rental demand from weather and temporal signals, exposes the model through a FastAPI inference API, and is consumed by the companion [R Shiny dashboard](https://github.com/deepan-mehta-analytics/bike-demand-prediction) via `httr::POST /predict`. The architecture separates training from inference cleanly, persists model artifacts for reproducible deployment, and is containerised for local and cloud deployment.

It is engineered as the next stage in a data analytics → data engineering → ML engineering trajectory: a model that ships to an API, not a notebook that ships to a screenshot.

### End-to-End ML System with FastAPI Inference, Service-Layer Architecture & Random Forest Regressor

---

## 🏷️ Project Badges

[![CI](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/ci.yml/badge.svg)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.8-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Inference_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![pandas](https://img.shields.io/badge/pandas-3.x-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-Validation-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Docker](https://img.shields.io/badge/Docker-Containerised-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=for-the-badge)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system)

---

## 📌 Project Overview
This project implements an **end-to-end machine learning system** for forecasting hourly bike-rental demand. It evolves from data analytics into a structured ML platform with a clean separation between training, persistence, business logic, and API delivery.

It uses the [Seoul Bike Sharing Demand Dataset (UCI)](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand), demonstrating ML engineering patterns required to ship a model from notebook into a deployable API.

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
| Containerisation | Docker + Docker Compose | python:3.11-slim image; models volume-mounted from host |
| Testing | pytest + httpx + anyio | Unit tests (feature pipeline) + async integration tests (API) |
| Linting / CI | ruff + GitHub Actions | Lint → test → docker build on every push to main |

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
├── requirements.txt                    ← pinned Python dependencies
├── Dockerfile                          ← python:3.11-slim, non-root user, health check
├── docker-compose.yml                  ← local dev orchestration; models volume mount
├── .dockerignore                       ← excludes venv/, .git/, *.pkl from build context
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── ci.yml                      ← ruff lint → pytest → docker build on every push
│
├── data/
│   ├── raw/                            ← place Seoul Bike Sharing CSV here
│   └── processed/                      ← reserved for processed outputs
│
├── models/
│   ├── features.py                     ← shared feature pipeline (used by train + predict)
│   ├── train.py                        ← training CLI: --city, --data; saves to artifacts/<city>/
│   ├── predict.py                      ← inference pipeline: load_artifacts(city), predict()
│   ├── __init__.py
│   └── artifacts/                      ← per-city artifact directories (gitignored)
│       └── seoul/                      ← example: random_forest_model.pkl + feature_columns.pkl
│
├── data/
│   ├── prepare_city_data.py            ← normalise London/NYC CSVs to Seoul schema
│   ├── raw/                            ← place city CSVs here before training
│   └── processed/                      ← output of prepare_city_data.py goes here
│
├── services/
│   └── predictor.py                    ← service layer: lazy singleton, decouples API from ML
│
├── api/
│   └── app.py                          ← FastAPI app: /, /predict, /docs
│
├── tests/
│   ├── conftest.py                     ← anyio asyncio backend fixture for async tests
│   ├── test_features.py                ← unit tests: temporal extraction, one-hot, schema
│   └── test_api.py                     ← integration tests: 200/422 via httpx.AsyncClient
│
└── venv/                               ← virtual environment (gitignored)
```

---

## ▶️ How to Run

### 📌 Option 1 — Local (Recommended for development)

> Train the model first (`python models/train.py`) so the `.pkl` artefacts are on disk before starting the service.

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

Download [Seoul Bike Sharing Demand (UCI)](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand) and save the CSV at:

```
data/raw/seoul_bike_sharing.csv
```

#### 5. Train the model

```bash
python -m models.train
```

This produces:

- `models/random_forest_model.pkl`
- `models/feature_columns.pkl`

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
      "DATE": "01/12/2017", "HOUR": 8,
      "TEMPERATURE": -5.2, "HUMIDITY": 37,
      "WIND_SPEED": 2.2, "VISIBILITY": 2000,
      "DEW_POINT_TEMPERATURE": -17.6, "SOLAR_RADIATION": 0.0,
      "RAINFALL": 0.0, "SNOWFALL": 0.0,
      "SEASONS": "Winter", "HOLIDAY": "No Holiday",
      "FUNCTIONING_DAY": "Yes"
    }]
  }'
```

Expected response: `{"predictions": [605.6]}`

> **`city`** is optional — defaults to `"Seoul"` if omitted. When London and NYC models are trained, pass `"city": "London"` or `"city": "NYC"` to route to their per-city artifacts.

---

### 🐳 Option 2 — Docker Compose

```bash
# 1. Train model artefacts on the host first
python models/train.py

# 2. Build and start the container (artefacts are volume-mounted into /app/models)
docker compose up --build

# 3. API is live at http://localhost:8000
```

---

## 🧪 Tests

```bash
# Train model artefacts first (required for full integration run)
python models/train.py

# Run the full test suite
pytest tests/
```

The suite has two modules:

| Module | Type | What it covers |
|---|---|---|
| `tests/test_features.py` | Unit | Temporal extraction (year/month/day/dayofweek), one-hot encoding for SEASONS and HOLIDAY, feature schema completeness |
| `tests/test_api.py` | Integration | `httpx.AsyncClient` against the live ASGI app: 200 for single record, 200 for batch, 422 for wrong type (`HOUR="not-an-int"`), 422 for missing required field |

CI runs lint → pytest → docker build on every push to `main`.

---

## 📊 Model Performance

### Per-City RMSE

Artifacts stored at `models/artifacts/<city>/` — train each city with `python -m models.train --city <name> --data <path>`.

| City | Dataset | RMSE (bikes/hr) | Status |
|------|---------|-----------------|--------|
| Seoul | UCI Seoul Bike Sharing (8,760 rows) | **173.21** | ✅ Trained |
| London | Kaggle London Bike Sharing (`london_merged.csv`) | — | Pending data download |
| NYC | BigQuery `new_york_citibike` + Open-Meteo weather | — | Pending data prep |

See `data/prepare_city_data.py` for London column-mapping and NYC BigQuery SQL.

### Seoul — Random Forest Regressor

| Metric | Value |
|---|---|
| Algorithm | Random Forest Regressor (`n_estimators=100`, `random_state=42`) |
| RMSE | **173.21** |
| MSE | 30,002.93 |
| Train / Test split | 80 / 20 (`random_state=42`) |
| Scaling | None (RF is scale-invariant — scaling removed from pipeline) |

### Top Feature Importances

| Rank | Feature | Importance |
|---|---|---|
| 1 | `TEMPERATURE` | 0.339 |
| 2 | `HOUR` | 0.302 |
| 3 | `SOLAR_RADIATION` | 0.097 |
| 4 | `HUMIDITY` | 0.084 |
| 5 | `dayofweek` | 0.040 |
| 6 | `RAINFALL` | 0.035 |
| 7 | `DEW_POINT_TEMPERATURE` | 0.024 |
| 8 | `SEASONS_Autumn` | 0.023 |
| 9 | `month` | 0.013 |
| 10 | `day` | 0.009 |

**Key insight surfaced by the model:** Temperature and hour-of-day dominate the forecast. This is consistent with rider behaviour driven by commuting cycles and weather comfort — a sanity check that the model has learned something real, not artifacts of the encoding.

---

## 🧪 Smoke-Test Evidence

End-to-end verification against a freshly trained model running behind `uvicorn`:

| Scenario | Input | Predicted Demand |
|---|---|---|
| Single record — winter 8 AM | `TEMP=-5.2`, `HOUR=8`, `SEASONS=Winter` | **605.6** bikes |
| Batch — summer rush hour | `HOUR=18`, `SEASONS=Summer`, `TEMP=24.5` | **3028.01** bikes |
| Batch — summer 03:00 | `HOUR=3`, `SEASONS=Summer`, `TEMP=18.0` | **435.64** bikes |
| Malformed input | `HOUR="not-an-int"` | **HTTP 422** (Pydantic validation rejected) |

The 7× spread between summer rush and middle-of-night confirms the model captures the strong hour-of-day signal seen in feature importances, and the Pydantic 422 confirms the API boundary rejects invalid types before they reach the model.

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
- No hyperparameter tuning (GridSearch / Optuna)
- No experiment tracking (MLflow / Weights & Biases)
- No request authentication or rate-limiting on the API
- No structured logging or observability hooks

These are tracked in [`PROJECT-STATUS.md`](PROJECT-STATUS.md).

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
- [ ] Download London data (`london_merged.csv` from Kaggle) and run `prepare_london()`
- [ ] Build NYC joined dataset (BigQuery trips + Open-Meteo weather) and run `prepare_nyc_from_joined()`
- [ ] Train London and NYC models; populate RMSE table

### Phase 3 — Cloud Run Deployment

- [ ] `cloudbuild.yaml` or GH Actions step — build → push to Artifact Registry → deploy to Cloud Run
- [ ] `config/cloud_run.yaml` — memory 512Mi, concurrency 80, env vars
- [ ] Update companion Shiny repo `FASTAPI_URL` env var to point at Cloud Run URL

### Phase 4 — Pub/Sub + Dataflow Pipeline

- [ ] `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB=false` runs locally
- [ ] `pipeline/dataflow_job.py` — Apache Beam: Pub/Sub → 5-min window → BigQuery / DuckDB
- [ ] `config/gcp_config.yaml` — project ID, topic, BQ dataset, staging bucket, region

### Phase 5 — Vertex AI + Experiment Tracking

- [ ] MLflow `autolog()` in `models/train.py`; register model if RMSE improves
- [ ] `pipeline/retrain_job.py` — BigQuery → feature engineering → retrain → log → register

### Phase 6 — Observability

- [ ] Structured JSON logging in `services/predictor.py` — city, inputs hash, prediction, latency_ms
- [ ] `/metrics` endpoint via `prometheus-fastapi-instrumentator`

---

## 📂 Dataset

**Source:** [UCI Machine Learning Repository — Seoul Bike Sharing Demand](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand)

- 8,760 hourly observations (Dec 2017 – Nov 2018)
- 13 input features:
  - **Temporal** — date, hour, season, holiday flag, functioning-day flag
  - **Meteorological** — temperature, humidity, wind speed, visibility, dew point, solar radiation, rainfall, snowfall
- **Target:** hourly count of bikes rented (`RENTED_BIKE_COUNT`)

---

## 👤 Author

**Deepan Mehta**

- Data Analytics → Data Engineering → AI/ML Engineering
- Focused on building end-to-end data and ML systems combining analytics, automation, and deployment
- Experience in ETL pipelines, predictive modelling, and analytical databases

🔗 GitHub: [deepan-mehta-analytics](https://github.com/deepan-mehta-analytics)
