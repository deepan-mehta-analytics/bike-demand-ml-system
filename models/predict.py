# ── Imports ─────────────────────────────────────────────────────────
import pandas as pd                                                   # to convert input JSON into DataFrame
import joblib                                                         # to load saved model artifacts

from models.features import create_features                           # reuse training feature transformations


# ── Load Artifacts ──────────────────────────────────────────────────

def load_artifacts():
    """Loads model and feature schema from disk.

    Returns:
        model: trained ML model
        feature_columns: list of expected feature columns
    """
    model = joblib.load("models/random_forest_model.pkl")             # load trained model artifact
    feature_columns = joblib.load("models/feature_columns.pkl")       # load saved feature column schema
    return model, feature_columns                                     # return both artifacts


# ── Prediction ──────────────────────────────────────────────────────

def predict(data, model, feature_columns):
    """Generate predictions from raw input records.

    Parameters:
        data: list of dicts (input JSON from API)
        model: trained ML model
        feature_columns: expected feature schema (post one-hot encoding)

    Returns:
        predictions (numpy array)
    """
    input_df = pd.DataFrame(data)                                     # convert list of dicts into DataFrame
    input_df = create_features(input_df)                              # apply same datetime-derived features as training
    input_df = input_df.drop(columns=["DATE"])                        # drop raw datetime column (not a feature)
    input_df = pd.get_dummies(input_df)                               # one-hot encode categorical variables
    input_df = input_df.reindex(                                      # align to training schema, fill missing dummies with 0
        columns=feature_columns, fill_value=0
    )
    predictions = model.predict(input_df)                             # generate predictions (RF needs no scaling)
    return predictions                                                # return numpy array of predictions
