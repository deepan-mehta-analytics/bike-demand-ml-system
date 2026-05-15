# ── Imports ─────────────────────────────────────────────────────────────────
import hashlib                                                         # SHA-256 fingerprint of input payload for log correlation
import json                                                            # serialize log records as single-line JSON to stdout
import logging                                                         # standard library structured logging
import time                                                            # wall-clock latency measurement
from pathlib import Path                                               # check artifact directory existence
from typing import Dict, List                                          # type hints for cache and service interface

from models.predict import load_artifacts, predict                     # inference utilities from ML layer


# ── JSON Log Formatter ───────────────────────────────────────────────────────
class _JsonFormatter(logging.Formatter):                               # emit each log record as a single JSON line to stdout
    def format(self, record: logging.LogRecord) -> str:               # override default text formatting
        try:
            payload = json.loads(record.getMessage())                  # parse structured payload when message is a JSON string
        except (json.JSONDecodeError, TypeError):
            payload = {"message": record.getMessage()}                 # fallback: treat message as plain text
        payload["severity"] = record.levelname                         # Cloud Logging severity field (INFO/WARNING/ERROR)
        payload["logger"]   = record.name                              # module path for log-based filtering
        return json.dumps(payload)                                     # single-line JSON; Cloud Run stdout → Cloud Logging (free)


# ── Logger Setup ─────────────────────────────────────────────────────────────
_handler = logging.StreamHandler()                                     # write to stdout; Cloud Run captures stdout for Cloud Logging
_handler.setFormatter(_JsonFormatter())                                # apply JSON format to every emitted record
logger = logging.getLogger(__name__)                                   # module-level logger keyed to services.predictor
logger.addHandler(_handler)                                            # attach the JSON handler to this logger
logger.propagate = False                                               # prevent double-emission to root logger

# ── Per-City Artifact Cache ──────────────────────────────────────────────────
# Artifacts are loaded on first call for each city, then cached for the process lifetime.
#
# Design rationale:
#   - Importing this module never crashes even if .pkl files are absent
#   - Each city's artifacts are loaded once per process, not on every request
#   - New cities are added to the cache on their first request with no restart required
#   - Cities without trained artifacts fall back to Seoul to avoid crashes

_cache: Dict[str, tuple] = {}                                          # keyed by lowercase city name -> (model, schema)
_FALLBACK_CITY = "seoul"                                               # default city when requested city has no artifacts

# Maps display-name slugs sent by clients to the artifact directory key.
# R Shiny sends tolower(CITY_ASCII), which may not match the training --city flag.
# E.g. "new york" -> artifact at models/artifacts/nyc/
#      "washington dc" -> artifact at models/artifacts/dc/
_CITY_SLUG_MAP: Dict[str, str] = {
    "new york":      "nyc",   # Citi Bike; matches --city nyc training flag
    "washington dc": "dc",    # Capital Bikeshare; matches --city dc training flag
}


def _resolve_city_key(city: str) -> str:
    """Normalise a raw city string to the artifact directory key."""
    raw = city.lower().strip()                                         # lowercase + strip whitespace
    return _CITY_SLUG_MAP.get(raw, raw)                               # apply slug map; return as-is if not in map


def _artifact_dir_exists(city: str) -> bool:
    """Return True if models/artifacts/<city>/ contains at least one .pkl file."""
    artifact_dir = Path("models/artifacts") / city                    # expected artifact subdirectory for this city
    return artifact_dir.is_dir() and any(artifact_dir.glob("*.pkl"))  # True only when directory exists and has pkl files


def _get_artifacts(city: str) -> tuple:
    """Return (model, feature_columns) for a city; load from disk on first call.

    Falls back to Seoul artifacts if no trained model exists for the requested city.
    """
    key = _resolve_city_key(city)                                      # normalise: lowercase + apply slug map (e.g. "new york" -> "nyc")
    if key not in _cache:                                              # only load when city not yet in cache
        if not _artifact_dir_exists(key):                              # check whether trained artifacts exist on disk
            logger.warning(                                            # warn; do not raise so the API keeps serving
                "No artifacts found for city '%s' — falling back to '%s' model.",
                key, _FALLBACK_CITY,
            )
            key = _FALLBACK_CITY                                       # reroute to fallback city for artifact load
        if key not in _cache:                                          # fallback city might not be cached yet either
            _cache[key] = load_artifacts(city=key)                     # populate cache entry from disk artifacts
    return _cache[key]                                                 # return cached (model, feature_columns) tuple


# ── Service Layer ────────────────────────────────────────────────────────────

def predict_service(data: List[Dict], city: str = "seoul") -> List[float]:
    """Service-layer prediction orchestrator.

    Parameters:
        data: list of input records (each a dict of features matching Seoul schema)
        city: lowercase city identifier — must match a trained artifact directory
              under models/artifacts/<city>/ (default: "seoul")

    Returns:
        list of predicted hourly bike demand values (JSON-serializable floats)

    Design purpose:
        - Decouples API layer from ML logic
        - Centralises per-city routing and lazy artifact loading
        - Hook point for future logging, monitoring, or A/B testing
    """
    t0 = time.perf_counter()                                           # record wall-clock start for latency measurement
    inputs_hash = hashlib.sha256(                                      # fingerprint the payload for request correlation
        json.dumps(data, sort_keys=True).encode()                      # serialise with sorted keys for deterministic hash
    ).hexdigest()[:12]                                                 # first 12 hex chars — sufficient for correlation
    model, feature_columns = _get_artifacts(city)                      # lazy-load and cache city-specific artifacts
    predictions = predict(                                             # delegate to shared inference pipeline
        data=data,                                                     # input records passed through from API layer
        model=model,                                                   # cached trained model for this city
        feature_columns=feature_columns,                               # cached schema for column alignment
    )
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)          # wall-clock ms from call entry to numpy output
    logger.info(json.dumps({                                           # emit structured prediction event → Cloud Logging (free)
        "event":       "prediction",                                   # event type label for log-based filtering
        "city":        city,                                           # resolved city slug after fallback check
        "n_records":   len(data),                                      # number of input rows scored this call
        "inputs_hash": inputs_hash,                                    # 12-char hash for cross-log request correlation
        "latency_ms":  latency_ms,                                     # end-to-end inference latency in milliseconds
    }))
    return predictions.tolist()                                        # convert numpy array to JSON-serializable list
