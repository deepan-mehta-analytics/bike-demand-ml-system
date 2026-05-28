# Automated Cost Audit — Design

**Date:** 2026-05-28
**Repo:** bike-demand-ml-system (GCP project `bike-demand-ml-system`, proj# 246440913351)
**Status:** Approved (brainstorming) — pending implementation plan

---

## 1. Motivation

The Artifact Registry silently grew to ~38 GB / 140 image versions over ~2 weeks because CI pushes an image on every commit and nothing pruned them. It was invisible in the build-test-ship loop and only cost ~₹83 before it was noticed — a *resource* problem before it was a *spend* problem. Cost-risk attention during planning had gone to compute (Cloud Run, Vertex, BigQuery); cheap-per-GB storage that compounds with volume was the blind spot.

This project adds automated cost auditing so accumulation and overspend surface early — **without the automation itself adding cost**. That caveat is a hard requirement, sharpened by the `billing-kill-switch` incident where a cost-control service became the single biggest Cloud Run cost (a 500-on-every-request Pub/Sub push-retry storm).

## 2. Goals / Non-goals

**Goals:**
- Catch **resource accumulation** early (registry bloat, forgotten VMs, growing BQ/GCS, unexpected services, Vertex endpoints).
- Catch **spend surprises** via native budget alerts.
- Deliver alerts to Slack `#gcp-alerts` (resource scan) and email (budget).
- Stay strictly within the GCP always-free tier; be structurally incapable of becoming a cost leak.

**Non-goals:**
- Not a cost *dashboard* / BI surface (Looker Studio over the billing export can come later if wanted).
- Not auto-remediation — it alerts; humans (or existing policies) act. (The kill-switch remains the only auto-action, and only for hard budget breach.)
- Not real-time — daily cadence is sufficient for accumulation.

## 3. Constraints

- **Zero added recurring cost.** Every component must sit inside the always-free tier with headroom.
- **No Pub/Sub-push trigger** for the scanner — Scheduler-triggered only, to make the kill-switch-style infinite-redelivery failure structurally impossible.
- **Read-only.** The scanner never mutates resources and never calls a paid API (notably no Cloud Monitoring custom-metric *writes*).
- Code versioned in-repo (like `billing-kill-switch/`), not Cloud-Shell-only.

## 4. Architecture — three layers

### Layer 0 — Prevention (first line of defense)
Retention/cleanup policies so write-heavy resources *cannot* bloat:
- Artifact Registry cleanup policy (`keep-recent-5` + `delete-older-than-4d`) — already in place (2026-05-28).
- Verify/extend: BigQuery table expirations (station_snapshots has 7-day partition TTL; check others incl. billing export), Cloud Logging retention (default 30d), GCS lifecycle rules if any bucket grows.

### Layer 1 — Spend safety net (native, no code)
A GCP **Budget** with tiered **email** thresholds (₹250 / ₹500 / ₹1,000) in addition to the existing 100%→`budget-alert-topic`→kill-switch link. Budgets and their email notifications are free and cannot fail in a way that costs money.

### Layer 2 — Daily resource scanner (the build)
- **`cost-audit/`** in this repo (`main.py` + `requirements.txt`), functions-framework HTTP target — same pattern as `billing-kill-switch/`.
- **Cloud Run service `cost-audit`**, private (`--no-allow-unauthenticated`), `maxScale=1`, 256 MiB, low timeout. Read-only.
- **Cloud Scheduler `cost-audit-cron`** — daily, OIDC-authenticated POST as a dedicated read-only SA `cost-audit-sa`. 3rd scheduler job (≤3 free).
- **Slack** — posts a summary to `#gcp-alerts` via an incoming webhook **only when a threshold trips** (alert-only; silent on healthy days). Webhook URL in **Secret Manager** (free tier).

## 5. Data flow

```
Cloud Scheduler (daily, OIDC)
  → POST → cost-audit Cloud Run (private)
    → read-only API calls (Artifact Registry, Compute, BigQuery, GCS, Cloud Run, Vertex)
      + 1 small query against the billing-export BQ table (month-to-date spend)
    → evaluate each reading against its threshold
    → if ANY tripped: format summary, read webhook from Secret Manager, POST to Slack #gcp-alerts
    → return 200
```

## 6. Thresholds (config block; tunable)

| Check | Alerts when |
|---|---|
| Artifact Registry | any package > 15 versions, OR repo > 10 GB |
| Compute Engine | any VM running (expected 0) |
| Vertex AI | any endpoint or deployed model exists (no free tier) |
| BigQuery | total storage > 8 GB (free 10) |
| GCS | any bucket > 4 GB (free 5) |
| Cloud Run | a service has `minScale>0` (always-on = $$), or a service appears that is not in the config allowlist (`bike-demand-api`, `gbfs-poller`, `bike-demand-trigger`, `billing-kill-switch`, `cost-audit`) |
| Spend (MTD) | billing-export month-to-date total > ₹500 |

## 7. Cost-safety analysis (the caveat)

- **Trigger:** Cloud Scheduler, not Pub/Sub push → bounded retries (configured max 1–2), no infinite redelivery. This is the specific failure mode that made the kill-switch expensive; it is structurally absent here.
- **Compute:** 1 invocation/day × ~15s × 1 vCPU / 256 MiB ≈ ~450 vCPU-sec + ~115 GiB-sec per month, vs 180k / 360k free. Negligible. `maxScale=1` prevents fan-out.
- **APIs:** all free *reads*. Explicitly NO Cloud Monitoring custom-metric writes (the one paid-risk API). BigQuery MTD query is a few MB scanned vs 1 TB/month free.
- **Delivery:** Slack incoming webhook (free); Secret Manager (6 secrets / 10k accesses per month free; one daily access).
- **Self-coverage:** the `cost-audit` image is governed by the same registry cleanup policy, so the auditor doesn't bloat the thing it audits.

## 8. Error handling

- Each resource check is independent — a single failing read is caught, recorded as "check failed" in the message, and does not abort the scan.
- The handler always returns HTTP 2xx (so even Scheduler's bounded retries never loop); Scheduler retry count set low regardless.
- A failed Slack POST is logged, not fatal.
- `DRY_RUN=true` prints the would-be Slack payload to stdout without posting (mirrors the poller's DRY_RUN), for local/integration testing.

## 9. Testing

- Unit tests on the pure logic: given a set of resource readings, does `evaluate_thresholds()` correctly decide alert vs silent, and does the message formatter produce the expected payload? GCP reads and the Slack POST are mocked (same shape as `tests/test_gbfs_poller_service.py`).
- A test asserting "all-healthy readings → no Slack POST" (the alert-only contract).

## 10. Open questions / future

- Exact client libraries vs REST for the read calls — decide in the implementation plan to keep deps slim.
- Optional later: a Looker Studio dashboard over the billing export for trend visualization (separate, also free).
- Optional later: have CI redeploy `bike-demand-trigger` (it currently pins a digest CI never refreshes — see cost-posture notes) so the cleanup policy can't strand it.
