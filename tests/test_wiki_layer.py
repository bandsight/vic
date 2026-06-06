import json

from benchmarking_data_factory.workbench.wiki_layer import (
    build_document_map,
    build_reference_input_map,
    build_wiki_pilot,
    classify_text_block,
    extract_heading_candidates,
    page_role_for_text,
    source_container_type_for_text,
)


def test_classify_text_block_tags_clause_context_content():
    result = classify_text_block(
        """
        12. Hours, allowances and higher duties
        Ordinary hours of work will be rostered for all employees.
        Higher duties allowance applies when an employee performs work at a higher classification.
        """
    )

    functions = {item["tag"] for item in result["clause_function"]}
    context = {item["tag"] for item in result["context_scope"]}

    assert result["clause_context_relevance"] == "core_clause"
    assert {"allowances", "higher_duties"} & functions
    assert "classification_context" in context


def test_classify_text_block_tags_band_responsibility_context():
    result = classify_text_block(
        """
        Appendix A - Classification Definitions
        Job characteristics for Band 5 include accountability and extent of authority,
        judgement and decision making, specialist knowledge and skills, management skills,
        interpersonal skills, and qualifications and experience.
        """
    )

    context = {item["tag"] for item in result["context_scope"]}

    assert result["clause_context_relevance"] == "context"
    assert "classification_context" in context
    assert "band_responsibility_context" in context


def test_extract_heading_candidates_handles_numbered_and_schedule_headings():
    headings = extract_heading_candidates(
        """
        1. Title
        This Agreement shall be known as the test agreement.

        14 Classification Structure
        Employees are classified by Band and Level.

        Schedule B - Maternal and Child Health Nurses
        Specialist schedule text.
        """
    )

    titles = [item["title"] for item in headings]

    assert "Title" in titles
    assert "Classification Structure" in titles
    assert "Maternal and Child Health Nurses" in titles


def test_extract_heading_candidates_stitches_split_clause_number_and_title():
    headings = extract_heading_candidates(
        """
        29.
        Allowances
        Employees will receive an allowance.

        30.
        Travel
        Travel reimbursement applies.
        """
    )

    assert [item["heading"] for item in headings[:2]] == ["29. Allowances", "30. Travel"]
    assert [item["title"] for item in headings[:2]] == ["Allowances", "Travel"]


def test_extract_heading_candidates_filters_numbered_paragraph_fragments():
    headings = extract_heading_candidates(
        """
        18 years of age, by a parent or guardian of the Employee; and
        3) The work is not appropriate for the Employee to perform; or
        3. 1.1
        12. Classification Structure
        """
    )

    assert [item["title"] for item in headings] == ["Classification Structure"]


def test_build_document_map_surfaces_context_questions_and_language_candidates():
    document_map = build_document_map(
        "ae-test",
        [
            """
            10. Ordinary Hours and Allowances
            Ordinary employees receive an on-call allowance and ordinary hours apply.
            Higher duties may be paid as an acting allowance.
            """,
            """
            Schedule C - Maternal and Child Health Nurses
            Nurses are covered by a specialist schedule. On-call and overtime provisions may differ for this group.
            """,
        ],
        metadata={"agreement_name": "Test Council Agreement"},
        generated_at="2026-05-05T00:00:00+00:00",
    )

    assert document_map["schema_version"] == "wiki.document_map.v1"
    assert document_map["summary"]["pages_scanned"] == 2
    assert document_map["summary"]["sections_detected"] >= 2
    assert document_map["summary"]["page_role_counts"]["agreement_text"] >= 1
    assert document_map["summary"]["language_candidates"] >= 2
    assert document_map["questions"][0]["code"] == "clause_context_scope_needs_review"
    assert document_map["sections"][0]["review_state"] == "proposed"
    assert document_map["sections"][0]["source_container_type"]


def test_page_role_model_separates_front_matter_contents_and_clause_text():
    assert page_role_for_text("2024 FWCA 3269\ns.185 Application for approval\nThe Commission must approve the agreement." * 8) == "approval_decision_front_matter"
    assert page_role_for_text("1. Title .......... 1\n2. Allowances .......... 4\n3. Annual Leave .......... 8\n4. Overtime .......... 10") == "table_of_contents"
    assert source_container_type_for_text("38. Annual Leave\nEmployees are entitled to annual leave loading.") == "agreement_clause"


def test_build_reference_input_map_uses_source_refs_not_agreement_refs():
    reference_input = build_reference_input_map(
        "know-your-award",
        [
            """
            POSITION DESCRIPTIONS AND CLASSIFICATIONS
            Employees should have a position description and classification by Band.
            Annual increments and higher duties allowance may be relevant.
            """,
            "",
        ],
        metadata={"source_name": "Know Your Award", "source_pdf_hash": "abc123"},
        generated_at="2026-05-05T00:00:00+00:00",
    )

    assert reference_input["schema_version"] == "wiki.reference_input.v1"
    assert reference_input["source_id"] == "know-your-award"
    assert reference_input["source"]["source_pdf_hash"] == "abc123"
    assert reference_input["summary"]["pages_scanned"] == 2
    assert reference_input["language_candidates"][0]["source_ref"]["source_id"] == "know-your-award"
    assert "agreement_id" not in reference_input["language_candidates"][0]["source_ref"]
    assert any(item["code"] == "weak_reference_page_text" for item in reference_input["learning_backlog"])


def test_build_reference_input_map_surfaces_band_responsibility_terms():
    reference_input = build_reference_input_map(
        "pds-and-classifications",
        [
            """
            PDS & CLASSIFICATIONS
            Guide 2 - Bands 3 to 8 Features - Accountability & Extent of Authority.
            Band responsibilities are described through judgement and decision making,
            specialist knowledge and skills, management skills, interpersonal skills,
            and qualifications and experience.
            """
        ],
        metadata={"source_name": "PDs and Classifications"},
        generated_at="2026-05-05T00:00:00+00:00",
    )

    terms = {candidate["canonical_term"] for candidate in reference_input["language_candidates"]}
    page_context = {
        item["tag"]
        for item in reference_input["pages"][0]["tags"]["context_scope"]
    }

    assert "band_responsibilities" in terms
    assert "band_responsibility_context" in page_context


def test_build_wiki_pilot_writes_document_maps_questions_and_language_map(tmp_path):
    pages = {
        "ae-one": [
            """
            1. Title
            Test Agreement One.

            9. Hours of Work
            Ordinary hours of work will be rostered for all employees.
            """
        ],
        "ae-two": [
            """
            2. Allowances
            Higher duties allowance applies to ordinary employees.
            Annual leave loading and personal leave are included.
            """,
            "",
        ],
    }

    result = build_wiki_pilot(
        root=tmp_path,
        ae_ids=["ae-one", "ae-two"],
        page_text_loader=lambda ae_id: pages[ae_id],
        metadata_loader=lambda ae_id: {"agreement_name": f"{ae_id} agreement"},
        now=lambda: "2026-05-05T01:02:03+00:00",
    )

    manifest = json.loads((tmp_path / "wiki" / "wiki-manifest.json").read_text(encoding="utf-8"))
    document_map = json.loads((tmp_path / "wiki" / "document-maps" / "ae-two.json").read_text(encoding="utf-8"))
    language_map = json.loads((tmp_path / "wiki" / "language-maps" / "clause-context-terms.json").read_text(encoding="utf-8"))
    questions = json.loads((tmp_path / "wiki" / "questions" / f"{result['run_id']}.json").read_text(encoding="utf-8"))
    backlog = json.loads((tmp_path / "wiki" / "learning-backlog" / f"{result['run_id']}.json").read_text(encoding="utf-8"))

    assert result["summary"]["agreements_mapped"] == 2
    assert manifest["latest_run_id"] == result["run_id"]
    assert manifest["scope_focus"] == "entitlements_conditions_benefits"
    assert document_map["agreement_name"] == "ae-two agreement"
    assert any(term["canonical_term"] == "higher_duties" for term in language_map["terms"])
    assert questions["schema_version"] == "wiki.questions.v1"
    assert any(item["code"] == "weak_page_text" for item in backlog["items"])
