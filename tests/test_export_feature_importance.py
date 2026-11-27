# ── Tests for models/export_feature_importance.py (2026-11-27) ───────────────
import pytest                                                           # approx for float sums
from models.export_feature_importance import base_feature, city_importances  # helpers under test


def test_one_hot_columns_fold_into_their_family():
    """Season / holiday / functioning-day dummies map back to one readable feature."""
    assert base_feature("SEASONS_Winter") == "SEASONS"                  # season dummy
    assert base_feature("HOLIDAY_No Holiday") == "HOLIDAY"              # holiday dummy
    assert base_feature("FUNCTIONING_DAY_Yes") == "FUNCTIONING_DAY"     # functioning-day dummy
    assert base_feature("HOUR") == "HOUR"                               # plain feature unchanged


def test_city_importances_sums_dummies_and_sorts_high_to_low():
    """Dummy weights add up under their family and the list is ordered by weight."""
    cols = ["HOUR", "SEASONS_Spring", "SEASONS_Winter", "RAINFALL"]      # tiny schema
    result = city_importances(cols, [0.5, 0.1, 0.16, 0.2])              # season = 0.1 + 0.16 = 0.26
    assert [name for name, _ in result] == ["HOUR", "SEASONS", "RAINFALL"]   # sorted by summed weight
    assert dict(result)["SEASONS"] == pytest.approx(0.26)               # dummies summed (float tolerance)
