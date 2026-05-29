import pytest                                               # pytest fixture registration
import sys                                                 # stdlib for path manipulation
import os                                                  # stdlib for path joining
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cost-audit"))  # make cost-audit/ importable regardless of invocation directory


@pytest.fixture(scope="session")                           # session-scoped: applies to all async tests in one run
def anyio_backend():                                       # anyio pytest plugin reads this to choose the event loop
    return "asyncio"                                       # use Python's stdlib asyncio backend (no trio needed)
