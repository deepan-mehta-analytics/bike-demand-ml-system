# v4.4.0 Drift Monitoring + MLflow 6/6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly weather-feature drift monitor (PSI per feature, same-season baseline, Open-Meteo refetch, markdown report committed back via GitHub Actions cron) for all 6 served cities, bundled with the deferred MLflow Paris + Chicago promotion to land the registry at 6/6.

**Architecture:** Standalone `monitoring/` Python package with declarative per-city config, PSI math, Open-Meteo client, and report writers. GitHub Actions cron triggers weekly; bot commits the report back to `main` with `[skip ci]`. Zero paid GCP surface — fully free-tier (Rule 12). MLflow promotion is a 2-line `Dockerfile.training` edit + Vertex AI re-run.

**Tech Stack:** Python 3.11 (numpy, pandas, requests — all already in requirements.txt), pyarrow (for parquet — already present via pandas), pytest, GitHub Actions, MLflow client, gcloud SDK (Vertex AI trigger).

**Spec:** [`docs/superpowers/specs/2026-05-23-drift-monitoring-design.md`](../specs/2026-05-23-drift-monitoring-design.md)

**Predecessor:** v4.3.0 (Paris timezone fix + Option B 2022 drop)

**Session shape:** S1 (spec + plan, this) → S2 (MLflow pre-flight) → S3 (drift module + baselines + TDD) → S4 (GHA cron + manual smoke) → S5 (close-out)

---

## File Structure

**Files to create:**

| Path | Responsibility | Owner sprint |
|---|---|---|
| `monitoring/__init__.py` | Mark `monitoring` as a Python package (empty) | S3 |
| `monitoring/city_config.py` | Declarative per-city config (LAT/LON/timezone/feature list) + PSI threshold constants | S3 |
| `monitoring/drift_check.py` | Orchestrator: Open-Meteo fetch, PSI math, season mapping, baseline regenerator, report writers, CLI | S3 |
| `monitoring/baselines/seoul.parquet` | Precomputed season-sliced feature distributions for Seoul | S3 |
| `monitoring/baselines/london.parquet` | … London | S3 |
| `monitoring/baselines/nyc.parquet` | … NYC | S3 |
| `monitoring/baselines/dc.parquet` | … DC | S3 |
| `monitoring/baselines/paris.parquet` | … Paris | S3 |
| `monitoring/baselines/chicago.parquet` | … Chicago | S3 |
| `monitoring/reports/.gitkeep` | Ensure `reports/` exists in fresh clones before first cron run | S3 |
| `tests/test_drift_check.py` | 8 unit tests (PSI math, season, baseline schema, report writers, error handling) | S3 (TDD; committed with module) |
| `.github/workflows/drift.yml` | Weekly cron (`schedule: cron '0 6 * * 1'`) + `workflow_dispatch:` + commit-back step | S4 |

**Files to modify:**

| Path | Change | Owner sprint |
|---|---|---|
| `Dockerfile.training:38-41` | Add `COPY` lines for paris + chicago CSVs | S2 |
| `README.md` | Update MLflow Known Limitation 4/6→6/6 (S2 small edit); add `📡 Drift Monitoring` section between Tests and Results, refresh Scaling Considerations, tick Roadmap drift item (S5) | S2 + S5 |
| `PROJECT-STATUS.md` | Note 6/6 MLflow in Known Limitations (S2); add Phase 15 block + Ecosystem row v4.3.0 → v4.4.0 (S5) | S2 + S5 |
| `bike_demand_prediction/PROJECT-STATUS.md` | Cross-repo hash sync (Python row v4.3.0 → v4.4.0) | S5 |

**Note on TDD scope:** The spec §6 lists "tests + GHA cron + smoke" in S4, but writing implementation code without tests is a workflow-quality regression. This plan applies TDD inside S3 — each implementation task starts with a failing test. `tests/test_drift_check.py` therefore lands in the same `feat(monitoring):` commit as the module, and S4 focuses cleanly on GHA workflow + manual smoke (no test authoring). Total test count delta vs spec §9 (`32 + 8 = 40`) is unchanged.

---

## Pre-flight (read before starting ANY sprint cold)

For an agent or operator resuming this plan mid-stream:

- [ ] **Verify repo state.** Working directory is `D:\OneDrive\Developer\Data Engineering\bike-demand-ml-system` on `main`. Run `git status` — should be clean unless a `## In Progress` block in `workflow_status.md` documents otherwise.
- [ ] **Read** `C:\Users\deepa\.claude\projects\D--OneDrive-Developer-Data-Engineering-bike-demand-ml-system\memory\workflow_status.md` — Status line indicates which sprint is current; Next action gives the exact entry task.
- [ ] **Read** [`docs/superpowers/specs/2026-05-23-drift-monitoring-design.md`](../specs/2026-05-23-drift-monitoring-design.md) — load constraints (no paid GCP, no Cloud Monitoring writes, no alerting, no refactor of `data/fetch_*_weather.py`).
- [ ] **Add a `## In Progress` block** to `workflow_status.md` listing the tasks you plan to execute this sprint (Rule 9). Remove + tick + update at sprint end.

---

# Sprint S2 — MLflow Pre-flight

**Goal:** Land Paris + Chicago in the MLflow Production registry. Closes Known Limitation "4 of 6 cities in MLflow Production registry" from v4.3.0.

**Boundary:** opens with `/clear`. Ends with 2 commits (`fix(training):` + `docs:`) pushed; `workflow_status.md` updated to S3 re-entry.

---

### Task S2.1: Add Paris + Chicago CSV copies to Dockerfile.training

**Files:**
- Modify: `Dockerfile.training` (lines 37-41 current `COPY` block for 4 cities)

- [ ] **Step 1: Read current Dockerfile.training:37-41 to confirm baseline**

Run: `git log -1 --oneline Dockerfile.training`
Expected: shows last commit touching this file. Cross-reference matches what's in the working tree before editing.

- [ ] **Step 2: Apply the 2-line addition**

Edit `Dockerfile.training` to extend the city-CSV copy block. The current state copies 4 cities (seoul, london, nyc, dc). Add paris + chicago in the same block, maintaining alphabetical-ish ordering (current order is geographic — keep it consistent):

```dockerfile
# Copy processed city CSVs — baked into image; Vertex AI job needs no GCS data fetch.
COPY data/processed/seoul_bike_sharing.csv ./data/processed/
COPY data/processed/london_bike_sharing.csv ./data/processed/
COPY data/processed/nyc_bike_sharing.csv ./data/processed/
COPY data/processed/dc_bike_sharing.csv ./data/processed/
COPY data/processed/paris_bike_sharing.csv ./data/processed/
COPY data/processed/chicago_bike_sharing.csv ./data/processed/
```

Note per CLAUDE.md Dockerfile exception: comments on instruction lines are FORBIDDEN. The comment above stays on its own line; no inline comments on the COPY lines.

- [ ] **Step 3: Verify the change is exactly 2 new lines**

Run: `git diff --stat Dockerfile.training`
Expected: `1 file changed, 2 insertions(+)`.

- [ ] **Step 4: Verify the source CSVs exist locally before pushing**

Run: `ls -la data/processed/paris_bike_sharing.csv data/processed/chicago_bike_sharing.csv`
Expected: both files exist, non-zero size (typically 1-3 MB each).

If either is missing, STOP — the Vertex AI build will fail. Re-run the city's fetch script before continuing.

- [ ] **Step 5: Stage the change**

Run: `git add Dockerfile.training`

(Commit happens in Task S2.3 alongside the docs update for clean atomic commits.)

---

### Task S2.2: Trigger Vertex AI re-run and verify 6/6 in MLflow Production

**Files:** None (cloud-side action)

- [ ] **Step 1: Confirm gcloud auth + project**

Run:
```bash
gcloud config list 2>&1
gcloud auth list 2>&1
```
Expected: active account is `deepanmehta@live.com`-tied service account; project is the bike-demand project.

If not authenticated, suggest the user runs: `! gcloud auth login` (interactive — needs to be typed by user with the `!` prefix per session guidance).

- [ ] **Step 2: Build + push the training image with the new Dockerfile**

Existing CI Job 6 (`build-training-container` in `.github/workflows/ci.yml`) pushes to GAR on every push to main. Push the Dockerfile change in Task S2.3 first; let the CI job build + push the image. Then trigger Vertex AI in Step 3 below.

Alternative (manual): build + push locally if you want to skip waiting for CI:
```bash
docker build -f Dockerfile.training -t \
  europe-west1-docker.pkg.dev/<PROJECT>/bike-demand/training:s2-mlflow-promotion .
docker push europe-west1-docker.pkg.dev/<PROJECT>/bike-demand/training:s2-mlflow-promotion
```
Project name from `gcloud config get-value project`. Recommended: wait for CI Job 6 to finish on the Task S2.3 push — saves local build time.

- [ ] **Step 3: Trigger the Vertex AI custom job**

The repo has a trigger script. Inspect first:

Run: `ls pipeline/ && grep -l "vertex" pipeline/*.py`
Expected: `vertex_trigger.py` or `retrain_job.py` present.

Two trigger paths:
1. **HTTP trigger** (if the Cloud Run `vertex_trigger` service is deployed):
   ```bash
   curl -X POST https://<vertex-trigger-url>/trigger \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)"
   ```
2. **gcloud direct** (always works):
   ```bash
   gcloud ai custom-jobs create \
     --region=europe-west1 \
     --display-name="v4.4.0-s2-mlflow-promotion" \
     --worker-pool-spec=replica-count=1,machine-type=n1-standard-4,\
container-image-uri=europe-west1-docker.pkg.dev/<PROJECT>/bike-demand/training:latest
   ```

Either way, the job runs all 6 city training pipelines and logs to MLflow.

- [ ] **Step 4: Wait for the job to finish**

Run: `gcloud ai custom-jobs list --region=europe-west1 --limit=1 --format=json`
Expected: most recent job has `state: JOB_STATE_SUCCEEDED`. Typical runtime ~10-15 min.

If `JOB_STATE_FAILED`, fetch logs:
```bash
gcloud ai custom-jobs describe <JOB_ID> --region=europe-west1
```
Common failure: missing CSV in image (Step 4 of S2.1 should have caught this).

- [ ] **Step 5: Verify all 6 cities in MLflow Production registry**

The repo uses MLflow tracking on GCS at `gs://bike-demand-staging/mlflow/mlflow.db`. Query the registry:

```bash
# Set MLFLOW_TRACKING_URI to the GCS-backed SQLite if running locally:
export MLFLOW_TRACKING_URI=sqlite:////tmp/mlflow.db
gsutil cp gs://bike-demand-staging/mlflow/mlflow.db /tmp/mlflow.db

# List registered models in Production stage
python -c "
import mlflow
client = mlflow.tracking.MlflowClient()
for city in ['seoul', 'london', 'nyc', 'dc', 'paris', 'chicago']:
    name = f'rf-{city}'
    try:
        versions = client.get_latest_versions(name, stages=['Production'])
        if versions:
            print(f'{city}: v{versions[0].version} (Production)')
        else:
            print(f'{city}: NO PRODUCTION VERSION')
    except mlflow.exceptions.RestException as e:
        print(f'{city}: NOT REGISTERED ({e.message})')
"
```

Expected output: 6 lines, each showing a Production version. If Paris or Chicago shows `NO PRODUCTION VERSION` or `NOT REGISTERED`, the Vertex job ran the training but did not promote — investigate `models/train.py` for the city's MLflow registration block (it should mirror Seoul's pattern).

- [ ] **Step 6: Capture the registry state for the docs update**

Save the output of Step 5 into a temp note — Task S2.3 needs the version numbers for the README + PROJECT-STATUS edits.

---

### Task S2.3: Commit fix + small docs update; update workflow_status

**Files:**
- Already staged: `Dockerfile.training` (from S2.1)
- Modify: `README.md` — find the Known Limitations section line referencing "MLflow registry honest about 4 of 6 cities" (added in commit `91b8af1`); update to "all 6 of 6 cities"
- Modify: `PROJECT-STATUS.md` — find the matching Known Limitations line; update similarly
- Modify: `workflow_status.md`

- [ ] **Step 1: Locate the README MLflow Known Limitation line**

Run: `grep -n "4 of 6 cities" README.md PROJECT-STATUS.md`
Expected: 1-2 matches per file. These are the lines to edit.

- [ ] **Step 2: Apply README + PROJECT-STATUS edits**

Replace `4 of 6 cities` → `6 of 6 cities` in each match. Keep surrounding prose intact. The line in README looks like:

> ~~MLflow registry promotion is honest about its scope: 4 of 6 cities (Seoul / London / NYC / DC) at v4.0.0 cut-off — Paris and Chicago train via the same Vertex AI job but their CSVs are not baked into the training image~~

Becomes:

> ✅ **MLflow registry promotion landed at 6 of 6 cities (Seoul / London / NYC / DC / Paris / Chicago) at v4.4.0** — `Dockerfile.training:38-43` now copies all 6 city CSVs; Vertex AI custom-job auto-promotes each to MLflow Production via `models/train.py`.

(Use strikethrough on the old text to preserve historical context; same pattern as v4.3.0's Paris hyperparameter tuning bullet.)

- [ ] **Step 3: Commit the Dockerfile fix as one atomic commit**

Run:
```bash
git status --short
```
Expected: 3 files staged or modified (`Dockerfile.training`, `README.md`, `PROJECT-STATUS.md`).

Stage all three and commit as a single `fix(training):` since the docs edit is the verification-evidence companion to the Dockerfile change:
```bash
git add Dockerfile.training README.md PROJECT-STATUS.md
git commit -m "$(cat <<'EOF'
fix(training): bake paris + chicago CSVs into training image; land MLflow 6/6

Dockerfile.training:38-43 now copies all 6 city CSVs. Vertex AI custom-job
auto-promoted Paris + Chicago to MLflow Production registry on first re-run
post-edit. Closes v4.3.0 tracked Known Limitation "4 of 6 cities in MLflow
Production registry".

README + PROJECT-STATUS Known Limitations updated with strikethrough +
post-v4.4.0 affirmative line.

Verified via mlflow.tracking.MlflowClient query against
gs://bike-demand-staging/mlflow/mlflow.db (all 6 cities show Production
version with timestamp after Vertex AI job <JOB_ID>).
EOF
)"
```

Replace `<JOB_ID>` with the actual Vertex AI custom-job ID from Task S2.2 Step 4.

- [ ] **Step 4: Push to origin/main**

Run: `git push origin main`
Expected: push succeeds; CI starts. CI Jobs 4 (Docker build), 6 (build-training-container), 7 (publish-gar) all rebuild the training image with the new Dockerfile.

- [ ] **Step 5: Update workflow_status.md for S3 re-entry**

Edit `C:\Users\deepa\.claude\projects\D--OneDrive-Developer-Data-Engineering-bike-demand-ml-system\memory\workflow_status.md`:

1. Remove the `## In Progress` block from S2 entry
2. Update Status line: `## Status: v4.4.0 S2 complete (MLflow 6/6 landed); next sprint S3 (drift module + baselines) (as of <today's date>)`
3. Add `## Last Session` block summarizing S2 work (commits, MLflow verification output)
4. Update `## Next action` to:
   > Resume v4.4.0 S3: implement drift module + city_config + 6 baselines per `docs/superpowers/plans/2026-05-23-drift-monitoring.md` Sprint S3. TDD discipline: write each test before implementation; commit module + tests + 6 baselines in one `feat(monitoring):` commit at sprint end.
5. Update `## Re-entry command`:
   > "resume bike-demand-ml-system v4.4.0 S3"

---

# Sprint S3 — Drift Module + Baselines (TDD)

**Goal:** Ship the entire `monitoring/` package end-to-end: config, PSI math, Open-Meteo fetch, season mapping, baseline regenerator, report writers, CLI orchestrator. All 6 baseline `.parquet` files committed. 8 unit tests written via TDD, all passing locally.

**Boundary:** opens with `/clear`. Ends with 1 `feat(monitoring):` commit covering module + tests + 6 baselines; `workflow_status.md` updated to S4 re-entry.

**TDD discipline:** every implementation task in S3 starts with a failing test before any production code is written. The test file accumulates across tasks; commit only at sprint end.

---

### Task S3.1: Bootstrap monitoring/ package + city_config.py

**Files:**
- Create: `monitoring/__init__.py` (empty)
- Create: `monitoring/city_config.py`
- Create: `monitoring/baselines/.gitkeep`
- Create: `monitoring/reports/.gitkeep`

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p monitoring/baselines monitoring/reports
touch monitoring/__init__.py monitoring/baselines/.gitkeep monitoring/reports/.gitkeep
```

(Use PowerShell-equivalent if running on Windows native: `New-Item -ItemType Directory -Path monitoring/baselines, monitoring/reports -Force; New-Item -ItemType File -Path monitoring/__init__.py, monitoring/baselines/.gitkeep, monitoring/reports/.gitkeep`.)

- [ ] **Step 2: Write `monitoring/city_config.py`**

Per spec §3.2 + §4.2 + §4.6. Coordinates verified against existing `data/fetch_*_weather.py` scripts (each script's Open-Meteo URL has the city's lat/lon; reuse those exact values to keep training-time and monitoring-time data points geographically identical).

```python
# ── Module Purpose ───────────────────────────────────────────────────────────
# Declarative configuration for the drift monitor. No logic lives here —
# only data tables and constants. Cold-restart sessions must source thresholds
# and per-city geo/feature lists from this file rather than redefining them.

from typing import TypedDict, List, Dict                              # type hints for the per-city config schema


# ── PSI Classification Thresholds (Siddiqi 2006 / SAS / banking standard) ───
PSI_THRESHOLD_MONITOR = 0.10                                          # below this: STABLE
PSI_THRESHOLD_DRIFT   = 0.25                                          # at or above this: DRIFT; between: MONITOR

# ── Weather Features Monitored ──────────────────────────────────────────────
# Numeric weather columns common to all 6 city processed CSVs (Seoul schema).
# Temporal columns (HOUR, dayofweek, month, year, day) are deterministic and
# excluded by design. Categorical flags (SEASONS, HOLIDAY, FUNCTIONING_DAY)
# are calendar/operational facts and excluded.
WEATHER_FEATURES: List[str] = [
    "TEMPERATURE",                                                    # degrees C
    "HUMIDITY",                                                       # percent
    "WIND_SPEED",                                                     # m/s
    "DEW_POINT_TEMPERATURE",                                          # degrees C
    "SOLAR_RADIATION",                                                # MJ/m^2
    "RAINFALL",                                                       # mm
    "SNOWFALL",                                                       # cm
    "VISIBILITY",                                                     # 10m units
]


# ── Per-City Configuration Schema ───────────────────────────────────────────
class CityConfig(TypedDict):                                          # one entry per served city
    lat: float                                                        # latitude for Open-Meteo fetch
    lon: float                                                        # longitude for Open-Meteo fetch
    timezone: str                                                     # IANA timezone passed to Open-Meteo
    baseline_path: str                                                # path to per-city baseline parquet


# ── Per-City Lookup Table ───────────────────────────────────────────────────
# Lat/lon values match the existing data/fetch_*_weather.py scripts to ensure
# fresh weather is sampled at the same geographic point as the training data.
CITY_CONFIG: Dict[str, CityConfig] = {
    "seoul":   {"lat": 37.5665, "lon": 126.9780, "timezone": "Asia/Seoul",        "baseline_path": "monitoring/baselines/seoul.parquet"},
    "london":  {"lat": 51.5074, "lon":  -0.1278, "timezone": "Europe/London",     "baseline_path": "monitoring/baselines/london.parquet"},
    "nyc":     {"lat": 40.7128, "lon": -74.0060, "timezone": "America/New_York",  "baseline_path": "monitoring/baselines/nyc.parquet"},
    "dc":      {"lat": 38.9072, "lon": -77.0369, "timezone": "America/New_York",  "baseline_path": "monitoring/baselines/dc.parquet"},
    "paris":   {"lat": 48.8566, "lon":   2.3522, "timezone": "Europe/Paris",      "baseline_path": "monitoring/baselines/paris.parquet"},
    "chicago": {"lat": 41.8781, "lon": -87.6298, "timezone": "America/Chicago",   "baseline_path": "monitoring/baselines/chicago.parquet"},
}


# ── Month → Season Mapping (Northern Hemisphere; all 6 cities NH) ───────────
MONTH_TO_SEASON: Dict[int, str] = {
    1:  "Winter",  2:  "Winter",  12: "Winter",
    3:  "Spring",  4:  "Spring",   5: "Spring",
    6:  "Summer",  7:  "Summer",   8: "Summer",
    9:  "Autumn", 10: "Autumn",   11: "Autumn",
}
```

- [ ] **Step 3: Verify lat/lon values match existing fetch scripts**

Run: `grep -nE "latitude|longitude" data/fetch_seoul_weather.py data/fetch_london_weather.py data/fetch_paris_weather.py data/fetch_chicago_weather.py data/fetch_dc_weather.py data/fetch_nyc_weather.py`

For each city, confirm the lat/lon in `city_config.py` matches the value used in the Open-Meteo URL of that city's fetch script. If any mismatch — STOP and reconcile. The drift monitor must sample fresh weather at the same point as training-time fetch.

- [ ] **Step 4: Verify import works**

Run: `python -c "from monitoring.city_config import CITY_CONFIG, WEATHER_FEATURES, MONTH_TO_SEASON, PSI_THRESHOLD_DRIFT; print(len(CITY_CONFIG), len(WEATHER_FEATURES), PSI_THRESHOLD_DRIFT)"`
Expected: `6 8 0.25`

- [ ] **Step 5: Stage (no commit yet — sprint-end commit per spec §6)**

```bash
git add monitoring/__init__.py monitoring/city_config.py monitoring/baselines/.gitkeep monitoring/reports/.gitkeep
```

---

### Task S3.2: TDD — PSI function

**Files:**
- Create: `tests/test_drift_check.py` (first contents)
- Create: `monitoring/drift_check.py` (first contents)

- [ ] **Step 1: Write the failing test for PSI identity (PSI(x, x) ≈ 0)**

Create `tests/test_drift_check.py`:

```python
# ── Imports ───────────────────────────────────────────────────────────────
import numpy as np                                              # synthetic test distributions
import pytest                                                   # parametrize + tolerance helpers


# ── PSI Math Tests ────────────────────────────────────────────────────────

def test_psi_identical_distributions_is_zero():
    """PSI of a sample against itself must be approximately zero."""
    from monitoring.drift_check import psi                      # import inside test so failure mode is clear

    rng = np.random.default_rng(seed=42)                        # deterministic random state for the test
    baseline = rng.normal(loc=0.0, scale=1.0, size=10_000)      # baseline sample
    fresh    = baseline.copy()                                  # identical fresh sample

    score = psi(fresh=fresh, baseline=baseline, n_bins=10)      # PSI with 10 quantile bins

    assert score < 0.01, f"PSI(x, x) should be ~0, got {score}"  # very tight tolerance — should be near-zero
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_psi_identical_distributions_is_zero -v`
Expected: FAIL with `ImportError: cannot import name 'psi' from 'monitoring.drift_check'` or similar — the function doesn't exist yet.

- [ ] **Step 3: Implement the minimal PSI function**

Create `monitoring/drift_check.py`:

```python
# ── Imports ───────────────────────────────────────────────────────────────
import numpy as np                                              # quantile bin computation + log arithmetic


# ── PSI (Population Stability Index) ─────────────────────────────────────
# Industry-standard distribution-shift metric (Siddiqi 2006).
# PSI = sum over bins of (a_i - e_i) * ln(a_i / e_i)
#   e_i = fraction of BASELINE observations in bin i
#   a_i = fraction of FRESH observations in bin i
# Bins are quantile-based deciles computed from the BASELINE; fresh
# observations are dropped into those fixed bins.

_PSI_FRACTION_FLOOR = 1e-4                                      # floor on both a_i and e_i to avoid log(0) / div-by-zero


def psi(fresh: np.ndarray, baseline: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index between two 1D numeric samples.

    Args:
        fresh:    new sample (e.g. last 7 days of weather)
        baseline: reference sample (training-time slice for same season)
        n_bins:   number of quantile bins from the baseline (default 10 = deciles)

    Returns:
        PSI as a non-negative float. Conventional thresholds:
          PSI < 0.10  : STABLE
          0.10–0.25   : MONITOR
          PSI >= 0.25 : DRIFT
    """
    # ── Compute quantile breaks from baseline ────────────────────────────
    quantile_edges = np.quantile(                                # decile breakpoints from baseline distribution
        baseline,
        q=np.linspace(0, 1, n_bins + 1),                         # n_bins+1 edges for n_bins bins
    )
    # Force outer edges to ±inf so fresh values outside baseline range land in extreme bins
    quantile_edges[0]  = -np.inf                                 # extend lowest bin to -inf
    quantile_edges[-1] = np.inf                                  # extend highest bin to +inf

    # ── Histogram each sample into the same bins ─────────────────────────
    baseline_counts, _ = np.histogram(baseline, bins=quantile_edges)  # baseline bin counts
    fresh_counts,    _ = np.histogram(fresh,    bins=quantile_edges)  # fresh bin counts

    # ── Convert counts to fractions; apply floor to avoid log(0) ─────────
    e = np.maximum(baseline_counts / baseline_counts.sum(), _PSI_FRACTION_FLOOR)  # expected fractions
    a = np.maximum(fresh_counts    / fresh_counts.sum(),    _PSI_FRACTION_FLOOR)  # actual fractions

    # ── Compute PSI ──────────────────────────────────────────────────────
    return float(np.sum((a - e) * np.log(a / e)))                # PSI scalar
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_psi_identical_distributions_is_zero -v`
Expected: PASS in < 1 second.

- [ ] **Step 5: Write the failing test for PSI shift detection (above DRIFT threshold)**

Append to `tests/test_drift_check.py`:

```python
def test_psi_shifted_distributions_above_drift_threshold():
    """A +3 sigma shift in the fresh sample must produce PSI >= 0.25 (DRIFT)."""
    from monitoring.drift_check import psi                      # already implemented in Step 3

    rng = np.random.default_rng(seed=42)                        # deterministic
    baseline = rng.normal(loc=0.0, scale=1.0, size=10_000)      # baseline N(0, 1)
    fresh    = rng.normal(loc=3.0, scale=1.0, size=10_000)      # fresh N(3, 1) — shifted by 3 sigma

    score = psi(fresh=fresh, baseline=baseline, n_bins=10)      # PSI with 10 quantile bins

    assert score >= 0.25, f"Expected PSI >= 0.25 for +3 sigma shift, got {score}"
```

- [ ] **Step 6: Run test to verify it passes immediately (PSI already implemented)**

Run: `pytest tests/test_drift_check.py::test_psi_shifted_distributions_above_drift_threshold -v`
Expected: PASS. (Confirms the +3σ shift does trigger DRIFT classification.)

- [ ] **Step 7: Write the failing test for empty-bin handling**

Append:

```python
def test_psi_handles_empty_bins_via_floor():
    """Bin with 0 fresh observations must not cause log(0); fraction is floored to 1e-4."""
    from monitoring.drift_check import psi

    baseline = np.concatenate([                                  # bimodal baseline at 0 and 10
        np.zeros(1000),
        np.full(1000, 10.0),
    ])
    fresh = np.zeros(1000)                                       # fresh sample only covers the lower mode

    score = psi(fresh=fresh, baseline=baseline, n_bins=10)       # several upper bins have 0 fresh observations

    assert np.isfinite(score), f"PSI must be finite; got {score}"  # must not be inf or nan
    assert score > 0.5, f"Severe shift should produce PSI > 0.5, got {score}"
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_psi_handles_empty_bins_via_floor -v`
Expected: PASS.

- [ ] **Step 9: Stage (no commit)**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.3: TDD — Season assignment helper

**Files:**
- Modify: `tests/test_drift_check.py` (append)
- Modify: `monitoring/drift_check.py` (append)

- [ ] **Step 1: Write the failing parametrized season test**

Append to `tests/test_drift_check.py`:

```python
# ── Season Mapping ────────────────────────────────────────────────────────

@pytest.mark.parametrize("month, expected_season", [
    (1, "Winter"),
    (2, "Winter"),
    (3, "Spring"),
    (4, "Spring"),
    (5, "Spring"),
    (6, "Summer"),
    (7, "Summer"),
    (8, "Summer"),
    (9, "Autumn"),
    (10, "Autumn"),
    (11, "Autumn"),
    (12, "Winter"),
])
def test_season_assignment_month_mapping(month, expected_season):
    """Month integer must map to NH meteorological season."""
    from monitoring.drift_check import month_to_season

    assert month_to_season(month) == expected_season
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_season_assignment_month_mapping -v`
Expected: FAIL — `month_to_season` not yet defined.

- [ ] **Step 3: Implement `month_to_season`**

Append to `monitoring/drift_check.py`:

```python
# ── Season Mapping (NH; thin wrapper over MONTH_TO_SEASON lookup) ────────
from monitoring.city_config import MONTH_TO_SEASON              # canonical month→season mapping


def month_to_season(month: int) -> str:
    """Return the NH meteorological season name for a calendar month (1-12).

    Args:
        month: integer 1-12

    Returns:
        One of "Spring" / "Summer" / "Autumn" / "Winter"
    """
    return MONTH_TO_SEASON[month]                                # KeyError surfaces invalid input loudly
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_season_assignment_month_mapping -v`
Expected: PASS (12 parametrized cases).

- [ ] **Step 5: Stage**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.4: TDD — Open-Meteo fetch (with mocking)

**Files:**
- Modify: `tests/test_drift_check.py` (append)
- Modify: `monitoring/drift_check.py` (append)

- [ ] **Step 1: Write the failing test for fetch-success path**

Append to `tests/test_drift_check.py`:

```python
# ── Open-Meteo Fetch ──────────────────────────────────────────────────────

def test_fetch_open_meteo_returns_dataframe_with_weather_features(monkeypatch):
    """Open-Meteo fetch must return a DataFrame with one row per hour and all 8 weather features as columns."""
    import pandas as pd
    from monitoring.drift_check import fetch_open_meteo
    from monitoring.city_config import WEATHER_FEATURES

    # ── Fake Open-Meteo JSON response (covers 24 hours × 1 day) ───────────
    fake_response = {
        "hourly": {
            "time": [f"2026-05-20T{h:02d}:00" for h in range(24)],
            "temperature_2m":      [15.0 + h * 0.1 for h in range(24)],
            "relative_humidity_2m":[60   + h       for h in range(24)],
            "wind_speed_10m":      [3.0  + h * 0.05 for h in range(24)],
            "dew_point_2m":        [10.0 + h * 0.05 for h in range(24)],
            "shortwave_radiation": [0.5 if 6 <= h <= 18 else 0.0 for h in range(24)],
            "rain":                [0.0] * 24,
            "snowfall":            [0.0] * 24,
            "visibility":          [10000] * 24,                  # metres in raw API; helper converts to 10m units
        }
    }

    class _FakeResp:
        status_code = 200
        def json(self): return fake_response
        def raise_for_status(self): pass

    def _fake_get(url, params, timeout):                          # match requests.get signature
        return _FakeResp()

    monkeypatch.setattr("requests.get", _fake_get)

    df = fetch_open_meteo(lat=37.5665, lon=126.9780, timezone="Asia/Seoul", days=1)

    assert isinstance(df, pd.DataFrame), "fetch_open_meteo must return a DataFrame"
    assert len(df) == 24, f"Expected 24 hourly rows, got {len(df)}"
    for feature in WEATHER_FEATURES:
        assert feature in df.columns, f"Missing required column {feature}; got {list(df.columns)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_fetch_open_meteo_returns_dataframe_with_weather_features -v`
Expected: FAIL — `fetch_open_meteo` not defined.

- [ ] **Step 3: Implement `fetch_open_meteo`**

Append to `monitoring/drift_check.py`:

```python
# ── Open-Meteo Client ─────────────────────────────────────────────────────
# Single function; no class wrapper. Returns a DataFrame with Seoul-schema
# weather columns (UPPERCASE) so PSI math + baselines can align on names.
#
# Open-Meteo raw → Seoul-schema column rename map. Open-Meteo "visibility"
# is in metres; Seoul schema is 10m units, so divide by 10.

import pandas as pd                                              # DataFrame construction
import requests                                                  # HTTP client (already in requirements.txt)


_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"       # public endpoint; no API key required

_OPEN_METEO_VARS_TO_SEOUL_SCHEMA = {                             # raw param name → Seoul schema column name
    "temperature_2m":       "TEMPERATURE",
    "relative_humidity_2m": "HUMIDITY",
    "wind_speed_10m":       "WIND_SPEED",
    "dew_point_2m":         "DEW_POINT_TEMPERATURE",
    "shortwave_radiation":  "SOLAR_RADIATION",
    "rain":                 "RAINFALL",
    "snowfall":             "SNOWFALL",
    "visibility":           "VISIBILITY",
}


def fetch_open_meteo(lat: float, lon: float, timezone: str, days: int = 7) -> pd.DataFrame:
    """Fetch the most recent N days of hourly weather from Open-Meteo.

    Args:
        lat:      latitude in decimal degrees
        lon:      longitude in decimal degrees
        timezone: IANA timezone string (e.g. "Asia/Seoul")
        days:    look-back window in days; default 7

    Returns:
        DataFrame with one row per hour and Seoul-schema weather columns:
        TEMPERATURE, HUMIDITY, WIND_SPEED, DEW_POINT_TEMPERATURE,
        SOLAR_RADIATION, RAINFALL, SNOWFALL, VISIBILITY.

    Raises:
        requests.HTTPError on non-200 response (caller handles for error reporting)
        KeyError on missing expected column in API response
    """
    params = {                                                   # Open-Meteo query params
        "latitude":  lat,
        "longitude": lon,
        "timezone":  timezone,
        "past_days": days,                                       # ask for last N days
        "forecast_days": 0,                                      # no forecast — we want historical only
        "hourly": ",".join(_OPEN_METEO_VARS_TO_SEOUL_SCHEMA.keys()),  # request all 8 weather variables
    }
    response = requests.get(_OPEN_METEO_URL, params=params, timeout=30)  # 30 s should be ample
    response.raise_for_status()                                  # raises HTTPError on 4xx/5xx
    payload = response.json()

    hourly = payload["hourly"]                                   # KeyError if API shape changes — caught by test #8
    df = pd.DataFrame({                                          # build DataFrame with Seoul-schema column names
        seoul_col: hourly[api_col]
        for api_col, seoul_col in _OPEN_METEO_VARS_TO_SEOUL_SCHEMA.items()
    })

    df["VISIBILITY"] = df["VISIBILITY"] / 10.0                   # raw metres → Seoul 10m units (training-time convention)

    return df                                                    # caller decides what to do with the rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_fetch_open_meteo_returns_dataframe_with_weather_features -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for fetch-failure resilience**

Append to `tests/test_drift_check.py`:

```python
def test_fetch_open_meteo_500_raises_http_error(monkeypatch):
    """A 500 response must raise HTTPError so the orchestrator can catch + log."""
    import requests
    from monitoring.drift_check import fetch_open_meteo

    class _FakeBadResp:
        status_code = 500
        def raise_for_status(self):
            raise requests.HTTPError("500 Server Error")

    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeBadResp())

    with pytest.raises(requests.HTTPError):
        fetch_open_meteo(lat=0.0, lon=0.0, timezone="UTC", days=1)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_fetch_open_meteo_500_raises_http_error -v`
Expected: PASS — the existing `raise_for_status()` line in `fetch_open_meteo` already handles this.

- [ ] **Step 7: Stage**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.5: TDD — Baseline regenerator

**Files:**
- Modify: `tests/test_drift_check.py` (append)
- Modify: `monitoring/drift_check.py` (append)

- [ ] **Step 1: Write the failing test for baseline schema**

Append to `tests/test_drift_check.py`:

```python
# ── Baselines ─────────────────────────────────────────────────────────────

def test_regenerate_baseline_writes_long_form_parquet(tmp_path):
    """Baseline regenerator must produce a parquet file with [season, feature, value] schema."""
    import pandas as pd
    from monitoring.drift_check import regenerate_baseline_for_city

    # ── Synthetic processed-CSV input (Seoul schema, 4 rows × 4 seasons) ──
    synthetic_csv = tmp_path / "fake_city_bike_sharing.csv"
    pd.DataFrame({
        "DATE": ["01/01/2024", "01/04/2024", "01/07/2024", "01/10/2024"],
        "HOUR": [12, 12, 12, 12],
        "TEMPERATURE":  [-2.0, 15.0, 28.0, 10.0],                # winter, spring, summer, autumn
        "HUMIDITY":     [80, 60, 50, 70],
        "WIND_SPEED":   [3.0, 4.0, 2.5, 3.5],
        "DEW_POINT_TEMPERATURE": [-5.0, 8.0, 20.0, 5.0],
        "SOLAR_RADIATION": [0.1, 1.2, 2.5, 0.8],
        "RAINFALL":     [0.0, 1.0, 0.0, 2.0],
        "SNOWFALL":     [1.0, 0.0, 0.0, 0.0],
        "VISIBILITY":   [1000, 2000, 2000, 1500],
        "RENTED_BIKE_COUNT": [100, 500, 800, 300],               # target column; unused by drift but present in real CSVs
    }).to_csv(synthetic_csv, index=False)

    output_path = tmp_path / "out.parquet"
    regenerate_baseline_for_city(processed_csv=str(synthetic_csv), output_parquet=str(output_path))

    assert output_path.exists(), "Baseline parquet not written"
    baseline = pd.read_parquet(output_path)
    assert set(baseline.columns) == {"season", "feature", "value"}, \
        f"Baseline schema must be [season, feature, value]; got {list(baseline.columns)}"
    assert set(baseline["season"].unique()) == {"Spring", "Summer", "Autumn", "Winter"}, \
        "All 4 seasons must appear in baseline"
    # 8 weather features × 4 seasons × 1 row each = 32 rows
    assert len(baseline) == 32, f"Expected 32 rows (8 features × 4 seasons × 1 each), got {len(baseline)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_regenerate_baseline_writes_long_form_parquet -v`
Expected: FAIL — `regenerate_baseline_for_city` not defined.

- [ ] **Step 3: Implement `regenerate_baseline_for_city`**

Append to `monitoring/drift_check.py`:

```python
# ── Baseline Regenerator ──────────────────────────────────────────────────
# Reads a processed city CSV (Seoul schema), tags each row with the NH
# season derived from its DATE, melts the 8 weather feature columns to
# long form, and writes [season, feature, value] parquet.

from monitoring.city_config import WEATHER_FEATURES              # canonical feature list


def regenerate_baseline_for_city(processed_csv: str, output_parquet: str) -> None:
    """Compute long-form season-sliced baseline distributions and write parquet.

    Args:
        processed_csv:  path to data/processed/<city>_bike_sharing.csv
        output_parquet: path to monitoring/baselines/<city>.parquet
    """
    df = pd.read_csv(processed_csv)                              # full training CSV for this city

    # ── Derive season from DATE ─────────────────────────────────────────
    # DATE is DD/MM/YYYY in Seoul-schema CSVs; pandas dayfirst parses it.
    months = pd.to_datetime(df["DATE"], dayfirst=True).dt.month  # 1-12 integer per row
    df["__season"] = months.map(MONTH_TO_SEASON)                 # NH season per row; underscore prefix avoids collision

    # ── Melt 8 weather features to long form ────────────────────────────
    long = df.melt(
        id_vars=["__season"],                                    # keep season as identifier
        value_vars=WEATHER_FEATURES,                             # 8 weather columns become rows
        var_name="feature",                                      # output column name for feature label
        value_name="value",                                      # output column name for numeric reading
    )
    long = long.rename(columns={"__season": "season"})           # final schema column name
    long = long[["season", "feature", "value"]]                  # enforce column order

    long.to_parquet(output_parquet, index=False)                 # write columnar; preserves dtypes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_regenerate_baseline_writes_long_form_parquet -v`
Expected: PASS.

- [ ] **Step 5: Write the parametrized "all 6 baselines loadable" test (will be skipped until baselines exist; real check in Task S3.7)**

Append to `tests/test_drift_check.py`:

```python
@pytest.mark.parametrize("city", ["seoul", "london", "nyc", "dc", "paris", "chicago"])
def test_all_six_baselines_exist_and_loadable(city):
    """Each city's baseline parquet must be present in the repo and have the expected schema."""
    import pandas as pd
    from pathlib import Path
    from monitoring.city_config import CITY_CONFIG

    path = Path(CITY_CONFIG[city]["baseline_path"])
    assert path.exists(), f"Missing baseline parquet for {city}: {path}"

    baseline = pd.read_parquet(path)
    assert set(baseline.columns) == {"season", "feature", "value"}, \
        f"{city} baseline schema mismatch: {list(baseline.columns)}"
    assert baseline["season"].nunique() == 4, f"{city} baseline missing seasons"
    assert baseline["feature"].nunique() == 8, f"{city} baseline missing weather features"
```

- [ ] **Step 6: Run test to verify it currently fails (baselines not yet generated)**

Run: `pytest tests/test_drift_check.py::test_all_six_baselines_exist_and_loadable -v`
Expected: FAIL for all 6 parametrized cases — files don't exist yet. This is expected; Task S3.7 generates them.

- [ ] **Step 7: Stage**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.6: TDD — Report writers (history append + latest render)

**Files:**
- Modify: `tests/test_drift_check.py` (append)
- Modify: `monitoring/drift_check.py` (append)

- [ ] **Step 1: Write the failing test for history append behavior**

Append to `tests/test_drift_check.py`:

```python
# ── Report Writers ────────────────────────────────────────────────────────

def test_history_writer_appends_not_overwrites(tmp_path):
    """Calling append_history twice must double the row count."""
    import pandas as pd
    from monitoring.drift_check import append_history

    history_path = tmp_path / "history.csv"
    sample_rows = [
        {"run_date": "2026-05-25", "city": "seoul", "feature": "TEMPERATURE",
         "season": "Spring", "psi": 0.045, "status": "STABLE", "n_fresh": 168, "n_baseline": 4248},
    ]

    append_history(rows=sample_rows, history_path=str(history_path))
    append_history(rows=sample_rows, history_path=str(history_path))

    df = pd.read_csv(history_path)
    assert len(df) == 2, f"Expected 2 rows after 2 appends, got {len(df)}"
    assert list(df.columns) == ["run_date", "city", "feature", "season",
                                 "psi", "status", "n_fresh", "n_baseline"], \
        f"Unexpected schema: {list(df.columns)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_history_writer_appends_not_overwrites -v`
Expected: FAIL — `append_history` not defined.

- [ ] **Step 3: Implement `append_history`**

Append to `monitoring/drift_check.py`:

```python
# ── Report Writers ────────────────────────────────────────────────────────
# history.csv is append-only audit log; latest.md is overwritten each run.

import os                                                        # exists check for header-write decision
from typing import List, Dict, Any                               # types for the rows-list

_HISTORY_COLUMNS = ["run_date", "city", "feature", "season",
                    "psi", "status", "n_fresh", "n_baseline"]


def append_history(rows: List[Dict[str, Any]], history_path: str) -> None:
    """Append rows to history.csv. Writes header only if the file is new.

    Args:
        rows:         list of dicts; each dict must contain all _HISTORY_COLUMNS keys
        history_path: path to monitoring/reports/history.csv
    """
    new_df = pd.DataFrame(rows, columns=_HISTORY_COLUMNS)        # enforce column order

    file_exists = os.path.exists(history_path) and os.path.getsize(history_path) > 0
    new_df.to_csv(
        history_path,
        mode="a" if file_exists else "w",                        # append if exists, else create with header
        header=not file_exists,                                  # write header only on creation
        index=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_history_writer_appends_not_overwrites -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for latest.md overwrite**

Append to `tests/test_drift_check.py`:

```python
def test_render_latest_md_writes_summary_and_per_city_tables(tmp_path):
    """render_latest_md must produce a markdown file with summary line + per-city sections."""
    import pandas as pd
    from monitoring.drift_check import render_latest_md

    history_path = tmp_path / "history.csv"
    latest_path  = tmp_path / "latest.md"

    # ── Build a minimal history.csv with 2 cities × 2 features ────────────
    pd.DataFrame([
        {"run_date": "2026-05-25", "city": "seoul",  "feature": "TEMPERATURE", "season": "Spring", "psi": 0.045, "status": "STABLE",  "n_fresh": 168, "n_baseline": 4248},
        {"run_date": "2026-05-25", "city": "seoul",  "feature": "HUMIDITY",    "season": "Spring", "psi": 0.118, "status": "MONITOR", "n_fresh": 168, "n_baseline": 4248},
        {"run_date": "2026-05-25", "city": "london", "feature": "TEMPERATURE", "season": "Spring", "psi": 0.250, "status": "DRIFT",   "n_fresh": 168, "n_baseline": 3624},
        {"run_date": "2026-05-25", "city": "london", "feature": "HUMIDITY",    "season": "Spring", "psi": 0.080, "status": "STABLE",  "n_fresh": 168, "n_baseline": 3624},
    ]).to_csv(history_path, index=False)

    render_latest_md(history_path=str(history_path), latest_path=str(latest_path))

    content = latest_path.read_text(encoding="utf-8")
    assert "# 📡 Drift Monitor" in content, "Missing title"
    assert "2026-05-25" in content, "Missing run date in summary"
    assert "Seoul"  in content or "seoul"  in content, "Missing Seoul section"
    assert "London" in content or "london" in content, "Missing London section"
    assert "STABLE" in content and "MONITOR" in content and "DRIFT" in content, "Status labels missing"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_drift_check.py::test_render_latest_md_writes_summary_and_per_city_tables -v`
Expected: FAIL — `render_latest_md` not defined.

- [ ] **Step 7: Implement `render_latest_md`**

Append to `monitoring/drift_check.py`:

```python
# ── Markdown Renderer ─────────────────────────────────────────────────────
# Builds a human-friendly markdown report from the most recent run rows in
# history.csv. Overwrites latest.md each call.

from datetime import datetime, timezone                          # UTC timestamp in report header

_STATUS_EMOJI = {                                                # visual badges in the per-city tables
    "STABLE":  "🟢",
    "MONITOR": "🟡",
    "DRIFT":   "🔴",
    "FETCH_FAILED":      "⚠️",
    "FETCH_SCHEMA_ERROR":"⚠️",
    "BASELINE_EMPTY":    "⚠️",
    "LOW_BASELINE":      "🟠",
}


def render_latest_md(history_path: str, latest_path: str) -> None:
    """Render the most-recent-run slice of history.csv into a markdown report.

    Args:
        history_path: path to monitoring/reports/history.csv
        latest_path:  path to monitoring/reports/latest.md (overwritten)
    """
    history = pd.read_csv(history_path)                          # full audit log
    if history.empty:                                            # defensive — should not happen in cron
        latest_path_obj = open(latest_path, "w", encoding="utf-8")
        latest_path_obj.write("# 📡 Drift Monitor\n\n_No runs recorded._\n")
        latest_path_obj.close()
        return

    most_recent_date = history["run_date"].max()                 # latest run timestamp
    latest_run = history[history["run_date"] == most_recent_date].copy()  # rows from the most recent run only

    # ── Previous run (for week-over-week trend arrows) ───────────────────
    previous_dates = sorted(history["run_date"].unique())
    previous_run = (
        history[history["run_date"] == previous_dates[-2]]
        if len(previous_dates) >= 2 else pd.DataFrame()
    )

    # ── Build summary counts ────────────────────────────────────────────
    counts = latest_run["status"].value_counts().to_dict()
    n_stable  = counts.get("STABLE",  0)
    n_monitor = counts.get("MONITOR", 0)
    n_drift   = counts.get("DRIFT",   0)
    n_total   = len(latest_run)

    # ── Compose markdown ────────────────────────────────────────────────
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 📡 Drift Monitor — Latest Report",
        "",
        f"**Run:** {most_recent_date} (rendered {now_iso})",
        "**Schedule:** weekly (Mondays 06:00 UTC) · [workflow](../../.github/workflows/drift.yml)",
        f"**Summary:** {n_stable} stable · {n_monitor} monitor · {n_drift} drift  (across {n_total} city × feature checks)",
        "",
        "---",
        "",
    ]

    for city, city_df in latest_run.groupby("city"):
        season    = city_df["season"].iloc[0]
        n_fresh   = city_df["n_fresh"].iloc[0]
        n_baseline= city_df["n_baseline"].iloc[0]
        lines.append(f"## {city.capitalize()} ({season}, n_fresh={n_fresh}, n_baseline={n_baseline})")
        lines.append("")
        lines.append("| Feature | PSI | Status | Trend (vs last week) |")
        lines.append("|---|---:|:---:|:---:|")
        for _, row in city_df.iterrows():
            emoji = _STATUS_EMOJI.get(row["status"], "❔")
            # Compute trend arrow vs previous run for this (city, feature) pair
            arrow = "–"
            if not previous_run.empty:
                match = previous_run[
                    (previous_run["city"] == row["city"]) &
                    (previous_run["feature"] == row["feature"])
                ]
                if not match.empty and pd.notna(row["psi"]) and pd.notna(match["psi"].iloc[0]):
                    delta = row["psi"] - match["psi"].iloc[0]
                    arrow = "▲" if delta > 0.005 else ("▼" if delta < -0.005 else "–")
            psi_str = f"{row['psi']:.3f}" if pd.notna(row["psi"]) else "n/a"
            lines.append(f"| {row['feature']} | {psi_str} | {emoji} {row['status']} | {arrow} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Methodology",
        "- **PSI thresholds:** <0.10 stable · 0.10-0.25 monitor · ≥0.25 drift (Siddiqi 2006)",
        "- **Baseline:** same-season slice of training data (`monitoring/baselines/<city>.parquet`)",
        "- **Fresh window:** last 7 days from Open-Meteo",
        "- **Code:** [`monitoring/drift_check.py`](../drift_check.py)",
        "- **Full history:** [`history.csv`](history.csv)",
        "",
    ])

    with open(latest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_render_latest_md_writes_summary_and_per_city_tables -v`
Expected: PASS.

- [ ] **Step 9: Stage**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.7: Wire CLI orchestrator + `--regenerate-baselines` flag

**Files:**
- Modify: `monitoring/drift_check.py` (append `main()` + `__name__` guard)
- Modify: `tests/test_drift_check.py` (append the orchestrator-resilience test)

- [ ] **Step 1: Append the CLI orchestrator to `monitoring/drift_check.py`**

```python
# ── CLI Orchestrator ──────────────────────────────────────────────────────
# Two modes:
#   python -m monitoring.drift_check                          # weekly check
#   python -m monitoring.drift_check --regenerate-baselines   # regenerate all 6 baselines

import argparse                                                  # CLI parsing
import logging                                                   # structured logs to stdout
from datetime import datetime                                    # run_date stamping

from monitoring.city_config import CITY_CONFIG, WEATHER_FEATURES, PSI_THRESHOLD_MONITOR, PSI_THRESHOLD_DRIFT

_LOW_BASELINE_THRESHOLD = 100                                    # below this n_baseline, flag LOW_BASELINE per spec §10 A4

logging.basicConfig(level=logging.INFO, format="%(message)s")    # one-line JSON-ish logs to stdout
_log = logging.getLogger("drift_check")


def _classify(psi_value: float) -> str:
    """Return STABLE / MONITOR / DRIFT classification for a PSI value."""
    if psi_value < PSI_THRESHOLD_MONITOR:
        return "STABLE"
    if psi_value < PSI_THRESHOLD_DRIFT:
        return "MONITOR"
    return "DRIFT"


def check_city(city: str, run_date: str) -> List[Dict[str, Any]]:
    """Run drift check for one city and return one row per weather feature.

    Args:
        city:     lowercase city key matching CITY_CONFIG
        run_date: YYYY-MM-DD string for the run_date column

    Returns:
        List of history-row dicts (one per weather feature, or one error row).
    """
    cfg = CITY_CONFIG[city]
    current_season = month_to_season(datetime.utcnow().month)    # NH season derived from UTC month

    # ── Fetch fresh weather; on failure produce a single FETCH_FAILED row ─
    try:
        fresh = fetch_open_meteo(lat=cfg["lat"], lon=cfg["lon"], timezone=cfg["timezone"], days=7)
    except requests.HTTPError as exc:
        _log.error('{"event":"fetch_failed","city":"%s","error":"%s"}', city, exc)
        return [{
            "run_date": run_date, "city": city, "feature": feature, "season": current_season,
            "psi": float("nan"), "status": "FETCH_FAILED", "n_fresh": 0, "n_baseline": 0,
        } for feature in WEATHER_FEATURES]
    except KeyError as exc:
        _log.error('{"event":"fetch_schema_error","city":"%s","missing":"%s"}', city, exc)
        return [{
            "run_date": run_date, "city": city, "feature": feature, "season": current_season,
            "psi": float("nan"), "status": "FETCH_SCHEMA_ERROR", "n_fresh": 0, "n_baseline": 0,
        } for feature in WEATHER_FEATURES]

    # ── Load baseline; same-season slice ─────────────────────────────────
    baseline_all = pd.read_parquet(cfg["baseline_path"])
    baseline_season = baseline_all[baseline_all["season"] == current_season]
    if baseline_season.empty:
        _log.warning('{"event":"baseline_empty","city":"%s","season":"%s"}', city, current_season)
        return [{
            "run_date": run_date, "city": city, "feature": feature, "season": current_season,
            "psi": float("nan"), "status": "BASELINE_EMPTY", "n_fresh": len(fresh), "n_baseline": 0,
        } for feature in WEATHER_FEATURES]

    # ── PSI per feature ──────────────────────────────────────────────────
    rows = []
    for feature in WEATHER_FEATURES:
        baseline_vals = baseline_season[baseline_season["feature"] == feature]["value"].to_numpy()
        n_baseline = len(baseline_vals)
        if n_baseline == 0:
            rows.append({
                "run_date": run_date, "city": city, "feature": feature, "season": current_season,
                "psi": float("nan"), "status": "BASELINE_EMPTY", "n_fresh": len(fresh), "n_baseline": 0,
            })
            continue

        fresh_vals = fresh[feature].to_numpy()
        score = psi(fresh=fresh_vals, baseline=baseline_vals, n_bins=10)
        status = _classify(score) if n_baseline >= _LOW_BASELINE_THRESHOLD else "LOW_BASELINE"
        rows.append({
            "run_date": run_date, "city": city, "feature": feature, "season": current_season,
            "psi": round(score, 4), "status": status,
            "n_fresh": len(fresh), "n_baseline": n_baseline,
        })

    return rows


def main() -> None:
    """CLI entry: weekly drift check, or --regenerate-baselines for one-off baseline rebuild."""
    parser = argparse.ArgumentParser(description="Bike-demand drift monitor")
    parser.add_argument("--regenerate-baselines", action="store_true",
                        help="Rebuild monitoring/baselines/<city>.parquet for all 6 cities from data/processed/")
    args = parser.parse_args()

    if args.regenerate_baselines:
        for city in CITY_CONFIG:
            processed_csv = f"data/processed/{city}_bike_sharing.csv"
            output_parquet = CITY_CONFIG[city]["baseline_path"]
            _log.info('{"event":"regenerate","city":"%s"}', city)
            regenerate_baseline_for_city(processed_csv=processed_csv, output_parquet=output_parquet)
        return

    # ── Weekly check path ────────────────────────────────────────────────
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    all_rows = []
    for city in CITY_CONFIG:
        _log.info('{"event":"check_start","city":"%s","run_date":"%s"}', city, run_date)
        all_rows.extend(check_city(city=city, run_date=run_date))

    append_history(rows=all_rows, history_path="monitoring/reports/history.csv")
    render_latest_md(history_path="monitoring/reports/history.csv",
                     latest_path="monitoring/reports/latest.md")
    _log.info('{"event":"run_complete","n_rows":%d,"run_date":"%s"}', len(all_rows), run_date)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing test for orchestrator fetch-failure resilience**

Append to `tests/test_drift_check.py`:

```python
def test_check_city_fetch_failure_returns_error_rows(monkeypatch, tmp_path):
    """When Open-Meteo fails, check_city returns one FETCH_FAILED row per weather feature — no uncaught exception."""
    import requests
    from monitoring.drift_check import check_city

    # ── Force fetch to raise ─────────────────────────────────────────────
    def _fail(*args, **kwargs):
        raise requests.HTTPError("500 Server Error")
    monkeypatch.setattr("monitoring.drift_check.fetch_open_meteo", _fail)

    rows = check_city(city="seoul", run_date="2026-05-25")

    assert len(rows) == 8, f"Expected 8 rows (one per weather feature), got {len(rows)}"
    assert all(r["status"] == "FETCH_FAILED" for r in rows), \
        "All rows must have status=FETCH_FAILED on fetch failure"
    assert all(r["n_fresh"] == 0 for r in rows)
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_drift_check.py::test_check_city_fetch_failure_returns_error_rows -v`
Expected: PASS.

- [ ] **Step 4: Stage**

```bash
git add monitoring/drift_check.py tests/test_drift_check.py
```

---

### Task S3.8: Generate all 6 baselines and verify

**Files:**
- Create (via script): `monitoring/baselines/seoul.parquet`, `london.parquet`, `nyc.parquet`, `dc.parquet`, `paris.parquet`, `chicago.parquet`

- [ ] **Step 1: Run the regenerator**

Run: `python -m monitoring.drift_check --regenerate-baselines`
Expected output: 6 log lines `{"event":"regenerate","city":"<city>"}`. No exceptions.

- [ ] **Step 2: Verify all 6 baselines on disk**

Run: `ls -la monitoring/baselines/*.parquet`
Expected: 6 files, each ~10-100 KB (size depends on city's training CSV row count).

- [ ] **Step 3: Spot-check Seoul baseline shape**

Run:
```bash
python -c "
import pandas as pd
df = pd.read_parquet('monitoring/baselines/seoul.parquet')
print('columns:', list(df.columns))
print('seasons:', df['season'].unique().tolist())
print('features:', df['feature'].unique().tolist())
print('n_rows:', len(df))
print('per-season:', df['season'].value_counts().to_dict())
"
```
Expected: columns `[season, feature, value]`; 4 seasons; 8 features; ~210k rows (26,303 rows × 8 features); per-season counts roughly balanced across the 4 seasons.

- [ ] **Step 4: Run the parametrized baseline-load test to confirm all 6 are valid**

Run: `pytest tests/test_drift_check.py::test_all_six_baselines_exist_and_loadable -v`
Expected: PASS (6 parametrized cases).

- [ ] **Step 5: Verify the full test file passes (8 tests + the 12 parametrized season cases)**

Run: `pytest tests/test_drift_check.py -v`
Expected: 26 tests pass (8 named test_* functions; one of them parametrized 12 ways for seasons; one parametrized 6 ways for baselines). Watch for the actual collected count and adjust the expected number based on parametrize expansion.

Use context-mode (per CLAUDE.md Rule 14) if output is voluminous:
`mcp__context-mode__ctx_batch_execute` with `pytest tests/test_drift_check.py -v`.

- [ ] **Step 6: Run the full pytest suite to confirm no regression**

Run: `pytest -v 2>&1 | tail -10`
Expected: 32 existing tests + new drift tests all pass; collection count rises from 32 to ~58 (depending on parametrize expansion of new tests). No failures.

- [ ] **Step 7: Stage baselines**

```bash
git add monitoring/baselines/seoul.parquet monitoring/baselines/london.parquet \
        monitoring/baselines/nyc.parquet monitoring/baselines/dc.parquet \
        monitoring/baselines/paris.parquet monitoring/baselines/chicago.parquet
```

(Each file listed explicitly per spec §10 CL5 mitigation — easy to forget one.)

---

### Task S3.9: Local end-to-end smoke + S3 commit

**Files:**
- Modify (via script): `monitoring/reports/history.csv`, `monitoring/reports/latest.md`

- [ ] **Step 1: Run the weekly-check path end-to-end**

Run: `python -m monitoring.drift_check`
Expected output: 6 `{"event":"check_start","city":"<city>"}` lines + 1 `{"event":"run_complete","n_rows":48}` line. Real Open-Meteo calls — should take ~30-60 seconds total.

If running offline or against rate-limited Open-Meteo, expect FETCH_FAILED status rows in the report; that's by design per error handling.

- [ ] **Step 2: Verify both output files written**

Run: `ls -la monitoring/reports/`
Expected: `history.csv` (~5 KB, 48 rows + header) and `latest.md` (~3 KB).

- [ ] **Step 3: Inspect latest.md content**

Run: `cat monitoring/reports/latest.md`
Expected: report header with run date, summary line, 6 per-city tables (Seoul / London / NYC / DC / Paris / Chicago), each with 8 feature rows showing PSI + status + trend "–" (no previous run yet for trend arrows).

If status counts look wrong (e.g. all DRIFT), it means seasonal-baseline assumption is broken OR fresh weather genuinely is anomalous — sanity-check via the Probe pattern from v4.3.0 Paris work before committing.

- [ ] **Step 4: Commit smoke output as part of the S3 module commit**

Stage smoke reports:
```bash
git add monitoring/reports/history.csv monitoring/reports/latest.md
```

Now stage everything for the single S3 feat commit:
```bash
git status --short
```
Expected: working tree shows monitoring/__init__.py, city_config.py, drift_check.py, baselines/*.parquet × 6, baselines/.gitkeep, reports/.gitkeep, reports/history.csv, reports/latest.md, tests/test_drift_check.py — all staged.

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(monitoring): add weekly weather-feature drift monitor (PSI per feature, same-season baseline)

Adds monitoring/ package: drift_check.py orchestrator (Open-Meteo fetch +
PSI math + season mapping + baseline regenerator + report writers + CLI)
+ city_config.py (per-city geo, weather feature list, classification
thresholds) + 6 baseline parquet files (long-form [season, feature, value]
schema, regenerable via `python -m monitoring.drift_check --regenerate-baselines`).

Engineering rationale: temporal features (HOUR, dayofweek, month) are
deterministic and cannot drift; weather features are the only legitimate
drift surface for this model architecture. Same-season baseline slicing
kills the December-always-flags-drift seasonal false-positive failure mode.

PSI thresholds per Siddiqi 2006 / SAS / banking standard:
  <0.10  STABLE / 0.10-0.25 MONITOR / >=0.25 DRIFT
Status enum extended for error states (FETCH_FAILED, FETCH_SCHEMA_ERROR,
BASELINE_EMPTY, LOW_BASELINE) so reports degrade to one bad row rather
than missing entirely.

Hard constraints honoured: no Cloud Monitoring writes, no paid GCP
surface, no alerting (the markdown report committed to git IS the
surface), no refactor of data/fetch_*_weather.py (off critical path),
no new requirements.txt entries (numpy + pandas + requests + pyarrow
all already present).

Reports surface: monitoring/reports/latest.md (rolling snapshot,
overwritten weekly) + monitoring/reports/history.csv (append-only audit).
First local smoke run committed alongside module so reviewers can see
the rendered output without invoking the cron.

8 unit tests in tests/test_drift_check.py via TDD discipline: PSI
identity / shift detection / empty-bin floor / season mapping (12
parametrized cases) / baseline schema (6 parametrized cities) /
history append / latest.md render / orchestrator fetch-failure
resilience. Full pytest collection lifts from 32 to ~58 tests.

S3 of v4.4.0 sprint chain (per
docs/superpowers/plans/2026-05-23-drift-monitoring.md); S4 wires GHA
cron + manual smoke.
EOF
)"
```

- [ ] **Step 6: Push**

Run: `git push origin main`
Expected: push succeeds. CI runs all 8 existing jobs (lint, test, accuracy, docker, publish, publish-gar, build-training-container) — the new pytest tests run under Job 2 (`test`); the slow `accuracy` Job 7 unchanged. Expected: all green.

- [ ] **Step 7: Verify CI green**

Run: `gh run list --branch main --limit 2`
Wait for the run to complete (~5-10 min). If any job red, drill in: `gh run view <RUN_ID> --json jobs` and address before continuing to S4.

- [ ] **Step 8: Update workflow_status.md for S4 re-entry**

Per Rule 9 + Rule 11 close-out:
1. Remove `## In Progress` block for S3
2. Update Status: `## Status: v4.4.0 S3 complete (drift module + 6 baselines + 8 TDD tests committed in feat: <HASH>); next sprint S4 (GHA cron + manual smoke) (as of <today>)`
3. Add `## Last Session` block summarizing S3 work
4. Update Next action:
   > Resume v4.4.0 S4: write `.github/workflows/drift.yml` (schedule cron + workflow_dispatch + commit-back step with `[skip ci]` tag) per plan Sprint S4; trigger manually via `gh workflow run drift.yml` to verify the commit-back loop before letting the cron auto-fire on the next Monday.
5. Update Re-entry: `"resume bike-demand-ml-system v4.4.0 S4"`

---

# Sprint S4 — GHA Cron + Manual Smoke

**Goal:** Add the GitHub Actions workflow that runs `python -m monitoring.drift_check` on a weekly cron, commits the updated `monitoring/reports/` files back to `main` with `[skip ci]`, and verify the loop works via manual `workflow_dispatch`.

**Boundary:** opens with `/clear`. Ends with 1 `ci(monitoring):` commit (workflow file only) + a successful manual run that produced a bot commit on `main`; `workflow_status.md` updated to S5 re-entry.

---

### Task S4.1: Author the GHA workflow file

**Files:**
- Create: `.github/workflows/drift.yml`

- [ ] **Step 1: Inspect existing workflow for conventions**

Run: `head -50 .github/workflows/ci.yml`
Note: Python version, checkout action version, pip-cache pattern. Match these in drift.yml for consistency.

- [ ] **Step 2: Author `.github/workflows/drift.yml`**

Create the file with:

```yaml
# ── Workflow Purpose ─────────────────────────────────────────────────────
# Weekly drift monitor: refetches Open-Meteo weather per city, computes PSI
# vs same-season training baseline, commits the updated report back to main.
# Free-tier safe: ~2 minutes wall-clock per run; cron weekly = ~104 min/year
# (well under GitHub Actions 2000 min/month free quota).
#
# [skip ci] in the bot commit message prevents the report-back commit from
# re-triggering the 8-job ci.yml workflow.

name: drift-monitor

on:
  schedule:
    # Monday 06:00 UTC (Sunday late evening US/EU). Adjust if quieter window preferred.
    - cron: '0 6 * * 1'
  workflow_dispatch: {}  # allow manual trigger from GitHub UI / gh CLI

permissions:
  contents: write  # required to push the bot commit back to main

jobs:
  drift-check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout main
        uses: actions/checkout@v4
        with:
          fetch-depth: 1
          token: ${{ secrets.GITHUB_TOKEN }}  # default GITHUB_TOKEN can push back to main

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run drift check
        run: python -m monitoring.drift_check

      - name: Show report summary
        run: head -15 monitoring/reports/latest.md

      - name: Commit and push report
        run: |
          git config user.name "drift-monitor-bot"
          git config user.email "drift-monitor-bot@users.noreply.github.com"
          git add monitoring/reports/latest.md monitoring/reports/history.csv
          if git diff --cached --quiet; then
            echo "No changes to commit (drift report identical to previous run)"
            exit 0
          fi
          git commit -m "chore(drift): weekly report $(date -u +%Y-%m-%d) [skip ci]"
          git push origin main
```

- [ ] **Step 3: Verify YAML syntax with a quick parse**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/drift.yml'))"`
Expected: no exception; clean parse.

- [ ] **Step 4: Stage**

```bash
git add .github/workflows/drift.yml
```

---

### Task S4.2: Commit + push workflow; trigger manual run

**Files:** Already staged.

- [ ] **Step 1: Commit**

```bash
git commit -m "$(cat <<'EOF'
ci(monitoring): add weekly drift-monitor GHA workflow

Adds .github/workflows/drift.yml:
- schedule: cron '0 6 * * 1' (Mondays 06:00 UTC) + workflow_dispatch for
  manual triggers
- runs `python -m monitoring.drift_check` after pip install
- commits monitoring/reports/{latest.md,history.csv} back to main as
  "chore(drift): weekly report YYYY-MM-DD [skip ci]"
- no-op skip if report is byte-identical to previous run (rare; happens
  if Open-Meteo returns identical fresh-week values)

[skip ci] tag prevents the bot commit from triggering the 8-job ci.yml
workflow — keeps GitHub Actions free-tier consumption to ~2 min/week
(~104 min/year vs the 2000 min/month free quota).

S4 of v4.4.0 sprint chain. S5 wires docs + release.
EOF
)"
```

- [ ] **Step 2: Push**

Run: `git push origin main`

- [ ] **Step 3: Trigger the workflow manually**

Run: `gh workflow run drift.yml`
Expected: command returns success; the workflow now appears in `gh run list`.

- [ ] **Step 4: Wait for the workflow to finish**

Run: `gh run watch` (interactive) OR `gh run list --workflow=drift.yml --limit 1` polled.
Expected runtime: ~2 minutes. Final status: `completed success`.

If failed, drill in: `gh run view <RUN_ID> --log-failed`. Common failures:
- pip install issue → check requirements.txt is current
- Open-Meteo rate limit → wait and re-run
- git push fails → check `permissions: contents: write` is in the YAML

- [ ] **Step 5: Verify the bot commit landed on main**

Run: `git pull origin main && git log --oneline -3`
Expected: top commit is `chore(drift): weekly report YYYY-MM-DD [skip ci]` from `drift-monitor-bot`. Second commit is the `ci(monitoring):` commit from Step 1.

- [ ] **Step 6: Verify the bot commit did NOT trigger ci.yml**

Run: `gh run list --workflow=ci.yml --limit 2`
Expected: most recent `ci.yml` run was from the Step 1 `ci(monitoring):` push, NOT from the bot commit. The `[skip ci]` worked.

- [ ] **Step 7: Inspect latest.md on GitHub web UI**

Open: `https://github.com/deepan-mehta-analytics/bike-demand-ml-system/blob/main/monitoring/reports/latest.md`

Verify:
- Header renders correctly (emoji, bold)
- All 6 per-city tables render with PSI columns right-aligned, Status emojis showing
- Relative links to `../drift_check.py` and `history.csv` work
- No raw markdown syntax bleed-through (no escaping issues)

If anything renders incorrectly, fix the template in `monitoring/drift_check.py:render_latest_md`, re-run locally, commit a follow-up `fix(monitoring):`.

- [ ] **Step 8: Update workflow_status.md for S5 re-entry**

Per Rule 9 + Rule 11 close-out:
1. Remove `## In Progress` block for S4
2. Update Status: `## Status: v4.4.0 S4 complete (GHA cron live + manual smoke verified); next sprint S5 (docs + release) (as of <today>)`
3. Add `## Last Session` block summarizing S4 work (workflow file landed, manual trigger green, bot commit on main, [skip ci] confirmed)
4. Update Next action:
   > Resume v4.4.0 S5: README new `📡 Drift Monitoring` section between Tests and Results; tick Roadmap drift item; refresh Known Limitations + Scaling Considerations; PROJECT-STATUS Phase 15 + Ecosystem row v4.3.0 → v4.4.0; Shiny PROJECT-STATUS cross-repo hash sync; v4.4.0 GitHub release per Rule 11 canonical format; final Step 1.5 staleness sweep across all tracked README + PROJECT-STATUS files.
5. Update Re-entry: `"resume bike-demand-ml-system v4.4.0 S5"`

---

# Sprint S5 — Close-out (Docs + Release + Cross-Repo)

**Goal:** Land the v4.4.0 documentation surface, sync the companion Shiny repo, publish the v4.4.0 GitHub release per Rule 11 canonical format, and run the Step 1.5 staleness sweep.

**Boundary:** opens with `/clear`. Ends with all v4.4.0 ship-gate criteria from spec §9 checked off; release tag visible on GitHub; tracked follow-ups block updated; workflow_status closed out.

---

### Task S5.1: README — add Drift Monitoring section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate insertion point**

Run: `grep -n "^## 🧪 Tests\|^## 📊 Results" README.md`
Expected: 2 line numbers. The new `📡 Drift Monitoring` section goes BETWEEN them.

- [ ] **Step 2: Compose and insert the new section**

Add the following section between `## 🧪 Tests` and `## 📊 Results` (preserve the surrounding `---` separators per README format Rule 6):

```markdown
## 📡 Drift Monitoring

A weekly GitHub Actions cron (`Mondays 06:00 UTC`) refetches the last 7
days of weather for each served city from Open-Meteo, computes PSI
(Population Stability Index) per weather feature against the
same-season slice of the training baseline, and commits the updated
report back to `main`.

**Why weather features only?** The model's input vector is
`(weather features) + (temporal features)`. Temporal features (HOUR,
dayofweek, month, season) are deterministic — they cannot drift.
**Weather features are the only legitimate drift surface for this
architecture**, so weather-side PSI is the correct monitoring target.

**Why same-season baseline?** Without seasonal slicing, every December
would flag drift on TEMPERATURE (fresh weather near 0°C vs pooled-year
baseline mean ~12°C). Slicing per Northern-Hemisphere meteorological
season eliminates this false-positive engine.

**Thresholds** (Siddiqi 2006 / SAS / banking standard):
- `PSI < 0.10` — 🟢 STABLE
- `0.10 ≤ PSI < 0.25` — 🟡 MONITOR
- `PSI ≥ 0.25` — 🔴 DRIFT (retraining candidate)

**Surface:**
- [`monitoring/reports/latest.md`](monitoring/reports/latest.md) —
  rolling snapshot of the most recent run (overwritten weekly)
- [`monitoring/reports/history.csv`](monitoring/reports/history.csv) —
  append-only audit log (one row per city × feature × run)
- [`.github/workflows/drift.yml`](.github/workflows/drift.yml) —
  workflow definition (cron + `workflow_dispatch:` for manual trigger)
- [`monitoring/drift_check.py`](monitoring/drift_check.py) — PSI math
  + Open-Meteo client + report renderers

**Baseline regeneration:** after each model retrain, run
`python -m monitoring.drift_check --regenerate-baselines` to rebuild
all 6 `monitoring/baselines/<city>.parquet` files from the canonical
training CSVs.
```

- [ ] **Step 3: Update Roadmap — tick drift monitoring**

Run: `grep -n "drift" README.md`
Find the Roadmap entry mentioning drift monitoring (likely `- [ ] Drift monitoring …`). Replace `[ ]` with `[x]` and append ` (shipped in v4.4.0)`.

- [ ] **Step 4: Update Known Limitations — record what's NOT yet monitored**

Find the Known Limitations section. Add a bullet:

```markdown
- ✅ ~~Drift monitoring~~ → shipped in v4.4.0 as weekly weather-feature PSI per city. **Concept drift** (changes in the feature→target relationship) is not monitored — would require ground-truth labels flowing back, which is impractical given different cities have different trip-data publication lag (Seoul monthly, NYC/DC quarterly). Tracked as v4.5+ candidate if Paris + London uniform-cadence subset becomes interesting.
```

- [ ] **Step 5: Update Scaling Considerations — note the monitoring tier**

Find the Scaling Considerations section (added in v4.2.0). Add a new row or note to the existing table acknowledging the monitoring tier:

```markdown
| Monitoring tier | Current | Markdown report committed to repo (free, GitHub-native) |
| Monitoring tier (heavier) | Considered | Grafana / Looker Studio dashboard backed by BigQuery (paid Cloud Monitoring metrics or ~$0.02/GB BQ storage); justified only at >100 prediction calls/day or when alerting needed |
```

- [ ] **Step 6: Add a Drift Monitor badge to Project Badges section**

Find `## 🏷️ Project Badges`. Add:

```markdown
[![Drift Monitor](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/drift.yml/badge.svg)](https://github.com/deepan-mehta-analytics/bike-demand-ml-system/actions/workflows/drift.yml)
```

- [ ] **Step 7: Stage**

```bash
git add README.md
```

(Commit happens in Task S5.3 alongside PROJECT-STATUS updates.)

---

### Task S5.2: PROJECT-STATUS.md — Phase 15 block + Ecosystem row

**Files:**
- Modify: `PROJECT-STATUS.md`

- [ ] **Step 1: Find Ecosystem Snapshot row**

Run: `grep -n "bike-demand-ml-system" PROJECT-STATUS.md`
Find the row in the Ecosystem Snapshot table (around line 14 per current state). Update:
- Phase column: `v4.3.0 — Paris timezone fix + cross-city table alignment` → `v4.4.0 — Drift monitoring + MLflow 6/6`
- Last Commit hash → S3 feat commit hash (or S4 ci commit — whichever was the last feature-bearing commit per v4.2.0/v4.3.0 convention)

- [ ] **Step 2: Find Next Milestones priority table**

Find the `### Next Milestones` table. Add a new strikethrough row for v4.4.0 ship:

```markdown
| ~~5.7~~ | bike-demand-ml-system | ~~Phase 15 — Drift monitoring + MLflow 6/6~~ | ~~v4.4.0~~ | **✅ Shipped (<today>)** |
```

- [ ] **Step 3: Add Phase 15 block under Roadmap**

After the existing Phase 14 block, add:

```markdown
### Phase 15 — Drift Monitoring + MLflow 6/6 Promotion ✅ Done (v4.4.0 — commits <S2-FIX-HASH> + <S3-FEAT-HASH> + <S4-CI-HASH>)
* New `monitoring/` package with `drift_check.py` (PSI math + Open-Meteo client + season mapping + baseline regenerator + report writers + CLI orchestrator) + `city_config.py` (declarative per-city geo, feature list, threshold constants) + 6 baseline parquet files (long-form `[season, feature, value]` schema, regenerable via `--regenerate-baselines` flag)
* New `.github/workflows/drift.yml` — weekly cron (Mondays 06:00 UTC) + `workflow_dispatch:` manual trigger; commits report back to `main` with `[skip ci]` (no CI re-trigger; ~2 min/week)
* New `tests/test_drift_check.py` — 8 unit tests via TDD discipline (PSI identity / shift detection / empty-bin floor / season mapping (12 parametrized) / baseline schema (6 parametrized) / history append / latest.md render / orchestrator fetch-failure resilience). pytest collection lifts from 32 to ~58 tests
* `Dockerfile.training:38-43` — added Paris + Chicago CSV copies; Vertex AI custom-job auto-promotes all 6 cities to MLflow Production registry (closes "4 of 6 cities" Known Limitation from v4.3.0)
* `README.md` — new `📡 Drift Monitoring` section between Tests and Results; ticked roadmap drift item; refreshed Known Limitations (concept drift remains open by design); Scaling Considerations updated with monitoring tier acknowledgement; new Drift Monitor badge
* GitHub release v4.4.0 published
```

- [ ] **Step 4: Update Known Limitations — strikethrough MLflow 4/6 line and add concept-drift entry**

Find the Known Limitations section. Apply the same edits as in `README.md`:
- Strikethrough the "4 of 6 cities in MLflow Production registry" line; add "✅ landed at 6/6 in v4.4.0"
- Add the concept-drift bullet matching README §S5.1 Step 4

- [ ] **Step 5: Update Next Step section**

Replace the v4.3.0-shipped framing with v4.4.0-shipped framing. Note the empty tracked-follow-ups block. List remaining open candidates.

- [ ] **Step 6: Stage**

```bash
git add PROJECT-STATUS.md
```

---

### Task S5.3: Python docs commit + push

**Files:** Already staged.

- [ ] **Step 1: Commit**

```bash
git commit -m "$(cat <<'EOF'
docs(monitoring): roll README + PROJECT-STATUS forward to v4.4.0

README:
- new section "📡 Drift Monitoring" between Tests and Results
- new Project Badges entry: drift-monitor workflow status badge
- Roadmap drift item ticked; Known Limitations strikethrough on
  monitoring entry + new concept-drift bullet (acknowledged gap)
- Scaling Considerations updated with monitoring-tier row

PROJECT-STATUS:
- Ecosystem row bumped v4.3.0 → v4.4.0
- Next Milestones priority table: new ~~5.7~~ v4.4.0 ship row
- new Phase 15 block under Roadmap
- Known Limitations: MLflow 4/6 strikethrough; concept-drift entry
- Next Step section rewritten to v4.4.0-SHIPPED framing
EOF
)"
```

- [ ] **Step 2: Push**

Run: `git push origin main`
Expected: push succeeds; ci.yml runs all 8 jobs green. Verify with `gh run list --branch main --limit 1`.

---

### Task S5.4: Cross-repo Shiny sync

**Files:**
- Modify: `bike_demand_prediction/PROJECT-STATUS.md` (hash bump)
- Possibly modify: `bike_demand_prediction/README.md` if any v4.x references appear

- [ ] **Step 1: Switch directory**

The Shiny repo lives at `D:\OneDrive\Developer\DataAnalytics\R-projects\bike-demand-prediction`. Open or `cd` there.

- [ ] **Step 2: Find Python-row references in PROJECT-STATUS.md**

Run: `grep -n "bike-demand-ml-system\|v4\." PROJECT-STATUS.md`
Identify rows referring to the Python repo's version + last commit.

- [ ] **Step 3: Apply edits**

- Ecosystem row: Python phase v4.3.0/<old hash> → v4.4.0/<new hash from Task S5.3>
- Trained City Models block: no change (RMSEs are unchanged; v4.4.0 is monitoring-only)
- Next Milestones priority table: add new `~~5.7~~` ship row mirroring Python side; update next-step row
- Known Limitations: mirror the MLflow 6/6 + concept-drift updates from Python side (cross-doc consistency per Rule 11 Pattern C)
- Next Step section: rewritten to v4.4.0-SHIPPED framing

- [ ] **Step 4: Spot-check Shiny README for stale Python-version references**

Run: `grep -nE "v4\.[0-9]" README.md`
For each match, update version reference to v4.4.0 if it's a "Python service version" reference (not a Shiny-side version like v1.5.0).

- [ ] **Step 5: Stage + commit + push**

```bash
git add PROJECT-STATUS.md README.md  # README only if Step 4 found matches
git commit -m "$(cat <<'EOF'
docs(cross-repo): sync Python v4.4.0 drift monitor + MLflow 6/6 into Shiny status

PROJECT-STATUS:
- bike-demand-ml-system row v4.3.0/<OLD_HASH> → v4.4.0/<NEW_HASH>
- new ~~5.7~~ v4.4.0 ship row; next-step row updated
- Known Limitations: MLflow 4/6 strikethrough; concept-drift entry
  (cross-doc consistency per Rule 11 Pattern C)
- Next Step rewritten v4.4.0-SHIPPED framing

No R code changes — Shiny continues to consume FastAPI over HTTP;
the drift monitor lives entirely in the Python repo.
EOF
)"
git push origin main
```

Replace `<OLD_HASH>` and `<NEW_HASH>` with actual commit hashes.

---

### Task S5.5: GitHub release v4.4.0

**Files:** None (GitHub-side).

- [ ] **Step 1: Verify the release does not already exist**

Run: `gh release list --repo deepan-mehta-analytics/bike-demand-ml-system --limit 5`
Expected: latest release is v4.3.0; v4.4.0 not yet present.

- [ ] **Step 2: Create the release**

```bash
gh release create v4.4.0 \
  --target main \
  --title "v4.4.0 — Drift Monitoring + MLflow 6/6 Promotion" \
  --notes "$(cat <<'EOF'
## 🚲 Bike-Demand-ML-System — v4.4.0

Closes the repo's one-way pipeline with a weekly weather-feature drift monitor for all 6 served cities, and lands the deferred MLflow Paris + Chicago promotion to bring the registry to 6/6.

---

### What's included

**Drift monitoring (new `monitoring/` package)**

| Component | Path | Purpose |
|---|---|---|
| Orchestrator + PSI math | `monitoring/drift_check.py` | Open-Meteo fetch, season mapping, baseline regenerator, report writers, CLI |
| Per-city config | `monitoring/city_config.py` | LAT/LON/tz/feature list + classification thresholds |
| Baselines | `monitoring/baselines/<city>.parquet` × 6 | Long-form `[season, feature, value]`; regenerable via `--regenerate-baselines` |
| Reports | `monitoring/reports/{latest.md, history.csv}` | Rolling snapshot + append-only audit |
| GHA workflow | `.github/workflows/drift.yml` | Weekly cron (Mondays 06:00 UTC) + `workflow_dispatch:` |

**Engineering rationale**

| Decision | Why |
|---|---|
| PSI per weather feature only | Temporal features (HOUR, dayofweek, month) are deterministic; cannot drift |
| Same-season baseline slicing | Eliminates "December always flags drift" false-positive engine |
| Markdown report committed to repo | Free-tier surface; no Cloud Monitoring writes; rendered on GitHub |
| `[skip ci]` on bot commits | Weekly cron consumes ~2 min/week (~104 min/year) of GHA free-tier quota |
| 10 quantile bins, 1e-4 fraction floor | Industry-standard PSI implementation; deterministic + numerically robust |

**MLflow 6/6 promotion**

| Before | After |
|---|---|
| 4 of 6 cities in Production registry (Seoul / London / NYC / DC) | All 6 in Production (added Paris + Chicago) |
| Source: `Dockerfile.training:38-41` copied 4 city CSVs | Now copies all 6 CSVs at lines 38-43 |

**Test coverage delta**

| Suite | Before (v4.3.0) | After (v4.4.0) |
|---|---:|---:|
| pytest collection | 32 | ~58 |
| New file | — | `tests/test_drift_check.py` (8 test_* functions; parametrize expands several) |

---

### Roadmap

- `v4.5.0` — open candidates (no committed thread):
  - Concept drift on the Paris + London uniform-cadence subset (only cities with weekly trip data publication)
  - 7th city (SF / Amsterdam) — diminishing portfolio return per [[portfolio-scaling-judgment]]; not committed
  - Drift-triggered auto-retrain (couples monitoring with training pipeline; out of scope for monitoring-only release)

---
EOF
)"
```

- [ ] **Step 3: Verify the release URL is live**

Run: `gh release view v4.4.0 --repo deepan-mehta-analytics/bike-demand-ml-system`
Expected: shows the release notes; `published` state.

---

### Task S5.6: Step 1.5 staleness sweep (per global CLAUDE.md Rule 11/12)

**Files:** Read-only sweep across all tracked README + PROJECT-STATUS files.

- [ ] **Step 1: Pattern A — counts that drift**

Run:
```bash
grep -nE "[0-9]+ (cities|cit|packages?|jobs?|tests?|rows?|models?|files?)" $(git ls-files '*README*' 'PROJECT-STATUS.md')
```

For each match, verify against current state. Specifically expect drift in:
- Test counts (32 → ~58)
- CI job counts (still 8 in ci.yml; +1 for drift.yml is in a separate file, so don't conflate)
- Python package counts (no change unless requirements.txt edited)
- City model counts (still 6)
- MLflow registry counts (4 → 6 — verify this was updated in Tasks S2.3 + S5.1 + S5.2)

Fix any stale claim inline.

- [ ] **Step 2: Pattern B — pending-vs-done framing rot**

Run:
```bash
grep -nE "^\s*\*\s+\*\*(Post-[a-z-]+|TODO|Pending|Next):\*\*|^\s*-\s+Add\s+`" $(git ls-files '*README*' 'PROJECT-STATUS.md')
grep -nE "(needs to|will be|to be added|pending)" $(git ls-files '*README*' 'PROJECT-STATUS.md')
```

For each match, cross-reference workflow_status.md history. If the action shipped, refactor the bullet to past tense + dated annotation or fold into a `[x]` checked roadmap item.

- [ ] **Step 3: Pattern C — cross-doc consistency (README ↔ PROJECT-STATUS Known Limitations)**

Run:
```bash
diff <(awk '/## (⚠️ |)Known Limitations/,/^---/' README.md | grep "^[-*]") \
     <(awk '/## (⚠️ |)Known Limitations/,/^---/' PROJECT-STATUS.md | grep "^[-*]")
```

For each one-sided bullet: decide whether the gap belongs in both docs (sync) or only one (note asymmetry).

- [ ] **Step 4: Pattern D — edit-bias check**

Run:
```bash
git diff v4.3.0..HEAD --stat -- $(git ls-files '*README*' 'PROJECT-STATUS.md')
```

Anything in those files NOT in the stat is at edit-bias-staleness risk. Walk the H2/H3 table-of-contents of each, mentally tick what S5.1+S5.2 touched, and inspect what they did NOT touch.

- [ ] **Step 5: If any fixes applied, commit them**

```bash
git status --short
```
If files modified:
```bash
git add <files>
git commit -m "docs: post-v4.4.0 staleness sweep — <brief summary of patterns A-D hits>"
git push origin main
```

---

### Task S5.7: Final workflow_status close-out

- [ ] **Step 1: Update workflow_status.md to closed state**

1. Remove `## In Progress` block (if present)
2. Update Status: `## Status: v4.4.0 SHIPPED + post-ship docs hardening complete; tracked follow-ups empty (as of <today>)`
3. Add `## Last Session` block summarizing S5 work (commits, release URL, staleness-sweep findings)
4. Update Next action:
   > No queued thread. v4.5+ candidates open: (a) concept drift on Paris + London uniform-cadence subset, (b) 7th city evaluation, (c) drift-triggered auto-retrain. Decide based on next portfolio outcome priority.
5. Update Re-entry: `"resume bike-demand-ml-system"` (generic — no specific thread queued)

- [ ] **Step 2: Verify all v4.4.0 spec §9 ship-gate criteria are checked**

Walk through the 8 criteria in spec §9. Confirm each is true. If any fail, address before declaring S5 done.

---

## Self-Review

After writing this plan, fresh-eyes check against the spec:

**1. Spec coverage:**
- ✅ §1 Executive Summary — covered by S2 (MLflow) + S3-S5 (drift)
- ✅ §2 Context — referenced in plan front-matter
- ✅ §3 Architecture (file layout + module boundaries + data flow) — implemented in Tasks S3.1-S3.7
- ✅ §4 Statistical Core (PSI + thresholds + season slicing + baseline schema + 6 features) — Tasks S3.2-S3.5, all 8 features in `WEATHER_FEATURES`
- ✅ §5 Report Schema (history.csv + latest.md + status enum) — Tasks S3.6 + S3.7
- ✅ §6 Sprint Shape — entire plan mapped to S2-S5; S1 (spec + plan) is this session
- ✅ §7 Error Handling — Task S3.7 implements all 5 failure modes; smoke test confirms degraded report still renders
- ✅ §8 Testing Strategy — TDD discipline in S3 + 8 tests
- ✅ §9 Success Criteria — Task S5.7 Step 2 walks them
- ✅ §10 Risk Register — mitigations woven into individual task steps (CL2 = explicit `[skip ci]` in S4.1; CL5 = explicit 6-baseline stage in S3.8 Step 7; A1 = Open-Meteo schema test in S3.4 Step 6; etc.)
- ✅ §11 Out-of-Scope — surfaced in S5.5 release notes Roadmap section
- ✅ §12 References — preserved in spec; plan does not duplicate

**2. Placeholder scan:** No "TBD" / "TODO in plan" / "fill in later". All code blocks are complete. `<JOB_ID>`, `<OLD_HASH>`, `<NEW_HASH>`, `<S2-FIX-HASH>`, `<S3-FEAT-HASH>`, `<S4-CI-HASH>`, `<today>` are RUNTIME values captured during execution — not plan-author placeholders. Each is explicitly described in its surrounding step.

**3. Type consistency:** `psi(fresh, baseline, n_bins=10)` signature consistent across Tasks S3.2 + tests + orchestrator usage in S3.7. `check_city(city, run_date)` signature consistent. `append_history(rows, history_path)` + `render_latest_md(history_path, latest_path)` consistent in tests + caller. `regenerate_baseline_for_city(processed_csv, output_parquet)` consistent.

**4. Naming consistency:** All function names use snake_case; module is `monitoring.drift_check`; CITY_CONFIG / WEATHER_FEATURES / MONTH_TO_SEASON / PSI_THRESHOLD_* are SCREAMING_SNAKE constants. Status values uppercase enums.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-23-drift-monitoring.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task in the current session OR allow the user to /clear between sprints and re-invoke; review between tasks; fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`; batch execution with checkpoints for review.

For this plan, the spec-locked S1→S2→S3→S4→S5 cadence with `/clear` boundaries between sprints already constrains the session shape. Recommend: **execute S2 in a fresh session** (after the user `/clear`s and types the S2 re-entry command from workflow_status). For each sprint when re-entered cold, the executing-agent should invoke `superpowers:executing-plans` to drive the task-by-task checklist.
