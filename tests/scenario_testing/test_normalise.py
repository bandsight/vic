from benchmarking_data_factory.scenario_testing.normalise import (
    cell_key,
    is_standard_band_level_row,
    row_to_weekly,
    standard_band_level_metadata,
    standard_cell_key,
)


def test_row_to_weekly_with_weekly_rate_present():
    assert row_to_weekly({"weekly_rate": 1234.56, "annual_rate": 99999}) == 1234.56


def test_row_to_weekly_with_only_annual_rate():
    assert row_to_weekly({"annual_rate": 52000}) == 1000.0


def test_row_to_weekly_with_only_fortnightly_rate():
    assert row_to_weekly({"fortnightly_rate": 2400}) == 1200.0


def test_row_to_weekly_with_all_none():
    assert row_to_weekly({"weekly_rate": None, "annual_rate": None, "fortnightly_rate": None}) is None


def test_row_to_weekly_with_string_weekly_rate():
    assert row_to_weekly({"weekly_rate": "1234.56"}) == 1234.56


def test_row_to_weekly_prefers_weekly_over_annual():
    assert row_to_weekly({"weekly_rate": 1100, "annual_rate": 52000}) == 1100


def test_row_to_weekly_ignores_zero_and_negative_values():
    assert row_to_weekly({"weekly_rate": 0, "annual_rate": -52000, "fortnightly_rate": 2400}) == 1200.0


def test_cell_key_returns_string_tuple():
    assert cell_key({"band": 1, "level": 2}) == ("1", "2")


def test_cell_key_returns_none_when_band_missing():
    assert cell_key({"level": 2}) is None


def test_cell_key_returns_none_when_level_missing():
    assert cell_key({"band": 1}) is None


def test_standard_cell_key_normalises_band_and_level():
    assert standard_cell_key({"band": "Band 5", "level": "level a"}) == ("5", "A")


def test_standard_band_level_metadata_materialises_dimension_fields():
    assert standard_band_level_metadata({"band": "Band 5", "level": "level a"}) == {
        "standard_band": "5",
        "standard_level": "A",
        "classification_key": "band_05_level_A",
        "classification_label": "Band 5 Level A",
        "classification_sort": 501,
    }


def test_standard_band_level_rejects_role_only_specialist_rows():
    row = {
        "band": None,
        "level": None,
        "title": "Maternal and Child Health Nurse Year 1",
        "weekly_rate": 2035.79,
    }
    assert not is_standard_band_level_row(row)


def test_standard_band_level_rejects_specialist_title_even_with_band():
    assert not is_standard_band_level_row({"band": 5, "level": "A", "title": "Senior Officer"})


def test_standard_band_level_accepts_numeric_band_and_level():
    assert is_standard_band_level_row({"band": 5, "level": "A", "weekly_rate": 1432.85})
