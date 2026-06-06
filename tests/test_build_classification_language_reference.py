from scripts.build_classification_language_reference import build_payload, markdown_for_payload


def test_build_payload_groups_classification_descriptor_language():
    reference_inputs = [
        {
            "schema_version": "wiki.reference_input.v1",
            "source_id": "pds-test",
            "source_name": "PDs Test",
            "summary": {"context_scope_counts": {"band_responsibility_context": 2}},
            "pages": [
                {
                    "page": 1,
                    "tags": {
                        "clause_function": [],
                        "context_scope": [{"tag": "band_responsibility_context"}],
                    },
                }
            ],
            "sections": [
                {
                    "section_id": "reference:pds-test::p0001::h01",
                    "title": "Guide 2 - Bands 3 to 8 Features",
                    "source_ref": {"source_id": "pds-test", "page": 1},
                    "tags": {
                        "clause_function": [],
                        "context_scope": [
                            {"tag": "classification_context"},
                            {"tag": "band_responsibility_context"},
                        ],
                    },
                    "evidence_excerpt": (
                        "Bands 3 to 8 use accountability and extent of authority, "
                        "judgement and decision making, specialist knowledge and skills, "
                        "management skills, interpersonal skills, and qualifications and experience. "
                        "Employees other than Physical/Community Services are discussed."
                    ),
                    "review_state": "proposed",
                }
            ],
            "language_candidates": [
                {
                    "canonical_term": "band_responsibilities",
                    "observed_term": "accountability and extent of authority",
                    "source_ref": {"source_id": "pds-test", "page": 1},
                }
            ],
        }
    ]

    payload = build_payload(reference_inputs, generated_at="2026-05-13T00:00:00+00:00")

    descriptor_ids = {item["id"] for item in payload["descriptor_signals"]}
    role_ids = {item["id"] for item in payload["role_family_signals"]}
    band_ids = {item["id"] for item in payload["band_mentions"]}

    assert payload["schema_version"] == "wiki.classification_language_reference.v1"
    assert payload["summary"]["classification_section_hits"] == 1
    assert "accountability_authority" in descriptor_ids
    assert "judgement_decision_making" in descriptor_ids
    assert "bands_3_to_8" in band_ids
    assert "employees_other_than_physical_community" in role_ids
    assert payload["language_terms"][0]["canonical_term"] == "band_responsibilities"


def test_markdown_for_payload_summarises_reference_artifact():
    payload = {
        "generated_at": "2026-05-13T00:00:00+00:00",
        "summary": {
            "reference_inputs_scanned": 1,
            "classification_section_hits": 2,
            "descriptor_signal_sections": 3,
            "classification_language_candidates": 4,
        },
        "descriptor_signals": [{"id": "management_skills", "count": 2}],
        "band_mentions": [{"id": "band_5", "count": 1}],
        "role_family_signals": [{"id": "physical_community_services", "count": 1}],
        "evidence": [
            {
                "source_name": "PDs Test",
                "page": 5,
                "title": "Management Skills",
                "descriptor_signals": ["management_skills"],
            }
        ],
        "review_prompts": [{"question": "Should descriptors become ontology fields?"}],
    }

    markdown = markdown_for_payload(payload)

    assert "# Classification Language Reference" in markdown
    assert "`management_skills`: 2" in markdown
    assert "PDs Test p. 5" in markdown
