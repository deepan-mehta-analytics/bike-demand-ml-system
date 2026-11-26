# ── Threshold Configuration ────────────────────────────────────────────────────

THRESHOLDS = {                                                          # single source of truth for all cost-safety limits
    "registry_max_versions_per_pkg": 7,                                 # alert when any package exceeds 7 versions; cleanup policy keeps ≤5 after 4-day window; 7 gives one CI-day buffer
    "registry_max_total_gb": 3.0,                                       # portfolio-mode target: 2 active packages × 5 images × ~250 MB = ~2.5 GB; 3 GB gives CI-day headroom
    "compute_max_running_vms": 0,                                       # alert on ANY running VM (expected = 0 in steady state)
    "vertex_max_endpoints": 0,                                          # alert on ANY Vertex endpoint (no free tier for endpoints)
    "bigquery_max_total_gb": 8.0,                                       # alert at 8 GB (free 10 GB storage)
    "gcs_max_bucket_gb": 5.0,                                           # portfolio mode: MLflow artifacts deleted; only CloudBuild temp files remain (~0 GB); 5 GB catches any unexpected accumulation
    "cloud_run_allowlist": frozenset({                                  # immutable set — prevents accidental runtime mutation
        "bike-demand-api",                                              # inference API (portfolio demo endpoint)
        "billing-kill-switch",                                          # budget protection (europe-west1)
        "cost-audit",                                                   # this monitoring service
    }),
    "spend_mtd_max_inr": 300.0,                                         # portfolio-mode target: ~₹80-120/month expected; 300 gives safe headroom before escalation
    "cloud_run_memory_errors_max": 0,                                   # any "Memory limit ... exceeded" in 24 h = instances are crashing (v4.5.1 lesson)
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

    # ── Cloud Run memory-limit errors ─────────────────────────────────────────
    for service, count in readings.get("cloud_run_errors", {}).get("memory_errors", {}).items():  # per service
        if count > THRESHOLDS["cloud_run_memory_errors_max"]:           # any crash in the window trips
            alerts.append({
                "check": "cloud_run_memory_errors",                     # discriminator key
                "service": service,                                     # which service is crashing
                "count": count,                                         # how many times in the window
                "limit": THRESHOLDS["cloud_run_memory_errors_max"],     # the threshold that was exceeded
            })

    # ── Checks that could not run ─────────────────────────────────────────────
    # main.py stores {"error": ...} when a check raises. Silently skipping it made a
    # broken check look healthy; report it so a missing permission is noticed.
    for label, reading in readings.items():                             # every check's result
        if isinstance(reading, dict) and "error" in reading:            # check raised instead of returning data
            alerts.append({"check": "check_failed", "label": label, "error": reading["error"]})

    return alerts                                                       # empty list = all healthy = no Slack notification
