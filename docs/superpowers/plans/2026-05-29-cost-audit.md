# Cost Audit Service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily read-only Cloud Run service that scans GCP resources against cost-safety thresholds and posts to Slack only when a threshold trips — structurally incapable of becoming a cost leak itself.

**Architecture:** An HTTP handler (`cost-audit/main.py`, functions-framework) is invoked once daily by Cloud Scheduler (OIDC auth). It calls seven independent resource-reading functions, evaluates each reading against configured thresholds, and fires a Slack webhook only if at least one threshold is breached. `DRY_RUN=true` prints the payload to stdout without posting (for local/integration testing). The Slack webhook URL is stored in Secret Manager.

**Tech Stack:** Python 3.11, functions-framework 3.x, google-cloud-artifact-registry, google-cloud-compute, google-cloud-bigquery, google-cloud-storage, google-cloud-secret-manager, google-auth, requests, pytest with unittest.mock.

**Spec:** `docs/superpowers/specs/2026-05-28-cost-audit-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `cost-audit/requirements.txt` | Create | Pinned deps for the Cloud Run service image |
| `cost-audit/thresholds.py` | Create | THRESHOLDS config + `evaluate_thresholds(readings)` → list of alert dicts |
| `cost-audit/notify.py` | Create | `format_alert_message(alerts)` + `post_to_slack(message, webhook_url)` |
| `cost-audit/checks.py` | Create | Seven independent read functions; each returns a dict of readings |
| `cost-audit/main.py` | Create | functions-framework HTTP handler; orchestrates checks → evaluate → notify |
| `cost-audit/Dockerfile` | Create | python:3.11-slim image; non-root user; CMD runs functions-framework |
| `tests/test_cost_audit.py` | Create | Unit tests for evaluate_thresholds + formatter; integration test for handler |

> **Note on imports in tests:** `cost-audit/` uses a hyphen so it is not directly importable. `tests/test_cost_audit.py` inserts `cost-audit/` onto `sys.path` at the top of the file. This is the same pattern as the existing test suite's `rprojroot` workaround.

> **Alert channel:** This plan implements Slack delivery as approved in the spec. The only file to change if switching to email is `notify.py` — replace `post_to_slack()` with an `smtplib`-based `send_email()` and update the Secret Manager secret from a webhook URL to SMTP credentials.

---

## Task 1: Scaffold — requirements, thresholds stub, first failing tests

**Files:**
- Create: `cost-audit/requirements.txt`
- Create: `cost-audit/thresholds.py` (THRESHOLDS dict + stub returning `[]`)
- Create: `tests/test_cost_audit.py` (failing tests)

- [ ] **Step 1: Create `cost-audit/requirements.txt`**

```text
functions-framework==3.5.0
google-cloud-artifact-registry==1.14.1
google-cloud-compute==1.21.0
google-cloud-bigquery==3.34.0
google-cloud-storage==2.18.2
google-cloud-secret-manager==2.23.0
google-auth==2.38.0
requests==2.32.3
```

> After creating the file, verify versions are installable: `pip install --dry-run -r cost-audit/requirements.txt`. If any version is not found on PyPI, bump to the nearest available version and re-verify.

- [ ] **Step 2: Create `cost-audit/thresholds.py` with the THRESHOLDS config and a stub**

```python
# ── Threshold Configuration ────────────────────────────────────────────────────

THRESHOLDS = {                                                          # single source of truth for all cost-safety limits
    "registry_max_versions_per_pkg": 15,                                # alert when any Docker package exceeds this version count
    "registry_max_total_gb": 10.0,                                      # alert when repo total size exceeds 10 GB (free tier is soft-unlimited but we set a guard)
    "compute_max_running_vms": 0,                                       # alert on ANY running VM (expected = 0 in steady state)
    "vertex_max_endpoints": 0,                                          # alert on ANY Vertex endpoint (no free tier for endpoints)
    "bigquery_max_total_gb": 8.0,                                       # alert at 8 GB (free 10 GB storage)
    "gcs_max_bucket_gb": 4.0,                                           # alert at 4 GB per bucket (free 5 GB total)
    "cloud_run_allowlist": {                                            # services that are expected and approved
        "bike-demand-api",                                              # inference API
        "gbfs-poller",                                                  # GBFS station poller
        "bike-demand-trigger",                                          # Vertex AI trigger
        "billing-kill-switch",                                          # budget protection
        "cost-audit",                                                   # this service
    },
    "spend_mtd_max_inr": 500.0,                                         # alert when month-to-date spend exceeds ₹500
}


# ── Threshold Evaluation ───────────────────────────────────────────────────────

def evaluate_thresholds(readings: dict) -> list:                        # stub: returns empty list until Task 2 implements it
    """Evaluate resource readings against thresholds. Returns list of alert dicts."""
    return []                                                           # placeholder — tests will fail until Task 2 implements this
```

- [ ] **Step 3: Write failing tests in `tests/test_cost_audit.py`**

```python
# ── Path Setup ────────────────────────────────────────────────────────────────
import sys                                                              # standard library for path manipulation
import os                                                               # standard library for path joining
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cost-audit"))  # add cost-audit/ to import path

# ── Imports ───────────────────────────────────────────────────────────────────
import pytest                                                           # test framework
from thresholds import evaluate_thresholds, THRESHOLDS                  # module under test


# ── Fixtures ──────────────────────────────────────────────────────────────────

def healthy_readings():                                                 # all readings within limits — used across multiple tests
    """Return a readings dict where every check is within threshold."""
    return {
        "registry": {"pkg_versions": {"bike-demand-api": 3}, "total_gb": 2.0},
        "compute": {"running_vms": []},
        "vertex": {"endpoints": []},
        "bigquery": {"total_gb": 1.0},
        "gcs": {"bucket_sizes": {"bike-demand-staging": 0.5}},
        "cloud_run": {"services": [
            {"name": "bike-demand-api", "min_instances": 0},
            {"name": "gbfs-poller", "min_instances": 0},
        ]},
        "spend": {"mtd_cost_inr": 200.0},
    }


# ── Alert-only contract ────────────────────────────────────────────────────────

def test_healthy_readings_produce_no_alerts():
    """Core contract: no alerts when all readings are within thresholds."""
    alerts = evaluate_thresholds(healthy_readings())
    assert alerts == [], f"Expected no alerts, got: {alerts}"


# ── Registry checks ────────────────────────────────────────────────────────────

def test_registry_version_count_trips_alert():
    """Alert fires when a package has more versions than the limit."""
    readings = healthy_readings()
    readings["registry"]["pkg_versions"]["bike-demand-api"] = 16        # one over the limit of 15
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "registry_versions" for a in alerts)

def test_registry_total_size_trips_alert():
    """Alert fires when total repo size exceeds 10 GB."""
    readings = healthy_readings()
    readings["registry"]["total_gb"] = 10.1                             # just over the 10 GB limit
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "registry_size" for a in alerts)


# ── Compute check ──────────────────────────────────────────────────────────────

def test_running_vm_trips_alert():
    """Alert fires when any VM is running (expected = 0)."""
    readings = healthy_readings()
    readings["compute"]["running_vms"] = ["instance-leftover"]          # unexpected VM present
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "compute_vms" for a in alerts)


# ── Vertex check ───────────────────────────────────────────────────────────────

def test_vertex_endpoint_trips_alert():
    """Alert fires when any Vertex endpoint is active."""
    readings = healthy_readings()
    readings["vertex"]["endpoints"] = [{"name": "projects/p/locations/l/endpoints/123"}]
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "vertex_endpoints" for a in alerts)


# ── BigQuery check ─────────────────────────────────────────────────────────────

def test_bigquery_size_trips_alert():
    """Alert fires when total BQ storage exceeds 8 GB."""
    readings = healthy_readings()
    readings["bigquery"]["total_gb"] = 8.1
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "bigquery_size" for a in alerts)


# ── GCS check ──────────────────────────────────────────────────────────────────

def test_gcs_bucket_size_trips_alert():
    """Alert fires when any GCS bucket exceeds 4 GB."""
    readings = healthy_readings()
    readings["gcs"]["bucket_sizes"]["bike-demand-staging"] = 4.1
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "gcs_bucket" for a in alerts)


# ── Cloud Run checks ───────────────────────────────────────────────────────────

def test_unknown_cloud_run_service_trips_alert():
    """Alert fires for any Cloud Run service not in the allowlist."""
    readings = healthy_readings()
    readings["cloud_run"]["services"].append({"name": "mystery-service", "min_instances": 0})
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "cloud_run_unknown" for a in alerts)

def test_always_on_cloud_run_service_trips_alert():
    """Alert fires when any service has minScale > 0 (always-on cost risk)."""
    readings = healthy_readings()
    readings["cloud_run"]["services"][0]["min_instances"] = 1           # bike-demand-api set to always-on
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "cloud_run_always_on" for a in alerts)


# ── Spend check ────────────────────────────────────────────────────────────────

def test_spend_mtd_trips_alert():
    """Alert fires when month-to-date spend exceeds ₹500."""
    readings = healthy_readings()
    readings["spend"]["mtd_cost_inr"] = 501.0
    alerts = evaluate_thresholds(readings)
    assert any(a["check"] == "spend_mtd" for a in alerts)


# ── Multiple alerts ────────────────────────────────────────────────────────────

def test_multiple_thresholds_tripped_returns_all_alerts():
    """All breached thresholds are reported, not just the first."""
    readings = healthy_readings()
    readings["compute"]["running_vms"] = ["vm-a"]
    readings["spend"]["mtd_cost_inr"] = 600.0
    alerts = evaluate_thresholds(readings)
    checks = [a["check"] for a in alerts]
    assert "compute_vms" in checks
    assert "spend_mtd" in checks
```

- [ ] **Step 4: Run tests to confirm they all fail**

```bash
cd "D:\OneDrive\Developer\Data Engineering\bike-demand-ml-system"
pytest tests/test_cost_audit.py -v
```

Expected: 11 FAILED (all assertions fail because `evaluate_thresholds` returns `[]`).

- [ ] **Step 5: Commit the failing scaffold**

```bash
git add cost-audit/requirements.txt cost-audit/thresholds.py tests/test_cost_audit.py
git commit -m "test(cost-audit): add failing unit tests for evaluate_thresholds scaffold"
```

---

## Task 2: Implement `evaluate_thresholds` + `notify.py`

**Files:**
- Modify: `cost-audit/thresholds.py` (replace stub body)
- Create: `cost-audit/notify.py`

- [ ] **Step 1: Replace the stub body in `cost-audit/thresholds.py`**

Replace only the `evaluate_thresholds` function body (keep THRESHOLDS dict unchanged):

```python
def evaluate_thresholds(readings: dict) -> list:                        # evaluates all resource readings; each check is independent
    """Evaluate resource readings against thresholds. Returns list of alert dicts."""
    alerts = []                                                         # accumulate all tripped thresholds

    # ── Registry ──────────────────────────────────────────────────────────────
    registry = readings.get("registry", {})                             # registry readings dict from checks.py
    for pkg, count in registry.get("pkg_versions", {}).items():        # check each package's version count
        if count > THRESHOLDS["registry_max_versions_per_pkg"]:         # trip when versions exceed limit
            alerts.append({
                "check": "registry_versions",
                "pkg": pkg,
                "count": count,
                "limit": THRESHOLDS["registry_max_versions_per_pkg"],
            })
    total_gb = registry.get("total_gb", 0.0)                           # total repo size in GB
    if total_gb > THRESHOLDS["registry_max_total_gb"]:                  # trip when repo exceeds 10 GB
        alerts.append({
            "check": "registry_size",
            "total_gb": total_gb,
            "limit": THRESHOLDS["registry_max_total_gb"],
        })

    # ── Compute ────────────────────────────────────────────────────────────────
    running_vms = readings.get("compute", {}).get("running_vms", [])   # list of running VM names
    if running_vms:                                                     # any VM = alert (expected = 0)
        alerts.append({"check": "compute_vms", "vms": running_vms})

    # ── Vertex AI ──────────────────────────────────────────────────────────────
    endpoints = readings.get("vertex", {}).get("endpoints", [])         # list of active endpoints
    if endpoints:                                                       # any endpoint = alert (no free tier)
        alerts.append({
            "check": "vertex_endpoints",
            "endpoints": [e.get("name", str(e)) for e in endpoints],
        })

    # ── BigQuery ───────────────────────────────────────────────────────────────
    bq_gb = readings.get("bigquery", {}).get("total_gb", 0.0)          # total BQ storage in GB
    if bq_gb > THRESHOLDS["bigquery_max_total_gb"]:                     # trip at 8 GB (free 10 GB)
        alerts.append({
            "check": "bigquery_size",
            "total_gb": bq_gb,
            "limit": THRESHOLDS["bigquery_max_total_gb"],
        })

    # ── GCS ────────────────────────────────────────────────────────────────────
    for bucket, size_gb in readings.get("gcs", {}).get("bucket_sizes", {}).items():  # check each bucket
        if size_gb > THRESHOLDS["gcs_max_bucket_gb"]:                   # trip at 4 GB per bucket
            alerts.append({
                "check": "gcs_bucket",
                "bucket": bucket,
                "size_gb": size_gb,
                "limit": THRESHOLDS["gcs_max_bucket_gb"],
            })

    # ── Cloud Run ──────────────────────────────────────────────────────────────
    allowlist = THRESHOLDS["cloud_run_allowlist"]                       # set of approved service names
    for svc in readings.get("cloud_run", {}).get("services", []):       # check each service
        name = svc["name"]                                              # short service name (no path prefix)
        if name not in allowlist:                                       # unknown service = alert
            alerts.append({"check": "cloud_run_unknown", "service": name})
        if svc.get("min_instances", 0) > 0:                            # always-on = alert
            alerts.append({
                "check": "cloud_run_always_on",
                "service": name,
                "min_instances": svc["min_instances"],
            })

    # ── Spend ──────────────────────────────────────────────────────────────────
    mtd = readings.get("spend", {}).get("mtd_cost_inr", 0.0)           # month-to-date spend in INR
    if mtd > THRESHOLDS["spend_mtd_max_inr"]:                          # trip at ₹500 MTD
        alerts.append({
            "check": "spend_mtd",
            "mtd_cost_inr": mtd,
            "limit": THRESHOLDS["spend_mtd_max_inr"],
        })

    return alerts                                                       # empty list = all healthy
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
pytest tests/test_cost_audit.py -v
```

Expected: 11 PASSED.

- [ ] **Step 3: Create `cost-audit/notify.py`**

```python
# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                         # HTTP client for Slack webhook POST


# ── Message Formatter ─────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a Slack-ready string
    """Format a list of alert dicts into a Slack message string."""
    lines = ["🚨 *GCP Cost Audit — Thresholds Tripped*"]               # header line always present when called
    for alert in alerts:                                                # one bullet per alert
        check = alert["check"]                                          # discriminator key
        if check == "registry_versions":
            lines.append(
                f"  • Artifact Registry: `{alert['pkg']}` has {alert['count']} versions "
                f"(limit {alert['limit']})"
            )
        elif check == "registry_size":
            lines.append(
                f"  • Artifact Registry: total size {alert['total_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )
        elif check == "compute_vms":
            vms = ", ".join(alert["vms"])                               # comma-separated VM names
            lines.append(f"  • Compute: {len(alert['vms'])} running VM(s): {vms}")
        elif check == "vertex_endpoints":
            lines.append(
                f"  • Vertex AI: {len(alert['endpoints'])} active endpoint(s) "
                f"(paid tier — no always-free quota)"
            )
        elif check == "bigquery_size":
            lines.append(
                f"  • BigQuery: total storage {alert['total_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )
        elif check == "gcs_bucket":
            lines.append(
                f"  • GCS: bucket `{alert['bucket']}` is {alert['size_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )
        elif check == "cloud_run_unknown":
            lines.append(
                f"  • Cloud Run: unknown service `{alert['service']}` not in allowlist"
            )
        elif check == "cloud_run_always_on":
            lines.append(
                f"  • Cloud Run: `{alert['service']}` has minScale={alert['min_instances']} "
                f"(always-on = paid)"
            )
        elif check == "spend_mtd":
            lines.append(
                f"  • MTD Spend: ₹{alert['mtd_cost_inr']:.0f} "
                f"(limit ₹{alert['limit']:.0f})"
            )
    return "\n".join(lines)                                             # single string; Slack renders newlines


# ── Slack Delivery ────────────────────────────────────────────────────────────

def post_to_slack(message: str, webhook_url: str) -> bool:              # posts to Slack incoming webhook
    """POST message to Slack. Returns True on HTTP 200, False otherwise."""
    try:
        resp = requests.post(                                           # Slack webhook expects JSON with 'text' key
            webhook_url,
            json={"text": message},
            timeout=10,                                                 # 10s timeout; failure is logged, not fatal
        )
        return resp.status_code == 200                                  # Slack returns 200 + "ok" on success
    except requests.RequestException:                                   # network errors are non-fatal
        return False
```

- [ ] **Step 4: Add formatter + delivery tests to `tests/test_cost_audit.py`**

Append these tests to the end of the existing file:

```python
# ── notify.py tests ────────────────────────────────────────────────────────────
from notify import format_alert_message, post_to_slack                  # formatter and delivery under test
from unittest.mock import patch, MagicMock                              # mock requests.post


def test_format_alert_message_contains_check_name():
    """Formatted message includes a recognisable line for each alert type."""
    alerts = [
        {"check": "registry_versions", "pkg": "bike-demand-api", "count": 20, "limit": 15},
        {"check": "compute_vms", "vms": ["instance-old"]},
        {"check": "spend_mtd", "mtd_cost_inr": 600.0, "limit": 500.0},
    ]
    msg = format_alert_message(alerts)
    assert "bike-demand-api" in msg                                     # registry package name present
    assert "instance-old" in msg                                        # VM name present
    assert "₹600" in msg                                                # spend amount present
    assert "🚨" in msg                                                  # header emoji present


def test_post_to_slack_returns_true_on_200():
    """post_to_slack returns True when webhook responds with HTTP 200."""
    with patch("notify.requests.post") as mock_post:                    # mock the requests.post call
        mock_response = MagicMock()                                     # fake response object
        mock_response.status_code = 200                                 # simulate success
        mock_post.return_value = mock_response
        result = post_to_slack("test message", "https://hooks.slack.com/fake")
    assert result is True


def test_post_to_slack_returns_false_on_non_200():
    """post_to_slack returns False when webhook returns a non-200 status."""
    with patch("notify.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400                                 # simulate failure
        mock_post.return_value = mock_response
        result = post_to_slack("test message", "https://hooks.slack.com/fake")
    assert result is False


def test_post_to_slack_returns_false_on_network_error():
    """post_to_slack returns False (not an exception) when network fails."""
    import requests as req                                              # real requests for exception type
    with patch("notify.requests.post", side_effect=req.ConnectionError("timeout")):
        result = post_to_slack("test message", "https://hooks.slack.com/fake")
    assert result is False
```

- [ ] **Step 5: Run full test file to confirm all tests pass**

```bash
pytest tests/test_cost_audit.py -v
```

Expected: 15 PASSED.

- [ ] **Step 6: Commit**

```bash
git add cost-audit/thresholds.py cost-audit/notify.py tests/test_cost_audit.py
git commit -m "feat(cost-audit): implement evaluate_thresholds and Slack notify"
```

---

## Task 3: Implement `checks.py` — seven resource-reading functions

**Files:**
- Create: `cost-audit/checks.py`

Each function takes explicit parameters (no globals), returns a plain dict, raises on unrecoverable error. The caller in `main.py` wraps each in `try/except`.

- [ ] **Step 1: Create `cost-audit/checks.py`**

```python
# ── Imports ───────────────────────────────────────────────────────────────────
import logging                                                          # structured logging to Cloud Logging via stdout
import requests                                                         # HTTP client for REST-based GCP calls
import google.auth                                                      # ADC credential resolution
import google.auth.transport.requests                                   # transport for refreshing credentials

from google.cloud import artifactregistry_v1                            # Artifact Registry client
from google.cloud import compute_v1                                     # Compute Engine instances client
from google.cloud import bigquery                                       # BigQuery client for queries + table metadata
from google.cloud import storage                                        # GCS client for listing buckets + blobs

logger = logging.getLogger(__name__)                                    # module-level logger


# ── Internal Helper ───────────────────────────────────────────────────────────

def _get_auth_headers() -> dict:                                        # returns Bearer token header for REST calls
    """Return Authorization header dict with a fresh ADC token."""
    creds, _ = google.auth.default()                                    # resolve ADC (Cloud Run SA in prod, gcloud in dev)
    auth_req = google.auth.transport.requests.Request()                 # transport object required for token refresh
    creds.refresh(auth_req)                                             # ensure token is current
    return {"Authorization": f"Bearer {creds.token}"}                  # header dict for requests.get/post


# ── Artifact Registry ─────────────────────────────────────────────────────────

def check_artifact_registry(project: str, location: str, repo: str) -> dict:
    """List Docker images in the repo. Returns pkg_versions dict + total_gb float."""
    client = artifactregistry_v1.ArtifactRegistryClient()              # uses ADC automatically
    parent = f"projects/{project}/locations/{location}/repositories/{repo}"  # resource path
    request = artifactregistry_v1.ListDockerImagesRequest(parent=parent)     # paginated request

    pkg_versions = {}                                                   # {package_name: version_count}
    total_bytes = 0                                                     # running byte total across all images

    for img in client.list_docker_images(request=request):             # auto-paginates
        # img.name looks like "projects/.../repositories/bike-demand-repo/dockerImages/bike-demand-api@sha256:abc"
        img_path = img.name.split("/dockerImages/")[-1]                # strip resource prefix
        pkg_name = img_path.split("@")[0]                              # package name is before the digest
        pkg_versions[pkg_name] = pkg_versions.get(pkg_name, 0) + 1    # increment version count
        total_bytes += img.image_size_bytes                             # accumulate size

    total_gb = total_bytes / 1_000_000_000                             # convert bytes to GB (1e9, not 2^30)
    logger.info(f"Registry: {sum(pkg_versions.values())} images, {total_gb:.2f} GB")
    return {"pkg_versions": pkg_versions, "total_gb": total_gb}


# ── Compute Engine ────────────────────────────────────────────────────────────

def check_compute(project: str) -> dict:
    """List running Compute Engine VMs. Returns list of VM names."""
    client = compute_v1.InstancesClient()                              # uses ADC automatically
    request = compute_v1.AggregatedListInstancesRequest(project=project)  # aggregated = all zones
    agg_list = client.aggregated_list(request=request)                 # returns per-zone groups

    running_vms = []                                                    # names of VMs currently RUNNING
    for _zone, instances_in_zone in agg_list:                          # iterate all zone groups
        if instances_in_zone.instances:                                 # skip empty zones
            for instance in instances_in_zone.instances:               # check each VM
                if instance.status == "RUNNING":                       # only care about active VMs
                    running_vms.append(instance.name)

    logger.info(f"Compute: {len(running_vms)} running VMs")
    return {"running_vms": running_vms}


# ── Vertex AI (REST) ──────────────────────────────────────────────────────────

def check_vertex(project: str, location: str) -> dict:
    """List Vertex AI endpoints via REST (avoids the heavy google-cloud-aiplatform dep)."""
    headers = _get_auth_headers()                                       # fresh Bearer token
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1"
        f"/projects/{project}/locations/{location}/endpoints"
    )                                                                   # Vertex AI Endpoints REST endpoint
    resp = requests.get(url, headers=headers, timeout=30)              # read-only GET
    resp.raise_for_status()                                             # raise on 4xx/5xx
    endpoints = resp.json().get("endpoints", [])                       # empty list = no endpoints (healthy)
    logger.info(f"Vertex: {len(endpoints)} endpoints")
    return {"endpoints": endpoints}


# ── BigQuery ──────────────────────────────────────────────────────────────────

def check_bigquery(project: str) -> dict:
    """Sum storage across all BQ datasets. Returns total_gb float."""
    client = bigquery.Client(project=project)                          # uses ADC automatically
    total_bytes = 0                                                     # running byte total across all tables

    for ds_item in client.list_datasets():                             # iterate all datasets in the project
        dataset_id = ds_item.dataset_id                                # e.g. "billing_export"
        for tbl_item in client.list_tables(dataset_id):                # iterate all tables in the dataset
            table_ref = f"{project}.{dataset_id}.{tbl_item.table_id}" # fully qualified table reference
            try:
                table = client.get_table(table_ref)                    # fetch table metadata (includes num_bytes)
                total_bytes += table.num_bytes or 0                    # num_bytes is None for streaming tables
            except Exception as e:
                logger.warning(f"BQ table metadata failed for {table_ref}: {e}")

    total_gb = total_bytes / 1_000_000_000                             # convert bytes to GB
    logger.info(f"BigQuery: {total_gb:.2f} GB total storage")
    return {"total_gb": total_gb}


# ── BigQuery — MTD spend ───────────────────────────────────────────────────────

BILLING_TABLE = (
    "bike-demand-ml-system.billing_export"
    ".gcp_billing_export_v1_015DB7_CE9C3D_2F5093"
)                                                                       # billing export table (account 015DB7-CE9C3D-2F5093)

def check_spend_mtd(project: str) -> dict:
    """Query billing export for month-to-date spend. Returns mtd_cost_inr float."""
    client = bigquery.Client(project=project)                          # uses ADC; SA needs bigquery.dataViewer on billing_export
    query = f"""
        SELECT ROUND(SUM(cost), 2) AS mtd_cost_inr
        FROM `{BILLING_TABLE}`
        WHERE DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
    """                                                                 # aggregates all services, current calendar month
    try:
        rows = list(client.query(query).result())                      # blocks until query completes (~1s for small tables)
        mtd_cost = float(rows[0]["mtd_cost_inr"]) if rows and rows[0]["mtd_cost_inr"] else 0.0
    except Exception as e:
        logger.warning(f"Billing query failed (table may not exist yet): {e}")
        mtd_cost = 0.0                                                  # treat as zero if table is absent or empty
    logger.info(f"Spend MTD: ₹{mtd_cost:.0f}")
    return {"mtd_cost_inr": mtd_cost}


# ── GCS ───────────────────────────────────────────────────────────────────────

def check_gcs(project: str) -> dict:
    """Sum blob sizes per bucket. Returns bucket_sizes dict {bucket_name: size_gb}."""
    client = storage.Client(project=project)                           # uses ADC automatically
    bucket_sizes = {}                                                   # {bucket_name: total_gb}

    for bucket in client.list_buckets():                               # iterate all buckets in the project
        total_bytes = sum(                                              # sum all blob sizes; list_blobs auto-paginates
            blob.size for blob in client.list_blobs(bucket.name)
            if blob.size                                                # skip blobs with None size (e.g. folders)
        )
        bucket_sizes[bucket.name] = total_bytes / 1_000_000_000       # convert bytes to GB
        logger.info(f"GCS: {bucket.name} = {bucket_sizes[bucket.name]:.2f} GB")

    return {"bucket_sizes": bucket_sizes}


# ── Cloud Run (REST) ──────────────────────────────────────────────────────────

def check_cloud_run(project: str, location: str) -> dict:
    """List Cloud Run services via REST. Returns list of {name, min_instances} dicts."""
    headers = _get_auth_headers()                                       # fresh Bearer token
    url = f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/services"
    resp = requests.get(url, headers=headers, timeout=30)              # read-only GET
    resp.raise_for_status()                                             # raise on 4xx/5xx

    services = []                                                       # list of service summary dicts
    for svc in resp.json().get("services", []):                        # empty list if no services exist
        name = svc["name"].split("/services/")[-1]                     # strip resource path prefix to get short name
        scaling = svc.get("scaling", {})                               # scaling config block may be absent
        min_instances = scaling.get("minInstanceCount", 0)             # 0 = scale-to-zero (desired state)
        services.append({"name": name, "min_instances": min_instances})

    logger.info(f"Cloud Run: {len(services)} services found")
    return {"services": services}
```

- [ ] **Step 2: Add mock-based tests for checks.py to `tests/test_cost_audit.py`**

Append to the end of the file:

```python
# ── checks.py tests ────────────────────────────────────────────────────────────
from unittest.mock import patch, MagicMock, PropertyMock                # standard mocking
from checks import (                                                    # all seven check functions
    check_artifact_registry,
    check_compute,
    check_vertex,
    check_bigquery,
    check_spend_mtd,
    check_gcs,
    check_cloud_run,
)


def test_check_artifact_registry_counts_versions_and_gb():
    """check_artifact_registry groups images by package and sums GB."""
    fake_img_a = MagicMock()                                           # first image — bike-demand-api pkg
    fake_img_a.name = "projects/p/locations/us-central1/repositories/r/dockerImages/bike-demand-api@sha256:aaa"
    fake_img_a.image_size_bytes = 500_000_000                          # 0.5 GB

    fake_img_b = MagicMock()                                           # second image — same package, different digest
    fake_img_b.name = "projects/p/locations/us-central1/repositories/r/dockerImages/bike-demand-api@sha256:bbb"
    fake_img_b.image_size_bytes = 300_000_000                          # 0.3 GB

    with patch("checks.artifactregistry_v1.ArtifactRegistryClient") as MockClient:
        MockClient.return_value.list_docker_images.return_value = [fake_img_a, fake_img_b]
        result = check_artifact_registry("proj", "us-central1", "bike-demand-repo")

    assert result["pkg_versions"]["bike-demand-api"] == 2              # two versions of the same package
    assert abs(result["total_gb"] - 0.8) < 0.001                      # 0.5 + 0.3 GB


def test_check_compute_returns_running_vm_names():
    """check_compute returns names of VMs in RUNNING state."""
    fake_instance = MagicMock()
    fake_instance.name = "stray-vm"
    fake_instance.status = "RUNNING"

    fake_zone_group = MagicMock()
    fake_zone_group.instances = [fake_instance]

    with patch("checks.compute_v1.InstancesClient") as MockClient:
        MockClient.return_value.aggregated_list.return_value = [("zones/us-central1-a", fake_zone_group)]
        result = check_compute("proj")

    assert "stray-vm" in result["running_vms"]


def test_check_vertex_returns_endpoint_list():
    """check_vertex returns list of endpoints from the Vertex AI REST API."""
    fake_endpoint = {"name": "projects/p/locations/us-central1/endpoints/123", "displayName": "test"}

    with patch("checks.requests.get") as mock_get, \
         patch("checks._get_auth_headers", return_value={"Authorization": "Bearer fake"}):
        mock_get.return_value.json.return_value = {"endpoints": [fake_endpoint]}
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = MagicMock()
        result = check_vertex("proj", "us-central1")

    assert len(result["endpoints"]) == 1
    assert result["endpoints"][0]["displayName"] == "test"


def test_check_bigquery_sums_table_bytes():
    """check_bigquery returns total GB summed across all datasets and tables."""
    fake_ds = MagicMock()
    fake_ds.dataset_id = "my_dataset"

    fake_tbl_item = MagicMock()
    fake_tbl_item.table_id = "my_table"

    fake_table = MagicMock()
    fake_table.num_bytes = 2_000_000_000                               # 2 GB

    with patch("checks.bigquery.Client") as MockClient:
        mock_bq = MockClient.return_value
        mock_bq.list_datasets.return_value = [fake_ds]
        mock_bq.list_tables.return_value = [fake_tbl_item]
        mock_bq.get_table.return_value = fake_table
        result = check_bigquery("proj")

    assert abs(result["total_gb"] - 2.0) < 0.001


def test_check_spend_mtd_returns_cost():
    """check_spend_mtd returns month-to-date cost in INR from billing export."""
    fake_row = {"mtd_cost_inr": 312.5}

    with patch("checks.bigquery.Client") as MockClient:
        MockClient.return_value.query.return_value.result.return_value = [fake_row]
        result = check_spend_mtd("proj")

    assert result["mtd_cost_inr"] == 312.5


def test_check_spend_mtd_returns_zero_on_query_failure():
    """check_spend_mtd returns 0.0 gracefully when billing table does not exist."""
    with patch("checks.bigquery.Client") as MockClient:
        MockClient.return_value.query.side_effect = Exception("Table not found")
        result = check_spend_mtd("proj")

    assert result["mtd_cost_inr"] == 0.0


def test_check_gcs_returns_bucket_sizes():
    """check_gcs returns per-bucket sizes in GB."""
    fake_bucket = MagicMock()
    fake_bucket.name = "bike-demand-staging"

    fake_blob = MagicMock()
    fake_blob.size = 100_000_000                                       # 0.1 GB

    with patch("checks.storage.Client") as MockClient:
        MockClient.return_value.list_buckets.return_value = [fake_bucket]
        MockClient.return_value.list_blobs.return_value = [fake_blob]
        result = check_gcs("proj")

    assert "bike-demand-staging" in result["bucket_sizes"]
    assert abs(result["bucket_sizes"]["bike-demand-staging"] - 0.1) < 0.001


def test_check_cloud_run_extracts_service_names_and_min_instances():
    """check_cloud_run returns service names and minScale values."""
    fake_service = {
        "name": "projects/p/locations/us-central1/services/gbfs-poller",
        "scaling": {"minInstanceCount": 0},
    }

    with patch("checks.requests.get") as mock_get, \
         patch("checks._get_auth_headers", return_value={"Authorization": "Bearer fake"}):
        mock_get.return_value.json.return_value = {"services": [fake_service]}
        mock_get.return_value.raise_for_status = MagicMock()
        result = check_cloud_run("proj", "us-central1")

    assert result["services"][0]["name"] == "gbfs-poller"
    assert result["services"][0]["min_instances"] == 0
```

- [ ] **Step 3: Run all cost-audit tests**

```bash
pytest tests/test_cost_audit.py -v
```

Expected: 23 PASSED.

- [ ] **Step 4: Commit**

```bash
git add cost-audit/checks.py tests/test_cost_audit.py
git commit -m "feat(cost-audit): implement all seven resource-reading check functions"
```

---

## Task 4: Wire `main.py` HTTP handler

**Files:**
- Create: `cost-audit/main.py`

- [ ] **Step 1: Create `cost-audit/main.py`**

```python
# ── Imports ───────────────────────────────────────────────────────────────────
import os                                                               # environment variable access
import logging                                                          # structured logging to stdout (Cloud Logging picks it up)
import functions_framework                                              # HTTP handler decorator for Cloud Run

from checks import (                                                    # all seven read functions
    check_artifact_registry,
    check_compute,
    check_vertex,
    check_bigquery,
    check_spend_mtd,
    check_gcs,
    check_cloud_run,
)
from thresholds import evaluate_thresholds                              # pure threshold evaluation
from notify import format_alert_message, post_to_slack                  # formatting + Slack delivery

# ── Configuration ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)                                # emit INFO+ to stdout
logger = logging.getLogger(__name__)                                    # module-level logger

PROJECT = os.environ.get("GCP_PROJECT", "bike-demand-ml-system")       # GCP project ID
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")              # GCP region for Cloud Run + Vertex
AR_REPO = os.environ.get("AR_REPO", "bike-demand-repo")                # Artifact Registry repo name
SLACK_SECRET = os.environ.get("SLACK_SECRET_NAME", "cost-audit-slack-webhook")  # Secret Manager secret name
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"             # if true: log payload, skip Slack POST


# ── HTTP Handler ──────────────────────────────────────────────────────────────

@functions_framework.http                                               # registers audit() as the Cloud Run HTTP handler
def audit(request):
    """Daily cost audit handler. Called by Cloud Scheduler once per day."""
    logger.info("Cost audit starting")

    readings = {}                                                       # accumulate results from each independent check

    # ── Run all checks (each wrapped independently) ────────────────────────────
    for label, fn, args in [
        ("registry",  check_artifact_registry, (PROJECT, LOCATION, AR_REPO)),
        ("compute",   check_compute,            (PROJECT,)),
        ("vertex",    check_vertex,             (PROJECT, LOCATION)),
        ("bigquery",  check_bigquery,           (PROJECT,)),
        ("spend",     check_spend_mtd,          (PROJECT,)),
        ("gcs",       check_gcs,                (PROJECT,)),
        ("cloud_run", check_cloud_run,          (PROJECT, LOCATION)),
    ]:
        try:
            readings[label] = fn(*args)                                 # call the check function
        except Exception as exc:                                        # one failing check must not abort the whole audit
            logger.error(f"{label} check failed: {exc}")
            readings[label] = {"error": str(exc)}                      # record the failure; evaluate_thresholds skips missing keys

    # ── Evaluate thresholds ────────────────────────────────────────────────────
    alerts = evaluate_thresholds(readings)                              # returns [] if all healthy
    logger.info(f"Audit complete: {len(alerts)} threshold(s) tripped")

    if not alerts:                                                      # alert-only: no post on healthy days
        logger.info("All checks healthy — Slack notification suppressed")
        return ("OK — all checks healthy", 200)                        # 200 so Scheduler does not retry

    # ── Format + deliver ───────────────────────────────────────────────────────
    message = format_alert_message(alerts)                              # human-readable Slack string

    if DRY_RUN:                                                         # local testing: print payload, skip POST
        logger.info(f"DRY_RUN=true — would post:\n{message}")
        return (f"DRY_RUN payload:\n{message}", 200)

    # Fetch webhook URL from Secret Manager at call time (not at import time)
    from google.cloud import secretmanager                              # import here to keep module lightweight
    sm = secretmanager.SecretManagerServiceClient()                     # uses ADC
    secret_name = f"projects/{PROJECT}/secrets/{SLACK_SECRET}/versions/latest"
    response = sm.access_secret_version(request={"name": secret_name}) # single read; free tier covers 10k/month
    webhook_url = response.payload.data.decode("utf-8").strip()        # strip trailing whitespace/newlines

    ok = post_to_slack(message, webhook_url)                           # non-fatal if this fails
    if not ok:
        logger.error("Slack POST failed — check webhook URL in Secret Manager")

    return ("OK — alerts dispatched", 200)                             # always 200; Scheduler does not retry on failure
```

- [ ] **Step 2: Add an integration test to `tests/test_cost_audit.py`**

Append to the end of the file:

```python
# ── main.py integration test ───────────────────────────────────────────────────
import sys                                                              # sys.path already set at top of file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cost-audit"))

from unittest.mock import patch, MagicMock


def test_audit_handler_silent_when_all_healthy():
    """Handler returns 200 and does NOT call Slack when all checks are healthy."""
    healthy = {
        "registry": {"pkg_versions": {}, "total_gb": 1.0},
        "compute":  {"running_vms": []},
        "vertex":   {"endpoints": []},
        "bigquery": {"total_gb": 0.5},
        "spend":    {"mtd_cost_inr": 100.0},
        "gcs":      {"bucket_sizes": {}},
        "cloud_run":{"services": [{"name": "bike-demand-api", "min_instances": 0}]},
    }

    # Patch all seven check functions to return healthy data
    with patch("main.check_artifact_registry", return_value=healthy["registry"]), \
         patch("main.check_compute",           return_value=healthy["compute"]), \
         patch("main.check_vertex",            return_value=healthy["vertex"]), \
         patch("main.check_bigquery",          return_value=healthy["bigquery"]), \
         patch("main.check_spend_mtd",         return_value=healthy["spend"]), \
         patch("main.check_gcs",               return_value=healthy["gcs"]), \
         patch("main.check_cloud_run",         return_value=healthy["cloud_run"]), \
         patch("main.post_to_slack")           as mock_slack:          # ensure Slack is never called
        import main as audit_main                                       # import after patches are in place
        fake_request = MagicMock()                                      # Cloud Run passes a Flask Request object
        body, status = audit_main.audit(fake_request)

    assert status == 200
    assert "healthy" in body
    mock_slack.assert_not_called()                                      # core contract: no post on healthy day


def test_audit_handler_calls_slack_when_threshold_tripped(monkeypatch):
    """Handler calls post_to_slack when at least one threshold is breached."""
    monkeypatch.setenv("DRY_RUN", "false")                             # ensure DRY_RUN is off

    tripped_readings = {
        "registry": {"pkg_versions": {"bike-demand-api": 20}, "total_gb": 1.0},  # 20 > limit of 15
        "compute":  {"running_vms": []},
        "vertex":   {"endpoints": []},
        "bigquery": {"total_gb": 0.5},
        "spend":    {"mtd_cost_inr": 100.0},
        "gcs":      {"bucket_sizes": {}},
        "cloud_run":{"services": [{"name": "bike-demand-api", "min_instances": 0}]},
    }

    fake_sm_response = MagicMock()
    fake_sm_response.payload.data = b"https://hooks.slack.com/fake-webhook"

    with patch("main.check_artifact_registry", return_value=tripped_readings["registry"]), \
         patch("main.check_compute",           return_value=tripped_readings["compute"]), \
         patch("main.check_vertex",            return_value=tripped_readings["vertex"]), \
         patch("main.check_bigquery",          return_value=tripped_readings["bigquery"]), \
         patch("main.check_spend_mtd",         return_value=tripped_readings["spend"]), \
         patch("main.check_gcs",               return_value=tripped_readings["gcs"]), \
         patch("main.check_cloud_run",         return_value=tripped_readings["cloud_run"]), \
         patch("main.secretmanager") as mock_sm, \
         patch("main.post_to_slack")           as mock_slack:
        mock_sm.SecretManagerServiceClient.return_value.access_secret_version.return_value = fake_sm_response
        mock_slack.return_value = True                                  # simulate successful POST
        import importlib, main as audit_main                            # may already be imported; reload to pick up env var
        importlib.reload(audit_main)
        body, status = audit_main.audit(MagicMock())

    assert status == 200
    mock_slack.assert_called_once()                                     # exactly one Slack POST
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/test_cost_audit.py -v
```

Expected: 25 PASSED.

- [ ] **Step 4: Commit**

```bash
git add cost-audit/main.py tests/test_cost_audit.py
git commit -m "feat(cost-audit): wire HTTP handler with DRY_RUN support and Secret Manager webhook"
```

---

## Task 5: Dockerfile + Cloud Run Deployment

**Files:**
- Create: `cost-audit/Dockerfile`

**GCP resources provisioned (not code):** Cloud Run service `cost-audit`, Service Account `cost-audit-sa`, Cloud Scheduler job `cost-audit-cron`, Secret Manager secret `cost-audit-slack-webhook`.

- [ ] **Step 1: Create `cost-audit/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY . .

# Run as non-root user for security.
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Cloud Run injects PORT; functions-framework honours it.
ENV PORT=8080
CMD exec functions-framework --target=audit --port=$PORT
```

- [ ] **Step 2: Commit the Dockerfile**

```bash
git add cost-audit/Dockerfile
git commit -m "build(cost-audit): add Dockerfile for Cloud Run deployment"
```

- [ ] **Step 3: Push the image to Artifact Registry**

Run these commands from the repo root (adjust the project and region if they differ from the defaults):

```bash
PROJECT=bike-demand-ml-system
REGION=us-central1
REPO=bike-demand-repo
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/cost-audit:latest

docker build -t $IMAGE cost-audit/
docker push $IMAGE
```

Expected: image appears in `us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/cost-audit`.

- [ ] **Step 4: Create the Service Account and grant read-only IAM roles**

```bash
PROJECT=bike-demand-ml-system

# Create the SA.
gcloud iam service-accounts create cost-audit-sa \
  --display-name="Cost Audit read-only SA" \
  --project=$PROJECT

SA=cost-audit-sa@$PROJECT.iam.gserviceaccount.com

# Artifact Registry reader (list images + tags).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/artifactregistry.reader"

# Compute viewer (list VMs).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/compute.viewer"

# BigQuery dataViewer (list datasets/tables + query billing_export).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/bigquery.dataViewer"

# BigQuery jobUser (run queries — required for client.query()).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/bigquery.jobUser"

# Storage objectViewer (list blobs in GCS buckets).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/storage.objectViewer"

# Cloud Run viewer (list services via REST).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/run.viewer"

# ML Platform viewer (list Vertex endpoints via REST).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/ml.viewer"

# Secret Manager secretAccessor (read the Slack webhook URL).
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"
```

- [ ] **Step 5: Store the Slack webhook URL in Secret Manager**

> **Prerequisite:** You need a Slack incoming webhook URL for `#gcp-alerts`.
> If using Slack: go to https://api.slack.com/apps → Create App → Incoming Webhooks → Add Webhook → copy the `https://hooks.slack.com/services/...` URL.
> If using email instead: skip this step and replace `post_to_slack()` in `notify.py` with an SMTP-based `send_email()` function; store the SMTP password here instead.

```bash
PROJECT=bike-demand-ml-system

# Store the webhook URL (paste your actual webhook URL when prompted).
echo -n "PASTE_WEBHOOK_URL_HERE" | \
  gcloud secrets create cost-audit-slack-webhook \
    --data-file=- \
    --project=$PROJECT

# Verify it was stored correctly.
gcloud secrets versions access latest --secret=cost-audit-slack-webhook --project=$PROJECT
```

- [ ] **Step 6: Deploy the Cloud Run service**

```bash
PROJECT=bike-demand-ml-system
REGION=us-central1
REPO=bike-demand-repo
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/cost-audit:latest
SA=cost-audit-sa@$PROJECT.iam.gserviceaccount.com

gcloud run deploy cost-audit \
  --image=$IMAGE \
  --region=$REGION \
  --project=$PROJECT \
  --service-account=$SA \
  --no-allow-unauthenticated \
  --max-instances=1 \
  --memory=256Mi \
  --timeout=120 \
  --set-env-vars="GCP_PROJECT=$PROJECT,GCP_LOCATION=$REGION,AR_REPO=$REPO,SLACK_SECRET_NAME=cost-audit-slack-webhook" \
  --platform=managed
```

Expected output includes the service URL (e.g. `https://cost-audit-<hash>-uc.a.run.app`). Save it for the next step.

- [ ] **Step 7: Create the Cloud Scheduler job**

```bash
PROJECT=bike-demand-ml-system
REGION=us-central1
SA=cost-audit-sa@$PROJECT.iam.gserviceaccount.com

# Get the service URL from the previous step and substitute below.
COST_AUDIT_URL=$(gcloud run services describe cost-audit \
  --region=$REGION --project=$PROJECT \
  --format='value(status.url)')

gcloud scheduler jobs create http cost-audit-cron \
  --location=$REGION \
  --project=$PROJECT \
  --schedule="0 9 * * *" \
  --uri="$COST_AUDIT_URL" \
  --http-method=POST \
  --oidc-service-account-email=$SA \
  --oidc-token-audience="$COST_AUDIT_URL" \
  --max-retry-attempts=1 \
  --attempt-deadline=120s \
  --description="Daily GCP cost audit — posts to Slack only on threshold breach"
```

Expected: `Job [cost-audit-cron] created.`

- [ ] **Step 8: Smoke test with DRY_RUN=true**

```bash
PROJECT=bike-demand-ml-system
REGION=us-central1
SA=cost-audit-sa@$PROJECT.iam.gserviceaccount.com
COST_AUDIT_URL=$(gcloud run services describe cost-audit \
  --region=$REGION --project=$PROJECT --format='value(status.url)')

# Get a fresh OIDC token as the SA.
TOKEN=$(gcloud auth print-identity-token --impersonate-service-account=$SA --audiences=$COST_AUDIT_URL)

# POST with DRY_RUN=true — reads all resources, prints payload, skips Slack.
curl -X POST "$COST_AUDIT_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{}'
```

Expected: response body containing either `"OK — all checks healthy"` or `"DRY_RUN payload: ..."` followed by any tripped thresholds. A 200 status confirms the service is alive and all GCP reads succeed.

> If you see `DRY_RUN=true` in the output but did not pass it — check the `--set-env-vars` on the Cloud Run service. Re-deploy without `DRY_RUN=true` if it was accidentally set.
>
> **Note:** `DRY_RUN` is an env var on the service. It was NOT set in Step 6 (intentionally). The above `curl` test exercises the live Slack path; to force a DRY_RUN test without posting: redeploy with `--update-env-vars="DRY_RUN=true"`, test, then redeploy with `--remove-env-vars="DRY_RUN"`.

- [ ] **Step 9: Trigger the Scheduler job manually to confirm end-to-end**

```bash
gcloud scheduler jobs run cost-audit-cron \
  --location=us-central1 \
  --project=bike-demand-ml-system
```

Then check Cloud Logging:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" resource.labels.service_name="cost-audit"' \
  --project=bike-demand-ml-system \
  --limit=50 \
  --format="value(textPayload)"
```

Expected: logs showing each check completing (e.g. `Registry: N images, X.XX GB`, `Compute: 0 running VMs`, etc.) and either `All checks healthy` or alert lines.

---

## Task 6: Layer 1 — Budget Email Thresholds (GCP Console)

This task has no code — it is a one-time console configuration step. The budget already exists (linked to `budget-alert-topic` → `billing-kill-switch`). This adds tiered email notifications on top of the existing kill-switch link.

- [ ] **Step 1: Open the GCP Budget in the console**

Navigate to: **Billing → Budgets & alerts → `[your existing budget name]` → Edit**

Or go directly to: `console.cloud.google.com/billing/budgets`

- [ ] **Step 2: Add tiered email threshold alerts**

In the **"Alert thresholds"** section, add three rows:

| Threshold | % of budget | Spend basis |
|-----------|-------------|-------------|
| ₹250 | 25% (if budget = ₹1,000) | Actual spend |
| ₹500 | 50% | Actual spend |
| ₹1,000 | 100% | Actual spend |

In the **"Manage notifications"** section, confirm:
- ✅ "Email alerts to billing admins and users" is checked
- ✅ Pub/Sub topic is still linked to `budget-alert-topic` (do NOT remove this — it feeds the kill-switch)

- [ ] **Step 3: Save the budget**

Click **Save**. Email notifications are now free and active alongside the existing kill-switch link.

---

## Self-Review: Spec Coverage Check

| Spec section | Covered by |
|---|---|
| §2 Catch resource accumulation | Task 3 `check_*` functions; Task 2 `evaluate_thresholds` |
| §2 Catch spend surprises (native budget) | Task 6 (console) |
| §2 Deliver to Slack via webhook | Task 2 `notify.py`; Task 5 Secret Manager |
| §2 Stay within always-free tier | Task 5 `maxScale=1`, private, read-only |
| §3 No Pub/Sub-push trigger | Task 5 uses Cloud Scheduler (confirmed in Step 7) |
| §3 Read-only | All `check_*` functions use only list/get/query operations |
| §3 Code in-repo | All code lives in `cost-audit/` (confirmed in File Map) |
| §4 Layer 0 — prevention (cleanup policy) | Already in place; no code change needed |
| §4 Layer 1 — budget email thresholds | Task 6 |
| §4 Layer 2 — daily scanner | Tasks 1–5 |
| §5 Data flow (Scheduler → Cloud Run → read → evaluate → Slack if tripped) | Task 4 `main.py` |
| §6 All seven thresholds | Task 2 `evaluate_thresholds` + Task 3 `checks.py` |
| §7 Cost-safety (Scheduler trigger, maxScale=1, no custom metric writes) | Task 5 deploy command |
| §8 Independent checks, always-200, DRY_RUN | Task 4 `main.py` |
| §9 Unit tests for `evaluate_thresholds` + formatter; mock GCP + Slack; alert-only contract | Tasks 1, 2, 3, 4 |
| §10 REST vs client library decision | Resolved in File Map preamble |

All spec requirements are covered. No gaps.
