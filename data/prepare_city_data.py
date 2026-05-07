"""
data/prepare_city_data.py
─────────────────────────────────────────────────────────────────────────────
Normalise city-specific bike-sharing CSVs into the Seoul schema used by
models/train.py. Each city source has different column names, units, and
categorical encodings — this module maps them to a common format.

Seoul Schema (target column names and types):
    DATE                  str  DD/MM/YYYY
    HOUR                  int  0-23
    TEMPERATURE           float  degrees Celsius
    HUMIDITY              int    0-100 percent
    WIND_SPEED            float  m/s
    VISIBILITY            int    10-metre units  (0 = not available)
    DEW_POINT_TEMPERATURE float  degrees Celsius (0 = not available)
    SOLAR_RADIATION       float  MJ/m^2          (0 = not available)
    RAINFALL              float  mm
    SNOWFALL              float  cm
    SEASONS               str    "Spring" | "Summer" | "Autumn" | "Winter"
    HOLIDAY               str    "Holiday" | "No Holiday"
    FUNCTIONING_DAY       str    "Yes" | "No"
    RENTED_BIKE_COUNT     int    hourly demand count (target)

Usage:
    from data.prepare_city_data import prepare_london

    df = prepare_london("data/raw/london_merged.csv")
    df.to_csv("data/processed/london_bike_sharing.csv", index=False)

    Then train:
    python -m models.train --city london --data data/processed/london_bike_sharing.csv
"""

# ── Imports ─────────────────────────────────────────────────────────────────
import pandas as pd                                                    # DataFrame operations


# ── Season Maps ─────────────────────────────────────────────────────────────

# London Kaggle dataset encodes season as integer 0-3 (0=Spring, 1=Summer, 2=Fall, 3=Winter)
_LONDON_SEASON_MAP = {                                                 # integer code → Seoul season label
    0: "Spring",                                                       # 0 = Spring in London Kaggle encoding
    1: "Summer",                                                       # 1 = Summer
    2: "Autumn",                                                       # 2 = Autumn (mapped from "Fall")
    3: "Winter",                                                       # 3 = Winter
}


# ── London ───────────────────────────────────────────────────────────────────

def prepare_london(path: str) -> pd.DataFrame:
    """Normalise the Kaggle London Bike Sharing dataset to Seoul schema.

    Source dataset:
        https://www.kaggle.com/datasets/hmavrodiev/london-bike-sharing-dataset
        File: london_merged.csv  (~17,400 hourly rows, 2015-2017)

    Column mapping applied:
        timestamp → DATE (DD/MM/YYYY) + HOUR
        cnt       → RENTED_BIKE_COUNT
        t1        → TEMPERATURE (Celsius; actual temperature, not feels-like)
        hum       → HUMIDITY (0-100 float → rounded int)
        wind_speed→ WIND_SPEED (km/h → m/s; factor: ÷ 3.6)
        is_holiday→ HOLIDAY (1 → "Holiday", 0 → "No Holiday")
        season    → SEASONS (0-3 int → Spring/Summer/Autumn/Winter)

    Columns not present in London dataset, filled with 0 / "Yes":
        VISIBILITY, DEW_POINT_TEMPERATURE, SOLAR_RADIATION, RAINFALL, SNOWFALL
        FUNCTIONING_DAY (always "Yes" — no non-functioning records in dataset)

    Parameters:
        path: local path to london_merged.csv

    Returns:
        DataFrame in Seoul schema ready to pass to models/train.py
    """
    df = pd.read_csv(path)                                             # load raw London CSV from disk

    # ── Timestamp Parsing ────────────────────────────────────────────────────
    ts = pd.to_datetime(df["timestamp"])                               # parse ISO timestamp strings to Timestamp objects
    df["DATE"] = ts.dt.strftime("%d/%m/%Y")                            # reformat to DD/MM/YYYY string (Seoul format)
    df["HOUR"] = ts.dt.hour                                            # extract hour-of-day as integer 0-23

    # ── Target ───────────────────────────────────────────────────────────────
    df["RENTED_BIKE_COUNT"] = df["cnt"].astype(int)                    # rename and coerce to integer

    # ── Weather Features ─────────────────────────────────────────────────────
    df["TEMPERATURE"] = df["t1"].astype(float)                         # actual temperature in Celsius (not feels-like t2)
    df["HUMIDITY"] = df["hum"].round().astype(int)                     # round float humidity to nearest integer percent
    df["WIND_SPEED"] = (df["wind_speed"] / 3.6).round(2)               # convert km/h to m/s (÷ 3.6); match Seoul units
    df["VISIBILITY"] = 0                                               # not available in London dataset; fill with 0
    df["DEW_POINT_TEMPERATURE"] = 0.0                                  # not available; fill with 0.0
    df["SOLAR_RADIATION"] = 0.0                                        # not available; fill with 0.0
    df["RAINFALL"] = 0.0                                               # not available separately; fill with 0.0
    df["SNOWFALL"] = 0.0                                               # not available; fill with 0.0

    # ── Categorical Features ─────────────────────────────────────────────────
    df["SEASONS"] = df["season"].map(_LONDON_SEASON_MAP)               # map integer 0-3 to season label strings
    df["HOLIDAY"] = df["is_holiday"].map(                              # map binary int to holiday label string
        {1: "Holiday", 0: "No Holiday"}
    )
    df["FUNCTIONING_DAY"] = "Yes"                                      # London dataset contains only operational records

    # ── Select and Return Seoul Schema Columns ────────────────────────────────
    seoul_cols = [                                                     # ordered list of Seoul schema column names
        "DATE", "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",       # temporal + core weather
        "VISIBILITY", "DEW_POINT_TEMPERATURE", "SOLAR_RADIATION",      # extended weather (zeroed)
        "RAINFALL", "SNOWFALL",                                        # precipitation (zeroed)
        "SEASONS", "HOLIDAY", "FUNCTIONING_DAY",                       # categorical features
        "RENTED_BIKE_COUNT",                                           # target column
    ]
    return df[seoul_cols].reset_index(drop=True)                       # return only schema columns; reset index


# ── NYC (BigQuery) ───────────────────────────────────────────────────────────

def nyc_bigquery_sql() -> str:
    """Return the BigQuery SQL to extract hourly NYC Citi Bike demand.

    The result must be joined with hourly weather data (e.g. Open-Meteo
    historical API for NYC lat/lng) and then saved as a CSV matching Seoul
    schema before training.

    Run via:
        bq query --use_legacy_sql=false --format=csv \\
            "$(python -c 'from data.prepare_city_data import nyc_bigquery_sql; print(nyc_bigquery_sql())')" \\
            > data/raw/nyc_trips_hourly.csv
    """
    return """
    SELECT
        FORMAT_DATE('%d/%m/%Y', DATE(starttime))  AS DATE,      -- DD/MM/YYYY for Seoul schema
        EXTRACT(HOUR FROM starttime)               AS HOUR,      -- 0-23 hour of day
        COUNT(*)                                   AS RENTED_BIKE_COUNT  -- trips started in this hour
    FROM
        `bigquery-public-data.new_york_citibike.citibike_trips`
    WHERE
        starttime IS NOT NULL
        AND EXTRACT(YEAR FROM starttime) BETWEEN 2017 AND 2022   -- limit to recent years
    GROUP BY DATE, HOUR
    ORDER BY DATE, HOUR
    """                                                                # returns hourly demand without weather columns
    # NOTE: after extracting this, join with Open-Meteo historical weather
    # for NYC (lat=40.71, lng=-74.01) to add TEMPERATURE, HUMIDITY, etc.
    # then use prepare_nyc_from_joined() below to map to Seoul schema.


def prepare_nyc_from_joined(path: str) -> pd.DataFrame:
    """Normalise a pre-joined NYC trips + weather CSV to Seoul schema.

    Expected input columns (after manual BigQuery export + Open-Meteo join):
        DATE               — DD/MM/YYYY string
        HOUR               — integer 0-23
        RENTED_BIKE_COUNT  — integer hourly trip count from BigQuery
        temperature_2m     — Celsius (Open-Meteo column name)
        relative_humidity_2m — percent
        wind_speed_10m     — m/s (Open-Meteo is already in m/s)
        precipitation      — mm
        snowfall           — cm
        visibility         — metres (divide by 10 for Seoul units)
        dew_point_2m       — Celsius

    Parameters:
        path: local path to the joined CSV

    Returns:
        DataFrame in Seoul schema ready to pass to models/train.py
    """
    df = pd.read_csv(path)                                             # load pre-joined trips + weather CSV

    # ── Weather Features ─────────────────────────────────────────────────────
    df["TEMPERATURE"] = df["temperature_2m"].astype(float)             # rename Open-Meteo column to Seoul name
    df["HUMIDITY"] = df["relative_humidity_2m"].round().astype(int)    # round to nearest integer percent
    df["WIND_SPEED"] = df["wind_speed_10m"].astype(float)              # Open-Meteo wind speed is already in m/s
    df["VISIBILITY"] = (df["visibility"] / 10).round().astype(int)     # convert metres to 10m units (÷ 10)
    df["DEW_POINT_TEMPERATURE"] = df["dew_point_2m"].astype(float)     # rename Open-Meteo column
    df["SOLAR_RADIATION"] = 0.0                                        # not available from Open-Meteo free tier; fill 0
    df["RAINFALL"] = df["precipitation"].astype(float)                 # rename precipitation to RAINFALL
    df["SNOWFALL"] = df["snowfall"].astype(float)                      # rename snowfall column

    # ── Derived Categoricals ─────────────────────────────────────────────────
    date_dt = pd.to_datetime(df["DATE"], dayfirst=True)                # parse DD/MM/YYYY for month-based season derivation
    month = date_dt.dt.month                                           # extract month number for season lookup
    df["SEASONS"] = pd.cut(                                            # derive season from month-of-year
        month,
        bins=[0, 2, 5, 8, 11, 12],                                    # month ranges: 1-2=Winter, 3-5=Spring, etc.
        labels=["Winter", "Spring", "Summer", "Autumn", "Winter"],     # season labels for each bin
        ordered=False,
    ).astype(str)                                                      # convert Categorical to plain strings
    df["HOLIDAY"] = "No Holiday"                                       # NYC public holidays not in Citi Bike data; default
    df["FUNCTIONING_DAY"] = "Yes"                                      # Citi Bike operates year-round; default "Yes"

    # ── Select and Return Seoul Schema Columns ────────────────────────────────
    seoul_cols = [                                                     # Seoul schema column order
        "DATE", "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",
        "VISIBILITY", "DEW_POINT_TEMPERATURE", "SOLAR_RADIATION",
        "RAINFALL", "SNOWFALL",
        "SEASONS", "HOLIDAY", "FUNCTIONING_DAY",
        "RENTED_BIKE_COUNT",
    ]
    return df[seoul_cols].reset_index(drop=True)                       # return schema-aligned DataFrame
