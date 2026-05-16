# -*- coding: utf-8 -*-
# =============================================================================
# pipeline/retrain_job.py
# -----------------------------------------------------------------------------
# Vertex AI CustomJob entry point: hyperparameter sweep → MLflow tracking →
# RMSE gate → MLflow Model Registry promotion.
#
# Runs inside the bike-demand-training Docker container on Vertex AI.
# Also runnable locally with DRY_RUN=true for zero-cost development.
#
# Usage (local dry-run — requires GOOGLE_APPLICATION_CREDENTIALS):
#   DRY_RUN=true python pipeline/retrain_job.py
#
# Usage (Vertex AI — triggered by vertex_trigger.py):
#   Submitted as a CustomJob; entry point CMD in Dockerfile.training.
# =============================================================================

# ── Imports ───────────────────────────────────────────────────
import itertools                                  # Cartesian product for param grid sweep
import math                                       # sqrt() for RMSE from MSE
import os                                         # environment variable access (DRY_RUN)
from pathlib import Path                          # cross-platform path construction

import mlflow                                     # experiment tracking and model registry
import mlflow.sklearn                             # sklearn model logging integration
import yaml                                       # gcp_config.yaml parsing
from mlflow.tracking import MlflowClient          # model registry client for stage transitions
from sklearn.ensemble import RandomForestRegressor  # demand prediction model
from sklearn.metrics import mean_absolute_error   # secondary evaluation metric (interpretable)
from sklearn.metrics import mean_squared_error    # primary evaluation metric (MSE → RMSE)

from models.features import create_features       # shared feature engineering pipeline
from models.features import get_feature_target    # feature/target split with OHE encoding
from models.features import load_data             # CSV → DataFrame loader

# ── Dry-run guard ─────────────────────────────────────────────
# DRY_RUN=true: runs entire sweep locally, logs to GCS MLflow URI, zero Vertex AI cost.
# Use this for local development and verifying MLflow connectivity before submitting real jobs.
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"  # read env var; default to production mode


# ── Config loader ─────────────────────────────────────────────
# _load_config() is a function (not module-level) to avoid WindowsPath pickling issues.
# If Path(__file__) is evaluated at module level on Windows, it creates a WindowsPath object.
# save_main_session=True (Dataflow/Vertex AI) pickles the module globals — Linux workers
# cannot unpickle WindowsPath and crash with NotImplementedError. Computing inside a function
# re-evaluates the path in the worker's own OS context at call time. Lesson from Phase 4.
def _load_config() -> dict:                       # returns parsed YAML as a Python dict
    """Load gcp_config.yaml from the repo root config/ directory."""
    config_path = Path(__file__).parent.parent / "config" / "gcp_config.yaml"  # resolve from this file's location
    with open(config_path, encoding="utf-8") as f:  # utf-8: config has ⚠️/— chars; cp1252 can't decode them
        return yaml.safe_load(f)                  # parse YAML to Python dict and return


# ── Registry helpers ──────────────────────────────────────────
def _get_production_rmse(client: MlflowClient, model_name: str):
    """Return the test_rmse of the current Production model, or None if no Production version exists."""
    versions = client.get_latest_versions(model_name, stages=["Production"])  # query registry for Production
    if not versions:                              # no Production version yet — this is the first run
        return None                              # signal to auto-promote without threshold comparison
    run = client.get_run(versions[0].run_id)      # fetch the MLflow run that produced the Production model
    return run.data.metrics.get("test_rmse")      # return the logged RMSE value (or None if missing)


def _promote_to_production(client: MlflowClient, model_name: str, version: str) -> None:
    """Archive the current Production model (if any) and promote the given version to Production."""
    old = client.get_latest_versions(model_name, stages=["Production"])  # get current Production versions
    for v in old:                                 # archive each existing Production version
        client.transition_model_version_stage(model_name, v.version, "Archived")  # move to Archived stage
    client.transition_model_version_stage(model_name, version, "Production")  # promote new version


# ── Main retrain loop ─────────────────────────────────────────
def retrain_all_cities() -> None:
    """Sweep hyperparameters for all 4 cities, log to MLflow, gate on RMSE, update the model registry."""
    cfg = _load_config()                          # load full GCP + retraining config from YAML

    # DRY_RUN redirects MLflow to a local mlruns/ directory so the entire sweep can be
    # run and inspected offline without GCS credentials or Vertex AI cost.
    # Production mode (DRY_RUN=false) logs to GCS so Vertex AI jobs persist across runs.
    if DRY_RUN:                                   # offline mode: no GCS credentials needed
        mlflow.set_tracking_uri("mlruns/")        # local filesystem store under cwd/mlruns/
        print("[DRY_RUN] MLflow redirected to local mlruns/ — no GCS credentials required")
    else:                                         # production mode: GCS-backed store
        mlflow.set_tracking_uri(cfg["mlflow"]["tracking_uri"])  # gs://bike-demand-staging/mlflow
    client = MlflowClient()                       # initialise MLflow model registry client

    cities     = cfg["retraining"]["cities"]                # list of {name, data_path} dicts
    n_est_list = cfg["retraining"]["param_grid"]["n_estimators"]  # [100, 200, 300]
    feat_list  = cfg["retraining"]["param_grid"]["max_features"]  # ["sqrt", "log2"]
    threshold  = cfg["retraining"]["rmse_improvement_threshold"]  # 0.97 (3% improvement required)
    prefix     = cfg["mlflow"]["experiment_prefix"]               # "bike-demand"

    for city_cfg in cities:                       # iterate over all 4 configured cities
        city_name  = city_cfg["name"]             # e.g. "seoul", "london", "nyc", "dc"
        data_path  = city_cfg["data_path"]        # e.g. "data/raw/seoul/seoul_bike_sharing.csv"
        model_name = f"{prefix}-{city_name}"      # MLflow experiment + registry name e.g. "bike-demand-seoul"

        mlflow.set_experiment(model_name)         # create experiment if it does not already exist

        best_rmse    = float("inf")               # lowest RMSE seen across all combos this sweep
        best_run_id  = None                       # MLflow run_id of the best-performing combo
        best_version = None                       # MLflow registry version string of the best model

        df = load_data(data_path)                 # load city CSV from disk (once, shared across combos)
        df = create_features(df)                  # add year/month/day/dayofweek derived columns
        X, y = get_feature_target(df)             # feature matrix and target series (OHE applied)

        # ── Chronological 80/20 split ─────────────────────────
        # Temporal demand data has autocorrelation — random split leaks future patterns into training.
        # Chronological split evaluates whether the model generalises to unseen future periods.
        split_idx = int(len(X) * 0.80)            # index marking the 80% boundary
        X_train = X.iloc[:split_idx]              # first 80% of rows → training (older data)
        X_test  = X.iloc[split_idx:]              # last 20% of rows → test (most recent data)
        y_train = y.iloc[:split_idx]              # target values aligned with training rows
        y_test  = y.iloc[split_idx:]              # target values aligned with test rows

        print(f"\n[{city_name}] {len(X_train)} train rows / {len(X_test)} test rows")  # log split sizes

        # ── Hyperparameter sweep ──────────────────────────────
        for n_est, max_feat in itertools.product(n_est_list, feat_list):  # 6 combos: 3 × 2
            with mlflow.start_run():              # one MLflow run per hyperparameter combination
                mlflow.log_param("city", city_name)          # tag city for cross-experiment filtering
                mlflow.log_param("n_estimators", n_est)      # log tree count hyperparameter
                mlflow.log_param("max_features", max_feat)   # log feature sampling strategy

                model = RandomForestRegressor(
                    n_estimators=n_est,           # number of trees in the forest
                    max_features=max_feat,        # feature sampling strategy per split node
                    random_state=42,              # fixed seed — reproducible tree splits across runs
                    n_jobs=-1,                    # use all available vCPUs on e2-standard-2 (2 cores)
                )
                model.fit(X_train, y_train)       # train on the older 80% of data

                y_pred = model.predict(X_test)    # generate predictions on most recent 20%
                mse  = mean_squared_error(y_test, y_pred)   # mean squared error (bikes/hr)^2
                rmse = math.sqrt(mse)                        # root mean squared error in bikes/hr
                mae  = mean_absolute_error(y_test, y_pred)  # mean absolute error in bikes/hr

                mlflow.log_metric("test_rmse", rmse)         # primary gate metric — used for Staging→Production
                mlflow.log_metric("test_mae",  mae)          # secondary metric — more interpretable operationally
                mlflow.log_metric("test_mse",  mse)          # raw MSE for completeness
                mlflow.sklearn.log_model(model, "model")     # log full model artifact to GCS

                # Log feature importances — drift signal: if HOUR drops from top, check data pipeline
                for feat, imp in zip(X_train.columns, model.feature_importances_):
                    mlflow.log_metric(f"importance_{feat}", round(float(imp), 4))  # one metric per feature

                run_id = mlflow.active_run().info.run_id     # capture run_id before context exits
                print(f"  n_estimators={n_est} max_features={max_feat}: RMSE={rmse:.2f} MAE={mae:.2f}")

                if rmse < best_rmse:              # this combo beats previous best for this city
                    best_rmse   = rmse            # update best RMSE seen this sweep
                    best_run_id = run_id          # record winning run_id for registration

        # ── Register best combo ───────────────────────────────
        model_uri    = f"runs:/{best_run_id}/model"              # MLflow URI pointing to the best run's artifact
        result       = mlflow.register_model(model_uri, model_name)  # register as a new version in registry
        best_version = result.version                            # version string assigned by MLflow e.g. "3"
        client.transition_model_version_stage(model_name, best_version, "Staging")  # mark as Staging

        # ── RMSE gate ─────────────────────────────────────────
        prod_rmse = _get_production_rmse(client, model_name)     # fetch RMSE of current Production model

        if prod_rmse is None:                    # first retraining cycle — no Production exists yet
            _promote_to_production(client, model_name, best_version)  # auto-promote without threshold
            print(f"  → First run: promoted v{best_version} to Production (RMSE {best_rmse:.2f})")

        elif best_rmse < prod_rmse * threshold:  # genuine ≥3% improvement — above RF noise floor
            _promote_to_production(client, model_name, best_version)  # archive old, promote new
            pct = (prod_rmse - best_rmse) / prod_rmse * 100   # improvement percentage for logging
            print(f"  → Promoted v{best_version} to Production (+{pct:.1f}% better: {best_rmse:.2f} vs {prod_rmse:.2f})")

        else:                                    # improvement below 3% threshold — stay in Staging
            gap = (best_rmse - prod_rmse) / prod_rmse * 100   # gap to threshold (as %)
            print(f"  → No promotion: RMSE {best_rmse:.2f} vs Production {prod_rmse:.2f} (need 3%, got {gap:+.1f}%)")


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    retrain_all_cities()                          # Dockerfile.training CMD runs this directly
