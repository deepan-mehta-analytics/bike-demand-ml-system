# ── Imports ────────────────────────────────────────────────────────────────
import pandas as pd                                          # DataFrame operations and datetime parsing


# ── Data Loading ────────────────────────────────────────────────────────────

def load_data(path: str) -> pd.DataFrame:
    """Load a city dataset from a CSV file on disk.

    The CSV must use Seoul schema column names, or be pre-normalised by
    data/prepare_city_data.py before being passed here.
    """
    return pd.read_csv(path)                                 # read CSV; returns DataFrame with all columns intact


# ── Feature Engineering ─────────────────────────────────────────────────────

def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive temporal features from the DATE column.

    Adds year, month, day, dayofweek in-place on a copy of the input DataFrame.
    Does not drop the DATE column — callers decide when to discard it.
    """
    df = df.copy()                                           # avoid mutating the caller's DataFrame in-place
    df["DATE"] = pd.to_datetime(df["DATE"], dayfirst=True)  # parse DD/MM/YYYY strings to Timestamp objects
    df["year"] = df["DATE"].dt.year                          # extract 4-digit calendar year
    df["month"] = df["DATE"].dt.month                        # extract month-of-year (1=Jan … 12=Dec)
    df["day"] = df["DATE"].dt.day                            # extract day-of-month (1-31)
    df["dayofweek"] = df["DATE"].dt.dayofweek                # extract weekday index (Monday=0 … Sunday=6)
    return df                                                # return df with four new temporal columns appended


# ── Feature / Target Split ──────────────────────────────────────────────────

def get_feature_target(df: pd.DataFrame):
    """Separate the feature matrix X from the target vector y.

    Returns:
        X: DataFrame of one-hot-encoded features (DATE and target column dropped)
        y: Series of RENTED_BIKE_COUNT values

    The X column list must be persisted at training time and re-applied at
    inference time to prevent train/serve schema skew.
    """
    target = "RENTED_BIKE_COUNT"                             # target column name expected in every city dataset
    X = df.drop(columns=[target, "DATE"])                    # drop target and raw date string from feature matrix
    y = df[target]                                           # isolate hourly demand count as the target Series
    X = pd.get_dummies(X)                                    # one-hot encode all remaining categorical columns
    return X, y                                              # return (feature matrix DataFrame, target Series)
