# ── Imports ───────────────────────────────────────────────────────────────
import io                                                     # in-memory buffer to measure the saved model size
import joblib                                                 # same serialiser train.py uses for the .pkl artifact
import pandas as pd                                           # CSV loading for each city dataset
import pytest                                                 # test framework and slow marker
from sklearn.ensemble import RandomForestRegressor            # same model class and defaults used in train.py
from sklearn.metrics import root_mean_squared_error           # sklearn 1.4+ dedicated RMSE function; no squared kwarg

from models.features import create_features, get_feature_target  # shared feature pipeline
from models.train import forest_settings                      # per-city forest settings — the same ones the image is built with

# ── Model Size Budget ─────────────────────────────────────────────────────
# The API caches every city's model in one Cloud Run instance capped at 512 MiB.
# v4.5.1: full-depth forests (108–261 MB each, ~1.2 GB for six) crashed the
# instance on every /predict. Six models under these caps total <= 195 MB
# (measured ~152 MB); all six loaded in one API process peak well under 512 MiB.
_MAX_MODEL_MB = {"paris": 70}                                 # Paris: 100 trees + depth cap, measures ~61 MB
_DEFAULT_MAX_MODEL_MB = 25                                    # 50 trees + 5-row leaves, measures ~10–22 MB


# ── City Config ───────────────────────────────────────────────────────────
# Each tuple: (csv_path, city_label, rmse_threshold)
# Thresholds carry ~50% headroom above trained RMSE to absorb minor random-state variance
# while still catching meaningful data-quality or feature-pipeline regressions.
# All six cities load from data/processed/ (uppercase Seoul schema).
_CITY_CONFIGS = [
    ("data/processed/seoul_bike_sharing.csv",  "seoul",  2080),  # v4.5.1 RMSE 1363.03 (was 1386.77 unlimited); 2022-2025 OA-15182; threshold = round(1386.77 × 1.5)
    ("data/processed/london_bike_sharing.csv", "london",  350),  # v4.5.1 RMSE 312.75 (was 316.6 unlimited); threshold 350
    ("data/processed/nyc_bike_sharing.csv",    "nyc",     500),  # v4.5.1 RMSE 469.26 (was 470.8 unlimited); threshold 500
    ("data/processed/dc_bike_sharing.csv",     "dc",      150),  # v4.5.1 RMSE 119.54 (was 119.3 unlimited); threshold 150
    ("data/processed/paris_bike_sharing.csv",  "paris",    40),  # v4.5.1 RMSE  20.59 (was 20.51 unlimited; post-v4.3.0 tz fix + Option B drop 2022); threshold 40 (normalised MEAN scale)
    ("data/processed/chicago_bike_sharing.csv","chicago",  350),  # v4.5.1 RMSE 200.69 (was 202.99 unlimited); threshold 350
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
    model = RandomForestRegressor(                           # matches train.py hyperparameters exactly
        random_state=42,                                     # train.py default seed
        **forest_settings(city),                             # same per-city tree count + size cap the Docker image trains with
    )
    model.fit(X_train, y_train)                              # fit on training partition

    # ── Evaluate ──────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)                           # generate holdout predictions
    rmse = root_mean_squared_error(y_test, y_pred)           # sklearn 1.4+ direct RMSE; no squared kwarg needed

    # ── Assert accuracy ───────────────────────────────────────────────────
    assert rmse < threshold, (                               # fail loudly with city name + actual RMSE
        f"{city} RMSE {rmse:.2f} exceeds threshold {threshold}. "
        f"Check {csv_path} for data corruption or schema changes in models/features.py."
    )

    # ── Assert size (keeps the API inside its 512 MiB Cloud Run limit) ────
    buffer = io.BytesIO()                                    # in-memory stand-in for the .pkl file
    joblib.dump(model, buffer)                               # serialise exactly as train.py does
    size_mb = buffer.tell() / 1e6                            # saved model size in MB
    budget_mb = _MAX_MODEL_MB.get(city, _DEFAULT_MAX_MODEL_MB)  # this city's size budget
    assert size_mb <= budget_mb, (                           # fail loudly if a model grows back
        f"{city} model is {size_mb:.1f} MB, over its {budget_mb} MB budget. "
        f"Six cached models must fit in the API's 512 MiB Cloud Run instance — see forest_settings() in models/train.py."
    )
