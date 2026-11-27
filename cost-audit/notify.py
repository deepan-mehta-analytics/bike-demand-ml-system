# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                        # HTTP client for the Slack incoming-webhook POST

PAUSE_POLLER = "gcloud scheduler jobs pause gbfs-poller-cron --location=us-central1"  # one command that stops the feed
URGENCY_ORDER = ["Act now", "Check soon", "Can wait"]                   # most → least urgent; drives the headline tag
TAG_LEGEND = ("Act now = may cost money or break the app today · "
              "Check soon = look within a day or two · "
              "Can wait = usually fixes itself")                        # one-line explanation of the tags
SUMMARY_LIMIT = 950                                                     # Google copies at most ~1,000 characters of a log label into the email
MORE_IN_SLACK = "(full list in Slack #cost-alerts)"                     # appended when the email summary is cut short


# ── Plain-English description of one alert ────────────────────────────────────
# Owner (2026-11-27): alerts must be understood right away, say why they matter
# and what to do. Slack and the email share this wording.

def _alert(urgency: str, what: str, why: str, action: str) -> dict:     # small constructor keeps the branches readable
    """Bundle the four parts of a plain-language alert."""
    return {"urgency": urgency, "what": what, "why": why, "action": action}


def describe_alert(alert: dict) -> dict:                                # returns {"urgency", "what", "why", "action"}
    """Return the urgency tag, what happened, why it matters and what to do for one alert dict."""
    check = alert["check"]                                              # discriminator key that selects the wording
    if check == "registry_versions":                                    # too many stored copies of one image
        return _alert("Can wait",
                      f"{alert['count']} copies of the `{alert['pkg']}` app image are stored (limit {alert['limit']}).",
                      "Each stored copy uses paid storage, a few rupees a month.",
                      "No action needed: old copies are deleted automatically after 4 days. "
                      "Only act if this repeats for more than a week.")
    if check == "registry_size":                                        # image store too big
        return _alert("Check soon",
                      f"The image store holds {alert['total_gb']:.1f} GB (limit {alert['limit']:.1f} GB).",
                      "Storage above 0.5 GB is billed every month and grows with each deploy.",
                      "Delete old images in Artifact Registry, or check that the automatic cleanup policy is still switched on.")
    if check == "compute_vms":                                          # virtual machines running
        names = ", ".join(alert["vms"])                                 # comma-separated machine names
        return _alert("Act now",
                      f"{len(alert['vms'])} virtual machine(s) are running ({names}). They are not part of the normal setup.",
                      "A running virtual machine is billed every hour and can cost hundreds of rupees a month.",
                      "Stop or delete them in Compute Engine unless you started them on purpose.")
    if check == "vertex_endpoints":                                     # paid model endpoints switched on
        return _alert("Act now",
                      f"{len(alert['endpoints'])} Vertex AI model endpoint(s) are switched on.",
                      "Endpoints have no free tier and are billed every hour they are on, even with no traffic.",
                      "Undeploy them in Vertex AI unless you are using them right now.")
    if check == "bigquery_size":                                        # BigQuery storage near the free limit
        return _alert("Check soon",
                      f"BigQuery storage is {alert['total_gb']:.1f} GB (warning at {alert['limit']:.1f} GB).",
                      "Storage above 10 GB is billed every month.",
                      "Find and delete large tables you no longer need before it passes 10 GB.")
    if check == "gcs_bucket":                                           # one storage bucket too big
        return _alert("Check soon",
                      f"Storage bucket `{alert['bucket']}` holds {alert['size_gb']:.1f} GB (limit {alert['limit']:.1f} GB).",
                      "Bucket storage above 5 GB is billed every month.",
                      "Delete files you no longer need from that bucket.")
    if check == "cloud_run_unknown":                                    # service nobody approved
        return _alert("Act now",
                      f"An unexpected Cloud Run service `{alert['service']}` exists.",
                      "An unknown service may be a mistaken deploy that runs up costs or exposes data.",
                      "If you did not create it, delete it. If you did, add its name to the allowlist in cost-audit/thresholds.py.")
    if check == "cloud_run_always_on":                                  # service kept running 24/7
        return _alert("Act now",
                      f"Cloud Run service `{alert['service']}` keeps {alert['min_instances']} copy/copies running all the time.",
                      "An always-on copy is billed every second, day and night.",
                      "Set its minimum instances back to 0.")
    if check == "spend_mtd":                                            # monthly spend above warning level
        return _alert("Act now",
                      f"This month's Google Cloud spend is ₹{alert['mtd_cost_inr']:.0f}, above the ₹{alert['limit']:.0f} warning level.",
                      "Normal spend for this project is about ₹80–120 a month, so something is costing more than usual.",
                      "Open the Billing report in the Google Cloud console to see which service is costing money.")
    if check == "cloud_run_memory_errors":                              # service crashing on memory
        return _alert("Act now",
                      f"`{alert['service']}` ran out of memory {alert['count']} time(s) in the last 24 hours (memory limit hit).",
                      "While it keeps crashing and restarting, dashboard predictions fail or are very slow.",
                      "Check its logs for \"Memory limit of\". The app may need smaller models or more memory.")
    if check == "check_failed":                                         # the audit could not check something
        return _alert("Check soon",
                      f"One of the checks (`{alert['label']}`) could not run: {str(alert['error'])[:160]}.",
                      "That area is not being watched, so a problem there would go unnoticed.",
                      "Usually a missing permission. Read the error text and fix the cost-audit service account's access.")
    if check == "gbfs_poller_requests":                                 # feed called too often
        return _alert("Act now",
                      f"The live station feed was called {alert['count']} times in 24 hours (normal is 288, limit {alert['limit']}).",
                      "Extra calls add running time and can push it past the free allowance.",
                      f"If unsure, pause it with `{PAUSE_POLLER}` and check the scheduler for retries.")
    if check == "gbfs_poller_runtime":                                  # feed running too long
        return _alert("Act now",
                      f"The live station feed ran for {alert['billed_seconds']:.0f} seconds in 24 hours (budget {alert['limit']}; normal is about 1150). "
                      f"Its longest single run took {alert['longest_seconds']:.0f} seconds.",
                      "More running time can push the feed past the free allowance and start costing money.",
                      f"Pause it with `{PAUSE_POLLER}`, then check the gbfs-poller logs.")
    if check == "gbfs_poller_feed_stale":                               # feed stopped producing data
        age = alert["age_minutes"]                                      # None means no recent data at all
        detail = "no data in the last 2 days" if age is None else f"the newest data is {age} min old"
        return _alert("Check soon",
                      f"The live station feed has stopped: {detail} (limit {alert['limit']} min).",
                      "The dashboard's GCP Stream tab shows old or no live station data.",
                      "Check the gbfs-poller logs in Cloud Run. If you paused it on purpose, set gbfs_poller_expected_on=False in cost-audit/thresholds.py.")
    return _alert("Check soon",                                         # defensive fallback for a new alert type without wording
                  f"Unknown check {check}: {alert}",
                  "This alert type has no plain description yet.",
                  "Add plain wording for this check in cost-audit/notify.py.")


def overall_urgency(alerts: list) -> str:                               # the most urgent tag among the problems
    """Return the most urgent tag across all alerts (used in the header and email subject)."""
    tags = {describe_alert(a)["urgency"] for a in alerts}               # distinct tags present
    return next(t for t in URGENCY_ORDER if t in tags)                  # first (most urgent) tag that occurs


def _header(alerts: list) -> str:                                       # "1 problem found" / "3 problems found"
    """Return the plain header line with a correctly pluralised count."""
    n = len(alerts)                                                     # number of problems
    return f"Bike demand cloud check: {n} problem{'s' if n != 1 else ''} found"


# ── Slack message ─────────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a single Slack-ready string
    """Format alerts as a plain-language Slack message: header, each tagged problem with why + what to do, tag legend."""
    lines = [f"*{_header(alerts)} ({overall_urgency(alerts)})*"]        # bold header with the most urgent tag
    for alert in alerts:                                                # one block per problem
        d = describe_alert(alert)                                       # plain wording
        lines.append(f"• *[{d['urgency']}]* {d['what']}")          # bullet: tag + what happened
        lines.append(f"    _Why it matters:_ {d['why']}")               # indented reason
        lines.append(f"    _What to do:_ {d['action']}")                # indented action
    lines.append(f"_Tags: {TAG_LEGEND}._")                             # explain the tags once at the end
    return "\n".join(lines)                                             # Slack renders \n as line breaks


# ── One-line summary for the email alert ──────────────────────────────────────
# The email comes from a Cloud Monitoring log alert, which copies text out of a
# single log entry (about 1,000 characters at most), so the summary is one line,
# without Slack markup, and cut short with a pointer to Slack if it is too long.

def plain_summary(alerts: list) -> str:                                 # numbered, tagged, single-line, no markup
    """Return the problems as one plain line, under SUMMARY_LIMIT characters."""
    parts = []                                                          # one part per problem
    for number, alert in enumerate(alerts, start=1):                    # number problems from 1
        d = describe_alert(alert)                                       # plain wording
        part = (f"{number}) [{d['urgency']}] {d['what']} Why it matters: {d['why']} "
                f"What to do: {d['action']}")                           # tag + what + why + action
        parts.append(part.replace("`", "").replace("*", "").replace("\n", " "))  # strip Slack markup
    text = " ".join(parts)                                              # single line
    if len(text) <= SUMMARY_LIMIT:                                      # fits: send everything
        return text
    room = SUMMARY_LIMIT - len(MORE_IN_SLACK) - 1                       # space left before the pointer
    kept = ""                                                           # whole problems that fit
    for part in parts:                                                  # keep whole problems while they fit
        candidate = f"{kept} {part}".strip()                            # add the next problem
        if len(candidate) > room:                                       # would overflow
            break
        kept = candidate                                                # accept it
    if not kept:                                                        # even the first problem is too long
        kept = parts[0][: room - 3].rstrip() + "..."                    # cut it mid-way
    return f"{kept} {MORE_IN_SLACK}"                                    # point to Slack for the rest


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
