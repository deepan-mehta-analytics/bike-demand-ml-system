# -*- coding: utf-8 -*-
# =============================================================================
# pipeline/vertex_trigger.py
# -----------------------------------------------------------------------------
# Cloud Run HTTP endpoint that submits a Vertex AI CustomJob on POST /trigger.
# Deployed as a Cloud Run service using the same bike-demand-training image
# with the default CMD overridden to uvicorn at deploy time.
#
# Cloud Scheduler fires POST /trigger every Sunday 02:00 UTC.
# This handler returns 200 immediately so Cloud Scheduler considers the trigger
# successful before the 30-minute training job finishes.
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
from pathlib import Path                                   # cross-platform path construction

import yaml                                                # gcp_config.yaml parsing
from fastapi import FastAPI                                # HTTP framework for Cloud Run trigger service
from google.cloud import aiplatform_v1                    # low-level Vertex AI client for job creation
from google.protobuf import duration_pb2                   # Duration proto for scheduling timeout

# ── App init ──────────────────────────────────────────────────
app = FastAPI()                                            # FastAPI application instance for Cloud Run


# ── Config loader ─────────────────────────────────────────────
# Inside a function (not module-level) — avoids WindowsPath pickle issues if module is re-imported
# on a different OS. Same pattern used in retrain_job.py and dataflow_job.py (Phase 4 lesson).
def _load_config() -> dict:                                # returns parsed YAML as a Python dict
    """Load gcp_config.yaml — path resolved at call time to avoid module-level OS path issues."""
    config_path = Path(__file__).parent.parent / "config" / "gcp_config.yaml"  # resolve from this file
    with open(config_path, encoding="utf-8") as f:         # utf-8: config has ⚠️/— chars; cp1252 can't decode them
        return yaml.safe_load(f)                           # parse YAML to Python dict


# ── Trigger endpoint ──────────────────────────────────────────
@app.post("/trigger")
def trigger():
    """Receive POST from Cloud Scheduler, submit Vertex AI CustomJob, return 200 immediately."""
    cfg = _load_config()                                   # load config on each request (avoids stale module state)
    va  = cfg["vertex_ai"]                                 # vertex_ai config block shorthand

    # ── Build the CustomJob proto ─────────────────────────────
    # Use the low-level aiplatform_v1 client so we can set scheduling.timeout cleanly.
    # The high-level aiplatform.CustomJob._gca_resource.job_spec.scheduling.timeout.seconds
    # raises AttributeError in protobuf 4.x because unset submessage fields return a
    # read-only default instance — direct .seconds = N assignment is not allowed.
    # Constructing the full proto from scratch avoids this entirely.
    worker_pool_spec = aiplatform_v1.types.WorkerPoolSpec(    # Vertex AI worker pool definition
        machine_spec=aiplatform_v1.types.MachineSpec(         # hardware spec for the training worker
            machine_type=va["machine_type"],                  # e.g. "n1-highmem-2"
        ),
        replica_count=va["replica_count"],                    # 1 — single-machine training, no distribution
        container_spec=aiplatform_v1.types.ContainerSpec(     # container to run on the worker
            image_uri=va["container_image_uri"],              # GAR training image built by CI Job 6
            env=[                                             # environment variables injected at runtime
                aiplatform_v1.types.EnvVar(                   # single env var definition
                    name="DRY_RUN",                           # env var name read by retrain_job.py
                    value="false",                            # production mode — full GCS MLflow logging
                ),
            ],
        ),
    )

    # ⚠️  COST GUARD — DO NOT REMOVE.
    # scheduling.timeout is the Vertex AI server-side hard kill timeout.
    # At n1-highmem-2 rates (~$0.091/hr), 1800s caps the maximum cost at $0.046 per run.
    # Without this, a hung container accrues cost indefinitely until manually cancelled.
    # job.run(timeout=...) is the SDK client-side wait only and is ignored with sync=False.
    scheduling = aiplatform_v1.types.Scheduling(              # server-side scheduling constraints
        timeout=duration_pb2.Duration(                        # hard kill after this many seconds
            seconds=va["job_timeout_seconds"],                # 1800s = 30 min server-side kill
        ),
    )

    custom_job_proto = aiplatform_v1.types.CustomJob(         # full CustomJob proto (not high-level wrapper)
        display_name="bike-demand-retrain",                   # display name visible in GCP console
        job_spec=aiplatform_v1.types.CustomJobSpec(           # job spec with worker + scheduling config
            worker_pool_specs=[worker_pool_spec],             # list of worker pools (one for single-node)
            scheduling=scheduling,                            # server-side timeout for cost capping
        ),
    )

    # ── Submit job via low-level client ───────────────────────
    client = aiplatform_v1.JobServiceClient(                  # low-level REST client for Vertex AI jobs
        client_options={                                      # region-specific API endpoint
            "api_endpoint": f"{va['region']}-aiplatform.googleapis.com",  # e.g. "us-central1-aiplatform.googleapis.com"
        },
    )

    parent = f"projects/{cfg['project_id']}/locations/{va['region']}"  # resource parent path for job creation
    response = client.create_custom_job(                      # submit the CustomJob to Vertex AI
        parent=parent,                                        # project + location path
        custom_job=custom_job_proto,                          # full proto with scheduling timeout set
    )

    return {                                                   # response body confirms successful submission
        "status": "submitted",                                # Cloud Scheduler treats any 2xx as success
        "job": response.display_name,                         # job display name for logging and debugging
        "timeout_seconds": va["job_timeout_seconds"],         # confirm cost guard is active in response
    }


# ── Health check endpoint ─────────────────────────────────────
@app.get("/health")
def health():
    """Health check endpoint for Cloud Run container readiness and liveness probes."""
    return {"status": "ok"}                                   # simple liveness response — no dependencies checked
