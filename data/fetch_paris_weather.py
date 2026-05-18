"""
data/fetch_paris_weather.py
─────────────────────────────────────────────────────────────────────────────
Builds the Paris training dataset for the bike demand RF model.

Prerequisites:
  1. Download "Comptage vélo - Données compteurs" from:
       https://opendata.paris.fr/explore/dataset/comptage-velo-donnees-compteurs/
     Click "Export" → CSV (semicolon-separated).
     Save as: data/raw/paris/paris_hourly.csv

Usage (from project root):
  python -m data.fetch_paris_weather

Output files:
  data/raw/paris/paris_trips_hourly.csv  — hourly avg cycling demand per active counter
  data/raw/paris/paris_weather.csv       — Open-Meteo historical hourly weather for Paris
  data/raw/paris/paris_joined.csv        — trips + weather joined on DATE + HOUR
  data/processed/paris_bike_sharing.csv  — Seoul-schema CSV ready for training

Then train:
  python -m models.train --city paris --data data/processed/paris_bike_sharing.csv
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import requests                                                        # HTTP client for Open-Meteo API
import pandas as pd                                                    # DataFrame operations
from pathlib import Path                                               # cross-platform file paths
from data.prepare_city_data import prepare_paris_from_joined           # Seoul-schema normaliser

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw/paris")                                 # Paris-specific raw data subdirectory
PROCESSED_DIR = Path("data/processed")                                 # directory for schema-normalised files
RAW_FILE      = RAW_DIR / "paris_hourly.csv"                           # user-provided opendata.paris.fr download
TRIPS_CSV     = RAW_DIR / "paris_trips_hourly.csv"                     # aggregated hourly demand
WEATHER_CSV   = RAW_DIR / "paris_weather.csv"                          # Open-Meteo weather output
JOINED_CSV    = RAW_DIR / "paris_joined.csv"                           # merged trips + weather
OUTPUT_CSV    = PROCESSED_DIR / "paris_bike_sharing.csv"               # final 14-column Seoul-schema training file

# ── Open-Meteo Config ─────────────────────────────────────────────────────────
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"        # historical weather archive endpoint

PARAMS = {
    "latitude":    48.8566,                                            # Paris latitude (city centre)
    "longitude":    2.3522,                                            # Paris longitude (city centre)
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
    "timezone":        "Europe/Paris",                                 # local time — matches counter timestamps
    "wind_speed_unit": "ms",                                           # return wind in m/s (Seoul schema units)
}

# ── Expected column names in opendata.paris.fr export ────────────────────────
DATE_COL  = "Date et heure de comptage"                                # ISO datetime column in source CSV
COUNT_COL = "Comptage horaire"                                         # hourly cycle count per counter


# ── Step 1: Aggregate counter data to hourly demand ──────────────────────────
def aggregate_counter_data() -> pd.DataFrame:
    """Load paris_hourly.csv, filter 2019-2022, compute avg demand per active counter per hour."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)                         # ensure raw directory exists

    if not RAW_FILE.is_file():                                         # abort with instructions if file missing
        raise FileNotFoundError(
            f"'{RAW_FILE}' not found.\n"
            "Download 'Comptage vélo - Données compteurs' from:\n"
            "  https://opendata.paris.fr/explore/dataset/comptage-velo-donnees-compteurs/\n"
            "Click Export → CSV (semicolon-separated).\n"
            f"Save as '{RAW_FILE}'."
        )

    print(f"Loading counter CSV: {RAW_FILE}")
    df = pd.read_csv(RAW_FILE, sep=";", encoding="utf-8", low_memory=False)  # semicolon-separated, UTF-8
    print(f"Columns detected: {df.columns.tolist()}")                  # print actual columns to diagnose schema changes

    if DATE_COL not in df.columns:                                     # abort with diagnostic if column names changed
        raise KeyError(
            f"Expected column '{DATE_COL}' not found.\n"
            f"Actual columns: {df.columns.tolist()}\n"
            "Check if opendata.paris.fr updated the dataset schema."
        )

    df[DATE_COL] = pd.to_datetime(df[DATE_COL], utc=True, errors="coerce")  # parse ISO datetime → UTC Timestamp
    df = df.dropna(subset=[DATE_COL])                                  # drop rows with unparseable datetimes

    # Filter to training window 2019-2022
    start = pd.Timestamp("2019-01-01", tz="UTC")                       # training window start as UTC Timestamp
    end   = pd.Timestamp("2022-12-31 23:59:59", tz="UTC")              # training window end as UTC Timestamp
    df = df[(df[DATE_COL] >= start) & (df[DATE_COL] <= end)].copy()   # keep only 2019-2022 rows
    print(f"Rows after date filter (2019-2022): {len(df):,}")

    df["DATE"] = df[DATE_COL].dt.strftime("%d/%m/%Y")                  # reformat to DD/MM/YYYY (Seoul schema)
    df["HOUR"] = df[DATE_COL].dt.hour                                  # extract integer hour 0-23

    # Average over active counters per hour (exclude zeros = offline counters)
    # This normalises the signal to ~50-500/hr, compatible with DC/Seoul Shiny thresholds
    df_active = df[df[COUNT_COL] > 0]                                  # exclude offline counter readings
    hourly = (
        df_active.groupby(["DATE", "HOUR"])[COUNT_COL]
        .mean()                                                        # mean across active counters per hour
        .round()                                                       # round to nearest integer
        .astype(int)                                                   # coerce to integer
        .reset_index()
        .rename(columns={COUNT_COL: "RENTED_BIKE_COUNT"})              # rename to Seoul schema target column
    )

    print(f"Hourly demand rows: {len(hourly):,}")
    print(f"RENTED_BIKE_COUNT stats:\n{hourly['RENTED_BIKE_COUNT'].describe()}")
    hourly.to_csv(TRIPS_CSV, index=False)                              # persist hourly demand
    print(f"Saved: {TRIPS_CSV}")
    return hourly


# ── Step 2: Fetch weather from Open-Meteo ────────────────────────────────────
def fetch_weather() -> pd.DataFrame:
    """Fetch Open-Meteo historical weather for Paris 2019-2022."""
    print("Fetching Paris weather from Open-Meteo (2019-2022)…")
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
    df_out = prepare_paris_from_joined(str(joined_path))               # map column names + derive SEASONS/HOLIDAY

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
    trips   = aggregate_counter_data()                                 # step 1: aggregate counter CSV
    weather = fetch_weather()                                          # step 2: fetch weather from Open-Meteo
    join_trips_weather(trips, weather)                                 # step 3: join on DATE + HOUR
    prepare_and_assert(JOINED_CSV)                                     # step 4: normalise + assert seasons
    print("\nDone. Train with:")
    print("  python -m models.train --city paris --data data/processed/paris_bike_sharing.csv")
