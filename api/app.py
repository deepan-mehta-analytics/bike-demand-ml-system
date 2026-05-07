# ── Imports ─────────────────────────────────────────────────────────────────
from typing import List                                                # type hint for batch record list
from fastapi import FastAPI                                            # web framework powering the inference API
from pydantic import BaseModel                                         # base class for request schema validation

from services.predictor import predict_service                         # service-layer prediction orchestrator


# ── Input Schema ─────────────────────────────────────────────────────────────

class BikePredictionInput(BaseModel):                                  # one weather/temporal record for a single hour
    DATE: str                                                          # date string in DD/MM/YYYY format
    HOUR: int                                                          # hour of day (0-23)
    TEMPERATURE: float                                                 # temperature in degrees Celsius
    HUMIDITY: int                                                      # relative humidity as a percentage
    WIND_SPEED: float                                                  # wind speed in m/s
    VISIBILITY: int                                                    # visibility in 10-metre units
    DEW_POINT_TEMPERATURE: float                                       # dew point temperature in Celsius
    SOLAR_RADIATION: float                                             # solar radiation in MJ/m^2
    RAINFALL: float                                                    # rainfall in mm
    SNOWFALL: float                                                    # snowfall in cm
    SEASONS: str                                                       # season label (Spring/Summer/Autumn/Winter)
    HOLIDAY: str                                                       # holiday flag (Holiday / No Holiday)
    FUNCTIONING_DAY: str                                               # system operational flag (Yes / No)


class PredictionRequest(BaseModel):                                    # top-level request: city + batch of hourly records
    city: str = "Seoul"                                                # city to predict for; must match a trained artifact
    data: List[BikePredictionInput]                                    # one or more hourly input records to score


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI()                                                        # create the FastAPI application instance


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/")                                                          # root path; polled by Docker and Shiny healthchecks
def home():
    return {"message": "Bike Demand Prediction API is running"}        # simple liveness confirmation response


# ── Prediction Endpoint ───────────────────────────────────────────────────────

@app.post("/predict")                                                  # POST endpoint for batch demand predictions
def make_prediction(request: PredictionRequest):
    """Validate input via Pydantic, dispatch to the service layer, return predictions."""
    city = request.city.lower()                                        # normalise city to lowercase for artifact lookup
    input_data = [item.model_dump() for item in request.data]          # convert Pydantic models to plain dicts
    predictions = predict_service(input_data, city=city)               # route to per-city artifacts via service layer
    return {"predictions": predictions}                                # return list of floats as JSON
