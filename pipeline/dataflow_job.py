# ── Imports ───────────────────────────────────────────────────
import argparse                                    # CLI argument parsing for the --runner flag
import json                                        # JSON parsing for Pub/Sub message bytes
from datetime import datetime, timezone            # timestamp conversion for window boundary formatting
from pathlib import Path                           # platform-safe path construction for the config file
from typing import Any                             # type hints for dict values

import apache_beam as beam                         # Apache Beam distributed processing framework
import yaml                                        # YAML config parser for gcp_config.yaml
from apache_beam.transforms.window import FixedWindows, TimestampedValue  # windowing primitives

# ── Config ────────────────────────────────────────────────────
_CONFIG_PATH = (                                   # absolute path to YAML config relative to this file
    Path(__file__).parent.parent / "config" / "gcp_config.yaml"
)

def _load_config() -> dict[str, Any]:              # load GCP pipeline config from the YAML file on disk
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:  # open config for reading
        return yaml.safe_load(f)                   # parse YAML safely and return as a nested dict

# ── BQ Schema ─────────────────────────────────────────────────
BQ_SCHEMA = {                                      # BigQuery table schema for station_snapshots
    "fields": [
        {"name": "city",                "type": "STRING",    "mode": "REQUIRED"},  # city slug (nyc/dc/london/chicago)
        {"name": "station_id",          "type": "STRING",    "mode": "REQUIRED"},  # station identifier string
        {"name": "station_name",        "type": "STRING",    "mode": "NULLABLE"},  # human-readable station name
        {"name": "window_start",        "type": "TIMESTAMP", "mode": "REQUIRED"},  # start of 5-min aggregation window
        {"name": "window_end",          "type": "TIMESTAMP", "mode": "REQUIRED"},  # end of 5-min aggregation window
        {"name": "avg_bikes_available", "type": "FLOAT",     "mode": "NULLABLE"},  # mean bikes across snapshots in window
        {"name": "min_bikes_available", "type": "INTEGER",   "mode": "NULLABLE"},  # minimum bikes seen in window
        {"name": "max_bikes_available", "type": "INTEGER",   "mode": "NULLABLE"},  # maximum bikes seen in window
        {"name": "total_snapshots",     "type": "INTEGER",   "mode": "NULLABLE"},  # count of snapshots aggregated
    ]
}

# ── DoFn: Parse Message ────────────────────────────────────────
class ParseMessage(beam.DoFn):                     # Beam DoFn: parse raw message bytes into a snapshot dict
    def process(self, element: bytes):             # element is raw UTF-8 JSON bytes from Pub/Sub or beam.Create
        try:                                       # attempt to decode and parse the message
            yield json.loads(element.decode("utf-8"))  # decode bytes → parse JSON → emit dict downstream
        except (json.JSONDecodeError, UnicodeDecodeError):  # malformed or non-UTF-8 message
            pass                                   # silently drop bad messages; do not crash the pipeline

# ── CombineFn: Window Aggregation ─────────────────────────────
class WindowedAgg(beam.CombineFn):                 # Beam CombineFn: aggregate bike snapshots within a 5-min window
    def create_accumulator(self) -> tuple:         # return the initial empty accumulator (sum, min, max, count)
        return (0, None, None, 0)                  # sum=0, min=None (no data), max=None (no data), count=0

    def add_input(self, accumulator: tuple, element: dict) -> tuple:  # fold one snapshot into the accumulator
        total, mn, mx, count = accumulator         # unpack current accumulator state
        bikes = element["num_bikes_available"]     # bikes_available count from the snapshot record
        return (                                   # return updated accumulator with this snapshot included
            total + bikes,                         # running sum for computing the average
            bikes if mn is None else min(mn, bikes),  # running minimum across snapshots
            bikes if mx is None else max(mx, bikes),  # running maximum across snapshots
            count + 1,                             # increment snapshot count
        )

    def merge_accumulators(self, accumulators: list) -> tuple:  # merge partial accumulators from parallel workers
        totals = [a[0] for a in accumulators]      # collect sums from each partial accumulator
        mins   = [a[1] for a in accumulators if a[1] is not None]  # collect valid (non-None) minimums
        maxes  = [a[2] for a in accumulators if a[2] is not None]  # collect valid (non-None) maximums
        counts = [a[3] for a in accumulators]      # collect counts from each partial accumulator
        return (                                   # return merged global accumulator
            sum(totals),                           # combined sum across all partitions
            min(mins)  if mins  else None,         # global minimum; None if no partitions had data
            max(maxes) if maxes else None,         # global maximum; None if no partitions had data
            sum(counts),                           # combined snapshot count
        )

    def extract_output(self, accumulator: tuple) -> dict:  # convert final accumulator to output metrics dict
        total, mn, mx, count = accumulator         # unpack final accumulator state
        avg = round(total / count, 2) if count > 0 else None  # mean bikes; None if window had no snapshots
        return {                                   # return aggregated metrics dict for this (city, station) window
            "avg_bikes_available": avg,            # mean bikes available across the window
            "min_bikes_available": mn,             # minimum bikes seen in the window
            "max_bikes_available": mx,             # maximum bikes seen in the window
            "total_snapshots":     count,          # total snapshots aggregated in the window
        }

# ── DoFn: Format BQ Row ───────────────────────────────────────
class FormatBQRow(beam.DoFn):                      # Beam DoFn: format a windowed KV pair as a BigQuery row dict
    def process(                                   # process one (key, metrics) element; window injected by runner
        self,
        kv: tuple,
        window=beam.DoFn.WindowParam,              # runner injects the current IntervalWindow object
    ):
        key, metrics = kv                          # unpack the composite key and the aggregated metrics dict
        city, station_id, station_name = key       # unpack city slug, station identifier, human-readable name
        win_start_dt = window.start.to_utc_datetime()  # Beam Timestamp → naive UTC datetime for window start
        win_end_dt   = window.end.to_utc_datetime()    # Beam Timestamp → naive UTC datetime for window end
        if win_start_dt.tzinfo is None:            # normalise naive datetime to timezone-aware UTC
            win_start_dt = win_start_dt.replace(tzinfo=timezone.utc)  # add UTC timezone info
        if win_end_dt.tzinfo is None:              # normalise naive datetime to timezone-aware UTC
            win_end_dt = win_end_dt.replace(tzinfo=timezone.utc)     # add UTC timezone info
        yield {                                    # emit a flat dict matching BQ_SCHEMA
            "city":                city,           # city slug
            "station_id":          station_id,     # station identifier
            "station_name":        station_name,   # human-readable name
            "window_start":        win_start_dt.isoformat(),  # ISO 8601 UTC window start for BigQuery TIMESTAMP
            "window_end":          win_end_dt.isoformat(),    # ISO 8601 UTC window end for BigQuery TIMESTAMP
            "avg_bikes_available": metrics["avg_bikes_available"],  # mean bikes in window
            "min_bikes_available": metrics["min_bikes_available"],  # min bikes in window
            "max_bikes_available": metrics["max_bikes_available"],  # max bikes in window
            "total_snapshots":     metrics["total_snapshots"],      # snapshots aggregated in window
        }

# ── Pipeline Builder ───────────────────────────────────────────
def build_pipeline(
    p: beam.Pipeline,
    config: dict[str, Any],
    test_messages: list[bytes] | None = None,
    sink: beam.PTransform | None = None,
) -> None:                                         # wire the full Beam DAG; sink injection enables testing without GCP
    window_seconds = config["dataflow"]["window_seconds"]    # 5-min FixedWindow size from config
    project_id     = config["project_id"]                   # GCP project ID for BQ table reference
    bq_dataset     = config["bigquery"]["dataset"]           # BigQuery dataset name
    bq_table       = config["bigquery"]["table"]             # BigQuery table name
    subscription   = (                                       # fully qualified Pub/Sub subscription resource name
        f"projects/{project_id}/subscriptions/{config['pubsub']['subscription']}"
    )

    if test_messages is not None:                  # DirectRunner local mode: use caller-supplied test messages
        source = p | "CreateTestMessages" >> beam.Create(test_messages)  # inject bytes as a bounded PCollection
    else:                                          # DataflowRunner streaming mode: read live from Pub/Sub
        from apache_beam.io.gcp.pubsub import ReadFromPubSub  # deferred import; only loaded for DataflowRunner
        source = p | "ReadFromPubSub" >> ReadFromPubSub(subscription=subscription)  # streaming Pub/Sub source

    if sink is None:                               # production path: write aggregated rows to Cloud BigQuery
        from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition  # deferred GCP import
        sink = WriteToBigQuery(                    # create the BigQuery write transform
            table=f"{project_id}:{bq_dataset}.{bq_table}",  # fully qualified BQ table reference
            schema=BQ_SCHEMA,                      # column definitions matching the station_snapshots schema
            create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,  # auto-create table if absent
            write_disposition=BigQueryDisposition.WRITE_APPEND,       # append new window rows to table
        )

    (
        source
        | "ParseJSON"    >> beam.ParDo(ParseMessage())    # decode UTF-8 bytes → snapshot dict; drop malformed
        | "AddTimestamp" >> beam.Map(                     # attach event timestamp from the snapshot_time field
            lambda r: TimestampedValue(
                r,
                datetime.fromisoformat(r["snapshot_time"]).timestamp(),  # parse ISO UTC string → Unix seconds float
            )
        )
        | "Window"       >> beam.WindowInto(              # apply 5-minute fixed tumbling windows
            FixedWindows(window_seconds),
        )
        | "KeyByStation" >> beam.Map(                     # key each snapshot by (city, station_id, station_name)
            lambda r: (
                (r["city"], r["station_id"], r.get("station_name", "")),  # composite key tuple
                r,                                        # full record as value for the CombineFn
            )
        )
        | "AggPerWindow" >> beam.CombinePerKey(WindowedAgg())  # aggregate all snapshots per (city, station) per window
        | "FormatBQRow"  >> beam.ParDo(FormatBQRow())    # format windowed KV pair → BQ row dict with window timestamps
        | "WriteToBQ"    >> sink                          # write rows to BigQuery (or injected test sink)
    )

# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":                         # run the pipeline when executed via python -m pipeline.dataflow_job
    parser = argparse.ArgumentParser(              # set up CLI argument parser
        description="Bike demand GBFS → Pub/Sub → BigQuery streaming pipeline",
    )
    parser.add_argument(                           # --runner flag: which Beam runner to use
        "--runner",
        default="Direct",                          # default: local DirectRunner (zero GCP cost)
        choices=["Direct", "DataflowRunner"],      # only these two runners are supported
        help="Beam runner: Direct (local, free) or DataflowRunner (GCP, ~$0.05/hr)",
    )
    args, beam_args = parser.parse_known_args()    # parse known args; pass remainder through to Beam

    config = _load_config()                        # load GCP + pipeline config from gcp_config.yaml

    pipeline_opts: dict[str, Any] = {             # base pipeline options shared by both runners
        "runner":            args.runner,          # selected Beam runner
        "save_main_session": True,                 # pickle main session so Dataflow workers have all imports
        "streaming":         args.runner == "DataflowRunner",  # enable streaming mode only for Dataflow
    }

    if args.runner == "DataflowRunner":            # GCP-specific options: only required for DataflowRunner
        pipeline_opts.update({                     # merge Dataflow-specific options into the base dict
            "project":          config["project_id"],             # GCP project for the Dataflow job
            "region":           config["region"],                 # Dataflow job region (us-central1)
            "staging_location": config["dataflow"]["staging_bucket"],  # GCS staging path for job artefacts
            "temp_location":    config["dataflow"]["staging_bucket"],  # GCS temp path for intermediate data
            "max_num_workers":  config["dataflow"]["max_num_workers"], # cap workers at 1 to limit demo cost
            "machine_type":     config["dataflow"]["machine_type"],    # cheapest viable machine (n1-standard-1)
        })
        test_messages_arg = None                   # DataflowRunner reads from live Pub/Sub; no test messages

    else:                                          # DirectRunner: inject synthetic test messages for local validation
        test_messages_arg = [                      # three hardcoded station snapshots to exercise the full DAG
            json.dumps({                           # NYC station snapshot — first record
                "city": "nyc", "station_id": "72", "station_name": "W 52 St & 11 Ave",
                "num_bikes_available": 12, "num_docks_available": 27,
                "is_renting": True, "snapshot_time": "2026-05-15T09:00:00+00:00",
            }).encode(),
            json.dumps({                           # NYC station snapshot — second record (same station, +1 min)
                "city": "nyc", "station_id": "72", "station_name": "W 52 St & 11 Ave",
                "num_bikes_available": 10, "num_docks_available": 29,
                "is_renting": True, "snapshot_time": "2026-05-15T09:01:00+00:00",
            }).encode(),
            json.dumps({                           # DC station snapshot — different city, different aggregation key
                "city": "dc", "station_id": "31000", "station_name": "Eads St & 15th St S",
                "num_bikes_available": 5, "num_docks_available": 10,
                "is_renting": True, "snapshot_time": "2026-05-15T09:00:00+00:00",
            }).encode(),
        ]

    from apache_beam.options.pipeline_options import PipelineOptions  # deferred import after option dict is built
    options = PipelineOptions(**pipeline_opts, flags=beam_args)       # create Beam PipelineOptions from dict

    with beam.Pipeline(options=options) as p:      # create and execute the Beam pipeline in a context manager
        build_pipeline(p, config, test_messages=test_messages_arg)    # wire the full DAG with runtime config
