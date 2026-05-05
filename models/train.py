# ── Imports ─────────────────────────────────────────────────────────
import pandas as pd                                                   # for data handling
from sklearn.model_selection import train_test_split                  # to split data into train and test
from sklearn.metrics import mean_squared_error                        # evaluation metric
from sklearn.ensemble import RandomForestRegressor                    # non-linear ensemble model
import joblib                                                         # to save trained model artifacts to disk

from models.features import load_data, create_features, get_feature_target  # reusable feature pipeline


# ── Main Training Pipeline ──────────────────────────────────────────
if __name__ == "__main__":

    # ── Load & Feature Engineering ──────────────────────────────────
    df = load_data("data/raw/seoul_bike_sharing.csv")                 # load raw dataset from disk
    df = create_features(df)                                          # add datetime-derived features
    X, y = get_feature_target(df)                                     # split into features X and target y

    # ── Persist Feature Schema ──────────────────────────────────────
    # Saved before the train/test split: column structure is invariant to the split.
    joblib.dump(X.columns.tolist(), "models/feature_columns.pkl")     # store column schema for inference alignment

    # ── Train / Test Split ──────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(              # 80/20 split with fixed seed for reproducibility
        X, y, test_size=0.2, random_state=42
    )

    # ── Model Training ──────────────────────────────────────────────
    # NOTE: Random Forest is invariant to monotonic feature scaling,
    # so we train on raw features and skip StandardScaler entirely.
    model = RandomForestRegressor(n_estimators=100, random_state=42)  # ensemble of 100 trees
    model.fit(X_train, y_train)                                       # fit model on raw training features

    # ── Persist Model ───────────────────────────────────────────────
    joblib.dump(model, "models/random_forest_model.pkl")              # save trained model artifact
    print("Model saved successfully!")                                # confirmation message

    # ── Evaluation ──────────────────────────────────────────────────
    predictions = model.predict(X_test)                               # generate predictions on test set
    mse = mean_squared_error(y_test, predictions)                     # mean squared error
    rmse = mse ** 0.5                                                 # RMSE in target units for interpretability
    print("Mean Squared Error:", mse)                                 # print MSE
    print("RMSE:", rmse)                                              # print RMSE

    # ── Feature Importance ──────────────────────────────────────────
    importances = model.feature_importances_                          # importance score per feature
    feature_names = X.columns                                         # original feature column names
    feature_importance_df = pd.DataFrame({                            # pair names with scores in a DataFrame
        "feature": feature_names,                                     # column names
        "importance": importances,                                    # importance scores
    })
    feature_importance_df = feature_importance_df.sort_values(        # sort descending by importance
        by="importance", ascending=False
    )
    print("\nTop 10 Feature Importances:")                             # header for the printout
    print(feature_importance_df.head(10))                             # display top contributors
