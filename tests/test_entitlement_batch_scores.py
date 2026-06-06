from scripts.build_entitlement_batch_scores import eligible_latest_cached_agreements


def test_eligible_latest_cached_agreements_excludes_decision_only_pdfs():
    rows = eligible_latest_cached_agreements()
    agreement_ids = {row["agreement_id"] for row in rows}

    assert "ae516921" not in agreement_ids
    assert "ae512085" not in agreement_ids
