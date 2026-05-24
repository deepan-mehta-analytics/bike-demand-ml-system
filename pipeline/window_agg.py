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
