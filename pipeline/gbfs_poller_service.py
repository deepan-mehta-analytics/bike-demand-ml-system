# =============================================================================
# pipeline/gbfs_poller_service.py
# -----------------------------------------------------------------------------
# Cloud Run service that polls GBFS endpoints every 5 minutes (triggered by
# Cloud Scheduler) and writes aggregated 5-min window snapshots to BigQuery.
#
# Replaces the paused Dataflow streaming path with a free-tier-safe Cloud Run
# + Scheduler + BQ load-job architecture. See spec:
# bike-demand-prediction/docs/superpowers/specs/2026-05-24-dashboard-truth-and-freshness-design.md
#
# Deploy command:
#   gcloud run deploy gbfs-poller \
#     --image us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/gbfs-poller:latest \
#     --region us-central1 \
#     --no-allow-unauthenticated \
#     --service-account gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com \
#     --max-instances 1 --memory 256Mi --cpu 1 --timeout 540
# =============================================================================

# ── Imports ───────────────────────────────────────────────────
import json                                                    # structured log payload serialisation
import logging                                                 # stdlib logger; Cloud Run captures stdout to Cloud Logging
import os                                                      # env var access for DRY_RUN flag
import time                                                    # sleep between poll iterations (60s × 4)
from datetime import datetime, timedelta, timezone             # window boundary computation
from typing import Any                                         # type hints for accumulator records

from fastapi import FastAPI                                    # HTTP framework for Cloud Run service
from google.cloud import bigquery                              # BigQuery client for load_table_from_json (free batch loads)

from pipeline.gbfs_to_pubsub import poll_once, _load_config    # reused unchanged from existing module
from pipeline.window_agg import aggregate_window               # pure-Python aggregator from Task 2

# ── Logger Setup ──────────────────────────────────────────────
class _JsonFormatter(logging.Formatter):                       # one-line JSON per log record for Cloud Logging
    def format(self, record: logging.LogRecord) -> str:        # override to emit JSON
        try:                                                    # try to parse message as a pre-serialised JSON dict
            payload = json.loads(record.getMessage())          # structured log path
        except (json.JSONDecodeError, TypeError):              # plain-text message → wrap in dict
            payload = {"message": record.getMessage()}         # fallback shape for unstructured logs
        payload["severity"] = record.levelname                 # Cloud Logging severity field
        payload["logger"]   = record.name                      # logger name for filtering
        return json.dumps(payload)                              # emit as single-line JSON

_handler = logging.StreamHandler()                             # write to stdout (captured by Cloud Run)
_handler.setFormatter(_JsonFormatter())                        # attach JSON formatter
logger = logging.getLogger(__name__)                           # module-level logger
logger.addHandler(_handler)                                    # register JSON handler
logger.propagate = False                                       # prevent duplicate output via root logger
logger.setLevel(logging.INFO)                                  # capture INFO and above

# ── App init ──────────────────────────────────────────────────
app = FastAPI(                                                 # FastAPI application instance
    title="GBFS Poller Service",                               # shown in /docs (not enabled by default)
    description="Cloud Run service: 5-min window GBFS → BigQuery",
)

# ── Window math constants ─────────────────────────────────────
WINDOW_SECONDS    = 300                                        # 5-minute window per spec § 4.4
POLL_ITERATIONS   = 5                                          # poll 5 times per window to compute meaningful min/max
POLL_INTERVAL_SEC = 60                                         # 60s between poll iterations (5 × 60 = 300s window)

# ── BQ table reference ────────────────────────────────────────
BQ_TABLE = "bike-demand-ml-system.bike_demand.station_snapshots"  # fully qualified table for load_table_from_json

# ── BQ schema (mirrors dataflow_job.BQ_SCHEMA) ────────────────
# Used as the schema arg to LoadJobConfig so load_table_from_json knows
# how to type the columns. Order does not matter for JSON loads.
BQ_SCHEMA: list[bigquery.SchemaField] = [
    bigquery.SchemaField("city",                "STRING",    mode="REQUIRED"),  # city slug
    bigquery.SchemaField("station_id",          "STRING",    mode="REQUIRED"),  # station identifier
    bigquery.SchemaField("station_name",        "STRING",    mode="NULLABLE"),  # human-readable name
    bigquery.SchemaField("window_start",        "TIMESTAMP", mode="REQUIRED"),  # 5-min window start UTC
    bigquery.SchemaField("window_end",          "TIMESTAMP", mode="REQUIRED"),  # 5-min window end UTC
    bigquery.SchemaField("avg_bikes_available", "FLOAT",     mode="NULLABLE"),  # mean bikes in window
    bigquery.SchemaField("min_bikes_available", "INTEGER",   mode="NULLABLE"),  # min bikes in window
    bigquery.SchemaField("max_bikes_available", "INTEGER",   mode="NULLABLE"),  # max bikes in window
    bigquery.SchemaField("total_snapshots",     "INTEGER",   mode="NULLABLE"),  # snapshot count in window
]

# ── Helpers ───────────────────────────────────────────────────
def _floor_to_window(now: datetime) -> datetime:               # round down to nearest 5-min boundary
    """Return the start of the 5-min window containing `now`."""
    minute = (now.minute // 5) * 5                             # 0, 5, 10, ..., 55
    return now.replace(minute=minute, second=0, microsecond=0) # zero out seconds/microseconds for clean boundary

# ── Health endpoint ───────────────────────────────────────────
@app.get("/health")
def health():
    """Liveness probe — no dependencies checked beyond process responsiveness."""
    return {"status": "ok"}                                    # 200 OK with minimal body

# ── Poll endpoint ─────────────────────────────────────────────
@app.post("/poll")
def poll():
    """Triggered by Cloud Scheduler every 5 min via OIDC-authenticated POST.

    Polls all configured GBFS cities 5 times (60s apart), aggregates into a
    single 5-min window per (city, station), and writes the result to BigQuery
    via a free batch load job. DRY_RUN=true skips the BQ write and returns
    the row count + sample for local/integration testing.
    """
    cfg          = _load_config()                              # GBFS endpoints + cities loaded at request time
    dry_run      = os.getenv("DRY_RUN", "false").lower() == "true"  # toggle for local tests + first-deploy verification
    window_start = _floor_to_window(datetime.now(timezone.utc))     # 5-min boundary on the UTC clock
    window_end   = window_start + timedelta(seconds=WINDOW_SECONDS) # window end = start + 5 min

    logger.info(json.dumps({                                   # structured start log
        "event":        "poll_start",
        "window_start": window_start.isoformat(),
        "window_end":   window_end.isoformat(),
        "dry_run":      dry_run,
        "iterations":   POLL_ITERATIONS,
    }))

    # ── Collect all snapshots across iterations ────────────────
    all_records: list[dict[str, Any]] = []                     # flat list of every snapshot from every iteration

    for i in range(POLL_ITERATIONS):                           # 5 iterations per window
        try:                                                    # poll_once already swallows per-city HTTP errors
            results = poll_once(cfg)                           # {city: [records]} for this iteration
            for city_records in results.values():              # flatten across cities into one list
                all_records.extend(city_records)               # append every record
        except Exception as exc:                               # defensive: anything poll_once doesn't catch
            logger.warning(json.dumps({                        # log and continue — next iteration may succeed
                "event":     "iteration_error",
                "iteration": i,
                "error":     str(exc),
            }))
        if i < POLL_ITERATIONS - 1:                            # skip sleep after the last iteration
            time.sleep(POLL_INTERVAL_SEC)                      # 60s gap before next poll

    # ── Aggregate into BQ rows ─────────────────────────────────
    rows = aggregate_window(all_records, window_start, window_end)  # pure function from Task 2

    logger.info(json.dumps({                                   # mid-cycle log: how many rows aggregated
        "event":        "aggregated",
        "rows":         len(rows),
        "raw_records":  len(all_records),
    }))

    # ── BigQuery write (skipped in DRY_RUN) ────────────────────
    if dry_run:                                                # local/integration test path
        logger.info(json.dumps({                               # log the dry-run skip
            "event":        "dry_run_skip_bq",
            "rows_skipped": len(rows),
        }))
        return {                                                # response shape mirrors real path + dry_run=True
            "status":       "ok",
            "dry_run":      True,
            "rows_written": len(rows),
            "window_start": window_start.isoformat(),
            "window_end":   window_end.isoformat(),
            "sample":       rows[:3],                          # first 3 rows for human inspection
        }

    if not rows:                                               # all polls failed for all cities (extreme edge case)
        logger.warning(json.dumps({                            # log and return early; no BQ load needed
            "event": "empty_window_no_rows",
        }))
        return {
            "status":       "ok",
            "dry_run":      False,
            "rows_written": 0,
            "window_start": window_start.isoformat(),
            "window_end":   window_end.isoformat(),
        }

    # ── Real BQ load path ──────────────────────────────────────
    client    = bigquery.Client()                              # default credentials from Cloud Run runtime SA
    job_config = bigquery.LoadJobConfig(                       # configure schema + append semantics
        schema=BQ_SCHEMA,                                      # explicit schema avoids autodetect inconsistency
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,  # append rows; never overwrite the table
    )
    load_job = client.load_table_from_json(                    # free batch load (vs paid streaming insert)
        json_rows=rows,                                        # in-memory rows; serialised by the client
        destination=BQ_TABLE,                                  # fully qualified table reference
        job_config=job_config,                                 # schema + append config
    )
    load_job.result()                                          # block until load completes (~3-5s)

    job_id_str = str(load_job.job_id)                              # coerce to str; MagicMock-safe in tests, real str in prod

    logger.info(json.dumps({                                   # successful write log
        "event":        "bq_load_complete",
        "rows_written": len(rows),
        "job_id":       job_id_str,
    }))

    return {                                                    # response body for Cloud Scheduler 2xx ack
        "status":       "ok",
        "dry_run":      False,
        "rows_written": len(rows),
        "window_start": window_start.isoformat(),
        "window_end":   window_end.isoformat(),
        "job_id":       job_id_str,                            # included for debuggability
    }
