# Bike Demand ML System

Production-oriented machine learning system for predicting bike rental demand using real-world weather and temporal data.

---

## 🚀 Overview

This project evolves from data analytics into a structured ML system with:

* Feature engineering pipeline
* Model training and evaluation
* Model persistence
* Inference (prediction) pipeline
* Clean, modular project structure

---

## 🧠 Model

* Algorithm: Random Forest Regressor
* Evaluation Metric: RMSE
* Current Performance: ~173 RMSE

---

## ⚙️ Pipeline

### Training (`models/train.py`)

* Loads raw data
* Applies feature engineering
* Encodes categorical variables
* Splits into train/test
* Trains model
* Saves:

  * model
  * scaler
  * feature schema

### Prediction (`models/predict.py`)

* Loads saved artifacts
* Applies same feature transformations
* Aligns input using saved schema
* Generates predictions

### API (`api/app.py`)

* FastAPI-based inference service
* Endpoint: `POST /predict`
* Accepts JSON input matching feature schema
* Returns predicted bike demand
* Includes input validation using Pydantic
* Interactive testing via Swagger UI (`/docs`)

---

## 📁 Project Structure

```
bike-demand-ml-system/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── models/
│   ├── features.py
│   ├── train.py
│   ├── predict.py
│   └── __init__.py
│
├── README.md
├── PROJECT-STATUS.md
└── .gitignore
```

---

## 🧩 Key Concepts Implemented

* Train vs Inference separation
* Feature consistency across pipelines
* Handling datetime and categorical variables
* Model persistence using joblib
* Reproducible ML workflow
* Git hygiene for ML projects

---

## ⚠️ Notes

* `.pkl` files are excluded from Git (reproducible artifacts)
* Feature schema is saved to ensure consistent inference

---

## ▶️ Next Steps

* FastAPI deployment layer
* Hyperparameter tuning
* Model optimization
* Experiment tracking
