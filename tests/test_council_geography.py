import json

from benchmarking_data_factory.spatial.council_geography import (
    analysis_geography_fields,
    build_council_geography_payload,
    council_type_from_name,
    geography_for_lga,
    normalise_spatial_key,
)


def test_normalise_spatial_key_matches_case_and_punctuation():
    assert normalise_spatial_key("Bass Coast") == "BASS COAST"
    assert normalise_spatial_key("French-Elizabeth-Sandstone Islands") == "FRENCH ELIZABETH SANDSTONE ISLANDS"


def test_council_type_from_name_prefers_rural_city():
    assert council_type_from_name("Ararat Rural City Council") == "rural_city"
    assert council_type_from_name("Ballarat City Council") == "city"
    assert council_type_from_name("Alpine Shire Council") == "shire"
    assert council_type_from_name("Queenscliffe Borough") == "borough"


def test_geography_lookup_and_analysis_fields(tmp_path):
    path = tmp_path / "geography.json"
    path.write_text(json.dumps({
        "summary": {"councils": 1},
        "sources": {},
        "councils": [{
            "short_name": "Ballarat",
            "long_name": "Ballarat City Council",
            "spatial_key": "BALLARAT",
            "lga_code": "305",
            "abs_lga_code": "20110",
            "council_type": "city",
            "office": {"seat_township": "Ballarat", "lat": -37.56, "lon": 143.85},
            "cohorts": {"council_type": "city", "office_geocoded": "yes", "polygon_attributed": "yes"},
        }],
    }), encoding="utf-8")

    assert geography_for_lga("ballarat", {"councils": json.loads(path.read_text())["councils"]})["lga_code"] == "305"
    fields = analysis_geography_fields("Ballarat", json.loads(path.read_text()))

    assert fields["abs_lga_code"] == "20110"
    assert fields["council_type"] == "city"
    assert fields["office_township"] == "Ballarat"
    assert fields["spatial_cohorts"]["office_geocoded"] == "yes"


def test_geography_lookup_handles_greater_council_aliases(tmp_path):
    payload = {
        "councils": [{
            "short_name": "Greater Geelong",
            "long_name": "Greater Geelong City Council",
            "spatial_name": "Greater Geelong",
            "spatial_key": "GREATER GEELONG",
            "official_name": "GREATER GEELONG CITY",
            "lga_code": "327",
        }],
    }

    assert geography_for_lga("Greater Geelong", payload)["lga_code"] == "327"
    assert geography_for_lga("Greater Geelong City Council", payload)["lga_code"] == "327"
    assert geography_for_lga("City of Greater Geelong", payload)["lga_code"] == "327"
    assert geography_for_lga("GREATER GEELONG CITY", payload)["lga_code"] == "327"


def test_build_council_geography_payload_shapes_map_points(tmp_path):
    path = tmp_path / "geography.json"
    path.write_text(json.dumps({
        "summary": {"councils": 1, "boundary_bounds": [140, -39, 150, -34]},
        "sources": {"sample": {"name": "fixture"}},
        "councils": [{
            "short_name": "Ballarat",
            "long_name": "Ballarat City Council",
            "spatial_key": "BALLARAT",
            "lga_code": "305",
            "abs_lga_code": "20110",
            "council_type": "city",
            "council_category": "Regional",
            "office": {"seat_township": "Ballarat", "address": "25 Armstrong St S", "lat": -37.56, "lon": 143.85},
            "cohorts": {
                "council_type": "city",
                "council_category": "Regional",
                "register_status": "active",
                "office_geocoded": "yes",
                "polygon_attributed": "yes",
            },
        }],
    }), encoding="utf-8")

    payload = build_council_geography_payload(path)

    assert payload["summary"]["office_point_features"] == 1
    assert payload["summary"]["rows"] == 1
    assert payload["cohorts"]["council_type"] == [{"cohort": "city", "count": 1}]
    assert payload["cohorts"]["council_category"] == [{"cohort": "Regional", "count": 1}]
    row = payload["rows"][0]
    assert row["council_key"] == "BALLARAT"
    assert row["council_category"] == "Regional"
    assert row["office_township"] == "Ballarat"
    assert row["office_geocoded"] == "yes"
    assert row["map_join_key"] == "BALLARAT"
    feature = payload["map"]["office_points"]["features"][0]
    assert feature["geometry"]["coordinates"] == [143.85, -37.56]
    assert feature["properties"]["short_name"] == "Ballarat"
    assert feature["properties"]["council_category"] == "Regional"
