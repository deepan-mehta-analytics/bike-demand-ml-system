"""Export each city's Random Forest feature importances to reports/feature_importance.csv.

The companion Shiny dashboard shows "What drives demand in {city}" from this file
(2026-11-27). One-hot columns (SEASONS_*, HOLIDAY_*, FUNCTIONING_DAY_*) are summed
back into their source feature so the chart shows "Season", not four season dummies.

Usage:  python -m models.export_feature_importance
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import csv                                                              # write the output table
from pathlib import Path                                                # filesystem paths

import joblib                                                           # load the saved model + feature schema

# ── Configuration ─────────────────────────────────────────────────────────────
ARTIFACTS = Path("models/artifacts")                                    # per-city artifact folders
OUTPUT = Path("reports/feature_importance.csv")                         # published table (tracked in git)
CITIES = ["seoul", "london", "nyc", "dc", "paris", "chicago"]           # every trained city
ONE_HOT_PREFIXES = ("SEASONS_", "HOLIDAY_", "FUNCTIONING_DAY_")         # dummy columns to fold back together


# ── Helpers ───────────────────────────────────────────────────────────────────

def base_feature(column: str) -> str:
    """Map a model column to the feature a person would name (SEASONS_Winter -> SEASONS)."""
    for prefix in ONE_HOT_PREFIXES:                                     # check each one-hot family
        if column.startswith(prefix):                                   # dummy column of that family
            return prefix.rstrip("_")                                   # family name without the trailing underscore
    return column                                                       # ordinary numeric feature


def city_importances(columns: list, importances: list) -> list:
    """Return [(feature, importance)] with one-hot columns summed, sorted high to low."""
    totals = {}                                                         # feature -> summed importance
    for column, value in zip(columns, importances):                     # pair each column with its weight
        feature = base_feature(column)                                  # fold dummies into their family
        totals[feature] = totals.get(feature, 0.0) + float(value)       # accumulate
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)   # most important first


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Read every city's artifacts and write one CSV row per (city, feature)."""
    rows = []                                                           # output rows
    for city in CITIES:                                                 # each trained city
        folder = ARTIFACTS / city                                       # its artifact folder
        # joblib/pickle can run code on load; safe here because these files are this
        # repo's own training output (models/train.py), never downloaded input.
        model = joblib.load(folder / "random_forest_model.pkl")         # trained RandomForestRegressor
        columns = list(joblib.load(folder / "feature_columns.pkl"))     # column order used in training
        for rank, (feature, value) in enumerate(city_importances(columns, model.feature_importances_), start=1):
            rows.append({"city": city, "rank": rank, "feature": feature, "importance": round(value, 4)})  # one row
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)                    # create reports/ if missing
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:      # overwrite the table
        writer = csv.DictWriter(handle, fieldnames=["city", "rank", "feature", "importance"])  # fixed column order
        writer.writeheader()                                            # header row
        writer.writerows(rows)                                          # data rows
    print(f"Wrote {len(rows)} rows for {len(CITIES)} cities to {OUTPUT}")  # summary for the console


if __name__ == "__main__":                                              # run as a script
    main()
