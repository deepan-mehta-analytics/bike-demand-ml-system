import pytest                                                           # test framework
import sys                                                              # stdlib for path and module manipulation
import os                                                               # stdlib for path joining
from unittest.mock import MagicMock                                     # used to stub optional Cloud SDK dependencies
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cost-audit"))  # make cost-audit/ importable regardless of invocation directory

# Stub functions_framework so cost-audit/main.py is importable in tests
# without the Cloud Functions SDK being installed in the project venv.
# The decorator @functions_framework.http must be a pass-through so that
# audit() stays callable and returns the real (body, status) tuple.
# A plain MagicMock() decorator would replace audit with a MagicMock object,
# causing "ValueError: not enough values to unpack" when tests call audit().
_ff_stub = MagicMock()                                                 # top-level stub module object
_ff_stub.http = lambda fn: fn                                          # .http used as @decorator — identity so the real function is preserved
sys.modules.setdefault("functions_framework", _ff_stub)                # only stubs if not already installed — real SDK takes precedence


@pytest.fixture(scope="session")                                        # session-scoped: applies to all async tests in one run
def anyio_backend():                                                    # anyio pytest plugin reads this to choose the event loop
    return "asyncio"                                                    # use Python's stdlib asyncio backend (no trio needed)
