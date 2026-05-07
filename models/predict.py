# ── Imports ─────────────────────────────────────────────────────────────────
import os                                                              # path construction for per-city artifact dirs
import pandas as pd                                                    # DataFrame for input normalisation
import joblib                                                          # deserialise .pkl artifacts from disk

from models.features import create_features                            # shared feature pipeline (mirrors training)


# ── Artifact Loading ─────────────────────────────────────────────────────────

def load_artifacts(city: str = "seoul"):
    """Load the trained model and feature schema for a specific city.

    Artifacts are read from models/artifacts/<city>/ — the directory
    created by models/train.py when run with --city <city>.

    Parameters:
        city: lowercase city identifier (must match directory name used at training time)

    Returns:
        (model, feature_columns): trained RF model and list of expected feature column names
    """
    artifact_dir = os.path.join("models", "artifacts", city)           # per-city subdirectory path
    model_path = os.path.join(artifact_dir, "random_forest_model.pkl") # trained model artifact path
    schema_path = os.path.join(artifact_dir, "feature_columns.pkl")    # feature column schema artifact path
    model = joblib.load(model_path)                                    # deserialise trained RF model from disk
    feature_columns = joblib.load(schema_path)                         # deserialise saved column name list
    return model, feature_columns                                      # return (model, schema) tuple to caller


# ── Prediction ───────────────────────────────────────────────────────────────

def predict(data, model, feature_columns):
    """Generate predictions from raw input records.

    Applies the same feature engineering pipeline as training, aligns columns
    to the saved schema, and runs RF inference. No scaling applied — RF is
    invariant to monotonic feature transforms.

    Parameters:
        data:            list of dicts (input JSON records from the API)
        model:           trained RF model loaded by load_artifacts()
        feature_columns: list of column names saved at training time

    Returns:
        numpy array of predicted hourly bike demand values
    """
    input_df = pd.DataFrame(data)                                      # convert list-of-dicts to DataFrame
    input_df = create_features(input_df)                               # derive temporal features (year/month/day/dayofweek)
    input_df = input_df.drop(columns=["DATE"])                         # remove raw date string (not a model feature)
    input_df = pd.get_dummies(input_df)                                # one-hot encode categorical columns
    input_df = input_df.reindex(                                       # align to training column schema
        columns=feature_columns, fill_value=0                          # fill unseen dummy columns with 0
    )
    return model.predict(input_df)                                     # numpy array of float predictions
