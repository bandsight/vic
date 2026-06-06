from benchmarking_data_factory.governed_set import classify_rule, UPLIFT_ARCHETYPES


def test_archetype_vocabulary_fixed():
    assert "flat_pct" in UPLIFT_ARCHETYPES
    assert "pct_OR_floor" in UPLIFT_ARCHETYPES
    assert "unclassified" in UPLIFT_ARCHETYPES
    assert len(UPLIFT_ARCHETYPES) == 10


def test_flat_pct():
    result = classify_rule({"quantum": "3%", "quantum_type": "percentage", "effective_date": "2026-07-01"})
    assert result["pattern_archetype"] == "flat_pct"
    assert result["pct_component"] == 3.0
    assert result["internal_pct_component"] == 3.0
    assert result["resolved_pct"] == 3.0
    assert result["dollar_component"] is None


def test_flat_dollar():
    result = classify_rule({"quantum": "$1,000 gross flat payment", "quantum_type": "flat", "effective_date": "2026-07-01"})
    assert result["pattern_archetype"] == "flat_dollar"
    assert result["dollar_component"] == 1000.0


def test_pct_OR_floor_with_dollar():
    result = classify_rule({
        "quantum": "3% or $46 per week, whichever is the greater",
        "quantum_type": "pct_OR_floor",
        "effective_date": "2026-07-01",
    })
    assert result["pattern_archetype"] == "pct_OR_floor"
    assert result["pct_component"] == 3.0
    assert result["floor_dollar"] == 46.0
    assert result["dollar_floor_component"] == 46.0
    assert result["dollar_basis"] == "weekly"


def test_rate_cap_tracking():
    result = classify_rule({
        "quantum": "Victorian state government rate cap for the financial year",
        "quantum_type": "conditional",
        "effective_date": "2026-07-01",
    }, rate_cap_value=2.75)
    assert result["pattern_archetype"] == "rate_cap_tracking"
    assert result["rate_cap_component"] == 2.75
    assert result["external_cap_pct"] == 2.75
    assert result["external_cap_share"] == 1.0
    assert result["external_formula_pct"] == 2.75
    assert result["resolved_pct"] == 2.75


def test_rate_cap_plus_margin():
    result = classify_rule({
        "quantum": "3.5% or ESC rate cap, whichever is higher",
        "quantum_type": "conditional",
        "effective_date": "2026-07-01",
    }, rate_cap_value=2.75)
    assert result["pattern_archetype"] == "rate_cap_plus_margin"
    assert result["pct_component"] == 3.5
    assert result["external_cap_pct"] == 2.75
    assert result["resolved_pct"] == 3.5


def test_flat_pct_equal_to_cap_does_not_imply_cap_share():
    result = classify_rule({
        "quantum": "2.75% annual increase",
        "quantum_type": "percentage",
        "effective_date": "2026-07-01",
    }, rate_cap_value=2.75)
    assert result["pct_of_rate_cap"] is None
    assert result["external_cap_share"] is None


def test_pct_of_rate_cap_parses_share_floor_and_resolution():
    result = classify_rule({
        "quantum": "90% of the official rate cap, or 3.0% or $50 per week, whichever is greater",
        "quantum_type": "conditional",
        "effective_date": "2026-07-01",
    }, rate_cap_value=3.0, rate_cap_resolution={
        "raw_rate_cap": 3.0,
        "fraction": 0.9,
        "effective_rate": 3.0,
        "fixed_floor_pct": 3.0,
        "dollar_floor_per_week": 50.0,
    })
    assert result["pattern_archetype"] == "rate_cap_plus_margin"
    assert result["pct_component"] == 3.0
    assert result["internal_pct_component"] == 3.0
    assert result["pct_of_rate_cap"] == 0.9
    assert result["external_cap_share"] == 0.9
    assert result["external_cap_pct"] == 3.0
    assert result["external_formula_pct"] == 2.7
    assert result["resolved_pct"] == 3.0
    assert result["resolved_basis"] == "internal_pct_floor"
    assert result["floor_dollar"] == 50.0


def test_stepped_schedule():
    result = classify_rule({"quantum": "As per Schedule A", "quantum_type": "table_embedded", "effective_date": "2026-07-01"})
    assert result["pattern_archetype"] == "stepped_schedule"


def test_unclassified():
    result = classify_rule({"quantum": "to be negotiated", "quantum_type": "unknown", "effective_date": "2026-07-01"})
    assert result["pattern_archetype"] == "unclassified"


def test_preserves_source_fields():
    rule = {"quantum": "3%", "quantum_type": "percentage", "effective_date": "2026-07-01", "period_label": "Year 1"}
    result = classify_rule(rule)
    assert result["effective_date"] == "2026-07-01"
    assert result["source_quantum_type"] == "percentage"
    assert "Year 1" in result["source_rule_id"] or "2026-07-01" in result["source_rule_id"]
