# ── Imports ───────────────────────────────────────────────────────────────
import pandas as pd                                           # DataFrame construction for test fixtures
import pytest                                                 # test framework and fixture decorator

from models.features import create_features, get_feature_target  # functions under test


# ── Frozen Feature Schema ─────────────────────────────────────────────────
# Update only after retraining all 6 city models + rebuilding the Vertex AI training container.
EXPECTED_COLUMNS = frozenset({                               # canonical column set from create_features + get_feature_target
    # ── Numeric weather features ──────────────────────────
    "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",         # core demand signals
    "VISIBILITY", "DEW_POINT_TEMPERATURE",                   # atmospheric conditions
    "SOLAR_RADIATION", "RAINFALL", "SNOWFALL",               # precipitation and solar
    # ── Temporal features (derived by create_features) ────
    "year", "month", "day", "dayofweek",                     # date components parsed from DATE column
    # ── One-hot: SEASONS ──────────────────────────────────
    "SEASONS_Autumn", "SEASONS_Spring",                      # season dummies (Seoul schema)
    "SEASONS_Summer", "SEASONS_Winter",                      # all four seasons must be present
    # ── One-hot: HOLIDAY ──────────────────────────────────
    "HOLIDAY_Holiday", "HOLIDAY_No Holiday",                 # public holiday flag dummies
    # ── One-hot: FUNCTIONING_DAY ──────────────────────────
    "FUNCTIONING_DAY_No", "FUNCTIONING_DAY_Yes",             # system operational flag dummies
})


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    """One-row DataFrame covering every input column; reused across all tests."""
    return pd.DataFrame([{                                    # wrap in list so DataFrame has one row
        "DATE": "01/06/2018",                                 # 1 June 2018 — Friday, predictable temporals
        "HOUR": 8,                                            # 8 AM
        "TEMPERATURE": 15.0,                                  # degrees Celsius
        "HUMIDITY": 60,                                       # percent
        "WIND_SPEED": 2.5,                                    # m/s
        "VISIBILITY": 1500,                                   # 10m units
        "DEW_POINT_TEMPERATURE": 7.0,                         # degrees Celsius
        "SOLAR_RADIATION": 0.8,                               # MJ/m^2
        "RAINFALL": 0.0,                                      # mm
        "SNOWFALL": 0.0,                                      # cm
        "SEASONS": "Summer",                                  # categorical season label
        "HOLIDAY": "No Holiday",                              # categorical holiday flag
        "FUNCTIONING_DAY": "Yes",                             # rental system is operational
        "RENTED_BIKE_COUNT": 500,                             # target; included for get_feature_target split
    }])


@pytest.fixture
def full_schema_df():
    """Multi-row DataFrame covering every categorical value so pd.get_dummies produces the full schema."""
    rows = []                                                 # accumulate one row per seasonal + holiday combo
    for season in ["Spring", "Summer", "Autumn", "Winter"]:  # all four seasons must be represented
        for holiday in ["Holiday", "No Holiday"]:            # both holiday states must be represented
            for func_day in ["Yes", "No"]:                   # both functioning-day states must be represented
                rows.append({                                 # one complete record per combination
                    "DATE": "01/06/2018",                    # fixed date — temporal values constant across rows
                    "HOUR": 8,                               # fixed hour
                    "TEMPERATURE": 15.0,                     # fixed numeric features
                    "HUMIDITY": 60,
                    "WIND_SPEED": 2.5,
                    "VISIBILITY": 1500,
                    "DEW_POINT_TEMPERATURE": 7.0,
                    "SOLAR_RADIATION": 0.8,
                    "RAINFALL": 0.0,
                    "SNOWFALL": 0.0,
                    "SEASONS": season,                       # varies per row — all four seasons present
                    "HOLIDAY": holiday,                      # varies per row — both states present
                    "FUNCTIONING_DAY": func_day,             # varies per row — both states present
                    "RENTED_BIKE_COUNT": 500,                # target column — required by get_feature_target
                })
    return pd.DataFrame(rows)                                # 16-row DataFrame covering all categorical combos


# ── Temporal Feature Extraction ───────────────────────────────────────────

def test_create_features_extracts_year(sample_df):
    """create_features must derive year from the DATE column."""
    result = create_features(sample_df.copy())                # apply feature engineering on a copy
    assert "year" in result.columns                           # year column must be present
    assert result["year"].iloc[0] == 2018                     # correct year from 01/06/2018


def test_create_features_extracts_month(sample_df):
    """create_features must derive month-of-year from the DATE column."""
    result = create_features(sample_df.copy())                # apply feature engineering on a copy
    assert "month" in result.columns                          # month column must be present
    assert result["month"].iloc[0] == 6                       # June is month 6


def test_create_features_extracts_day(sample_df):
    """create_features must derive day-of-month from the DATE column."""
    result = create_features(sample_df.copy())                # apply feature engineering on a copy
    assert "day" in result.columns                            # day column must be present
    assert result["day"].iloc[0] == 1                         # first of the month


def test_create_features_extracts_dayofweek(sample_df):
    """create_features must derive ISO weekday index from the DATE column."""
    result = create_features(sample_df.copy())                # apply feature engineering on a copy
    assert "dayofweek" in result.columns                      # dayofweek column must be present
    # 01/06/2018 is a Friday; pandas dt.dayofweek is Monday=0 … Friday=4
    assert result["dayofweek"].iloc[0] == 4                   # Friday maps to index 4


# ── One-Hot Encoding ──────────────────────────────────────────────────────

def test_get_feature_target_encodes_seasons(sample_df):
    """get_feature_target must one-hot encode the SEASONS column."""
    df = create_features(sample_df.copy())                    # derive temporal features first
    X, _ = get_feature_target(df)                             # split into features and target
    seasons_cols = [c for c in X.columns if c.startswith("SEASONS_")]  # collect SEASONS_ dummies
    assert len(seasons_cols) > 0                              # at least one SEASONS_ dummy must exist


def test_get_feature_target_encodes_holiday(sample_df):
    """get_feature_target must one-hot encode the HOLIDAY column."""
    df = create_features(sample_df.copy())                    # derive temporal features first
    X, _ = get_feature_target(df)                             # split
    holiday_cols = [c for c in X.columns if c.startswith("HOLIDAY_")]  # collect HOLIDAY_ dummies
    assert len(holiday_cols) > 0                              # at least one HOLIDAY_ dummy must exist


# ── Feature Schema Alignment ──────────────────────────────────────────────

def test_get_feature_target_removes_raw_date(sample_df):
    """get_feature_target must not include the raw DATE string in features."""
    df = create_features(sample_df.copy())                    # derive temporal features first
    X, _ = get_feature_target(df)                             # split
    assert "DATE" not in X.columns                            # raw date string must not leak into X


def test_get_feature_target_removes_target_from_X(sample_df):
    """get_feature_target must exclude RENTED_BIKE_COUNT from the feature matrix."""
    df = create_features(sample_df.copy())                    # derive temporal features first
    X, y = get_feature_target(df)                             # split into X and y
    assert "RENTED_BIKE_COUNT" not in X.columns               # target must not leak into features
    assert len(y) == len(df)                                  # y must have the same row count as input


def test_get_feature_target_includes_core_numerics(sample_df):
    """Feature matrix must include the core numeric weather and temporal columns."""
    df = create_features(sample_df.copy())                    # derive temporal features first
    X, _ = get_feature_target(df)                             # split
    expected = {                                              # minimum expected numeric columns
        "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",     # weather signals
        "year", "month", "day", "dayofweek",                  # temporal features derived by create_features
    }
    assert expected.issubset(set(X.columns))                  # all expected numerics must be present


# ── Schema Guard ──────────────────────────────────────────────────────────

def test_feature_schema_is_frozen(full_schema_df):
    """Feature column set must not change without retraining all city models."""
    df = create_features(full_schema_df.copy())              # derive temporal columns from DATE
    X, _ = get_feature_target(df)                            # one-hot encode and drop target + DATE
    assert set(X.columns) == EXPECTED_COLUMNS, (             # exact column set must match frozen schema
        "Feature schema changed. Before merging:\n"
        "  - retrain all 6 city models: seoul, london, nyc, dc, paris, chicago\n"
        "  - rebuild and push the Vertex AI training container (Dockerfile.training)\n"
        "  - verify RMSE gates still pass: pytest -m slow tests/test_model_accuracy.py"
    )
