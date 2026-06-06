from benchmarking_data_factory.reference.council_master import council_master_reference_payload


def test_council_master_has_full_source_coverage():
    payload = council_master_reference_payload()

    assert payload["set_id"] == "victorian_council_master"
    assert payload["summary"]["councils"] == 79
    assert len(payload["rows"]) == 79
    assert len({row["council_key"] for row in payload["rows"]}) == 79
    assert payload["summary"]["coverage"]["abs_asgs"] == 79
    assert payload["summary"]["coverage"]["lgprf"] == 79
    assert payload["summary"]["coverage"]["governance"] == 79
    assert payload["summary"]["coverage"]["vec"] == 79
    assert payload["summary"]["coverage"]["vgccc"] == 79


def test_council_master_carries_reference_dimensions():
    payload = council_master_reference_payload()
    rows = {row["short_name"]: row for row in payload["rows"]}

    ballarat = rows["Ballarat"]
    assert ballarat["council_category"] == "Regional"
    assert ballarat["vif_regional_partnership"] == "Central Highlands"
    assert ballarat["abs_area_albers_sqkm"] > 0
    assert ballarat["vec_councillor_count"] == 9
    assert ballarat["governance_item_count"] == 27

    merri_bek = rows["Merri-bek"]
    assert merri_bek["abs_lga_code"] == "25250"
    assert merri_bek["abs_lga_code_2025"] == "24700"
    assert merri_bek["abs_join_method"] == "name"
    assert merri_bek["vif_metropolitan_region"] == "Northern"

    mitchell = rows["Mitchell"]
    assert mitchell["vif_metropolitan_region"] == "Northern (part)"
    assert mitchell["vif_regional_partnership"] == "Goulburn (part)"
