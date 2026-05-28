# =============================================================================
# billing-kill-switch/main.py
# -----------------------------------------------------------------------------
# Cloud Run service (functions-framework HTTP target) wired to a Pub/Sub push
# subscription on the budget-alert topic. When a budget notification reports
# cost >= budget, it unlinks the project's billing account (the "kill switch").
#
# Deploy:
#   gcloud run deploy billing-kill-switch --source billing-kill-switch \
#     --region europe-west1 --function stop_billing
#
# Why each request MUST return 2xx: the previous version returned None, so the
# Flask layer raised (HTTP 500) on every call; Pub/Sub never got its ack and
# redelivered forever (a billable retry storm). Always returning 204 acks the
# message and stops redelivery.
# =============================================================================

# ── Imports ───────────────────────────────────────────────────
import base64                                            # decode the base64 Pub/Sub payload
import json                                              # parse the budget-notification JSON
import google.auth                                       # Application Default Credentials + project resolution
from googleapiclient import discovery                    # build the Cloud Billing API client


# ── HTTP entry point ──────────────────────────────────────────
def stop_billing(request):                               # functions-framework HTTP signature: receives a Flask request
    """Disable project billing when a budget alert reports cost >= budget.

    Always returns a 2xx so Pub/Sub acks the push message (no redelivery loop).
    """
    # ── Parse the Pub/Sub push envelope: {"message": {"data": "<base64>"}} ──
    envelope = request.get_json(silent=True) or {}       # push body as JSON; silent=True → None instead of raising
    data_b64 = envelope.get("message", {}).get("data", "")  # base64-encoded budget notification, or "" if absent
    try:                                                 # a malformed message must never crash → would loop
        budget = json.loads(base64.b64decode(data_b64).decode("utf-8")) if data_b64 else {}  # decode → JSON dict
    except Exception as exc:                             # any decode/parse failure
        print(f"Unparseable budget message: {exc}")      # log for debugging
        return ("", 204)                                 # ack the bad message so Pub/Sub drops it

    cost  = budget.get("costAmount", 0)                  # current spend reported by the budget alert
    limit = budget.get("budgetAmount", 0)                # the configured budget amount
    print(f"Budget alert: cost={cost} limit={limit}")    # structured-enough log line for Cloud Logging

    # ── Only act when actually at/over budget (ignore 50% / 90% alerts) ──
    if not limit or cost < limit:                        # no limit, or sub-threshold alert
        return ("", 204)                                 # ack and keep billing ON

    # ── Resolve the project from ADC (Cloud Run does NOT set GCP_PROJECT) ──
    credentials, project_id = google.auth.default()      # second return value is the active project id
    project_name = f"projects/{project_id}"              # Cloud Billing API resource name
    billing = discovery.build("cloudbilling", "v1", credentials=credentials)  # build the API client

    info = billing.projects().getBillingInfo(name=project_name).execute()  # read current billing state
    if not info.get("billingEnabled"):                   # already unlinked → nothing to do
        print(f"Billing already disabled for {project_id}")  # log no-op
        return ("", 204)                                 # ack

    # ── The kill switch: unlink the billing account ──────────────
    billing.projects().updateBillingInfo(                # PATCH billing info
        name=project_name,                               # target project
        body={"billingAccountName": ""},                 # empty account name = unlink = billing OFF
    ).execute()                                          # execute the disable call
    print(f"DISABLED billing for {project_id} (cost {cost} >= limit {limit})")  # audit log
    return ("", 204)                                     # ack the message
