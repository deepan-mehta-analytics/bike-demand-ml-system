# ── Threshold Configuration ────────────────────────────────────────────────────

THRESHOLDS = {                                                          # single source of truth for all cost-safety limits
    "registry_max_versions_per_pkg": 15,                                # alert when any Docker package exceeds this version count
    "registry_max_total_gb": 10.0,                                      # alert when repo total size exceeds 10 GB
    "compute_max_running_vms": 0,                                       # alert on ANY running VM (expected = 0 in steady state)
    "vertex_max_endpoints": 0,                                          # alert on ANY Vertex endpoint (no free tier for endpoints)
    "bigquery_max_total_gb": 8.0,                                       # alert at 8 GB (free 10 GB storage)
    "gcs_max_bucket_gb": 25.0,                                          # alert at 25 GB; bike-demand-staging holds MLflow artifacts (~12 GB normal; 21-day lifecycle caps at ~30 GB max; alert fires if lifecycle fails or accumulation runs away
    "cloud_run_allowlist": frozenset({                                  # immutable set — prevents accidental runtime mutation
        "bike-demand-api",                                              # inference API
        "gbfs-poller",                                                  # GBFS station poller
        "bike-demand-trigger",                                          # Vertex AI trigger
        "billing-kill-switch",                                          # budget protection
        "cost-audit",                                                   # this service
    }),
    "spend_mtd_max_inr": 500.0,                                         # alert when month-to-date spend exceeds ₹500
}


# ── Threshold Evaluation ───────────────────────────────────────────────────────

def evaluate_thresholds(readings: dict) -> list:                        # evaluates all resource readings; each check is independent
    """Evaluate resource readings against thresholds. Returns list of alert dicts."""
    alerts = []                                                         # accumulate all tripped thresholds — caller gets the full list

    # ── Registry ──────────────────────────────────────────────────────────────
    registry = readings.get("registry", {})                             # registry readings dict (may be absent if check failed)
    for pkg, count in registry.get("pkg_versions", {}).items():        # check each package's version count independently
        if count > THRESHOLDS["registry_max_versions_per_pkg"]:         # trip when versions exceed limit
            alerts.append({
                "check": "registry_versions",                           # discriminator key used by notify.py and tests
                "pkg": pkg,                                             # package name that is over the limit
                "count": count,                                         # actual version count
                "limit": THRESHOLDS["registry_max_versions_per_pkg"],   # the threshold that was exceeded
            })
    total_gb = registry.get("total_gb", 0.0)                           # total repo size in GB (0.0 if absent)
    if total_gb > THRESHOLDS["registry_max_total_gb"]:                  # trip when repo exceeds 10 GB
        alerts.append({
            "check": "registry_size",                                   # discriminator key
            "total_gb": total_gb,                                       # actual size
            "limit": THRESHOLDS["registry_max_total_gb"],               # the threshold that was exceeded
        })

    # ── Compute ────────────────────────────────────────────────────────────────
    running_vms = readings.get("compute", {}).get("running_vms", [])   # list of running VM names ([] if none or check failed)
    if running_vms:                                                     # any VM = alert (expected = 0 in steady state)
        alerts.append({"check": "compute_vms", "vms": running_vms})    # include VM names for actionability

    # ── Vertex AI ──────────────────────────────────────────────────────────────
    endpoints = readings.get("vertex", {}).get("endpoints", [])         # list of active endpoint dicts
    if endpoints:                                                       # any endpoint = alert (no free tier)
        alerts.append({
            "check": "vertex_endpoints",                                # discriminator key
            "endpoints": [e.get("name", str(e)) for e in endpoints],   # extract names for the alert message
        })

    # ── BigQuery ───────────────────────────────────────────────────────────────
    bq_gb = readings.get("bigquery", {}).get("total_gb", 0.0)          # total BQ storage in GB
    if bq_gb > THRESHOLDS["bigquery_max_total_gb"]:                     # trip at 8 GB (free tier is 10 GB)
        alerts.append({
            "check": "bigquery_size",                                   # discriminator key
            "total_gb": bq_gb,                                          # actual size
            "limit": THRESHOLDS["bigquery_max_total_gb"],               # the threshold that was exceeded
        })

    # ── GCS ────────────────────────────────────────────────────────────────────
    for bucket, size_gb in readings.get("gcs", {}).get("bucket_sizes", {}).items():  # check each bucket independently
        if size_gb > THRESHOLDS["gcs_max_bucket_gb"]:                   # trip at 4 GB per bucket (free total is 5 GB)
            alerts.append({
                "check": "gcs_bucket",                                  # discriminator key
                "bucket": bucket,                                       # bucket name for actionability
                "size_gb": size_gb,                                     # actual size
                "limit": THRESHOLDS["gcs_max_bucket_gb"],               # the threshold that was exceeded
            })

    # ── Cloud Run ──────────────────────────────────────────────────────────────
    allowlist = THRESHOLDS["cloud_run_allowlist"]                       # set of approved service names
    for svc in readings.get("cloud_run", {}).get("services", []):       # check each service independently
        name = svc.get("name", "<unknown>")                                    # guard against malformed service dicts from the API
        if name not in allowlist:                                       # unknown service = potential rogue spend
            alerts.append({"check": "cloud_run_unknown", "service": name})  # include name for actionability
        if svc.get("min_instances", 0) > 0:                            # minScale > 0 means always-on = paid
            alerts.append({
                "check": "cloud_run_always_on",                         # discriminator key
                "service": name,                                        # service name for actionability
                "min_instances": svc["min_instances"],                  # actual minScale value
            })

    # ── Spend ──────────────────────────────────────────────────────────────────
    mtd = readings.get("spend", {}).get("mtd_cost_inr", 0.0)           # month-to-date spend in INR (0.0 if check failed)
    if mtd > THRESHOLDS["spend_mtd_max_inr"]:                          # trip at ₹500 MTD
        alerts.append({
            "check": "spend_mtd",                                       # discriminator key
            "mtd_cost_inr": mtd,                                        # actual spend
            "limit": THRESHOLDS["spend_mtd_max_inr"],                   # the threshold that was exceeded
        })

    return alerts                                                       # empty list = all healthy = no Slack notification
