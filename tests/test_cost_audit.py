# ── Imports ───────────────────────────────────────────────────────────────────
import pytest                                                           # test framework
from thresholds import evaluate_thresholds, THRESHOLDS                  # module under test


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
    healthy_readings["registry"]["pkg_versions"]["bike-demand-api"] = 16  # one over the limit of 15
    alerts = evaluate_thresholds(healthy_readings)                      # fixture value mutated then evaluated
    assert any(a["check"] == "registry_versions" for a in alerts)

def test_registry_total_size_trips_alert(healthy_readings):             # pytest injects the fixture dict
    """Alert fires when total repo size exceeds 10 GB."""
    healthy_readings["registry"]["total_gb"] = 10.1                    # just over the 10 GB limit
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
    """Alert fires when any GCS bucket exceeds 4 GB."""
    healthy_readings["gcs"]["bucket_sizes"]["bike-demand-staging"] = 4.1  # just over the 4 GB limit
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
