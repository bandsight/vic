"""Deterministic review hints for pay-table and scenario workflows.

These hints encode operator heuristics that are independent of a particular
agreement. They do not mutate canonical data; they surface likely next actions
and short save-note reasons for human review.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from benchmarking_data_factory.scenario_testing.normalise import (
    is_standard_band_level_row,
    standard_cell_key,
)


STANDARD_COMPLETE_CELL_THRESHOLD = 30

NON_STANDARD_HINT_TERMS = (
    "maternal",
    "child health",
    "immunisation",
    "nurse",
    "library",
    "leisure",
    "early childhood",
    "school crossing",
    "sessional",
    "waste",
    "recycling",
    "outdoor",
    "infrastructure",
    "executive",
    "senior officer",
    "coordinator",
    "team leader",
    "preschool",
)


def build_pay_table_review_hints(
    canonical: dict[str, Any],
    tables: list[dict[str, Any]],
    *,
    suggestions: list[dict[str, Any]] | None = None,
    candidate_pages: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic hints for the pay-table review pane."""
    hints: list[dict[str, Any]] = []
    all_candidate_pages = _normalise_pages(candidate_pages) or _overview_pay_pages(canonical)
    rules = _extract_uplift_rules(canonical)
    suggestion_by_index = _suggestion_by_index(suggestions or [])

    hints.extend(_starting_point_hints(canonical, tables, suggestions or [], rules))
    hints.extend(_range_extraction_hints(tables, all_candidate_pages))
    hints.extend(_undated_prior_table_hints(tables, suggestion_by_index))
    hints.extend(_standard_scope_hints(tables))
    hints.extend(_rules_first_hints(tables, suggestion_by_index, rules))
    hints.extend(_level_d_missing_hints(tables))

    return _dedupe_hints(hints)


def build_scenario_review_hints(
    canonical: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic hints for uplift scenario review outputs."""
    del canonical  # Reserved for future cross-checks against canonical context.
    hints: list[dict[str, Any]] = []

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        period = str(scenario.get("period_effective_from") or "")
        decision = scenario.get("decision_recommendation")
        if isinstance(decision, dict) and decision.get("action") == "use_computed":
            deltas = _scenario_deltas(scenario)
            affected = [
                delta for delta in deltas
                if delta.get("recommended_action") == "use_computed"
                or (
                    delta.get("within_tolerance") is False
                    and delta.get("computed_weekly") is not None
                    and delta.get("recommended_action") != "accept_table"
                )
            ]
            introduced = [
                delta for delta in deltas
                if delta.get("recommended_action") == "accept_table"
                and delta.get("computed_weekly") is None
                and delta.get("actual_weekly") is not None
            ]
            value_evidence = _scenario_value_evidence(affected)
            introduced_count = len(introduced) or int(decision.get("introduced_cells") or 0)
            hints.append(_hint(
                code="scenario_use_computed",
                scope=period or "unknown",
                category="scenario",
                severity="decision",
                title="Use computed values",
                message=(
                    "The scenario engine found a systemic variance and its "
                    "decision recommendation is to use computed rates."
                ),
                recommendation=(
                    "Apply the computed override for the computed variance cells"
                    + (
                        " and keep introduced rows at published table value"
                        if introduced_count else ""
                    )
                    + ", then save the scenario note with the basis shown here."
                ),
                confidence=str(decision.get("confidence") or "medium"),
                evidence=[
                    f"Period: {period}" if period else "",
                    f"Basis: {decision.get('basis')}" if decision.get("basis") else "",
                    f"Rule quantum: {scenario.get('rule_quantum')}" if scenario.get("rule_quantum") else "",
                    f"Computed variance cells: {len(affected) or decision.get('affected_cells') or 0}",
                    f"Introduced rows accepted from table: {introduced_count}" if introduced_count else "",
                    *value_evidence,
                ],
                save_note=(
                    f"{period}: used computed values because the scenario "
                    f"recommendation was {decision.get('basis') or 'systemic variance'}"
                    + ("; introduced rows were kept at the published table value." if introduced_count else ".")
                ),
                target={
                    "period": period,
                    "basis": decision.get("basis"),
                    "introduced_cells": introduced_count,
                },
            ))
        elif isinstance(decision, dict) and decision.get("action") == "needs_rule_extraction_review":
            deltas = _scenario_deltas(scenario)
            affected = [delta for delta in deltas if delta.get("within_tolerance") is False]
            hints.append(_hint(
                code="scenario_review_extracted_uplift_rule",
                scope=period or "unknown",
                category="scenario",
                severity="warning",
                title="Review extracted uplift rule",
                message=(
                    "The table has a coherent movement pattern, but it conflicts "
                    "with the accepted uplift rule."
                ),
                recommendation=(
                    "Go back to uplift-rule extraction and correct the accepted rule "
                    "before saving scenario decisions or promoting this period."
                ),
                confidence=str(decision.get("confidence") or "high"),
                evidence=[
                    f"Period: {period}" if period else "",
                    f"Basis: {decision.get('basis')}" if decision.get("basis") else "",
                    f"Rule quantum: {scenario.get('rule_quantum')}" if scenario.get("rule_quantum") else "",
                    f"Mechanised weekly increase: {decision.get('mechanised_weekly_increase')}" if decision.get("mechanised_weekly_increase") is not None else "",
                    f"Table implied weekly increase: {decision.get('implied_weekly_increase')}" if decision.get("implied_weekly_increase") is not None else "",
                    f"Consistent offset: {decision.get('consistent_offset')}" if decision.get("consistent_offset") is not None else "",
                    *_scenario_value_evidence(affected),
                ],
                save_note=(
                    f"{period}: held scenario acceptance because the published "
                    "table pattern conflicts with the extracted uplift rule."
                ),
                target={
                    "period": period,
                    "basis": decision.get("basis"),
                    "implied_weekly_increase": decision.get("implied_weekly_increase"),
                    "mechanised_weekly_increase": decision.get("mechanised_weekly_increase"),
                },
            ))
        elif isinstance(decision, dict) and decision.get("action") == "needs_human_review":
            deltas = _scenario_deltas(scenario)
            affected = [delta for delta in deltas if delta.get("within_tolerance") is False]
            hints.append(_hint(
                code="scenario_inspect_values_before_choice",
                scope=period or "unknown",
                category="scenario",
                severity="decision",
                title="Inspect table values before choosing",
                message=(
                    "The engine found a variance but did not have enough evidence "
                    "to automatically choose the computed values."
                ),
                recommendation=(
                    "Compare the printed value against the computed value and the "
                    "uplift basis. If there is no source clue, use rules-first reasoning."
                ),
                confidence=str(decision.get("confidence") or "medium"),
                evidence=[
                    f"Period: {period}" if period else "",
                    f"Basis: {decision.get('basis')}" if decision.get("basis") else "",
                    f"Fallback action: {decision.get('fallback_action')}" if decision.get("fallback_action") else "",
                    f"Rule quantum: {scenario.get('rule_quantum')}" if scenario.get("rule_quantum") else "",
                    *_scenario_value_evidence(affected),
                ],
                save_note=(
                    f"{period}: reviewed printed values against computed values "
                    f"before choosing an override for {decision.get('basis') or 'variance'}."
                ),
                target={
                    "period": period,
                    "basis": decision.get("basis"),
                    "fallback_action": decision.get("fallback_action"),
                },
            ))

        if scenario.get("sub_status") in {"rate_cap_pending", "rate_cap_confirmed_since_save"}:
            hints.append(_rate_cap_hint(scenario))
            continue
        if any(_external_dep_pending(dep) for dep in scenario.get("external_deps") or []):
            hints.append(_rate_cap_hint(scenario))

        level_d_cells = _scenario_missing_level_d_cells(scenario)
        if level_d_cells:
            hints.append(_hint(
                code="scenario_level_d_missing",
                scope=period or "unknown",
                category="scenario",
                severity="decision",
                title="Level D missing after prior period",
                message=(
                    "A Level D cell appears in the prior/computed chain but is "
                    "missing from the extracted period while neighbouring levels remain."
                ),
                recommendation=(
                    "Treat this as a likely table misprint and use the computed "
                    "Level D value unless the source gives a separate exclusion."
                ),
                confidence="medium",
                evidence=[f"Period: {period}", f"Cells: {', '.join(level_d_cells[:6])}"],
                save_note=(
                    f"{period}: treated missing Level D cell(s) as likely misprint "
                    "and used computed values."
                ),
                target={"period": period, "cells": level_d_cells},
            ))

    return _dedupe_hints(hints)


def _starting_point_hints(
    canonical: dict[str, Any],
    tables: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not tables:
        return []

    hints: list[dict[str, Any]] = []
    missing_dates = [
        index + 1 for index, table in enumerate(tables)
        if not _iso_text(table.get("effective_from"))
    ]
    operative_date = _agreement_operative_date(canonical)
    if not suggestions and (missing_dates or tables):
        evidence = [
            f"Draft tables: {len(tables)}",
            f"Undated tables: {len(missing_dates)}",
            f"Accepted uplift rules: {len(rules)}",
            f"Agreement operative/effective date: {operative_date}" if operative_date else "",
        ]
        hints.append(_hint(
            code="run_suggest_effective_dates",
            scope="pay_tables",
            category="workflow",
            severity="decision",
            title="Run Suggest Effective Dates",
            message=(
                "The review starting point is the agreement operative date, the "
                "uplift rule, and any future factor that changes after that date."
            ),
            recommendation=(
                "Run Suggest Effective Dates, then compare the suggestion against "
                "accepted uplift rules and future factors before saving."
            ),
            confidence="high",
            evidence=evidence,
            save_note=(
                "Checked suggested effective dates against operative date, uplift "
                "rule, and future factors before saving."
            ),
            target={"missing_effective_date_tables": missing_dates},
        ))

    if not rules:
        hints.append(_hint(
            code="accept_uplift_rules_before_final_dates",
            scope="pay_tables",
            category="workflow",
            severity="warning",
            title="Accept uplift rules before final dates",
            message=(
                "No accepted uplift rules are available to anchor the pay-table "
                "timeline."
            ),
            recommendation=(
                "Extract or accept uplift rules before finalising effective dates. "
                "Without other clues, use rules-first chronology."
            ),
            confidence="medium",
            evidence=[f"Draft tables: {len(tables)}", "Accepted uplift rules: 0"],
            save_note="Finalised pay-table dates after checking accepted uplift rules.",
            target={},
        ))

    future_rules = [rule for rule in rules if _rule_has_future_factor(rule)]
    if future_rules:
        hints.append(_hint(
            code="future_factor_check",
            scope="pay_tables",
            category="effective_dates",
            severity="warning",
            title="Check future uplift factors",
            message=(
                "At least one uplift rule depends on a future factor such as a "
                "rate cap or conditional comparison."
            ),
            recommendation=(
                "Do not promote or construct future periods until the factor is "
                "known, unless the table is explicitly a working assumption."
            ),
            confidence="high",
            evidence=[_rule_evidence(rule) for rule in future_rules[:4]],
            save_note="Checked future uplift factor before promoting or constructing later periods.",
            target={"rule_dates": [rule.get("effective_date") for rule in future_rules]},
        ))

    return hints


def _range_extraction_hints(
    tables: list[dict[str, Any]],
    candidate_pages: list[int],
) -> list[dict[str, Any]]:
    runs = [run for run in _contiguous_runs(candidate_pages) if len(run) >= 2]
    if not runs:
        return []
    has_spanning_table = any(len(_table_source_pages(table)) >= 2 for table in tables)
    if has_spanning_table:
        return []

    run = max(runs, key=len)
    scope = f"{run[0]}-{run[-1]}"
    return [_hint(
        code="extract_range_for_page_spanning_table",
        scope=scope,
        category="extraction",
        severity="decision",
        title="Use extract range for candidate pages",
        message=(
            "Candidate pay-table pages are contiguous, which often means one "
            "logical table spans more than one page."
        ),
        recommendation=(
            "Use Extract range over the contiguous candidate pages before saving "
            "or dropping tables."
        ),
        confidence="medium",
        evidence=[f"Contiguous candidate pages: {scope}", f"Draft tables: {len(tables)}"],
        save_note=f"Used extract range for pages {scope} because pay tables appeared page-spanning.",
        target={"pages": run},
    )]


def _undated_prior_table_hints(
    tables: list[dict[str, Any]],
    suggestion_by_index: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    affected: list[str] = []
    for index, table in enumerate(tables):
        if _iso_text(table.get("effective_from")):
            continue
        suggestion = suggestion_by_index.get(index) or {}
        if _iso_text(suggestion.get("suggested_effective_from")):
            continue
        text = _table_text(table)
        if not _looks_like_prior_or_base_table(text):
            continue
        affected.append(f"Table {index + 1}: {table.get('table_title') or 'Untitled'}")

    if not affected:
        return []

    return [_hint(
        code="drop_undated_prior_or_base_table",
        scope="pay_tables",
        category="effective_dates",
        severity="decision",
        title="Drop undated prior/base table if it blocks the chain",
        message=(
            "A prior/base table is useful context, but it should not be forced "
            "onto the agreement operative date when the agreement does not date it."
        ),
        recommendation=(
            "Leave it out of the saved governed pay-table chain, or keep it only "
            "as contextual evidence, if no effective_from can be established."
        ),
        confidence="medium",
        evidence=affected[:6],
        save_note=(
            "Dropped undated prior/base table because no effective_from was "
            "established and retaining it would distort the pay-table timeline."
        ),
        target={"affected": affected},
    )]


def _standard_scope_hints(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    affected: list[str] = []
    for index, table in enumerate(tables):
        table_text = _table_text(table)
        rows = table.get("rows") or []
        standard_count = len(_standard_cells(table))
        keyword_hits = _keyword_hits(table_text)
        non_standard_rows = [
            row for row in rows
            if _keyword_hits(" ".join(str(row.get(key) or "") for key in ("title", "classification", "notes")))
        ]
        if keyword_hits or non_standard_rows:
            table_label = table.get("table_title") or f"Table {index + 1}"
            affected.append(
                f"{table_label} ({standard_count} standard cells, "
                f"{len(non_standard_rows)} specialised rows)"
            )

    if not affected:
        return []

    return [_hint(
        code="standard_banding_scope",
        scope="pay_tables",
        category="scope",
        severity="warning",
        title="Keep standard bandings only",
        message=(
            "The draft includes text that looks like a specialised cohort or "
            "role-only schedule."
        ),
        recommendation=(
            "Keep ordinary band/level rows for benchmarking and drop specialised "
            "cohort tables or rows unless they are the general employee matrix."
        ),
        confidence="high",
        evidence=affected[:6],
        save_note="Dropped specialised cohort rows/tables and retained standard bandings only.",
        target={"affected": affected},
    )]


def _rules_first_hints(
    tables: list[dict[str, Any]],
    suggestion_by_index: dict[int, dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    table_rules = sorted(
        (rule for rule in rules if _is_table_embedded_rule(rule)),
        key=lambda rule: str(rule.get("effective_date") or ""),
    )
    if not table_rules:
        return []

    table_rule_dates = {
        _iso_text(rule.get("effective_date"))
        for rule in table_rules
        if _iso_text(rule.get("effective_date"))
    }
    hints: list[dict[str, Any]] = []
    for index, table in enumerate(tables):
        if len(_standard_cells(table)) < STANDARD_COMPLETE_CELL_THRESHOLD:
            continue
        current_date = _iso_text(table.get("effective_from"))
        suggestion = suggestion_by_index.get(index) or {}
        suggested_date = _iso_text(suggestion.get("suggested_effective_from"))
        candidate_date = suggested_date or current_date
        if not candidate_date:
            continue
        if current_date in table_rule_dates or suggested_date in table_rule_dates:
            continue
        later_rule = next(
            (
                rule for rule in table_rules
                if _iso_text(rule.get("effective_date")) and str(rule.get("effective_date")) > candidate_date
            ),
            None,
        )
        if later_rule is None:
            continue
        rule_date = str(later_rule.get("effective_date"))
        hints.append(_hint(
            code="rules_first_table_embedded_effective_date",
            scope=f"table_{index + 1}_{rule_date}",
            category="effective_dates",
            severity="decision",
            title="Rules-first effective date check",
            message=(
                "This looks like a complete standard table, but the accepted "
                "uplift rules contain a later table-embedded/reform date."
            ),
            recommendation=(
                f"Use {rule_date} for the complete table unless the source table "
                "explicitly says all displayed rates applied earlier."
            ),
            confidence="medium",
            evidence=[
                f"Table {index + 1}: {table.get('table_title') or 'Untitled'}",
                f"Suggested/current date: {candidate_date}",
                _rule_evidence(later_rule),
            ],
            save_note=(
                f"Table {index + 1}: used {rule_date} because the uplift rule is "
                "table-embedded/reform; using the earlier date would bring later "
                "table rates forward too early."
            ),
            target={"table_index": index, "preferred_effective_from": rule_date},
        ))
    return hints


def _level_d_missing_hints(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated = [
        (str(table.get("effective_from") or ""), table)
        for table in tables
        if _iso_text(table.get("effective_from"))
    ]
    dated.sort(key=lambda item: item[0])
    hints: list[dict[str, Any]] = []

    for (prev_date, prev_table), (next_date, next_table) in zip(dated, dated[1:]):
        prev_by_band = _standard_levels_by_band(prev_table)
        next_by_band = _standard_levels_by_band(next_table)
        missing: list[str] = []
        for band, prev_levels in prev_by_band.items():
            if "D" not in prev_levels:
                continue
            next_levels = next_by_band.get(band, set())
            if "D" in next_levels:
                continue
            if next_levels.intersection({"A", "B", "C", "1", "2", "3"}):
                missing.append(f"Band {band} Level D")
        if not missing:
            continue
        hints.append(_hint(
            code="standard_level_d_missing",
            scope=f"{prev_date}_{next_date}",
            category="pay_table",
            severity="decision",
            title="Level D likely missing misprint",
            message=(
                "Level D exists in the previous period and the next period keeps "
                "neighbouring levels for the same band but omits D."
            ),
            recommendation=(
                "Treat the missing Level D as a likely table misprint and use "
                "computed values during scenario review unless the agreement "
                "clearly removed that level."
            ),
            confidence="medium",
            evidence=[
                f"Previous period: {prev_date}",
                f"Next period: {next_date}",
                f"Missing: {', '.join(missing[:6])}",
            ],
            save_note=(
                f"{next_date}: treated {', '.join(missing[:3])} as likely "
                "misprint because Level D existed in the prior period; use computed values."
            ),
            target={"period": next_date, "cells": missing},
        ))

    return hints


def _rate_cap_hint(scenario: dict[str, Any]) -> dict[str, Any]:
    period = str(scenario.get("period_effective_from") or "")
    pending = [
        dep for dep in scenario.get("external_deps") or []
        if isinstance(dep, dict) and dep.get("dep_status") == "pending"
    ]
    evidence = [f"Period: {period}" if period else ""]
    for dep in pending[:3]:
        evidence.append(
            f"{dep.get('dep_kind') or 'external dependency'} "
            f"{dep.get('financial_year') or ''}: pending"
        )
    if scenario.get("reason"):
        evidence.append(str(scenario.get("reason")))
    return _hint(
        code="scenario_rate_cap_pending",
        scope=period or "unknown",
        category="scenario",
        severity="warning",
        title="Future rate cap not resolved",
        message=(
            "This period depends on a future or unresolved external rate-cap factor."
        ),
        recommendation=(
            "Leave the affected future period unpromoted until the rate cap is "
            "confirmed, or record it as a working assumption only."
        ),
        confidence="high",
        evidence=evidence,
        save_note=(
            f"{period}: left unpromoted because the rate-cap factor is not "
            "available yet."
        ),
        target={"period": period},
    )


def _extract_uplift_rules(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    data = (((canonical.get("sections") or {}).get("uplift_rules") or {}).get("data") or {})
    paths = (
        ("accepted", "document", "rules"),
        ("accepted", "rules"),
        ("suggestion", "document", "rules"),
        ("rules",),
    )
    for path in paths:
        cursor: Any = data
        for key in path:
            if not isinstance(cursor, dict):
                cursor = None
                break
            cursor = cursor.get(key)
        if isinstance(cursor, list) and cursor:
            return [rule for rule in cursor if isinstance(rule, dict)]
    return []


def _overview_pay_pages(canonical: dict[str, Any]) -> list[int]:
    data = (((canonical.get("sections") or {}).get("overview") or {}).get("data") or {})
    return _normalise_pages(
        data.get("likely_pay_table_pages")
        or data.get("pay_table_pages")
        or data.get("candidate_pages")
        or []
    )


def _suggestion_by_index(suggestions: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, int):
            out[index] = item
    return out


def _standard_cells(table: dict[str, Any]) -> set[tuple[str, str]]:
    cells: set[tuple[str, str]] = set()
    for row in table.get("rows") or []:
        if not isinstance(row, dict) or not is_standard_band_level_row(row):
            continue
        key = standard_cell_key(row)
        if key is not None:
            cells.add(key)
    return cells


def _standard_levels_by_band(table: dict[str, Any]) -> dict[str, set[str]]:
    by_band: dict[str, set[str]] = defaultdict(set)
    for band, level in _standard_cells(table):
        by_band[band].add(level)
    return by_band


def _table_source_pages(table: dict[str, Any]) -> list[int]:
    values: list[Any] = []
    for key in ("source_pages", "pages"):
        raw = table.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw is not None:
            values.append(raw)
    for key in ("source_page", "page"):
        if table.get(key) is not None:
            values.append(table.get(key))
    source = table.get("source")
    if isinstance(source, dict):
        for key in ("source_pages", "pages"):
            raw = source.get(key)
            if isinstance(raw, list):
                values.extend(raw)
            elif raw is not None:
                values.append(raw)
        for key in ("source_page", "page"):
            if source.get(key) is not None:
                values.append(source.get(key))
    return _normalise_pages(values)


def _normalise_pages(values: Any) -> list[int]:
    if values is None:
        return []
    raw_values = values if isinstance(values, list) else [values]
    pages: set[int] = set()
    for value in raw_values:
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if page > 0:
            pages.add(page)
    return sorted(pages)


def _contiguous_runs(pages: list[int]) -> list[list[int]]:
    pages = sorted(set(pages))
    if not pages:
        return []
    runs: list[list[int]] = [[pages[0]]]
    for page in pages[1:]:
        if page == runs[-1][-1] + 1:
            runs[-1].append(page)
        else:
            runs.append([page])
    return runs


def _table_text(table: dict[str, Any]) -> str:
    parts = [
        table.get("table_title"),
        table.get("source_clause"),
        table.get("effective_from_note"),
        table.get("period_label_source"),
        table.get("rate_kind"),
    ]
    for row in table.get("rows") or []:
        if isinstance(row, dict):
            parts.extend(row.get(key) for key in ("title", "classification", "notes"))
    return " ".join(str(part or "") for part in parts).lower()


def _keyword_hits(text: str) -> list[str]:
    lowered = str(text or "").lower()
    return [term for term in NON_STANDARD_HINT_TERMS if term in lowered]


def _is_table_embedded_rule(rule: dict[str, Any]) -> bool:
    qtype = str(rule.get("quantum_type") or "").strip().lower()
    if qtype == "table_embedded":
        return True
    text = " ".join(
        str(rule.get(key) or "")
        for key in ("quantum", "quantum_resolution", "period_label", "timing_clause")
    ).lower()
    return "table embedded" in text or "table-embedded" in text


def _rule_has_future_factor(rule: dict[str, Any]) -> bool:
    qtype = str(rule.get("quantum_type") or "").strip().lower()
    if qtype in {"conditional", "pct_or_floor"}:
        return True
    text = " ".join(
        str(rule.get(key) or "")
        for key in (
            "quantum",
            "quantum_external_ref",
            "quantum_external_definition",
            "quantum_resolution",
            "timing_clause",
        )
    ).lower()
    return any(term in text for term in ("rate cap", "gazetted", "esc", "greater of", "lesser of"))


def _rule_evidence(rule: dict[str, Any]) -> str:
    label = str(rule.get("period_label") or "uplift rule")
    date = str(rule.get("effective_date") or "")
    qtype = str(rule.get("quantum_type") or "unknown")
    quantum = str(rule.get("quantum") or rule.get("quantum_resolution") or "").strip()
    tail = f": {quantum}" if quantum else ""
    return f"{label} {date} ({qtype}){tail}".strip()


def _agreement_operative_date(canonical: dict[str, Any]) -> str:
    sections = canonical.get("sections") or {}
    candidates = [
        ((sections.get("front_matter") or {}).get("data") or {}).get("operative_date"),
        ((sections.get("front_matter") or {}).get("data") or {}).get("effective_date"),
        ((sections.get("overview") or {}).get("data") or {}).get("operative_date"),
        ((sections.get("overview") or {}).get("data") or {}).get("effective_date"),
        canonical.get("operative_date"),
        canonical.get("effective_date"),
    ]
    for candidate in candidates:
        iso = _iso_text(candidate)
        if iso:
            return iso
    return ""


def _looks_like_prior_or_base_table(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        term in lowered
        for term in (
            "prior",
            "previous",
            "before agreement",
            "pre-agreement",
            "base table",
            "baseline",
            "commencing",
            "commencement",
            "sign off",
            "sign-off",
        )
    )


def _iso_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) != 10:
        return ""
    year, month, day = text[:4], text[5:7], text[8:]
    if text[4:5] != "-" or text[7:8] != "-":
        return ""
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return ""
    return text


def _scenario_deltas(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    deltas = scenario.get("cell_deltas") or []
    return [delta for delta in deltas if isinstance(delta, dict)]


def _scenario_missing_level_d_cells(scenario: dict[str, Any]) -> list[str]:
    deltas = _scenario_deltas(scenario)
    levels_by_band: dict[str, set[str]] = defaultdict(set)
    missing_d: set[str] = set()
    for delta in deltas:
        band = str(delta.get("band") or "")
        level = str(delta.get("level") or "").upper()
        if not band:
            continue
        if delta.get("actual_weekly") is not None:
            levels_by_band[band].add(level)
        if level == "D" and delta.get("prior_weekly") is not None and delta.get("actual_weekly") is None:
            missing_d.add(band)
    out: list[str] = []
    for band in sorted(missing_d):
        if levels_by_band[band].intersection({"A", "B", "C", "1", "2", "3"}):
            out.append(f"Band {band} Level D")
    return out


def _scenario_value_evidence(deltas: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for delta in deltas[:4]:
        band = delta.get("band")
        level = delta.get("level")
        actual = _format_money(delta.get("actual_weekly"))
        computed = _format_money(delta.get("computed_weekly"))
        prior = _format_money(delta.get("prior_weekly"))
        abs_delta = _format_money(delta.get("abs_delta"))
        pieces = [f"Band {band} Level {level}"]
        if prior:
            pieces.append(f"prior {prior}")
        if actual:
            pieces.append(f"printed {actual}")
        if computed:
            pieces.append(f"computed {computed}")
        if abs_delta:
            pieces.append(f"delta {abs_delta}")
        reason = delta.get("recommendation_reason")
        if reason:
            pieces.append(str(reason))
        evidence.append(": " + ", ".join(pieces) if not pieces else ", ".join(pieces))
    return evidence


def _format_money(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    return f"${numeric:,.2f}"


def _external_dep_pending(dep: Any) -> bool:
    return isinstance(dep, dict) and dep.get("dep_status") == "pending"


def _hint(
    *,
    code: str,
    scope: str,
    category: str,
    severity: str,
    title: str,
    message: str,
    recommendation: str,
    confidence: str,
    evidence: list[str],
    save_note: str,
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{code}:{scope}",
        "code": code,
        "category": category,
        "severity": severity,
        "title": title,
        "message": message,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence": [item for item in evidence if item],
        "save_note": save_note,
        "target": target or {},
    }


def _dedupe_hints(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for hint in hints:
        key = str(hint.get("id") or hint.get("code") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(hint)
    return out


__all__ = [
    "build_pay_table_review_hints",
    "build_scenario_review_hints",
]
