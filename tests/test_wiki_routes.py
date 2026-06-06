import json

from fastapi.testclient import TestClient

from benchmarking_data_factory.workbench.app_factory import create_workbench_app
from benchmarking_data_factory.workbench.application_core import WikiLayerService, WorkbenchPathService
from benchmarking_data_factory.workbench.wiki_routes import build_wiki_router_for_service


def test_wiki_routes_expose_generated_records(tmp_path):
    wiki = tmp_path / "wiki"
    for folder in [
        "document-maps",
        "reference-inputs",
        "language-maps",
        "questions",
        "learning-backlog",
        "runs",
        "artifacts",
    ]:
        (wiki / folder).mkdir(parents=True)
    run_id = "wiki-run-test"
    (wiki / "wiki-manifest.json").write_text(
        json.dumps({"schema_version": "wiki.manifest.v1", "latest_run_id": run_id, "scope_focus": "entitlements_conditions_benefits"}),
        encoding="utf-8",
    )
    (wiki / "runs" / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "summary": {"agreements_mapped": 1}}),
        encoding="utf-8",
    )
    (wiki / "document-maps" / "ae-test.json").write_text(
        json.dumps({
            "agreement_id": "ae-test",
            "agreement_name": "Test Agreement",
            "review_state": "proposed",
            "summary": {"pages_scanned": 1},
            "pages": [
                {
                    "page": 1,
                    "tags": {"clause_function": [{"tag": "hours", "score": 2}], "context_scope": []},
                    "clause_context_relevance": "core_clause",
                }
            ],
            "sections": [
                {
                    "title": "Ordinary Hours",
                    "source_ref": {"agreement_id": "ae-test", "page": 1},
                    "tags": {"clause_function": [{"tag": "hours", "score": 2}], "context_scope": []},
                    "evidence_excerpt": "Ordinary hours of work will be rostered.",
                    "review_state": "proposed",
                }
            ],
        }),
        encoding="utf-8",
    )
    (wiki / "reference-inputs" / "know-your-award.json").write_text(
        json.dumps(
            {
                "source_id": "know-your-award",
                "source_name": "Know Your Award",
                "source_kind": "reference_material",
                "summary": {"pages_scanned": 41},
            }
        ),
        encoding="utf-8",
    )
    (wiki / "questions" / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "questions": [{"status": "open"}]}),
        encoding="utf-8",
    )
    (wiki / "learning-backlog" / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "items": [{"status": "observed"}]}),
        encoding="utf-8",
    )
    (wiki / "language-maps" / "clause-context-terms.json").write_text(
        json.dumps({
            "terms": [
                {
                    "canonical_term": "ordinary_hours",
                    "observed_terms": [
                        {
                            "observed_term": "ordinary hours",
                            "count": 1,
                            "source_refs": [{"agreement_id": "ae-test", "page": 1}],
                        }
                    ],
                }
            ]
        }),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "downstream-analysis-exemplars").mkdir()
    (wiki / "artifacts" / "entitlement-clause-evidence").mkdir()
    (wiki / "artifacts" / "downstream-analysis-exemplars" / "test-exemplar.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.downstream_report_exemplar.v1",
                "artifact_id": "test-exemplar",
                "artifact_type": "downstream_analysis_exemplar",
                "title": "Test Entitlement Benchmark Exemplar",
                "wiki_role": "supporting_document_pattern",
                "gold_comparator_target": {
                    "accuracy_target": 0.95,
                    "scope": "standard_employees",
                    "seed_role": "thought_starter_and_comparator_council_selection",
                },
                "summary": {"entitlements": 1, "categories": 1, "explicit_review_items": 1},
                "categories": [
                    {
                        "category_id": "leave",
                        "label": "Leave",
                        "description": "Leave entitlements.",
                        "entitlements": [
                            {
                                "entitlement_id": "annual-leave",
                                "entitlement_label": "Annual Leave",
                                "definition": "Standard annual leave entitlement.",
                                "category": "Leave",
                                "clause_context_tags": ["leave_annual"],
                                "semantic_mapping": {
                                    "concept": {
                                        "human_taxonomy_path": ["Leave", "Annual Leave"],
                                        "comparison_basis": "leave_duration_or_access",
                                    },
                                    "comparator_semantics": {
                                        "entries": [
                                            {
                                                "council": "Ballarat",
                                                "finding": "4 weeks annual leave per year.",
                                                "presence": "provided",
                                                "quantum_signals": ["4 weeks"],
                                                "scope": "standard_employees",
                                            }
                                        ]
                                    },
                                    "target_semantics": {
                                        "target_council": "Ballarat",
                                        "presence": "provided",
                                        "comparator_posture": "aligns_with_comparator_pattern",
                                    },
                                    "quantification_semantics": {"quantification_type": "quantified_value"},
                                    "supportability_semantics": {"production_support_status": "report_semantics_captured_source_refs_required_for_production"},
                                    "review_semantics": {"learning_action": "candidate_for_structured_report_generation"},
                                },
                                "row_model": {"target_takeaway": "Ballarat aligns with other councils."},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-clause-evidence" / "annual-leave-source-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_clause_evidence.v1",
                "artifact_id": "annual-leave-source-evidence",
                "artifact_type": "entitlement_clause_evidence",
                "wiki_role": "source_clause_evidence",
                "entitlement_id": "annual-leave",
                "summary": {"source_clause_observed": 2},
                "global_takeaway": "Across the current source evidence set, Annual Leave is source-backed in the available councils.",
                "methodology": {
                    "method": "profiled_source_clause_search",
                    "hit_discovery_method": {"acceptance_rule": "test acceptance rule"},
                },
                "ab_test": {
                    "baseline": {"councils": 1, "source_clause_observed": 1},
                    "variant": {"councils": 2, "source_clause_observed": 2},
                },
                "council_evidence": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "presence": "source_clause_observed",
                        "finding": "Source clause provides 4 weeks annual leave.",
                        "quantum_signals": ["4 weeks"],
                        "normalised_values": [{"value": "4", "unit": "weeks per year"}],
                        "source_ref": {
                            "source_type": "agreement_cache_page",
                            "agreement_id": "ae-test",
                            "page": 2,
                            "evidence_state": "source_clause_observed",
                        },
                        "source_excerpts": [
                            {
                                "page": 2,
                                "excerpt": "An employee is entitled to 4 weeks annual leave.",
                            }
                        ],
                    },
                    {
                        "council": "Queenscliffe",
                        "agreement_id": "ae-extra",
                        "presence": "source_clause_observed",
                        "finding": "Source clause provides an extra annual leave day.",
                        "quantum_signals": ["1 day"],
                        "normalised_values": [{"value": "1", "unit": "day per year"}],
                        "source_ref": {
                            "source_type": "agreement_cache_page",
                            "agreement_id": "ae-extra",
                            "page": 5,
                            "evidence_state": "source_clause_observed",
                        },
                        "source_excerpts": [
                            {
                                "page": 5,
                                "excerpt": "One extra day applies.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    review_dir = tmp_path / "data" / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "entitlement_locator_gold_v1.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "agreement_id": "ae-test",
                        "clause_card_id": "clause-abc",
                        "council": "Ballarat",
                        "entitlement_id": "annual-leave",
                        "entitlement_label": "Annual Leave",
                        "entitlement_key": "annual_leave",
                        "feature_card_id": "feature-one",
                        "feature_card_ids": ["feature-one", "feature-two"],
                        "raw_clause_text_hash": "a" * 64,
                        "evidence_span_text": "An employee is entitled to 4 weeks annual leave.",
                        "evidence_span_text_hash": "b" * 64,
                        "machine_cell_status": "clause_value",
                        "machine_presence_status": "present_candidate",
                        "machine_value_status": "quantified",
                        "page": 2,
                        "reference_link_count": 1,
                        "reference_links": [{"relationship": "statutory_floor_dependency", "to_external": "NES", "text_hash": "c" * 64}],
                        "review_id": "review-annual-leave",
                        "review_status": "not_reviewed",
                    }
                ),
                json.dumps(
                    {
                        "agreement_id": "ae-test",
                        "clause_card_id": "",
                        "council": "Ballarat",
                        "entitlement_id": "bonus-leave",
                        "entitlement_label": "Bonus Leave",
                        "machine_cell_status": "not_found",
                        "review_status": "not_reviewed",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    (review_dir / "entitlement_locator_codex_suggestions_v1.jsonl").write_text(
        json.dumps(
            {
                "gold_review_id": "review-annual-leave",
                "suggested_review_decision": "correct",
                "confidence": "high",
                "requires_human_confirmation": True,
                "risk_flags": ["reference_links_present"],
                "evidence_summary": {
                    "agreement_id": "ae-test",
                    "clause_card_id": "clause-abc",
                    "feature_card_id": "feature-one",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-locator-qa-review").mkdir()
    (wiki / "artifacts" / "entitlement-locator-human-review").mkdir()
    (wiki / "artifacts" / "entitlement-locator-experiment").mkdir()
    (wiki / "artifacts" / "entitlement-cards").mkdir()
    (wiki / "artifacts" / "entitlement-card-repair-loop").mkdir()
    (wiki / "artifacts" / "entitlement-self-improvement").mkdir()
    (wiki / "artifacts" / "entitlement-loop-intelligence").mkdir()
    (wiki / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-next-10-offset-0.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_locator_experiment.v2",
                "artifact_id": "entitlement-locator-experiment-next-10-offset-0",
                "generated_at": "2026-05-10T00:00:00+00:00",
                "target_comparator_set": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "agreement_name": "Test Agreement",
                    }
                ],
                "profiles": [
                    {
                        "key": "annual_leave",
                        "entitlement_id": "annual-leave",
                        "label": "Annual Leave",
                        "rule_contract": {
                            "definition": "Annual leave for ordinary employees.",
                            "scope": "standard_employees",
                            "classification_boundary": {
                                "canonical_definition": "Annual leave for ordinary employees.",
                                "included": ["Ordinary paid annual leave."],
                                "excluded": ["Purchased leave."],
                                "needs_review": ["Ambiguous extra leave."],
                            },
                            "accepted_subclasses": [{"subclass_id": "annual-leave.ordinary", "label": "Ordinary annual leave"}],
                            "ai_improvement_questions": ["Does the value match the observed council pattern?"],
                        },
                        "target_rows": [
                            {
                                "council": "Ballarat",
                                "agreement_id": "ae-test",
                                "agreement_name": "Test Agreement",
                                "page_count": 3,
                                "state": "clause_found_value_extracted",
                                "candidate_count": 1,
                                "value_signals": ["4 weeks"],
                                "normalised_values": [{"value": "4", "unit": "weeks"}],
                                "clause_cards": [
                                    {
                                        "clause_id": "clause-abc",
                                        "page_number_physical": 2,
                                        "raw_clause_text": "Trailing page fragment. 12.1 An employee is entitled to 4 weeks annual leave. 12.2 Leave loading applies.",
                                        "review_status": "auto_extracted_benchmark_value",
                                    }
                                ],
                                "feature_cards": [
                                    {
                                        "feature_id": "feature-one",
                                        "clause_id": "clause-abc",
                                        "page_number_physical": 2,
                                        "value": "4",
                                        "unit": "weeks",
                                        "evidence_span_text": "An employee is entitled to 4 weeks annual leave.",
                                        "review_status": "auto_extracted_benchmark_value",
                                    }
                                ],
                                "best_candidate": {
                                    "page": 2,
                                    "heading": "Annual leave",
                                    "matched_terms": ["annual_leave"],
                                    "excerpt": "An employee is entitled to 4 weeks annual leave.",
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-cards" / "entitlement-cards-entitlement-locator-experiment-next-10-offset-0.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_cards.v1",
                "artifact_id": "entitlement-cards-entitlement-locator-experiment-next-10-offset-0",
                "generated_at": "2026-05-10T00:30:00+00:00",
                "method": {
                    "doctrine": "If the row needs review, the entitlement card is not emitted.",
                    "hard_gates": ["no review-required status"],
                },
                "summary": {
                    "source_cells": 1,
                    "value_extracted_cells": 1,
                    "entitlement_cards": 1,
                    "blocked_cells": 0,
                    "blocked_value_cells": 0,
                    "status_counts": {"proposed_governed": 1},
                    "gate_failure_counts": {},
                },
                "cards": [
                    {
                        "entitlement_card_id": "entitlement-card-one",
                        "status": "proposed_governed",
                        "entitlement_id": "annual-leave",
                        "entitlement_label": "Annual Leave",
                        "entitlement_definition": "Annual leave for ordinary employees.",
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "simple_sentence": "4 weeks of annual leave.",
                        "quantum": {"value_text": "4 weeks", "timeframe_or_basis": "per_year"},
                        "source_refs": {"clause_card_ids": ["clause-abc"], "feature_card_ids": ["feature-one"]},
                    }
                ],
                "blocked_samples": [],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-card-repair-loop" / "entitlement-card-repair-loop-entitlement-locator-experiment-next-10-offset-0.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_card_repair_loop.v1",
                "artifact_id": "entitlement-card-repair-loop-entitlement-locator-experiment-next-10-offset-0",
                "generated_at": "2026-05-10T00:45:00+00:00",
                "summary": {
                    "entitlements_reviewed": 1,
                    "blocked_rows_reviewed": 1,
                    "blocked_value_rows_reviewed": 1,
                    "llm_statuses": {"parsed": 1},
                    "sample_decisions": {"candidate_for_card_after_specific_fix": 1},
                    "failure_counts": {"review_status_not_strong": 1},
                },
                "rows": [
                    {
                        "entitlement_id": "annual-leave",
                        "label": "Annual Leave",
                        "blocked_rows": 1,
                        "blocked_value_rows": 1,
                        "failure_counts": {"review_status_not_strong": 1},
                        "llm_status": "parsed",
                        "repair_review": {
                            "entitlement_card_standard_review": {
                                "can_any_blocked_rows_become_cards": "yes",
                                "dominant_blocker": "review_status_not_strong",
                            }
                        },
                        "blocked_samples": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-self-improvement" / "entitlement-self-improvement-pass-entitlement-locator-experiment-next-10-offset-0.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_self_improvement_pass.v1",
                "artifact_id": "entitlement-self-improvement-pass-entitlement-locator-experiment-next-10-offset-0",
                "generated_at": "2026-05-10T01:00:00+00:00",
                "method": {"name": "internal_feature_card_self_improvement_pass"},
                "summary": {
                    "entitlements": 1,
                    "green_feature_cells": 1,
                    "statuses": {"definition_ready_candidate": 1},
                    "suggestion_types": {},
                    "definition_solidification_needed": 0,
                },
                "rows": [
                    {
                        "entitlement_id": "annual-leave",
                        "label": "Annual Leave",
                        "status": "definition_ready_candidate",
                        "coverage": {
                            "green_feature_cells": 1,
                            "clause_only_cells": 0,
                            "blocked_or_adjacent_cells": 0,
                        },
                        "observed_value_profile": {"feature_values": 1},
                        "normal_value_hypothesis": "Most common observed value is 4 weeks.",
                        "research_tasks": ["Compare green feature cards against the entitlement's cross-council value pattern."],
                        "improvement_suggestions": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-loop-intelligence" / "entitlement-loop-intelligence-entitlement-locator-experiment-next-10-offset-0.json").write_text(
        json.dumps(
            {
                "schema_version": "wiki.entitlement_loop_intelligence.v1",
                "artifact_id": "entitlement-loop-intelligence-entitlement-locator-experiment-next-10-offset-0",
                "generated_at": "2026-05-10T02:00:00+00:00",
                "method": {"name": "entitlement_loop_intelligence_synthesis"},
                "summary": {
                    "entitlements": 1,
                    "loop_statuses": {"ready_for_validation": 1},
                    "promotion_gates": {"candidate_for_human_validation": 1},
                    "validation_queue_items": 1,
                },
                "rows": [
                    {
                        "entitlement_id": "annual-leave",
                        "label": "Annual Leave",
                        "loop_status": "ready_for_validation",
                        "promotion_gate": "candidate_for_human_validation",
                        "entitlement_question": "For standard employees, does the agreement provide Annual Leave, and what duration applies?",
                        "answer_shape": {
                            "kind": "duration_or_time",
                            "expectation": "Expect 4 weeks as the normal answer unless source context shows a subclass or exception.",
                        },
                        "rule_change_candidates": {
                            "value_rules": ["Use 4 weeks as the provisional normal value and flag materially different values for review."],
                        },
                        "validation_queue": [
                            {
                                "council": "Ballarat",
                                "reasons": ["representative green feature card"],
                                "value_labels": ["4 weeks"],
                            }
                        ],
                        "next_loop_steps": ["Validate sampled green feature cards against the entitlement question."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-locator-qa-review" / "locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json").write_text(
        json.dumps(
            {
                "artifact_id": "locator-qa-review-entitlement-locator-experiment-next-52-offset-0",
                "generated_at": "2026-05-09T00:00:00+00:00",
                "doctrine": "Review doctrine",
                "review_questions": ["Did it find the right clause?"],
                "guardrails": ["Review before promotion."],
                "profiles": [
                    {
                        "key": "annual_leave",
                        "entitlement_id": "annual-leave",
                        "label": "Annual Leave",
                        "summary": {"councils": 1, "clause_found": 1, "value_found": 1},
                        "details": [
                            {
                                "agreement_id": "ae-test",
                                "cell_status": "clause_value",
                                "row_state": "clause_found_value_found",
                                "clause_found": True,
                                "value_found": True,
                                "clause_card_id": "clause-abc",
                                "feature_card_ids": ["feature-one"],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-locator-human-review" / "locator-human-review-worksheet-v1.csv").write_text(
        "\n".join(
            [
                "gold_review_id,council,agreement_id,entitlement_label,machine_cell_status,codex_confidence,human_review_decision,human_governance_result",
                "review-annual-leave,Ballarat,ae-test,Annual Leave,clause_value,high,,",
            ]
        ),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "entitlement-locator-human-review" / "locator-human-review-worksheet-v1.md").write_text(
        "# Human worksheet\n\nRows: `1`\n",
        encoding="utf-8",
    )
    governed_dir = tmp_path / "data" / "governed_canonical"
    governed_dir.mkdir(parents=True)
    (governed_dir / "entitlement_items.json").write_text(
        json.dumps(
            {
                "row_count": 1,
                "rows": [
                    {
                        "entitlement_id": "annual-leave",
                        "entitlement_label": "Annual Leave",
                        "review_governance_status": "staged_not_governed",
                        "governed_canonical_status": "staged_not_governed",
                        "value_status": "not_reviewed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    datamart_dir = tmp_path / "data" / "datamarts"
    datamart_dir.mkdir(parents=True)
    (datamart_dir / "entitlement_summary_mart.json").write_text(
        json.dumps({"mart_id": "entitlement_summary_mart", "row_count": 1, "rows": []}),
        encoding="utf-8",
    )
    static = tmp_path / "static"
    static.mkdir()
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=static,
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
        wiki_dir=wiki,
    )
    app = create_workbench_app(static_dir=static)
    app.include_router(build_wiki_router_for_service(WikiLayerService(paths)))
    client = TestClient(app)

    assert client.get("/api/wiki/status").json()["latest_run_id"] == run_id
    assert client.get("/api/wiki/runs/latest").json()["summary"]["agreements_mapped"] == 1
    assert client.get("/api/wiki/document-maps").json()["count"] == 1
    assert client.get("/api/wiki/document-maps/ae-test").json()["agreement_name"] == "Test Agreement"
    assert client.get("/api/wiki/reference-inputs").json()["count"] == 1
    assert client.get("/api/wiki/reference-inputs/know-your-award").json()["source_name"] == "Know Your Award"
    clause_library = client.get("/api/wiki/clause-library").json()
    assert clause_library["orientation"] == "global_clause_library"
    assert clause_library["summary"]["categories"] >= 1
    assert any(
        child["id"] == "ordinary-hours" and child["evidence_count"] >= 2
        for category in clause_library["categories"]
        for child in category["children"]
    )
    tag_registry = client.get("/api/wiki/tag-registry").json()
    assert tag_registry["scope_role"] == "source_knowledge_tagging"
    assert "not benchmark or entitlement findings" in tag_registry["governance_note"]
    assert tag_registry["summary"]["source_records"] == 2
    assert tag_registry["summary"]["tagged_records"] == 2
    assert any(
        tag["tag"] == "hours" and tag["record_count"] == 2
        for family in tag_registry["families"]
        for tag in family["tags"]
    )
    tagged_evidence = client.get("/api/wiki/tagged-evidence?tag=hours&limit=1").json()
    assert tagged_evidence["scope_role"] == "source_knowledge_tagging"
    assert "does not assert a benchmark fact" in tagged_evidence["governance_note"]
    assert tagged_evidence["summary"]["total"] == 2
    assert tagged_evidence["summary"]["returned"] == 1
    assert tagged_evidence["summary"]["has_more"] is True
    assert tagged_evidence["rows"][0]["tag_entries"][0]["tag"] == "hours"
    assert client.get("/api/wiki/tagged-evidence?tag=hours&record_type=section").json()["summary"]["total"] == 1
    assert client.get("/api/wiki/questions").json()["questions"][0]["status"] == "open"
    assert client.get("/api/wiki/learning-backlog").json()["items"][0]["status"] == "observed"
    assert client.get("/api/wiki/language-map").json()["terms"][0]["canonical_term"] == "ordinary_hours"
    artifacts = client.get("/api/wiki/artifacts").json()
    assert artifacts["count"] == 10
    exemplar_artifact = next(item for item in artifacts["artifacts"] if item["artifact_id"] == "test-exemplar")
    assert exemplar_artifact["gold_comparator_target"]["accuracy_target"] == 0.95
    assert exemplar_artifact["summary"]["entitlements"] == 1
    gold_target = client.get("/api/wiki/gold-comparator-target?artifact_id=test-exemplar").json()
    assert gold_target["gold_comparator_target"]["seed_role"] == "thought_starter_and_comparator_council_selection"
    child = gold_target["categories"][0]["children"][0]
    assert child["definition"] == "Standard annual leave entitlement."
    assert child["analysis"]["status"] == "source_clause_evidence_enriched"
    assert child["analysis"]["quick_takeaway"] == "Across the current source evidence set, Annual Leave is source-backed in the available councils."
    assert "Ballarat aligns" not in child["analysis"]["quick_takeaway"]
    assert child["analysis"]["source_evidence_methodology"]["method"] == "profiled_source_clause_search"
    assert child["analysis"]["source_evidence_ab_test"]["variant"]["councils"] == 2
    assert child["supportability"]["production_support_status"] == "source_clause_search_partial"
    assert len(child["council_evidence"]) == 2
    evidence = child["council_evidence"][0]
    assert evidence["council"] == "Ballarat"
    assert evidence["finding"] == "Source clause provides 4 weeks annual leave."
    assert evidence["report_finding"] == "4 weeks annual leave per year."
    assert evidence["agreement_id"] == "ae-test"
    assert evidence["source_excerpts"][0]["page"] == 2
    assert evidence["source_ref"]["agreement_id"] == "ae-test"
    assert evidence["source_ref"]["page"] == 2
    assert evidence["normalised_values"][0]["unit"] == "weeks per year"
    extra_evidence = child["council_evidence"][1]
    assert extra_evidence["council"] == "Queenscliffe"
    assert extra_evidence["report_finding"] is None
    assert extra_evidence["agreement_id"] == "ae-extra"
    assert extra_evidence["source_ref"]["agreement_id"] == "ae-extra"
    clause_cards = client.get("/api/wiki/clause-cards").json()
    assert clause_cards["summary"]["review_rows"] == 2
    assert clause_cards["summary"]["clause_cards"] == 1
    assert clause_cards["summary"]["feature_cards"] == 2
    assert clause_cards["summary"]["rows_without_clause_card"] == 1
    clause_card = clause_cards["cards"][0]
    assert clause_card["clause_card_id"] == "clause-abc"
    assert clause_card["pages"] == [2]
    assert clause_card["entitlements"][0]["label"] == "Annual Leave"
    assert clause_card["reference_links"][0]["to_external"] == "NES"
    clause_intelligence = client.get("/api/wiki/clause-intelligence").json()
    assert clause_intelligence["summary"]["locator_profiles"] == 1
    assert clause_intelligence["summary"]["gold_seed_rows"] == 2
    assert clause_intelligence["summary"]["codex_suggestions"] == 1
    assert clause_intelligence["summary"]["human_review_rows"] == 1
    assert clause_intelligence["summary"]["entitlement_cards"] == 1
    assert clause_intelligence["summary"]["entitlement_card_repair_entitlements"] == 1
    assert clause_intelligence["summary"]["governed_entitlement_rows"] == 1
    assert clause_intelligence["summary"]["final_entitlements"] == 1
    assert clause_intelligence["summary"]["target_test_councils"] == 1
    assert clause_intelligence["summary"]["entitlement_test_cells"] == 1
    assert clause_intelligence["summary"]["feature_card_test_cells"] == 1
    assert clause_intelligence["summary"]["self_improvement_entitlements"] == 1
    assert clause_intelligence["summary"]["definition_solidification_needed"] == 0
    assert clause_intelligence["summary"]["loop_intelligence_entitlements"] == 1
    assert clause_intelligence["summary"]["loop_validation_queue_items"] == 1
    assert clause_intelligence["summary"]["pipeline_freshness_status"] == "stale"
    assert clause_intelligence["summary"]["pipeline_stale_stages"] == 3
    assert clause_intelligence["pipeline_freshness"]["checks"][0]["stage"] == "entitlement_locator"
    assert clause_intelligence["entitlement_self_improvement"]["rows_by_entitlement"]["annual-leave"]["normal_value_hypothesis"] == "Most common observed value is 4 weeks."
    assert clause_intelligence["entitlement_loop_intelligence"]["rows_by_entitlement"]["annual-leave"]["loop_status"] == "ready_for_validation"
    matrix = clause_intelligence["entitlement_test_matrix"]
    assert matrix["summary"]["complete_to_feature_card"] == 1
    assert matrix["summary"]["document_spine_ready"] == 1
    assert matrix["entitlements"][0]["status"] == "complete_to_feature_card"
    assert matrix["cells"][0]["document_spine"] == "ready"
    assert matrix["cells"][0]["clause_cards"] == "ready"
    assert matrix["cells"][0]["feature_cards"] == "ready"
    assert matrix["cells"][0]["best_heading"] == "Annual leave"
    assert matrix["cells"][0]["review_text"].startswith("12.1 An employee")
    assert "4 weeks annual leave" in matrix["cells"][0]["review_text"]
    assert matrix["cells"][0]["feature_card_previews"][0]["feature_id"] == "feature-one"
    assert "4 weeks annual leave" in matrix["cells"][0]["clause_card_previews"][0]["text"]
    assert matrix["entitlements"][0]["rule_contract"]["classification_boundary"]["included"] == ["Ordinary paid annual leave."]
    assert matrix["entitlements"][0]["value_profile"]["common_values"]["4 weeks"] == 1
    assert client.get("/api/wiki/entitlement-test-matrix").json()["summary"]["test_cells"] == 1
    assert clause_intelligence["feature_cards"]["summary"]["feature_cards"] == 2
    assert clause_intelligence["entitlement_cards"]["summary"]["entitlement_cards"] == 1
    assert clause_intelligence["entitlement_cards"]["cards"][0]["simple_sentence"] == "4 weeks of annual leave."
    assert clause_intelligence["entitlement_card_repair_loop"]["summary"]["entitlements_reviewed"] == 1
    assert clause_intelligence["entitlement_card_repair_loop"]["summary"]["sample_decisions"]["candidate_for_card_after_specific_fix"] == 1
    assert clause_intelligence["reference_edges"]["summary"]["reference_edges"] == 1
    assert clause_intelligence["qa_review_pack"]["summary"]["clause_found"] == 1
    assert clause_intelligence["codex_suggestions"]["summary"]["confidence"]["high"] == 1
    assert clause_intelligence["human_review_worksheet"]["summary"]["blank_human_fields"]["human_review_decision"] == 1
    assert clause_intelligence["governed_entitlement_measures"]["summary"]["mart_rows"] == 1
    assert client.get("/api/wiki/runs/..%2Fbad").status_code == 404
