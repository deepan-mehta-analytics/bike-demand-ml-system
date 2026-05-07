# ── fetch_nyc_weather.py ───────────────────────────────────────────────────────
# Fetches historical hourly weather for NYC from Open-Meteo (free, no auth),
# joins with the BigQuery Citi Bike trip counts in data/raw/nyc_trips_hourly.csv,
# and produces data/processed/nyc_bike_sharing.csv in the Seoul 14-column schema.
#
# Run from the project root:
#   python -m data.fetch_nyc_weather
# ──────────────────────────────────────────────────────────────────────────────

# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                    # HTTP client for Open-Meteo API
import pandas as pd                                               # DataFrame operations
from pathlib import Path                                          # cross-platform file paths
from data.prepare_city_data import prepare_nyc_from_joined        # Seoul-schema normaliser

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw")                                  # directory for raw source files
PROCESSED_DIR = Path("data/processed")                            # directory for schema-normalised files
TRIPS_CSV     = RAW_DIR / "nyc_trips_hourly.csv"                  # BigQuery export: DATE, HOUR, RENTED_BIKE_COUNT
WEATHER_CSV   = RAW_DIR / "nyc_weather.csv"                       # Open-Meteo output: hourly weather columns
JOINED_CSV    = RAW_DIR / "nyc_joined.csv"                        # merged trips + weather before schema normalisation
OUTPUT_CSV    = PROCESSED_DIR / "nyc_bike_sharing.csv"            # final 14-column Seoul-schema training file

# ── Open-Meteo Config ─────────────────────────────────────────────────────────
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"  # historical weather archive endpoint

PARAMS = {
    "latitude":    40.71,                                         # NYC latitude (central Manhattan)
    "longitude":  -74.01,                                         # NYC longitude (central Manhattan)
    "start_date": "2014-01-01",                                   # earliest date in nyc_trips_hourly.csv
    "end_date":   "2018-12-31",                                   # latest date in nyc_trips_hourly.csv
    "hourly": (                                                   # comma-separated weather variables
        "temperature_2m,"                                         # air temperature at 2m (°C)
        "relative_humidity_2m,"                                   # relative humidity at 2m (%)
        "wind_speed_10m,"                                         # wind speed at 10m (m/s via wind_speed_unit)
        "precipitation,"                                          # total precipitation per hour (mm)
        "snowfall,"                                               # snowfall per hour (cm)
        "visibility,"                                             # visibility (metres)
        "dew_point_2m"                                            # dew point at 2m (°C)
    ),
    "timezone":        "America/New_York",                        # local time — matches Citi Bike starttime zone
    "wind_speed_unit": "ms",                                      # return wind in m/s (Seoul schema units)
}


# ── Step 1: Fetch weather from Open-Meteo ────────────────────────────────────
def fetch_weather() -> pd.DataFrame:
    print("Fetching NYC weather from Open-Meteo (2014-2018)…")   # progress indicator
    response = requests.get(OPENMETEO_URL, params=PARAMS)         # send GET request to archive API
    response.raise_for_status()                                   # raise HTTPError on 4xx/5xx

    hourly = response.json()["hourly"]                            # extract hourly dict from JSON response
    df     = pd.DataFrame(hourly)                                 # flatten to one row per hour

    df["time"] = pd.to_datetime(df["time"])                       # parse ISO datetime string to Timestamp
    df["DATE"] = df["time"].dt.strftime("%d/%m/%Y")               # reformat to DD/MM/YYYY (Seoul schema)
    df["HOUR"] = df["time"].dt.hour                               # extract integer hour 0-23
    df = df.drop(columns=["time"])                                # remove raw datetime column after extraction

    df.to_csv(WEATHER_CSV, index=False)                           # persist weather CSV for inspection/re-use
    print(f"  Saved {len(df):,} rows -> {WEATHER_CSV}")           # confirm row count
    return df                                                     # return DataFrame for join step


# ── Step 2: Join trips + weather ──────────────────────────────────────────────
def join_trips_weather(weather_df: pd.DataFrame) -> pd.DataFrame:
    print(f"Loading trips from {TRIPS_CSV}…")                    # progress indicator
    trips = pd.read_csv(TRIPS_CSV)                                # load BigQuery hourly trip counts

    print("Joining trips and weather on (DATE, HOUR)…")          # progress indicator
    joined = trips.merge(weather_df, on=["DATE", "HOUR"],         # inner join: keep only hours present in both
                         how="inner")

    joined.to_csv(JOINED_CSV, index=False)                        # persist joined CSV before schema normalisation
    print(f"  Joined: {len(joined):,} rows -> {JOINED_CSV}")      # confirm post-join row count
    return joined                                                 # return for prepare step


# ── Step 3: Normalise to Seoul schema ─────────────────────────────────────────
def prepare(joined_path: Path) -> pd.DataFrame:
    print("Normalising to Seoul 14-column schema…")              # progress indicator
    df_out = prepare_nyc_from_joined(str(joined_path))            # map column names + derive SEASONS/HOLIDAY
    PROCESSED_DIR.mkdir(exist_ok=True)                            # ensure processed/ directory exists
    df_out.to_csv(OUTPUT_CSV, index=False)                        # write final training-ready CSV
    print(f"  Final: {len(df_out):,} rows -> {OUTPUT_CSV}")       # confirm output row count
    print(f"  Columns: {list(df_out.columns)}")                   # show all 14 column names for verification
    return df_out                                                 # return for optional further inspection


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    weather_df = fetch_weather()                                  # step 1: fetch and save weather CSV
    join_trips_weather(weather_df)                                # step 2: merge with trip counts
    prepare(JOINED_CSV)                                           # step 3: normalise to Seoul schema
    print("\nDone. Train with:")                                  # print next-step command for convenience
    print("  python -m models.train --city nyc --data data/processed/nyc_bike_sharing.csv")
