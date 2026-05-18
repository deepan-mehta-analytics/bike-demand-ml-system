"""
data/fetch_chicago_weather.py
─────────────────────────────────────────────────────────────────────────────
Builds the Chicago training dataset for the bike demand RF model.

Prerequisites:
  1. Download Divvy trip data for 2019-2022 from:
       https://divvybikes.com/system-data
     Extract all quarterly/annual zip files into:
       data/raw/chicago/trips/
     Files use "started_at" column (post-2020) or "start_time" (2019 files).

Usage (from project root):
  python -m data.fetch_chicago_weather

Output files:
  data/raw/chicago/chicago_trips_hourly.csv  — hourly trip counts from Divvy CSVs
  data/raw/chicago/chicago_weather.csv       — Open-Meteo historical hourly weather for Chicago
  data/raw/chicago/chicago_joined.csv        — trips + weather joined on DATE + HOUR
  data/processed/chicago_bike_sharing.csv    — Seoul-schema CSV ready for training

Then train:
  python -m models.train --city chicago --data data/processed/chicago_bike_sharing.csv
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import glob                                                            # file pattern matching for CSV discovery
import requests                                                        # HTTP client for Open-Meteo API
import pandas as pd                                                    # DataFrame operations
from pathlib import Path                                               # cross-platform file paths
from data.prepare_city_data import prepare_chicago_from_joined         # Seoul-schema normaliser

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw/chicago")                               # Chicago-specific raw data subdirectory
TRIPS_DIR     = RAW_DIR / "trips"                                      # user extracts Divvy zip files here
PROCESSED_DIR = Path("data/processed")                                 # directory for schema-normalised files
TRIPS_CSV     = RAW_DIR / "chicago_trips_hourly.csv"                   # aggregated hourly trip counts
WEATHER_CSV   = RAW_DIR / "chicago_weather.csv"                        # Open-Meteo weather output
JOINED_CSV    = RAW_DIR / "chicago_joined.csv"                         # merged trips + weather
OUTPUT_CSV    = PROCESSED_DIR / "chicago_bike_sharing.csv"             # final 14-column Seoul-schema training file

# ── Open-Meteo Config ─────────────────────────────────────────────────────────
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"        # historical weather archive endpoint

PARAMS = {
    "latitude":    41.8781,                                            # Chicago latitude (city centre)
    "longitude":  -87.6298,                                            # Chicago longitude (city centre)
    "start_date": "2019-01-01",                                        # training window start
    "end_date":   "2022-12-31",                                        # training window end
    "hourly": (                                                        # comma-separated weather variables
        "temperature_2m,"                                              # air temperature at 2m (°C)
        "relative_humidity_2m,"                                        # relative humidity at 2m (%)
        "wind_speed_10m,"                                              # wind speed at 10m (m/s via wind_speed_unit)
        "precipitation,"                                               # total precipitation per hour (mm)
        "snowfall,"                                                    # snowfall per hour (cm)
        "visibility,"                                                  # visibility (metres)
        "dew_point_2m"                                                 # dew point at 2m (°C)
    ),
    "timezone":        "America/Chicago",                              # local time — matches Divvy trip timestamps
    "wind_speed_unit": "ms",                                           # return wind in m/s (Seoul schema units)
}


# ── Step 1: Aggregate Divvy trip CSVs to hourly demand ───────────────────────
def aggregate_divvy_trips() -> pd.DataFrame:
    """Load all CSVs in data/raw/chicago/trips/, aggregate to hourly trip count."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)                         # ensure raw directory exists

    csv_files = glob.glob(str(TRIPS_DIR / "*.csv"))                    # find all CSV files in trips directory
    if not csv_files:                                                   # abort if user hasn't downloaded data
        raise FileNotFoundError(
            f"No CSV files found in '{TRIPS_DIR}'.\n"
            "Download 2019-2022 Divvy zip files from https://divvybikes.com/system-data\n"
            f"and extract all CSVs into '{TRIPS_DIR}'."
        )

    print(f"Found {len(csv_files)} trip CSV file(s) in {TRIPS_DIR}")

    frames = []                                                        # accumulate DataFrames from each file
    for f in sorted(csv_files):                                        # iterate in sorted order for reproducibility
        try:
            df_raw = pd.read_csv(f, usecols=lambda c: c in (          # load only the datetime column we need
                "started_at", "start_time"                             # post-2020 name: "started_at"; 2019 name: "start_time"
            ), low_memory=False)

            # Detect which column name this file uses (Divvy renamed the column in 2020)
            col = "started_at" if "started_at" in df_raw.columns else "start_time"  # explicit guard for name change

            df_raw[col] = pd.to_datetime(df_raw[col], errors="coerce")  # parse datetime; invalid values → NaT
            df_raw = df_raw.dropna(subset=[col])                        # drop rows with unparseable datetimes
            df_raw["DATE"] = df_raw[col].dt.strftime("%d/%m/%Y")        # reformat to DD/MM/YYYY (Seoul schema)
            df_raw["HOUR"] = df_raw[col].dt.hour                        # extract integer hour 0-23
            frames.append(df_raw[["DATE", "HOUR"]])                     # keep only DATE and HOUR columns
            print(f"  Loaded: {Path(f).name} ({len(df_raw):,} rows)")

        except Exception as e:                                          # catch per-file errors; skip bad files
            print(f"  Warning: skipping {Path(f).name}: {e}")

    if not frames:                                                      # abort if all files failed
        raise ValueError("No valid trip records loaded from any CSV file.")

    all_trips = pd.concat(frames, ignore_index=True)                   # combine all files into one DataFrame

    # Filter to training window 2019-2022
    all_trips["_dt"] = pd.to_datetime(all_trips["DATE"], dayfirst=True)  # temporary column for date comparison
    all_trips = all_trips[
        (all_trips["_dt"] >= "2019-01-01") &
        (all_trips["_dt"] <= "2022-12-31")
    ].drop(columns=["_dt"])                                            # drop temporary column

    hourly = (
        all_trips.groupby(["DATE", "HOUR"])
        .size()                                                        # count rows (trips) per DATE+HOUR bucket
        .reset_index(name="RENTED_BIKE_COUNT")                         # name the count column
    )

    print(f"Hourly demand rows: {len(hourly):,}")
    print(f"RENTED_BIKE_COUNT stats:\n{hourly['RENTED_BIKE_COUNT'].describe()}")
    hourly.to_csv(TRIPS_CSV, index=False)                              # persist hourly demand
    print(f"Saved: {TRIPS_CSV}")
    return hourly


# ── Step 2: Fetch weather from Open-Meteo ────────────────────────────────────
def fetch_weather() -> pd.DataFrame:
    """Fetch Open-Meteo historical weather for Chicago 2019-2022."""
    print("Fetching Chicago weather from Open-Meteo (2019-2022)…")
    response = requests.get(OPENMETEO_URL, params=PARAMS, timeout=60)  # single batch request; 60s timeout
    response.raise_for_status()                                        # raise HTTPError on 4xx/5xx

    hourly = response.json()["hourly"]                                 # extract hourly dict from JSON response
    df     = pd.DataFrame(hourly)                                      # flatten to one row per hour

    df["time"] = pd.to_datetime(df["time"])                            # parse ISO datetime string to Timestamp
    df["DATE"] = df["time"].dt.strftime("%d/%m/%Y")                    # reformat to DD/MM/YYYY
    df["HOUR"] = df["time"].dt.hour                                    # extract integer hour 0-23
    df = df.drop(columns=["time"])                                     # remove raw datetime column

    df.to_csv(WEATHER_CSV, index=False)                                # persist weather CSV
    print(f"Saved {len(df):,} rows → {WEATHER_CSV}")
    return df


# ── Step 3: Join trips + weather ──────────────────────────────────────────────
def join_trips_weather(trips: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Inner-join hourly demand with hourly weather on (DATE, HOUR)."""
    joined = trips.merge(weather, on=["DATE", "HOUR"], how="inner")    # inner join: keep hours present in both

    if len(joined) == 0:                                               # abort if join is empty
        raise ValueError(
            "Inner join produced 0 rows.\n"
            f"Trips date range:   {trips['DATE'].min()} → {trips['DATE'].max()}\n"
            f"Weather date range: {weather['DATE'].min()} → {weather['DATE'].max()}"
        )

    joined.to_csv(JOINED_CSV, index=False)                             # persist joined CSV
    print(f"Joined: {len(joined):,} rows → {JOINED_CSV}")
    return joined


# ── Step 4: Normalise to Seoul schema + season assertion ─────────────────────
def prepare_and_assert(joined_path: Path) -> pd.DataFrame:
    """Normalise to Seoul schema and assert all four seasons are present."""
    PROCESSED_DIR.mkdir(exist_ok=True)                                 # ensure processed/ directory exists
    df_out = prepare_chicago_from_joined(str(joined_path))             # map column names + derive SEASONS/HOLIDAY

    # Pre-mortem guard: if any season is missing, pd.get_dummies() at training time
    # will not create that season's dummy column, causing a schema mismatch at inference.
    expected_seasons = {"Spring", "Summer", "Autumn", "Winter"}
    actual_seasons   = set(df_out["SEASONS"].unique())
    assert actual_seasons == expected_seasons, (
        f"Season assertion failed — training data incomplete.\n"
        f"Expected: {expected_seasons}\n"
        f"Got:      {actual_seasons}\n"
        "Extend the date range or check that 2019-2022 data covers all seasons."
    )

    df_out.to_csv(OUTPUT_CSV, index=False)                             # write final training-ready CSV
    print(f"Final: {len(df_out):,} rows → {OUTPUT_CSV}")
    print(f"Columns: {list(df_out.columns)}")                          # confirm all 14 Seoul-schema columns
    return df_out


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    trips   = aggregate_divvy_trips()                                  # step 1: aggregate Divvy CSVs
    weather = fetch_weather()                                          # step 2: fetch weather from Open-Meteo
    join_trips_weather(trips, weather)                                 # step 3: join on DATE + HOUR
    prepare_and_assert(JOINED_CSV)                                     # step 4: normalise + assert seasons
    print("\nDone. Train with:")
    print("  python -m models.train --city chicago --data data/processed/chicago_bike_sharing.csv")
