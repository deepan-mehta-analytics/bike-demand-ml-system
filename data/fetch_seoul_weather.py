"""
data/fetch_seoul_weather.py
─────────────────────────────────────────────────────────────────────────────
Builds the Seoul training dataset for the bike demand RF model from the
Seoul Metropolitan Government OA-15182 (Tareungi Public Bicycle Rental
History) dataset joined with Open-Meteo historical weather.

Prerequisites:
  1. Download annual ZIP attachments from OA-15182:
       https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do
     Recommended: 2022 + 2023 + 2024 (3 post-COVID, full-year datasets).
     No API key required. Direct download from the portal.
  2. Extract the CSVs from each ZIP and place ALL of them into:
       data/raw/seoul/
     Filenames typically: 2022_bike_rental.csv, 2023_bike_rental.csv, ...
     Any [0-9]{4}*.csv file in that directory is loaded and aggregated.
     If the source format is XLS rather than CSV, convert via Excel or
     LibreOffice to CSV first; the script only reads .csv files.

Usage (from project root):
  python -m data.fetch_seoul_weather

Output files:
  data/raw/seoul/seoul_trips_hourly.csv  — hourly aggregated trip count
  data/raw/seoul/seoul_weather.csv       — Open-Meteo historical weather (Seoul)
  data/raw/seoul/seoul_joined.csv        — trips + weather joined on DATE + HOUR
  data/processed/seoul_bike_sharing.csv  — 14-col Seoul-schema training file

Then train:
  python -m models.train --city seoul --data data/processed/seoul_bike_sharing.csv

Notes on schema choices (see spec sections 7.6 and 7.8):
  - SOLAR_RADIATION: Open-Meteo returns shortwave_radiation in W/m^2; this
    script multiplies by 0.0036 to convert to MJ/m^2 to match the original
    UCI Seoul scale before writing seoul_weather.csv.
  - VISIBILITY: Open-Meteo has no equivalent variable; this script writes a
    constant 2000 (UCI 10m-unit scale: ~20 km, "good visibility"). The RF
    sees zero variance on this column and effectively ignores it.
  - Korea has no DST → Asia/Seoul tz is attached via tz_localize with
    ambiguous="infer", nonexistent="shift_forward" (effectively a label
    attachment, no hour shift). Times stay in Seoul wall-clock to align
    with Open-Meteo (also fetched with timezone="Asia/Seoul") on the
    (DATE, HOUR) inner-join key. A previous UTC conversion silently
    misaligned trips vs weather by 9 hours and was removed.
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import glob                                                            # file pattern matching for multi-year CSVs
import time                                                            # sleep between Open-Meteo retry attempts
from pathlib import Path                                               # cross-platform file paths

import pandas as pd                                                    # DataFrame ops + chunked CSV reads
import requests                                                        # HTTP client for Open-Meteo API

from data.prepare_city_data import prepare_seoul_from_joined           # Seoul-schema normaliser appended in Task 2

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw/seoul")                                 # Seoul raw subdirectory; place OA-15182 CSVs here
PROCESSED_DIR = Path("data/processed")                                 # directory for schema-normalised training files
TRIPS_CSV     = RAW_DIR / "seoul_trips_hourly.csv"                     # aggregated hourly trip count output
WEATHER_CSV   = RAW_DIR / "seoul_weather.csv"                          # Open-Meteo weather output
JOINED_CSV    = RAW_DIR / "seoul_joined.csv"                           # merged trips + weather output
OUTPUT_CSV    = PROCESSED_DIR / "seoul_bike_sharing.csv"               # final 14-column Seoul-schema training file

# ── OA-15182 schema ───────────────────────────────────────────────────────────
# Candidate column names per year (Korean ↔ romanised drift expected).
# Each tuple key is the canonical name; values are the candidate raw header strings.
_CANDIDATE_COLS = {                                                    # canonical → list of possible raw headers
    "start_time": [                                                    # rental start datetime column candidates
        "대여일시", "rental_date", "rent_date", "start_time", "RENT_DT",
    ],
}

# Encoding cascade — OA-15182 CSVs may be utf-8-sig (BOM), plain utf-8, or cp949 (legacy Korean Windows).
_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")                           # try in this order, raise if all fail

# ── Open-Meteo Config ─────────────────────────────────────────────────────────
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"        # historical weather archive endpoint

PARAMS = {                                                             # request parameters; date range filled at runtime
    "latitude":      37.5665,                                          # Seoul latitude (city centre)
    "longitude":    126.9780,                                          # Seoul longitude (city centre)
    "start_date": "2022-01-01",                                        # placeholder; overridden from trips_hourly min DATE
    "end_date":   "2024-12-31",                                        # placeholder; overridden from trips_hourly max DATE
    "hourly": (                                                        # comma-separated weather variables requested
        "temperature_2m,"                                              # air temperature at 2m (°C)
        "relative_humidity_2m,"                                        # relative humidity at 2m (%)
        "wind_speed_10m,"                                              # wind speed at 10m (m/s with wind_speed_unit=ms)
        "precipitation,"                                               # total precipitation per hour (mm)
        "snowfall,"                                                    # snowfall per hour (cm)
        "dew_point_2m,"                                                # dew point at 2m (°C)
        "shortwave_radiation"                                          # surface solar irradiance (W/m^2) → converted to MJ/m^2
    ),
    "timezone":        "Asia/Seoul",                                   # local time — matches trip start_time after conversion
    "wind_speed_unit": "ms",                                           # return wind in m/s (Seoul schema units)
}

# ── Constants applied at fetch time (see spec sections 7.6 and 7.8) ──────────
_SOLAR_W_TO_MJ = 0.0036                                                # W/m^2 × 0.0036 → MJ/m^2 (UCI Seoul scale)
_VISIBILITY_DEFAULT = 2000                                             # Open-Meteo has no visibility variable; constant per spec


# ── Helper: defensive CSV opener with encoding cascade ───────────────────────
def _read_seoul_csv_chunks(path: Path, chunksize: int = 500_000):
    """Yield DataFrame chunks; try utf-8-sig → utf-8 → cp949; raise if all fail."""
    for enc in _ENCODINGS:                                             # try each encoding in defined order
        try:
            reader = pd.read_csv(                                      # open as chunked iterator to bound memory
                path,
                encoding=enc,
                chunksize=chunksize,                                   # ~500k rows ≈ 50-80 MB peak per chunk
                low_memory=False,                                      # avoid mixed-dtype warnings for raw OA-15182 columns
            )
            for chunk in reader:                                       # iterate chunks lazily
                yield chunk                                            # yield to caller
            return                                                     # success: stop trying encodings
        except UnicodeDecodeError:
            continue                                                   # encoding failed; try next
    raise RuntimeError(                                                # all encodings failed — fail loudly with file name
        f"Could not decode {path} as any of {_ENCODINGS}. "
        f"Inspect the file's encoding (file -bi on Unix, or open in a text editor)."
    )


# ── Helper: pick canonical start_time column from per-year header drift ───────
def _resolve_start_time_col(columns) -> str:
    """Return the first matching candidate column name for start_time, else raise."""
    candidates = _CANDIDATE_COLS["start_time"]                         # ordered list of possible raw header strings
    for name in candidates:                                            # check each candidate against the actual columns
        if name in columns:                                            # match on exact string
            return name
    raise KeyError(                                                    # fail loudly naming both the file and the candidate list
        f"No start_time column found. Expected one of {candidates}. "
        f"Actual columns: {list(columns)[:10]}..."
    )


# ── Step 1: Aggregate per-trip data to hourly demand ─────────────────────────
def _aggregate_one_year(path: Path) -> pd.DataFrame:
    """Read one annual CSV in chunks; aggregate to hourly; return small DataFrame."""
    print(f"  Aggregating {path.name.encode('ascii', errors='replace').decode('ascii')}...")  # ASCII-safe filename for cp1252 terminals
    aggregates = []                                                    # list of per-chunk groupby results
    start_col = None                                                   # resolved on first chunk; reused across chunks

    for chunk in _read_seoul_csv_chunks(path):                         # iterate chunks via encoding cascade
        if start_col is None:                                          # resolve start_time column name once per file
            start_col = _resolve_start_time_col(chunk.columns)

        ts = pd.to_datetime(chunk[start_col], errors="coerce")         # parse to Timestamp; coerce bad rows to NaT
        chunk = chunk.assign(_ts=ts).dropna(subset=["_ts"])            # drop unparseable rows up front

        if chunk["_ts"].dt.tz is None:                                 # if timestamps are tz-naive
            chunk["_ts"] = (                                           # attach Asia/Seoul tz (Korea has no DST; label only, no hour shift)
                chunk["_ts"]
                .dt.tz_localize("Asia/Seoul", ambiguous="infer", nonexistent="shift_forward")
            )
        # Stay in Seoul wall-clock — Open-Meteo weather is also Asia/Seoul, so the (DATE, HOUR) join aligns.
        # A previous tz_convert("UTC") here silently shifted trip hours by 9, corrupting the hour-of-day signal.

        chunk["DATE"] = chunk["_ts"].dt.strftime("%d/%m/%Y")           # DD/MM/YYYY (Seoul schema)
        chunk["HOUR"] = chunk["_ts"].dt.hour                           # integer hour 0-23

        aggregates.append(                                             # per-chunk groupby keeps memory tiny
            chunk.groupby(["DATE", "HOUR"]).size().reset_index(name="RENTED_BIKE_COUNT")
        )

    if not aggregates:                                                 # the file had no parseable rows
        raise RuntimeError(f"Aggregation produced no rows for {path}")

    yearly = (                                                         # sum across per-chunk aggregates to true hourly totals
        pd.concat(aggregates, ignore_index=True)
          .groupby(["DATE", "HOUR"], as_index=False)["RENTED_BIKE_COUNT"]
          .sum()
    )
    print(f"    -> {len(yearly):,} hourly rows")                       # tiny output: ~8,760 rows per full year
    return yearly


def load_and_aggregate_trips() -> pd.DataFrame:
    """Glob OA-15182 year files in RAW_DIR; aggregate each; concat → seoul_trips_hourly.csv.

    Supports two source file layouts:
      Annual:  data/raw/seoul/2022_bike_rental.csv  (filename starts with 4-digit year)
      Monthly: data/raw/seoul/2025/jan.csv          (any CSV inside a 4-digit year subdir)

    When source CSVs are found and an existing intermediate (seoul_trips_hourly.csv) exists,
    unions them to preserve years whose source CSVs are no longer on disk (gitignored). A
    re-run guard skips the union if the new-source dates are already in the intermediate,
    preventing double-counting on repeat runs.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)                         # ensure raw directory exists

    annual_csvs  = sorted(glob.glob(str(RAW_DIR / "[0-9][0-9][0-9][0-9]*.csv")))       # annual files at root
    monthly_csvs = sorted(glob.glob(str(RAW_DIR / "[0-9][0-9][0-9][0-9]" / "*.csv")))  # monthly files in year subdirs
    csv_paths    = annual_csvs + monthly_csvs                                            # combine both layouts

    if not csv_paths:                                                  # abort with download instructions if none found
        raise FileNotFoundError(
            f"No year-prefixed source CSVs found in '{RAW_DIR}'.\n"
            "Download annual ZIPs from OA-15182 (no API key required):\n"
            "  https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do\n"
            "Recommended: 2022 + 2023 + 2024 + 2025.\n"
            f"Place annual CSVs directly in '{RAW_DIR}' (filenames must start with 4 digits)\n"
            f"or monthly CSVs in year subdirectories e.g. '{RAW_DIR}/2025/'."
        )
    print(f"Found {len(csv_paths)} OA-15182 source CSV(s)")           # Korean filenames omitted: cp1252 console

    per_year = [_aggregate_one_year(Path(p)) for p in csv_paths]      # aggregate one file at a time (bounded memory)

    if TRIPS_CSV.exists():                                             # intermediate exists — may have prior years to preserve
        existing       = pd.read_csv(TRIPS_CSV)                       # load committed 2022-2024 intermediate
        new_dates      = set(pd.concat(per_year, ignore_index=True)["DATE"].unique())   # dates from new source CSVs
        existing_dates = set(existing["DATE"].unique())                # dates already in intermediate
        if not new_dates.issubset(existing_dates):                     # new dates not yet present — safe to union
            per_year.append(existing)                                  # include existing to preserve prior years
            print(f"Unioned with existing {TRIPS_CSV} ({len(existing):,} rows, prior years preserved)")
        else:
            print(f"Re-run guard: new dates already in {TRIPS_CSV} — skipping union to prevent double-count")

    hourly = (                                                         # sum across per-file aggregates to true hourly totals
        pd.concat(per_year, ignore_index=True)
          .groupby(["DATE", "HOUR"], as_index=False)["RENTED_BIKE_COUNT"]
          .sum()
    )

    print(f"Hourly demand rows after concat: {len(hourly):,}")        # expect ~35,000 rows for 2022-2025
    print(f"RENTED_BIKE_COUNT stats:\n{hourly['RENTED_BIKE_COUNT'].describe()}")
    hourly.to_csv(TRIPS_CSV, index=False)                             # persist intermediate
    print(f"Saved: {TRIPS_CSV}")
    return hourly


# ── Step 2: Fetch weather from Open-Meteo ────────────────────────────────────
def fetch_weather() -> pd.DataFrame:
    """Fetch Open-Meteo Seoul weather; 3-attempt retry with exponential backoff; apply SOLAR conversion + VISIBILITY constant."""
    print(f"Fetching Seoul weather from Open-Meteo ({PARAMS['start_date']} to {PARAMS['end_date']})...")

    last_exc = None                                                    # remember last exception for final raise
    for attempt, backoff in enumerate((2, 4, 8), start=1):             # 3 attempts: sleep 2s/4s/8s between failures
        try:
            response = requests.get(OPENMETEO_URL, params=PARAMS, timeout=60)   # 60s; extended for 4-year fetch window
            response.raise_for_status()                                # raise HTTPError on 4xx/5xx
            break                                                      # success: exit retry loop
        except requests.RequestException as exc:                       # transient network / 5xx
            last_exc = exc                                             # capture for final raise
            print(f"  attempt {attempt} failed ({exc}); sleeping {backoff}s")
            time.sleep(backoff)                                        # exponential backoff
    else:                                                              # no break = all attempts failed
        raise RuntimeError(f"Open-Meteo failed after 3 attempts: {last_exc}")

    hourly = response.json()["hourly"]                                 # extract hourly dict from JSON response
    df     = pd.DataFrame(hourly)                                      # flatten to one row per hour

    df["time"] = pd.to_datetime(df["time"])                            # parse ISO datetime string
    df["DATE"] = df["time"].dt.strftime("%d/%m/%Y")                    # reformat to DD/MM/YYYY (Seoul schema)
    df["HOUR"] = df["time"].dt.hour                                    # integer hour 0-23
    df = df.drop(columns=["time"])                                     # remove raw datetime column

    # Apply Seoul-specific transforms before writing — see spec sections 7.6 and 7.8.
    df["SOLAR_RADIATION"] = (df["shortwave_radiation"] * _SOLAR_W_TO_MJ).round(2)   # W/m^2 → MJ/m^2 (UCI scale)
    df = df.drop(columns=["shortwave_radiation"])                                   # original column no longer needed
    df["VISIBILITY"] = _VISIBILITY_DEFAULT                                          # constant 2000 (Open-Meteo has no equivalent)

    df.to_csv(WEATHER_CSV, index=False)                                # persist weather CSV
    print(f"Saved {len(df):,} rows -> {WEATHER_CSV}")
    return df


# ── Step 3: Join trips + weather ──────────────────────────────────────────────
def join_trips_weather(trips: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Inner-join hourly trip demand with hourly weather on (DATE, HOUR)."""
    joined = trips.merge(weather, on=["DATE", "HOUR"], how="inner")    # drops edge hours with missing weather (rare)

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
    """Run prepare_seoul_from_joined on the joined CSV; assert all four seasons present."""
    PROCESSED_DIR.mkdir(exist_ok=True)                                 # ensure processed/ directory exists
    df_out = prepare_seoul_from_joined(str(joined_path))               # delegate column mapping + categoricals

    expected_seasons = {"Spring", "Summer", "Autumn", "Winter"}        # season completeness contract
    actual_seasons   = set(df_out["SEASONS"].unique())
    assert actual_seasons == expected_seasons, (                       # fail loudly if any season is missing
        f"Season assertion failed — training data incomplete.\n"
        f"Expected: {expected_seasons}\n"
        f"Got:      {actual_seasons}\n"
        "Extend the date range or check that the source CSVs cover all four seasons."
    )

    df_out.to_csv(OUTPUT_CSV, index=False)                             # write final training-ready CSV
    print(f"Final: {len(df_out):,} rows -> {OUTPUT_CSV}")
    print(f"Columns: {list(df_out.columns)}")                          # confirm all 14 Seoul-schema columns
    return df_out


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    trips = load_and_aggregate_trips()                                 # step 1: per-year aggregation → trips_hourly

    # Derive Open-Meteo date window from trips (OA-15182 release cadence varies year to year)
    trip_dates  = pd.to_datetime(trips["DATE"], format="%d/%m/%Y")     # parse DD/MM/YYYY trip dates
    date_min_str = trip_dates.min().strftime("%Y-%m-%d")               # YYYY-MM-DD format for Open-Meteo
    date_max_str = trip_dates.max().strftime("%Y-%m-%d")               # YYYY-MM-DD format for Open-Meteo
    PARAMS["start_date"] = date_min_str                                # override placeholder
    PARAMS["end_date"]   = date_max_str                                # override placeholder
    print(f"Open-Meteo window: {date_min_str} to {date_max_str}")

    weather = fetch_weather()                                          # step 2: weather + SOLAR conversion + VISIBILITY const
    join_trips_weather(trips, weather)                                 # step 3: inner-join on DATE + HOUR
    prepare_and_assert(JOINED_CSV)                                     # step 4: normalise + season assertion
    print("\nDone. Train with:")
    print("  python -m models.train --city seoul --data data/processed/seoul_bike_sharing.csv")
