# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                        # HTTP client for the Slack incoming-webhook POST


# ── Message Formatter ─────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a single human-readable string
    """Format a list of alert dicts into a single Slack-ready text string."""
    lines = ["*GCP Cost Audit — Thresholds Tripped*"]                   # Slack mrkdwn bold header (*..* renders bold)
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
