# Pytest Suite Design — bike-demand-ml-system

**Date:** 2026-05-18  
**Status:** Approved

---

## Problem

The existing test suite (15 tests across `test_features.py`, `test_api.py`, `test_pipeline.py`) verifies routing correctness and API schema but does not:

1. Guard against silent feature schema drift that would break all 6 city models
2. Detect data-quality regressions that cause RMSE to degrade between sessions
3. Guarantee that Paris and Chicago route to their own trained artifacts (not the Seoul fallback)

---

## Design

Three tiers, each independently motivated and independently runnable.

---

### Tier 1 — Feature Schema Guard

**File:** `tests/test_features.py` (one new test added to existing file)  
**CI job:** Job 2 (existing `pytest` job — fast, runs on every push)

**Test:** `test_feature_schema_is_frozen`

Calls `create_features` + `get_feature_target` on the existing `sample_df` fixture.  
Asserts `set(X.columns) == EXPECTED_COLUMNS` against a hardcoded frozen set.

Failure message:
```
Feature schema changed. Before merging:
  - retrain all 6 city models (seoul, london, nyc, dc, paris, chicago)
  - rebuild and push the Vertex AI training container (Dockerfile.training)
  - verify RMSE gates still pass (pytest -m slow)
```

**Why this matters:** `get_feature_target` produces column names from `pd.get_dummies` on live data. Any new categorical value, renamed column, or added feature silently produces a different schema — models trained on the old schema become misaligned with inference. This test makes that failure loud and immediate.

---

### Tier 2 — RMSE Gates

**File:** `tests/test_model_accuracy.py` (new file)  
**CI job:** Job 7 (`accuracy`) — new job, push to main only, parallel to Job 2

Each test is marked `@pytest.mark.slow`.

**Per-test logic:**
1. Load the city's committed processed CSV from `data/processed/<city>_bike_sharing.csv`  
   (Seoul uses `data/processed/clean_bike_data.csv`)
2. Call `create_features` + `get_feature_target`
3. Chronological 80/20 split — `iloc[:split_idx]` / `iloc[split_idx:]` — matching `train.py` exactly
4. Train `RandomForestRegressor(n_estimators=100, random_state=42)` on train set
5. Predict on holdout; compute `mean_squared_error(y_test, y_pred, squared=False)`
6. Assert RMSE < threshold

**Thresholds:**

| City    | Threshold | Trained RMSE | Headroom |
|---------|-----------|--------------|----------|
| Seoul   | 250       | 173.21       | 76       |
| London  | 350       | 228.58       | 121      |
| NYC     | 500       | 345.69       | 154      |
| DC      | 150       | 97.47        | 53       |
| Paris   | 50        | 23.30        | 27       |
| Chicago | 350       | 202.99       | 147      |

Paris RMSE is low because the source data uses a normalised MEAN station counter scale (~50–500/hr), not raw city-wide volume. The threshold of 50 is correct for that scale.

**What this tests:** Data quality + feature pipeline correctness. These tests re-train from the committed CSVs — they do not load production `.pkl` artifacts. A regression here means either a CSV was corrupted, feature engineering changed, or a data fetch introduced bad rows.

**CI Job 7 spec:**
```yaml
accuracy:
  name: RMSE accuracy gates
  runs-on: ubuntu-latest
  needs: lint                  # parallel to test job; no need to wait for docker
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install -r requirements.txt
    - run: pytest -m slow tests/test_model_accuracy.py -v
```

Expected wall time: ~5 min (6 RF training runs on committed CSVs).

---

### Tier 3 — No-Fallback Routing Guarantee

**File:** `tests/test_routing.py` (new file)  
**CI job:** Job 2 (existing `pytest` job — fast)

**Purpose:** Assert that city slugs resolve to their own artifacts — not the Seoul fallback. This is a direct regression guard for the `_resolve_city_key` + `_get_artifacts` path in `services/predictor.py`.

**Fixture strategy:**

```
@pytest.fixture(autouse=True)
def clear_predictor_cache():
    services.predictor._cache.clear()   # wipe module-level cache before each test
    yield
    services.predictor._cache.clear()   # wipe after too (paranoid teardown)
```

Each test:
1. Creates a tiny real sklearn RF + matching `feature_columns` list in `tmp_path`
2. Monkeypatches `services.predictor._artifact_dir_exists` to return `True` for the target city
3. Monkeypatches `services.predictor.load_artifacts` to load from `tmp_path` artifacts
4. Calls `predict_service(data=[...], city=<slug>)`
5. Asserts `load_artifacts` was called with the expected resolved key — not "seoul"

**Why real sklearn RF, not MagicMock:** `predict_service` calls `predict()` which calls `model.predict(input_df)`. A MagicMock would accept any input silently; a real RF will raise if feature alignment is broken. The fixture catches two classes of bugs, not one.

**Tests:**

| Test | Input city | Expected artifact key |
|------|-----------|----------------------|
| `test_paris_routes_to_paris_artifacts` | `"paris"` | `"paris"` |
| `test_chicago_routes_to_chicago_artifacts` | `"chicago"` | `"chicago"` |
| `test_new_york_slug_resolves_to_nyc` | `"new york"` | `"nyc"` |
| `test_washington_dc_slug_resolves_to_dc` | `"washington dc"` | `"dc"` |
| `test_missing_city_falls_back_to_seoul` | `"atlantis"` | `"seoul"` (fallback) |

---

## File Changes

| File | Change |
|------|--------|
| `tests/test_features.py` | Add `EXPECTED_COLUMNS` constant + `test_feature_schema_is_frozen` |
| `tests/test_model_accuracy.py` | New file — 6 `@pytest.mark.slow` RMSE gate tests |
| `tests/test_routing.py` | New file — 5 routing/no-fallback tests |
| `pytest.ini` | Add `markers = slow: marks tests as slow-running RMSE accuracy checks` |
| `.github/workflows/ci.yml` | Add Job 7: `accuracy` (push to main only, parallel to `test`) |

**Total new tests:** 12 (1 + 6 + 5). Existing 15 tests unchanged.

---

## Out of Scope

- `pipeline/retrain_job.py` and `pipeline/vertex_trigger.py` tests — deferred; require GCP mocking or VCR cassettes
- `testthat` suite for the R Shiny repo — separate spec, separate session
- Mutation testing or property-based testing — YAGNI at current project scale
