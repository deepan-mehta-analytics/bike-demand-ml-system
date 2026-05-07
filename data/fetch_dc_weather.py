# =============================================================================
# data/fetch_dc_weather.py
# -----------------------------------------------------------------------------
# Builds the Washington DC training dataset for the bike demand RF model.
#
# Prerequisites:
#   1. Download Capital Bikeshare trip data for 2014-2018 from:
#        https://capitalbikeshare.com/system-data
#      Extract all quarterly/annual zip files into:
#        data/raw/dc_trips/
#      The directory should contain multiple CSV files with columns including
#      "Start date" (format: "YYYY-MM-DD HH:MM:SS").
#
# Usage:
#   python data/fetch_dc_weather.py
#
# Output files:
#   data/raw/dc_trips_hourly.csv  — hourly trip counts aggregated from Capital Bikeshare
#   data/raw/dc_weather.csv       — Open-Meteo historical hourly weather for DC
#   data/raw/dc_joined.csv        — trips + weather joined on DATE + HOUR
#   data/processed/dc_bike_sharing.csv — final Seoul-schema CSV ready for training
#
# Then train:
#   python -m models.train --city dc --data data/processed/dc_bike_sharing.csv
# =============================================================================

# ── Imports ───────────────────────────────────────────────────────────────────
import glob                                                            # file pattern matching for CSV discovery
import os                                                              # path construction and existence check
import requests                                                        # HTTP client for Open-Meteo API
import pandas as pd                                                    # DataFrame for all tabular operations


# ── Step 1 — Aggregate Capital Bikeshare Trips to Hourly ──────────────────────

TRIPS_DIR = "data/raw/dc_trips"                                        # directory user extracts zip files into
TRIPS_HOURLY_OUT = "data/raw/dc_trips_hourly.csv"                      # output: one row per DATE+HOUR with count

csv_files = glob.glob(os.path.join(TRIPS_DIR, "*.csv"))                # find all CSV files in the trips directory
if not csv_files:                                                       # abort early if user has not downloaded data yet
    raise FileNotFoundError(
        f"No CSV files found in '{TRIPS_DIR}'.\n"
        "Download 2014-2018 zip files from https://capitalbikeshare.com/system-data\n"
        f"and extract all CSVs into '{TRIPS_DIR}/'."
    )

print(f"Found {len(csv_files)} trip CSV file(s) in {TRIPS_DIR}")       # confirm how many files were discovered

frames = []                                                            # accumulate DataFrames from each file
for f in sorted(csv_files):                                            # iterate in sorted order for reproducibility
    try:
        df_raw = pd.read_csv(f, usecols=lambda c: c in (              # only load the column we need
            "Start date", "started_at"                                 # old format: "Start date"; new format: "started_at"
        ))
        if "Start date" in df_raw.columns:                             # old Capital Bikeshare format (pre-2019)
            df_raw = df_raw.rename(columns={"Start date": "started_at"})  # normalise to single column name
        if "started_at" not in df_raw.columns:                         # neither expected column found
            print(f"  Skipping {os.path.basename(f)} — unrecognised column format")
            continue                                                   # skip file without crashing
        frames.append(df_raw)                                          # add to accumulator
        print(f"  Loaded {os.path.basename(f)}: {len(df_raw):,} rows") # per-file progress
    except Exception as e:
        print(f"  Warning: could not read {os.path.basename(f)} — {e}") # report error; continue with remaining files

if not frames:                                                          # all files failed to load
    raise RuntimeError("No trip data could be loaded — check CSV column format.")

trips_all = pd.concat(frames, ignore_index=True)                       # combine all files into one DataFrame
print(f"\nTotal trip rows before filtering: {len(trips_all):,}")       # show combined row count

# ── Parse datetime and filter to 2014-2018 ────────────────────────────────────
trips_all["start_dt"] = pd.to_datetime(                                # parse start timestamp to Timestamp object
    trips_all["started_at"], infer_datetime_format=True                # handle both common datetime string formats
)
mask = trips_all["start_dt"].dt.year.between(2014, 2018)               # limit to 5-year training window (matching NYC)
trips_all = trips_all[mask].copy()                                     # filter to target year range
print(f"After filtering to 2014-2018: {len(trips_all):,} rows")       # confirm filtered count

# ── Extract DATE and HOUR ─────────────────────────────────────────────────────
trips_all["DATE"] = trips_all["start_dt"].dt.strftime("%d/%m/%Y")      # DD/MM/YYYY string matching Seoul schema
trips_all["HOUR"] = trips_all["start_dt"].dt.hour                      # integer hour 0-23

# ── Aggregate to hourly counts ────────────────────────────────────────────────
hourly = (                                                             # group by each DATE+HOUR combination
    trips_all.groupby(["DATE", "HOUR"], as_index=False)                # group key preserved as columns
    .size()                                                            # count rows (= trips started) in each group
    .rename(columns={"size": "RENTED_BIKE_COUNT"})                     # rename count to Seoul target column name
)
os.makedirs("data/raw", exist_ok=True)                                 # ensure output directory exists
hourly.to_csv(TRIPS_HOURLY_OUT, index=False)                           # write hourly aggregates to disk
print(f"Hourly trip counts: {len(hourly):,} rows -> {TRIPS_HOURLY_OUT}")  # confirm output


# ── Step 2 — Fetch Open-Meteo Historical Weather for Washington DC ─────────────

WEATHER_OUT = "data/raw/dc_weather.csv"                                # output: one row per hour

url = "https://archive-api.open-meteo.com/v1/archive"                 # Open-Meteo historical archive endpoint (free)
params = {
    "latitude":    38.8951,                                            # Washington DC latitude
    "longitude":  -77.0364,                                            # Washington DC longitude
    "start_date": "2014-01-01",                                        # match first date in trip data
    "end_date":   "2018-12-31",                                        # match last date in trip data
    "hourly": (                                                        # request all Seoul-schema weather variables
        "temperature_2m,"
        "relative_humidity_2m,"
        "wind_speed_10m,"
        "precipitation,"
        "snowfall,"
        "visibility,"
        "dew_point_2m"
    ),
    "timezone":        "America/New_York",                             # DC uses Eastern time — aligns with trip timestamps
    "wind_speed_unit": "ms",                                           # m/s matches Seoul schema units; no conversion needed
}

print("\nFetching Open-Meteo historical weather for Washington DC (2014-2018)...")
response = requests.get(url, params=params)                            # call Open-Meteo archive API
response.raise_for_status()                                            # raise for HTTP 4xx/5xx errors
weather_json = response.json()["hourly"]                               # extract hourly block from JSON response
weather = pd.DataFrame(weather_json)                                   # flatten nested JSON to one row per hour

# ── Parse datetime -> DATE + HOUR ─────────────────────────────────────────────
weather["time"] = pd.to_datetime(weather["time"])                      # parse ISO datetime string to Timestamp
weather["DATE"] = weather["time"].dt.strftime("%d/%m/%Y")              # reformat to DD/MM/YYYY (Seoul schema)
weather["HOUR"] = weather["time"].dt.hour                              # extract integer hour 0-23
weather = weather.drop(columns=["time"])                               # remove raw datetime column after extraction

weather.to_csv(WEATHER_OUT, index=False)                               # write weather data to disk
print(f"Weather rows: {len(weather):,} -> {WEATHER_OUT}")             # confirm output row count


# ── Step 3 — Join Trips + Weather on DATE + HOUR ─────────────────────────────

JOINED_OUT = "data/raw/dc_joined.csv"                                  # output: trips + weather merged

trips = pd.read_csv(TRIPS_HOURLY_OUT)                                  # reload hourly trip counts from disk
joined = trips.merge(weather, on=["DATE", "HOUR"], how="inner")        # inner join: only hours with both trips + weather
joined.to_csv(JOINED_OUT, index=False)                                 # write joined CSV to disk
print(f"\nJoined: {len(joined):,} rows -> {JOINED_OUT}")              # confirm row count after join


# ── Step 4 — Prepare to Seoul Schema ─────────────────────────────────────────

FINAL_OUT = "data/processed/dc_bike_sharing.csv"                       # final training-ready output

os.makedirs("data/processed", exist_ok=True)                           # ensure processed directory exists

from data.prepare_city_data import prepare_dc_from_joined              # import Seoul-schema normaliser for DC

df_out = prepare_dc_from_joined(JOINED_OUT)                            # map joined CSV to 14-column Seoul schema
df_out.to_csv(FINAL_OUT, index=False)                                  # write final CSV to disk
print(f"Final dataset: {len(df_out):,} rows -> {FINAL_OUT}")          # confirm final output

print("\nDone. Train the DC model with:")                              # guide user to next step
print("  python -m models.train --city dc --data data/processed/dc_bike_sharing.csv")
