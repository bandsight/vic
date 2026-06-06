"""Scenario testing engine — read-only comparison of uplift rules vs pay tables."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
import re
from typing import Any, Optional

from benchmarking_data_factory.scenario_testing.schema import (
    CellDelta,
    ExternalDep,
    ScenarioResult,
)
from benchmarking_data_factory.scenario_testing.normalise import cell_key, row_to_weekly

TOLERANCE = 0.001  # 0.1%
RULE_DATE_MATCH_WINDOW_DAYS = 30  # Fuzzy-match window for rule.effective_date vs table period.
_LGA_STOP_WORDS = {"city", "shire", "rural", "council", "borough"}


def _lga_name_parts(value: str | None) -> tuple[str, ...]:
    raw = str(value or "").lower()
    return tuple(
        part for part in re.split(r"[^a-z0-9]+", raw)
        if len(part) >= 3 and part not in _LGA_STOP_WORDS
    )


def _table_text(table: dict) -> str:
    parts: list[Any] = [
        table.get("table_title"),
        table.get("source_clause"),
        table.get("effective_from_note"),
        table.get("period_label_source"),
    ]
    for row in table.get("rows") or []:
        if isinstance(row, dict):
            parts.extend([row.get("title"), row.get("classification"), row.get("notes")])
    return " ".join(str(part or "") for part in parts).lower()


def _multi_council_names(canonical: dict) -> tuple[str, ...]:
    text = " ".join(
        str(part or "")
        for part in (
            canonical.get("source_name"),
            canonical.get("title"),
            canonical.get("name"),
            (canonical.get("overview") or {}).get("source_name") if isinstance(canonical.get("overview"), dict) else "",
            (canonical.get("overview") or {}).get("document_structure_notes") if isinstance(canonical.get("overview"), dict) else "",
        )
    )
    names = [
        match.group(1).strip()
        for match in re.finditer(
            r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3})\s+(?:Rural\s+City\s+Council|City\s+Council|Shire\s+Council|Borough\s+Council)\b",
            text,
        )
    ]
    return tuple(dict.fromkeys(names))


def _filter_tables_by_council(tables: list[dict], lga_short_name: str | None, canonical: dict) -> list[dict]:
    """Keep split-agreement scenario baselines inside the active council.

    The rule extractor can identify council-specific uplift rules, but pay table
    appendices may contain another employer's full timeline. If those foreign
    tables are left in the period order, the engine can accidentally compare a
    Central Goldfields table against an Ararat baseline and report a false wage
    mismatch.
    """
    active_parts = _lga_name_parts(lga_short_name)
    if not active_parts:
        return tables
    council_names = _multi_council_names(canonical)
    foreign_parts = tuple(
        part
        for name in council_names
        if not any(active in _lga_name_parts(name) for active in active_parts)
        for part in _lga_name_parts(name)
    )
    if not foreign_parts:
        return tables

    current: list[dict] = []
    unmarked: list[dict] = []
    for table in tables:
        text = _table_text(table)
        if any(part in text for part in active_parts):
            current.append(table)
        elif any(part in text for part in foreign_parts):
            continue
        else:
            unmarked.append(table)
    filtered = [*current, *unmarked]
    return filtered or tables


def run_scenarios(
    canonical: dict,
    overrides: dict[str, dict[str, dict]] | None = None,
    lga_short_name: str | None = None,
) -> tuple[ScenarioResult, ...]:
    """Run scenario testing for every period in an agreement.

    Input: the parsed canonical YAML dict for one agreement (e.g. ae521669.yaml loaded).
    Output: one ScenarioResult per distinct period effective_from (earliest first).
    """
    ae_id = canonical.get("agreement_id", "")
    sections = canonical.get("sections", {}) or {}
    pay_tables_section = sections.get("pay_tables", {}) or {}
    uplift_rules_section = sections.get("uplift_rules", {}) or {}

    tables = pay_tables_section.get("tables") or []
    tables = _filter_tables_by_council(tables, lga_short_name, canonical)
    rules = _extract_rules(uplift_rules_section)
    rules = _filter_rules_by_council(rules, lga_short_name)

    blockers = []
    if pay_tables_section.get("status") != "done":
        blockers.append(f"pay_tables={pay_tables_section.get('status')!r}")
    if not tables:
        blockers.append("no pay tables in canonical")
    if not rules:
        blockers.append("no uplift rules to test")
    if blockers:
        return (
            ScenarioResult(
                ae_id=ae_id,
                period_effective_from="",
                period_label="",
                status="blocked",
                sub_status="",
                reason="Cannot run scenarios: " + "; ".join(blockers),
                rule_id=None,
                rule_quantum=None,
                prior_period_effective_from=None,
                table_names=(),
                cell_deltas=(),
                external_deps=(),
            ),
        )

    from collections import defaultdict
    tables_by_period: dict[str, list[dict]] = defaultdict(list)
    for t in tables:
        eff = t.get("effective_from") or ""
        if eff:
            tables_by_period[eff].append(t)

    ordered_periods = sorted(tables_by_period.keys())
    if not ordered_periods:
        return ()

    results: list[ScenarioResult] = []
    prior_weekly_by_cell: dict[tuple[str, str], float] = {}
    prior_period = ""

    for idx, period in enumerate(ordered_periods):
        _pending_external_deps: tuple[ExternalDep, ...] = ()
        period_tables = tables_by_period[period]
        table_names = tuple(t.get("table_title", "") for t in period_tables)

        current_weekly_by_cell: dict[tuple[str, str], float] = {}
        has_any_weekly_equivalent = False
        for t in period_tables:
            for r in t.get("rows") or []:
                key = cell_key(r)
                if key is None:
                    continue
                weekly = row_to_weekly(r)
                if weekly is None:
                    continue
                has_any_weekly_equivalent = True
                current_weekly_by_cell[key] = weekly

        original_weekly_by_cell = dict(current_weekly_by_cell)

        period_overrides: dict[str, dict] = (overrides or {}).get(period, {})
        for cell_str, ov in period_overrides.items():
            parts = cell_str.split(":", 1)
            if len(parts) != 2:
                continue
            key = (parts[0], parts[1])
            action = ov.get("action")
            if action == "use_computed" and ov.get("weekly") is not None:
                current_weekly_by_cell[key] = float(ov["weekly"])
            elif action == "deleted":
                current_weekly_by_cell.pop(key, None)

        if idx == 0:
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"Baseline ({period})",
                    status="baseline",
                    sub_status="",
                    reason="First period of agreement; no scenario applies.",
                    rule_id=None,
                    rule_quantum=None,
                    prior_period_effective_from=None,
                    table_names=table_names,
                    cell_deltas=tuple(
                        CellDelta(
                            band=key[0],
                            level=key[1],
                            prior_weekly=None,
                            computed_weekly=None,
                            actual_weekly=weekly,
                            abs_delta=None,
                            pct_delta=None,
                            within_tolerance=True,
                        )
                        for key, weekly in sorted(current_weekly_by_cell.items())
                    ),
                    external_deps=(),
                )
            )
            prior_weekly_by_cell = current_weekly_by_cell
            prior_period = period
            continue

        if not has_any_weekly_equivalent:
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"{period}",
                    status="needs_attention",
                    sub_status="no_weekly_equivalent",
                    reason="No weekly/annual/fortnightly rates available to normalise.",
                    rule_id=None,
                    rule_quantum=None,
                    prior_period_effective_from=prior_period,
                    table_names=table_names,
                    cell_deltas=(),
                    external_deps=(),
                )
            )
            prior_period = period
            continue

        rule = _find_rule_for_period(rules, period)

        if rule is None:
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"{period}",
                    status="needs_attention",
                    sub_status="table_only",
                    reason="Table exists for this period but no uplift rule covers it.",
                    rule_id=None,
                    rule_quantum=None,
                    prior_period_effective_from=prior_period,
                    table_names=table_names,
                    cell_deltas=(),
                    external_deps=(),
                )
            )
            prior_weekly_by_cell = current_weekly_by_cell
            prior_period = period
            continue

        fuzzy_days: Optional[int] = None
        rule_eff = rule.get("effective_date")
        if isinstance(rule_eff, str) and rule_eff != period:
            rd = _parse_iso_date(rule_eff)
            pd = _parse_iso_date(period)
            if rd is not None and pd is not None:
                fuzzy_days = (rd - pd).days

        qtype = rule.get("quantum_type", "unknown")
        if qtype in ("conditional", "pct_OR_floor"):
            from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (
                RateCapResolutionError,
                classify_rate_cap_mode,
                date_to_financial_year,
                get_year_status_row,
                resolve_effective_rate,
            )

            quantum_str = rule.get("quantum") or ""
            external_ref = rule.get("quantum_external_ref") or ""
            cap_mode = classify_rate_cap_mode(quantum_str, external_ref)

            if cap_mode != "no_rate_cap_ref":
                try:
                    fy = date_to_financial_year(period)
                except RateCapResolutionError:
                    fy = None

                year_row = get_year_status_row(fy) if fy else None
                year_status = year_row.get("resolution_status") if year_row else "unknown"
                confirmed_at = year_row.get("confirmed_date") if year_row else None

                dep = ExternalDep(
                    dep_key=f"vic_gazetted_cap:{fy}" if fy else "vic_gazetted_cap:unknown",
                    dep_kind="rate_cap",
                    financial_year=fy or "",
                    dep_status="confirmed" if year_status == "confirmed" else "pending",
                    confirmed_at=confirmed_at if year_status == "confirmed" and confirmed_at else None,
                )

                if year_status == "confirmed" and lga_short_name and fy:
                    try:
                        resolution = resolve_effective_rate(lga_short_name, fy, quantum_str, external_ref)
                    except RateCapResolutionError:
                        resolution = None

                    effective_rate = resolution["effective_rate"] if resolution else None
                    if effective_rate is not None:
                        dep = ExternalDep(
                            dep_key=f"vic_gazetted_cap:{fy}" if fy else "vic_gazetted_cap:unknown",
                            dep_kind="rate_cap",
                            financial_year=fy or "",
                            dep_status="confirmed",
                            confirmed_at=confirmed_at if confirmed_at else None,
                            raw_rate_cap=resolution.get("raw_rate_cap"),
                            effective_rate=effective_rate,
                            resolution_note=resolution.get("resolution_note"),
                        )
                        resolved_rule = dict(rule)
                        resolved_rule["quantum_type"] = "percentage"
                        resolved_rule["quantum"] = f"{effective_rate:.4f}%"
                        resolved_rule["_rate_cap_resolution"] = resolution
                        # Clear quantum_external_ref so the awaiting_input check
                        # below does not fire after a successful rate cap resolution.
                        resolved_rule.pop("quantum_external_ref", None)
                        rule = resolved_rule
                        qtype = "percentage"
                        _pending_external_deps = (dep,)
                    else:
                        if has_any_weekly_equivalent:
                            results.append(
                                ScenarioResult(
                                    ae_id=ae_id,
                                    period_effective_from=period,
                                    period_label=f"{period}",
                                    status="table_resolved",
                                    sub_status="rate_cap_pending",
                                    reason=_annotate_reason(
                                        f"Conditional rule references rate cap; mechanical resolution failed (confirmed FY {fy}).",
                                        fuzzy_days,
                                    ),
                                    rule_id=_rule_id(rule),
                                    rule_quantum=rule.get("quantum"),
                                    prior_period_effective_from=prior_period,
                                    table_names=table_names,
                                    cell_deltas=_build_table_resolved_deltas(
                                        current_weekly_by_cell, prior_weekly_by_cell
                                    ),
                                    external_deps=(dep,),
                                )
                            )
                            prior_weekly_by_cell = current_weekly_by_cell
                            prior_period = period
                            continue
                elif year_status == "confirmed" and not lga_short_name:
                    if has_any_weekly_equivalent:
                        results.append(
                            ScenarioResult(
                                ae_id=ae_id,
                                period_effective_from=period,
                                period_label=f"{period}",
                                status="table_resolved",
                                sub_status="missing_lga_context",
                                reason=_annotate_reason(
                                    "Rate-cap dependent rule requires lga_short_name; harness did not pass it.",
                                    fuzzy_days,
                                ),
                                rule_id=_rule_id(rule),
                                rule_quantum=rule.get("quantum"),
                                prior_period_effective_from=prior_period,
                                table_names=table_names,
                                cell_deltas=_build_table_resolved_deltas(
                                    current_weekly_by_cell, prior_weekly_by_cell
                                ),
                                external_deps=(dep,),
                            )
                        )
                        prior_weekly_by_cell = current_weekly_by_cell
                        prior_period = period
                        continue
                elif year_status != "confirmed" and has_any_weekly_equivalent:
                    results.append(
                        ScenarioResult(
                            ae_id=ae_id,
                            period_effective_from=period,
                            period_label=f"{period}",
                            status="table_resolved",
                            sub_status="rate_cap_pending",
                            reason=_annotate_reason(
                                f"Rate cap for FY {fy or 'unknown'} is {year_status}; using published tables as working assumption.",
                                fuzzy_days,
                            ),
                            rule_id=_rule_id(rule),
                            rule_quantum=rule.get("quantum"),
                            prior_period_effective_from=prior_period,
                            table_names=table_names,
                            cell_deltas=_build_table_resolved_deltas(
                                current_weekly_by_cell, prior_weekly_by_cell
                            ),
                            external_deps=(dep,),
                        )
                    )
                    prior_weekly_by_cell = current_weekly_by_cell
                    prior_period = period
                    continue

        if qtype == "table_embedded" and has_any_weekly_equivalent:
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"{period}",
                    status="table_resolved",
                    sub_status="table_embedded",
                    reason=_annotate_reason(
                        "Rule is table-embedded; published pay table is the governing source for this period.",
                        fuzzy_days,
                    ),
                    rule_id=_rule_id(rule),
                    rule_quantum=rule.get("quantum"),
                    prior_period_effective_from=prior_period,
                    table_names=table_names,
                    cell_deltas=_build_table_resolved_deltas(
                        current_weekly_by_cell, prior_weekly_by_cell
                    ),
                    external_deps=(),
                )
            )
            prior_weekly_by_cell = current_weekly_by_cell
            prior_period = period
            continue

        if qtype in ("conditional", "table_embedded", "unknown"):
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"{period}",
                    status="needs_attention",
                    sub_status="ambiguous_rule",
                    reason=_annotate_reason(f"Rule quantum_type={qtype!r} is not mechanisable in v1.", fuzzy_days),
                    rule_id=_rule_id(rule),
                    rule_quantum=rule.get("quantum"),
                    prior_period_effective_from=prior_period,
                    table_names=table_names,
                    cell_deltas=(),
                    external_deps=(),
                )
            )
            prior_weekly_by_cell = current_weekly_by_cell
            prior_period = period
            continue

        ext_ref = rule.get("quantum_external_ref")
        resolution = rule.get("quantum_resolution")
        if ext_ref and not resolution:
            results.append(
                ScenarioResult(
                    ae_id=ae_id,
                    period_effective_from=period,
                    period_label=f"{period}",
                    status="awaiting_input",
                    sub_status="",
                    reason=_annotate_reason(f"Rule references external input ({ext_ref!r}) with no resolution yet.", fuzzy_days),
                    rule_id=_rule_id(rule),
                    rule_quantum=rule.get("quantum"),
                    prior_period_effective_from=prior_period,
                    table_names=table_names,
                    cell_deltas=(),
                    external_deps=(),
                )
            )
            prior_weekly_by_cell = current_weekly_by_cell
            prior_period = period
            continue

        computed_by_cell = _apply_rule(rule, prior_weekly_by_cell)

        deltas: list[CellDelta] = []
        all_within = True
        any_covered = False
        any_uncovered = False
        for key, actual in current_weekly_by_cell.items():
            cell_str = f"{key[0]}:{key[1]}"
            cell_ov = period_overrides.get(cell_str)
            ov_action: str | None = cell_ov.get("action") if cell_ov else None
            prior = prior_weekly_by_cell.get(key)
            computed = computed_by_cell.get(key)
            if prior is None or computed is None:
                within = False
                if ov_action == "accept":
                    within = True
                if not within:
                    any_uncovered = True
                    all_within = False
                deltas.append(
                    CellDelta(
                        band=key[0],
                        level=key[1],
                        prior_weekly=prior,
                        computed_weekly=computed,
                        actual_weekly=actual,
                        abs_delta=None,
                        pct_delta=None,
                        within_tolerance=within,
                        override_action=ov_action,
                    )
                )
                continue
            any_covered = True
            abs_delta = abs(computed - actual)
            pct_delta = abs_delta / actual if actual else None
            within = pct_delta is not None and pct_delta <= TOLERANCE
            if ov_action == "accept":
                within = True
            if not within:
                all_within = False
            deltas.append(
                CellDelta(
                    band=key[0],
                    level=key[1],
                    prior_weekly=prior,
                    computed_weekly=computed,
                    actual_weekly=actual,
                    abs_delta=abs_delta,
                    pct_delta=pct_delta,
                    within_tolerance=within,
                    override_action=ov_action,
                )
            )

        existing_keys = {(d.band, d.level) for d in deltas}
        for cell_str, ov in period_overrides.items():
            if ov.get("action") != "deleted":
                continue
            parts = cell_str.split(":", 1)
            if len(parts) != 2:
                continue
            key = (parts[0], parts[1])
            if key in existing_keys:
                continue
            if key not in original_weekly_by_cell:
                continue
            deltas.append(CellDelta(
                band=key[0],
                level=key[1],
                prior_weekly=prior_weekly_by_cell.get(key),
                computed_weekly=None,
                actual_weekly=original_weekly_by_cell[key],
                abs_delta=None,
                pct_delta=None,
                within_tolerance=True,
                override_action="deleted",
            ))

        if any_uncovered and any_covered:
            status = "needs_attention"
            sub = "partial_rule"
            reason = "Rule covers some but not all cells in the period's tables."
        elif not any_covered:
            status = "needs_attention"
            sub = "partial_rule"
            reason = "Rule did not cover any cells in the period's tables."
        elif all_within:
            status = "consistent"
            sub = ""
            reason = "All cells match rule application within 0.1% tolerance."
        else:
            status = "needs_attention"
            sub = "conflict"
            reason = "One or more cells exceed 0.1% tolerance between rule-computed and extracted."

        decision_recommendation = None
        if status == "needs_attention" and sub in {"conflict", "partial_rule"}:
            decision_recommendation = _conflict_decision_recommendation(
                rule,
                deltas,
                _pending_external_deps,
            )
            if decision_recommendation and decision_recommendation.get("action") == "use_computed":
                deltas = _apply_delta_recommendation(deltas, decision_recommendation)

        result_deltas = tuple(deltas)
        results.append(
            ScenarioResult(
                ae_id=ae_id,
                period_effective_from=period,
                period_label=f"{period}",
                status=status,
                sub_status=sub,
                reason=_annotate_reason(reason, fuzzy_days),
                rule_id=_rule_id(rule),
                rule_quantum=rule.get("quantum"),
                prior_period_effective_from=prior_period,
                table_names=table_names,
                cell_deltas=result_deltas,
                external_deps=_pending_external_deps,
                decision_recommendation=decision_recommendation,
            )
        )

        prior_weekly_by_cell = _downstream_prior_with_recommendations(
            current_weekly_by_cell,
            result_deltas,
            decision_recommendation,
        )
        prior_period = period

    return tuple(results)


def _downstream_prior_with_recommendations(
    current_weekly_by_cell: dict[tuple[str, str], float],
    deltas: tuple[CellDelta, ...],
    decision_recommendation: Optional[dict[str, Any]],
) -> dict[tuple[str, str], float]:
    """Preview downstream periods using computed values the backend recommends.

    This does not mark the current period resolved. It only prevents later
    periods from being projected from rows the engine already believes should be
    superseded by computed values, such as confirmed rate-cap estimates.
    """
    next_prior = dict(current_weekly_by_cell)
    if not decision_recommendation or decision_recommendation.get("action") != "use_computed":
        return next_prior
    for delta in deltas:
        if delta.recommended_action != "use_computed" or delta.computed_weekly is None:
            continue
        next_prior[(str(delta.band), str(delta.level))] = float(delta.computed_weekly)
    return next_prior


def _extract_rules(uplift_rules_section: dict) -> tuple:
    """Locate the rules list in a canonical uplift_rules section.

    Canonical layouts we accept, in priority order:
      1. data.accepted.document.rules  (user-accepted snapshot; document wrapper preserved)
      2. data.suggestion.document.rules
      3. data.rules
    First non-empty list wins. Returns an empty tuple if none are populated.
    """
    data = uplift_rules_section.get("data") or {}
    accepted = data.get("accepted") or {}
    if isinstance(accepted, dict):
        document = accepted.get("document") or {}
        if isinstance(document, dict):
            r = document.get("rules")
            if r:
                return tuple(r)
    suggestion = data.get("suggestion") or {}
    if isinstance(suggestion, dict):
        document = suggestion.get("document") or {}
        if isinstance(document, dict):
            r = document.get("rules")
            if r:
                return tuple(r)
    r = data.get("rules")
    if r:
        return tuple(r)
    return ()


def _filter_rules_by_council(rules: tuple, lga_short_name: str | None) -> tuple:
    """For multi-employer agreements, narrow the rule set to the relevant council.

    A multi-employer agreement has rules whose period_label contains the council
    name (e.g. "Year 1 – Ararat Rural City Council").  When lga_short_name
    matches any such label we filter to only those rules so ARCC rules don't
    contaminate CGSC scenario matching and vice versa.

    For single-employer agreements (period_labels like "Year 1" with no council
    name embedded) no rules will match the filter check and the full set is
    returned unchanged.
    """
    if not lga_short_name:
        return rules
    needle = lga_short_name.lower()
    matched = tuple(
        r for r in rules
        if isinstance(r, dict) and needle in (r.get("period_label") or "").lower()
    )
    return matched if matched else rules


def _find_rule_for_period(rules: tuple, period: str) -> Optional[dict]:
    exact_matches = [
        r for r in rules
        if isinstance(r, dict) and r.get("effective_date") == period
    ]
    if exact_matches:
        return _combine_period_rules(exact_matches)

    period_d = _parse_iso_date(period)
    if period_d is None:
        return None
    best_matches: list[dict] = []
    best_distance: Optional[int] = None
    best_rule_date: Optional[date] = None
    for r in rules:
        if not isinstance(r, dict):
            continue
        rd = _parse_iso_date(r.get("effective_date"))
        if rd is None:
            continue
        distance = abs((rd - period_d).days)
        if distance > RULE_DATE_MATCH_WINDOW_DAYS:
            continue
        if (
            not best_matches
            or distance < best_distance
            or (distance == best_distance and rd < best_rule_date)
        ):
            best_matches = [r]
            best_distance = distance
            best_rule_date = rd
        elif distance == best_distance and rd == best_rule_date:
            best_matches.append(r)
    return _combine_period_rules(best_matches) if best_matches else None


def _combine_period_rules(matches: list[dict]) -> Optional[dict]:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    general_matches = [item for item in matches if not _is_specialised_rule(item)]
    if general_matches:
        matches = general_matches
    if len(matches) == 1:
        return matches[0]

    def sort_key(item: dict) -> tuple[int, str]:
        qtype = item.get("quantum_type", "unknown")
        order = {"flat": 0, "percentage": 1, "pct_OR_floor": 1}.get(qtype, 9)
        return (order, str(item.get("period_label") or ""))

    ordered = sorted(matches, key=sort_key)
    if any(item.get("quantum_type") not in {"flat", "percentage", "pct_OR_floor"} for item in ordered):
        return matches[0]

    base = dict(ordered[-1])
    base["period_label"] = " + ".join(str(item.get("period_label") or "") for item in ordered if item.get("period_label"))
    base["quantum"] = " then ".join(str(item.get("quantum") or "") for item in ordered if item.get("quantum"))
    base["quantum_type"] = "sequence"
    base["_sequence"] = tuple(dict(item) for item in ordered)
    base["quantum_resolution"] = "Sequential same-date uplift rules applied in order."
    return base


def _is_specialised_rule(rule: dict[str, Any]) -> bool:
    label = str(rule.get("period_label") or "")
    quantum = str(rule.get("quantum") or "")
    text = f"{label} {quantum}".lower()
    return bool(
        re.search(
            r"\bmchn\b|\bmaternal\b|\bchild health\b|\bnurse\b|\bnursing\b|\blibrary\b|\bpool\b|\bleisure\b|\bschool crossing\b",
            text,
        )
    )


def _parse_iso_date(value) -> Optional[date]:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _rule_id(rule: dict) -> str:
    return f"{rule.get('effective_date', '')}::{rule.get('period_label', '')}"


def _apply_rule(rule: dict, prior_by_cell: dict) -> dict:
    qtype = rule.get("quantum_type", "unknown")
    quantum_str = rule.get("quantum") or ""

    if qtype == "sequence":
        current = dict(prior_by_cell)
        for step in rule.get("_sequence") or ():
            current = _apply_rule(step, current)
            if not current:
                return {}
        return current

    if qtype == "percentage":
        pct = _parse_percentage(quantum_str, rule)
        if pct is None:
            return {}
        dollar_floor = (rule.get("_rate_cap_resolution") or {}).get("dollar_floor_per_week")
        if dollar_floor is not None:
            return {k: max(v * (1 + pct / 100.0), v + dollar_floor) for k, v in prior_by_cell.items()}
        return {k: v * (1 + pct / 100.0) for k, v in prior_by_cell.items()}

    if qtype == "flat":
        return _apply_flat_rule(rule, prior_by_cell)

    if qtype == "pct_OR_floor":
        pct = _parse_percentage(quantum_str, rule)
        floor = _parse_flat(rule.get("quantum_floor") or "", rule)
        if floor is None and "$" in str(quantum_str):
            floor = _parse_flat(quantum_str, rule)
        if pct is None and floor is None:
            return {}
        result = {}
        for k, v in prior_by_cell.items():
            pct_val = v * (1 + pct / 100.0) if pct is not None else None
            flat_val = v + floor if floor is not None else None
            candidates = [x for x in (pct_val, flat_val) if x is not None]
            if not candidates:
                continue
            result[k] = max(candidates)
        return result

    return {}


def _apply_flat_rule(rule: dict, prior_by_cell: dict) -> dict:
    quantum_str = rule.get("quantum") or ""
    band_amounts = _parse_band_flat_amounts(quantum_str)
    if band_amounts:
        result = {}
        for key, value in prior_by_cell.items():
            band = _band_number(key[0])
            flat = band_amounts.get(band)
            if flat is not None:
                result[key] = value + flat
        if result:
            return result

    flat = _parse_flat(quantum_str, rule)
    if flat is None:
        return {}
    return {k: v + flat for k, v in prior_by_cell.items()}


def _band_number(value: str) -> int | None:
    import re
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def _parse_band_flat_amounts(text: str) -> dict[int, float]:
    import re
    amounts: dict[int, float] = {}
    for segment in str(text or "").split(";"):
        dollar_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", segment)
        band_match = re.search(
            r"\bbands?\s+(\d+)(?:\s*(?:-|to|–|—)\s*(\d+))?",
            segment,
            flags=re.IGNORECASE,
        )
        if not dollar_match or not band_match:
            continue
        start = int(band_match.group(1))
        end = int(band_match.group(2) or start)
        if end < start:
            start, end = end, start
        for band in range(start, end + 1):
            amounts[band] = float(dollar_match.group(1))
    return amounts


def _parse_percentage(text: str, rule: dict) -> Optional[float]:
    import re
    if text is None:
        return None
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text))
    if percent_match:
        try:
            return float(percent_match.group(1))
        except ValueError:
            return None
    cleaned = str(text).strip().rstrip("%").strip()
    try:
        return float(cleaned)
    except ValueError:
        m = re.search(r"(\d+\.?\d*)", str(text))
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None


def _parse_flat(text: str, rule: dict) -> Optional[float]:
    import re
    if text is None:
        return None
    dollar_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", str(text))
    if dollar_match:
        try:
            return float(dollar_match.group(1))
        except ValueError:
            return None
    cleaned = str(text).strip().lstrip("$").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        m = re.search(r"(\d+\.?\d*)", str(text))
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None



def _build_table_resolved_deltas(
    current_weekly_by_cell: dict[tuple[str, str], float],
    prior_weekly_by_cell: dict[tuple[str, str], float],
) -> tuple[CellDelta, ...]:
    """Build cell deltas for a table_resolved result: show prior→actual, computed unknown."""
    deltas: list[CellDelta] = []
    all_keys = set(current_weekly_by_cell.keys()) | set(prior_weekly_by_cell.keys())
    for key in sorted(all_keys):
        deltas.append(
            CellDelta(
                band=key[0],
                level=key[1],
                prior_weekly=prior_weekly_by_cell.get(key),
                computed_weekly=None,
                actual_weekly=current_weekly_by_cell.get(key),
                abs_delta=None,
                pct_delta=None,
                within_tolerance=True,
            )
        )
    return tuple(deltas)

def _conflict_decision_recommendation(
    rule: dict[str, Any],
    deltas: list[CellDelta],
    external_deps: tuple[ExternalDep, ...],
) -> dict[str, Any] | None:
    covered = [
        delta for delta in deltas
        if delta.prior_weekly is not None
        and delta.computed_weekly is not None
        and delta.override_action != "deleted"
    ]
    variance_cells = [
        delta for delta in covered
        if not delta.within_tolerance and delta.computed_weekly is not None
    ]
    if not variance_cells:
        return None

    introduced_cells = [
        delta for delta in deltas
        if delta.prior_weekly is None
        and delta.computed_weekly is None
        and delta.actual_weekly is not None
        and delta.override_action not in {"accept", "deleted"}
    ]
    failed_count = len(variance_cells)
    covered_count = len(covered)
    variance_ratio = failed_count / covered_count if covered_count else 0
    no_increase_recommendation = _isolated_no_increase_recommendation(
        variance_cells,
        failed_count,
        covered_count,
        variance_ratio,
    )
    if no_increase_recommendation:
        return no_increase_recommendation
    stale_prior_recommendation = _systemic_stale_prior_recommendation(
        rule,
        variance_cells,
        failed_count,
        covered_count,
        variance_ratio,
    )
    if stale_prior_recommendation:
        return stale_prior_recommendation

    confirmed_external = [
        dep for dep in external_deps
        if dep.dep_status == "confirmed" and dep.dep_kind in {"rate_cap"}
    ]

    if not confirmed_external:
        rule_extraction_recommendation = _systemic_rule_extraction_recommendation(
            rule,
            variance_cells,
            failed_count,
            covered_count,
            variance_ratio,
        )
        if rule_extraction_recommendation:
            return rule_extraction_recommendation
        return {
            "action": "needs_human_review",
            "basis": "unexplained_variance",
            "confidence": "low",
            "affected_cells": failed_count,
            "covered_cells": covered_count,
            "reason": (
                "Variance exceeds tolerance but the engine has no confirmed rate cap "
                "or external dependency explaining the difference."
            ),
        }

    if failed_count < 2:
        return {
            "action": "needs_human_review",
            "basis": "isolated_variance_with_external_dependency",
            "fallback_action": "use_computed",
            "confidence": "medium",
            "affected_cells": failed_count,
            "covered_cells": covered_count,
            "external_deps": [dep.dep_key for dep in confirmed_external],
            "reason": (
                "Confirmed external dependency is present, but the variance is isolated "
                "to one row; review downstream impact before choosing computed or table value."
            ),
        }

    rate_notes = [
        dep.resolution_note for dep in confirmed_external
        if dep.resolution_note
    ]
    reason = (
        "Confirmed rate-cap or external dependency explains a multi-cell variance; "
        "policy recommends using computed values for the variance cells."
    )
    if rate_notes:
        reason = f"{reason} {' '.join(rate_notes)}"

    return {
        "action": "use_computed",
        "basis": "confirmed_external_dependency_multi_cell_variance",
        "confidence": "high",
        "affected_cells": failed_count,
        "covered_cells": covered_count,
        "introduced_cells": len(introduced_cells),
        "introduced_action": "accept_table" if introduced_cells else None,
        "variance_ratio": round(variance_ratio, 4),
        "external_deps": [dep.dep_key for dep in confirmed_external],
        "rule_quantum": rule.get("quantum"),
        "reason": reason,
    }


def _systemic_rule_extraction_recommendation(
    rule: dict[str, Any],
    variance_cells: list[CellDelta],
    failed_count: int,
    covered_count: int,
    variance_ratio: float,
) -> dict[str, Any] | None:
    if failed_count < 2 or variance_ratio < 0.8:
        return None
    offsets = [
        float(delta.actual_weekly) - float(delta.computed_weekly)
        for delta in variance_cells
        if delta.actual_weekly is not None and delta.computed_weekly is not None
    ]
    if len(offsets) == failed_count and max(offsets) - min(offsets) <= 0.05 and abs(offsets[0]) > 0.01:
        consistent_offset = round(sum(offsets) / len(offsets), 2)
    else:
        consistent_offset = None
    actual_increases = [
        float(delta.actual_weekly) - float(delta.prior_weekly)
        for delta in variance_cells
        if delta.actual_weekly is not None and delta.prior_weekly is not None
    ]
    computed_increases = [
        float(delta.computed_weekly) - float(delta.prior_weekly)
        for delta in variance_cells
        if delta.computed_weekly is not None and delta.prior_weekly is not None
    ]
    if (
        len(actual_increases) == failed_count
        and max(actual_increases) - min(actual_increases) <= 0.05
    ):
        implied_weekly_increase = round(sum(actual_increases) / len(actual_increases), 2)
    else:
        implied_weekly_increase = None
    if (
        len(computed_increases) == failed_count
        and max(computed_increases) - min(computed_increases) <= 0.05
    ):
        mechanised_weekly_increase = round(sum(computed_increases) / len(computed_increases), 2)
    else:
        mechanised_weekly_increase = None
    reason = (
        "The published table differs systemically from the mechanised rule and no "
        "confirmed external dependency explains a computed override. Treat this as "
        "a likely uplift-rule extraction, table-family, or effective-date binding "
        "defect before scenario acceptance or governed promotion."
    )
    if consistent_offset is not None:
        reason = (
            "The published table differs from the mechanised rule by a consistent "
            "multi-cell offset and no confirmed external dependency explains a "
            "computed override. Treat this as a likely uplift-rule extraction, "
            "table-family, or effective-date binding defect before scenario "
            "acceptance or governed promotion."
        )
    return {
        "action": "needs_rule_extraction_review",
        "basis": "extracted_rule_conflicts_with_published_table_pattern",
        "confidence": "high" if consistent_offset is not None else "medium",
        "affected_cells": failed_count,
        "covered_cells": covered_count,
        "variance_ratio": round(variance_ratio, 4),
        "rule_quantum": rule.get("quantum"),
        "implied_weekly_increase": implied_weekly_increase,
        "mechanised_weekly_increase": mechanised_weekly_increase,
        "consistent_offset": consistent_offset,
        "reason": reason,
    }


def _systemic_stale_prior_recommendation(
    rule: dict[str, Any],
    variance_cells: list[CellDelta],
    failed_count: int,
    covered_count: int,
    variance_ratio: float,
) -> dict[str, Any] | None:
    if failed_count < 2 or variance_ratio < 0.8:
        return None
    carried_forward = all(
        delta.prior_weekly is not None
        and delta.actual_weekly is not None
        and abs(delta.actual_weekly - delta.prior_weekly) <= 0.01
        and delta.computed_weekly is not None
        and abs(delta.computed_weekly - delta.prior_weekly) > 0.01
        for delta in variance_cells
    )
    if not carried_forward:
        return None
    return {
        "action": "use_computed",
        "basis": "systemic_stale_prior_table_values",
        "confidence": "high",
        "affected_cells": failed_count,
        "covered_cells": covered_count,
        "variance_ratio": round(variance_ratio, 4),
        "rule_quantum": rule.get("quantum"),
        "reason": (
            "The target table repeats prior-period values across the period while "
            "the accepted uplift rule produces a non-zero increase. Policy treats "
            "this as a stale extraction/table-copy issue and recommends computed values."
        ),
    }


def _isolated_no_increase_recommendation(
    variance_cells: list[CellDelta],
    failed_count: int,
    covered_count: int,
    variance_ratio: float,
) -> dict[str, Any] | None:
    if failed_count > 3 or variance_ratio > 0.15:
        return None
    if not variance_cells:
        return None
    carried_forward = all(
        delta.prior_weekly is not None
        and delta.actual_weekly is not None
        and abs(delta.actual_weekly - delta.prior_weekly) <= 0.01
        for delta in variance_cells
    )
    if not carried_forward:
        return None
    return {
        "action": "use_computed",
        "basis": "isolated_no_increase_rows_against_mechanised_rule",
        "confidence": "medium",
        "affected_cells": failed_count,
        "covered_cells": covered_count,
        "variance_ratio": round(variance_ratio, 4),
        "reason": (
            "A small number of rows carried forward unchanged while the mechanised rule "
            "moves the comparable table. Policy recommends computed values because these "
            "isolated prior-period errors affect downstream projections."
        ),
    }


def _apply_delta_recommendation(
    deltas: list[CellDelta],
    recommendation: dict[str, Any],
) -> list[CellDelta]:
    reason = str(recommendation.get("reason") or "")
    basis = str(recommendation.get("basis") or "")
    return [
        replace(
            delta,
            recommended_action="use_computed",
            recommendation_reason=reason,
            recommendation_basis=basis,
        )
        if not delta.within_tolerance and delta.computed_weekly is not None
        and recommendation.get("action") == "use_computed"
        else replace(
            delta,
            recommended_action="accept_table",
            recommendation_reason=(
                f"{reason} Introduced rows without a prior-period equivalent should retain the published table value unless there is evidence of a misprint."
            ),
            recommendation_basis=f"{basis}_introduced_row",
        )
        if recommendation.get("introduced_action") == "accept_table"
        and delta.prior_weekly is None
        and delta.computed_weekly is None
        and delta.actual_weekly is not None
        and delta.override_action not in {"accept", "deleted"}
        else delta
        for delta in deltas
    ]


def _annotate_reason(base: str, fuzzy_days: Optional[int]) -> str:
    if fuzzy_days is None or fuzzy_days == 0:
        return base
    direction = "after" if fuzzy_days > 0 else "before"
    return f"[matched rule {abs(fuzzy_days)}d {direction} period] {base}"
