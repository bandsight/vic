from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal

from benchmarking_data_factory.pay_tables.processing import (
    PAY_TABLE_EXTRACTION_RATE_PRIORITY,
    apply_timeline_policy_to_tables as pay_table_apply_timeline_policy_to_tables,
    candidate_table_rate_kind as pay_table_candidate_table_rate_kind,
    expand_table_rows as pay_table_expand_table_rows,
    is_hourly_only_table as pay_table_is_hourly_only_table,
    nearest_rule_date as pay_table_nearest_rule_date,
    normalise_effective_from as pay_table_normalise_effective_from,
    normalise_extracted_pay_table_candidates as pay_table_normalise_extracted_pay_table_candidates,
    parse_iso_date as pay_table_parse_iso_date,
    prepare_source_date_fields as pay_table_prepare_source_date_fields,
    recalc_to_dates as pay_table_recalc_to_dates,
    validate_pay_tables as pay_table_validate_pay_tables,
)
from benchmarking_data_factory.workbench.canonical_agreement import (
    build_provenance_stamp as canonical_build_provenance_stamp,
    get_nominated_expiry as canonical_get_nominated_expiry,
    resolve_fwc as canonical_resolve_fwc,
)


def get_uplift_rule_dates(canonical: dict[str, Any]) -> list[str]:
    try:
        rules_data = (
            canonical.get("sections", {})
            .get("uplift_rules", {})
            .get("data", {})
        )
        rules = (
            (rules_data.get("accepted") or {}).get("document", {}).get("rules")
            or (rules_data.get("suggestion") or {}).get("document", {}).get("rules")
            or rules_data.get("rules")
            or []
        )
        dates: list[str] = []
        for rule in rules:
            effective_date = (rule.get("effective_date") or "").strip()
            if effective_date and len(effective_date) == 10:
                try:
                    date.fromisoformat(effective_date)
                    dates.append(effective_date)
                except ValueError:
                    pass
        return sorted(set(dates))
    except Exception:
        return []


def get_nominated_expiry(
    canonical: dict[str, Any],
    fetch_metadata_for_ae_id: Callable[[str], dict[str, Any] | None],
) -> str | None:
    return canonical_get_nominated_expiry(canonical, fetch_metadata_for_ae_id)


def parse_iso_date(value: Any) -> str | None:
    return pay_table_parse_iso_date(value)


def prepare_source_date_fields(table: dict[str, Any]) -> str | None:
    return pay_table_prepare_source_date_fields(table)


def nearest_rule_date(source_iso: str, rule_dates: list[date]) -> tuple[str | None, str | None]:
    return pay_table_nearest_rule_date(source_iso, rule_dates)


def apply_timeline_policy_to_tables(
    tables: list[dict[str, Any]],
    timeline_policy: Literal["current", "rule_anchored"],
    uplift_rule_dates: list[str] | None,
) -> dict[str, Any]:
    return pay_table_apply_timeline_policy_to_tables(tables, timeline_policy, uplift_rule_dates)


def recalc_to_dates(
    tables: list[dict[str, Any]],
    nominated_expiry: str | None,
    uplift_rule_dates: list[str] | None = None,
) -> list[dict[str, Any]]:
    return pay_table_recalc_to_dates(tables, nominated_expiry, uplift_rule_dates)


def validate_pay_tables(tables: list[dict[str, Any]], nominated_expiry: str | None = None) -> list[dict[str, Any]]:
    return pay_table_validate_pay_tables(tables, nominated_expiry)


def expand_table_rows(table: dict[str, Any]) -> dict[str, Any]:
    return pay_table_expand_table_rows(table)


def normalise_effective_from(table: dict[str, Any]) -> dict[str, Any]:
    return pay_table_normalise_effective_from(table)


def is_hourly_only_table(table: dict[str, Any]) -> bool:
    return pay_table_is_hourly_only_table(table)


def candidate_table_rate_kind(table: dict[str, Any]) -> str:
    return pay_table_candidate_table_rate_kind(table)


def normalise_extracted_pay_table_candidates(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return pay_table_normalise_extracted_pay_table_candidates(tables)


def resolve_fwc(canonical: dict[str, Any], fetch_metadata: dict[str, Any]) -> dict[str, Any]:
    return canonical_resolve_fwc(canonical, fetch_metadata)


def build_provenance_stamp(
    canonical: dict[str, Any],
    fetch_metadata: dict[str, Any],
    ae_id: str,
    resolve_canonical_lga_short_name: Callable[[str, dict[str, Any]], str | None],
) -> dict[str, Any]:
    return canonical_build_provenance_stamp(
        canonical,
        fetch_metadata,
        ae_id,
        resolve_canonical_lga_short_name(ae_id, fetch_metadata),
    )
