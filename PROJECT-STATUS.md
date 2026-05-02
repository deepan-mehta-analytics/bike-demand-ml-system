# Project Status — Bike Demand ML System

## Current Stage

ML pipeline complete (Training + Inference)

---

## ✅ Completed

### Data & Features

* Dataset ingested and structured
* Datetime parsing handled (DD/MM format)
* Feature extraction:

  * year, month, day, dayofweek
* One-hot encoding applied to categorical features

### Model Training

* Baseline Linear Regression implemented
* Upgraded to Random Forest Regressor
* Evaluation:

  * MSE
  * RMSE ≈ 173

### Model Persistence

* Saved artifacts:

  * model (`random_forest_model.pkl`)
  * scaler (`scaler.pkl`)
  * feature schema (`feature_columns.pkl`)

### Inference Pipeline

* `predict.py` implemented
* Loads saved artifacts
* Applies same feature transformations
* Uses saved schema (no dependency on training data)
* Generates predictions successfully

### Git & Project Structure

* Clean modular structure
* `.gitignore` configured (no `.pkl` files committed)
* Code committed and pushed

---

## 🧠 Key Learnings

* Separation of training and inference pipelines
* Importance of feature consistency
* Handling categorical + datetime features
* Model persistence and reuse
* Clean Git practices for ML systems

---

## ⚠️ Known Limitations

* Feature scaling applied but not required for Random Forest
* No hyperparameter tuning yet
* No API layer
* No experiment tracking

---

## 🚀 Next Step

Refactor API architecture by separating business logic from API layer.

---
## 🔜 Upcoming Tasks

1. Create service layer (`services/predictor.py`)
2. Move prediction logic out of API into service module
3. Refactor API to call service layer
4. Add request/response models for better structure
5. Optimize pipeline (remove unnecessary scaling for Random Forest)
---
### API Layer (FastAPI)

* FastAPI application implemented (`api/app.py`)
* Health check endpoint (`/`) added
* Prediction endpoint (`/predict`) created
* Input validation using Pydantic schema
* End-to-end inference via API confirmed
* Swagger UI testing enabled (`/docs`)
