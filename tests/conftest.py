import pytest                                                           # test framework
import sys                                                              # stdlib for path and module manipulation
import os                                                               # stdlib for path joining
from unittest.mock import MagicMock                                     # used to stub optional Cloud SDK dependencies
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cost-audit"))  # make cost-audit/ importable regardless of invocation directory

# ── Cloud SDK stubs ───────────────────────────────────────────────────────────
# cost-audit/checks.py and cost-audit/main.py import several Google Cloud SDK
# packages at module level.  The main requirements.txt (used by the CI pytest
# job) does NOT include those packages — they live only in
# cost-audit/requirements.txt.  We stub every affected module here so that
# Python's import machinery satisfies the `import X` statements without
# needing the real SDK installed.
#
# Stubs are inserted with setdefault so a real SDK installation always wins.
# All stubs are plain MagicMock() except functions_framework.http, which must
# be an identity decorator so audit() keeps its real return signature.

_ff_stub = MagicMock()                                                 # top-level functions_framework stub object
_ff_stub.http = lambda fn: fn                                          # .http used as @decorator — identity preserves the real function
sys.modules.setdefault("functions_framework", _ff_stub)                # stub only when real SDK is absent

# google.auth — credential resolution used in checks._get_auth_headers
sys.modules.setdefault("google", MagicMock())                          # top-level google namespace
sys.modules.setdefault("google.auth", MagicMock())                     # ADC credential resolution
sys.modules.setdefault("google.auth.transport", MagicMock())           # transport sub-package
sys.modules.setdefault("google.auth.transport.requests", MagicMock())  # Request transport object

# google.cloud — client libraries used in checks.py
sys.modules.setdefault("google.cloud", MagicMock())                    # google.cloud namespace
sys.modules.setdefault("google.cloud.artifactregistry_v1", MagicMock())  # Artifact Registry client
sys.modules.setdefault("google.cloud.compute_v1", MagicMock())         # Compute Engine client
sys.modules.setdefault("google.cloud.bigquery", MagicMock())           # BigQuery client
sys.modules.setdefault("google.cloud.storage", MagicMock())            # GCS client
sys.modules.setdefault("google.cloud.secretmanager", MagicMock())      # Secret Manager (local import inside audit())


@pytest.fixture(scope="session")                                        # session-scoped: applies to all async tests in one run
def anyio_backend():                                                    # anyio pytest plugin reads this to choose the event loop
    return "asyncio"                                                    # use Python's stdlib asyncio backend (no trio needed)
