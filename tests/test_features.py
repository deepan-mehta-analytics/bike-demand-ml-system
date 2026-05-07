# ── Imports ───────────────────────────────────────────────────────────────
import pandas as pd                                           # DataFrame construction for test fixtures
import pytest                                                 # test framework and fixture decorator

from models.features import create_features, get_feature_target  # functions under test


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
