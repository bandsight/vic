from __future__ import annotations

from collections import Counter
import re
from typing import Any


QUALITY_STANDARD_MAX_SCORE = 1000

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONFIDENCE_WORDS = {
    "very high": 0.95,
    "high": 0.9,
    "medium": 0.7,
    "moderate": 0.65,
    "low": 0.45,
    "very low": 0.25,
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _is_iso_date(value: Any) -> bool:
    return bool(_ISO_DATE_RE.match(_clean_text(value)))


def _clamp_int(value: float | int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _normalise_confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in _CONFIDENCE_WORDS:
            return _CONFIDENCE_WORDS[clean]
        value = clean
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1:
        numeric = numeric / 100 if numeric <= 100 else 1
    return max(0.0, min(1.0, numeric))


def _collect_confidences(value: Any) -> list[float]:
    values: list[float] = []
    if isinstance(value, dict):
        if "confidence" in value:
            normalised = _normalise_confidence(value.get("confidence"))
            if normalised is not None:
                values.append(normalised)
        for nested in value.values():
            values.extend(_collect_confidences(nested))
    elif isinstance(value, list):
        for nested in value:
            values.extend(_collect_confidences(nested))
    return values


def _source_pages(table: dict[str, Any]) -> list[Any]:
    pages = table.get("source_pages")
    if isinstance(pages, list):
        return [page for page in pages if page not in (None, "")]
    page = table.get("source_page")
    return [page] if page not in (None, "") else []


def _collect_rule_dicts(value: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("effective_date") and (
            value.get("period_label")
            or value.get("quantum")
            or value.get("quantum_type")
            or value.get("confidence") is not None
        ):
            rules.append(value)
        for nested in value.values():
            rules.extend(_collect_rule_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            rules.extend(_collect_rule_dicts(nested))
    return rules


def _table_quality_summary(table: dict[str, Any]) -> dict[str, Any]:
    rows = _as_list(table.get("rows"))
    return {
        "table_title": table.get("table_title"),
        "effective_from": table.get("effective_from"),
        "effective_from_note": table.get("effective_from_note"),
        "source_page": table.get("source_page"),
        "source_pages": _source_pages(table),
        "source_clause": table.get("source_clause"),
        "rate_kind": table.get("rate_kind"),
        "row_count": len(rows),
        "source_date_raw": table.get("source_date_raw"),
        "source_date_iso": table.get("source_date_iso"),
        "canonical_date_iso": table.get("canonical_date_iso"),
        "date_snapped": bool(table.get("date_snapped")),
        "snap_basis": table.get("snap_basis"),
        "snap_note": table.get("snap_note"),
    }


def audit_quality_inputs(canonical: dict[str, Any]) -> dict[str, Any]:
    """Extract compact quality evidence from a canonical agreement."""

    canonical = _as_dict(canonical)
    sections = _as_dict(canonical.get("sections"))
    overview_section = _as_dict(sections.get("overview"))
    overview_data = _as_dict(overview_section.get("data"))
    overview_root = _as_dict(canonical.get("overview"))
    pay_section = _as_dict(sections.get("pay_tables"))
    uplift_section = _as_dict(sections.get("uplift_rules"))
    uplifts_section = _as_dict(sections.get("uplifts"))
    clauses_section = _as_dict(sections.get("clauses"))

    pay_tables = [
        _table_quality_summary(table)
        for table in _as_list(pay_section.get("tables"))
        if isinstance(table, dict)
    ]
    validations = [
        validation
        for validation in _as_list(pay_section.get("validations"))
        if isinstance(validation, dict)
    ]
    uplift_data = _as_dict(uplift_section.get("data"))
    uplift_rules = _collect_rule_dicts(uplift_data)
    governed_periods: list[dict[str, Any]] = []
    for period in _as_list(_as_dict(uplifts_section.get("data")).get("periods")):
        if not isinstance(period, dict):
            continue
        pay_table = period.get("pay_table") if isinstance(period.get("pay_table"), dict) else {}
        uplift_rule = period.get("uplift_rule") if isinstance(period.get("uplift_rule"), dict) else {}
        override_counts = _as_dict(pay_table.get("scenario_override_counts"))
        governed_periods.append({
            "effective_from": period.get("effective_from"),
            "has_pay_table": bool(pay_table),
            "has_uplift_rule": bool(uplift_rule),
            "pay_table_effective_from": pay_table.get("effective_from"),
            "uplift_rule_effective_date": uplift_rule.get("effective_date"),
            "pay_table_rows": len(_as_list(pay_table.get("rows"))),
            "source_rows_count": int(pay_table.get("source_rows_count") or 0),
            "standard_rows_count": int(pay_table.get("standard_rows_count") or 0),
            "excluded_rows_count": int(pay_table.get("excluded_rows_count") or 0),
            "scenario_override_count": sum(int(value or 0) for value in override_counts.values()),
            "pay_table_governed_at": period.get("pay_table_governed_at"),
            "uplift_rule_governed_at": period.get("uplift_rule_governed_at"),
        })

    confidence_values = (
        _collect_confidences(uplift_data)
        + _collect_confidences(_as_dict(clauses_section.get("data")))
        + _collect_confidences(_as_dict(canonical.get("conditions")))
    )
    pay_table_dates = sorted({
        _clean_text(table.get("effective_from"))
        for table in pay_tables
        if _clean_text(table.get("effective_from"))
    })
    uplift_rule_dates = sorted({
        _clean_text(rule.get("effective_date"))
        for rule in uplift_rules
        if _clean_text(rule.get("effective_date"))
    })
    governed_dates = sorted({
        _clean_text(period.get("effective_from"))
        for period in governed_periods
        if _clean_text(period.get("effective_from"))
    })

    return {
        "overview": {
            "generated_at": overview_root.get("generated_at") or overview_section.get("completed_at"),
            "page_count": overview_root.get("page_count") or overview_data.get("page_count"),
            "likely_pay_table_pages": overview_root.get("likely_pay_table_pages") or overview_data.get("likely_pay_table_pages") or [],
            "likely_uplift_pages": overview_root.get("likely_uplift_pages") or overview_data.get("likely_uplift_pages") or [],
            "red_flags": overview_root.get("red_flags") or [],
            "document_structure_notes": overview_root.get("document_structure_notes") or "",
        },
        "pay_tables": pay_tables,
        "pay_table_dates": pay_table_dates,
        "pay_table_validations": validations,
        "uplift_rules": [
            {
                "period_label": rule.get("period_label"),
                "effective_date": rule.get("effective_date"),
                "source_page": rule.get("source_page"),
                "confidence": rule.get("confidence"),
                "quantum_type": rule.get("quantum_type"),
            }
            for rule in uplift_rules
        ],
        "uplift_rule_dates": uplift_rule_dates,
        "governed_periods": governed_periods,
        "governed_dates": governed_dates,
        "confidence_values": confidence_values,
    }


def _rating(score: int) -> str:
    if score >= 900:
        return "Excellent"
    if score >= 800:
        return "Strong"
    if score >= 650:
        return "Needs review"
    if score >= 500:
        return "Fragile"
    return "Incomplete"


def _status(score: int, max_score: int) -> str:
    ratio = score / max_score if max_score else 0
    if ratio >= 0.9:
        return "excellent"
    if ratio >= 0.8:
        return "strong"
    if ratio >= 0.65:
        return "needs_review"
    if ratio >= 0.5:
        return "fragile"
    return "incomplete"


def _measure(key: str, label: str, score: int, max_score: int, signals: list[str], penalties: list[str]) -> dict[str, Any]:
    clipped = _clamp_int(score, 0, max_score)
    return {
        "key": key,
        "label": label,
        "score": clipped,
        "max_score": max_score,
        "status": _status(clipped, max_score),
        "signals": [signal for signal in signals if signal],
        "penalties": [penalty for penalty in penalties if penalty],
    }


def _source_structure_measure(lineage: dict[str, Any], workspace: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    score = 0
    signals: list[str] = []
    penalties: list[str] = []
    overview = _as_dict(inputs.get("overview"))
    fetch_metadata = _as_dict(workspace.get("fetch_metadata"))

    if lineage.get("source_ready"):
        score += 40
        signals.append("Fetched source evidence is registered.")
    else:
        penalties.append("No fetched source evidence is registered.")

    source_status = _clean_text(lineage.get("source_status"))
    serviceability = _clean_text(lineage.get("serviceability_status"))
    if source_status or serviceability:
        score += 20
        signals.append("Source status and serviceability are recorded.")
    else:
        penalties.append("Source status/serviceability fields are blank.")

    if lineage.get("source_size_bytes"):
        score += 10
    else:
        penalties.append("Source file size is missing.")
    if lineage.get("content_hash"):
        score += 10
    else:
        penalties.append("Source content hash is missing.")
    if lineage.get("source_origin"):
        score += 5

    identity_points = 0
    if lineage.get("ae_id") and (lineage.get("title") or workspace.get("source_name")):
        identity_points += 8
    if lineage.get("operative_date"):
        identity_points += 7
    if lineage.get("expiry_date"):
        identity_points += 5
    if lineage.get("matched_lgas") or workspace.get("canonical_lga_short_name") or fetch_metadata.get("lga_short_name"):
        identity_points += 5
    score += identity_points
    if identity_points < 20:
        penalties.append("Agreement identity, date or council fields are incomplete.")

    overview_points = 0
    if overview.get("generated_at") or overview.get("page_count"):
        overview_points += 12
    if overview.get("page_count"):
        overview_points += 8
    if overview.get("likely_pay_table_pages"):
        overview_points += 5
    if overview.get("likely_uplift_pages"):
        overview_points += 5
    score += overview_points
    if overview_points >= 20:
        signals.append("Overview structure includes page and likely evidence-page signals.")
    else:
        penalties.append("Overview structure signals are incomplete.")

    red_flags = _as_list(overview.get("red_flags"))
    if red_flags:
        penalty = min(15, len(red_flags) * 5)
        score -= penalty
        penalties.append(f"{len(red_flags)} overview red flag(s) recorded.")

    return _measure(
        "source_structure",
        "Source structure",
        score,
        150,
        signals,
        penalties,
    )


def _confidence_measure(workspace: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    values = [
        value
        for value in _as_list(inputs.get("confidence_values"))
        if isinstance(value, (int, float))
    ]
    signals: list[str] = []
    penalties: list[str] = []
    if not values:
        fallback = 25 if workspace.get("done_count") else 0
        return _measure(
            "confidence_numbers",
            "Confidence numbers",
            fallback,
            150,
            ["Workspace review exists, but no confidence fields were found."] if fallback else [],
            ["No extraction confidence values were found."],
        )

    average = sum(values) / len(values)
    minimum = min(values)
    low_count = sum(1 for value in values if value < 0.7)
    score = round((average * 95) + (minimum * 35) + (min(1.0, len(values) / 8) * 20))
    signals.append(f"{len(values)} confidence value(s), average {average:.0%}.")
    signals.append(f"Lowest confidence {minimum:.0%}.")
    if low_count:
        score -= min(30, low_count * 4)
        penalties.append(f"{low_count} confidence value(s) below 70%.")
    return _measure(
        "confidence_numbers",
        "Confidence numbers",
        score,
        150,
        signals,
        penalties,
    )


def _table_rule_agreement_measure(workspace: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    pay_dates = set(str(value) for value in _as_list(inputs.get("pay_table_dates")) if value)
    rule_dates = set(str(value) for value in _as_list(inputs.get("uplift_rule_dates")) if value)
    governed_periods = [
        period for period in _as_list(inputs.get("governed_periods"))
        if isinstance(period, dict)
    ]
    governed_summary = _as_dict(workspace.get("governed"))
    signals: list[str] = []
    penalties: list[str] = []
    score = 0

    upstream_union = pay_dates | rule_dates
    if upstream_union:
        overlap = len(pay_dates & rule_dates)
        score += round(55 * overlap / len(upstream_union))
        signals.append(f"{overlap} of {len(upstream_union)} upstream effective date(s) have both table and rule evidence.")
    else:
        penalties.append("No upstream pay-table or uplift-rule dates were found.")

    governed_entities = [
        period for period in governed_periods
        if period.get("has_pay_table") or period.get("has_uplift_rule")
    ]
    paired = [
        period for period in governed_entities
        if period.get("has_pay_table") and period.get("has_uplift_rule")
    ]
    if governed_entities:
        score += round(80 * len(paired) / len(governed_entities))
        signals.append(f"{len(paired)} of {len(governed_entities)} governed period(s) carry both pay table and uplift rule.")
    else:
        penalties.append("No governed table/rule periods were found.")

    pay_rows = int(governed_summary.get("pay_table_rows") or 0)
    if pay_rows:
        score += 15
        signals.append(f"{pay_rows} governed pay-table row(s) are available.")
    else:
        penalties.append("No governed pay-table rows are available.")

    source_rows = sum(int(period.get("source_rows_count") or 0) for period in governed_periods)
    standard_rows = sum(int(period.get("standard_rows_count") or 0) for period in governed_periods)
    if source_rows:
        score += round(15 * standard_rows / source_rows)
        excluded = source_rows - standard_rows
        if excluded:
            penalties.append(f"{excluded} source row(s) were excluded from governed standard rows.")
    elif pay_rows:
        score += 8

    mismatches = 0
    for period in governed_periods:
        effective_from = _clean_text(period.get("effective_from"))
        pay_effective = _clean_text(period.get("pay_table_effective_from"))
        rule_effective = _clean_text(period.get("uplift_rule_effective_date"))
        if pay_effective and effective_from and pay_effective != effective_from:
            mismatches += 1
        if rule_effective and effective_from and rule_effective != effective_from:
            mismatches += 1
    score += max(0, 30 - (mismatches * 8))
    if mismatches:
        penalties.append(f"{mismatches} governed period date mismatch(es) between table/rule evidence.")
    else:
        signals.append("Governed period dates agree with promoted table/rule dates.")

    return _measure(
        "table_rule_agreement",
        "Table-rule agreement",
        score,
        180,
        signals,
        penalties,
    )


def _date_alignment_measure(inputs: dict[str, Any]) -> dict[str, Any]:
    tables = [
        table for table in _as_list(inputs.get("pay_tables"))
        if isinstance(table, dict)
    ]
    validations = [
        validation for validation in _as_list(inputs.get("pay_table_validations"))
        if isinstance(validation, dict)
    ]
    governed_periods = [
        period for period in _as_list(inputs.get("governed_periods"))
        if isinstance(period, dict)
    ]
    signals: list[str] = []
    penalties: list[str] = []
    score = 0

    if tables:
        iso_tables = sum(1 for table in tables if _is_iso_date(table.get("effective_from")))
        score += round(45 * iso_tables / len(tables))
        signals.append(f"{iso_tables} of {len(tables)} pay table(s) have ISO effective dates.")
        snapped = sum(1 for table in tables if table.get("date_snapped"))
        aligned = sum(
            1 for table in tables
            if _is_iso_date(table.get("effective_from"))
            and (
                not table.get("canonical_date_iso")
                or _clean_text(table.get("canonical_date_iso")) == _clean_text(table.get("effective_from"))
            )
        )
        snap_penalty = min(8, snapped * 2)
        score += max(0, round(35 * aligned / len(tables)) - snap_penalty)
        if snapped:
            penalties.append(f"{snapped} table date(s) required snapping.")
    else:
        penalties.append("No pay tables were available for date alignment checks.")

    date_validations = [
        validation for validation in validations
        if any(token in _clean_text(validation.get("code")).lower() for token in ("date", "effective", "expiry"))
    ]
    penalty = 0
    for validation in date_validations:
        level = _clean_text(validation.get("level")).lower()
        penalty += 15 if level == "error" else 8 if level == "warning" else 3
    score += max(0, 35 - min(35, penalty))
    if date_validations:
        penalties.append(f"{len(date_validations)} date validation item(s) are recorded.")
    else:
        signals.append("No date validation warnings are recorded.")

    if governed_periods:
        consistent = 0
        for period in governed_periods:
            effective_from = _clean_text(period.get("effective_from"))
            pay_effective = _clean_text(period.get("pay_table_effective_from"))
            rule_effective = _clean_text(period.get("uplift_rule_effective_date"))
            if not _is_iso_date(effective_from):
                continue
            if pay_effective and pay_effective != effective_from:
                continue
            if rule_effective and rule_effective != effective_from:
                continue
            consistent += 1
        score += round(35 * consistent / len(governed_periods))
        signals.append(f"{consistent} of {len(governed_periods)} governed period date(s) are internally aligned.")
    else:
        penalties.append("No governed periods were available for date alignment.")

    return _measure(
        "date_alignment",
        "Date alignment",
        score,
        150,
        signals,
        penalties,
    )


def _qa_change_burden_measure(workspace: dict[str, Any]) -> dict[str, Any]:
    qa_events = _as_dict(workspace.get("qa_events"))
    events = [
        event for event in (_as_list(qa_events.get("pay_tables")) + _as_list(qa_events.get("scenarios")))
        if isinstance(event, dict)
    ]
    counts = Counter(_clean_text(event.get("event_type")) for event in events)
    row_treatment = _as_dict(workspace.get("row_level_treatment"))
    penalty_weights = {
        "pay_table_added": 12,
        "pay_table_removed": 12,
        "pay_table_date_changed": 10,
        "pay_table_cell_value_changed": 5,
        "pay_table_row_added": 8,
        "pay_table_row_removed": 8,
        "pay_table_note_updated": 2,
        "pay_table_source_ref_updated": 2,
        "scenario_cell_override_added": 4,
        "scenario_cell_override_changed": 4,
        "scenario_cell_override_removed": 2,
        "scenario_group_override_applied": 4,
        "scenario_note_updated": 1,
        "scenario_overrides_cleared": 2,
    }
    penalty = sum(count * penalty_weights.get(event_type, 3) for event_type, count in counts.items())
    non_standard_rows = int(row_treatment.get("non_standard_row_count") or 0)
    penalty += min(18, non_standard_rows * 3)

    signals: list[str] = []
    penalties: list[str] = []
    if events:
        signals.append(f"{len(events)} reviewer change(s) recorded.")
        major = [
            f"{count} {event_type.replace('_', ' ')}"
            for event_type, count in counts.most_common(4)
            if event_type
        ]
        if major:
            penalties.append("Change burden: " + ", ".join(major) + ".")
    else:
        signals.append("No reviewer changes were required or recorded.")
    if non_standard_rows:
        penalties.append(f"{non_standard_rows} non-standard row-level item(s) required treatment.")

    return _measure(
        "qa_change_burden",
        "QA change burden",
        140 - penalty,
        140,
        signals,
        penalties,
    )


def _governed_pipeline_measure(workspace: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    governed = _as_dict(workspace.get("governed"))
    governed_periods = [
        period for period in _as_list(inputs.get("governed_periods"))
        if isinstance(period, dict)
    ]
    row_treatment = _as_dict(workspace.get("row_level_treatment"))
    signals: list[str] = []
    penalties: list[str] = []
    score = 0

    done_count = int(workspace.get("done_count") or 0)
    total_sections = int(workspace.get("total_sections") or 0)
    if total_sections:
        score += round(60 * done_count / total_sections)
        signals.append(f"{done_count} of {total_sections} workspace section(s) are complete.")
    else:
        penalties.append("Workspace review section count is missing.")

    governed_entities = [
        period for period in governed_periods
        if period.get("has_pay_table") or period.get("has_uplift_rule")
    ]
    paired = [
        period for period in governed_entities
        if period.get("has_pay_table") and period.get("has_uplift_rule")
    ]
    if governed_entities:
        score += round(80 * len(paired) / len(governed_entities))
    elif governed.get("periods"):
        score += 20
    else:
        penalties.append("No governed periods have been promoted.")

    pay_periods = int(governed.get("pay_table_periods") or 0)
    rule_periods = int(governed.get("uplift_rule_periods") or 0)
    if pay_periods and governed.get("pay_table_governed_at"):
        score += 20
    elif pay_periods:
        score += 10
    else:
        penalties.append("No governed pay-table promotion stamp is available.")
    if rule_periods and governed.get("uplift_rule_governed_at"):
        score += 20
    elif rule_periods:
        score += 10
    else:
        penalties.append("No governed uplift-rule promotion stamp is available.")

    status = _clean_text(governed.get("governed_set_status")).lower()
    if status == "done":
        score += 25
        signals.append("Governed set status is done.")
    elif status in {"in_progress", "flagged"}:
        score += 15
        penalties.append(f"Governed set status is {status.replace('_', ' ')}.")
    elif governed.get("periods"):
        score += 8
    else:
        penalties.append("Governed set status has not started.")

    treatment_status = _clean_text(row_treatment.get("status")).lower()
    if treatment_status == "not_detected":
        score += 25
    elif treatment_status == "present":
        score += 18
        signals.append("Non-standard row treatment has been identified and isolated.")
    elif treatment_status == "not_assessed" and not pay_periods:
        score += 8
    else:
        penalties.append("Row-level treatment is not fully assessed.")

    return _measure(
        "governed_pipeline",
        "Governed pipeline",
        score,
        230,
        signals,
        penalties,
    )


def _agreement_quality_score(lineage: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    inputs = _as_dict(workspace.get("quality_inputs"))
    measures = [
        _source_structure_measure(lineage, workspace, inputs),
        _confidence_measure(workspace, inputs),
        _table_rule_agreement_measure(workspace, inputs),
        _date_alignment_measure(inputs),
        _qa_change_burden_measure(workspace),
        _governed_pipeline_measure(workspace, inputs),
    ]
    score = sum(int(measure["score"]) for measure in measures)
    max_score = sum(int(measure["max_score"]) for measure in measures)
    score = _clamp_int(score, 0, QUALITY_STANDARD_MAX_SCORE)
    return {
        "ae_id": lineage.get("ae_id") or workspace.get("ae_id"),
        "title": lineage.get("title") or workspace.get("source_name") or lineage.get("ae_id") or workspace.get("ae_id"),
        "score": score,
        "max_score": max_score,
        "rating": _rating(score),
        "status": _status(score, max_score),
        "measures": measures,
        "summary": _agreement_summary(score, measures),
    }


def _agreement_summary(score: int, measures: list[dict[str, Any]]) -> str:
    strongest = max(measures, key=lambda item: item["score"] / item["max_score"])
    weakest = min(measures, key=lambda item: item["score"] / item["max_score"])
    return (
        f"{_rating(score)} quality standard. Strongest measure: {strongest['label']} "
        f"({strongest['score']}/{strongest['max_score']}); review focus: {weakest['label']} "
        f"({weakest['score']}/{weakest['max_score']})."
    )


def _aggregate_measures(agreements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not agreements:
        return []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for agreement in agreements:
        for measure in agreement.get("measures") or []:
            if isinstance(measure, dict):
                by_key.setdefault(str(measure.get("key")), []).append(measure)
    aggregated: list[dict[str, Any]] = []
    for key, items in by_key.items():
        max_score = int(items[0].get("max_score") or 0)
        score = round(sum(int(item.get("score") or 0) for item in items) / len(items))
        label = str(items[0].get("label") or key)
        aggregated.append(_measure(
            key,
            label,
            score,
            max_score,
            [f"Average across {len(items)} agreement score(s)."],
            [],
        ))
    return sorted(aggregated, key=lambda item: item["key"])


def build_quality_standard(lineage: list[dict[str, Any]], workspace_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a council-level and per-agreement quality score out of 1000."""

    ordered_ids: list[str] = []
    lineage_by_id: dict[str, dict[str, Any]] = {}
    normalised_workspaces = {
        _clean_text(ae_id).lower(): workspace
        for ae_id, workspace in workspace_by_id.items()
        if _clean_text(ae_id)
    }
    for row in lineage:
        if not isinstance(row, dict):
            continue
        ae_id = _clean_text(row.get("ae_id")).lower()
        if not ae_id:
            continue
        lineage_by_id[ae_id] = row
        if ae_id not in ordered_ids:
            ordered_ids.append(ae_id)
    for ae_id in normalised_workspaces:
        if ae_id and ae_id not in ordered_ids:
            ordered_ids.append(ae_id)

    agreements = [
        _agreement_quality_score(
            lineage_by_id.get(ae_id, {"ae_id": ae_id}),
            normalised_workspaces.get(ae_id) or {"ae_id": ae_id},
        )
        for ae_id in ordered_ids
    ]
    measures = _aggregate_measures(agreements)
    score = sum(int(measure.get("score") or 0) for measure in measures) if measures else 0
    score = _clamp_int(score, 0, QUALITY_STANDARD_MAX_SCORE)
    weakest = min(measures, key=lambda item: item["score"] / item["max_score"]) if measures else None
    return {
        "score": score,
        "max_score": QUALITY_STANDARD_MAX_SCORE,
        "rating": _rating(score),
        "status": _status(score, QUALITY_STANDARD_MAX_SCORE),
        "agreement_count": len(agreements),
        "aggregation": "average_of_agreement_scores",
        "summary": (
            f"{_rating(score)} council quality standard across {len(agreements)} agreement(s). "
            f"Main review focus: {weakest['label']} ({weakest['score']}/{weakest['max_score']})."
            if weakest
            else "No agreement quality evidence is available."
        ),
        "measures": measures,
        "agreements": agreements,
    }
