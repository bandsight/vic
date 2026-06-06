import pytest

from benchmarking_data_factory.scenario_testing.engine import _apply_rule, run_scenarios


def _table(effective_from, rows, table_title="Rates"):
    return {
        "effective_from": effective_from,
        "table_title": table_title,
        "rows": rows,
    }


def _row(band, level, weekly=None, annual=None, fortnightly=None):
    row = {"band": band, "level": level}
    if weekly is not None:
        row["weekly_rate"] = weekly
    if annual is not None:
        row["annual_rate"] = annual
    if fortnightly is not None:
        row["fortnightly_rate"] = fortnightly
    return row


def _rule(effective_date, quantum_type="percentage", quantum="3.5%", **extra):
    rule = {
        "effective_date": effective_date,
        "period_label": f"Period {effective_date}",
        "quantum_type": quantum_type,
        "quantum": quantum,
    }
    rule.update(extra)
    return rule


def _canonical(pay_status="done", uplift_status="done", tables=None, rules=None):
    return {
        "agreement_id": "ae-test",
        "sections": {
            "pay_tables": {
                "status": pay_status,
                "tables": tables or [],
            },
            "uplift_rules": {
                "status": uplift_status,
                "data": {"rules": rules or []},
            },
        },
    }


def test_blocked_when_pay_tables_not_done():
    # pay_tables status must be done (gate); even with rules present, pending tables block.
    results = run_scenarios(
        _canonical(
            pay_status="pending",
            tables=[_table("2024-01-01", [_row("1", "1", weekly=1000.0)])],
            rules=[_rule("2025-01-01")],
        )
    )
    assert len(results) == 1
    assert results[0].status == "blocked"
    assert "pay_tables" in results[0].reason


def test_not_blocked_when_uplift_rules_status_is_in_progress():
    # Scenario testing is part of the decision to mark uplift_rules done,
    # so in_progress status must NOT block when rules exist.
    results = run_scenarios(
        _canonical(
            uplift_status="in_progress",
            tables=[
                _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
                _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
            ],
            rules=[_rule("2025-01-01")],
        )
    )
    # 2 periods: baseline + consistent
    assert len(results) == 2
    assert results[0].status == "baseline"
    assert results[1].status == "consistent"


def test_blocked_when_no_tables():
    results = run_scenarios(_canonical(tables=[], rules=[_rule("2025-01-01")]))
    assert len(results) == 1
    assert results[0].status == "blocked"
    assert "no pay tables" in results[0].reason


def test_blocked_when_no_rules():
    results = run_scenarios(
        _canonical(
            tables=[_table("2024-01-01", [_row("1", "1", weekly=1000.0)])],
            rules=[],
        )
    )
    assert len(results) == 1
    assert results[0].status == "blocked"
    assert "no uplift rules" in results[0].reason


def test_baseline_first_period():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[0].status == "baseline"
    assert len(results[0].cell_deltas) > 0


def test_consistent_clean_3pct_rule():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0), _row("2", "1", weekly=2000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0), _row("2", "1", weekly=2070.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"
    assert all(delta.within_tolerance for delta in results[1].cell_deltas)


def test_consistent_within_tolerance():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.5175)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"


def test_conflict_beyond_tolerance():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0), _row("2", "1", weekly=2000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1040.175), _row("2", "1", weekly=2070.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "conflict"
    assert any(not delta.within_tolerance for delta in results[1].cell_deltas)
    assert results[1].decision_recommendation["action"] == "needs_human_review"
    assert all(delta.recommended_action is None for delta in results[1].cell_deltas)


def test_isolated_no_increase_rows_recommend_computed():
    baseline_rows = [_row(str(band), "A", weekly=1000.0 + band * 10) for band in range(1, 11)]
    target_rows = []
    for band in range(1, 11):
        weekly = 1000.0 + band * 10
        if band == 2:
            target_rows.append(_row(str(band), "A", weekly=weekly))
        else:
            target_rows.append(_row(str(band), "A", weekly=weekly + 50.0))
    canonical = _canonical(
        tables=[
            _table("2024-01-01", baseline_rows),
            _table("2025-01-01", target_rows),
        ],
        rules=[_rule("2025-01-01", quantum_type="flat", quantum="$50 per week")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "needs_attention"
    assert results[1].decision_recommendation["action"] == "use_computed"
    assert results[1].decision_recommendation["basis"] == "isolated_no_increase_rows_against_mechanised_rule"
    failed = [delta for delta in results[1].cell_deltas if not delta.within_tolerance]
    assert len(failed) == 1
    assert failed[0].recommended_action == "use_computed"


def test_recommended_computed_values_cascade_to_downstream_preview():
    baseline_rows = [_row(str(band), "A", weekly=1000.0 + band * 10) for band in range(1, 11)]
    period_two_rows = []
    period_three_rows = []
    for band in range(1, 11):
        prior = 1000.0 + band * 10
        corrected_period_two = prior + 50.0
        if band == 2:
            period_two_rows.append(_row(str(band), "A", weekly=prior))
        else:
            period_two_rows.append(_row(str(band), "A", weekly=corrected_period_two))
        period_three_rows.append(_row(str(band), "A", weekly=corrected_period_two + 35.0))
    canonical = _canonical(
        tables=[
            _table("2024-01-01", baseline_rows),
            _table("2025-01-01", period_two_rows),
            _table("2026-01-01", period_three_rows),
        ],
        rules=[
            _rule("2025-01-01", quantum_type="flat", quantum="$50 per week"),
            _rule("2026-01-01", quantum_type="flat", quantum="$35 per week"),
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].decision_recommendation["action"] == "use_computed"
    period_two_bad = next(delta for delta in results[1].cell_deltas if delta.band == "2")
    period_three_bad = next(delta for delta in results[2].cell_deltas if delta.band == "2")
    assert period_two_bad.recommended_action == "use_computed"
    assert period_three_bad.prior_weekly == pytest.approx(1070.0)
    assert results[2].status == "consistent"


def test_table_only_no_rule():
    # Period 2025-01-01 has a table but no rule matches it.
    # Period 2026-01-01 has a matching rule so the canonical isn't globally blocked.
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
            _table("2026-01-01", [_row("1", "1", weekly=1070.0)]),
        ],
        rules=[_rule("2026-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "table_only"


def test_ambiguous_rule_conditional():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
        ],
        rules=[_rule("2025-01-01", quantum_type="conditional", quantum="if CPI > 2 then 3.5%")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "ambiguous_rule"


def test_awaiting_input_external_ref():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
        ],
        rules=[_rule("2025-01-01", quantum_external_ref="ESC rate cap")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "awaiting_input"


def test_pct_or_floor_applies_greater():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=100.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=140.0)]),
        ],
        rules=[_rule("2025-01-01", quantum_type="pct_OR_floor", quantum="3.5%", quantum_floor="$40")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"
    assert results[1].cell_deltas[0].computed_weekly == 140.0


def test_pct_or_floor_parses_percentage_after_dollar_floor():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "A", weekly=1250.275)]),
            _table("2025-01-01", [_row("1", "A", weekly=1290.275)]),
        ],
        rules=[
            _rule(
                "2025-01-01",
                quantum_type="pct_OR_floor",
                quantum="the greater of $40 or 2.5%",
                quantum_floor="$40",
            )
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"
    assert results[1].cell_deltas[0].computed_weekly == pytest.approx(1290.275)


def test_same_date_flat_then_percentage_sequence():
    canonical = _canonical(
        tables=[
            _table("2023-01-01", [_row("1", "A", weekly=1000.0), _row("4", "A", weekly=1200.0)]),
            _table("2024-01-01", [_row("1", "A", weekly=1027.17), _row("4", "A", weekly=1235.655)]),
        ],
        rules=[
            _rule(
                "2024-01-01",
                quantum_type="flat",
                quantum="Band 1-2: $10.00/week; Band 4-5: $15.00/week",
                period_label="Flat amount",
            ),
            _rule("2024-01-01", quantum_type="percentage", quantum="1.7%", period_label="Percentage amount"),
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"
    assert results[1].rule_quantum == "Band 1-2: $10.00/week; Band 4-5: $15.00/week then 1.7%"


def test_flat_rule_adds_dollar():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1025.0)]),
        ],
        rules=[_rule("2025-01-01", quantum_type="flat", quantum="$25.00")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"


def test_partial_rule_when_prior_missing_cells():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1035.0), _row("2", "1", weekly=2070.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "partial_rule"


def test_skips_allowance_rows():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [{"allowance": "meal", "weekly_rate": 25.0}, _row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [{"allowance": "meal", "weekly_rate": 26.0}, _row("1", "1", weekly=1035.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert len(results[1].cell_deltas) == 1
    assert results[1].status == "consistent"


def test_ordering_by_effective_from():
    canonical = _canonical(
        tables=[
            _table("2025-01-01", [_row("1", "1", weekly=1035.0)]),
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2026-01-01", [_row("1", "1", weekly=1071.225)]),
        ],
        rules=[_rule("2025-01-01"), _rule("2026-01-01")],
    )
    results = run_scenarios(canonical)
    assert [result.period_effective_from for result in results] == [
        "2024-01-01",
        "2025-01-01",
        "2026-01-01",
    ]


def test_no_weekly_equivalent():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [{"band": "1", "level": "1", "weekly_rate": None, "annual_rate": None, "fortnightly_rate": None}]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "no_weekly_equivalent"


def test_fuzzy_match_within_window_matches_rule():
    canonical = _canonical(
        tables=[
            _table("2026-07-01", [_row("1", "1", weekly=1000.0)]),
            _table("2027-07-01", [_row("1", "1", weekly=1030.0)]),
        ],
        rules=[_rule("2027-07-10", quantum_type="percentage", quantum="3.0")],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "consistent"
    assert results[1].sub_status != "table_only"
    assert "[matched rule 9d after period]" in results[1].reason


def test_fuzzy_match_outside_window_leaves_table_only():
    canonical = _canonical(
        tables=[
            _table("2026-07-01", [_row("1", "1", weekly=1000.0)]),
            _table("2027-07-01", [_row("1", "1", weekly=1030.0)]),
        ],
        rules=[_rule("2027-08-15", quantum_type="percentage", quantum="3.0")],
    )
    results = run_scenarios(canonical)
    assert results[1].sub_status == "table_only"


def test_exact_match_preferred_over_fuzzy():
    canonical = _canonical(
        tables=[
            _table("2026-07-01", [_row("1", "1", weekly=1000.0)]),
            _table("2027-07-01", [_row("1", "1", weekly=1030.0)]),
        ],
        rules=[
            _rule("2027-07-01", quantum_type="percentage", quantum="3.0"),
            _rule("2027-07-05", quantum_type="percentage", quantum="9.0"),
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].rule_id == "2027-07-01::Period 2027-07-01"
    assert results[1].rule_quantum == "3.0"


def test_closest_fuzzy_wins_and_ties_prefer_earlier():
    canonical = _canonical(
        tables=[
            _table("2026-07-01", [_row("1", "1", weekly=1000.0)]),
            _table("2027-07-01", [_row("1", "1", weekly=1030.0)]),
        ],
        rules=[
            _rule("2027-07-05", quantum_type="percentage", quantum="3.0"),
            _rule("2027-07-10", quantum_type="percentage", quantum="7.0"),
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].rule_id == "2027-07-05::Period 2027-07-05"
    assert results[1].reason.startswith("[matched rule 4d after period]")

    tie_canonical = _canonical(
        tables=[
            _table("2026-07-01", [_row("1", "1", weekly=1000.0)]),
            _table("2027-07-01", [_row("1", "1", weekly=1030.0)]),
        ],
        rules=[
            _rule("2027-06-27", quantum_type="percentage", quantum="3.0"),
            _rule("2027-07-05", quantum_type="percentage", quantum="5.0"),
        ],
    )
    tie_results = run_scenarios(tie_canonical)
    assert tie_results[1].rule_id == "2027-06-27::Period 2027-06-27"
    assert tie_results[1].reason.startswith("[matched rule 4d before period]")


def test_baseline_has_cell_deltas():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("2", "1", weekly=1000.0)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    assert len(results) == 1
    assert results[0].status == "baseline"
    assert len(results[0].cell_deltas) > 0
    for delta in results[0].cell_deltas:
        assert delta.prior_weekly is None
        assert delta.computed_weekly is None
        assert delta.actual_weekly is not None
        assert delta.within_tolerance is True


def test_baseline_cell_deltas_sorted():
    canonical = _canonical(
        tables=[
            _table(
                "2024-01-01",
                [
                    _row("3", "2", weekly=1300.0),
                    _row("1", "3", weekly=1100.0),
                    _row("1", "1", weekly=1000.0),
                ],
            ),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(canonical)
    observed = [(delta.band, delta.level) for delta in results[0].cell_deltas]
    assert observed == sorted(observed)


def test_override_use_computed():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1040.175)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(
        canonical,
        overrides={
            "2025-01-01": {
                "1:1": {"action": "use_computed", "weekly": 1035.0},
            }
        },
    )
    delta = results[1].cell_deltas[0]
    assert delta.within_tolerance is True
    assert delta.override_action == "use_computed"
    assert results[1].status == "consistent"


def test_override_accept():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1040.175)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(
        canonical,
        overrides={
            "2025-01-01": {
                "1:1": {"action": "accept"},
            }
        },
    )
    delta = results[1].cell_deltas[0]
    assert delta.within_tolerance is True
    assert delta.override_action == "accept"
    assert delta.actual_weekly == 1040.175


def test_override_accept_resolves_new_uncovered_row():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "A", weekly=1000.0)]),
            _table(
                "2025-01-01",
                [
                    _row("1", "A", weekly=1035.0),
                    _row("2", "A", weekly=1200.0),
                ],
            ),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(
        canonical,
        overrides={
            "2025-01-01": {
                "2:A": {"action": "accept"},
            }
        },
    )
    assert results[1].status == "consistent"
    new_row = next(delta for delta in results[1].cell_deltas if delta.band == "2")
    assert new_row.prior_weekly is None
    assert new_row.override_action == "accept"
    assert new_row.within_tolerance is True


def test_table_embedded_rule_uses_published_table_as_source():
    canonical = _canonical(
        tables=[
            _table("2025-08-01", [_row("1", "A", weekly=1000.0)]),
            _table("2026-02-01", [_row("1", "A", weekly=1020.0)]),
        ],
        rules=[
            _rule(
                "2026-02-01",
                quantum_type="table_embedded",
                quantum="Rates as per Pay Schedule 1 effective 1 February 2026",
            )
        ],
    )
    results = run_scenarios(canonical)
    assert results[1].status == "table_resolved"
    assert results[1].sub_status == "table_embedded"
    assert results[1].cell_deltas[0].prior_weekly == 1000.0
    assert results[1].cell_deltas[0].actual_weekly == 1020.0


def test_rate_cap_pct_or_floor_uses_external_cap_and_dollar_floor():
    canonical = _canonical(
        tables=[
            _table(
                "2025-09-01",
                [
                    _row("1", "A", weekly=1000.0),
                    _row("8", "D", weekly=2000.0),
                ],
            ),
            _table(
                "2026-09-01",
                [
                    _row("1", "A", weekly=1038.0),
                    _row("8", "D", weekly=2055.0),
                ],
            ),
        ],
        rules=[
            _rule(
                "2026-09-01",
                quantum_type="pct_OR_floor",
                quantum="the greater of: the Rate Cap Amount; 1.75%; or $38.00 per week",
                quantum_floor="$38.00 per week",
                quantum_external_ref="Rate Cap Amount",
            )
        ],
    )
    results = run_scenarios(canonical, lga_short_name="Whitehorse")
    assert results[1].status == "consistent"
    observed = {(delta.band, delta.level): delta.computed_weekly for delta in results[1].cell_deltas}
    assert observed[("1", "A")] == pytest.approx(1038.0)
    assert observed[("8", "D")] == pytest.approx(2055.0)


def test_override_deleted():
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1040.175)]),
        ],
        rules=[_rule("2025-01-01")],
    )
    results = run_scenarios(
        canonical,
        overrides={
            "2025-01-01": {
                "1:1": {"action": "deleted"},
            }
        },
    )
    delta = results[1].cell_deltas[0]
    assert delta.override_action == "deleted"
    assert delta.actual_weekly == 1040.175
    assert delta.within_tolerance is True


def test_override_chain_recalculation():
    """use_computed in period N should flow through as prior_weekly in period N+1."""
    canonical = _canonical(
        tables=[
            _table("2024-01-01", [_row("1", "1", weekly=1000.0)]),
            _table("2025-01-01", [_row("1", "1", weekly=1040.0)]),
            _table("2026-01-01", [_row("1", "1", weekly=1071.225)]),
        ],
        rules=[_rule("2025-01-01"), _rule("2026-01-01")],
    )
    results = run_scenarios(
        canonical,
        overrides={
            "2025-01-01": {
                "1:1": {"action": "use_computed", "weekly": 1035.0},
            }
        },
    )
    # Period 2: override marks the cell as within-tolerance
    override_delta = results[1].cell_deltas[0]
    assert override_delta.within_tolerance is True
    assert override_delta.override_action == "use_computed"
    # Period 3: prior_weekly reflects the overridden value, not the raw 1040
    assert results[2].cell_deltas[0].prior_weekly == 1035.0
    # And with 1035 prior + 3.5% rule, computed 1071.225 matches actual → consistent
    assert results[2].status == "consistent"


def test_dollar_floor_binds_row_1a():
    rule = {
        "quantum_type": "percentage",
        "quantum": "3.0000%",
        "_rate_cap_resolution": {"dollar_floor_per_week": 50.0},
    }
    result = _apply_rule(rule, {("1", "A"): 1234.41})
    assert result[("1", "A")] == pytest.approx(1284.41, abs=0.01)


def test_dollar_floor_binds_row_5a():
    rule = {
        "quantum_type": "percentage",
        "quantum": "3.0000%",
        "_rate_cap_resolution": {"dollar_floor_per_week": 50.0},
    }
    result = _apply_rule(rule, {("5", "A"): 1556.48})
    assert result[("5", "A")] == pytest.approx(1606.48, abs=0.01)


def test_dollar_floor_not_binding_row_7a():
    rule = {
        "quantum_type": "percentage",
        "quantum": "3.0000%",
        "_rate_cap_resolution": {"dollar_floor_per_week": 50.0},
    }
    result = _apply_rule(rule, {("7", "A"): 2099.10})
    assert result[("7", "A")] == pytest.approx(2162.07, abs=0.01)
