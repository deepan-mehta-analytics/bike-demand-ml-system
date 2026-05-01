# Import required libraries
import pandas as pd  # for handling input data
import joblib  # to load saved model and scaler

# Import feature engineering functions
from models.features import create_features  # reuse same transformations used in training


# -------------------------------
# LOAD SAVED MODEL AND SCALER
# -------------------------------

# Load trained Random Forest model from disk
model = joblib.load("models/random_forest_model.pkl")  # load trained model

# Load scaler used during training
scaler = joblib.load("models/scaler.pkl")  # load scaler to ensure consistent transformations



# -------------------------------
# CREATE SAMPLE INPUT DATA
# -------------------------------

# Create a sample input (same structure as original dataset)
data = {
    "DATE": ["01/01/2018"],  # date in DD/MM/YYYY format
    "HOUR": [10],
    "TEMPERATURE": [5],
    "HUMIDITY": [40],
    "WIND_SPEED": [2.0],
    "VISIBILITY": [2000],
    "DEW_POINT_TEMPERATURE": [-5],
    "SOLAR_RADIATION": [1.5],
    "RAINFALL": [0.0],
    "SNOWFALL": [0.0],
    "SEASONS": ["Winter"],
    "HOLIDAY": ["No Holiday"],
    "FUNCTIONING_DAY": ["Yes"]
}

# Convert dictionary into DataFrame
input_df = pd.DataFrame(data)  # ensures compatibility with pipeline


# -------------------------------
# APPLY FEATURE ENGINEERING
# -------------------------------

# Apply same feature engineering as training phase
input_df = create_features(input_df)  # adds year, month, day, dayofweek


# -------------------------------
# ALIGN FEATURES WITH TRAINING DATA
# -------------------------------

# Drop DATE column (not used in model)
input_df = input_df.drop(columns=["DATE"])  # remove datetime column

# Convert categorical variables to numeric using one-hot encoding
input_df = pd.get_dummies(input_df)  # same transformation as training


# ⚠️ IMPORTANT: Align columns with training data
# Some columns may be missing → we add them with 0
# This ensures input shape matches model expectations

# Load saved feature column structure
feature_columns = joblib.load("models/feature_columns.pkl")  # ensures consistent schema

# Align input with training feature columns
input_df = input_df.reindex(columns=feature_columns, fill_value=0)  # fill missing columns with 0


# -------------------------------
# SCALE INPUT DATA
# -------------------------------

# Apply same scaler used during training
input_scaled = scaler.transform(input_df)  # ensures consistency


# -------------------------------
# MAKE PREDICTION
# -------------------------------

# Predict bike demand
prediction = model.predict(input_scaled)  # generate prediction

# Print result
print("Predicted Bike Count:", prediction[0])  # display predicted value