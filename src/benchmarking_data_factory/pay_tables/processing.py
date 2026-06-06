from __future__ import annotations

from collections import defaultdict
from datetime import date
import re
from typing import Any, Literal

from benchmarking_data_factory.scenario_testing.normalise import (
    is_standard_band_level_row,
    standard_cell_key,
)


PAY_TABLE_EXTRACTION_RATE_PRIORITY = {
    "weekly": 0,
    "annual": 1,
    "fortnightly": 2,
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_RULE_DATE_SNAP_DAYS = 92


def parse_iso_date(value: Any) -> str | None:
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            date.fromisoformat(s)
            return s
        except ValueError:
            return None
    return None


def prepare_source_date_fields(table: dict[str, Any]) -> str | None:
    if "source_date_raw" not in table:
        table["source_date_raw"] = table.get("effective_from")

    source_iso = parse_iso_date(table.get("source_date_iso"))
    if source_iso is None:
        source_iso = parse_iso_date(table.get("source_date_raw"))
    if source_iso is None:
        source_iso = parse_iso_date(table.get("effective_from"))

    table["source_date_iso"] = source_iso
    return source_iso


def nearest_rule_date(source_iso: str, rule_dates: list[date], *, max_days: int = MAX_RULE_DATE_SNAP_DAYS) -> tuple[str | None, str | None]:
    source_date = date.fromisoformat(source_iso)
    candidates = sorted(
        ((abs((rd - source_date).days), rd) for rd in rule_dates),
        key=lambda x: (x[0], x[1].isoformat()),
    )
    if not candidates:
        return None, None
    best_delta, best_date = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best_delta:
        return None, (
            f"source date {source_iso} is equidistant to uplift rule dates "
            f"{best_date.isoformat()} and {candidates[1][1].isoformat()}"
        )
    if best_delta > max_days:
        return None, f"nearest uplift rule date is {best_delta} days away, beyond the {max_days}-day snap guard"
    return best_date.isoformat(), None


def _year_header_rule_dates(
    prepared: list[tuple[int, dict[str, Any], str | None]],
    rule_dates: list[date],
) -> dict[int, date]:
    """Detect year-labelled appendix tables that should align to same-year rules.

    Some pay appendices put columns/tables under simple year headings ("2024",
    "2025", "2026"). Extraction normalises those to YYYY-01-01, but the
    operative uplift date may be later in that same year. When a sequence of
    year-start tables matches a sequence of rule years, same-year alignment is
    more faithful than nearest-date snapping.
    """
    source_years = {
        date.fromisoformat(source_iso).year
        for _, _, source_iso in prepared
        if source_iso and date.fromisoformat(source_iso).month == 1 and date.fromisoformat(source_iso).day == 1
    }
    rules_by_year: dict[int, list[date]] = defaultdict(list)
    for rule_date in rule_dates:
        rules_by_year[rule_date.year].append(rule_date)
    if len(source_years) < 2:
        return {}
    overlap = source_years & set(rules_by_year)
    if len(overlap) < 2:
        return {}
    return {
        year: dates[0]
        for year, dates in rules_by_year.items()
        if len(dates) == 1 and year in overlap
    }


def apply_timeline_policy_to_tables(
    tables: list[dict[str, Any]],
    timeline_policy: Literal["current", "rule_anchored"],
    uplift_rule_dates: list[str] | None,
) -> dict[str, Any]:
    prepared: list[tuple[int, dict[str, Any], str | None]] = []
    for idx, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        source_iso = prepare_source_date_fields(table)
        prepared.append((idx, table, source_iso))

    def _set_current_metadata(note: str | None = None) -> None:
        for _, table, source_iso in prepared:
            canonical_iso = parse_iso_date(table.get("effective_from")) or source_iso
            table["canonical_date_iso"] = canonical_iso
            table["date_snapped"] = False
            table["snap_basis"] = None
            table["snap_note"] = note

    if timeline_policy == "current":
        _set_current_metadata(note="timeline_policy=current")
        return {
            "timeline_policy": timeline_policy,
            "timeline_policy_status": "current_behaviour",
            "timeline_policy_issue": None,
        }

    parsed_rule_dates = sorted(
        {
            date.fromisoformat(s)
            for s in (parse_iso_date(d) for d in (uplift_rule_dates or []))
            if s is not None
        }
    )

    if not parsed_rule_dates:
        issue = "no uplift rule effective_date values available for rule_anchored mapping"
        _set_current_metadata(note=f"rule_anchored fallback: {issue}")
        return {
            "timeline_policy": timeline_policy,
            "timeline_policy_status": "fallback_current_behaviour",
            "timeline_policy_issue": issue,
            }

    year_header_rules = _year_header_rule_dates(prepared, parsed_rule_dates)

    for idx, _, source_iso in prepared:
        if not source_iso:
            continue
        source_date = date.fromisoformat(source_iso)
        if (
            year_header_rules
            and source_date.month == 1
            and source_date.day == 1
            and source_date.year in year_header_rules
        ):
            continue
        _, tie_issue = nearest_rule_date(source_iso, parsed_rule_dates)
        if tie_issue and "equidistant" in tie_issue:
            issue = f"table_idx={idx}: {tie_issue}"
            _set_current_metadata(note=f"rule_anchored fallback: {issue}")
            return {
                "timeline_policy": timeline_policy,
                "timeline_policy_status": "fallback_current_behaviour",
                "timeline_policy_issue": issue,
            }

    for _, table, source_iso in prepared:
        if not source_iso:
            table["canonical_date_iso"] = parse_iso_date(table.get("effective_from"))
            table["date_snapped"] = False
            table["snap_basis"] = None
            table["snap_note"] = "No source ISO effective_from available; left unchanged"
            continue

        source_date = date.fromisoformat(source_iso)
        same_year_rule = (
            year_header_rules.get(source_date.year)
            if source_date.month == 1 and source_date.day == 1
            else None
        )
        if same_year_rule is not None:
            canonical_iso = same_year_rule.isoformat()
            snap_issue = None
            snap_basis = "uplift_rule_year_header"
        else:
            nearest_iso, snap_issue = nearest_rule_date(source_iso, parsed_rule_dates)
            canonical_iso = nearest_iso or source_iso
            snap_basis = "uplift_rule_event"
        did_snap = canonical_iso != source_iso

        table["canonical_date_iso"] = canonical_iso
        table["date_snapped"] = did_snap
        table["snap_basis"] = snap_basis if did_snap else None
        table["snap_note"] = (
            f"Snapped year-labelled table {source_iso} to same-year uplift rule date {canonical_iso}"
            if did_snap and snap_basis == "uplift_rule_year_header"
            else f"Snapped {source_iso} to uplift rule date {canonical_iso}"
            if did_snap
            else snap_issue or "Already aligned to uplift rule date"
        )
        table["effective_from"] = canonical_iso

    return {
        "timeline_policy": timeline_policy,
        "timeline_policy_status": "rule_anchored_applied",
        "timeline_policy_issue": None,
    }


def recalc_to_dates(
    tables: list[dict[str, Any]],
    nominated_expiry: str | None,
    uplift_rule_dates: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Recompute to_date on each table within each rate_kind group."""

    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for table in tables:
        ef = (table.get("effective_from") or "").strip()
        kind = (table.get("rate_kind") or "").strip() or "__unknown__"
        if ef:
            groups[kind].append((ef, table))

    def add_one_year(iso: str) -> str:
        d = date.fromisoformat(iso)
        try:
            return d.replace(year=d.year + 1).isoformat()
        except ValueError:
            return d.replace(year=d.year + 1, day=28).isoformat()

    def minus_one_day(iso: str) -> str:
        d = date.fromisoformat(iso)
        return (d.fromordinal(d.toordinal() - 1)).isoformat()

    for items in groups.values():
        items.sort(key=lambda x: x[0])
        for i, (ef, table) in enumerate(items):
            if i < len(items) - 1:
                next_ef = items[i + 1][0]
                if next_ef == ef:
                    table["to_date"] = None
                else:
                    try:
                        table["to_date"] = minus_one_day(next_ef)
                    except ValueError:
                        table["to_date"] = None
            else:
                try:
                    rule_boundary: str | None = None
                    if uplift_rule_dates:
                        future_rule_dates = sorted(d for d in uplift_rule_dates if d > ef)
                        if future_rule_dates:
                            rule_boundary = minus_one_day(future_rule_dates[0])
                    if rule_boundary:
                        table["to_date"] = rule_boundary
                    elif nominated_expiry:
                        table["to_date"] = nominated_expiry
                    else:
                        table["to_date"] = add_one_year(ef)
                except ValueError:
                    table["to_date"] = None
    return tables


def validate_pay_tables(tables: list[dict[str, Any]], nominated_expiry: str | None = None) -> list[dict[str, Any]]:
    validations: list[dict[str, Any]] = []
    for ti, table in enumerate(tables):
        rows = table.get("rows", []) or []
        if not rows:
            validations.append({
                "level": "error",
                "code": "no_rows",
                "message": "Table has zero rows",
                "table_idx": ti,
                "row_idx": None,
            })
            continue
        non_standard_rows = [
            ri for ri, row in enumerate(rows)
            if isinstance(row, dict) and not is_standard_band_level_row(row)
        ]
        if non_standard_rows:
            preview = ", ".join(str(idx) for idx in non_standard_rows[:8])
            suffix = "" if len(non_standard_rows) <= 8 else f" plus {len(non_standard_rows) - 8} more"
            validations.append({
                "level": "warning",
                "code": "non_standard_band_level_rows",
                "message": (
                    f"{len(non_standard_rows)} row(s) are outside the standard numeric band / level matrix "
                    f"and will be excluded from governed benchmark outputs: rows {preview}{suffix}"
                ),
                "table_idx": ti,
                "row_idx": None,
            })
        seen_standard_cells: dict[tuple[str, str], int] = {}
        for ri, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            standard_key = standard_cell_key(row)
            if standard_key is None:
                continue
            if standard_key in seen_standard_cells:
                validations.append({
                    "level": "warning",
                    "code": "duplicate_standard_band_level",
                    "message": (
                        f"Rows {seen_standard_cells[standard_key]} and {ri} both map to "
                        f"Band {standard_key[0]} Level {standard_key[1]}"
                    ),
                    "table_idx": ti,
                    "row_idx": ri,
                })
            else:
                seen_standard_cells[standard_key] = ri
        if not table.get("effective_from"):
            validations.append({
                "level": "warning",
                "code": "missing_effective_date",
                "message": "Table has no effective_from",
                "table_idx": ti,
                "row_idx": None,
            })
        prev_weekly = None
        for ri, row in enumerate(rows):
            w = row.get("weekly_rate")
            a = row.get("annual_rate")
            h = row.get("hourly_rate")
            f = row.get("fortnightly_rate")
            if w is not None and not (800 <= w <= 3500):
                validations.append({
                    "level": "warning",
                    "code": "out_of_range_weekly",
                    "message": f"weekly_rate {w} outside plausible $800-$3500",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if a is not None and not (40000 <= a <= 180000):
                validations.append({
                    "level": "warning",
                    "code": "out_of_range_annual",
                    "message": f"annual_rate {a} outside plausible $40k-$180k",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if h is not None and not (20 <= h <= 100):
                validations.append({
                    "level": "warning",
                    "code": "out_of_range_hourly",
                    "message": f"hourly_rate {h} outside plausible $20-$100",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if h is not None and w is None and a is None and f is None:
                validations.append({
                    "level": "warning",
                    "code": "hourly_only",
                    "message": "Row has hourly_rate but no weekly/annual/fortnightly; suspect incomplete extraction.",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if f is not None and w is None and a is None:
                validations.append({
                    "level": "warning",
                    "code": "fortnightly_only",
                    "message": "Row has fortnightly but no weekly/annual; suspect a specialised pay table that needs reviewer confirmation.",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if w is not None and a is not None and a > 0:
                ratio_off = abs(a - w * 52) / a
                if ratio_off > 0.02:
                    validations.append({
                        "level": "info",
                        "code": "annual_weekly_mismatch",
                        "message": f"annual/weekly ratio off by {ratio_off:.1%}",
                        "table_idx": ti,
                        "row_idx": ri,
                    })
            if prev_weekly is not None and w is not None and w < prev_weekly:
                validations.append({
                    "level": "warning",
                    "code": "monotonicity_break",
                    "message": f"weekly_rate {w} < previous row {prev_weekly}",
                    "table_idx": ti,
                    "row_idx": ri,
                })
            if w is not None:
                prev_weekly = w

    for i, table in enumerate(tables):
        ef = (table.get("effective_from") or "").strip()
        if not ef:
            validations.append({
                "level": "warning",
                "code": "missing_effective_from",
                "message": f"Table {i}: effective_from is blank",
            })

    seen: dict[tuple[str, str], int] = {}
    for i, table in enumerate(tables):
        ef = (table.get("effective_from") or "").strip()
        kind = (table.get("rate_kind") or "").strip() or "__unknown__"
        if ef:
            key = (ef, kind)
            if key in seen:
                j = seen[key]
                validations.append({
                    "level": "error",
                    "code": "duplicate_effective_kind",
                    "message": f"Tables {j} and {i} share effective_from={ef} rate_kind={kind}",
                })
            else:
                seen[key] = i

    if not nominated_expiry:
        has_ef = any((table.get("effective_from") or "").strip() for table in tables)
        if has_ef:
            validations.append({
                "level": "info",
                "code": "expiry_fallback",
                "message": "No nominated expiry override found; used +1 year fallback for last table's to_date",
            })

    return validations


def expand_table_rows(table: dict[str, Any]) -> dict[str, Any]:
    rate_kind = table.get("rate_kind")
    rate_field_map = {
        "hourly": "hourly_rate",
        "weekly": "weekly_rate",
        "fortnightly": "fortnightly_rate",
        "annual": "annual_rate",
    }
    target_field = rate_field_map.get(rate_kind) if rate_kind else None

    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if "rate" in row and target_field:
            row.setdefault(target_field, row.pop("rate"))
        for field in ("band", "level", "title", "weekly_rate", "annual_rate", "hourly_rate", "fortnightly_rate", "notes"):
            row.setdefault(field, None)
    return table


def normalise_effective_from(table: dict[str, Any]) -> dict[str, Any]:
    ef = table.get("effective_from")
    if ef is None or ef == "":
        return table
    if isinstance(ef, str) and not _ISO_DATE_RE.match(ef):
        existing_note = table.get("effective_from_note") or ""
        table["effective_from_note"] = existing_note if existing_note else ef
        table["effective_from"] = None
    return table


def is_hourly_only_table(table: dict[str, Any]) -> bool:
    if (table.get("rate_kind") or "").lower() == "hourly":
        return True
    rows = table.get("rows") or []
    if not rows:
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("hourly_rate") is None:
            continue
        if any(row.get(field) is not None for field in ("weekly_rate", "fortnightly_rate", "annual_rate")):
            return False
    has_any_hourly = any(
        isinstance(row, dict) and row.get("hourly_rate") is not None
        for row in rows
    )
    has_any_other = any(
        isinstance(row, dict) and any(
            row.get(field) is not None for field in ("weekly_rate", "fortnightly_rate", "annual_rate")
        )
        for row in rows
    )
    return has_any_hourly and not has_any_other


def candidate_table_rate_kind(table: dict[str, Any]) -> str:
    kind = str(table.get("rate_kind") or "").strip().lower()
    if kind in PAY_TABLE_EXTRACTION_RATE_PRIORITY:
        return kind
    rows = table.get("rows") or []
    if any(isinstance(row, dict) and row.get("weekly_rate") is not None for row in rows):
        return "weekly"
    if any(isinstance(row, dict) and row.get("annual_rate") is not None for row in rows):
        return "annual"
    if any(isinstance(row, dict) and row.get("fortnightly_rate") is not None for row in rows):
        return "fortnightly"
    return kind


def normalise_extracted_pay_table_candidates(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        table = normalise_effective_from(expand_table_rows(table))
        if is_hourly_only_table(table):
            continue
        rows = [
            row
            for row in (table.get("rows") or [])
            if isinstance(row, dict) and is_standard_band_level_row(row)
        ]
        if not rows:
            continue
        table["rows"] = rows
        cleaned.append(table)

    rate_kinds = [
        candidate_table_rate_kind(table)
        for table in cleaned
        if candidate_table_rate_kind(table) in PAY_TABLE_EXTRACTION_RATE_PRIORITY
    ]
    if not rate_kinds:
        return cleaned
    preferred_kind = min(rate_kinds, key=lambda kind: PAY_TABLE_EXTRACTION_RATE_PRIORITY[kind])
    return [
        table
        for table in cleaned
        if candidate_table_rate_kind(table) == preferred_kind
    ]


__all__ = [
    "PAY_TABLE_EXTRACTION_RATE_PRIORITY",
    "apply_timeline_policy_to_tables",
    "candidate_table_rate_kind",
    "expand_table_rows",
    "is_hourly_only_table",
    "nearest_rule_date",
    "normalise_effective_from",
    "normalise_extracted_pay_table_candidates",
    "parse_iso_date",
    "prepare_source_date_fields",
    "recalc_to_dates",
    "validate_pay_tables",
]
