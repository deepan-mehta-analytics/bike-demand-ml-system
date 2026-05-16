# Phase 5 — Vertex AI + MLflow Experiment Tracking Design
**Date:** 2026-05-16  
**Status:** Approved — ready for implementation plan  
**Target version:** v4.0.0  
**Repo:** `bike-demand-ml-system` (Python FastAPI + ML backend)

---

## 1. Problem / Motivation

The current training pipeline is fully manual: run `python -m models.train --city <city>` locally, inspect printed RMSE, and manually decide whether to commit the new `.pkl` artifact. There is no experiment tracking, no model registry, and no automated retraining. Every run overwrites the previous model with no record of whether it improved.

Phase 5 adds:
- **Experiment tracking** — every training run logged to MLflow with params, RMSE, MAE, feature importances, and model artifact
- **Hyperparameter search** — 6 combinations tested per city per run; best selected automatically
- **Model lifecycle management** — MLflow Model Registry: Staging → Production promotion gated on 3% RMSE improvement
- **Automated retraining** — Cloud Scheduler triggers weekly; Vertex AI CustomJob executes training in GCP
- **Cost guard** — hard 30-minute job timeout; Cloud Monitoring email alerts on failure or approaching timeout

---

## 2. Architecture

```
Cloud Scheduler (cron: "0 2 * * 0" — every Sunday 02:00 UTC)
         │  HTTP POST + OIDC token
         ▼
Cloud Run: vertex_trigger.py
  Receives POST → submits Vertex AI CustomJob (sync=False) → returns 200 immediately
  Container exits; Vertex job runs async
         │
         ▼ Vertex AI CustomJob
┌──────────────────────────────────────────────────────────────────┐
│  retrain_job.py  (Docker container pulled from GAR)              │
│                                                                  │
│  For each city in [seoul, london, nyc, dc]:                      │
│    1. Load CSV from data/raw/{city}/                             │
│    2. Chronological 80/20 train/test split                       │
│    3. Sweep 6 hyperparameter combos (n_estimators × max_features)│
│    4. mlflow.autolog() per combo run                             │
│       → all runs land in gs://bike-demand-staging/mlflow/        │
│    5. Best combo (lowest test RMSE) registered as Staging        │
│    6. Compare best RMSE vs current Production baseline           │
│       If new_rmse < prod_rmse × 0.97 → promote to Production    │
│       Else → stay Staging, log improvement delta                 │
│                                                                  │
│  ⚠️  COST GUARD — job_timeout_seconds: 1800                       │
│     At e2-standard-2 rates (~$0.067/hr), 1800s = $0.034 cap.    │
│     DO NOT REMOVE — prevents runaway billing on hung containers. │
└──────────────────────────────────────────────────────────────────┘
         │
         ├─▶ Cloud Monitoring → email alert on FAILED or duration > 1500s
         │
         ▼
MLflow Model Registry (state in GCS: gs://bike-demand-staging/mlflow/)
  Browse locally: mlflow ui --backend-store-uri gs://bike-demand-staging/mlflow
         │
         ▼
Manual deploy (when Production model updated):
  gsutil cp gs://bike-demand-staging/mlflow/{city}/Production/*.pkl models/artifacts/{city}/
  git commit + push → existing CI rebuilds Docker image → Cloud Run redeploy
```

---

## 3. Hyperparameter Grid

6 combinations per city per run. All combinations tracked in MLflow; best RMSE wins.

| n_estimators | max_features | Rationale |
|-------------|-------------|-----------|
| 100 | sqrt | Current baseline |
| 100 | log2 | Fewer features per split → more diverse trees |
| 200 | sqrt | 2× trees, same feature sampling |
| 200 | log2 | 2× trees, log2 feature sampling |
| 300 | sqrt | Maximum trees, sqrt sampling |
| 300 | log2 | Maximum trees, log2 sampling |

`sqrt` and `log2` are both standard RF feature sampling strategies from sklearn documentation. For p features: `sqrt(p) ≈ 7` vs `log2(p) ≈ 5` for a typical 50-feature post-OHE schema.

---

## 4. RMSE Gate

### Threshold: 0.97 (3% improvement required)

**Why 3%:**
- RF training with different hyperparameters produces ~1–2% RMSE variation from feature subsampling randomness alone
- 3% is the minimum signal reliably above this noise floor
- Industry standard for tree-based demand models (consistent with Uber/Lyft engineering blog references for comparable short-horizon demand prediction)
- Lowering below 0.97 risks promoting noise; raising above 0.95 would miss genuine improvements

**Operational meaning of 3% improvement:**

| City | Current RMSE | Must beat | Real-world meaning |
|------|-------------|-----------|-------------------|
| Seoul | 173.21 | 167.91 | ~5 fewer bikes/hr error |
| London | 228.58 | 221.72 | ~7 fewer bikes/hr error |
| NYC | 345.69 | 335.32 | ~10 fewer bikes/hr error |
| DC | 97.47 | 94.55 | ~3 fewer bikes/hr error |

### First-run behaviour
If no Production model exists for a city (first retraining cycle), the best combo is promoted automatically — no threshold comparison.

### Gate logic pseudocode
```python
prod_versions = client.get_latest_versions(f"bike-demand-{city}", stages=["Production"])

if not prod_versions:
    promote_to_production(best_run_id)                 # first run: auto-promote
elif best_rmse < prod_rmse * RMSE_IMPROVEMENT_THRESHOLD:
    promote_to_production(best_run_id)                 # genuine improvement
    archive_current_production(prod_versions[0])
else:
    log_no_promotion(best_rmse, prod_rmse, delta_pct)  # log and move on
```

### Secondary metrics (logged, not gated)

| Metric | Why |
|--------|-----|
| MAE | More interpretable operationally: "off by X bikes on average" |
| MAPE | Scale-invariant comparison across cities; not gated — undefined at zero-demand hours (early morning) |
| Feature importances | Drift signal: if HOUR drops from top feature, data distribution may have shifted |

---

## 5. Train/Test Split Change

Current `models/train.py` uses `sklearn.model_selection.train_test_split` with `random_state=42` — a random (non-temporal) split. Phase 5 changes this to a **chronological split**:

```python
# Sort by date, take first 80% for training, last 20% for test
df_sorted = df.sort_values("DATE")
split_idx = int(len(df_sorted) * 0.80)
train = df_sorted.iloc[:split_idx]
test  = df_sorted.iloc[split_idx:]
```

**Why:** Temporal demand data has autocorrelation. A random split leaks future patterns into training (e.g., a winter week in training AND test). Chronological split evaluates whether the model generalises to unseen future periods — the actual production scenario.

This is a correctness fix, not just a style preference.

---

## 6. Cost Profile

| Component | Cost | Free tier |
|-----------|------|-----------|
| Vertex AI CustomJob (e2-standard-2, ~15 min/run) | ~$0.017/run | None |
| Cloud Scheduler (1 weekly job) | $0 | 3 jobs/month free |
| Cloud Run trigger (~4 invocations/month) | $0 | 2M requests/month free |
| GCS storage for MLflow artifacts | ~$0.01/month | 5 GB free |
| Cloud Monitoring alerts (2 policies) | $0 | Built-in GCP metrics free |
| **Monthly total (weekly cadence)** | **~$0.08** | |

**⚠️ COST GUARD — mandatory config:**
```yaml
vertex_ai:
  # DO NOT REMOVE — billing hard cap.
  # At e2-standard-2 (~$0.067/hr), 1800s = $0.034 maximum per run.
  # A hung container without this would accrue cost indefinitely.
  job_timeout_seconds: 1800
```

---

## 7. Monitoring + Alerting

Two Cloud Monitoring alerting policies — both **free** (built-in GCP metrics):

| Alert | Condition | Notification |
|-------|-----------|-------------|
| Job failed | CustomJob state transitions to FAILED or CANCELLED | Email: deepanmehta@live.com |
| Approaching timeout | Job running time > 1,500s (25-min warning) | Email: deepanmehta@live.com |

The 25-minute warning gives time to inspect Cloud Logging before the 30-minute hard kill fires — useful to distinguish a legitimately slow run from a genuinely hung container.

**Setup:** 1 email notification channel + 2 alerting policies in Cloud Monitoring console. Exact steps included in the implementation plan.

---

## 8. IAM Roles Required

| Role | Principal | Why |
|------|-----------|-----|
| `roles/aiplatform.user` | `vertex-sa` (new service account) | Submit CustomJob via Vertex AI SDK |
| `roles/storage.objectAdmin` on `gs://bike-demand-staging` | `vertex-sa` | MLflow reads/writes to GCS |
| `roles/artifactregistry.reader` | Vertex AI service agent | Pull training container from GAR |
| `roles/run.invoker` on `vertex_trigger` Cloud Run service | Cloud Scheduler service account | Invoke the trigger endpoint |

---

## 9. File-Level Changes

### New files

| File | Purpose |
|------|---------|
| `pipeline/retrain_job.py` | Vertex AI container entry point: sweep → autolog → gate → promote |
| `pipeline/vertex_trigger.py` | Cloud Run HTTP handler: POST → submit CustomJob → return 200 |
| `Dockerfile.training` | Training image: python:3.11-slim + requirements-vertex.txt |
| `requirements-vertex.txt` | `google-cloud-aiplatform`, `mlflow`, `google-cloud-storage` pinned |
| `docs/superpowers/specs/2026-05-16-phase5-vertex-mlflow-design.md` | This file |

### Modified files

| File | Change |
|------|--------|
| `config/gcp_config.yaml` | Add `vertex_ai:`, `mlflow:`, `retraining:` blocks |
| `models/train.py` | Chronological split; MAE logged; function signature unchanged |
| `.github/workflows/ci.yml` | Job 6: build + push `Dockerfile.training` to GAR on push to main |

### Unchanged files
`api/app.py`, `models/predict.py`, `models/features.py`, `services/predictor.py`, all existing tests.

---

## 10. Config Block (gcp_config.yaml additions)

```yaml
vertex_ai:
  # ⚠️  COST GUARD — DO NOT REMOVE.
  # At e2-standard-2 rates (~$0.067/hr), 1800s caps exposure at $0.034 per run.
  # Without this, a hung container accrues cost indefinitely with no auto-stop.
  job_timeout_seconds: 1800
  machine_type: "e2-standard-2"
  replica_count: 1

mlflow:
  # GCS-backed tracking — no server required. Browse locally with:
  # mlflow ui --backend-store-uri gs://bike-demand-staging/mlflow
  tracking_uri: "gs://bike-demand-staging/mlflow"
  experiment_prefix: "bike-demand"   # → experiments named "bike-demand-seoul" etc.

retraining:
  # Minimum RMSE reduction to promote a model from Staging to Production.
  # 3% is above the RF noise floor (~1-2%) and represents genuine improvement.
  # Do not lower below 0.97 — risks promoting noise as signal.
  rmse_improvement_threshold: 0.97

  # All 6 combinations run per city per retraining cycle.
  param_grid:
    n_estimators: [100, 200, 300]
    max_features: ["sqrt", "log2"]
```

---

## 11. Manual Deploy Workflow

When MLflow registry shows a new Production model for a city, the artifact URI must be
looked up from the registry (MLflow stores artifacts under `{experiment_id}/{run_id}/`,
not under a human-readable city/stage path):

```bash
# Step 1 — query MLflow registry for the Production artifact URI, then copy to repo
# (retrain_job.py will also print the artifact URI to stdout on promotion for convenience)
python - <<'EOF'
import mlflow
client = mlflow.tracking.MlflowClient(tracking_uri="gs://bike-demand-staging/mlflow")
v = client.get_latest_versions("bike-demand-{city}", stages=["Production"])[0]
print(v.source)   # e.g. gs://bike-demand-staging/mlflow/{exp_id}/{run_id}/artifacts/model
EOF

# Step 2 — copy the .pkl files from the printed GCS URI
gsutil cp gs://bike-demand-staging/mlflow/{exp_id}/{run_id}/artifacts/model/*.pkl \
          models/artifacts/{city}/

# Step 3 — commit and push; CI Job 5 (publish-gar) rebuilds image → GAR → Cloud Run redeploy
git add models/artifacts/{city}/
git commit -m "feat: promote {city} RF v{N} to production (RMSE {new} vs {old})"
git push
```

---

## 12. Dry-Run Mode

`retrain_job.py` supports `DRY_RUN=true` for local development and CI smoke tests:

```bash
DRY_RUN=true python pipeline/retrain_job.py
```

Behaviour: trains all 4 cities locally, logs to GCS MLflow URI, skips Vertex AI submission entirely. Zero Vertex AI cost. Used in local dev and as a CI sanity check.

---

## 13. Verification Steps

1. `DRY_RUN=true python pipeline/retrain_job.py` — all 4 cities complete; MLflow runs visible in GCS
2. `mlflow ui --backend-store-uri gs://bike-demand-staging/mlflow` — 4 experiments, 6 runs each, visible in browser
3. Submit one Vertex AI CustomJob manually via `gcloud ai custom-jobs create` — job completes, no timeout alert fires
4. Trigger Cloud Scheduler job manually via console — verify email notification received on completion
5. Manually promote one city via MLflow UI — Production tag applied in registry
6. `git push` → CI Job 6 builds `Dockerfile.training` and pushes to GAR without error
7. Run `mlflow ui` after promotion — Production model appears with correct RMSE and artifact links
