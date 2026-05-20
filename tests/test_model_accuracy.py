# ── Imports ───────────────────────────────────────────────────────────────
import pandas as pd                                           # CSV loading for each city dataset
import pytest                                                 # test framework and slow marker
from sklearn.ensemble import RandomForestRegressor            # same model class and defaults used in train.py
from sklearn.metrics import root_mean_squared_error           # sklearn 1.4+ dedicated RMSE function; no squared kwarg

from models.features import create_features, get_feature_target  # shared feature pipeline


# ── City Config ───────────────────────────────────────────────────────────
# Each tuple: (csv_path, city_label, rmse_threshold)
# Thresholds carry ~50% headroom above trained RMSE to absorb minor random-state variance
# while still catching meaningful data-quality or feature-pipeline regressions.
# All six cities load from data/processed/ (uppercase Seoul schema).
_CITY_CONFIGS = [
    ("data/processed/seoul_bike_sharing.csv",  "seoul",  2200),  # trained RMSE 1503.52; threshold 2200
    ("data/processed/london_bike_sharing.csv", "london",  350),  # trained RMSE 228.58; threshold 350
    ("data/processed/nyc_bike_sharing.csv",    "nyc",     500),  # trained RMSE 345.69; threshold 500
    ("data/processed/dc_bike_sharing.csv",     "dc",      150),  # trained RMSE  97.47; threshold 150
    ("data/processed/paris_bike_sharing.csv",  "paris",    50),  # trained RMSE  23.30; threshold  50 (normalised MEAN scale)
    ("data/processed/chicago_bike_sharing.csv","chicago",  350),  # trained RMSE 202.99; threshold 350
]


# ── RMSE Gate ─────────────────────────────────────────────────────────────

@pytest.mark.slow                                             # excluded from Job 2; runs only in Job 7 (push to main)
@pytest.mark.parametrize(
    "csv_path, city, threshold",
    _CITY_CONFIGS,
    ids=[cfg[1] for cfg in _CITY_CONFIGS],                   # label each parametrised test by city name
)
def test_city_rmse_within_threshold(csv_path, city, threshold):
    """Train a fresh RF from the committed CSV and assert holdout RMSE is below threshold.

    Catches data-quality regressions and feature-pipeline breaks.
    Does NOT test production .pkl artifacts — that is intentionally separate.
    """
    # ── Load + feature engineering ────────────────────────────────────────
    df = pd.read_csv(csv_path)                               # load committed city CSV from repo
    df = create_features(df)                                 # derive year/month/day/dayofweek from DATE
    X, y = get_feature_target(df)                           # one-hot encode categoricals; drop DATE and target

    # ── Chronological 80/20 split (mirrors train.py exactly) ─────────────
    split_idx = int(len(df) * 0.8)                          # 80% boundary — no shuffle, preserves time order
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]  # earlier rows for training
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]  # later rows for evaluation

    # ── Train ─────────────────────────────────────────────────────────────
    model = RandomForestRegressor(n_estimators=100, random_state=42)  # matches train.py default hyperparameters
    model.fit(X_train, y_train)                              # fit on training partition

    # ── Evaluate ──────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)                           # generate holdout predictions
    rmse = root_mean_squared_error(y_test, y_pred)           # sklearn 1.4+ direct RMSE; no squared kwarg needed

    # ── Assert ────────────────────────────────────────────────────────────
    assert rmse < threshold, (                               # fail loudly with city name + actual RMSE
        f"{city} RMSE {rmse:.2f} exceeds threshold {threshold}. "
        f"Check {csv_path} for data corruption or schema changes in models/features.py."
    )
