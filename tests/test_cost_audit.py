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
