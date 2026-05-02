# Import FastAPI framework to build API
from fastapi import FastAPI  # used to create API instance

# Import required libraries for model inference
import pandas as pd  # for handling input data
import joblib  # to load saved model and scaler

# Import feature engineering function
from models.features import create_features  # reuse same transformations as training

# Import Pydantic models for API requests and responses, used to define the structure of data sent in request and response
# And to validate the data received by API endpoints

from pydantic import BaseModel  # used to define structured input schema for API requests


# -------------------------------
# DEFINE INPUT SCHEMA
# -------------------------------

class BikePredictionInput(BaseModel):
    DATE: str  # date in DD/MM/YYYY format
    HOUR: int  # hour of day (0–23)
    TEMPERATURE: float  # temperature in Celsius
    HUMIDITY: int  # humidity percentage
    WIND_SPEED: float  # wind speed value
    VISIBILITY: int  # visibility distance
    DEW_POINT_TEMPERATURE: float  # dew point temperature
    SOLAR_RADIATION: float  # solar radiation level
    RAINFALL: float  # rainfall amount
    SNOWFALL: float  # snowfall amount
    SEASONS: str  # season category (e.g., Winter, Summer)
    HOLIDAY: str  # holiday indicator (Yes/No)
    FUNCTIONING_DAY: str  # system operational status (Yes/No)
    


# -------------------------------
# INITIALIZE FASTAPI APP
# -------------------------------

app = FastAPI()  # create API application instance


# -------------------------------
# LOAD MODEL ARTIFACTS
# -------------------------------

# Load trained model from disk
model = joblib.load("models/random_forest_model.pkl")  # load saved Random Forest model

# Load scaler used during training
scaler = joblib.load("models/scaler.pkl")  # load saved scaler

# Load feature column schema
feature_columns = joblib.load("models/feature_columns.pkl")  # load feature structure


# -------------------------------
# ROOT ENDPOINT (HEALTH CHECK)
# -------------------------------

@app.get("/")  # define root endpoint
def home():
    return {"message": "Bike Demand Prediction API is running"}  # simple health check response


# -------------------------------
# PREDICTION ENDPOINT
# -------------------------------

@app.post("/predict")  # define POST endpoint for predictions
def predict(data: BikePredictionInput):  # accept validated input schema
    
    # Convert validated input object to dictionary and wrap into DataFrame
    input_df = pd.DataFrame([data.model_dump()])  # use model_dump() for Pydantic v2

    # Preprocess the data

    # Apply feature engineering
    input_df = create_features(input_df)  # add datetime features

    # Drop DATE column (not used in model)
    input_df = input_df.drop(columns=["DATE"])  # remove raw datetime column

    # Convert categorical variables to numeric
    input_df = pd.get_dummies(input_df)  # one-hot encoding

    # Align with training feature schema
    input_df = input_df.reindex(columns=feature_columns, fill_value=0)  # ensure column consistency

    # Scale input data
    input_scaled = scaler.transform(input_df)  # apply same scaling as training

    # Make prediction
    prediction = model.predict(input_scaled)  # generate prediction

    # Return result as JSON
    return {"predicted_bike_count": float(prediction[0])}  # convert numpy to native type
