# =============================================================================
# billing-kill-switch/main.py
# -----------------------------------------------------------------------------
# Cloud Run service (functions-framework HTTP target) wired to a Pub/Sub push
# subscription on the budget-alert topic. When a budget notification reports
# cost >= budget, it unlinks the billing account from EVERY project attached
# to that billing account — protecting any current or future GCP repo.
#
# Deploy:
#   gcloud run deploy billing-kill-switch --source billing-kill-switch \
#     --region europe-west1 --function stop_billing
#
# Required env var:
#   BILLING_ACCOUNT_ID — the billing account ID (e.g. 015DB7-CE9C3D-2F5093)
#   Set via: gcloud run services update billing-kill-switch \
#     --update-env-vars BILLING_ACCOUNT_ID=015DB7-CE9C3D-2F5093 --region europe-west1
#
# Required IAM on the billing account (for the Compute Engine default SA):
#   roles/billing.viewer         — list all projects on the billing account
#   roles/billing.projectManager — call updateBillingInfo to unlink each project
#
# Why each request MUST return 2xx: the previous version returned None, so the
# Flask layer raised (HTTP 500) on every call; Pub/Sub never got its ack and
# redelivered forever (a billable retry storm). Always returning 204 acks the
# message and stops redelivery.
# =============================================================================

# ── Imports ────────────────────────────────────────────────────────────────
import base64                                                  # decode the base64 Pub/Sub payload
import json                                                    # parse the budget-notification JSON
import os                                                      # read BILLING_ACCOUNT_ID env var
import google.auth                                             # Application Default Credentials
from googleapiclient import discovery                          # build the Cloud Billing API client


# ── HTTP entry point ────────────────────────────────────────────────────────
def stop_billing(request):                                     # functions-framework HTTP signature
    """Disable billing for ALL projects on the billing account when cost >= budget.

    Enumerates every project linked to BILLING_ACCOUNT_ID and unlinks each one,
    so any future GCP project on the same billing account is automatically covered.
    Always returns 2xx so Pub/Sub acks the message (no redelivery loop).
    """

    # ── Parse the Pub/Sub push envelope: {"message": {"data": "<base64>"}} ──
    envelope = request.get_json(silent=True) or {}             # push body as JSON; silent=True avoids raising
    data_b64 = envelope.get("message", {}).get("data", "")    # base64-encoded budget notification, or ""
    try:                                                       # malformed message must never crash → would loop
        budget = json.loads(base64.b64decode(data_b64).decode("utf-8")) if data_b64 else {}  # decode → dict
    except Exception as exc:                                   # any decode/parse failure
        print(f"Unparseable budget message: {exc}")            # log for debugging
        return ("", 204)                                       # ack the bad message so Pub/Sub drops it

    cost  = budget.get("costAmount", 0)                        # current spend reported by the budget alert
    limit = budget.get("budgetAmount", 0)                      # the configured budget ceiling
    print(f"Budget alert: cost={cost} limit={limit}")          # structured log line for Cloud Logging

    # ── Only act when actually at/over budget (ignore 50% / 90% threshold alerts) ──
    if not limit or cost < limit:                              # sub-threshold alert or no limit configured
        return ("", 204)                                       # ack and keep billing ON

    # ── Validate the billing account env var is set ────────────────────────
    billing_account_id = os.environ.get("BILLING_ACCOUNT_ID", "").strip()  # e.g. "015DB7-CE9C3D-2F5093"
    if not billing_account_id:                                 # missing env var = cannot enumerate projects
        print("ERROR: BILLING_ACCOUNT_ID env var not set — cannot enumerate projects to disable")
        return ("", 204)                                       # ack so Pub/Sub doesn't retry forever

    billing_account_name = f"billingAccounts/{billing_account_id}"  # Cloud Billing API resource name format

    # ── Build the Cloud Billing API client ─────────────────────────────────
    credentials, _ = google.auth.default()                     # ADC — Cloud Run injects the SA credentials
    billing = discovery.build("cloudbilling", "v1", credentials=credentials)  # build the API client

    # ── DRY_RUN guard — must be checked before any updateBillingInfo call ──
    dry_run = os.environ.get("DRY_RUN", "false").strip().lower() == "true"  # only exact "true" activates
    if dry_run:                                                # log clearly so Cloud Logging shows it
        print("DRY_RUN=true: will list projects and log what would be unlinked — no billing changes")

    # ── Enumerate every project on the billing account (handles pagination) ─
    disabled = []                                              # collect names of projects we act on
    page_token = None                                          # start with no pagination token
    while True:                                                # loop until all pages are consumed
        kwargs = {"name": billing_account_name}                # base request params
        if page_token:                                         # add token only when paginating
            kwargs["pageToken"] = page_token
        try:                                                   # list call can fail if API disabled or IAM missing
            response = billing.billingAccounts().projects().list(**kwargs).execute()  # list projects
        except Exception as exc:                               # any API or network failure
            print(f"ERROR listing projects on {billing_account_name}: {exc}")  # log for diagnosis
            return ("", 204)                                   # ack so Pub/Sub doesn't retry forever

        for project in response.get("projectBillingInfo", []):  # iterate projects on this page
            if not project.get("billingEnabled"):              # already unlinked — skip
                continue
            project_name = project["name"]                     # "projects/<project-id>" resource name
            if dry_run:                                        # DRY_RUN: log intent, skip the actual call
                print(f"DRY_RUN: would disable billing for {project_name}")
                disabled.append(project_name)                  # still record so the summary is useful
            else:                                              # live mode: unlink billing for real
                billing.projects().updateBillingInfo(          # PATCH billing info for this project
                    name=project_name,                         # target project resource name
                    body={"billingAccountName": ""},           # empty string = unlink = billing OFF
                ).execute()                                    # execute the disable call
                disabled.append(project_name)                  # record for the audit log

        page_token = response.get("nextPageToken")             # None when this is the last page
        if not page_token:                                     # no more pages — exit loop
            break

    # ── Audit log: one line summarising the full kill-switch action ─────────
    mode = "DRY_RUN" if dry_run else "LIVE"                   # label so log lines are unambiguous
    print(
        f"[{mode}] Kill switch fired: cost={cost} >= limit={limit}. "
        f"{'Would disable' if dry_run else 'Disabled'} billing for "
        f"{len(disabled)} project(s): {disabled}"
    )
    return ("", 204)                                           # ack the Pub/Sub message
