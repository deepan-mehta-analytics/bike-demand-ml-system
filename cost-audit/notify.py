# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                        # HTTP client for the Slack incoming-webhook POST

PAUSE_POLLER = "gcloud scheduler jobs pause gbfs-poller-cron --location=us-central1"  # one command that stops the feed


# ── Plain-English description of one alert ────────────────────────────────────
# Owner (2026-11-27): alerts must be understood right away and say what to do.
# Each alert becomes (what happened, what to do). Slack and the email share it.

def describe_alert(alert: dict) -> tuple:                               # returns (what happened, what to do)
    """Return a plain-language (what happened, what to do) pair for one alert dict."""
    check = alert["check"]                                              # discriminator key that selects the wording
    if check == "registry_versions":                                    # too many stored copies of one image
        return (f"{alert['count']} copies of the `{alert['pkg']}` app image are stored (limit {alert['limit']}).",
                "No action needed: old copies are deleted automatically after 4 days. "
                "Only act if this repeats for more than a week.")
    if check == "registry_size":                                        # image store too big
        return (f"The image store holds {alert['total_gb']:.1f} GB (limit {alert['limit']:.1f} GB), so its storage cost is rising.",
                "Delete old images in Artifact Registry, or check that the automatic cleanup policy is still switched on.")
    if check == "compute_vms":                                          # virtual machines running
        names = ", ".join(alert["vms"])                                 # comma-separated machine names
        return (f"{len(alert['vms'])} virtual machine(s) are running ({names}). They are not part of the normal setup and are billed every hour.",
                "Stop or delete them in Compute Engine unless you started them on purpose.")
    if check == "vertex_endpoints":                                     # paid model endpoints switched on
        return (f"{len(alert['endpoints'])} Vertex AI model endpoint(s) are switched on. They have no free tier and cost money every hour.",
                "Undeploy them in Vertex AI unless you are using them right now.")
    if check == "bigquery_size":                                        # BigQuery storage near the free limit
        return (f"BigQuery storage is {alert['total_gb']:.1f} GB (warning at {alert['limit']:.1f} GB; free up to 10 GB).",
                "Find and delete large tables you no longer need before it passes 10 GB.")
    if check == "gcs_bucket":                                           # one storage bucket too big
        return (f"Storage bucket `{alert['bucket']}` holds {alert['size_gb']:.1f} GB (limit {alert['limit']:.1f} GB).",
                "Delete files you no longer need from that bucket.")
    if check == "cloud_run_unknown":                                    # service nobody approved
        return (f"An unexpected Cloud Run service `{alert['service']}` exists.",
                "If you did not create it, delete it. If you did, add its name to the allowlist in cost-audit/thresholds.py.")
    if check == "cloud_run_always_on":                                  # service kept running 24/7
        return (f"Cloud Run service `{alert['service']}` keeps {alert['min_instances']} copy/copies running all the time, which is billed around the clock.",
                "Set its minimum instances back to 0.")
    if check == "spend_mtd":                                            # monthly spend above warning level
        return (f"This month's Google Cloud spend is ₹{alert['mtd_cost_inr']:.0f}, above the ₹{alert['limit']:.0f} warning level.",
                "Open the Billing report in the Google Cloud console to see which service is costing money.")
    if check == "cloud_run_memory_errors":                              # service crashing on memory
        return (f"`{alert['service']}` ran out of memory {alert['count']} time(s) in the last 24 hours (memory limit hit), so it kept crashing and restarting.",
                "Check its logs for \"Memory limit of\". The app may need smaller models or more memory.")
    if check == "check_failed":                                         # the audit could not check something
        return (f"One of the checks (`{alert['label']}`) could not run: {str(alert['error'])[:200]}. Until it is fixed, that area is not being watched.",
                "Usually a missing permission. Read the error text above and fix the cost-audit service account's access.")
    if check == "gbfs_poller_requests":                                 # feed called too often
        return (f"The live station feed was called {alert['count']} times in 24 hours (normal is 288, limit {alert['limit']}).",
                f"Something is calling it too often. If unsure, pause it with `{PAUSE_POLLER}` and check the scheduler.")
    if check == "gbfs_poller_runtime":                                  # feed running too long
        return (f"The live station feed ran for {alert['billed_seconds']:.0f} seconds in 24 hours (budget {alert['limit']}; normal is about 1150). "
                f"Its longest single run took {alert['longest_seconds']:.0f} seconds.",
                f"It is slowing down and could start costing money. Pause it with `{PAUSE_POLLER}`, then check the gbfs-poller logs.")
    if check == "gbfs_poller_feed_stale":                               # feed stopped producing data
        age = alert["age_minutes"]                                      # None means no recent data at all
        detail = "no data in the last 2 days" if age is None else f"the newest data is {age} min old"
        return (f"The live station feed has stopped: {detail} (limit {alert['limit']} min). The dashboard's GCP Stream tab will show old or no data.",
                "Check the gbfs-poller logs in Cloud Run. If you paused it on purpose, set gbfs_poller_expected_on=False in cost-audit/thresholds.py.")
    return (f"Unknown check {check}: {alert}",                          # defensive fallback for a new alert type without wording
            "Add plain wording for this check in cost-audit/notify.py.")


def _header(alerts: list) -> str:                                       # "1 problem found" / "3 problems found"
    """Return the plain header line with a correctly pluralised count."""
    n = len(alerts)                                                     # number of problems
    return f"Bike demand cloud check: {n} problem{'s' if n != 1 else ''} found"


# ── Slack message ─────────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a single Slack-ready string
    """Format alerts as a plain-language Slack message: header, then each problem with its action."""
    lines = [f"*{_header(alerts)}*"]                                    # bold header (Slack mrkdwn)
    for alert in alerts:                                                # one block per problem
        what, action = describe_alert(alert)                            # plain wording
        lines.append(f"• {what}")                                  # bullet: what happened
        lines.append(f"    _What to do:_ {action}")                     # indented italic action line
    return "\n".join(lines)                                             # Slack renders \n as line breaks


# ── One-line summary for the email alert ──────────────────────────────────────
# The email comes from a Cloud Monitoring log alert, which can only copy text
# out of a single log entry, so the summary must be one line without Slack markup.

def plain_summary(alerts: list) -> str:                                 # numbered, single-line, no markup
    """Return all problems as one plain line: '1) <what> What to do: <action> 2) ...'."""
    parts = []                                                          # one part per problem
    for number, alert in enumerate(alerts, start=1):                    # number problems from 1
        what, action = describe_alert(alert)                            # plain wording
        parts.append(f"{number}) {what} What to do: {action}")          # problem + action
    text = " ".join(parts)                                              # single line
    return text.replace("`", "").replace("*", "").replace("\n", " ")    # strip Slack markup; keep underscores (file/setting names use them)


# ── Slack Delivery ─────────────────────────────────────────────────────────────

def send_alert(message: str, webhook_url: str) -> bool:                 # posts the formatted message to a Slack incoming webhook
    """Post alert message to a Slack incoming webhook. Returns True on success, False otherwise."""
    try:
        resp = requests.post(                                           # Slack incoming webhooks accept a simple JSON body
            webhook_url,                                                # the https://hooks.slack.com/services/... URL from Secret Manager
            json={"text": message},                                     # {"text": ...} is the minimal Slack webhook payload
            timeout=10,                                                 # short timeout — never block the audit on a slow Slack
        )
        return resp.status_code == 200                                  # Slack returns 200 + body "ok" on success
    except Exception:                                                   # network errors, timeouts, malformed URL, etc.
        return False                                                    # failure is logged by caller; never raises here
