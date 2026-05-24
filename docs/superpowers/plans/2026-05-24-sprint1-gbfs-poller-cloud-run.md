# GBFS Poller Cloud Run — Sprint 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paused Dataflow streaming path with a free-tier-safe Cloud Run service that polls GBFS APIs every 5 minutes and writes aggregated 5-min window snapshots to BigQuery, so the Shiny dashboard's GCP Stream tab actually streams.

**Architecture:** Cloud Scheduler (`*/5 * * * *`) → Cloud Run (`gbfs-poller`, slim FastAPI service) → reuse `poll_once` from existing `gbfs_to_pubsub.py` × 5 iterations with 60s sleep → in-memory aggregation per (city, station, window) → `bigquery.Client().load_table_from_json()` (free, atomic) → existing `bike_demand.station_snapshots` table.

**Tech Stack:** Python 3.11, FastAPI + uvicorn, google-cloud-bigquery, requests, pyyaml. Container: `python:3.11-slim` via `Dockerfile.poller`. GCP: Cloud Run, Cloud Scheduler, IAM, BigQuery (load jobs), Artifact Registry.

**Spec reference:** `bike-demand-prediction/docs/superpowers/specs/2026-05-24-dashboard-truth-and-freshness-design.md` § 4 (commit `9d5c70e`).

---

## Files created in this sprint

| File | Responsibility |
|---|---|
| `requirements-poller.txt` | Slim deps for the poller service (no Apache Beam, no ML libs). |
| `pipeline/window_agg.py` | Pure-Python `aggregate_window()` helper — folds station snapshots into per-(city, station, window) avg/min/max/count. Independent reimplementation of the math in `dataflow_job.py::WindowedAgg` (lower coupling than extracting). |
| `pipeline/gbfs_poller_service.py` | FastAPI app with `POST /poll` and `GET /health`. Imports `poll_once` from `gbfs_to_pubsub.py` **unchanged**. |
| `Dockerfile.poller` | Slim image: `python:3.11-slim` + `requirements-poller.txt` + pipeline code. ~150 MB. |
| `tests/test_window_agg.py` | Unit tests for aggregation helper (synthetic snapshots, edge cases). |
| `tests/test_gbfs_poller_service.py` | TestClient-based tests for FastAPI endpoints with DRY_RUN. |

## Files NOT touched in this sprint

- `pipeline/gbfs_to_pubsub.py` — imported as-is. Zero modifications. This is intentional: the Dataflow path stays resurrectable.
- `pipeline/dataflow_job.py` — left intact. The `WindowedAgg` math is reimplemented (not extracted) so this file remains a working independent reference.
- `config/gcp_config.yaml` — already has the 4 cities (nyc, dc, london, chicago) under `gbfs.cities`. No edits needed.
- `requirements.txt` / `requirements-pipeline.txt` — unchanged; new file `requirements-poller.txt` keeps the poller's dep set isolated.

---

## Engineering decisions made under the hood (FYI, not for approval)

Per the [[engineering-autonomy]] memory rule, the following choices are made inline:

- **Service account = same SA for Cloud Run runtime AND Cloud Scheduler OIDC.** `gbfs-poller-sa@` is granted `roles/bigquery.dataEditor` on dataset, deployed as the service's runtime identity, and ALSO used by Scheduler to mint OIDC tokens. Cloud Run's `--no-allow-unauthenticated` + invoker binding on the SA closes the loop. Simpler than two SAs; matches the `vertex-sa@` pattern used by `vertex_trigger.py`.
- **No global aggregator class** — `aggregate_window()` is a single pure function that takes an iterator of records and returns a dict. No state, no class, no mutability surprises. Easier to test.
- **DRY_RUN flag** — read by `gbfs_poller_service.py` from env var. When `true`, skips the BQ write step and returns the row count + sample rows in the response. Used for local + first-deploy testing.
- **Schedule = `*/5 * * * *` UTC.** Aligns with the existing `floor(now, 5min)` window math. Skipped runs are tolerated.
- **Retry count = 0** on the Scheduler job. No duplicate-write risk; next cron is 5 min away.
- **Attempt deadline = 540s** on the Scheduler job. Matches Cloud Run request timeout. Cycle budget is ~270s so this is 2× headroom.
- **Image tag = `:latest`** for v1 ship. If a future v1.6.1 needs a separate tag, easy to add then.
- **No CI workflow** for this service yet. Manual `gcloud builds submit` for the first deploy. CI job can land in a later sprint if/when iteration pace demands it.
- **Logging** — Python stdlib `logging` to stdout, structured JSON. Mirrors `gbfs_to_pubsub.py`'s `_JsonFormatter`. Cloud Run auto-captures and ships to Cloud Logging free tier.

---

## Task list

### Task 1: Create `requirements-poller.txt` and confirm install works

**Files:**
- Create: `requirements-poller.txt`

- [ ] **Step 1: Write `requirements-poller.txt`**

```
# Poller-only dependencies — install for the gbfs-poller Cloud Run service.
# Deliberately separate from requirements.txt (inference image) and requirements-pipeline.txt
# (Apache Beam Dataflow path) to keep the poller's container image slim (~150 MB).
# Install with: pip install -r requirements-poller.txt
fastapi==0.136.1                  # HTTP framework for POST /poll and GET /health endpoints; pin matches requirements.txt
uvicorn[standard]==0.46.0         # ASGI server with httptools/uvloop; pin matches requirements.txt
google-cloud-bigquery==3.27.0     # BigQuery client for load_table_from_json (free batch loads)
requests==2.32.3                  # HTTP client for GBFS and TFL API calls (reused via gbfs_to_pubsub.py)
pyyaml==6.0.2                     # YAML parser for reading config/gcp_config.yaml
```

- [ ] **Step 2: Install into existing venv**

Run: `venv\Scripts\pip install -r requirements-poller.txt`
Expected: All five packages install or report "Requirement already satisfied" (fastapi, requests, pyyaml likely already present from sibling files; uvicorn and google-cloud-bigquery may be fresh).

- [ ] **Step 3: Smoke-test imports**

Run: `venv\Scripts\python -c "import fastapi, uvicorn, requests, yaml; from google.cloud import bigquery; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements-poller.txt
git commit -m "feat: add requirements-poller.txt for new Cloud Run service

Isolated dep set for the gbfs-poller service (Sprint 1 of v1.6.0
dashboard truth and freshness ship). Keeps the slim poller image
free of Apache Beam and ML deps that the inference and pipeline
images carry."
```

---

### Task 2: Implement `window_agg.py` aggregation helper — TDD

**Files:**
- Create: `pipeline/window_agg.py`
- Create: `tests/test_window_agg.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_window_agg.py`:

```python
# ── Imports ───────────────────────────────────────────────────
from datetime import datetime, timezone                       # UTC timestamps for window boundaries
import pytest                                                  # testing framework

from pipeline.window_agg import aggregate_window               # function under test

# ── Shared fixtures ───────────────────────────────────────────
WINDOW_START = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)  # arbitrary 5-min window start
WINDOW_END   = datetime(2026, 5, 24, 12, 5, 0, tzinfo=timezone.utc)  # window end = start + 5 min

def _rec(city, station_id, name, bikes):                       # helper to build minimal snapshot dicts
    return {                                                    # record shape mirrors gbfs_to_pubsub _build_snapshot_gbfs
        "city":                city,                            # city slug from config
        "station_id":          station_id,                      # station identifier string
        "station_name":        name,                            # human-readable station name
        "num_bikes_available": bikes,                           # integer bike count
        "num_docks_available": 0,                               # unused by aggregator but present in real records
        "is_renting":          True,                            # unused by aggregator but present in real records
        "snapshot_time":       WINDOW_START.isoformat(),        # snapshot time (not consumed by aggregator)
    }

# ── Test 1: empty input ───────────────────────────────────────
def test_empty_input_returns_empty_list():                     # aggregator must handle "no polls succeeded" gracefully
    result = aggregate_window([], WINDOW_START, WINDOW_END)    # call with empty iterator
    assert result == []                                         # no rows to write; caller skips BQ load

# ── Test 2: single station, single snapshot ───────────────────
def test_single_snapshot_avg_equals_min_equals_max():          # one snapshot per station: degenerate stats
    records = [_rec("nyc", "72", "W 52 St & 11 Ave", 10)]      # one record from one poll iteration
    result = aggregate_window(records, WINDOW_START, WINDOW_END)
    assert len(result) == 1                                     # one row per (city, station) key
    row = result[0]
    assert row["city"]                == "nyc"                  # city slug preserved
    assert row["station_id"]          == "72"                   # station_id preserved
    assert row["station_name"]        == "W 52 St & 11 Ave"     # name preserved
    assert row["window_start"]        == WINDOW_START.isoformat()  # ISO 8601 UTC for BigQuery TIMESTAMP load
    assert row["window_end"]          == WINDOW_END.isoformat()    # ISO 8601 UTC for BigQuery TIMESTAMP load
    assert row["avg_bikes_available"] == 10.0                   # mean of [10] = 10.0 (FLOAT per BQ_SCHEMA)
    assert row["min_bikes_available"] == 10                     # min of [10] = 10 (INTEGER per BQ_SCHEMA)
    assert row["max_bikes_available"] == 10                     # max of [10] = 10
    assert row["total_snapshots"]     == 1                      # one snapshot folded into this window

# ── Test 3: single station, five snapshots ────────────────────
def test_multiple_snapshots_compute_avg_min_max():             # one station polled 5 times: real avg/min/max
    records = [_rec("nyc", "72", "W 52 St & 11 Ave", b)        # five snapshots, bikes = [12, 11, 10, 13, 9]
               for b in [12, 11, 10, 13, 9]]
    result = aggregate_window(records, WINDOW_START, WINDOW_END)
    assert len(result) == 1                                     # still one row per (city, station)
    row = result[0]
    assert row["avg_bikes_available"] == 11.0                   # (12+11+10+13+9)/5 = 11.0
    assert row["min_bikes_available"] == 9                      # min of [12,11,10,13,9] = 9
    assert row["max_bikes_available"] == 13                     # max = 13
    assert row["total_snapshots"]     == 5                      # five snapshots aggregated

# ── Test 4: multiple stations, multiple cities ────────────────
def test_multiple_stations_and_cities_are_separate_keys():     # aggregator must group by (city, station_id, station_name)
    records = [
        _rec("nyc",     "72",    "NYC Station A", 10),
        _rec("nyc",     "72",    "NYC Station A", 14),         # same NYC station, second snapshot
        _rec("nyc",     "100",   "NYC Station B", 5),
        _rec("london",  "BP_1",  "TfL Station X", 7),
        _rec("london",  "BP_1",  "TfL Station X", 9),          # same TfL station, second snapshot
    ]
    result = aggregate_window(records, WINDOW_START, WINDOW_END)
    assert len(result) == 3                                     # three unique (city, station) keys
    by_key = {(r["city"], r["station_id"]): r for r in result} # index by (city, station_id) for assertions
    assert by_key[("nyc",    "72")]["avg_bikes_available"]   == 12.0   # (10+14)/2
    assert by_key[("nyc",    "72")]["total_snapshots"]       == 2
    assert by_key[("nyc",    "100")]["avg_bikes_available"]  == 5.0    # single snapshot
    assert by_key[("london", "BP_1")]["avg_bikes_available"] == 8.0    # (7+9)/2

# ── Test 5: avg rounded to 2 decimals (matches dataflow_job behaviour) ─
def test_avg_is_rounded_to_two_decimals():                     # matches existing Dataflow WindowedAgg rounding
    records = [_rec("nyc", "x", "X", b) for b in [10, 11, 11]] # avg = 10.6666... → must round to 10.67
    result = aggregate_window(records, WINDOW_START, WINDOW_END)
    assert result[0]["avg_bikes_available"] == 10.67           # exactly 2 decimal places
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python -m pytest tests/test_window_agg.py -v`
Expected: `ImportError: No module named 'pipeline.window_agg'` (5 errors during collection or skipped — module doesn't exist yet).

- [ ] **Step 3: Implement `pipeline/window_agg.py`**

Create `pipeline/window_agg.py`:

```python
# ── Imports ───────────────────────────────────────────────────
from datetime import datetime                                  # type annotation for window boundary arguments
from typing import Iterable, Any                               # type hints for input iterator and record dicts

# ── Public API ────────────────────────────────────────────────
def aggregate_window(
    records:      Iterable[dict[str, Any]],                    # iterator over GBFS snapshot dicts from poll_once
    window_start: datetime,                                    # 5-minute window start as timezone-aware UTC datetime
    window_end:   datetime,                                    # window end (start + 5 min) as timezone-aware UTC datetime
) -> list[dict[str, Any]]:                                     # returns one BQ row per (city, station_id, station_name) key
    """Fold snapshot records into one row per (city, station, window).

    Mirrors the avg/min/max/count math in pipeline.dataflow_job.WindowedAgg
    but as a pure Python function suitable for use inside a Cloud Run
    request handler — no Apache Beam dependency.
    """
    # ── Accumulator ─────────────────────────────────────────────
    # Key: (city, station_id, station_name); value: dict with running stats.
    # Using a dict keyed by tuple keeps the implementation O(N) over records.
    acc: dict[tuple[str, str, str], dict[str, Any]] = {}      # accumulator keyed by composite station key

    for r in records:                                          # iterate every snapshot from every poll iteration
        key = (                                                # composite key matching the Dataflow GroupByKey
            r["city"],                                          # city slug (nyc / dc / london / chicago)
            r["station_id"],                                    # station identifier string
            r.get("station_name", ""),                          # name may be absent in malformed records; default empty
        )
        bikes = int(r["num_bikes_available"])                  # bikes available at this snapshot (coerce to int)

        if key not in acc:                                     # first snapshot for this (city, station): seed accumulator
            acc[key] = {                                        # initialise running stats with this single snapshot
                "sum":   bikes,                                 # running sum for computing the average
                "min":   bikes,                                 # running minimum
                "max":   bikes,                                 # running maximum
                "count": 1,                                     # snapshot count for this window
            }
        else:                                                  # subsequent snapshot: fold into existing accumulator
            a = acc[key]                                        # local alias for readability
            a["sum"]   += bikes                                # add to running sum
            a["min"]   = min(a["min"], bikes)                  # update running minimum
            a["max"]   = max(a["max"], bikes)                  # update running maximum
            a["count"] += 1                                    # increment snapshot count

    # ── Flatten to BQ rows ──────────────────────────────────────
    # Output shape matches dataflow_job.BQ_SCHEMA for drop-in compatibility
    # with bike-demand-ml-system.bike_demand.station_snapshots.
    win_start_iso = window_start.isoformat()                   # ISO 8601 UTC string for BigQuery TIMESTAMP column
    win_end_iso   = window_end.isoformat()                     # ISO 8601 UTC string for BigQuery TIMESTAMP column

    rows: list[dict[str, Any]] = []                            # output buffer; one row per accumulator key
    for (city, station_id, station_name), a in acc.items():    # iterate accumulator entries in insertion order
        rows.append({                                          # one row dict matching BQ_SCHEMA exactly
            "city":                city,                       # STRING REQUIRED
            "station_id":          station_id,                 # STRING REQUIRED
            "station_name":        station_name,               # STRING NULLABLE
            "window_start":        win_start_iso,              # TIMESTAMP REQUIRED
            "window_end":          win_end_iso,                # TIMESTAMP REQUIRED
            "avg_bikes_available": round(a["sum"] / a["count"], 2),  # FLOAT NULLABLE; 2dp matches Dataflow
            "min_bikes_available": a["min"],                   # INTEGER NULLABLE
            "max_bikes_available": a["max"],                   # INTEGER NULLABLE
            "total_snapshots":     a["count"],                 # INTEGER NULLABLE
        })
    return rows                                                # caller passes this directly to load_table_from_json
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python -m pytest tests/test_window_agg.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/window_agg.py tests/test_window_agg.py
git commit -m "feat(pipeline): add window_agg helper for poller aggregation

Pure-Python aggregate_window() folds GBFS snapshots into per-(city,
station, window) avg/min/max/count rows matching the Dataflow
BQ_SCHEMA exactly. Independent reimplementation of WindowedAgg
math (not an extraction) so dataflow_job.py stays untouched and
resurrection-capable.

Sprint 1 of v1.6.0 dashboard truth and freshness."
```

---

### Task 3: Implement `gbfs_poller_service.py` FastAPI app — TDD

**Files:**
- Create: `pipeline/gbfs_poller_service.py`
- Create: `tests/test_gbfs_poller_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_gbfs_poller_service.py`:

```python
# ── Dependency Guard ──────────────────────────────────────────
# Skip the entire module if poller deps (fastapi, google-cloud-bigquery) aren't installed.
import pytest                                                  # testing framework
pytest.importorskip("fastapi",                                 # FastAPI test client requires this
                    reason="fastapi not installed — pip install -r requirements-poller.txt")
pytest.importorskip("google.cloud.bigquery",                   # google-cloud-bigquery installed via requirements-poller
                    reason="google-cloud-bigquery not installed — pip install -r requirements-poller.txt")

# ── Imports ───────────────────────────────────────────────────
import os                                                      # env var manipulation for DRY_RUN flag
from unittest.mock import patch                                # patch poll_once to return canned data without HTTP calls
from fastapi.testclient import TestClient                      # in-process HTTP test client for FastAPI

from pipeline.gbfs_poller_service import app                   # FastAPI app under test

client = TestClient(app)                                       # one client reused across tests

# ── Test 1: health endpoint returns 200 + ok ──────────────────
def test_health_endpoint_returns_ok():                         # basic liveness check
    response = client.get("/health")                           # GET /health
    assert response.status_code == 200                         # FastAPI returns 200
    assert response.json() == {"status": "ok"}                 # exact body match

# ── Test 2: POST /poll in DRY_RUN mode returns row count ──────
def test_poll_dry_run_returns_aggregated_rows():               # verify aggregation runs end-to-end without BQ
    # Canned response from poll_once: 1 city, 1 station, 1 snapshot per iteration
    canned = {                                                  # mirrors poll_once return shape
        "nyc": [{                                              # nyc city key with one record
            "city":                "nyc",
            "station_id":          "72",
            "station_name":        "W 52 St & 11 Ave",
            "num_bikes_available": 10,
            "num_docks_available": 27,
            "is_renting":          True,
            "snapshot_time":       "2026-05-24T12:00:00+00:00",
        }],
    }
    # Patch poll_once + the sleep so the test runs in milliseconds, not 4 minutes
    with patch("pipeline.gbfs_poller_service.poll_once",       # stub the GBFS HTTP loop
               return_value=canned), \
         patch("pipeline.gbfs_poller_service.time.sleep",       # skip the 60s waits
               return_value=None), \
         patch.dict(os.environ, {"DRY_RUN": "true"}):           # DRY_RUN skips the BQ write step
        response = client.post("/poll")                         # trigger the handler

    assert response.status_code == 200                         # successful response
    body = response.json()
    assert body["status"]       == "ok"                        # status field
    assert body["rows_written"] == 1                           # one (city, station) aggregate row
    assert body["dry_run"]      is True                        # confirm DRY_RUN was honoured
    assert "window_start" in body                              # response includes window boundary
    assert "window_end"   in body                              # response includes window boundary

# ── Test 3: POST /poll without DRY_RUN attempts BQ load ───────
def test_poll_calls_bq_load_when_not_dry_run():                # verify real path invokes load_table_from_json
    canned = {                                                  # one city, one station, one snapshot
        "nyc": [{
            "city":                "nyc",
            "station_id":          "72",
            "station_name":        "W 52 St & 11 Ave",
            "num_bikes_available": 10,
            "num_docks_available": 27,
            "is_renting":          True,
            "snapshot_time":       "2026-05-24T12:00:00+00:00",
        }],
    }
    with patch("pipeline.gbfs_poller_service.poll_once",       # stub HTTP
               return_value=canned), \
         patch("pipeline.gbfs_poller_service.time.sleep",       # skip sleeps
               return_value=None), \
         patch("pipeline.gbfs_poller_service.bigquery.Client") as mock_client_cls, \
         patch.dict(os.environ, {"DRY_RUN": "false"}):          # DRY_RUN=false → real BQ path

        mock_load_method = mock_client_cls.return_value.load_table_from_json  # capture the call
        mock_load_method.return_value.result.return_value = None              # load_job.result() returns None on success

        response = client.post("/poll")

    assert response.status_code == 200                         # successful response
    assert response.json()["dry_run"] is False                 # confirm real path taken
    mock_load_method.assert_called_once()                      # exactly one BQ load triggered
    call_args = mock_load_method.call_args                     # inspect what was passed to load_table_from_json
    rows_arg = call_args.kwargs.get("json_rows") or call_args.args[0]  # row list is first positional or json_rows kwarg
    assert len(rows_arg) == 1                                  # one (city, station) aggregate row
    assert rows_arg[0]["city"]       == "nyc"
    assert rows_arg[0]["station_id"] == "72"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python -m pytest tests/test_gbfs_poller_service.py -v`
Expected: `ImportError: cannot import name 'app' from 'pipeline.gbfs_poller_service'` (3 errors during collection — module doesn't exist yet).

- [ ] **Step 3: Implement `pipeline/gbfs_poller_service.py`**

Create `pipeline/gbfs_poller_service.py`:

```python
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

    logger.info(json.dumps({                                   # successful write log
        "event":        "bq_load_complete",
        "rows_written": len(rows),
        "job_id":       load_job.job_id,
    }))

    return {                                                    # response body for Cloud Scheduler 2xx ack
        "status":       "ok",
        "dry_run":      False,
        "rows_written": len(rows),
        "window_start": window_start.isoformat(),
        "window_end":   window_end.isoformat(),
        "job_id":       load_job.job_id,                       # included for debuggability
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python -m pytest tests/test_gbfs_poller_service.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Run the full test suite to confirm nothing else broke**

Run: `venv\Scripts\python -m pytest tests/ -v`
Expected: All prior tests still pass; new tests included.

- [ ] **Step 6: Commit**

```bash
git add pipeline/gbfs_poller_service.py tests/test_gbfs_poller_service.py
git commit -m "feat(pipeline): add gbfs_poller_service FastAPI Cloud Run app

POST /poll triggered by Cloud Scheduler every 5 min: polls GBFS
endpoints 5 times (60s apart), aggregates via window_agg, writes
to BigQuery via load_table_from_json (free batch load).

DRY_RUN=true env var skips BQ write and returns row count for
local/first-deploy testing. Imports poll_once from gbfs_to_pubsub.py
unchanged.

Sprint 1 of v1.6.0 dashboard truth and freshness."
```

---

### Task 4: Create `Dockerfile.poller` slim image and verify local build

**Files:**
- Create: `Dockerfile.poller`

- [ ] **Step 1: Write `Dockerfile.poller`**

```dockerfile
# Base image: official slim Python 3.11 — matches CI python-version.
FROM python:3.11-slim

# Non-root user for safer runtime defaults.
RUN useradd -m appuser

# All subsequent COPY/RUN commands resolve relative to /app.
WORKDIR /app

# Copy the dep manifest first so the pip-install layer caches independently of source.
COPY requirements-poller.txt .

# Install the slim dep set without pip cache to keep the layer small.
RUN pip install --no-cache-dir -r requirements-poller.txt

# Copy only the directories the poller needs:
#   pipeline/  — service code + reused gbfs_to_pubsub and new window_agg
#   config/    — gcp_config.yaml read by _load_config at request time
COPY --chown=appuser:appuser pipeline/ ./pipeline/
COPY --chown=appuser:appuser config/   ./config/

# Switch to non-root user before exposing the port.
USER appuser

# Document the port uvicorn binds to inside the container.
EXPOSE 8080

# Liveness probe — polls /health every 30s; marks unhealthy after 3 failures.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Bind on all interfaces so Cloud Run can reach the port from the host.
# Cloud Run sets $PORT to 8080 by default; passing --port=8080 hardcodes the same value.
CMD ["uvicorn", "pipeline.gbfs_poller_service:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Build the image locally**

Run: `docker build -t gbfs-poller:local -f Dockerfile.poller .`
Expected: Successful build. Final line approximately `=> => writing image sha256:...`.

- [ ] **Step 3: Verify image size**

Run: `docker images gbfs-poller:local --format "{{.Size}}"`
Expected: ~150-200 MB (vs ~1.5 GB for the monolith Dockerfile). If significantly larger, review what got copied.

- [ ] **Step 4: Smoke-test the container locally with DRY_RUN**

Run (foreground OK; ctrl-C to stop):
```bash
docker run --rm -p 8080:8080 -e DRY_RUN=true gbfs-poller:local
```

In a second terminal:
```bash
curl http://localhost:8080/health
```
Expected: `{"status":"ok"}`

Then trigger a poll (this takes ~270s with the 4 × 60s sleeps):
```bash
curl -X POST http://localhost:8080/poll
```
Expected after ~270s: JSON body with `"status":"ok"`, `"dry_run":true`, `"rows_written":<a few thousand>`, `window_start` and `window_end` ISO timestamps, and a `sample` array of up to 3 rows.

Stop the container with ctrl-C.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.poller
git commit -m "build: add Dockerfile.poller slim image for Cloud Run

Separate from the monolith Dockerfile to keep cold starts fast
(~3s vs ~30s) and image size small (~150 MB vs ~1.5 GB). Only
copies pipeline/ and config/ — no ML model artifacts.

Sprint 1 of v1.6.0 dashboard truth and freshness."
```

---

### Task 5: GCP setup — service account, IAM, GAR push

No source-code commit in this task. All steps are gcloud + bq + docker push.

- [ ] **Step 1: Create the service account**

Run:
```bash
gcloud iam service-accounts create gbfs-poller-sa \
  --display-name="GBFS Poller (Cloud Run + Scheduler)" \
  --project=bike-demand-ml-system
```
Expected: `Created service account [gbfs-poller-sa].`

If it already exists: `gcloud iam service-accounts list --filter="email:gbfs-poller-sa@*"` and skip this step.

- [ ] **Step 2: Grant `roles/bigquery.dataEditor` on the dataset only**

Run:
```bash
bq add-iam-policy-binding \
  --member="serviceAccount:gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor" \
  bike-demand-ml-system:bike_demand
```
Expected: Output ending with the updated policy showing the new binding.

- [ ] **Step 3: Grant `roles/bigquery.jobUser` at project level (required to submit load jobs)**

Run:
```bash
gcloud projects add-iam-policy-binding bike-demand-ml-system \
  --member="serviceAccount:gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```
Expected: Output ending with `Updated IAM policy for project [bike-demand-ml-system].`

(Note: `bigquery.dataEditor` permits writing rows but does NOT permit creating jobs — load jobs require `bigquery.jobs.create`, which `bigquery.jobUser` provides. This was the same pattern needed when wiring the Shiny bigrquery client.)

- [ ] **Step 4: Build and push the image to Artifact Registry**

Run:
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/gbfs-poller:latest \
  --project=bike-demand-ml-system \
  -f Dockerfile.poller .
```
Expected: Final output `SUCCESS` with the image digest.

Verify:
```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo \
  --filter="package=gbfs-poller" \
  --format="value(version,createTime)"
```
Expected: One row showing the `:latest` tag with today's timestamp.

---

### Task 6: Deploy Cloud Run service `gbfs-poller`

- [ ] **Step 1: Deploy the service**

Run:
```bash
gcloud run deploy gbfs-poller \
  --image=us-central1-docker.pkg.dev/bike-demand-ml-system/bike-demand-repo/gbfs-poller:latest \
  --region=us-central1 \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com \
  --max-instances=1 \
  --memory=256Mi \
  --cpu=1 \
  --timeout=540 \
  --project=bike-demand-ml-system
```
Expected: Output ending with `Service [gbfs-poller] revision [gbfs-poller-00001-xxx] has been deployed and is serving 100 percent of traffic.` and the service URL.

Capture the service URL — referred to below as `$SERVICE_URL`.

- [ ] **Step 2: Verify the health endpoint with auth**

Run:
```bash
gcloud run services proxy gbfs-poller --region=us-central1 --port=8080
```
Then in another terminal:
```bash
curl http://localhost:8080/health
```
Expected: `{"status":"ok"}`.

Stop the proxy with ctrl-C.

Alternative (direct cURL with auth token):
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  $SERVICE_URL/health
```
Expected: `{"status":"ok"}`.

- [ ] **Step 3: Verify DRY_RUN mode works in the deployed environment**

Set DRY_RUN as a service env var (temporarily — will remove after verification):
```bash
gcloud run services update gbfs-poller \
  --region=us-central1 \
  --set-env-vars=DRY_RUN=true \
  --project=bike-demand-ml-system
```

Trigger a poll (response will take ~270s):
```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  --max-time 600 \
  $SERVICE_URL/poll
```
Expected: JSON body with `"status":"ok"`, `"dry_run":true`, `"rows_written":<a few thousand>`, a `sample` array.

If this works → remove the DRY_RUN env var so the real path takes effect:
```bash
gcloud run services update gbfs-poller \
  --region=us-central1 \
  --remove-env-vars=DRY_RUN \
  --project=bike-demand-ml-system
```

---

### Task 7: Apply BigQuery partition expiration

- [ ] **Step 1: Confirm the table is currently partitioned**

Run:
```bash
bq show --format=prettyjson bike-demand-ml-system:bike_demand.station_snapshots | findstr /i partition
```
Expected: A `timePartitioning` block with `type: DAY`. (If absent — pause and discuss; the ALTER below assumes day-partitioning.)

- [ ] **Step 2: Apply 7-day partition expiration**

Run:
```bash
bq query --use_legacy_sql=false --project_id=bike-demand-ml-system \
  "ALTER TABLE \`bike-demand-ml-system.bike_demand.station_snapshots\` SET OPTIONS (partition_expiration_days = 7)"
```
Expected: `Done.` (No row count for ALTER statements.)

- [ ] **Step 3: Verify the option is set**

Run:
```bash
bq show --format=prettyjson bike-demand-ml-system:bike_demand.station_snapshots | findstr /i expiration
```
Expected: A line showing `"expirationMs": "604800000"` (7 days in ms).

(No commit — this is a metadata change on the table, not on any tracked file.)

---

### Task 8: Create Cloud Scheduler job `gbfs-poller-cron`

- [ ] **Step 1: Grant Cloud Scheduler permission to invoke the Cloud Run service**

Since we're using the same SA (`gbfs-poller-sa@`) for both Cloud Run runtime AND Scheduler OIDC, we grant `roles/run.invoker` on the service to that SA:

```bash
gcloud run services add-iam-policy-binding gbfs-poller \
  --member="serviceAccount:gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=us-central1 \
  --project=bike-demand-ml-system
```
Expected: Output showing the updated policy with the new binding.

- [ ] **Step 2: Create the Scheduler job**

Replace `$SERVICE_URL` with the URL from Task 6 Step 1 (e.g. `https://gbfs-poller-xxx-uc.a.run.app`):

```bash
gcloud scheduler jobs create http gbfs-poller-cron \
  --location=us-central1 \
  --schedule="*/5 * * * *" \
  --time-zone="UTC" \
  --uri="$SERVICE_URL/poll" \
  --http-method=POST \
  --oidc-service-account-email=gbfs-poller-sa@bike-demand-ml-system.iam.gserviceaccount.com \
  --oidc-token-audience="$SERVICE_URL" \
  --attempt-deadline=540s \
  --max-retry-attempts=0 \
  --description="Poll GBFS endpoints every 5 min → BQ station_snapshots" \
  --project=bike-demand-ml-system
```
Expected: `Created job [gbfs-poller-cron].`

- [ ] **Step 3: Verify the job exists and is enabled**

Run:
```bash
gcloud scheduler jobs describe gbfs-poller-cron \
  --location=us-central1 \
  --format="value(name,schedule,state,attemptDeadline)" \
  --project=bike-demand-ml-system
```
Expected: One row showing the job name, `*/5 * * * *`, `ENABLED`, `540s`.

---

### Task 9: End-to-end verification — run scheduler once, confirm data lands

- [ ] **Step 1: Snapshot the current MAX(window_start) in BQ**

Run:
```bash
bq query --use_legacy_sql=false --project_id=bike-demand-ml-system \
  "SELECT MAX(window_start) AS latest_before FROM \`bike-demand-ml-system.bike_demand.station_snapshots\`"
```
Capture the timestamp — referred to as `$BEFORE`.

- [ ] **Step 2: Trigger the Scheduler job manually**

Run:
```bash
gcloud scheduler jobs run gbfs-poller-cron \
  --location=us-central1 \
  --project=bike-demand-ml-system
```
Expected: No error output.

- [ ] **Step 3: Wait ~5 minutes for the cycle to complete**

The Cloud Run handler does 4 × 60s sleeps + ~5s polls + ~5s BQ load ≈ 270s, but Cloud Scheduler's view of "complete" is when the service responds. Wait at least 5 minutes after the manual trigger before checking.

- [ ] **Step 4: Verify new rows landed**

Run:
```bash
bq query --use_legacy_sql=false --project_id=bike-demand-ml-system \
  "SELECT city, COUNT(*) AS row_count, MIN(window_start) AS first_window, MAX(window_start) AS last_window FROM \`bike-demand-ml-system.bike_demand.station_snapshots\` WHERE window_start > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 15 MINUTE) GROUP BY city ORDER BY city"
```
Expected: 4 rows (nyc, dc, london, chicago), each with `row_count` ≈ 500-2000 stations, `first_window` = `last_window` ≈ the most recent 5-min boundary, all within the last 15 minutes.

If empty: check Cloud Run logs:
```bash
gcloud run services logs read gbfs-poller --region=us-central1 --limit=100 --project=bike-demand-ml-system
```
Look for `poll_start`, `aggregated`, `bq_load_complete` log lines.

- [ ] **Step 5: Verify Shiny GCP Stream tab shows the data**

Restart Shiny (per [[vscode-shiny-run]]: in the VS Code R terminal, run `shiny::runApp("shiny_app")`). Open the GCP Stream tab.

Expected:
- Status panel shows "BigQuery Connected · 4 cities with recent data"
- Latest Snapshot card shows 4 rows, each with `Xm ago` close to single digits
- Trend chart for the selected city (NYC by default) shows at least 1 data point on the time axis

If only 1 window appears: that's correct after the first manual trigger. Subsequent automated runs every 5 min will populate the trend chart.

- [ ] **Step 6: Wait one full automated cycle (10 min)**

Cloud Scheduler should fire `gbfs-poller-cron` again at the next `*/5` boundary. Wait until at least 2 cycles have run automatically.

Verify in BQ:
```bash
bq query --use_legacy_sql=false --project_id=bike-demand-ml-system \
  "SELECT COUNT(DISTINCT window_start) AS distinct_windows FROM \`bike-demand-ml-system.bike_demand.station_snapshots\` WHERE window_start > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE)"
```
Expected: At least 2 distinct windows. If 0 or 1 after waiting 15+ min from the last successful manual trigger, check Scheduler execution history:
```bash
gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=gbfs-poller-cron' --limit=10 --project=bike-demand-ml-system
```

---

### Task 10: Cross-repo doc sync (both repos) + push

Per [[cross-repo-sync-mandatory-closeout]], every cross-repo-impacting ship requires updates on both sides.

- [ ] **Step 1: Update `PROJECT-STATUS.md` in this repo (`bike-demand-ml-system`)**

Open `PROJECT-STATUS.md`. Find the "Phase / Status" table and the priority/roadmap section. Add a new row marking Sprint 1 of v1.6.0 dashboard truth as ✅ Shipped (or whatever the standing convention is in this repo). Update the ecosystem snapshot to reference the new latest commit on this repo. Update any "Next move" prose so it points to Sprint 2 (Shiny-repo Workstream B).

Specific edits depend on existing structure — preserve formatting; mirror the style of prior `docs(cross-repo):` commits in `git log --oneline | head -30`.

- [ ] **Step 2: Update `PROJECT-STATUS.md` in the Shiny repo (`bike-demand-prediction`)**

`cd D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction`

Open `PROJECT-STATUS.md`. Find:
- The Phase 7F / GCP Stream row — update from "paused" framing to "live (Cloud Run poller)".
- The Known Limitations section — remove the "Pipeline paused for cost" bullet if present; add a v1.6.0 honesty note if relevant.
- The ecosystem snapshot ML-repo row — bump to point at the new latest commit on the ML repo.

- [ ] **Step 3: Commit ML repo changes**

```bash
git add PROJECT-STATUS.md
git commit -m "docs(cross-repo): mark Sprint 1 v1.6.0 GBFS poller Cloud Run shipped

Cloud Run service gbfs-poller deployed, Cloud Scheduler gbfs-poller-cron
firing every 5 min, BQ partition expiration set to 7 days. Shiny
dashboard GCP Stream tab now actually streams.

Sprint 1 of 3 for v1.6.0 dashboard truth and freshness ship."
git push origin main
```

- [ ] **Step 4: Commit Shiny repo changes**

```bash
cd D:\OneDrive\Developer\DataAnalytics\R_projects\bike_demand_prediction
git add PROJECT-STATUS.md
git commit -m "docs(cross-repo): GCP Stream tab unpaused (Sprint 1 of v1.6.0)

ML repo now runs a Cloud Run poller (gbfs-poller + gbfs-poller-cron)
writing 5-min window snapshots to bike_demand.station_snapshots
every 5 min. GCP Stream tab status panel and trend chart populate
within ~10 min of session start.

Sprint 2 (Shiny-repo forecast freshness + honest demo) up next.
Spec: docs/superpowers/specs/2026-05-24-dashboard-truth-and-freshness-design.md"
git push origin main
```

- [ ] **Step 5: Doc-only hash reconciliation (Shiny repo)**

If the `PROJECT-STATUS.md` ecosystem snapshot in the Shiny repo references its own latest commit, the commit in Step 4 will have just bumped HEAD — reconcile per [[cross-repo-sync-mandatory-closeout]]:

```bash
git log --oneline -1
# Note the hash from Step 4.

# Edit PROJECT-STATUS.md to bump own-row to that hash.
git add PROJECT-STATUS.md
git commit -m "docs(status): reconcile own hash to <new-hash>"
git push origin main
```

Skip Step 5 if the ecosystem snapshot doesn't track own-repo hash.

---

## Definition of Done for Sprint 1

When all of the following are true, Sprint 1 is shipped:

- [ ] `gcloud run services describe gbfs-poller --region=us-central1` shows the service is deployed and `ready: True`.
- [ ] `gcloud scheduler jobs describe gbfs-poller-cron --location=us-central1` shows `state: ENABLED`, `schedule: */5 * * * *`.
- [ ] `bq query "SELECT MAX(window_start) FROM bike_demand.station_snapshots"` returns a timestamp within the last 10 minutes.
- [ ] Shiny GCP Stream tab status panel shows "4 cities with recent data" with all 4 city stat cards showing `Xm ago` ≤ 10.
- [ ] `bq show bike_demand.station_snapshots` shows `expirationMs: "604800000"` (7-day partition expiration).
- [ ] Both `bike-demand-ml-system` and `bike-demand-prediction` have a `docs(cross-repo):` commit on main reflecting the Sprint 1 ship.
- [ ] No active Dataflow jobs (`gcloud dataflow jobs list --region=us-central1 --status=active`) — confirming the new Cloud Run path replaced rather than supplemented the paused one.
- [ ] `pytest tests/test_window_agg.py tests/test_gbfs_poller_service.py -v` is green.

---

## Rollback / Pause plan

If something goes wrong after Sprint 1 ships (unexpected cost, GBFS endpoint changes, runaway Cloud Run instances):

1. **Pause the Scheduler job** — `gcloud scheduler jobs pause gbfs-poller-cron --location=us-central1`. Stops new invocations immediately; existing data preserved; no cost beyond storage. Reversible with `gcloud scheduler jobs resume`.
2. **Delete the Scheduler job** — if you want to step back further: `gcloud scheduler jobs delete gbfs-poller-cron --location=us-central1`. Cloud Run service remains deployed but unused.
3. **Tear down the service** — `gcloud run services delete gbfs-poller --region=us-central1`. Final clean-up. Reversible by re-running Task 6.
4. **Restore Dataflow path** — out of scope; the existing `pipeline/dataflow_job.py` is unchanged and remains executable. But this is the costly path that we just replaced; only useful if Cloud Run path proves architecturally inadequate.

---

## Reference

- Spec: `bike-demand-prediction/docs/superpowers/specs/2026-05-24-dashboard-truth-and-freshness-design.md`
- Existing patterns: `pipeline/gbfs_to_pubsub.py::poll_once` (reused), `pipeline/dataflow_job.py::WindowedAgg` (mirrored), `pipeline/vertex_trigger.py` (Cloud Run + OIDC Scheduler template)
- Memory rules: [[engineering-autonomy]], [[cross-repo-sync-mandatory-closeout]], [[vscode-shiny-run]]
- GCP free tier audit: spec § 4.8
