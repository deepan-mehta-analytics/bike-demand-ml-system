"""
data/fetch_paris_weather.py
─────────────────────────────────────────────────────────────────────────────
Builds the Paris training dataset for the bike demand RF model.

Prerequisites:
  1. Download annual ZIP attachments from the historical counter dataset:
       https://opendata.paris.fr/explore/dataset/comptage-velo-historique-donnees-compteurs/information/
     Recommended: 2022 + 2023 + 2024 (3 clean post-COVID years, no lockdown distortion).
     Direct ZIP URLs:
       .../attachments/2022_comptage_velo_donnees_compteurs_zip
       .../attachments/2023_comptage_velo_donnees_compteurs_zip
       .../attachments/2024_comptage_velo_donnees_compteurs_zip
  2. Extract the CSVs from each ZIP and place ALL of them into:
       data/raw/paris/
     Any *.csv file in that directory is loaded and concatenated automatically.
     The semicolon-separated format and column names must match the standard schema.

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
import glob                                                            # file pattern matching for multi-year CSVs
from data.prepare_city_data import prepare_paris_from_joined           # Seoul-schema normaliser

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw/paris")                                 # Paris-specific raw data subdirectory; place annual CSVs here
PROCESSED_DIR = Path("data/processed")                                 # directory for schema-normalised files
TRIPS_CSV     = RAW_DIR / "paris_trips_hourly.csv"                     # aggregated hourly demand
WEATHER_CSV   = RAW_DIR / "paris_weather.csv"                          # Open-Meteo weather output
JOINED_CSV    = RAW_DIR / "paris_joined.csv"                           # merged trips + weather
OUTPUT_CSV    = PROCESSED_DIR / "paris_bike_sharing.csv"               # final 14-column Seoul-schema training file

# ── Open-Meteo Config ─────────────────────────────────────────────────────────
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"        # historical weather archive endpoint

PARAMS = {
    "latitude":    48.8566,                                            # Paris latitude (city centre)
    "longitude":    2.3522,                                            # Paris longitude (city centre)
    "start_date": "2025-01-01",                                        # placeholder; overridden dynamically from CSV
    "end_date":   "2026-12-31",                                        # placeholder; overridden dynamically from CSV
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
    """Glob all *.csv files in RAW_DIR, concat them, compute avg demand per active counter per hour."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)                         # ensure raw directory exists

    csv_paths = sorted(glob.glob(str(RAW_DIR / "*.csv")))              # find every CSV in the paris raw directory
    # Exclude any intermediate output files this script itself writes
    csv_paths = [p for p in csv_paths if Path(p).name not in {        # skip files generated by this script
        "paris_trips_hourly.csv", "paris_weather.csv", "paris_joined.csv"
    }]

    if not csv_paths:                                                  # abort with instructions if no source CSVs
        raise FileNotFoundError(
            f"No source CSVs found in '{RAW_DIR}'.\n"
            "Download annual ZIPs from the historical counter dataset:\n"
            "  https://opendata.paris.fr/explore/dataset/comptage-velo-historique-donnees-compteurs/information/\n"
            "Recommended: 2022 + 2023 + 2024 ZIPs.\n"
            f"Extract the CSVs and place them in '{RAW_DIR}'."
        )

    print(f"Found {len(csv_paths)} source CSV(s): {[Path(p).name for p in csv_paths]}")
    frames = []                                                        # accumulate one DataFrame per file
    for path in csv_paths:                                             # iterate each annual CSV
        try:
            frame = pd.read_csv(path, sep=";", encoding="utf-8", low_memory=False)  # semicolon-separated UTF-8

            if DATE_COL not in frame.columns:                          # abort with diagnostic if column missing
                raise KeyError(
                    f"Expected column '{DATE_COL}' not found in {Path(path).name}.\n"
                    f"Actual columns: {frame.columns.tolist()}"
                )

            # Normalise dates immediately per file to avoid mixed-format issues after concat.
            # Annual files have three different formats across years:
            #   2022: '2022-01-01T00:00:00'          (no timezone — naive)
            #   2023: '2023-01-01T07:00:00+01:00'    (ISO with offset)
            #   2024: '2024-01-02 19:00:00.000 +0100' (space-separated, milliseconds)
            # pandas 2.x drops naive datetimes to NaT when a mixed series is parsed with
            # utc=True, so we localise timezone-naive rows to Europe/Paris first.
            raw_dates  = pd.to_datetime(frame[DATE_COL], utc=True, errors="coerce")  # parse aware rows to UTC
            naive_mask = raw_dates.isna() & frame[DATE_COL].notna()    # rows that failed = timezone-naive
            if naive_mask.any():                                        # handle files without timezone (e.g. 2022)
                naive_parsed = pd.to_datetime(                         # parse naive strings without tz
                    frame.loc[naive_mask, DATE_COL], errors="coerce"
                )
                naive_utc = (                                          # localise to Paris then convert to UTC
                    naive_parsed
                    .dt.tz_localize("Europe/Paris", ambiguous="infer", nonexistent="shift_forward")
                    .dt.tz_convert("UTC")
                )
                raw_dates = raw_dates.copy()                           # avoid SettingWithCopyWarning
                raw_dates[naive_mask] = naive_utc                      # fill in the previously-NaT slots
            frame[DATE_COL] = raw_dates                                # replace raw strings with UTC Timestamps
            n_valid = frame[DATE_COL].notna().sum()                    # count parseable rows for logging
            print(f"  Loaded {Path(path).name}: {len(frame):,} rows ({n_valid:,} with valid dates)")
            frames.append(frame)                                       # add normalised frame to list
        except Exception as exc:                                       # skip corrupted or mismatched files
            print(f"  WARNING: skipped {Path(path).name} — {exc}")

    df = pd.concat(frames, ignore_index=True)                         # stack all annual DataFrames into one
    print(f"Total rows after concat: {len(df):,}")

    df = df.dropna(subset=[DATE_COL])                                  # drop any remaining unparseable datetimes
    print(f"Rows with valid dates: {len(df):,}")

    # Use all available data in the file (opendata.paris.fr is a rolling dataset)
    date_min = df[DATE_COL].min()                                      # earliest timestamp in source file
    date_max = df[DATE_COL].max()                                      # latest timestamp in source file
    print(f"Available date range: {date_min.date()} to {date_max.date()} ({len(df):,} rows)")

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
    """Fetch Open-Meteo historical weather for Paris using date range set dynamically in PARAMS."""
    print(f"Fetching Paris weather from Open-Meteo ({PARAMS['start_date']} to {PARAMS['end_date']})...")
    response = requests.get(OPENMETEO_URL, params=PARAMS, timeout=60)  # single batch request; 60s timeout
    response.raise_for_status()                                        # raise HTTPError on 4xx/5xx

    hourly = response.json()["hourly"]                                 # extract hourly dict from JSON response
    df     = pd.DataFrame(hourly)                                      # flatten to one row per hour

    df["time"] = pd.to_datetime(df["time"])                            # parse ISO datetime string to Timestamp
    df["DATE"] = df["time"].dt.strftime("%d/%m/%Y")                    # reformat to DD/MM/YYYY
    df["HOUR"] = df["time"].dt.hour                                    # extract integer hour 0-23
    df = df.drop(columns=["time"])                                     # remove raw datetime column

    df.to_csv(WEATHER_CSV, index=False)                                # persist weather CSV
    print(f"Saved {len(df):,} rows -> {WEATHER_CSV}")
    return df


# ── Step 3: Join trips + weather ──────────────────────────────────────────────
def join_trips_weather(trips: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Inner-join hourly demand with hourly weather on (DATE, HOUR)."""
    joined = trips.merge(weather, on=["DATE", "HOUR"], how="inner")    # inner join: keep hours present in both

    if len(joined) == 0:                                               # abort if join is empty
        raise ValueError(
            "Inner join produced 0 rows.\n"
            f"Trips date range:   {trips['DATE'].min()} to {trips['DATE'].max()}\n"
            f"Weather date range: {weather['DATE'].min()} to {weather['DATE'].max()}"
        )

    joined.to_csv(JOINED_CSV, index=False)                             # persist joined CSV
    print(f"Joined: {len(joined):,} rows -> {JOINED_CSV}")
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
        "Extend the date range or check that the source CSV covers all four seasons."
    )

    df_out.to_csv(OUTPUT_CSV, index=False)                             # write final training-ready CSV
    print(f"Final: {len(df_out):,} rows -> {OUTPUT_CSV}")
    print(f"Columns: {list(df_out.columns)}")                          # confirm all 14 Seoul-schema columns
    return df_out


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    trips = aggregate_counter_data()                                   # step 1: aggregate counter CSV

    # Derive Open-Meteo date window from whatever dates exist in the source file
    # (opendata.paris.fr is a rolling dataset; we cannot assume a fixed year range)
    trip_dates  = pd.to_datetime(trips["DATE"], format="%d/%m/%Y")    # parse DD/MM/YYYY trip dates
    date_min_str = trip_dates.min().strftime("%Y-%m-%d")              # YYYY-MM-DD format for Open-Meteo API
    date_max_str = trip_dates.max().strftime("%Y-%m-%d")              # YYYY-MM-DD format for Open-Meteo API
    PARAMS["start_date"] = date_min_str                               # override placeholder with actual start
    PARAMS["end_date"]   = date_max_str                               # override placeholder with actual end
    print(f"Open-Meteo window: {date_min_str} to {date_max_str}")    # confirm dynamic range before API call

    weather = fetch_weather()                                          # step 2: fetch weather from Open-Meteo
    join_trips_weather(trips, weather)                                 # step 3: join on DATE + HOUR
    prepare_and_assert(JOINED_CSV)                                     # step 4: normalise + assert seasons
    print("\nDone. Train with:")
    print("  python -m models.train --city paris --data data/processed/paris_bike_sharing.csv")
