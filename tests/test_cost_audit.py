# ── Imports ───────────────────────────────────────────────────────────────────
import pytest                                                           # test framework
from thresholds import evaluate_thresholds                              # module under test


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture                                                         # pytest manages lifecycle — fresh dict per test call
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
            # NB: only 2 of 5 allowlisted services are present — the unknown-service
            # test checks that unknown names trip an alert, not that known ones are present
        ]},
        "spend": {"mtd_cost_inr": 200.0},
    }


# ── Alert-only contract ────────────────────────────────────────────────────────

def test_healthy_readings_produce_no_alerts(healthy_readings):          # pytest injects the fixture dict
    """Core contract: no alerts when all readings are within thresholds."""
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value passed directly, no call needed
    assert alerts == [], f"Expected no alerts, got: {alerts}"


# ── Registry checks ────────────────────────────────────────────────────────────

def test_registry_version_count_trips_alert(healthy_readings):          # pytest injects the fixture dict
    """Alert fires when a package has more versions than the limit."""
    healthy_readings["registry"]["pkg_versions"]["bike-demand-api"] = 21  # one over the limit of 20
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "registry_versions" for a in alerts)

def test_registry_total_size_trips_alert(healthy_readings):             # pytest injects the fixture dict
    """Alert fires when total repo size exceeds 10 GB."""
    healthy_readings["registry"]["total_gb"] = 15.1                    # just over the 15 GB limit
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "registry_size" for a in alerts)


# ── Compute check ──────────────────────────────────────────────────────────────

def test_running_vm_trips_alert(healthy_readings):                      # pytest injects the fixture dict
    """Alert fires when any VM is running (expected = 0)."""
    healthy_readings["compute"]["running_vms"] = ["instance-leftover"]  # unexpected VM present
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "compute_vms" for a in alerts)


# ── Vertex check ───────────────────────────────────────────────────────────────

def test_vertex_endpoint_trips_alert(healthy_readings):                 # pytest injects the fixture dict
    """Alert fires when any Vertex endpoint is active."""
    healthy_readings["vertex"]["endpoints"] = [{"name": "projects/p/locations/l/endpoints/123"}]
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "vertex_endpoints" for a in alerts)


# ── BigQuery check ─────────────────────────────────────────────────────────────

def test_bigquery_size_trips_alert(healthy_readings):                   # pytest injects the fixture dict
    """Alert fires when total BQ storage exceeds 8 GB."""
    healthy_readings["bigquery"]["total_gb"] = 8.1                     # just over the 8 GB limit
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "bigquery_size" for a in alerts)


# ── GCS check ──────────────────────────────────────────────────────────────────

def test_gcs_bucket_size_trips_alert(healthy_readings):                 # pytest injects the fixture dict
    """Alert fires when any GCS bucket exceeds 25 GB (MLflow artifact accumulation guard)."""
    healthy_readings["gcs"]["bucket_sizes"]["bike-demand-staging"] = 25.1  # just over the 25 GB limit; normal healthy size is ~12 GB
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "gcs_bucket" for a in alerts)


# ── Cloud Run checks ───────────────────────────────────────────────────────────

def test_unknown_cloud_run_service_trips_alert(healthy_readings):       # pytest injects the fixture dict
    """Alert fires for any Cloud Run service not in the allowlist."""
    healthy_readings["cloud_run"]["services"].append({"name": "mystery-service", "min_instances": 0})
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "cloud_run_unknown" for a in alerts)

def test_always_on_cloud_run_service_trips_alert(healthy_readings):     # pytest injects the fixture dict
    """Alert fires when any service has minScale > 0 (always-on cost risk)."""
    healthy_readings["cloud_run"]["services"][0]["min_instances"] = 1   # bike-demand-api set to always-on
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "cloud_run_always_on" for a in alerts)


# ── Spend check ────────────────────────────────────────────────────────────────

def test_spend_mtd_trips_alert(healthy_readings):                       # pytest injects the fixture dict
    """Alert fires when month-to-date spend exceeds ₹500."""
    healthy_readings["spend"]["mtd_cost_inr"] = 501.0                  # just over the ₹500 limit
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "spend_mtd" for a in alerts)


# ── Multiple alerts ────────────────────────────────────────────────────────────

def test_multiple_thresholds_tripped_returns_all_alerts(healthy_readings):  # pytest injects the fixture dict
    """All breached thresholds are reported, not just the first."""
    healthy_readings["compute"]["running_vms"] = ["vm-a"]              # trip compute_vms threshold
    healthy_readings["spend"]["mtd_cost_inr"] = 600.0                  # trip spend_mtd threshold
    alerts = evaluate_thresholds(healthy_readings)                      # evaluate with two breaches present
    for alert in alerts:                                                # verify every alert has minimum required fields
        assert "check" in alert, f"Alert missing 'check' key: {alert}" # check key identifies which threshold tripped
    checks = [a["check"] for a in alerts]                              # collect all check names for assertion
    assert "compute_vms" in checks                                     # compute breach must appear
    assert "spend_mtd" in checks                                       # spend breach must appear


# ── notify.py tests ────────────────────────────────────────────────────────────
from notify import format_alert_message, send_alert                     # formatter and delivery module under test  # noqa: E402
from unittest.mock import patch, MagicMock                              # mock smtplib to avoid real network calls  # noqa: E402


def test_format_alert_message_contains_key_fields():                    # no fixture needed — alert dicts are constructed inline
    """Formatted message includes recognisable content for each alert type."""
    alerts = [
        {"check": "registry_versions", "pkg": "bike-demand-api", "count": 20, "limit": 15},
        {"check": "compute_vms", "vms": ["instance-old"]},
        {"check": "spend_mtd", "mtd_cost_inr": 600.0, "limit": 500.0},
    ]
    msg = format_alert_message(alerts)                                  # call formatter with mixed alert types
    assert "bike-demand-api" in msg                                     # registry package name must appear
    assert "instance-old" in msg                                        # VM name must appear
    assert "600" in msg                                                 # spend amount must appear
    assert "Thresholds Tripped" in msg                                  # header line must appear


def test_send_alert_returns_true_on_success():                          # no fixture needed — only mocks are used
    """send_alert returns True when Slack webhook responds 200."""
    with patch("notify.requests.post") as mock_post:                    # mock the HTTP POST so no real Slack call is made
        mock_post.return_value = MagicMock(status_code=200)             # Slack returns 200 on a successful post
        result = send_alert("test message", "https://hooks.slack.com/services/T/B/x")
    assert result is True                                               # 200 → True


def test_send_alert_returns_false_on_non_200():                         # no fixture needed — only mocks are used
    """send_alert returns False when Slack responds with a non-200 status (e.g. bad webhook)."""
    with patch("notify.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=404)            # invalid/revoked webhook → 404
        result = send_alert("test message", "https://hooks.slack.com/services/bad")
    assert result is False                                              # non-200 → False


def test_send_alert_returns_false_on_network_error():                   # no fixture needed — only mocks are used
    """send_alert returns False (not raises) when the POST raises a network error."""
    with patch("notify.requests.post") as mock_post:
        mock_post.side_effect = OSError("network unreachable")         # simulate connection failure
        result = send_alert("test message", "https://hooks.slack.com/services/T/B/x")
    assert result is False                                              # network error → False, never an exception


# ── checks.py tests ────────────────────────────────────────────────────────────
from checks import (                                                    # all seven check functions under test  # noqa: E402
    check_artifact_registry,
    check_compute,
    check_vertex,
    check_bigquery,
    check_spend_mtd,
    check_gcs,
    check_cloud_run,
)


def test_check_artifact_registry_groups_by_package_and_sums_gb():
    """check_artifact_registry groups images by package name and sums total GB."""
    fake_img_a = MagicMock()                                           # first image — bike-demand-api package
    fake_img_a.name = "projects/p/locations/us-central1/repositories/r/dockerImages/bike-demand-api@sha256:aaa"
    fake_img_a.image_size_bytes = 500_000_000                          # 0.5 GB

    fake_img_b = MagicMock()                                           # second image — same package, different digest
    fake_img_b.name = "projects/p/locations/us-central1/repositories/r/dockerImages/bike-demand-api@sha256:bbb"
    fake_img_b.image_size_bytes = 300_000_000                          # 0.3 GB

    with patch("checks.artifactregistry_v1.ArtifactRegistryClient") as MockClient:
        MockClient.return_value.list_docker_images.return_value = [fake_img_a, fake_img_b]
        result = check_artifact_registry("proj", "us-central1", "bike-demand-repo")

    assert result["pkg_versions"]["bike-demand-api"] == 2              # two images = two versions of the same package
    assert abs(result["total_gb"] - 0.8) < 0.001                      # 0.5 + 0.3 GB


def test_check_compute_returns_running_vm_names():
    """check_compute returns names of VMs in RUNNING state; ignores TERMINATED."""
    fake_running = MagicMock()                                         # a VM that is actively running
    fake_running.name = "stray-vm"
    fake_running.status = "RUNNING"

    fake_stopped = MagicMock()                                         # a VM that is stopped — should NOT appear in results
    fake_stopped.name = "stopped-vm"
    fake_stopped.status = "TERMINATED"

    fake_zone_group = MagicMock()                                      # aggregated list zone group
    fake_zone_group.instances = [fake_running, fake_stopped]           # both VMs in the same zone

    with patch("checks.compute_v1.InstancesClient") as MockClient:
        MockClient.return_value.aggregated_list.return_value = [("zones/us-central1-a", fake_zone_group)]
        result = check_compute("proj")

    assert "stray-vm" in result["running_vms"]                         # running VM must appear
    assert "stopped-vm" not in result["running_vms"]                   # stopped VM must NOT appear


def test_check_compute_skips_empty_zone_groups():
    """check_compute handles zone groups with no instances without crashing."""
    empty_zone_group = MagicMock()                                     # simulate a zone group that has no VMs
    empty_zone_group.instances = []                                    # empty list — the guard `if instances_in_zone.instances` must handle this

    fake_running = MagicMock()                                         # a running VM in a different zone
    fake_running.name = "running-vm"
    fake_running.status = "RUNNING"

    non_empty_group = MagicMock()                                      # a zone group that contains one VM
    non_empty_group.instances = [fake_running]

    with patch("checks.compute_v1.InstancesClient") as MockClient:
        MockClient.return_value.aggregated_list.return_value = [
            ("zones/us-east1-a", empty_zone_group),                    # empty zone — should be skipped cleanly
            ("zones/us-central1-a", non_empty_group),                  # zone with VM — should be counted
        ]
        result = check_compute("proj")

    assert "running-vm" in result["running_vms"]                       # VM from non-empty zone must appear
    assert len(result["running_vms"]) == 1                             # empty zone must not contribute phantom entries


def test_check_vertex_returns_endpoint_list():
    """check_vertex returns endpoint list from Vertex AI REST response."""
    fake_endpoint = {"name": "projects/p/locations/us-central1/endpoints/123", "displayName": "test-ep"}

    with patch("checks.requests.get") as mock_get, \
         patch("checks._get_auth_headers", return_value={"Authorization": "Bearer fake"}):
        mock_resp = MagicMock()                                        # fake requests.Response
        mock_resp.json.return_value = {"endpoints": [fake_endpoint]}   # one endpoint in the response
        mock_resp.raise_for_status = MagicMock()                       # no-op; simulate 200 OK
        mock_get.return_value = mock_resp
        result = check_vertex("proj", "us-central1")

    assert len(result["endpoints"]) == 1                               # one endpoint returned
    assert result["endpoints"][0]["displayName"] == "test-ep"          # endpoint data preserved


def test_check_bigquery_sums_table_bytes():
    """check_bigquery sums num_bytes across all datasets and tables."""
    fake_ds = MagicMock()                                              # fake dataset list item
    fake_ds.dataset_id = "my_dataset"

    fake_tbl_item = MagicMock()                                        # fake table list item
    fake_tbl_item.table_id = "my_table"

    fake_table = MagicMock()                                           # fake full table metadata
    fake_table.num_bytes = 2_000_000_000                               # 2 GB in bytes

    with patch("checks.bigquery.Client") as MockClient:
        mock_bq = MockClient.return_value                              # the client instance
        mock_bq.list_datasets.return_value = [fake_ds]                # one dataset
        mock_bq.list_tables.return_value = [fake_tbl_item]            # one table in the dataset
        mock_bq.get_table.return_value = fake_table                   # table metadata with num_bytes set
        result = check_bigquery("proj")

    assert abs(result["total_gb"] - 2.0) < 0.001                      # 2 GB


def test_check_spend_mtd_returns_cost_from_billing_table():
    """check_spend_mtd returns month-to-date cost in INR from the billing export."""
    fake_row = {"mtd_cost_inr": 312.5}                                 # fake billing query result row

    with patch("checks.bigquery.Client") as MockClient:
        MockClient.return_value.query.return_value.result.return_value = [fake_row]
        result = check_spend_mtd("proj")

    assert result["mtd_cost_inr"] == 312.5                             # cost value passed through unchanged


def test_check_spend_mtd_returns_zero_on_missing_table():
    """check_spend_mtd returns 0.0 when billing table does not exist (graceful)."""
    with patch("checks.bigquery.Client") as MockClient:
        MockClient.return_value.query.side_effect = Exception("Table not found: billing_export")
        result = check_spend_mtd("proj")

    assert result["mtd_cost_inr"] == 0.0                               # graceful zero — no alert fires on absent table


def test_check_gcs_sums_blob_sizes_per_bucket():
    """check_gcs returns per-bucket sizes in GB summed across all blobs."""
    fake_bucket = MagicMock()                                          # fake bucket object
    fake_bucket.name = "bike-demand-staging"

    fake_blob = MagicMock()                                            # a single blob in the bucket
    fake_blob.size = 100_000_000                                       # 0.1 GB

    with patch("checks.storage.Client") as MockClient:
        MockClient.return_value.list_buckets.return_value = [fake_bucket]
        MockClient.return_value.list_blobs.return_value = [fake_blob]
        result = check_gcs("proj")

    assert "bike-demand-staging" in result["bucket_sizes"]             # bucket must appear in results
    assert abs(result["bucket_sizes"]["bike-demand-staging"] - 0.1) < 0.001  # 0.1 GB


def test_check_cloud_run_extracts_name_and_min_instances():
    """check_cloud_run extracts short service names and minInstanceCount values."""
    fake_service = {                                                    # Cloud Run v2 service resource dict
        "name": "projects/proj/locations/us-central1/services/gbfs-poller",
        "scaling": {"minInstanceCount": 0},                            # scale-to-zero = healthy
    }

    with patch("checks.requests.get") as mock_get, \
         patch("checks._get_auth_headers", return_value={"Authorization": "Bearer fake"}):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"services": [fake_service]}    # one service in the response
        mock_resp.raise_for_status = MagicMock()                      # no-op; simulate 200 OK
        mock_get.return_value = mock_resp
        result = check_cloud_run("proj", "us-central1")

    assert result["services"][0]["name"] == "gbfs-poller"              # resource path stripped to short name
    assert result["services"][0]["min_instances"] == 0                 # scale-to-zero confirmed


# ── main.py integration tests ─────────────────────────────────────────────────
import importlib                                                        # used to reload main module after env var changes  # noqa: E402


def _healthy_check_readings():                                          # helper — NOT a pytest fixture, used only in integration tests
    """Return a complete readings dict where every check is within threshold."""
    return {                                                            # mirrors healthy_readings fixture but standalone for main.py tests
        "registry":  {"pkg_versions": {}, "total_gb": 1.0},           # no packages over limit; 1 GB total
        "compute":   {"running_vms": []},                              # no running VMs
        "vertex":    {"endpoints": []},                                 # no Vertex endpoints
        "bigquery":  {"total_gb": 0.5},                                # well under 8 GB limit
        "spend":     {"mtd_cost_inr": 100.0},                          # well under ₹500 limit
        "gcs":       {"bucket_sizes": {}},                             # no buckets over limit
        "cloud_run": {"services": [{"name": "bike-demand-api", "min_instances": 0}]},  # one approved service at scale-to-zero
    }


def test_audit_handler_silent_when_all_healthy():
    """Handler returns 200 and does NOT call Slack when all checks are healthy."""
    healthy = _healthy_check_readings()                                 # all readings within thresholds

    with patch("main.check_artifact_registry", return_value=healthy["registry"]), \
         patch("main.check_compute",           return_value=healthy["compute"]), \
         patch("main.check_vertex",            return_value=healthy["vertex"]), \
         patch("main.check_bigquery",          return_value=healthy["bigquery"]), \
         patch("main.check_spend_mtd",         return_value=healthy["spend"]), \
         patch("main.check_gcs",               return_value=healthy["gcs"]), \
         patch("main.check_cloud_run",         return_value=healthy["cloud_run"]), \
         patch("main.send_alert")           as mock_alert:          # email must never be sent on a healthy day
        import main as audit_main                                       # import after patches are in place
        fake_request = MagicMock()                                      # functions-framework passes a Flask Request object
        body, status = audit_main.audit(fake_request)

    assert status == 200                                                # always 200
    assert "healthy" in body                                            # response body confirms healthy state
    mock_alert.assert_not_called()                                      # core contract: no email on a healthy day


def test_audit_handler_sends_email_when_threshold_tripped(monkeypatch):
    """Handler calls send_alert exactly once when at least one threshold is breached."""
    import sys                                                          # needed to inject a fake secretmanager into sys.modules

    # ORDER MATTERS (1 of 3): setenv must happen BEFORE importlib.reload.
    # main.py reads os.environ["DRY_RUN"] at module load time (not inside audit()).
    # If reload runs first, it captures the old env value and the branch that skips
    # Slack is taken, making mock_slack.assert_called_once() fail.
    monkeypatch.setenv("DRY_RUN", "false")                             # ensure DRY_RUN is not active for this test

    tripped = _healthy_check_readings()                                 # start from healthy baseline
    tripped["registry"]["pkg_versions"]["bike-demand-api"] = 21        # 21 versions > limit of 20 — trips an alert

    fake_sm_response = MagicMock()                                      # fake Secret Manager response
    fake_sm_response.payload.data = b"https://hooks.slack.com/services/T/B/x"  # fake Slack webhook URL bytes stored in the secret

    mock_sm_module = MagicMock()                                        # fake google.cloud.secretmanager module
    mock_sm_module.SecretManagerServiceClient.return_value \
        .access_secret_version.return_value = fake_sm_response         # wire the fake client method to return the fake response

    # ORDER MATTERS (2 of 3): reload happens AFTER setenv so the fresh module
    # sees the correct DRY_RUN value.  It must also happen BEFORE the
    # sys.modules injection below, because reload re-executes the top-level
    # import statements in main.py — any sys.modules entry set before reload
    # may be overwritten by the re-import machinery.
    import main as audit_main                                           # import module reference for reload and patching
    importlib.reload(audit_main)                                        # reload to pick up the monkeypatched DRY_RUN env var

    # ORDER MATTERS (3 of 3): inject the fake secretmanager AFTER reload but
    # BEFORE audit() is called.  audit() contains a local `from google.cloud
    # import secretmanager` — Python resolves that import by checking
    # sys.modules first, so the entry must be present at the moment audit()
    # executes, not at module-load time.  Injecting it before reload would
    # risk the reload overwriting the entry; injecting it after audit() would
    # be too late and the real SDK import (which may fail in CI) would run.
    monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", mock_sm_module)  # intercept the local import

    with patch("main.check_artifact_registry", return_value=tripped["registry"]), \
         patch("main.check_compute",           return_value=tripped["compute"]), \
         patch("main.check_vertex",            return_value=tripped["vertex"]), \
         patch("main.check_bigquery",          return_value=tripped["bigquery"]), \
         patch("main.check_spend_mtd",         return_value=tripped["spend"]), \
         patch("main.check_gcs",               return_value=tripped["gcs"]), \
         patch("main.check_cloud_run",         return_value=tripped["cloud_run"]), \
         patch("main.send_alert")           as mock_alert:          # intercept email delivery
        mock_alert.return_value = True                                  # simulate email accepted
        body, status = audit_main.audit(MagicMock())

    assert status == 200                                                # always 200
    mock_alert.assert_called_once()                                     # exactly one email when a threshold trips
