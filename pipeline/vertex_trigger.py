# -*- coding: utf-8 -*-
# =============================================================================
# pipeline/vertex_trigger.py
# -----------------------------------------------------------------------------
# Cloud Run HTTP endpoint that submits a Vertex AI CustomJob on POST /trigger.
# Deployed as a Cloud Run service using the same bike-demand-training image
# with the default CMD overridden to uvicorn at deploy time.
#
# Cloud Scheduler fires POST /trigger every Sunday 02:00 UTC.
# This handler returns 200 immediately (sync=False) so Cloud Scheduler
# considers the trigger successful before the 30-minute training job finishes.
#
# Deploy command:
#   gcloud run deploy bike-demand-trigger \
#     --image us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/bike-demand-training:latest \
#     --platform managed --region us-central1 \
#     --command uvicorn \
#     --args "pipeline.vertex_trigger:app,--host,0.0.0.0,--port,8080" \
#     --no-allow-unauthenticated \
#     --service-account vertex-sa@bike-demand-ml-system.iam.gserviceaccount.com \
#     --project bike-demand-ml-system
# =============================================================================

# ── Imports ───────────────────────────────────────────────────
from pathlib import Path                          # cross-platform path construction

import yaml                                       # gcp_config.yaml parsing
from fastapi import FastAPI                       # HTTP framework for Cloud Run trigger service
from google.cloud import aiplatform              # Vertex AI SDK for CustomJob submission

# ── App init ──────────────────────────────────────────────────
app = FastAPI()                                   # FastAPI application instance for Cloud Run


# ── Config loader ─────────────────────────────────────────────
# Inside a function (not module-level) — avoids WindowsPath pickle issues if module is re-imported
# on a different OS. Same pattern used in retrain_job.py and dataflow_job.py (Phase 4 lesson).
def _load_config() -> dict:                       # returns parsed YAML as a Python dict
    """Load gcp_config.yaml — path resolved at call time to avoid module-level OS path issues."""
    config_path = Path(__file__).parent.parent / "config" / "gcp_config.yaml"  # resolve from this file
    with open(config_path) as f:                  # open the config file for reading
        return yaml.safe_load(f)                  # parse YAML to Python dict


# ── Trigger endpoint ──────────────────────────────────────────
@app.post("/trigger")
def trigger():
    """Receive POST from Cloud Scheduler, submit Vertex AI CustomJob, return 200 immediately."""
    cfg = _load_config()                          # load config on each request (avoids stale module state)
    va  = cfg["vertex_ai"]                        # vertex_ai config block shorthand

    aiplatform.init(                              # initialise Vertex AI SDK with project credentials
        project=cfg["project_id"],                # GCP project ID from config
        location=va["region"],                    # deployment region e.g. "us-central1"
        staging_bucket=va["staging_bucket"],      # GCS bucket for Vertex AI job staging artifacts
    )

    worker_pool_spec = [{                         # Vertex AI worker pool spec: one machine per job
        "machine_spec": {
            "machine_type": va["machine_type"],   # e.g. "e2-standard-2" — cheapest with enough RAM
        },
        "replica_count": va["replica_count"],     # 1 — single-machine training, no distribution needed
        "container_spec": {
            "image_uri": va["container_image_uri"],  # GAR training image built by CI Job 6
            "env": [
                {"name": "DRY_RUN", "value": "false"},  # production mode — full GCS MLflow logging
            ],
        },
    }]

    job = aiplatform.CustomJob(                   # define the Vertex AI CustomJob
        display_name="bike-demand-retrain",       # display name visible in GCP console
        worker_pool_specs=worker_pool_spec,       # worker configuration defined above
    )

    # ⚠️  COST GUARD — DO NOT REMOVE.
    # job.run(timeout=...) is the SDK *client-side* wait timeout only.
    # With sync=False the function returns immediately so that parameter is silently ignored.
    # Setting scheduling.timeout.seconds on the underlying gca_resource proto is the correct
    # way to tell Vertex AI to auto-cancel the container server-side after this many seconds.
    # At e2-standard-2 rates (~$0.067/hr), 1800s caps the maximum cost at $0.034 per run.
    # Without this line, a hung container accrues cost indefinitely until manually cancelled.
    job._gca_resource.job_spec.scheduling.timeout.seconds = va["job_timeout_seconds"]  # 1800s server-side kill

    job.run(                                      # submit the job to Vertex AI
        sync=False,                               # return immediately; Cloud Scheduler gets 200 now
    )

    return {                                      # response body confirms successful submission
        "status": "submitted",                   # Cloud Scheduler treats any 2xx as success
        "job": job.display_name,                 # job display name for logging and debugging
        "timeout_seconds": va["job_timeout_seconds"],  # confirm cost guard is active in response
    }


# ── Health check endpoint ─────────────────────────────────────
@app.get("/health")
def health():
    """Health check endpoint for Cloud Run container readiness and liveness probes."""
    return {"status": "ok"}                       # simple liveness response — no dependencies checked
