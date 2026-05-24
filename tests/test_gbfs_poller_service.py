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
