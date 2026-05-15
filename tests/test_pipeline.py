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
    from apache_beam.testing.test_pipeline import TestPipeline        # DirectRunner test pipeline
    from apache_beam.testing.util import assert_that                  # Beam-native PCollection assertion

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

    def check_bq_rows(rows):                       # custom matcher: validates row count and NYC aggregation values
        assert len(rows) == 2, f"Expected 2 BQ rows (nyc + dc), got {len(rows)}: {rows}"  # two unique (city, station) keys
        cities = {r["city"] for r in rows}         # extract city slugs from all produced rows
        assert "nyc" in cities, "nyc row missing"  # NYC station window row must be present
        assert "dc"  in cities, "dc row missing"   # DC station window row must be present
        nyc = next(r for r in rows if r["city"] == "nyc")  # find the NYC aggregated row
        assert nyc["total_snapshots"] == 2,        "NYC should aggregate 2 snapshots"        # two snapshots in window
        assert nyc["avg_bikes_available"] == 11.0, "NYC avg should be (12+10)/2 = 11.0"     # mean of 12 and 10
        assert nyc["min_bikes_available"] == 10,   "NYC min should be 10"                   # minimum observed
        assert nyc["max_bikes_available"] == 12,   "NYC max should be 12"                   # maximum observed

    with TestPipeline() as p:                      # DirectRunner test pipeline (synchronous, in-process)
        bq_rows = build_pipeline(                  # wire the full DAG; returns pre-sink PCollection for assertion
            p,
            config,
            test_messages=test_messages,           # 3 synthetic messages replace the live Pub/Sub source
            sink=beam.Map(lambda x: x),            # no-op sink: passes rows through without writing to BigQuery
        )
        assert_that(bq_rows, check_bq_rows)        # Beam-native assertion; runs inside the pipeline execution context
