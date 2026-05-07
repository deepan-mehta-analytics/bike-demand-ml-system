# ── Imports ─────────────────────────────────────────────────────────────────
from typing import Dict, List                                          # type hints for cache and service interface

from models.predict import load_artifacts, predict                     # inference utilities from ML layer


# ── Per-City Artifact Cache ──────────────────────────────────────────────────
# Artifacts are loaded on first call for each city, then cached for the process lifetime.
#
# Design rationale:
#   - Importing this module never crashes even if .pkl files are absent
#   - Each city's artifacts are loaded once per process, not on every request
#   - New cities are added to the cache on their first request with no restart required

_cache: Dict[str, tuple] = {}                                          # keyed by lowercase city name → (model, schema)


def _get_artifacts(city: str) -> tuple:
    """Return (model, feature_columns) for a city; load from disk on first call."""
    key = city.lower()                                                 # normalise case for consistent cache key lookup
    if key not in _cache:                                              # only load when city not yet in cache
        _cache[key] = load_artifacts(city=key)                         # populate cache entry from disk artifacts
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
