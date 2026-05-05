# Project Status — Bike Demand ML System

## Current Stage

ML pipeline + service layer + FastAPI inference all live and verified end-to-end. Model retrained on the cleaned (scaler-free) pipeline; `/predict` smoke-tested with single, batch, and malformed inputs. (as of 2026-05-05)

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

### Git & Project Structure
* Clean modular structure (`api/`, `services/`, `models/`, `data/`)
* `.gitignore` configured (no `.pkl`, `__pycache__/`, `venv/`, `.env` committed)
* Cleanup pass on `main` branch — pending commit

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

* No `requirements.txt` / `pyproject.toml` yet (dependencies installed ad-hoc)
* No hyperparameter tuning (single fixed RF configuration)
* No experiment tracking (no MLflow / W&B integration)
* No automated test suite (unit / integration)
* No CI/CD pipeline (no GitHub Actions)
* No containerised deployment (no Dockerfile / compose)
* No request authentication or rate-limiting on the API
* No structured logging or observability hooks in the service layer
* No drift monitoring on inference inputs

---

## 🔜 Roadmap

Synchronised with the [README Roadmap](README.md#-roadmap):

1. Pin dependencies (`requirements.txt`)
2. Hyperparameter tuning (Optuna or `GridSearchCV`)
3. Experiment tracking (MLflow run logs + model registry)
4. Automated tests — pytest unit tests for `features.py` / `predict.py`, plus FastAPI integration tests via `httpx.AsyncClient`
5. `Dockerfile` + `docker-compose.yml` for reproducible execution
6. CI/CD via GitHub Actions (lint + test + container build on every push)
7. Structured JSON logging + Prometheus metrics in the service layer
8. API authentication (API key or OAuth2)
9. Drift monitoring on inference inputs

---

## 🚀 Next Step

Commit the 2026-05-05 cleanup pass (5 modified files + new `services/predictor.py`, plus `.claude/` added to `.gitignore`). Then begin Roadmap item #1: pin dependencies in `requirements.txt`.
