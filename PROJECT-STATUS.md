# Project Status — Bike Demand ML System (Python Backend)

> Re-entry command: `"resume bike-demand-ml-system project"`
> Companion repo: `D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction`

---

## 🌐 Ecosystem Snapshot

Both repos form a single portfolio system. Track them together here.

| Repo | Role | Current Phase | Status | Last Commit |
|------|------|--------------|--------|-------------|
| **bike-demand-ml-system** (this repo) | Python FastAPI + ML training | Phase 2 Multi-City + CI fixes | ✅ Complete | `1ae284f` |
| **bike_demand_prediction** | R Shiny dashboard | Phase 7H Containerisation + city routing | ✅ Complete | `b39cede` |

### Trained City Models

| City | Dataset | Rows | RMSE | Top Feature | Artifacts |
|------|---------|------|------|-------------|-----------|
| Seoul | UCI Seoul Bike Sharing | 8,760 | **173.21** | TEMPERATURE (0.34) | `models/artifacts/seoul/` |
| London | Kaggle london_merged.csv | 17,414 | **228.58** | HOUR (0.71) | `models/artifacts/london/` |
| NYC | BigQuery citibike_trips (2014–2018) + Open-Meteo | 34,187 | **345.69** | HOUR (0.52) | `models/artifacts/nyc/` |

### Next Milestones (Both Repos)

| Repo | Next Phase | Dependency |
|------|-----------|------------|
| bike-demand-ml-system | Phase 3 — Cloud Run Deployment | None — can start now |
| bike_demand_prediction | Phase 7F — GCP Streaming Pipeline | Waits on Python Phase 4 (Pub/Sub + Dataflow) |

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
* `services/predictor.py`: fallback to Seoul for cities without trained artifacts (Paris, Chicago)
* `data/prepare_city_data.py`: `prepare_london()`, `nyc_bigquery_sql()`, `prepare_nyc_from_joined()`

### Infrastructure (containerisation + CI)
* `requirements.txt` — 10 packages pinned; `pytest.ini` — `pythonpath = .`
* 15 tests: 9 unit (feature engineering) + 5 integration (API) + 1 city default test
* `Dockerfile` — `python:3.11-slim`, non-root `appuser`, stdlib health check; inline comments moved to standalone lines (Docker parse fix, commit `1ae284f`)
* `docker-compose.yml` — fastapi service, port 8000, `./models:/app/models` volume, `USE_PUBSUB=false`
* `.github/workflows/ci.yml` — ruff lint → pytest (trains Seoul model) → docker build; all 3 jobs green

---

## ⚠️ Known Limitations

* No hyperparameter tuning — single fixed RF config (`n_estimators=100`, `random_state=42`)
* No experiment tracking — no MLflow / Vertex AI integration
* No API authentication or rate-limiting
* No structured logging or observability in service layer
* No drift monitoring on inference inputs
* Paris and Chicago have no trained models — service falls back to Seoul (proxy only)
* NYC RMSE (345.69) is higher due to larger absolute trip volumes; adding weather data beyond
  temperature/humidity (e.g. actual visibility, not Open-Meteo zeros) would likely reduce it

---

## 🔜 Roadmap

### Phase 3 — Cloud Run Deployment ← **next**
* GH Actions step: build image → push to Artifact Registry → deploy to Cloud Run
* `config/cloud_run.yaml` — memory 512Mi, concurrency 80, env vars for city artifact paths
* R Shiny `FASTAPI_URL` switches from `http://fastapi:8000` (local) → Cloud Run URL (GCP)
* Pre-requisite for R Shiny Phase 7F (streaming pipeline needs a stable FastAPI endpoint)

### Phase 4 — Pub/Sub + Dataflow Pipeline
* `pipeline/gbfs_to_pubsub.py` — GBFS poller every 60s; `USE_PUBSUB=false` for local mode
* `pipeline/dataflow_job.py` — Apache Beam: Pub/Sub → 5-min windowed aggregation → BigQuery
* `config/gcp_config.yaml` — project ID, topic, BQ dataset, staging bucket, region
* Unlocks R Shiny Phase 7F (companion repo waits on this)

### Phase 5 — Vertex AI + Experiment Tracking
* MLflow `autolog()` in `models/train.py`; register model if RMSE improves vs current baseline
* `pipeline/retrain_job.py` — BigQuery → feature engineering → retrain → log → register best model

### Phase 6 — Observability
* Structured JSON logging in `services/predictor.py` — city, inputs hash, prediction, latency_ms
* `/metrics` Prometheus endpoint via `prometheus-fastapi-instrumentator`

---

## 🚀 Next Step

**Phase 3 — Cloud Run Deployment.** Resume with: `"resume bike-demand-ml-system project"`
