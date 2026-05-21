# ── Imports ─────────────────────────────────────────────────────────────────
import argparse                                                        # CLI argument parsing for --city / --data
import os                                                              # directory creation for per-city artifact paths
import pandas as pd                                                    # DataFrame for feature importance display
from sklearn.metrics import mean_squared_error, mean_absolute_error   # regression evaluation metrics
from sklearn.ensemble import RandomForestRegressor                     # non-linear ensemble model
import joblib                                                          # artifact serialisation to .pkl files

from models.features import load_data, create_features, get_feature_target  # shared feature pipeline


# ── CLI Argument Parser ──────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Return a configured argument parser for the training CLI."""
    parser = argparse.ArgumentParser(                                  # parser with descriptive help text
        description="Train a per-city Random Forest demand model and persist artifacts."
    )
    parser.add_argument(                                               # city name → artifact subdirectory key
        "--city",
        type=str,
        default="seoul",
        help="City identifier used as the artifact subfolder name (e.g. 'seoul', 'london', 'nyc')",
    )
    parser.add_argument(                                               # path to city's prepared CSV
        "--data",
        type=str,
        default="data/processed/seoul_bike_sharing.csv",
        help="Path to the city CSV in Seoul-schema format (see data/prepare_city_data.py for other cities)",
    )
    parser.add_argument(                                               # number of trees; affects speed vs accuracy
        "--n-estimators",
        type=int,
        default=100,
        dest="n_estimators",
        help="Number of trees in the Random Forest (default: 100)",
    )
    parser.add_argument(                                               # fixed seed for reproducible results
        "--random-state",
        type=int,
        default=42,
        dest="random_state",
        help="Random seed for reproducible RF node splits (default: 42); split is now chronological",
    )
    return parser                                                      # return configured parser to caller


# ── Training Pipeline ────────────────────────────────────────────────────────

def train(city: str, data_path: str, n_estimators: int, random_state: int) -> dict:
    """Run the full training pipeline for one city.

    Parameters:
        city:          lowercase city identifier matching the artifact directory name
        data_path:     path to a CSV in Seoul schema format
        n_estimators:  number of trees in the Random Forest
        random_state:  seed for the train/test split and RF training

    Returns:
        dict with keys: city, n_train, n_test, rmse, mse, top_features, artifact_dir
    """
    # ── Load & Engineer Features ─────────────────────────────────────────────
    df = load_data(data_path)                                          # load city CSV from disk
    df = create_features(df)                                           # derive year/month/day/dayofweek columns
    X, y = get_feature_target(df)                                      # split into feature matrix and target vector

    # ── Artifact Directory ───────────────────────────────────────────────────
    artifact_dir = os.path.join("models", "artifacts", city)           # per-city subdirectory e.g. models/artifacts/seoul
    os.makedirs(artifact_dir, exist_ok=True)                           # create directory tree; no-op if already exists

    # ── Persist Feature Schema ───────────────────────────────────────────────
    # Schema is saved before the split — column structure is split-invariant
    # and must exactly match inference-time schema to prevent train/serve skew.
    schema_path = os.path.join(artifact_dir, "feature_columns.pkl")    # full path for column schema artifact
    joblib.dump(X.columns.tolist(), schema_path)                       # serialise column name list to disk

    # ── Chronological Train / Test Split ────────────────────────────────────
    # Temporal demand data has autocorrelation — random split leaks future patterns into training.
    # Chronological split evaluates whether the model generalises to unseen future periods,
    # which is the actual production scenario. random_state is kept as a parameter for the RF constructor.
    split_idx = int(len(X) * 0.80)                                      # index marking 80% of sorted rows
    X_train = X.iloc[:split_idx]                                        # first 80% rows for training (older data)
    X_test  = X.iloc[split_idx:]                                        # last 20% rows for test (most recent data)
    y_train = y.iloc[:split_idx]                                        # target values matching train rows
    y_test  = y.iloc[split_idx:]                                        # target values matching test rows

    # ── Model Training ───────────────────────────────────────────────────────
    # Random Forest is invariant to monotonic feature scaling,
    # so StandardScaler is intentionally omitted from this pipeline.
    model = RandomForestRegressor(                                     # ensemble of decision trees
        n_estimators=n_estimators,                                     # number of trees in the forest
        random_state=random_state,                                     # reproducible node splits inside each tree
    )
    model.fit(X_train, y_train)                                        # fit forest on raw (unscaled) training features

    # ── Persist Model ────────────────────────────────────────────────────────
    model_path = os.path.join(artifact_dir, "random_forest_model.pkl") # full path for model artifact
    joblib.dump(model, model_path)                                     # serialise trained model to disk

    # ── Evaluation ───────────────────────────────────────────────────────────
    preds = model.predict(X_test)                                      # generate predictions on held-out test set
    mse  = mean_squared_error(y_test, preds)                           # mean squared error in (bikes/hr)^2
    rmse = mse ** 0.5                                                  # RMSE in original target units (bikes/hr)
    mae  = mean_absolute_error(y_test, preds)                          # mean absolute error in bikes/hr

    # ── Feature Importances ──────────────────────────────────────────────────
    importance_df = pd.DataFrame({                                     # pair feature names with RF importance scores
        "feature": X.columns,                                          # column names from post-encoding schema
        "importance": model.feature_importances_,                      # mean decrease in impurity per feature
    }).sort_values("importance", ascending=False)                      # sort descending so top contributors appear first

    return {                                                           # return all metrics and metadata to the caller
        "city": city,                                                  # city identifier string
        "n_train": len(X_train),                                       # number of training rows
        "n_test": len(X_test),                                         # number of test rows
        "rmse": rmse,                                                  # RMSE on held-out test set (bikes/hr)
        "mae": mae,                                                    # MAE on held-out test set (bikes/hr)
        "mse": mse,                                                    # MSE on held-out test set
        "top_features": importance_df.head(10),                        # top-10 feature importances as DataFrame
        "artifact_dir": artifact_dir,                                  # directory where artifacts were saved
    }


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = _build_parser().parse_args()                                # parse CLI arguments (uses defaults if none given)

    print(f"\nTraining RF model -- city: {args.city}")                 # training header
    print(f"Data path : {args.data}")                                  # show input file being used
    print(f"Trees     : {args.n_estimators}  |  Seed: {args.random_state}\n")  # show hyperparameters

    result = train(                                                    # run the full training pipeline
        city=args.city,                                                # city identifier for artifact directory
        data_path=args.data,                                           # path to the city CSV
        n_estimators=args.n_estimators,                                # RF hyperparameter
        random_state=args.random_state,                                # reproducibility seed
    )

    print(f"Artifacts saved -> {result['artifact_dir']}")               # confirm artifact save location
    print(f"Train rows: {result['n_train']}  |  Test rows: {result['n_test']}")  # data split sizes
    print(f"MSE : {result['mse']:.2f}")                                # raw MSE value
    print(f"RMSE: {result['rmse']:.2f} bikes/hr")                      # interpretable RMSE
    print(f"MAE : {result['mae']:.2f} bikes/hr")                       # mean absolute error
    print("\nTop 10 Feature Importances:\n")                          # importance table header
    print(result["top_features"].to_string(index=False))               # print without pandas row index
