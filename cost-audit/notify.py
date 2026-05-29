# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                         # HTTP client for Slack incoming webhook POST


# ── Message Formatter ─────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a single Slack-ready string
    """Format a list of alert dicts into a Slack message string."""
    lines = ["🚨 *GCP Cost Audit — Thresholds Tripped*"]               # header line — always present when this function is called
    for alert in alerts:                                                # one bullet per alert dict
        check = alert["check"]                                          # discriminator key that selects the right message template
        if check == "registry_versions":
            lines.append(
                f"  • Artifact Registry: `{alert['pkg']}` has {alert['count']} versions "
                f"(limit {alert['limit']})"
            )                                                           # package name + actual vs limit for actionability
        elif check == "registry_size":
            lines.append(
                f"  • Artifact Registry: total size {alert['total_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )                                                           # size in GB to 1 decimal place
        elif check == "compute_vms":
            vms = ", ".join(alert["vms"])                               # comma-separated list of running VM names
            lines.append(f"  • Compute: {len(alert['vms'])} running VM(s): {vms}")
        elif check == "vertex_endpoints":
            lines.append(
                f"  • Vertex AI: {len(alert['endpoints'])} active endpoint(s) "
                f"(paid tier — no always-free quota)"
            )                                                           # count is enough; names are in the alert dict if needed
        elif check == "bigquery_size":
            lines.append(
                f"  • BigQuery: total storage {alert['total_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )
        elif check == "gcs_bucket":
            lines.append(
                f"  • GCS: bucket `{alert['bucket']}` is {alert['size_gb']:.1f} GB "
                f"(limit {alert['limit']:.1f} GB)"
            )
        elif check == "cloud_run_unknown":
            lines.append(
                f"  • Cloud Run: unknown service `{alert['service']}` not in allowlist"
            )                                                           # unknown service may be a rogue deploy
        elif check == "cloud_run_always_on":
            lines.append(
                f"  • Cloud Run: `{alert['service']}` has minScale={alert['min_instances']} "
                f"(always-on = paid)"
            )
        elif check == "spend_mtd":
            lines.append(
                f"  • MTD Spend: ₹{alert['mtd_cost_inr']:.0f} "
                f"(limit ₹{alert['limit']:.0f})"
            )                                                           # INR to nearest rupee
        else:                                                           # defensive fallback for any undocumented check key
            lines.append(f"  • Unknown check: {check} — {alert}")     # surfaces new alert types that lack a formatter branch
    return "\n".join(lines)                                             # single string; Slack renders \n as line breaks


# ── Slack Delivery ────────────────────────────────────────────────────────────

SLACK_CHANNEL = "#gcp-alerts"                                           # channel the bot posts cost-audit alerts to

def post_to_slack(message: str, bot_token: str) -> bool:                # posts via Slack Web API chat.postMessage; non-fatal on failure
    """POST message to Slack using a bot token. Returns True on success, False otherwise."""
    try:
        resp = requests.post(                                           # Slack Web API endpoint — works with any bot token
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {bot_token}"},          # bot token stored in Secret Manager (xoxb-...)
            json={                                                      # payload for chat.postMessage
                "channel": SLACK_CHANNEL,                              # target channel; bot must be invited to it
                "text": message,                                        # message body; Slack renders *bold* and `code` markdown
            },
            timeout=10,                                                 # 10-second timeout; network errors are non-fatal
        )
        data = resp.json()                                              # Slack always returns JSON even on failure
        return resp.status_code == 200 and data.get("ok") is True      # Slack sets ok=true on success, ok=false with error key on failure
    except requests.RequestException:                                   # covers ConnectionError, Timeout, etc.
        return False                                                    # failure is logged by caller; never raises here
