from benchmarking_data_factory.conditions.section_picker import score_condition_pages


def test_score_condition_pages_finds_quantified_condition_pages():
    pages = [
        "General introduction only.",
        "Redundancy Payments: severance pay is two weeks for each completed year to a maximum of 48 weeks.",
        "Payment of overtime and time in lieu: time and a half for the first two hours and double time thereafter.",
        "Parental leave provides twenty (20) weeks paid primary carer leave.",
    ]

    candidates = score_condition_pages(pages)
    by_category = {candidate.category: candidate for candidate in candidates}

    assert by_category["redundancy_redeployment"].page_number == 2
    assert by_category["redundancy_redeployment"].has_quantifier is True
    assert by_category["overtime_penalties_rosters"].page_number == 3
    assert by_category["paid_parental_family_leave"].page_number == 4


def test_score_condition_pages_excludes_specialised_cohort_pages_by_default():
    pages = [
        "Maternal and Child Health Nurses overtime: time and a half for two hours and double time thereafter.",
        "Payment of overtime and time in lieu for employees: time and a half for the first two hours.",
    ]

    candidates = score_condition_pages(pages)

    assert [candidate.page_number for candidate in candidates] == [2]


def test_score_condition_pages_can_include_specialised_pages_for_audit():
    pages = [
        "Pool Services employees public holiday work is paid at double time and a half.",
    ]

    candidates = score_condition_pages(pages, exclude_specialised_cohorts=False)

    assert candidates[0].page_number == 1
