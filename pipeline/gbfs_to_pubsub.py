# ── Imports ───────────────────────────────────────────────────
import json                               # JSON serialisation for records and structured log payloads
import logging                            # Python stdlib logger; stdout captured by Cloud Logging (free)
import os                                 # environment variable access for USE_PUBSUB flag
import time                               # sleep between poll cycles
from datetime import datetime, timezone   # UTC timestamp generation for each snapshot
from pathlib import Path                  # platform-safe path construction for the config file
from typing import Any                    # type hints for dict values

import requests                           # HTTP client for GBFS and TFL API calls
import yaml                               # YAML config parser for gcp_config.yaml

# ── Logger Setup ──────────────────────────────────────────────
class _JsonFormatter(logging.Formatter):  # custom formatter: output one structured JSON line per log record
    def format(self, record: logging.LogRecord) -> str:  # override to produce single-line JSON
        try:                                              # attempt to parse message as a JSON dict
            payload = json.loads(record.getMessage())    # structured call: message is pre-serialised JSON
        except (json.JSONDecodeError, TypeError):         # plain-text message; wrap it in a dict
            payload = {"message": record.getMessage()}   # fallback shape for non-structured logs
        payload["severity"] = record.levelname           # add Cloud Logging severity field
        payload["logger"]   = record.name                # add logger name for filtering in Cloud Logging
        return json.dumps(payload)                        # emit as a single-line JSON string to stdout

_handler = logging.StreamHandler()               # write log records to stdout (captured by Cloud Run)
_handler.setFormatter(_JsonFormatter())          # attach the JSON formatter to the handler
logger = logging.getLogger(__name__)             # module-level logger named after this file
logger.addHandler(_handler)                      # register the JSON stdout handler
logger.propagate = False                         # prevent duplicate output via the root logger
logger.setLevel(logging.INFO)                    # capture INFO, WARNING, ERROR and above

# ── Config ────────────────────────────────────────────────────
_CONFIG_PATH = (                                   # absolute path to YAML config relative to this file
    Path(__file__).parent.parent / "config" / "gcp_config.yaml"
)

def _load_config() -> dict[str, Any]:              # load GCP + GBFS config from the YAML file on disk
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:  # open config file for reading
        return yaml.safe_load(f)                   # parse YAML safely and return as a nested dict

# ── GBFS Fetch ────────────────────────────────────────────────
def _fetch_gbfs(url: str) -> list[dict[str, Any]]:  # fetch a standard GBFS station_status.json endpoint
    resp = requests.get(url, timeout=10)            # HTTP GET with 10-second timeout
    resp.raise_for_status()                         # raise HTTPError on any 4xx or 5xx response
    data = resp.json()                              # parse JSON response body into a dict
    return data.get("data", {}).get("stations", []) # extract the stations list from the GBFS envelope

# ── TFL Fetch ─────────────────────────────────────────────────
def _fetch_tfl(url: str) -> list[dict[str, Any]]:  # fetch the TFL BikePoint API (non-standard GBFS format)
    resp = requests.get(url, timeout=10)            # HTTP GET with 10-second timeout
    resp.raise_for_status()                         # raise HTTPError on any 4xx or 5xx response
    return resp.json()                              # return the raw list; each item is a BikePoint station

# ── Snapshot Builders ─────────────────────────────────────────
def _build_snapshot_gbfs(
    city: str,
    station: dict[str, Any],
    ts: str,
) -> dict[str, Any]:                               # normalise a standard GBFS station dict to the common record schema
    return {                                        # return a flat snapshot record
        "city":                city,               # city slug (e.g. "nyc", "dc", "chicago")
        "station_id":          str(station.get("station_id", "")),         # unique station ID cast to string
        "station_name":        station.get("name", ""),                    # human-readable station name
        "num_bikes_available": int(station.get("num_bikes_available", 0)), # bikes currently available at dock
        "num_docks_available": int(station.get("num_docks_available", 0)), # empty dock slots available
        "is_renting":          bool(station.get("is_renting", False)),     # station is actively renting bikes
        "snapshot_time":       ts,                 # ISO 8601 UTC timestamp for this poll snapshot
    }

def _build_snapshot_tfl(
    city: str,
    station: dict[str, Any],
    ts: str,
) -> dict[str, Any]:                               # normalise a TFL BikePoint dict to the common record schema
    props = {                                       # flatten the additionalProperties list into a key→value dict
        p["key"]: p["value"]
        for p in station.get("additionalProperties", [])
    }
    bikes_available = int(props.get("NbBikes",      0))   # number of available bikes at this docking point
    docks_available = int(props.get("NbEmptyDocks", 0))   # number of empty docking spaces
    return {                                        # return a flat snapshot record using the common schema
        "city":                city,               # "london"
        "station_id":          station.get("id", ""),            # TFL station identifier (e.g. "BikePoints_1")
        "station_name":        station.get("commonName", ""),    # human-readable station name
        "num_bikes_available": bikes_available,    # bikes currently at this station
        "num_docks_available": docks_available,    # empty docking spaces available
        "is_renting":          bikes_available > 0,  # treat as renting when any bikes are present
        "snapshot_time":       ts,                 # ISO 8601 UTC timestamp for this poll snapshot
    }

# ── Publisher (USE_PUBSUB=true path) ──────────────────────────
def _publish(
    publisher: Any,
    topic_path: str,
    records: list[dict[str, Any]],
) -> None:                                         # publish a list of snapshot records to a Cloud Pub/Sub topic
    for record in records:                         # iterate over each station snapshot record
        data = json.dumps(record).encode("utf-8")  # serialise record to UTF-8 JSON bytes (Pub/Sub payload)
        future = publisher.publish(topic_path, data)  # publish message; returns a concurrent.futures.Future
        future.result()                            # block until the publish is acknowledged by the server

# ── Local Output (USE_PUBSUB=false path) ──────────────────────
def _log_local(city: str, records: list[dict[str, Any]]) -> None:  # print records to stdout for local/test mode
    for record in records:                         # iterate over each station snapshot record
        print(json.dumps(record))                  # print as a single-line JSON string to stdout

# ── Poll Once ─────────────────────────────────────────────────
def poll_once(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:  # poll all cities; return {city_key: [records]}
    ts = datetime.now(timezone.utc).isoformat()   # capture current UTC timestamp for this poll round
    cities = config["gbfs"]["cities"]              # dict of city configs loaded from gcp_config.yaml
    results: dict[str, list[dict[str, Any]]] = {} # accumulator: city_key → list of station snapshot dicts
    for city_key, city_cfg in cities.items():      # iterate over each configured city
        url     = city_cfg["url"]                  # GBFS or TFL endpoint URL from config
        adapter = city_cfg.get("adapter", "gbfs")  # adapter type: "tfl" for London, "gbfs" for all others
        try:                                        # attempt to fetch live station data for this city
            if adapter == "tfl":                    # London uses the TFL BikePoint format (non-standard GBFS)
                raw     = _fetch_tfl(url)           # fetch TFL station list as raw JSON list
                records = [_build_snapshot_tfl(city_key, s, ts) for s in raw]  # normalise all TFL stations
            else:                                   # all other cities use standard GBFS station_status.json
                raw     = _fetch_gbfs(url)          # fetch GBFS station_status list
                records = [_build_snapshot_gbfs(city_key, s, ts) for s in raw]  # normalise all GBFS stations
            results[city_key] = records             # store normalised records under the city key
            logger.info(json.dumps({                # structured log: one line per city per poll cycle
                "event": "poll_cycle",              # event type identifier for log filtering
                "city":  city_key,                  # which city was polled this round
                "count": len(records),              # number of station records fetched
                "ts":    ts,                        # snapshot timestamp shared across all records in this round
            }))
        except Exception as exc:                    # catch any HTTP, parse, or network error
            logger.warning(json.dumps({             # structured warning — do not crash the poller on one city
                "event": "poll_error",             # event type identifier
                "city":  city_key,                 # which city failed this round
                "error": str(exc),                 # error message for debugging
            }))
            results[city_key] = []                 # store empty list so caller sees a consistent dict shape
    return results                                  # return all city results for this poll round

# ── Pub/Sub Publish ───────────────────────────────────────────
def _run_pubsub_publish(
    config: dict[str, Any],
    results: dict[str, list[dict[str, Any]]],
) -> None:                                         # publish all poll results to Cloud Pub/Sub
    from google.cloud import pubsub_v1             # deferred import: only loaded when USE_PUBSUB=true
    publisher  = pubsub_v1.PublisherClient()       # create the Cloud Pub/Sub publisher client
    project_id = config["project_id"]             # GCP project ID from config
    topic_name = config["pubsub"]["topic"]        # Pub/Sub topic name from config
    topic_path = publisher.topic_path(project_id, topic_name)  # fully qualified topic resource name
    for city_key, records in results.items():      # iterate over each city's records
        if records:                                # only publish non-empty result sets
            _publish(publisher, topic_path, records)  # send all records for this city to Pub/Sub

# ── Poller Main Loop ──────────────────────────────────────────
def run_poller() -> None:                          # main loop: poll all cities → publish or print → sleep
    config     = _load_config()                    # load GCP + GBFS config from gcp_config.yaml
    use_pubsub = os.getenv("USE_PUBSUB", "false").lower() == "true"  # USE_PUBSUB=true → Cloud Pub/Sub publish
    interval   = config["gbfs"]["poll_interval_seconds"]              # seconds to sleep between poll rounds
    logger.info(json.dumps({                       # log poller startup configuration
        "event":      "poller_start",             # event type identifier
        "use_pubsub": use_pubsub,                 # whether Pub/Sub publishing is active
        "interval_s": interval,                   # configured poll interval
    }))
    while True:                                    # infinite loop — run until process is killed
        results = poll_once(config)                # poll all cities and collect station snapshots
        if use_pubsub:                             # USE_PUBSUB=true: send all records to Cloud Pub/Sub
            _run_pubsub_publish(config, results)   # publish all cities' records to the topic
        else:                                      # USE_PUBSUB=false: print to stdout for local dev / testing
            for city_key, records in results.items():  # iterate over each city's records
                _log_local(city_key, records)      # print each record as a JSON line to stdout
        time.sleep(interval)                       # wait for the configured interval before the next round

# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":                         # run the poller when executed via python -m pipeline.gbfs_to_pubsub
    run_poller()                                   # start the infinite poll loop
