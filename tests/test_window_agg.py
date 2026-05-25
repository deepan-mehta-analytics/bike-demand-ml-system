# ── Imports ───────────────────────────────────────────────────
from datetime import datetime, timezone                       # UTC timestamps for window boundaries

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
