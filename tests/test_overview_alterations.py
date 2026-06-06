"""Tests for band_level_alterations in Overview parsing."""
from __future__ import annotations

import json

import pytest

from main import parse_overview_response, ALTERATION_KEYWORDS


def test_alteration_keywords_match_annex():
    assert ALTERATION_KEYWORDS.search("Annexure A — Banyule Salary Structure")
    assert ALTERATION_KEYWORDS.search("ANNEX A")
    assert ALTERATION_KEYWORDS.search("annex b")


def test_alteration_keywords_match_undertaking_alteration_variation():
    assert ALTERATION_KEYWORDS.search("Undertaking re Level 7 progression")
    assert ALTERATION_KEYWORDS.search("Alteration under s.207")
    assert ALTERATION_KEYWORDS.search("Variation — Outdoor Staff")
    assert ALTERATION_KEYWORDS.search("Side Letter between the parties")


def test_alteration_keywords_match_band_level_vocabulary():
    assert ALTERATION_KEYWORDS.search("Band 8 progression")
    assert ALTERATION_KEYWORDS.search("Level 7 salary point")
    assert ALTERATION_KEYWORDS.search("Classification structure review")


def test_parse_overview_returns_empty_list_when_llm_omits_field():
    raw = json.dumps({
        "page_count": 120,
        "likely_pay_table_pages": [45, 46],
        "likely_uplift_pages": [12],
        "estimated_earliest_commencing": "2025-07-01",
        "estimated_latest_commencing": "2027-07-01",
        "document_structure_notes": "Standard layout.",
        "red_flags": [],
    })
    out = parse_overview_response(raw, 120, [45, 46], [12], [100, 101])
    assert out["band_level_alterations"] == []


def test_parse_overview_preserves_structured_alterations():
    raw = json.dumps({
        "page_count": 120,
        "likely_pay_table_pages": [45],
        "likely_uplift_pages": [12],
        "estimated_earliest_commencing": None,
        "estimated_latest_commencing": None,
        "document_structure_notes": "",
        "red_flags": [],
        "band_level_alterations": [
            {
                "page": 100,
                "heading": "Annexure A",
                "affects": "Band 8 salary points",
                "summary": "Adds a new Step 4 to Band 8 effective 1 July 2026.",
            },
            {
                "page": 108,
                "heading": "Undertaking re Level 7",
                "affects": "Level 7 progression",
                "summary": "Progression capped at 3 years in role.",
            },
        ],
    })
    out = parse_overview_response(raw, 120, [45], [12], [100, 108])
    assert len(out["band_level_alterations"]) == 2
    assert out["band_level_alterations"][0]["heading"] == "Annexure A"
    assert out["band_level_alterations"][1]["affects"] == "Level 7 progression"


def test_parse_overview_fallback_includes_empty_alterations():
    # Unparseable LLM output: fallback must still expose the field
    out = parse_overview_response("not json at all", 50, [1], [2], [3])
    assert "band_level_alterations" in out
    assert out["band_level_alterations"] == []


def test_parse_overview_does_not_save_llm_error_as_notes():
    out = parse_overview_response("ERROR: ANTHROPIC_API_KEY not set", 162, [44], [28], [151])
    assert out["document_structure_notes"] == ""
    assert out["generation_warning"] == "ERROR: ANTHROPIC_API_KEY not set"
    assert out["likely_pay_table_pages"] == [44]
    assert out["likely_uplift_pages"] == [28]
