from types import SimpleNamespace

from benchmarking_data_factory.workbench.scenario_review_resolution import _scenario_section_resolution


def test_source_table_only_scenario_does_not_block_section_completion():
    results = [
        SimpleNamespace(
            period_effective_from="2025-08-01",
            period_label="Baseline",
            status="baseline",
            sub_status="",
            reason="First period of agreement; no scenario applies.",
            rule_id=None,
            rule_quantum=None,
            external_deps=(),
        ),
        SimpleNamespace(
            period_effective_from="2026-02-01",
            period_label="2026-02-01",
            status="needs_attention",
            sub_status="table_only",
            reason="Table exists for this period but no uplift rule covers it.",
            rule_id=None,
            rule_quantum=None,
            external_deps=(),
        ),
    ]

    status, data = _scenario_section_resolution(results, "2026-05-04T00:00:00+00:00")

    assert status == "done"
    assert data["blocking_results"] == []
