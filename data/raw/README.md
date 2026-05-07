# Raw Data

Source files for each city's bike demand training pipeline. Files are preserved in their original format — no transformations applied here. Each city uses a dedicated subfolder.

---

## Directory Structure

```
data/raw/
├── seoul/
│   └── seoul_bike_sharing.csv       ← UCI ML Repository dataset
├── london/
│   └── london_merged.csv            ← Kaggle London Bike Sharing dataset
├── nyc/
│   ├── nyc_trips_hourly.csv         ← BigQuery export (hourly trip counts)
│   ├── nyc_weather.csv              ← Open-Meteo historical weather for NYC
│   └── nyc_joined.csv               ← trips + weather joined on DATE + HOUR
├── dc/
│   ├── dc_trips_hourly.csv          ← Capital Bikeshare trips aggregated to hourly
│   ├── dc_weather.csv               ← Open-Meteo historical weather for DC
│   ├── dc_joined.csv                ← trips + weather joined on DATE + HOUR
│   └── trips/                       ← raw Capital Bikeshare quarterly CSVs (not tracked in git)
└── selected_cities.csv              ← city list used by the R Shiny dashboard
```

---

## City Sources

### Seoul — `seoul/seoul_bike_sharing.csv`

- **Source:** [UCI ML Repository — Seoul Bike Sharing Demand](https://archive.ics.uci.edu/dataset/560/seoul+bike+sharing+demand)
- **Coverage:** Dec 2017 – Nov 2018 (8,760 hourly rows)
- **Format:** Already in Seoul schema — used directly by `models/train.py`
- **Columns:** DATE (DD/MM/YYYY), HOUR, TEMPERATURE, HUMIDITY, WIND_SPEED, VISIBILITY, DEW_POINT_TEMPERATURE, SOLAR_RADIATION, RAINFALL, SNOWFALL, SEASONS, HOLIDAY, FUNCTIONING_DAY, RENTED_BIKE_COUNT

### London — `london/london_merged.csv`

- **Source:** [Kaggle — London Bike Sharing Dataset](https://www.kaggle.com/datasets/hmavrodiev/london-bike-sharing-dataset)
- **Coverage:** 2015–2017 (17,414 hourly rows)
- **Format:** Kaggle schema — normalised to Seoul schema via `data/prepare_city_data.prepare_london()`
- **Key differences:** Wind speed in km/h (converted ÷3.6 to m/s); season as integer 0–3; no VISIBILITY/SOLAR_RADIATION columns (zeroed in prepare step)

### NYC — `nyc/`

- **Source:** BigQuery `bigquery-public-data.new_york_citibike.citibike_trips` (2014–2018) + Open-Meteo historical API
- **Coverage:** 2014–2018 (34,187 hourly rows after join)
- **`nyc_trips_hourly.csv`** — exported from BigQuery console; columns: DATE (DD/MM/YYYY), HOUR, RENTED_BIKE_COUNT
- **`nyc_weather.csv`** — Open-Meteo archive (lat=40.71, lng=-74.01, timezone=America/New_York); columns: DATE, HOUR + 7 weather variables
- **`nyc_joined.csv`** — inner join of the above two files on DATE + HOUR
- Regenerate with: `python -m data.fetch_nyc_weather`

### Washington DC — `dc/`

- **Source:** [Capital Bikeshare System Data](https://capitalbikeshare.com/system-data) (2014–2018) + Open-Meteo historical API
- **Coverage:** 2014–2018 (37,663 hourly rows after join)
- **`dc/trips/`** — raw quarterly/annual Capital Bikeshare CSV files (not committed to git — download from Capital Bikeshare and extract here)
- **`dc_trips_hourly.csv`** — Capital Bikeshare trips aggregated to DATE + HOUR (produced by `fetch_dc_weather.py`)
- **`dc_weather.csv`** — Open-Meteo archive (lat=38.8951, lng=-77.0364, timezone=America/New_York)
- **`dc_joined.csv`** — inner join of trips + weather on DATE + HOUR
- Regenerate with: `python data/fetch_dc_weather.py`

### `selected_cities.csv`

- City metadata (name, coordinates, population) for the companion R Shiny dashboard
- Not used in model training — consumed by `shiny_app/` in the R repo

---

## Notes

- Files in this directory are the **single source of truth** — do not modify them
- All normalisation to Seoul schema happens in `data/prepare_city_data.py`
- Normalised outputs land in `data/processed/`
- `dc/trips/` is excluded from git (large raw CSVs); all other files in this directory are tracked
