# ── Imports ───────────────────────────────────────────────────────────────
from unittest.mock import patch                               # patch predict_service without loading model files

import pytest                                                 # test runner and mark decorator
from httpx import ASGITransport, AsyncClient                  # in-process ASGI transport for async HTTP testing

from api.app import app                                       # FastAPI application under test


# ── Shared Fixture Data ───────────────────────────────────────────────────

VALID_RECORD = {                                              # one complete, correctly-typed input record
    "DATE": "01/01/2018",                                     # DD/MM/YYYY — winter date
    "HOUR": 8,                                                # integer hour (0-23)
    "TEMPERATURE": 5.0,                                       # float Celsius
    "HUMIDITY": 30,                                           # integer percent
    "WIND_SPEED": 1.5,                                        # float m/s
    "VISIBILITY": 2000,                                       # integer 10m units
    "DEW_POINT_TEMPERATURE": -3.0,                            # float Celsius
    "SOLAR_RADIATION": 0.1,                                   # float MJ/m^2
    "RAINFALL": 0.0,                                          # float mm
    "SNOWFALL": 0.0,                                          # float cm
    "SEASONS": "Winter",                                      # categorical string
    "HOLIDAY": "No Holiday",                                  # categorical string
    "FUNCTIONING_DAY": "Yes",                                 # categorical string
}


# ── Health Check ──────────────────────────────────────────────────────────

@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_health_check_returns_200():
    """GET / must return HTTP 200 with a status message key."""
    async with AsyncClient(                                   # in-process client — no network socket opened
        transport=ASGITransport(app=app),                     # route requests directly into the ASGI app
        base_url="http://test",                               # placeholder base URL required by httpx
    ) as client:
        response = await client.get("/")                      # hit the health-check route
    assert response.status_code == 200                        # service must respond OK
    assert "message" in response.json()                       # response body must carry the message key


# ── Valid Input → 200 ─────────────────────────────────────────────────────

@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_valid_single_record_returns_200():
    """POST /predict with one valid record must return 200 and a single prediction."""
    async with AsyncClient(
        transport=ASGITransport(app=app),                     # in-process ASGI transport
        base_url="http://test",
    ) as client:
        with patch("api.app.predict_service", return_value=[605.0]):  # mock service layer; no .pkl files needed
            response = await client.post(
                "/predict",
                json={"city": "Seoul", "data": [VALID_RECORD]},  # explicit city field + single record
            )
    assert response.status_code == 200                        # must succeed
    body = response.json()                                    # parse response body
    assert "predictions" in body                              # response must carry 'predictions' key
    assert len(body["predictions"]) == 1                      # one input record → one prediction


@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_valid_batch_returns_200():
    """POST /predict with two valid records must return 200 and two predictions."""
    async with AsyncClient(
        transport=ASGITransport(app=app),                     # in-process ASGI transport
        base_url="http://test",
    ) as client:
        with patch("api.app.predict_service", return_value=[605.0, 435.0]):  # mock two predictions
            response = await client.post(
                "/predict",
                json={"city": "Seoul", "data": [VALID_RECORD, VALID_RECORD]},  # two records
            )
    assert response.status_code == 200                        # must succeed
    body = response.json()                                    # parse response body
    assert len(body["predictions"]) == 2                      # two records → two predictions


@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_city_field_defaults_to_seoul():
    """POST /predict without a city field must default to Seoul and route correctly."""
    async with AsyncClient(
        transport=ASGITransport(app=app),                     # in-process ASGI transport
        base_url="http://test",
    ) as client:
        with patch("api.app.predict_service", return_value=[500.0]) as mock_svc:  # capture call arguments
            response = await client.post(
                "/predict",
                json={"data": [VALID_RECORD]},                # omit city — Pydantic default should apply
            )
    assert response.status_code == 200                        # must not error on missing optional city field
    _, kwargs = mock_svc.call_args                            # inspect the keyword args passed to mock
    assert kwargs.get("city") == "seoul"                      # city must be lowercased to "seoul" by the endpoint


# ── Invalid Input → 422 ───────────────────────────────────────────────────

@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_invalid_hour_type_returns_422():
    """POST /predict with HOUR as a non-integer string must return HTTP 422."""
    bad_record = {**VALID_RECORD, "HOUR": "not-an-int"}       # override HOUR with a string — invalid type
    async with AsyncClient(
        transport=ASGITransport(app=app),                     # in-process ASGI transport
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/predict",
            json={"city": "Seoul", "data": [bad_record]},     # Pydantic validation should reject HOUR type
        )
    assert response.status_code == 422                        # Pydantic must return 422 Unprocessable Entity


@pytest.mark.anyio                                            # anyio runs this coroutine on asyncio
async def test_missing_required_field_returns_422():
    """POST /predict with a missing required field must return HTTP 422."""
    incomplete = {k: v for k, v in VALID_RECORD.items() if k != "TEMPERATURE"}  # drop TEMPERATURE
    async with AsyncClient(
        transport=ASGITransport(app=app),                     # in-process ASGI transport
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/predict",
            json={"city": "Seoul", "data": [incomplete]},     # Pydantic validation should reject missing field
        )
    assert response.status_code == 422                        # Pydantic must return 422 Unprocessable Entity
