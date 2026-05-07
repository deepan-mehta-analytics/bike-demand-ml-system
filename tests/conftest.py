import pytest                                               # pytest fixture registration


@pytest.fixture(scope="session")                           # session-scoped: applies to all async tests in one run
def anyio_backend():                                       # anyio pytest plugin reads this to choose the event loop
    return "asyncio"                                       # use Python's stdlib asyncio backend (no trio needed)
