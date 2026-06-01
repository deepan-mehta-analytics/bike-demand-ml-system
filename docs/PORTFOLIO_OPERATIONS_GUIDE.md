# Portfolio Operations Guide
## bike-demand-ml-system — How to Use the Repo and GCP Services

> Written after the June 2026 cost audit and portfolio-mode cleanup.
> Reflects current state: active inference API, no automated retraining, no live GBFS feed.

---

## 1. What exists now (portfolio mode)

### Repos

| Repo | What it does | Where |
|---|---|---|
| `bike-demand-ml-system` | Python FastAPI inference API, RF model training, GCP data pipeline source | `D:\OneDrive\Developer\Data Engineering\bike-demand-ml-system` |
| `bike_demand_prediction` | R Shiny dashboard that calls the FastAPI | `D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction` |

### Live GCP services (always-on at zero cost)

| Service | URL | What it does | Cost when idle |
|---|---|---|---|
| `bike-demand-api` | `https://bike-demand-api-76372oragq-uc.a.run.app` | FastAPI inference endpoint — 6-city RF models baked into the image | ₹0 (scale-to-zero) |
| `billing-kill-switch` | `https://billing-kill-switch-76372oragq-ew.a.run.app` | Unlinks billing account if budget threshold is breached | ₹0 (scale-to-zero) |
| `cost-audit` | `https://cost-audit-76372oragq-uc.a.run.app` | Daily infrastructure health check → Slack alert | ₹0 (cron-triggered only) |

### Disabled services (can be re-enabled for demos)

| Service | How to re-enable | Why paused |
|---|---|---|
| `gbfs-poller-cron` (every 5 min) | `gcloud scheduler jobs resume gbfs-poller-cron --location=us-central1 --project=bike-demand-ml-system` | Adds ~₹60–100/month in Cloud Run + BQ streaming charges; not needed for static demo |
| GBFS live station feed | Re-enable cron above | Paused with cron |

### Deleted services (no longer exist)

| Service | What it did | Why deleted |
|---|---|---|
| `bike-demand-trigger` Cloud Run | Submitted weekly Vertex AI training jobs | Weekly retrain adds ~₹14/month in Vertex AI; static models are sufficient for portfolio |
| `bike-demand-weekly-retrain` scheduler | Triggered retrain every Sunday 02:00 UTC | Deleted with trigger service |
| GCS `mlflow/` prefix | Stored MLflow run artifacts (~22 GB at peak) | Deleted; was growing ~10 GB/week from Sunday retrains |

---

## 2. The inference API — demo endpoint

**URL:** `https://bike-demand-api-76372oragq-uc.a.run.app`

### Cold start behaviour
The service scales to zero when idle. First request after ~15 min of inactivity triggers a cold start (~3–5 seconds). Subsequent requests within the same session are fast (<200ms).

**For a live demo:** make one warm-up call 30 seconds before presenting.

```bash
# Health check
curl https://bike-demand-api-76372oragq-uc.a.run.app/health

# Prediction — Paris evening rush
curl -X POST https://bike-demand-api-76372oragq-uc.a.run.app/predict \
  -H "Content-Type: application/json" \
  -d '{"city":"paris","HOUR":18,"TEMP":22,"HUMIDITY":60,"WIND_SPEED":3,
       "VISIBILITY":2000,"SOLAR_RADIATION":0.5,"RAINFALL":0,"SNOWFALL":0,
       "SEASONS":3,"HOLIDAY":0,"FUNCTIONING_DAY":1}'

# Available cities
curl https://bike-demand-api-76372oragq-uc.a.run.app/cities
```

### Deployed model RMSEs

| City | RMSE (bikes/hr) | Training data |
|---|---|---|
| Paris | 20.51 | 2023–2024 (2022 dropped — data quality gate) |
| Seoul | ~311 | UCI 2017–2018 |
| NYC | ~471 | BigQuery 2014–2018 |
| DC | ~149 | BigQuery 2014–2018 |
| London | ~514 | TfL 2022–2024 |
| Chicago | ~RMSE | BigQuery 2014–2018 |

> **Note:** Seoul shows ~1,552 RMSE in the weekly retrain path (pipeline/retrain_job.py).
> This is a data path issue in that script — the production model served by the API
> (trained via models/train.py) is correct. Investigate before re-enabling retraining.

---

## 3. CI/CD pipeline — what runs on every push to main

```
push to main
│
├── Job 1: Ruff lint
├── Job 2: pytest (all unit tests + trains Seoul model locally)
├── Job 3: Docker build (inference image — trains 4 city models)
├── Job 4: Push to GHCR (ghcr.io/deepan-mehta-analytics/...)
├── Job 5: Push to GAR + redeploy Cloud Run bike-demand-api
└── Job 6: RMSE accuracy gates (6 cities, ~5 min)
```

> Job 6 ("Build training container") was removed in June 2026 — the training
> image has no consumer now that the weekly retrain scheduler is deleted.

**Every push to main automatically:**
- Retrains 4 city models (inside the Docker build step)
- Deploys the fresh image to Cloud Run (zero-downtime revision swap)
- Runs RMSE gates — CI fails if any city regresses past its threshold

---

## 4. Cost monitoring — cost-audit service

Runs daily at **09:00 UTC** via Cloud Scheduler. Sends a Slack alert to `#all-supernova-surfer-solutions` if any threshold is breached.

### Current thresholds (portfolio mode, as of June 2026)

| Check | Threshold | Rationale |
|---|---|---|
| Registry versions per package | > 7 | Cleanup policy keeps ≤5; 7 allows a CI-day buffer |
| Registry total size | > 3 GB | 2 active packages × 5 images × ~250 MB = ~2.5 GB |
| GCS bucket size | > 5 GB | MLflow deleted; only CloudBuild temp files remain |
| Compute VMs | > 0 | Expected = 0; any VM = rogue spend |
| Vertex AI endpoints | > 0 | No free tier; any endpoint = paid |
| BigQuery storage | > 8 GB | Free tier = 10 GB |
| MTD spend | > ₹300 | Portfolio-mode expected ~₹80–120/month |
| Cloud Run allowlist | `bike-demand-api`, `billing-kill-switch`, `cost-audit` | Alert on any unrecognised service |

### If you get a Slack alert

```bash
# Check audit logs
gcloud logging read "resource.labels.service_name=cost-audit" \
  --project=bike-demand-ml-system --limit=20 --freshness=1d

# Run the audit manually (dry run — no Slack post)
gcloud run jobs execute cost-audit --region=us-central1 \
  --project=bike-demand-ml-system
# (or just hit the URL)
curl https://cost-audit-76372oragq-uc.a.run.app/
```

---

## 5. Billing — key facts

- **Billing account:** HDFC bank account, denominated in **INR (₹)**
- **BQ billing export:** `billing_export.gcp_billing_export_v1_015DB7_CE9C3D_2F5093`
- **All `cost` column values in the export are INR** — never treat them as USD
- **May 2026 actual spend:** ₹798 ($9.60 USD) — inflated by dev-week VMs, Dataflow, Network Intelligence Center (all now gone)
- **Expected June 2026 onward:** ₹80–120/month (~$1–1.50 USD)
- **Spending-based discount:** GCP applies ~40–46% automatically; invoice total is lower than BQ sum

### Query actual MTD spend

```sql
-- Run in BigQuery console or bq CLI
SELECT ROUND(SUM(cost), 2) AS mtd_cost_inr
FROM `bike-demand-ml-system.billing_export.gcp_billing_export_v1_015DB7_CE9C3D_2F5093`
WHERE DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
  AND project.id = 'bike-demand-ml-system'
```

> Note: 24–48h export lag — June 1 MTD shows ₹0 until June 2 data lands.

---

## 6. Billing kill switch — is it working?

**Wiring status:** ✅ Correctly deployed.

| Component | Status |
|---|---|
| Cloud Run service `billing-kill-switch` | Deployed in **europe-west1** (not us-central1) |
| Pub/Sub topic `budget-alert-topic` | Exists |
| Pub/Sub subscription | Push subscription → kill switch URL ✅ |
| IAM: Compute SA has `run.invoker` | ✅ confirmed |
| Code: unlinksBilling when `costAmount >= budgetAmount` | ✅ verified in `billing-kill-switch/main.py` |

**One unverified risk:** The Cloud Run service account must have `roles/billing.projectManager` on the **billing account** (not just the project) to actually call `updateBillingInfo`. This requires testing with a real budget trigger or checking the billing account IAM in the console under `Billing → Account management → Permissions`.

**What happens if triggered:** The billing account is unlinked from the project. **All GCP services stop immediately.** To restore: re-link the billing account in the console. This is a nuclear option — suitable as a hard cap, not a soft warning.

---

## 7. GAR image cleanup policy

The cleanup policy (`keep-recent-5` + `delete-older-than-4d`) runs automatically on both active packages (`bike-demand-ml-system`, `cost-audit`). You do not need to manually delete images.

**Expected steady state after June 3:**
- `bike-demand-ml-system`: 1–5 images (May 28–29 images pruned by June 2–3)
- `cost-audit`: 1–5 images

**To check current registry size:**
```bash
gcloud artifacts repositories describe bike-demand-repo \
  --location=us-central1 --project=bike-demand-ml-system \
  --format="value(sizeBytes)"
```

> Size counter has a 1–24h delay after deletions. The May 2026 package deletions
> (gbfs-poller + bike-demand-training, 21 images) will show in the counter by June 2.

---

## 8. Running the project locally

### FastAPI inference API

```bash
cd "D:\OneDrive\Developer\Data Engineering\bike-demand-ml-system"

# Install dependencies
pip install -r requirements.txt

# Train models (first time only — ~5 min for all 4 cities)
python -m models.train --city paris
python -m models.train --city seoul
# etc.

# Start API
uvicorn services.api:app --host 0.0.0.0 --port 8000

# Test
curl http://localhost:8000/health
```

### R Shiny dashboard

```r
# In RStudio — open the Shiny project
setwd("D:/OneDrive/Developer/DataAnalytics/R_projects/bike_demand_prediction")

# Ensure FastAPI URL is set (local or Cloud Run)
Sys.setenv(FASTAPI_URL = "https://bike-demand-api-76372oragq-uc.a.run.app")
Sys.setenv(USE_FASTAPI = "true")

shiny::runApp("shiny_app")
```

### Run tests

```bash
# All tests
pytest tests/ -v

# RMSE accuracy gates only (~5 min)
pytest -m slow tests/test_model_accuracy.py -v

# Cost-audit unit tests only (fast)
pytest tests/test_cost_audit.py -v
```

---

## 9. Enabling GBFS live data for a demo

The GBFS pipeline is paused (scheduler disabled, Cloud Run service deleted). To re-enable:

```bash
# Step 1: Redeploy the GBFS poller Cloud Run service from source
cd "D:\OneDrive\Developer\Data Engineering\bike-demand-ml-system"
gcloud run deploy gbfs-poller \
  --source pipeline/ \
  --region us-central1 \
  --project bike-demand-ml-system \
  --no-allow-unauthenticated

# Step 2: Resume the Cloud Scheduler job
gcloud scheduler jobs resume gbfs-poller-cron \
  --location=us-central1 \
  --project=bike-demand-ml-system

# Step 3: Verify it's polling (wait 5 min then check BQ)
bq query --nouse_legacy_sql \
  "SELECT * FROM bike_demand.station_snapshots ORDER BY timestamp DESC LIMIT 5"

# To pause again after the demo:
gcloud scheduler jobs pause gbfs-poller-cron \
  --location=us-central1 \
  --project=bike-demand-ml-system
```

---

## 10. Re-running model training (manual)

The weekly retrain scheduler is deleted. To retrain manually:

```bash
# Option A — local (no GCP cost)
python -m models.train --city paris

# Option B — run the full MLflow sweep locally (writes to local mlruns/)
DRY_RUN=true python -m pipeline.retrain_job

# Option C — push to main (CI retrains and redeploys automatically)
git push origin main
```

> **Do not re-enable the weekly retrain scheduler** without first fixing the
> Seoul RMSE regression in `pipeline/retrain_job.py` (RMSE 311 → 1,552 between
> the May 17 and May 24 runs — likely a data path or feature mismatch).

---

## 11. Key file map

```
bike-demand-ml-system/
├── services/api.py              ← FastAPI app (inference endpoint)
├── models/train.py              ← Simple RF training (used in CI + local)
├── models/predict.py            ← Prediction logic (called by API)
├── pipeline/retrain_job.py      ← MLflow hyperparameter sweep (manual use only)
├── pipeline/gbfs_poller_service.py ← GBFS live station feed (paused)
├── cost-audit/
│   ├── main.py                  ← Cloud Run handler
│   ├── checks.py                ← 7 GCP resource checks
│   ├── thresholds.py            ← Threshold config (edit here to tune alerts)
│   └── notify.py                ← Slack webhook delivery
├── billing-kill-switch/main.py  ← Budget kill switch (europe-west1)
├── .github/workflows/ci.yml    ← CI pipeline (lint → test → build → deploy)
└── docs/
    ├── PORTFOLIO_OPERATIONS_GUIDE.md  ← this file
    └── superpowers/plans/             ← v4.5.0 drift monitoring plan (pending)
```

---

## 12. What's next (v4.5.0)

The drift monitoring spec and plan are committed on main:
- `docs/superpowers/specs/2026-05-23-drift-monitoring-design.md`
- `docs/superpowers/plans/2026-05-23-drift-monitoring.md`

Resume with: **`"resume bike-demand-ml-system v4.5.0 S2"`**

Before starting S2, investigate the Seoul weekly-retrain RMSE regression (311 → 1,552) — the drift monitoring feature will catch this kind of shift, making it an ideal first real use case.
