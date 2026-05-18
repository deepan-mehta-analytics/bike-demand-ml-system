# ── Imports ───────────────────────────────────────────────────────────────
import joblib                                                 # save tiny RF artifacts to tmp_path
import numpy as np                                            # synthetic training data for tiny RF
import pytest                                                 # test framework, fixtures, monkeypatch
from sklearn.ensemble import RandomForestRegressor            # real model so predict() validates feature alignment

import services.predictor                                     # module under test; _cache and helpers patched here


# ── Shared Test Record ────────────────────────────────────────────────────
# Minimal valid prediction input. SEASONS=Summer so get_dummies produces SEASONS_Summer only;
# reindex in predict.py fills any missing dummy columns with 0.
_RECORD = {                                                   # one valid record for predict_service()
    "DATE": "01/06/2018",                                    # DD/MM/YYYY — parsed by create_features
    "HOUR": 8,                                               # integer hour (0–23)
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

# Columns produced by predict.py when processing _RECORD:
# create_features → drop DATE → get_dummies → reindex(feature_columns)
# With SEASONS=Summer / HOLIDAY=No Holiday / FUNCTIONING_DAY=Yes, get_dummies
# produces exactly these 16 columns. The tiny RF is trained on this exact schema.
_FEATURE_COLUMNS = [                                         # must match get_dummies output for _RECORD
    "HOUR", "TEMPERATURE", "HUMIDITY", "WIND_SPEED",         # numeric weather signals
    "VISIBILITY", "DEW_POINT_TEMPERATURE",                   # atmospheric conditions
    "SOLAR_RADIATION", "RAINFALL", "SNOWFALL",               # precipitation and solar
    "year", "month", "day", "dayofweek",                     # temporal features added by create_features
    "SEASONS_Summer",                                        # only Summer present in _RECORD
    "HOLIDAY_No Holiday",                                    # only No Holiday present in _RECORD
    "FUNCTIONING_DAY_Yes",                                   # only Yes present in _RECORD
]


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tiny_rf(tmp_path):
    """Build a minimal real RF + schema pkl in tmp_path for use as a fake artifact dir."""
    rng = np.random.default_rng(0)                           # seeded RNG for reproducibility
    X = rng.random((20, len(_FEATURE_COLUMNS)))              # 20 synthetic rows × 16 features
    y = rng.random(20) * 500                                 # synthetic demand targets
    model = RandomForestRegressor(n_estimators=3, random_state=0)  # tiny tree count — speed not accuracy
    model.fit(X, y)                                          # fit on synthetic data matching _FEATURE_COLUMNS
    joblib.dump(model, tmp_path / "random_forest_model.pkl") # save model artifact to tmp dir
    joblib.dump(_FEATURE_COLUMNS, tmp_path / "feature_columns.pkl")  # save schema artifact to tmp dir
    return tmp_path                                          # return path so tests can reference pkl files


@pytest.fixture(autouse=True)
def clear_cache():
    """Wipe the module-level artifact cache before and after every test to prevent cross-test bleed."""
    services.predictor._cache.clear()                        # clear before: start with empty cache
    yield                                                    # run the test
    services.predictor._cache.clear()                        # clear after: paranoid teardown


# ── Helper ────────────────────────────────────────────────────────────────

def _wire(monkeypatch, tiny_rf, exists_for):
    """Patch _artifact_dir_exists and load_artifacts; return the list of cities load_artifacts was called with.

    Args:
        exists_for: city key that should appear to have trained artifacts (str), or None for no artifacts.
    """
    loaded = []                                              # capture every city key passed to load_artifacts

    def fake_exists(city):                                   # replace filesystem artifact check
        return city == exists_for                            # True only for the target city; None → always False

    def fake_load(city):                                     # replace joblib disk load
        loaded.append(city)                                  # record which city key was requested
        return (                                             # return tiny RF from tmp_path
            joblib.load(tiny_rf / "random_forest_model.pkl"),
            joblib.load(tiny_rf / "feature_columns.pkl"),
        )

    monkeypatch.setattr(services.predictor, "_artifact_dir_exists", fake_exists)  # patch filesystem guard
    monkeypatch.setattr(services.predictor, "load_artifacts", fake_load)          # patch disk load
    return loaded                                            # caller checks this list to verify routing


# ── Routing Tests ─────────────────────────────────────────────────────────

def test_paris_routes_to_paris_artifacts(monkeypatch, tiny_rf):
    """city='paris' must load the paris artifact — not fall back to seoul."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="paris") # paris artifacts exist; nothing else does
    services.predictor.predict_service(data=[_RECORD], city="paris")  # call with paris
    assert loaded == ["paris"], f"Expected load_artifacts('paris'), got {loaded}"


def test_chicago_routes_to_chicago_artifacts(monkeypatch, tiny_rf):
    """city='chicago' must load the chicago artifact — not fall back to seoul."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="chicago")  # chicago artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="chicago")
    assert loaded == ["chicago"], f"Expected load_artifacts('chicago'), got {loaded}"


def test_new_york_slug_resolves_to_nyc(monkeypatch, tiny_rf):
    """city='new york' must resolve through _CITY_SLUG_MAP to 'nyc' and load nyc artifacts."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="nyc")   # nyc artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="new york")  # R Shiny sends "new york"
    assert loaded == ["nyc"], f"Expected load_artifacts('nyc'), got {loaded}"


def test_washington_dc_slug_resolves_to_dc(monkeypatch, tiny_rf):
    """city='washington dc' must resolve through _CITY_SLUG_MAP to 'dc' and load dc artifacts."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for="dc")    # dc artifacts exist
    services.predictor.predict_service(data=[_RECORD], city="washington dc")  # R Shiny sends "washington dc"
    assert loaded == ["dc"], f"Expected load_artifacts('dc'), got {loaded}"


def test_missing_city_falls_back_to_seoul(monkeypatch, tiny_rf):
    """An unrecognised city with no trained artifacts must fall back to 'seoul', not raise."""
    loaded = _wire(monkeypatch, tiny_rf, exists_for=None)    # _wire patches exists → always False

    # Re-patch exists so seoul "exists" — allows the fallback load to complete without error.
    # The load_artifacts patch from _wire stays in place; loaded still captures the call.
    monkeypatch.setattr(
        services.predictor, "_artifact_dir_exists",
        lambda city: city == "seoul",                        # only seoul has artifacts; all others don't
    )
    services.predictor.predict_service(data=[_RECORD], city="atlantis")  # unknown city → should fall back
    assert "seoul" in loaded, f"Expected fallback to load_artifacts('seoul'), got {loaded}"
