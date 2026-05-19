# Processed Data

Seoul-schema CSVs ready for `models/train.py`, plus two legacy files from the original R Shiny v1.0 pipeline. All files here are generated outputs — do not edit directly.

---

## Files

### Active — multi-city training inputs

These three files share an identical 14-column Seoul schema and are passed directly to `models/train.py --city <name> --data <path>`.

| File | City | Rows | Source | How to regenerate |
|---|---|---|---|---|
| `london_bike_sharing.csv` | London | 17,414 | `data/raw/london/london_merged.csv` | `prepare_city_data.prepare_london()` |
| `nyc_bike_sharing.csv` | NYC | 34,187 | `data/raw/nyc/nyc_joined.csv` | `python -m data.fetch_nyc_weather` |
| `dc_bike_sharing.csv` | Washington DC | 37,663 | `data/raw/dc/dc_joined.csv` | `python data/fetch_dc_weather.py` |
| `paris_bike_sharing.csv` | Paris | 26,297 | `data/raw/paris/paris_joined.csv` | `python -m data.fetch_paris_weather` |
| `chicago_bike_sharing.csv` | Chicago | 32,720 | `data/raw/chicago/chicago_joined.csv` | `python -m data.fetch_chicago_weather` |

Seoul itself (`data/raw/seoul/seoul_bike_sharing.csv`) is already in Seoul schema and is loaded directly by `models/train.py` without a processed intermediate.

**Seoul schema** — 14 columns common to all four files:

```
DATE (DD/MM/YYYY), HOUR (0-23),
TEMPERATURE (°C), HUMIDITY (%), WIND_SPEED (m/s), VISIBILITY (10m units),
DEW_POINT_TEMPERATURE (°C), SOLAR_RADIATION (MJ/m²), RAINFALL (mm), SNOWFALL (cm),
SEASONS, HOLIDAY, FUNCTIONING_DAY,
RENTED_BIKE_COUNT  ← training target
```

---

### Legacy — R Shiny v1.0 pipeline (Seoul only)

These files were produced during the original R-based Seoul analysis and are retained for reference. They are **not consumed by the current Python ML system**.

| File | Shape | Description |
|---|---|---|
| `clean_bike_data.csv` | 8,465 × 18 | Seoul data after cleaning + one-hot encoding (lowercase columns, `season_spring/summer/autumn/winter` flags) — output of the original R pre-processing notebook |
| `model.csv` | 33 × 2 | Linear regression coefficients (`Variable`, `Coef`) from the R Shiny v1.0 local model; consumed by the Shiny app when `USE_FASTAPI=false` |

---

## Notes

- Generated files — do not edit manually
- Regenerate by running the relevant fetch/prepare script (see table above)
- Training commands:
  ```
  python -m models.train --city london  --data data/processed/london_bike_sharing.csv
  python -m models.train --city nyc     --data data/processed/nyc_bike_sharing.csv
  python -m models.train --city dc      --data data/processed/dc_bike_sharing.csv
  python -m models.train --city paris   --data data/processed/paris_bike_sharing.csv
  python -m models.train --city chicago --data data/processed/chicago_bike_sharing.csv
  ```
