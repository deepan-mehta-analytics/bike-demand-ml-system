# ── Threshold Configuration ────────────────────────────────────────────────────

THRESHOLDS = {                                                          # single source of truth for all cost-safety limits
    "registry_max_versions_per_pkg": 15,                                # alert when any Docker package exceeds this version count
    "registry_max_total_gb": 10.0,                                      # alert when repo total size exceeds 10 GB
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
