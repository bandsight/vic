def test_extracted_pay_candidates_keep_weekly_and_drop_non_standard_rows():
    import main

    tables = [
        {
            "table_title": "Weekly rates",
            "rate_kind": "weekly",
            "effective_from": "2027-07-01",
            "rows": [
                {"band": "1", "level": "A", "rate": 1000.0},
                {"title": "Maternal and Child Health Nurse Year 1", "rate": 2000.0},
            ],
        },
        {
            "table_title": "Annual rates",
            "rate_kind": "annual",
            "effective_from": "2027-07-01",
            "rows": [
                {"band": "1", "level": "A", "rate": 52000.0},
            ],
        },
        {
            "table_title": "Hourly rates",
            "rate_kind": "hourly",
            "effective_from": "2027-07-01",
            "rows": [
                {"band": "1", "level": "A", "rate": 25.0},
            ],
        },
    ]

    result = main.normalise_extracted_pay_table_candidates(tables)

    assert len(result) == 1
    assert result[0]["table_title"] == "Weekly rates"
    assert result[0]["rate_kind"] == "weekly"
    assert result[0]["rows"] == [
        {
            "band": "1",
            "level": "A",
            "weekly_rate": 1000.0,
            "annual_rate": None,
            "hourly_rate": None,
            "fortnightly_rate": None,
            "notes": None,
            "title": None,
        }
    ]


def test_extracted_pay_candidates_fall_back_to_annual_before_fortnightly():
    import main

    tables = [
        {
            "table_title": "Fortnightly rates",
            "rate_kind": "fortnightly",
            "effective_from": "2027-07-01",
            "rows": [
                {"band": "1", "level": "A", "rate": 2000.0},
            ],
        },
        {
            "table_title": "Annual rates",
            "rate_kind": "annual",
            "effective_from": "2027-07-01",
            "rows": [
                {"band": "1", "level": "A", "rate": 52000.0},
            ],
        },
    ]

    result = main.normalise_extracted_pay_table_candidates(tables)

    assert len(result) == 1
    assert result[0]["table_title"] == "Annual rates"
    assert result[0]["rows"][0]["annual_rate"] == 52000.0


def test_extracted_pay_candidates_use_fortnightly_when_no_weekly_or_annual():
    import main

    tables = [
        {
            "table_title": "Fortnightly rates",
            "rate_kind": "fortnightly",
            "effective_from": "from sign-off",
            "rows": [
                {"band": "1", "level": "A", "rate": 2000.0},
            ],
        },
    ]

    result = main.normalise_extracted_pay_table_candidates(tables)

    assert len(result) == 1
    assert result[0]["table_title"] == "Fortnightly rates"
    assert result[0]["effective_from"] is None
    assert result[0]["effective_from_note"] == "from sign-off"
    assert result[0]["rows"][0]["fortnightly_rate"] == 2000.0
