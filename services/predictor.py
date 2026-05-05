# ── Imports ─────────────────────────────────────────────────────────
from typing import List, Dict                                         # type hints for service interface

from models.predict import load_artifacts, predict                    # reuse inference utilities (no duplication)


# ── Artifact Cache (Lazy Singleton) ─────────────────────────────────
# Artifacts are loaded on first use, not at import time, so that:
#  - importing this module does not crash if .pkl files are missing
#  - tests and tooling can import without requiring a trained model
#  - the cost of loading is paid once, then cached for the process lifetime
_artifacts = None                                                     # module-level cache, populated lazily


def _get_artifacts():
    """Load model artifacts on first call; return the cached pair afterwards."""
    global _artifacts                                                 # mutate module-level cache
    if _artifacts is None:                                            # only load on first invocation
        _artifacts = load_artifacts()                                 # (model, feature_columns)
    return _artifacts                                                 # cached tuple for subsequent calls


# ── Service Layer ───────────────────────────────────────────────────

def predict_service(data: List[Dict]) -> List[float]:
    """Service-layer prediction orchestrator.

    Parameters:
        data: list of input records (each a dict of features)

    Returns:
        list of predicted bike demand values (JSON-serializable floats)

    Design purpose:
        - Decouples API layer from ML logic
        - Centralizes prediction orchestration
        - Hook point for future logging / monitoring / A/B testing
    """
    model, feature_columns = _get_artifacts()                         # lazy-load artifacts (cached after first call)
    predictions = predict(                                            # delegate to shared inference function
        data=data,                                                    # input data passed through from API layer
        model=model,                                                  # cached trained model
        feature_columns=feature_columns,                              # cached schema for column alignment
    )
    return predictions.tolist()                                       # convert numpy array to list for JSON response
