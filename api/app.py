# ── Imports ─────────────────────────────────────────────────────────
from typing import List                                    # type hint for batch request payload
from fastapi import FastAPI                                # web framework powering the prediction API
from pydantic import BaseModel                             # base class for request schema validation

from services.predictor import predict_service            # service-layer prediction orchestrator


# ── Input Schema ────────────────────────────────────────────────────

class BikePredictionInput(BaseModel):                      # one record of model inputs
    DATE: str                                              # date in DD/MM/YYYY format
    HOUR: int                                              # hour of day (0-23)
    TEMPERATURE: float                                     # temperature in Celsius
    HUMIDITY: int                                          # relative humidity percentage
    WIND_SPEED: float                                      # wind speed in m/s
    VISIBILITY: int                                        # visibility distance (10m units)
    DEW_POINT_TEMPERATURE: float                           # dew point temperature in Celsius
    SOLAR_RADIATION: float                                 # solar radiation level (MJ/m^2)
    RAINFALL: float                                        # rainfall amount in mm
    SNOWFALL: float                                        # snowfall amount in cm
    SEASONS: str                                           # season category (Spring/Summer/Autumn/Winter)
    HOLIDAY: str                                           # holiday flag (Holiday / No Holiday)
    FUNCTIONING_DAY: str                                   # whether the rental system is operational (Yes/No)


class PredictionRequest(BaseModel):                        # batch wrapper for multiple input records
    data: List[BikePredictionInput]                        # list of records to predict on


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI()                                            # create the FastAPI application instance


# ── Health Check ────────────────────────────────────────────────────

@app.get("/")                                              # root endpoint exposed for health checks
def home():
    return {"message": "Bike Demand Prediction API is running"}  # simple response confirming service is up


# ── Prediction Endpoint ─────────────────────────────────────────────

@app.post("/predict")                                      # POST endpoint for generating predictions
def make_prediction(request: PredictionRequest):
    """Validate input via Pydantic, delegate to the service layer, return predictions."""
    input_data = [item.model_dump() for item in request.data]  # convert Pydantic models to plain dicts
    predictions = predict_service(input_data)              # invoke service-layer prediction
    return {"predictions": predictions}                    # return predictions as JSON response
