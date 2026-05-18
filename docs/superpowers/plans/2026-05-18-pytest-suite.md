# Pytest Suite — Three-Tier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 12 new tests across three tiers: a feature schema guard, per-city RMSE gates, and a no-fallback routing guarantee; wire the RMSE gates into a dedicated CI job.

**Architecture:** Tier 1 extends the existing `test_features.py`. Tiers 2 and 3 are new files. `pytest.ini` gains a `slow` marker. CI gains Job 7 (`accuracy`) running only on push to main, parallel to the existing `test` job.

**Tech Stack:** pytest 9, scikit-learn 1.8 (`root_mean_squared_error`), joblib, pandas 3, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-18-pytest-suite-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `pytest.ini` | Modify | Register `slow` marker to suppress PytestUnknownMarkWarning |
| `tests/test_features.py` | Modify | Add `full_schema_df` fixture + `test_feature_schema_is_frozen` |
| `tests/test_model_accuracy.py` | Create | 6 `@pytest.mark.slow` parametrised RMSE gate tests |
| `tests/test_routing.py` | Create | 5 routing / no-fallback tests |
| `.github/workflows/ci.yml` | Modify | Add Job 7: `accuracy` |

---

## Task 1: Register the `slow` marker in pytest.ini

**Files:**
- Modify: `pytest.ini`

- [ ] **Step 1: Update pytest.ini**

Replace the current content with:

```ini
[pytest]
pythonpath = .
markers =
    slow: marks tests as slow-running RMSE accuracy checks (run with -m slow)
```

- [ ] **Step 2: Verify no warnings**

Run: `pytest tests/ --co -q`  
Expected: collection output with no `PytestUnknownMarkWarning` lines.

- [ ] **Step 3: Commit**

```bash
git add pytest.ini
git commit -m "test(config): register slow marker in pytest.ini"
```

---

## Task 2: Tier 1 — Feature schema guard

**Files:**
- Modify: `tests/test_features.py`

- [ ] **Step 1: Add the frozen column constant and full_schema_df fixture**

Open `tests/test_features.py`. After the existing imports block, add the frozen set constant. After the existing `sample_df` fixture, add `full_schema_df`. Insert the text below at the correct positions:

At the top of the file, **after the existing imports**, add:

```python
# ── Frozen Feature Schema ─────────────────────────────────────────────────
# Update only after retraining all 6 city models + rebuilding Vertex AI container.
EXPECTED_COLUMNS = frozenset({                                # canonical column set produced by create_features + get_feature_target
    # ── Numeric weather features ──────────────────────────
    "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",          # core demand signals
    "VISIBILITY", "DEW_POINT_TEMPERATURE",                    # atmospheric conditions
    "SOLAR_RADIATION", "RAINFALL", "SNOWFALL",                # precipitation and solar
    # ── Temporal features (derived by create_features) ───
    "year", "month", "day", "dayofweek",                      # date components parsed from DATE column
    # ── One-hot: SEASONS ─────────────────────────────────
    "SEASONS_Autumn", "SEASONS_Spring",                       # season dummies (Seoul schema)
    "SEASONS_Summer", "SEASONS_Winter",                       # all four seasons must be present
    # ── One-hot: HOLIDAY ─────────────────────────────────
    "HOLIDAY_Holiday", "HOLIDAY_No Holiday",                  # public holiday flag dummies
    # ── One-hot: FUNCTIONING_DAY ─────────────────────────
    "FUNCTIONING_DAY_No", "FUNCTIONING_DAY_Yes",              # system operational flag dummies
})
```

After the existing `sample_df` fixture, add:

```python
@pytest.fixture
def full_schema_df():
    """Multi-row DataFrame covering every categorical value so pd.get_dummies produces the full schema."""
    rows = []                                                 # accumulate one row per seasonal + holiday combo
    for season in ["Spring", "Summer", "Autumn", "Winter"]:  # all four seasons must be represented
        for holiday in ["Holiday", "No Holiday"]:            # both holiday states must be represented
            for func_day in ["Yes", "No"]:                   # both functioning-day states must be represented
                rows.append({                                 # build one complete record per combination
                    "DATE": "01/06/2018",                    # fixed date — temporal values don't vary here
                    "HOUR": 8,                               # fixed hour
                    "TEMPERATURE": 15.0,                     # fixed numeric features
                    "HUMIDITY": 60,
                    "WIND_SPEED": 2.5,
                    "VISIBILITY": 1500,
                    "DEW_POINT_TEMPERATURE": 7.0,
                    "SOLAR_RADIATION": 0.8,
                    "RAINFALL": 0.0,
                    "SNOWFALL": 0.0,
                    "SEASONS": season,                       # vary season per row
                    "HOLIDAY": holiday,                      # vary holiday per row
                    "FUNCTIONING_DAY": func_day,             # vary functioning day per row
                    "RENTED_BIKE_COUNT": 500,                # target column — required by get_feature_target
                })
    return pd.DataFrame(rows)                                # 16-row DataFrame covering all categorical combos
```

- [ ] **Step 2: Add the schema guard test**

At the end of `tests/test_features.py`, append:

```python
# ── Schema Guard ──────────────────────────────────────────────────────────

def test_feature_schema_is_frozen(full_schema_df):
    """Feature column set must not change without retraining all city models."""
    df = create_features(full_schema_df.copy())              # derive temporal columns from DATE
    X, _ = get_feature_target(df)                            # one-hot encode and drop target + DATE
    assert set(X.columns) == EXPECTED_COLUMNS, (             # exact column set must match frozen schema
        "Feature schema changed. Before merging:\n"
        "  - retrain all 6 city models: seoul, london, nyc, dc, paris, chicago\n"
        "  - rebuild and push the Vertex AI training container (Dockerfile.training)\n"
        "  - verify RMSE gates still pass: pytest -m slow tests/test_model_accuracy.py"
    )
```

- [ ] **Step 3: Run to verify it passes**

Run: `pytest tests/test_features.py -v`  
Expected: 10 tests collected, all PASSED. Confirm `test_feature_schema_is_frozen` is in the list.

- [ ] **Step 4: Commit**

```bash
git add tests/test_features.py
git commit -m "test(features): add feature schema frozen-set guard"
```

---

## Task 3: Tier 2 — RMSE gate tests

**Files:**
- Create: `tests/test_model_accuracy.py`

- [ ] **Step 1: Create the file**

```python
# ── Imports ───────────────────────────────────────────────────────────────
import numpy as np                                            # RMSE computation
import pandas as pd                                           # CSV loading
import pytest                                                 # test framework and slow marker
from sklearn.ensemble import RandomForestRegressor            # same model class used in train.py
from sklearn.metrics import root_mean_squared_error           # sklearn 1.4+ dedicated RMSE function

from models.features import create_features, get_feature_target  # shared feature pipeline


# ── City Config ───────────────────────────────────────────────────────────
# Each tuple: (csv_path, city_label, rmse_threshold)
# Thresholds carry ~50% headroom above trained RMSE — tight enough to catch regressions,
# loose enough to survive minor random-state variance in a fresh training run.
_CITY_CONFIGS = [
    ("data/processed/clean_bike_data.csv",    "seoul",   250),  # trained RMSE 173.21; threshold 250
    ("data/processed/london_bike_sharing.csv", "london",  350),  # trained RMSE 228.58; threshold 350
    ("data/processed/nyc_bike_sharing.csv",    "nyc",     500),  # trained RMSE 345.69; threshold 500
    ("data/processed/dc_bike_sharing.csv",     "dc",      150),  # trained RMSE  97.47; threshold 150
    ("data/processed/paris_bike_sharing.csv",  "paris",    50),  # trained RMSE  23.30; threshold  50 (normalised MEAN scale)
    ("data/processed/chicago_bike_sharing.csv","chicago",  350),  # trained RMSE 202.99; threshold 350
]


# ── RMSE Gate ─────────────────────────────────────────────────────────────

@pytest.mark.slow                                             # excluded from Job 2; runs in Job 7 (push to main only)
@pytest.mark.parametrize(
    "csv_path, city, threshold",
    _CITY_CONFIGS,
    ids=[cfg[1] for cfg in _CITY_CONFIGS],                   # label each test by city name
)
def test_city_rmse_within_threshold(csv_path, city, threshold):
    """Train a fresh RF from the committed CSV and assert holdout RMSE is below threshold.

    Catches data-quality regressions and feature-pipeline breaks.
    Does NOT test production .pkl artifacts — that is a separate concern.
    """
    # ── Load + feature engineering ────────────────────────────────────────
    df = pd.read_csv(csv_path)                               # load committed processed CSV from repo
    df = create_features(df)                                 # derive temporal columns from DATE
    X, y = get_feature_target(df)                           # one-hot encode; split features and target

    # ── Chronological 80/20 split (mirrors train.py) ──────────────────────
    split_idx = int(len(df) * 0.8)                          # 80% boundary index — no shuffle, preserves time order
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]  # earlier rows for training
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]  # later rows for evaluation

    # ── Train ─────────────────────────────────────────────────────────────
    model = RandomForestRegressor(n_estimators=100, random_state=42)  # matches train.py hyperparameters
    model.fit(X_train, y_train)                              # fit on training partition

    # ── Evaluate ──────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)                           # generate holdout predictions
    rmse = root_mean_squared_error(y_test, y_pred)           # sklearn 1.4+ dedicated function; no squared kwarg needed

    # ── Assert ────────────────────────────────────────────────────────────
    assert rmse < threshold, (                               # regression guard
        f"{city} RMSE {rmse:.2f} exceeds threshold {threshold}. "
        f"Check data/processed/ for CSV corruption or schema changes in models/features.py."
    )
```

- [ ] **Step 2: Verify the slow marker excludes these from the fast job**

Run: `pytest tests/test_model_accuracy.py --co -q`  
Expected: 6 tests collected (`seoul`, `london`, `nyc`, `dc`, `paris`, `chicago`).

Run: `pytest tests/ -m "not slow" --co -q`  
Expected: 0 tests from `test_model_accuracy.py` in the list.

- [ ] **Step 3: Run the RMSE gates and confirm all pass**

Run: `pytest -m slow tests/test_model_accuracy.py -v`  
Expected: 6 tests PASSED. This will take ~5 minutes (6 RF training runs).

- [ ] **Step 4: Commit**

```bash
git add tests/test_model_accuracy.py
git commit -m "test(accuracy): add per-city RMSE gate tests (slow marker)"
```

---

## Task 4: Tier 3 — No-fallback routing tests

**Files:**
- Create: `tests/test_routing.py`

- [ ] **Step 1: Create the file**

```python
# ── Imports ───────────────────────────────────────────────────────────────
import joblib                                                 # save/load tiny RF artifacts to tmp_path
import numpy as np                                            # synthetic training data for tiny RF
import pytest                                                 # test framework, fixtures, monkeypatch
from sklearn.ensemble import RandomForestRegressor            # real model — not MagicMock — so predict() validates feature alignment

import services.predictor                                     # module under test; _cache and helpers live here


# ── Shared Test Record ────────────────────────────────────────────────────
# One valid input dict that predict_service() can consume.
# SEASONS=Summer so get_dummies produces SEASONS_Summer only — reindex fills others with 0.
_RECORD = {                                                   # minimal valid prediction input record
    "DATE": "01/06/2018",                                    # DD/MM/YYYY — parsed by create_features
    "HOUR": 8,                                               # integer hour
    "TEMPERATURE": 15.0,                                     # float Celsius
    "HUMIDITY": 60,                                          # integer percent
    "WIND_SPEED": 2.5,                                       # float m/s
    "VISIBILITY": 1500,                                      # integer 10m units
    "DEW_POINT_TEMPERATURE": 7.0,                            # float Celsius
    "SOLAR_RADIATION": 0.8,                                  # float MJ/m^2
    "RAINFALL": 0.0,                                         # float mm
    "SNOWFALL": 0.0,                                         # float cm
    "SEASONS": "Summer",                                     # categorical — produces SEASONS_Summer dummy
    "HOLIDAY": "No Holiday",                                 # categorical — produces HOLIDAY_No Holiday dummy
    "FUNCTIONING_DAY": "Yes",                                # categorical — produces FUNCTIONING_DAY_Yes dummy
}

# ── Feature columns produced by predict.py from _RECORD ───────────────────
# predict.py: create_features → drop DATE → get_dummies → reindex(feature_columns)
# With SEASONS=Summer/HOLIDAY=No Holiday/FUNCTIONING_DAY=Yes, get_dummies produces exactly these 16 columns.
_FEATURE_COLUMNS = [                                         # must match get_dummies output for _RECORD exactly
    "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",         # numeric weather
    "VISIBILITY", "DEW_POINT_TEMPERATURE",                   # atmospheric
    "SOLAR_RADIATION", "RAINFALL", "SNOWFALL",               # precipitation and solar
    "year", "month", "day", "dayofweek",                     # temporal — added by create_features
    "SEASONS_Summer",                                        # only Summer present in _RECORD
    "HOLIDAY_No Holiday",                                    # only No Holiday present in _RECORD
    "FUNCTIONING_DAY_Yes",                                   # only Yes present in _RECORD
]


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tiny_rf(tmp_path):
    """Build a minimal real RF + schema pkl in tmp_path — enough for predict() to run without error."""
    X = np.random.default_rng(0).random((20, len(_FEATURE_COLUMNS)))  # synthetic training data; 20 rows × 16 features
    y = np.random.default_rng(0).random(20) * 500            # synthetic target values
    model = RandomForestRegressor(n_estimators=3, random_state=0)  # tiny tree count — speed, not accuracy
    model.fit(X, y)                                          # fit on synthetic data
    joblib.dump(model, tmp_path / "random_forest_model.pkl") # save model artifact
    joblib.dump(_FEATURE_COLUMNS, tmp_path / "feature_columns.pkl")  # save schema artifact
    return tmp_path                                          # return dir path so tests can reference pkl files


@pytest.fixture(autouse=True)
def clear_cache():
    """Wipe the module-level artifact cache before and after each test to prevent cross-test bleed."""
    services.predictor._cache.clear()                        # clear before: start each test with empty cache
    yield                                                    # run the test
    services.predictor._cache.clear()                        # clear after: paranoid teardown


# ── Helper ────────────────────────────────────────────────────────────────

def _wire(monkeypatch, tiny_rf, exists_for: str):
    """Monkeypatch _artifact_dir_exists and load_artifacts for a single target city.

    Args:
        exists_for: the artifact key that should appear to have trained artifacts.
                    Pass None to simulate no artifacts existing (fallback scenario).
    """
    loaded = []                                              # capture which city key load_artifacts is called with

    def fake_exists(city):                                   # replace filesystem check
        return city == exists_for                            # True only for the target city

    def fake_load(city):                                     # replace joblib disk load
        loaded.append(city)                                  # record the key that was requested
        return (                                             # return tiny RF artifacts from tmp_path
            joblib.load(tiny_rf / "random_forest_model.pkl"),
            joblib.load(tiny_rf / "feature_columns.pkl"),
        )

    monkeypatch.setattr(services.predictor, "_artifact_dir_exists", fake_exists)  # patch filesystem guard
    monkeypatch.setattr(services.predictor, "load_artifacts", fake_load)          # patch disk load
    return loaded                                            # caller inspects this list to verify routing


# ── Routing Tests ─────────────────────────────────────────────────────────

def test_paris_routes_to_paris_artifacts(monkeypatch, tiny_rf):
    """city='paris' must load the paris artifact, not the seoul fallback."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="paris") # paris artifacts exist; nothing else does
    services.predictor.predict_service(data=[_RECORD], city="paris")  # call service with paris
    assert loaded == ["paris"], f"Expected load_artifacts('paris'), got {loaded}"  # must not fall back


def test_chicago_routes_to_chicago_artifacts(monkeypatch, tiny_rf):
    """city='chicago' must load the chicago artifact, not the seoul fallback."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="chicago")  # chicago artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="chicago")
    assert loaded == ["chicago"], f"Expected load_artifacts('chicago'), got {loaded}"


def test_new_york_slug_resolves_to_nyc(monkeypatch, tiny_rf):
    """city='new york' must resolve via _CITY_SLUG_MAP to 'nyc' and load nyc artifacts."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="nyc")   # nyc artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="new york")  # R Shiny sends "new york"
    assert loaded == ["nyc"], f"Expected load_artifacts('nyc'), got {loaded}"


def test_washington_dc_slug_resolves_to_dc(monkeypatch, tiny_rf):
    """city='washington dc' must resolve via _CITY_SLUG_MAP to 'dc' and load dc artifacts."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="dc")    # dc artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="washington dc")  # R Shiny sends "washington dc"
    assert loaded == ["dc"], f"Expected load_artifacts('dc'), got {loaded}"


def test_missing_city_falls_back_to_seoul(monkeypatch, tiny_rf):
    """An unrecognised city with no artifacts must fall back to 'seoul', not raise."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for=None)    # no city has artifacts (exists_for=None → always False)

    # Patch fake_exists to also return True for seoul so fallback load succeeds
    monkeypatch.setattr(
        services.predictor, "_artifact_dir_exists",
        lambda city: city == "seoul",                        # only seoul "exists" — allows fallback load to complete
    )
    services.predictor.predict_service(data=[_RECORD], city="atlantis")  # unknown city
    assert "seoul" in loaded, f"Expected fallback to 'seoul', got {loaded}"  # must have loaded seoul artifacts
```

- [ ] **Step 2: Run the routing tests and confirm all pass**

Run: `pytest tests/test_routing.py -v`  
Expected: 5 tests PASSED. All should run in under 5 seconds.

- [ ] **Step 3: Run the full fast suite to confirm nothing broken**

Run: `pytest tests/ -m "not slow" -v`  
Expected: 20 tests PASSED (10 features + 6 api + 4 routing; `test_pipeline.py` skips if no beam; `test_model_accuracy.py` excluded by marker).

Wait — test_routing.py has 5 tests. test_features.py has 10. test_api.py has 6. So total fast tests = 21 (plus any skipped from test_pipeline.py). The exact count may vary. What matters: 0 failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_routing.py
git commit -m "test(routing): add no-fallback city artifact routing guarantee"
```

---

## Task 5: Add CI Job 7 — RMSE accuracy gates

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add Job 7 to ci.yml**

At the end of `.github/workflows/ci.yml` (after the `build-training-container` job), append:

```yaml
  # Job 7: RMSE accuracy gates
  # Trains a fresh RF per city from committed processed CSVs; asserts RMSE < threshold.
  # Runs only on push to main (not PRs); parallel to Job 2 (test).
  # Wall time: ~5 min. No GCP credentials needed — pure pandas + sklearn.
  accuracy:
    name: RMSE accuracy gates
    runs-on: ubuntu-latest                                  # standard GitHub-hosted runner
    needs: lint                                             # run parallel to test job; skip if lint fails
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4                           # check out source and committed CSVs
      - uses: actions/setup-python@v5                       # provision Python
        with:
          python-version: "3.11"                            # match all other jobs
      - run: pip install -r requirements.txt                # install sklearn, pandas, joblib, pytest
      - run: pytest -m slow tests/test_model_accuracy.py -v  # run only the 6 RMSE gate tests
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" `  
Expected: no output (no parse error).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add Job 7 accuracy gate — per-city RMSE checks on push to main"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run complete fast test suite**

Run: `pytest tests/ -m "not slow" -v`  
Expected: all tests PASSED, 0 failures. `test_model_accuracy.py` tests are deselected (not run).

- [ ] **Step 2: Run RMSE gates one more time**

Run: `pytest -m slow tests/test_model_accuracy.py -v`  
Expected: 6 tests PASSED.

- [ ] **Step 3: Check total test counts**

Run: `pytest tests/ --co -q`  
Expected output summary should show:
- `test_features.py`: 10 tests
- `test_api.py`: 6 tests
- `test_routing.py`: 5 tests
- `test_model_accuracy.py`: 6 tests (slow)
- `test_pipeline.py`: skipped or 0 (no beam dep)

- [ ] **Step 4: Push to main**

```bash
git push origin main
```

Expected: CI triggers; Job 7 (`accuracy`) appears in the Actions run alongside Jobs 1–6.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Tier 1: schema guard in test_features.py | Task 2 |
| Tier 2: 6 RMSE gates, `@pytest.mark.slow`, chrono split, thresholds | Task 3 |
| Tier 3: 5 routing tests, tmp_path + monkeypatch, real RF, cache cleared | Task 4 |
| pytest.ini `markers` declaration | Task 1 |
| CI Job 7: push to main only, parallel to test, `pytest -m slow` | Task 5 |

All spec requirements covered. ✓

**Placeholder scan:** No TBDs, no "similar to task N", all code blocks are complete. ✓

**Type consistency:**
- `tiny_rf` fixture returns `tmp_path` (a `pathlib.Path`); all tests access it as `tiny_rf / "file.pkl"` ✓
- `_wire` returns `loaded` list; all tests assert against `loaded` ✓
- `services.predictor._cache` cleared via `.clear()` — matches `Dict` type in predictor.py:40 ✓
- `services.predictor._artifact_dir_exists` patched as a lambda — matches `def _artifact_dir_exists(city: str) -> bool` signature ✓
- `services.predictor.load_artifacts` patched as a function returning `(model, feature_columns)` tuple — matches `load_artifacts` return in predict.py:28 ✓

One fix needed: `test_missing_city_falls_back_to_seoul` calls `_wire` (which patches `_artifact_dir_exists` to always return `False`) and then immediately re-patches it to `lambda city: city == "seoul"`. The second `monkeypatch.setattr` call overwrites the first. The `loaded` list from `_wire` is still valid because `fake_load` was bound before the second patch. Logic is correct. ✓
