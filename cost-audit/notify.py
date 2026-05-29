# ── Imports ───────────────────────────────────────────────────────────────────
import smtplib                                                          # stdlib SMTP client — no extra dep needed
from email.mime.text import MIMEText                                    # builds plain-text email body
from email.mime.multipart import MIMEMultipart                          # wraps subject + body into one message object


# ── Email config ──────────────────────────────────────────────────────────────
SMTP_HOST = "smtp-mail.outlook.com"                                     # Microsoft/Outlook SMTP server
SMTP_PORT = 587                                                         # STARTTLS port


# ── Message Formatter ─────────────────────────────────────────────────────────

def format_alert_message(alerts: list) -> str:                          # converts alert dicts to a single human-readable string
    """Format a list of alert dicts into a plain-text alert message."""
    lines = ["GCP Cost Audit - Thresholds Tripped"]                    # email-safe header (no emoji — avoids MIME encoding issues)
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


# ── Email Delivery ───────────────────────────────────────────────────────────

def send_alert(message: str, from_addr: str, to_addr: str, app_password: str) -> bool:
    """Send alert email via Outlook SMTP. Returns True on success, False otherwise."""
    try:
        msg = MIMEMultipart()                                           # container for headers + body
        msg["From"] = from_addr                                         # sender address (same as login for Outlook)
        msg["To"] = to_addr                                             # recipient — typically the same address
        msg["Subject"] = "GCP Cost Audit — Thresholds Tripped"         # plain ASCII subject avoids MIME encoding edge cases
        msg.attach(MIMEText(message, "plain"))                          # attach body as plain text

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:             # open connection to Outlook SMTP
            server.starttls()                                           # upgrade to TLS before sending credentials
            server.login(from_addr, app_password)                      # authenticate with the Microsoft App Password
            server.send_message(msg)                                    # deliver the email
        return True                                                     # no exception = delivery accepted by SMTP server
    except Exception:                                                   # catches SMTP errors, auth failures, network issues
        return False                                                    # failure is logged by caller; never raises here
