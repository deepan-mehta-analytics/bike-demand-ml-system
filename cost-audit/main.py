# ── Imports ───────────────────────────────────────────────────────────────────
import os                                                               # environment variable access for config
import logging                                                          # structured logging to stdout (Cloud Logging reads it)
import functions_framework                                              # HTTP handler decorator for Cloud Run deployment

from checks import (                                                    # all seven independent resource-reading functions
    check_artifact_registry,
    check_compute,
    check_vertex,
    check_bigquery,
    check_spend_mtd,
    check_gcs,
    check_cloud_run,
)
from thresholds import evaluate_thresholds                              # pure threshold evaluation — no GCP calls
from notify import format_alert_message, post_to_slack                  # message formatting + Slack delivery

# ── Configuration ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)                                # emit INFO+ to stdout so Cloud Logging picks it up
logger = logging.getLogger(__name__)                                    # module-level logger; name helps filter in Cloud Logging

PROJECT = os.environ.get("GCP_PROJECT", "bike-demand-ml-system")       # GCP project ID; overridable for testing
LOCATION = os.environ.get("GCP_LOCATION", "us-central1")              # GCP region; Cloud Run and Vertex are both us-central1
AR_REPO = os.environ.get("AR_REPO", "bike-demand-repo")                # Artifact Registry repo name
SLACK_SECRET = os.environ.get("SLACK_SECRET_NAME", "cost-audit-slack-webhook")  # Secret Manager secret that holds the webhook URL
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"             # when true: log payload and return, skip Slack POST


# ── HTTP Handler ──────────────────────────────────────────────────────────────

@functions_framework.http                                               # registers audit() as the HTTP entry point for Cloud Run
def audit(request):
    """Daily cost audit handler. Invoked by Cloud Scheduler once per day.

    Runs all resource checks, evaluates against thresholds, and posts to Slack
    only if at least one threshold is breached. Always returns HTTP 200 so
    Cloud Scheduler does not retry on application-level outcomes.
    """
    logger.info("Cost audit starting")                                  # log the start so Cloud Logging captures execution time

    readings = {}                                                       # accumulate results from each independent check

    # ── Run all checks independently ─────────────────────────────────────────
    for label, fn, args in [                                            # iterate check definitions as (label, function, args tuple)
        ("registry",   check_artifact_registry, (PROJECT, LOCATION, AR_REPO)),
        ("compute",    check_compute,            (PROJECT,)),
        ("vertex",     check_vertex,             (PROJECT, LOCATION)),
        ("bigquery",   check_bigquery,           (PROJECT,)),
        ("spend",      check_spend_mtd,          (PROJECT,)),
        ("gcs",        check_gcs,                (PROJECT,)),
        ("cloud_run",  check_cloud_run,          (PROJECT, LOCATION)),
    ]:
        try:
            readings[label] = fn(*args)                                 # call the check function with its arguments
        except Exception as exc:                                        # one failing check must NOT abort the whole audit
            logger.error(f"{label} check failed: {exc}")               # log failure with the label for filtering in Cloud Logging
            readings[label] = {"error": str(exc)}                      # store the error; evaluate_thresholds skips missing keys

    # ── Evaluate thresholds ────────────────────────────────────────────────────
    alerts = evaluate_thresholds(readings)                              # returns [] if all checks are within thresholds
    logger.info(f"Audit complete: {len(alerts)} threshold(s) tripped") # log outcome; count is the key signal

    if not alerts:                                                      # alert-only contract: silent on healthy days
        logger.info("All checks healthy — Slack notification suppressed")
        return ("OK — all checks healthy", 200)                        # 200 so Scheduler marks the job successful

    # ── Format + deliver ───────────────────────────────────────────────────────
    message = format_alert_message(alerts)                              # convert alert dicts to a Slack-ready string

    if DRY_RUN:                                                         # DRY_RUN=true: log payload, skip Slack POST
        logger.info(f"DRY_RUN=true — would post:\n{message}")          # full payload visible in Cloud Logging for inspection
        return (f"DRY_RUN payload:\n{message}", 200)                   # 200 so Scheduler does not retry

    # ── Fetch bot token from Secret Manager ──────────────────────────────────
    from google.cloud import secretmanager                              # imported here to keep module load lightweight
    sm = secretmanager.SecretManagerServiceClient()                     # uses ADC automatically — SA must have secretAccessor role
    secret_name = f"projects/{PROJECT}/secrets/{SLACK_SECRET}/versions/latest"
    response = sm.access_secret_version(request={"name": secret_name}) # single read; well within 10k/month free tier
    bot_token = response.payload.data.decode("utf-8").strip()          # strip trailing whitespace/newlines from the xoxb-... token

    ok = post_to_slack(message, bot_token)                             # POST to #gcp-alerts via chat.postMessage; non-fatal on failure
    if not ok:
        logger.error("Slack POST failed — check bot token in Secret Manager")  # log for debugging; do not raise

    return ("OK — alerts dispatched", 200)                             # always 200; Scheduler must not retry on delivery failure
