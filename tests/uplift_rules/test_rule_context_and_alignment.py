from __future__ import annotations

import json

from benchmarking_data_factory.uplift_rules.prompt import get_prompt
from benchmarking_data_factory.uplift_rules.schema import CURRENT_PROMPT_VERSION
from benchmarking_data_factory.uplift_rules.suggest import _parse_llm_response
from benchmarking_data_factory.uplift_rules.table_alignment import (
    build_rule_table_alignment_issues,
)


def test_current_uplift_prompt_requires_rule_table_binding_context():
    assert CURRENT_PROMPT_VERSION == "pass1_system_v2"
    prompt = get_prompt(CURRENT_PROMPT_VERSION).system

    assert "nearby_table_headings" in prompt
    assert "RULE/TABLE BINDING CONTEXT" in prompt
    assert "Do not invent a different uplift" in prompt


def test_uplift_parser_preserves_rule_binding_context():
    raw = json.dumps({
        "council": "Mansfield Shire Council",
        "covered_councils": ["Mansfield Shire Council"],
        "multi_employer": False,
        "timing_pattern": "annual_specific_pp",
        "rules": [
            {
                "period_label": "Year 3",
                "quantum": "2.00% or $28.00 (whichever is greater) per week",
                "quantum_type": "pct_OR_floor",
                "timing_clause": "first full pay period on or after 7 November 2023",
                "effective_date": "2023-11-07",
                "quantum_floor": "$28.00",
                "source_page": 64,
                "applies_to": "all salary tables",
                "nearby_table_headings": [
                    "Indoor - Other than Physical & Community Services",
                    "Outdoor - Physical & Community Services",
                ],
                "extraction_warnings": [
                    "Adjacent Indoor/Outdoor table sequence may confuse date binding."
                ],
                "confidence": 0.95,
            }
        ],
        "notes": "Salary increases are general; table families follow the clause.",
    })

    document, status = _parse_llm_response(raw, "ae516687")

    assert status == "ok"
    rule = document.rules[0]
    assert rule.applies_to == "all salary tables"
    assert "Outdoor - Physical & Community Services" in rule.nearby_table_headings
    assert rule.extraction_warnings == (
        "Adjacent Indoor/Outdoor table sequence may confuse date binding.",
    )


def test_rule_table_alignment_flags_extraction_binding_conflict():
    canonical = {
        "agreement_id": "aetest-table-binding",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2022-11-07",
                        "table_title": "Indoor benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1114.90},
                            {"band": "1", "level": "B", "weekly_rate": 1124.20},
                            {"band": "2", "level": "A", "weekly_rate": 1155.90},
                        ],
                    },
                    {
                        "effective_from": "2023-11-07",
                        "table_title": "Indoor benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1147.53},
                            {"band": "1", "level": "B", "weekly_rate": 1156.83},
                            {"band": "2", "level": "A", "weekly_rate": 1188.53},
                        ],
                    },
                ],
            },
            "uplift_rules": {
                "status": "done",
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "period_label": "Year 3",
                                    "effective_date": "2023-11-07",
                                    "quantum_type": "pct_OR_floor",
                                    "quantum": "2.00% or $28.00 (whichever is greater) per week",
                                    "quantum_floor": "$28.00",
                                }
                            ]
                        }
                    }
                },
            },
        },
    }

    issues = build_rule_table_alignment_issues(canonical)

    assert len(issues) == 1
    assert issues[0]["code"] == "uplift_rule_table_binding_conflict"
    assert issues[0]["mechanised_weekly_increase"] == 28.0
    assert issues[0]["implied_weekly_increase"] == 32.63
