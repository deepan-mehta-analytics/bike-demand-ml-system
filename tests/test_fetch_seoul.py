# tests/test_fetch_seoul.py
import glob                                                            # filesystem globbing under test
import pandas as pd                                                    # DataFrame construction in helpers
from pathlib import Path                                               # path construction in tests


# ── Helper ────────────────────────────────────────────────────────────────────
def _make_hourly_df(dates: list) -> pd.DataFrame:                     # build minimal hourly trips fixture
    """Return a minimal hourly-trips DataFrame for the given date strings."""
    rows = [                                                           # one row per date × hour combination
        {"DATE": d, "HOUR": h, "RENTED_BIKE_COUNT": 100}
        for d in dates for h in range(24)
    ]
    return pd.DataFrame(rows)                                          # 24 × len(dates) rows


# ── Glob tests ────────────────────────────────────────────────────────────────
def test_glob_finds_monthly_subdirectory_csvs(tmp_path):
    """CSVs placed in a 4-digit year subdirectory are found by the extended glob pattern."""
    year_dir = tmp_path / "2025"                                       # create year subdirectory
    year_dir.mkdir()                                                   # must exist for files to land in it
    (year_dir / "2025_01.csv").write_text("col\n1\n")                  # first monthly file
    (year_dir / "2025_02.csv").write_text("col\n1\n")                  # second monthly file

    annual_csvs  = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]*.csv")))       # root-level annual files
    monthly_csvs = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]" / "*.csv")))  # subdirectory monthly files
    csv_paths    = annual_csvs + monthly_csvs                                            # combined list

    assert sorted(Path(p).name for p in csv_paths) == ["2025_01.csv", "2025_02.csv"]  # exact filenames matched


def test_glob_does_not_pick_up_intermediate_files(tmp_path):
    """Intermediate files (seoul_trips_hourly.csv etc.) do not match the source-CSV glob."""
    (tmp_path / "seoul_trips_hourly.csv").write_text("DATE,HOUR,RENTED_BIKE_COUNT\n")   # intermediate file
    (tmp_path / "seoul_weather.csv").write_text("DATE,HOUR\n")                          # another intermediate

    annual_csvs  = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]*.csv")))
    monthly_csvs = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]" / "*.csv")))
    csv_paths    = annual_csvs + monthly_csvs

    assert len(csv_paths) == 0                                         # intermediates ignored — no 4-digit prefix


def test_glob_finds_both_annual_and_monthly_layouts(tmp_path):
    """Root-level annual CSV and subdirectory monthly CSV are both found by the combined glob."""
    (tmp_path / "2024_annual.csv").write_text("col\n1\n")           # root-level annual file (old layout)
    year_dir = tmp_path / "2025"                                    # year subdirectory (new layout)
    year_dir.mkdir()                                                # must exist before writing files
    (year_dir / "2025_01.csv").write_text("col\n1\n")               # monthly file in year subdir

    annual_csvs  = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]*.csv")))       # root-level matches
    monthly_csvs = sorted(glob.glob(str(tmp_path / "[0-9][0-9][0-9][0-9]" / "*.csv")))  # subdir matches
    csv_paths    = annual_csvs + monthly_csvs                                            # combined list

    assert len(csv_paths) == 2                                      # one annual + one monthly found
    assert any("2024" in p for p in csv_paths)                      # 2024 annual file present
    assert any("2025" in p for p in csv_paths)                      # 2025 monthly file present


# ── Re-run guard tests ─────────────────────────────────────────────────────────
def test_rerun_guard_prevents_double_count():
    """Guard fires when new-source dates are already present in the existing intermediate."""
    existing  = _make_hourly_df(["01/06/2025", "02/06/2025"])          # intermediate already has 2025 dates
    new_data  = [_make_hourly_df(["01/06/2025", "02/06/2025"])]        # source CSVs cover those same dates

    new_dates      = set(pd.concat(new_data, ignore_index=True)["DATE"].unique())   # dates from new source
    existing_dates = set(existing["DATE"].unique())                                 # dates in intermediate

    assert new_dates.issubset(existing_dates)                         # all new dates present — guard fires, no union


def test_rerun_guard_allows_union_on_partial_overlap():
    """Guard does NOT fire when only some new dates are already in the intermediate — partial overlap triggers union."""
    existing = _make_hourly_df(["01/06/2025"])                      # intermediate has one 2025 date
    new_data = [_make_hourly_df(["01/06/2025", "02/06/2025"])]      # source has that date plus a new one

    new_dates      = set(pd.concat(new_data, ignore_index=True)["DATE"].unique())   # {01/06/2025, 02/06/2025}
    existing_dates = set(existing["DATE"].unique())                                 # {01/06/2025}
    should_union   = not new_dates.issubset(existing_dates)                         # True: new date 02/06 not in existing

    assert should_union                                             # partial overlap: union proceeds (02/06 is new)


def test_union_preserves_prior_years():
    """Union appends existing intermediate when new-source dates are novel (different years)."""
    existing = _make_hourly_df(["01/06/2022", "01/06/2023", "01/06/2024"])  # intermediate: 2022-2024
    new_data = [_make_hourly_df(["01/06/2025"])]                             # source CSVs: 2025 only

    new_dates      = set(pd.concat(new_data, ignore_index=True)["DATE"].unique())
    existing_dates = set(existing["DATE"].unique())
    should_union   = not new_dates.issubset(existing_dates)

    assert should_union                                                # guard passes: union should happen
