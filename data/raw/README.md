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
├── paris/
│   ├── paris_trips_hourly.csv       ← Vélib' Métropole counter records aggregated to hourly
│   ├── paris_weather.csv            ← Open-Meteo historical weather for Paris
│   ├── paris_joined.csv             ← counter + weather joined on DATE + HOUR
│   ├── [year]_comptage*.csv         ← raw opendata.paris.fr annual ZIPs (not tracked in git — ~1-2 GB each)
│   └── comptage*.csv                ← raw rolling-window opendata.paris.fr CSV (not tracked in git)
├── chicago/
│   ├── chicago_trips_hourly.csv     ← Divvy trips aggregated to hourly
│   ├── chicago_weather.csv          ← Open-Meteo historical weather for Chicago
│   ├── chicago_joined.csv           ← trips + weather joined on DATE + HOUR
│   └── trips/                       ← raw Divvy quarterly CSVs (not tracked in git)
└── selected_cities.csv              ← city list used by the R Shiny dashboard
```

---

## City Sources

### Seoul — `seoul/`

- **Source:** [Seoul Open Data Plaza — 따릉이 대여이력 (OA-15182)](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do) + Open-Meteo historical API
- **Coverage:** Jan 2022 – Dec 2024 (26,303 hourly rows after join)
- **Raw monthly CSVs** — 36 files named `YYYY-MM.csv` (cp949-encoded per-trip logs, ~23 GB total); downloaded as annual ZIPs from data.seoul.go.kr and gitignored
- **`seoul_trips_hourly.csv`** — aggregated hourly trip counts; columns: DATE (DD/MM/YYYY), HOUR, RENTED_BIKE_COUNT
- **`seoul_weather.csv`** — Open-Meteo archive (lat=37.57, lng=126.98, timezone=Asia/Seoul); columns: DATE, HOUR + 7 weather variables
- **`seoul_joined.csv`** — inner join of the above two files on DATE + HOUR
- Regenerate with: `python -m data.fetch_seoul_weather`

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

### Paris — `paris/`

- **Source:** [opendata.paris.fr — Vélib' Métropole counter data](https://opendata.paris.fr/explore/dataset/comptage-velo-donnees-compteurs/) (annual ZIPs, 2022–2024) + Open-Meteo historical API
- **Coverage:** 2023–2024 (17,539 hourly rows after MEAN-counter aggregation, weather join, and the v4.3.0 Option B 2022 drop). The 2022 export CSV is still on disk and loaded by the fetch script, but its rows are filtered out at the post-concat stage — see Option B note below.
- **Annual ZIPs** (gitignored) — large opendata.paris.fr downloads: `2023_comptage-velo-donnees-compteurs.csv` (~1.2 GB), `2024-comptage-velo-donnees-compteurs.csv` (~1.7 GB), `comptage-velo-donnees-compteurs.csv` (~390 MB rolling-window 2022 file). Patterns `[0-9]{4}*.csv` and `comptage*.csv` excluded by `.gitignore`.
- **`paris_trips_hourly.csv`** — counter records aggregated to DATE + HOUR using MEAN across all stations (normalised counter scale)
- **`paris_weather.csv`** — Open-Meteo archive (lat=48.8566, lng=2.3522, timezone=Europe/Paris)
- **`paris_joined.csv`** — inner join of counter + weather on DATE + HOUR
- Regenerate with: `python -m data.fetch_paris_weather`
- **Note on scale:** Paris uses MEAN counter values, not raw station sums — RMSE of 20.51 bikes/hr (post-v4.3.0; was 23.30 in v1.4.0 baseline) is correct for this normalised scale (~50–500/hr range), not directly comparable to other cities' raw counts.
- **Option B 2022 drop (v4.3.0):** the 2022 export from opendata.paris.fr peaks 2h later than 2023+2024 in both AM and PM rush hours and is DST-consistent within 2022 — an intrinsic provider-side aggregation anomaly, not a timezone parser bug on our side. The fetch script (`data/fetch_paris_weather.py:135-149`) filters 2022 rows out at the post-concat stage as a data-quality gate. Reversible by removing that single block if upstream ever publishes a correction.

### Chicago — `chicago/`

- **Source:** [Divvy Bikes System Data](https://divvybikes.com/system-data) (quarterly CSVs, 2019–2022) + Open-Meteo historical API
- **Coverage:** 2019–2022 (32,720 hourly rows; 37 of 38 quarters loaded — Q2-2019 skipped due to a different Divvy column schema)
- **`chicago/trips/`** — raw Divvy quarterly CSV files (not committed to git — download from Divvy and extract here)
- **`chicago_trips_hourly.csv`** — Divvy trips aggregated to DATE + HOUR (produced by `fetch_chicago_weather.py`)
- **`chicago_weather.csv`** — Open-Meteo archive (lat=41.8781, lng=-87.6298, timezone=America/Chicago)
- **`chicago_joined.csv`** — inner join of trips + weather on DATE + HOUR
- Regenerate with: `python -m data.fetch_chicago_weather`

### `selected_cities.csv`

- City metadata (name, coordinates, population) for the companion R Shiny dashboard
- Not used in model training — consumed by `shiny_app/` in the R repo

---

## Notes

- Files in this directory are the **single source of truth** — do not modify them
- All normalisation to Seoul schema happens in `data/prepare_city_data.py`
- Normalised outputs land in `data/processed/`
- **Gitignored raw downloads** (large, regenerable): `dc/trips/`, `chicago/trips/`, and `paris/[0-9]{4}*.csv` + `paris/comptage*.csv` patterns
- **Tracked intermediate CSVs** (small, deterministic outputs of fetch scripts): every `<city>_trips_hourly.csv`, `<city>_weather.csv`, `<city>_joined.csv` is committed for reproducibility — same pattern across DC, Paris, and Chicago
