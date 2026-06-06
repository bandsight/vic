from __future__ import annotations

from typing import Any, Callable

from benchmarking_data_factory.workbench.review_sections import (
    default_sections,
    merge_section_defaults,
)


FetchMetadataLookup = Callable[[str], dict[str, Any] | None]


def fresh_canonical(ae_id: str, source_name: str) -> dict[str, Any]:
    return {
        "agreement_id": ae_id,
        "source_name": source_name,
        "fwc": {
            "lga_code": None,
            "matter_number": None,
            "print_id": None,
            "operative_date": None,
            "expiry_date": None,
            "version": None,
            "superseded_by_ae_id": None,
        },
        "overview": {
            "page_count": None,
            "likely_pay_table_pages": [],
            "likely_uplift_pages": [],
            "estimated_earliest_commencing": None,
            "estimated_latest_commencing": None,
            "document_structure_notes": "",
            "red_flags": [],
            "band_level_alterations": [],
            "generation_warning": "",
            "generated_at": None,
        },
        "sections": default_sections(),
    }


def merge_defaults(data: dict[str, Any] | None, ae_id: str, source_name: str) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    merged = fresh_canonical(ae_id, source_name)
    merged.update(data)
    merged["agreement_id"] = ae_id
    merged["source_name"] = data.get("source_name") or source_name

    overview_defaults = fresh_canonical(ae_id, source_name)["overview"]
    overview_incoming = data.get("overview") if isinstance(data.get("overview"), dict) else {}
    overview_current = merged.get("overview") if isinstance(merged.get("overview"), dict) else {}
    overview_defaults.update(overview_current)
    overview_defaults.update(overview_incoming)
    merged["overview"] = overview_defaults
    merged["sections"] = merge_section_defaults(data.get("sections") if isinstance(data.get("sections"), dict) else {})
    return merged


def clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def get_nominated_expiry(
    canonical: dict[str, Any],
    fetch_metadata_lookup: FetchMetadataLookup | None = None,
) -> str | None:
    """Resolve nominal expiry from canonical data, then optional source metadata."""
    canonical = canonical if isinstance(canonical, dict) else {}
    sections = canonical.get("sections") if isinstance(canonical.get("sections"), dict) else {}

    front_matter = sections.get("front_matter") if isinstance(sections, dict) else {}
    front_matter_data = front_matter.get("data") if isinstance(front_matter, dict) else None
    if isinstance(front_matter_data, dict):
        value = clean_string(front_matter_data.get("nominated_expiry"))
        if value:
            return value

    fwc = canonical.get("fwc") if isinstance(canonical.get("fwc"), dict) else {}
    value = clean_string(fwc.get("expiry_date")) if isinstance(fwc, dict) else None
    if value:
        return value

    pay_tables = sections.get("pay_tables") if isinstance(sections, dict) else {}
    tables = pay_tables.get("tables") if isinstance(pay_tables, dict) else []
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            provenance = table.get("provenance")
            if not isinstance(provenance, dict):
                continue
            value = clean_string(provenance.get("expiry_date"))
            if value:
                return value

    ae_id = clean_string(canonical.get("agreement_id"))
    if ae_id and fetch_metadata_lookup:
        try:
            fetch_metadata = fetch_metadata_lookup(ae_id)
        except Exception:  # noqa: BLE001 - expiry lookup must not break report loading
            fetch_metadata = None
        if isinstance(fetch_metadata, dict):
            value = clean_string(fetch_metadata.get("Expiry Date"))
            if value:
                return value

    return None


def resolve_fwc(canonical: dict[str, Any] | None, fetch_metadata: dict[str, Any] | None) -> dict[str, Any]:
    fwc_canonical = canonical.get("fwc") if isinstance(canonical, dict) else {}
    if not isinstance(fwc_canonical, dict):
        fwc_canonical = {}
    metadata = fetch_metadata or {}
    return {
        "lga_code": fwc_canonical.get("lga_code") or metadata.get("lga_code"),
        "matter_number": fwc_canonical.get("matter_number") or metadata.get("Matter Number"),
        "print_id": fwc_canonical.get("print_id") or metadata.get("Print ID"),
        "operative_date": fwc_canonical.get("operative_date") or metadata.get("Operative Date"),
        "expiry_date": fwc_canonical.get("expiry_date") or metadata.get("Expiry Date"),
        "version": fwc_canonical.get("version") or metadata.get("Version"),
        "superseded_by_ae_id": fwc_canonical.get("superseded_by_ae_id") or metadata.get("superseded_by_ae_id"),
    }


def build_provenance_stamp(
    canonical: dict[str, Any],
    fetch_metadata: dict[str, Any] | None,
    ae_id: str,
    canonical_lga_short_name: str | None,
) -> dict[str, Any]:
    fwc = resolve_fwc(canonical, fetch_metadata)
    metadata = fetch_metadata or {}
    return {
        "agreement_id": ae_id,
        "canonical_lga_short_name": canonical_lga_short_name,
        "lga_code": fwc.get("lga_code"),
        "matter_number": fwc.get("matter_number"),
        "print_id": fwc.get("print_id"),
        "expiry_date": fwc.get("expiry_date"),
        "version": fwc.get("version"),
        "superseded_by_ae_id": fwc.get("superseded_by_ae_id"),
        "scope_resolution_status": metadata.get("scope_resolution_status"),
        "lineage_key": metadata.get("lineage_key"),
    }
