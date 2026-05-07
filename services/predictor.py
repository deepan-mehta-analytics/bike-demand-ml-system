# ── Imports ─────────────────────────────────────────────────────────────────
import logging                                                         # standard library logger for fallback warnings
from pathlib import Path                                               # check artifact directory existence
from typing import Dict, List                                          # type hints for cache and service interface

from models.predict import load_artifacts, predict                     # inference utilities from ML layer

logger = logging.getLogger(__name__)                                   # module-level logger; callers configure handlers

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


def _artifact_dir_exists(city: str) -> bool:
    """Return True if models/artifacts/<city>/ contains at least one .pkl file."""
    artifact_dir = Path("models/artifacts") / city                    # expected artifact subdirectory for this city
    return artifact_dir.is_dir() and any(artifact_dir.glob("*.pkl"))  # True only when directory exists and has pkl files


def _get_artifacts(city: str) -> tuple:
    """Return (model, feature_columns) for a city; load from disk on first call.

    Falls back to Seoul artifacts if no trained model exists for the requested city.
    """
    key = city.lower()                                                 # normalise case for consistent cache key lookup
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
    model, feature_columns = _get_artifacts(city)                      # lazy-load and cache city-specific artifacts
    predictions = predict(                                             # delegate to shared inference pipeline
        data=data,                                                     # input records passed through from API layer
        model=model,                                                   # cached trained model for this city
        feature_columns=feature_columns,                               # cached schema for column alignment
    )
    return predictions.tolist()                                        # convert numpy array to JSON-serializable list
