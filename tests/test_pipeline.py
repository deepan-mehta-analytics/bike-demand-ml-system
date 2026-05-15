# ── Dependency Guard ──────────────────────────────────────────
# Skip the entire module gracefully when pipeline dependencies are not installed.
# Install with: pip install -r requirements-pipeline.txt
import pytest                                       # testing framework
pytest.importorskip("yaml",         reason="pyyaml not installed — pip install -r requirements-pipeline.txt")
pytest.importorskip("apache_beam",  reason="apache-beam not installed — pip install -r requirements-pipeline.txt")

# ── Imports ───────────────────────────────────────────────────
import json                                        # JSON serialisation for building test fixture payloads

from pipeline.gbfs_to_pubsub import (              # functions under test from the GBFS poller module
    _build_snapshot_gbfs,                          # standard GBFS snapshot normaliser
    _build_snapshot_tfl,                           # TFL BikePoint snapshot normaliser
)
from pipeline.dataflow_job import (                # Beam transforms and config loader under test
    ParseMessage,                                  # DoFn: parse raw bytes → snapshot dict
    WindowedAgg,                                   # CombineFn: aggregate snapshots within a window
    build_pipeline,                                # full Beam DAG builder (used in DirectRunner test)
    _load_config,                                  # YAML config loader
)

# ── Shared Fixture ────────────────────────────────────────────
TS = "2026-05-15T09:00:00+00:00"                   # fixed UTC ISO timestamp shared across all test fixtures

# ── Test 1: GBFS snapshot schema ──────────────────────────────
def test_build_snapshot_gbfs_schema():             # verify _build_snapshot_gbfs outputs the correct record schema
    station = {                                    # mock GBFS station dict (matches station_status.json format)
        "station_id": "72",                        # station identifier as returned by GBFS API
        "name": "W 52 St & 11 Ave",               # human-readable station name
        "num_bikes_available": 12,                 # bikes available at dock
        "num_docks_available": 27,                 # empty dock slots
        "is_renting": 1,                           # station is renting (GBFS uses int 0/1)
    }
    result = _build_snapshot_gbfs("nyc", station, TS)  # call the GBFS snapshot builder
    assert result["city"] == "nyc"                 # city slug is preserved exactly
    assert result["station_id"] == "72"            # station_id is cast to string (GBFS may return int)
    assert result["num_bikes_available"] == 12     # bikes_available is preserved as int
    assert result["num_docks_available"] == 27     # docks_available is preserved as int
    assert result["snapshot_time"] == TS           # timestamp is passed through unchanged
    assert "is_renting" in result                  # is_renting field must always be present in the record

# ── Test 2: TFL snapshot schema ───────────────────────────────
def test_build_snapshot_tfl_schema():              # verify _build_snapshot_tfl outputs the same schema as GBFS
    station = {                                    # mock TFL BikePoint dict (matches BikePoint API response shape)
        "id": "BikePoints_1",                      # TFL station identifier
        "commonName": "River Street, Clerkenwell", # human-readable TFL station name
        "additionalProperties": [                  # TFL encodes live counts in an additionalProperties list
            {"key": "NbBikes",      "value": "8"},  # available bikes at this docking point
            {"key": "NbEmptyDocks", "value": "11"}, # empty docking spaces available
        ],
    }
    result = _build_snapshot_tfl("london", station, TS)  # call the TFL snapshot builder
    assert result["city"] == "london"              # city is always "london" for TFL stations
    assert result["station_id"] == "BikePoints_1"  # station_id comes from the TFL id field
    assert result["num_bikes_available"] == 8      # extracted and cast to int from additionalProperties
    assert result["num_docks_available"] == 11     # extracted and cast to int from additionalProperties
    assert result["snapshot_time"] == TS           # timestamp is passed through unchanged

# ── Test 3: ParseMessage — valid JSON ─────────────────────────
def test_parse_message_valid():                    # verify ParseMessage DoFn correctly decodes valid JSON bytes
    record = {                                     # valid station snapshot record as a Python dict
        "city": "nyc", "station_id": "72", "station_name": "W 52 St & 11 Ave",
        "num_bikes_available": 12, "num_docks_available": 27,
        "is_renting": True, "snapshot_time": TS,
    }
    raw    = json.dumps(record).encode("utf-8")    # serialise to UTF-8 JSON bytes (as Pub/Sub delivers)
    dofn   = ParseMessage()                        # instantiate the DoFn
    output = list(dofn.process(raw))               # call process and collect all yielded elements
    assert len(output) == 1                        # exactly one output element expected per valid message
    assert output[0]["city"] == "nyc"              # city field is preserved through JSON round-trip
    assert output[0]["num_bikes_available"] == 12  # numeric field is preserved

# ── Test 4: ParseMessage — malformed JSON ─────────────────────
def test_parse_message_invalid():                  # verify ParseMessage silently drops malformed bytes
    raw    = b"not valid json {"                   # deliberately malformed JSON bytes
    dofn   = ParseMessage()                        # instantiate the DoFn
    output = list(dofn.process(raw))               # call process and collect all yielded elements
    assert output == []                            # no output — malformed messages are silently dropped (no crash)

# ── Test 5: DirectRunner end-to-end pipeline ──────────────────
def test_windowed_pipeline_direct():               # verify the full pipeline runs on DirectRunner with test data
    import apache_beam as beam                     # import inside test to respect importorskip at module level
    from apache_beam.testing.test_pipeline import TestPipeline  # test-friendly pipeline that uses DirectRunner

    config = _load_config()                        # load real config from config/gcp_config.yaml

    test_messages = [                              # three synthetic station snapshots covering two cities
        json.dumps({                               # NYC snapshot 1: 12 bikes at 09:00
            "city": "nyc", "station_id": "72", "station_name": "W 52 St & 11 Ave",
            "num_bikes_available": 12, "num_docks_available": 27,
            "is_renting": True, "snapshot_time": "2026-05-15T09:00:00+00:00",
        }).encode(),
        json.dumps({                               # NYC snapshot 2: 10 bikes at 09:01 (same station, same window)
            "city": "nyc", "station_id": "72", "station_name": "W 52 St & 11 Ave",
            "num_bikes_available": 10, "num_docks_available": 29,
            "is_renting": True, "snapshot_time": "2026-05-15T09:01:00+00:00",
        }).encode(),
        json.dumps({                               # DC snapshot: different city → different aggregation key
            "city": "dc", "station_id": "31000", "station_name": "Eads St & 15th St S",
            "num_bikes_available": 5, "num_docks_available": 10,
            "is_renting": True, "snapshot_time": "2026-05-15T09:00:00+00:00",
        }).encode(),
    ]

    rows_written: list[dict] = []                  # list to capture BQ rows emitted by the pipeline

    def _capture(row: dict) -> dict:               # passthrough that also appends to rows_written for assertion
        rows_written.append(row)                   # capture the row before discarding it
        return row                                 # return unchanged so beam.Map can pass it downstream

    capture_sink = beam.Map(_capture)              # injected sink: captures rows without writing to BigQuery

    with TestPipeline() as p:                      # DirectRunner test pipeline (synchronous, in-process)
        build_pipeline(                            # wire the full DAG with test data and capture sink
            p,
            config,
            test_messages=test_messages,           # 3 synthetic messages replace the Pub/Sub source
            sink=capture_sink,                     # capture sink replaces WriteToBigQuery (no GCP call)
        )
    # Pipeline has run synchronously at this point; rows_written contains all BQ rows produced
    assert len(rows_written) == 2                  # two unique (city, station_id) keys → two aggregated BQ rows
    cities_in_output = {r["city"] for r in rows_written}  # extract city slugs from captured rows
    assert "nyc" in cities_in_output               # NYC window row was produced
    assert "dc"  in cities_in_output               # DC window row was produced
    nyc_row = next(r for r in rows_written if r["city"] == "nyc")  # find the NYC aggregated row
    assert nyc_row["total_snapshots"] == 2         # two NYC snapshots were aggregated in the window
    assert nyc_row["avg_bikes_available"] == 11.0  # average of 12 and 10 bikes across the two snapshots
    assert nyc_row["min_bikes_available"] == 10    # minimum bikes seen in the window
    assert nyc_row["max_bikes_available"] == 12    # maximum bikes seen in the window
