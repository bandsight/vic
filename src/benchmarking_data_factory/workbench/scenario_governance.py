from __future__ import annotations

from contextvars import ContextVar
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException

from benchmarking_data_factory.workbench.scenario_qa_events import (
    QA_EVENT_LIMIT,
    QA_RATE_FIELDS,
    QA_TABLE_DATE_FIELDS,
    _append_qa_events,
    _make_qa_event,
    _normalise_scenario_override_payload,
    _pay_row_key,
    _pay_row_maps,
    _pay_table_label,
    _pay_table_qa_events,
    _qa_json_equivalent,
    _qa_numeric_equivalent,
    _scenario_cell_parts,
    _scenario_note_events,
    _scenario_override_events,
    _short_qa_excerpt,
)
from benchmarking_data_factory.workbench.scenario_review_resolution import (
    _apply_needs_review as _apply_needs_review_impl,
    _future_trigger_date as _future_trigger_date_impl,
    _is_future_iso_date as _is_future_iso_date_impl,
    _scenario_compact_result as _scenario_compact_result_impl,
    _scenario_future_trigger as _scenario_future_trigger_impl,
    _scenario_section_resolution as _scenario_section_resolution_impl,
)


@dataclass(frozen=True)
class ScenarioGovernanceDependencies:
    scenario_overrides_dir: Callable[[], Path]
    split_ae_id: Callable[[str], tuple[str, str | None]]
    find_pdf: Callable[[str], Path | None]
    load_registry: Callable[[], dict[str, str]]
    get_canonical: Callable[[str], dict[str, Any]]
    recalc_to_dates: Callable[..., Any]
    get_nominated_expiry: Callable[[dict[str, Any]], str | None]
    get_uplift_rule_dates: Callable[[dict[str, Any]], list[str]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any]]
    resolve_canonical_lga_short_name: Callable[..., str | None]
    run_scenarios: Callable[..., Any]
    now_iso: Callable[[], str]
    apply_section_status: Callable[..., Any]
    save_canonical: Callable[[str, dict[str, Any]], None]
    construct_table: Callable[..., dict[str, Any] | None]
    normalised_governed_payload_for_response: Callable[..., dict[str, Any]]
    rate_cap_data_dir: Callable[[], Path]
    invalidate_rate_cap_caches: Callable[[], None]


_ACTIVE_DEPS: ContextVar[ScenarioGovernanceDependencies | None] = ContextVar(
    "scenario_governance_dependencies",
    default=None,
)


class _ScenarioGovernanceDependencyScope:
    def __init__(self, deps: ScenarioGovernanceDependencies):
        self.deps = deps
        self.token: Any = None

    def __enter__(self) -> None:
        self.token = _ACTIVE_DEPS.set(self.deps)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.token is not None:
            _ACTIVE_DEPS.reset(self.token)


def scenario_governance_dependencies(deps: ScenarioGovernanceDependencies) -> _ScenarioGovernanceDependencyScope:
    return _ScenarioGovernanceDependencyScope(deps)


def _deps() -> ScenarioGovernanceDependencies:
    deps = _ACTIVE_DEPS.get()
    if deps is None:
        raise RuntimeError("Scenario governance dependencies are not configured")
    return deps


def scenario_overrides_dir() -> Path:
    return _deps().scenario_overrides_dir()


def split_ae_id(ae_id: str) -> tuple[str, str | None]:
    return _deps().split_ae_id(ae_id)


def find_pdf(ae_id: str) -> Path | None:
    return _deps().find_pdf(ae_id)


def load_registry() -> dict[str, str]:
    return _deps().load_registry()


def get_canonical(ae_id: str) -> dict[str, Any]:
    return _deps().get_canonical(ae_id)


def recalc_to_dates(*args: Any, **kwargs: Any) -> Any:
    return _deps().recalc_to_dates(*args, **kwargs)


def get_nominated_expiry(canonical: dict[str, Any]) -> str | None:
    return _deps().get_nominated_expiry(canonical)


def get_uplift_rule_dates(canonical: dict[str, Any]) -> list[str]:
    return _deps().get_uplift_rule_dates(canonical)


def fetch_metadata_for_ae_id(ae_id: str, decisions: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if decisions is None:
        return _deps().fetch_metadata_for_ae_id(ae_id)
    return _deps().fetch_metadata_for_ae_id(ae_id, decisions)


def resolve_canonical_lga_short_name(
    ae_id: str,
    fetch_metadata: dict[str, Any] | None,
    decisions: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    if decisions is None:
        return _deps().resolve_canonical_lga_short_name(ae_id, fetch_metadata)
    return _deps().resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)


def run_scenarios(canonical: dict[str, Any], **kwargs: Any) -> Any:
    return _deps().run_scenarios(canonical, **kwargs)


def now_iso() -> str:
    return _deps().now_iso()


def apply_section_status(*args: Any, **kwargs: Any) -> Any:
    return _deps().apply_section_status(*args, **kwargs)


def save_canonical(ae_id: str, canonical: dict[str, Any]) -> None:
    _deps().save_canonical(ae_id, canonical)


def construct_table(canonical: dict[str, Any], effective_date: str, **kwargs: Any) -> dict[str, Any] | None:
    return _deps().construct_table(canonical, effective_date, **kwargs)


def normalised_governed_payload_for_response(governed: dict[str, Any] | None, **kwargs: Any) -> dict[str, Any]:
    return _deps().normalised_governed_payload_for_response(governed, **kwargs)


def rate_cap_data_dir() -> Path:
    return _deps().rate_cap_data_dir()


def invalidate_rate_cap_caches() -> None:
    _deps().invalidate_rate_cap_caches()


def _ensure_council_available(ae_id: str) -> None:
    parent_ae_id, _ = split_ae_id(ae_id)
    if find_pdf(ae_id) is None and ae_id.lower() not in load_registry() and parent_ae_id not in load_registry():
        raise HTTPException(status_code=404, detail="Council not found")


def _scenario_override_path(ae_id: str) -> Path:
    return scenario_overrides_dir() / f"{ae_id.lower()}.json"


def _read_scenario_override_state(ae_id: str) -> dict[str, Any]:
    path = _scenario_override_path(ae_id)
    if not path.exists():
        return {
            "ae_id": ae_id,
            "overrides": {},
            "notes": None,
            "saved_at": None,
            "audit_events": [],
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        state = {}
    state.setdefault("ae_id", ae_id)
    state["overrides"] = _normalise_scenario_override_payload(state.get("overrides") or {})
    state.setdefault("notes", None)
    state.setdefault("saved_at", None)
    state["audit_events"] = [event for event in (state.get("audit_events") or []) if isinstance(event, dict)]
    return state


def _scenario_cell_overrides_for_period(ae_id: str, effective_from: str) -> dict[str, Any] | None:
    state = _read_scenario_override_state(ae_id)
    overrides = state.get("overrides") if isinstance(state, dict) else None
    if not isinstance(overrides, dict):
        return None
    period_overrides = overrides.get(effective_from)
    return period_overrides if isinstance(period_overrides, dict) else None


def _write_scenario_override_state(
    ae_id: str,
    overrides: dict[str, Any],
    notes: Any,
    saved_at: str | None,
    audit_events: Any = None,
) -> dict[str, Any]:
    scenario_overrides_dir().mkdir(parents=True, exist_ok=True)
    path = _scenario_override_path(ae_id)
    payload = {
        "ae_id": ae_id,
        "overrides": _normalise_scenario_override_payload(overrides),
        "notes": notes,
        "saved_at": saved_at,
        "audit_events": [event for event in (audit_events or []) if isinstance(event, dict)][-QA_EVENT_LIMIT:],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _apply_needs_review(
    results: tuple,
    saved_at: Optional[str],
) -> list:
    """Flip table_resolved â†’ needs_review when any dep was confirmed after saved_at."""
    return _apply_needs_review_impl(results, saved_at)


def _scenario_compact_result(result: Any) -> dict[str, Any]:
    return _scenario_compact_result_impl(result)


def _is_future_iso_date(value: str | None) -> bool:
    return _is_future_iso_date_impl(value)


def _future_trigger_date(period_effective_from: str | None) -> str:
    return _future_trigger_date_impl(period_effective_from)


def _scenario_future_trigger(result: Any) -> dict[str, Any] | None:
    return _scenario_future_trigger_impl(result)


def _scenario_section_resolution(results: list[Any], run_at: str) -> tuple[str, dict[str, Any]]:
    return _scenario_section_resolution_impl(results, run_at)


def _body_overrides_to_raw(body: Any) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        period: {
            cell: {"action": ov.action, "weekly": ov.weekly}
            for cell, ov in cells.items()
        }
        for period, cells in body.overrides.items()
    }


def run_uplift_rule_scenarios(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        _ensure_council_available(ae_id)
        canonical = get_canonical(ae_id)
        scenario_tables = canonical.get("sections", {}).get("pay_tables", {}).get("tables") or []
        if scenario_tables:
            recalc_to_dates(
                scenario_tables,
                get_nominated_expiry(canonical),
                get_uplift_rule_dates(canonical),
            )
        fetch_metadata = fetch_metadata_for_ae_id(ae_id)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
        canonical_lga_short_name = canonical.get("canonical_lga_short_name")
        if canonical_lga_short_name and ("__" in ae_id or not lga_short_name):
            lga_short_name = canonical_lga_short_name
        existing_state = _read_scenario_override_state(ae_id)
        raw_overrides = _body_overrides_to_raw(body)
        if not raw_overrides:
            raw_overrides = _normalise_scenario_override_payload(existing_state.get("overrides") or {})
        results = run_scenarios(canonical, overrides=raw_overrides or None, lga_short_name=lga_short_name)
        saved_at = existing_state.get("saved_at")
        results = _apply_needs_review(results, saved_at)
        run_at = now_iso()
        scenario_section = canonical.setdefault("sections", {}).setdefault("scenarios", {})
        scenario_status, scenario_data = _scenario_section_resolution(results, run_at)
        apply_section_status(scenario_section, scenario_status, run_at if scenario_status == "done" else None)
        scenario_section["data"] = scenario_data
        save_canonical(ae_id, canonical)
        existing_tables = [
            t for t in (canonical.get("sections", {}).get("pay_tables", {}).get("tables") or [])
            if t.get("effective_from")
        ]
        existing_table_dates = {t.get("effective_from") for t in existing_tables}
        extracted_dates = [
            t.get("effective_from") for t in existing_tables
            if t.get("provenance") != "constructed"
        ]
        baseline_floor = min(extracted_dates) if extracted_dates else None
        ur_section = (canonical.get("sections") or {}).get("uplift_rules", {}) or {}
        from benchmarking_data_factory.scenario_testing.engine import _filter_rules_by_council  # noqa: PLC0415
        from benchmarking_data_factory.scenario_testing.projector import extract_rules_for_projection  # noqa: PLC0415
        all_rules = list(_filter_rules_by_council(tuple(extract_rules_for_projection(ur_section)), lga_short_name))
        constructable_periods = []
        for rule in all_rules:
            if not isinstance(rule, dict):
                continue
            effective_date = rule.get("effective_date")
            if not effective_date or effective_date in existing_table_dates:
                continue
            if baseline_floor and effective_date <= baseline_floor:
                continue
            quantum_type = rule.get("quantum_type", "unknown")
            if quantum_type in ("table_embedded", "unknown"):
                continue
            constructable_periods.append({
                "effective_date": effective_date,
                "rule_id": f"{effective_date}::{rule.get('period_label', '')}",
                "rule_quantum": rule.get("quantum", ""),
            })
        scenario_payloads = [asdict(result) for result in results]
        from benchmarking_data_factory.workbench import review_advice as review_advice_module  # noqa: PLC0415

        return {
            "ae_id": ae_id,
            "scenarios": scenario_payloads,
            "constructable_periods": constructable_periods,
            "future_triggers": scenario_data.get("future_triggers", []),
            "blocking_results": scenario_data.get("blocking_results", []),
            "section_status": scenario_section.get("status", "in_progress"),
            "review_hints": review_advice_module.build_scenario_review_hints(canonical, scenario_payloads),
        }


def get_uplift_rule_scenario_overrides(ae_id: str, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        return _read_scenario_override_state(ae_id)


def post_uplift_rule_scenario_overrides(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        raw_overrides = _normalise_scenario_override_payload(_body_overrides_to_raw(body))
        path = _scenario_override_path(ae_id)
        existing = _read_scenario_override_state(ae_id)
        saved_at = datetime.now(timezone.utc).isoformat()
        new_events = _scenario_override_events(
            existing.get("overrides") or {},
            raw_overrides,
            saved_at,
            body.change_context,
        )
        audit_events = _append_qa_events(existing.get("audit_events"), new_events)
        if not raw_overrides and not audit_events and not existing.get("notes"):
            if path.exists():
                path.unlink()
            return {"ae_id": ae_id, "overrides": {}, "notes": None, "saved_at": None, "audit_events": []}
        return _write_scenario_override_state(
            ae_id,
            raw_overrides,
            existing.get("notes"),
            saved_at,
            audit_events,
        )


def post_uplift_rule_scenario_note(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        existing = _read_scenario_override_state(ae_id)
        saved_at = datetime.now(timezone.utc).isoformat()
        overrides_to_save = _normalise_scenario_override_payload(
            body.overrides if body.overrides is not None else (existing.get("overrides") or {})
        )
        new_events = [
            *_scenario_override_events(existing.get("overrides") or {}, overrides_to_save, saved_at, body.change_context),
            *_scenario_note_events(existing.get("notes"), body.notes, saved_at, body.change_context),
        ]
        audit_events = _append_qa_events(existing.get("audit_events"), new_events)
        return _write_scenario_override_state(ae_id, overrides_to_save, body.notes, saved_at, audit_events)


def delete_uplift_rule_scenario_overrides(ae_id: str, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        existing = _read_scenario_override_state(ae_id)
        saved_at = datetime.now(timezone.utc).isoformat()
        clear_context = {"scope": "group", "action": "clear_overrides", "affected_cells": sum(
            len(cells) for cells in (existing.get("overrides") or {}).values() if isinstance(cells, dict)
        )}
        new_events = _scenario_override_events(existing.get("overrides") or {}, {}, saved_at, clear_context)
        if existing.get("overrides"):
            new_events.insert(
                0,
                _make_qa_event(
                    saved_at,
                    "scenario_overrides_cleared",
                    "scenario_override",
                    "group",
                    affected_count=clear_context["affected_cells"],
                    change_context=clear_context,
                ),
            )
        audit_events = _append_qa_events(existing.get("audit_events"), new_events)
        if not audit_events:
            path = _scenario_override_path(ae_id)
            if path.exists():
                path.unlink()
            return {"ae_id": ae_id, "cleared": True, "overrides": {}, "notes": None, "saved_at": None, "audit_events": []}
        payload = _write_scenario_override_state(ae_id, {}, None, saved_at, audit_events)
        payload["cleared"] = True
        return payload


def construct_pay_table_for_period(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        _ensure_council_available(ae_id)
        canonical = get_canonical(ae_id)
        existing_dates = {
            table.get("effective_from")
            for table in (canonical.get("sections", {}).get("pay_tables", {}).get("tables") or [])
            if table.get("effective_from")
        }
        if body.effective_date in existing_dates:
            raise HTTPException(status_code=409, detail=f"Table already exists for {body.effective_date}")
        fetch_metadata = fetch_metadata_for_ae_id(ae_id)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
        table = construct_table(canonical, body.effective_date, lga_short_name=lga_short_name)
        if table is None:
            raise HTTPException(status_code=422, detail=f"Cannot construct table for {body.effective_date}: no matching mechanisable rule or no prior table")
        sections = canonical.setdefault("sections", {})
        pay_tables = sections.setdefault("pay_tables", {})
        if "tables" not in pay_tables or pay_tables["tables"] is None:
            pay_tables["tables"] = []
        pay_tables["tables"].append(table)
        save_canonical(ae_id, canonical)
        return {"ae_id": ae_id, "effective_date": body.effective_date, "table": table}


def _required_period_effective_from(value: Any) -> str:
    effective_from = str(value or "").strip()
    if not effective_from:
        raise HTTPException(status_code=400, detail="period_effective_from is required")
    return effective_from


def promote_governed_set(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        from benchmarking_data_factory.governed_set import (  # noqa: PLC0415
            extract_uplift_rules,
            promote_pay_table,
            promote_uplift_rule,
            select_uplift_rule_for_period,
        )
        from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (  # noqa: PLC0415
            RateCapResolutionError,
            date_to_financial_year,
            resolve_effective_rate,
        )

        _ensure_council_available(ae_id)
        kind = str(body.kind or "").strip()
        effective_from = _required_period_effective_from(body.period_effective_from)
        if kind not in ("pay_table", "uplift_rule"):
            raise HTTPException(status_code=400, detail="kind must be pay_table or uplift_rule")
        canonical = get_canonical(ae_id)
        try:
            if kind == "pay_table":
                promote_pay_table(
                    canonical,
                    effective_from,
                    cell_overrides=_scenario_cell_overrides_for_period(ae_id, effective_from),
                )
            else:
                fetch_metadata = fetch_metadata_for_ae_id(ae_id)
                lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
                rate_cap_value = None
                rate_cap_resolution = None
                rules = extract_uplift_rules(canonical)
                match = select_uplift_rule_for_period(rules, effective_from, lga_short_name=lga_short_name)
                quantum_str = (match or {}).get("quantum") or ""
                external_ref = (match or {}).get("quantum_external_ref") or ""
                if effective_from and lga_short_name and quantum_str:
                    try:
                        financial_year = date_to_financial_year(effective_from)
                        try:
                            resolution = resolve_effective_rate(lga_short_name, financial_year, quantum_str, external_ref)
                            if isinstance(resolution, dict):
                                rate_cap_resolution = resolution
                                rate_cap_value = resolution.get("raw_rate_cap")
                        except RateCapResolutionError:
                            rate_cap_value = None
                    except (ValueError, RateCapResolutionError):
                        rate_cap_value = None
                promote_uplift_rule(
                    canonical,
                    effective_from,
                    rate_cap_value=rate_cap_value,
                    rate_cap_resolution=rate_cap_resolution,
                    lga_short_name=lga_short_name,
                )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        save_canonical(ae_id, canonical)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
        governed = normalised_governed_payload_for_response(
            canonical.get("sections", {}).get("uplifts", {}).get("data", {"periods": []}),
            lga_short_name=lga_short_name,
        )
        return {"ae_id": ae_id, "governed": governed}


def unwind_governed_set(ae_id: str, body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        from benchmarking_data_factory.governed_set import unwind  # noqa: PLC0415

        _ensure_council_available(ae_id)
        kind = str(body.kind or "").strip()
        effective_from = _required_period_effective_from(body.period_effective_from)
        if kind not in ("pay_table", "uplift_rule"):
            raise HTTPException(status_code=400, detail="kind must be pay_table or uplift_rule")
        canonical = get_canonical(ae_id)
        try:
            summary = unwind(canonical, effective_from, kind)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        save_canonical(ae_id, canonical)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
        governed = normalised_governed_payload_for_response(
            (canonical.get("sections", {}).get("uplifts", {}) or {}).get("data") or {"periods": []},
            lga_short_name=lga_short_name,
        )
        return {"ae_id": ae_id, "summary": summary, "governed": governed}


def get_governed_set(ae_id: str, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        _ensure_council_available(ae_id)
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata)
        governed = normalised_governed_payload_for_response(
            (canonical.get("sections", {}).get("uplifts", {}) or {}).get("data") or {"periods": []},
            lga_short_name=lga_short_name,
        )
        return {"ae_id": ae_id, "governed": governed}


def get_rate_cap_status(deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        invalidate_rate_cap_caches()
        year_status_path = rate_cap_data_dir() / "rate-cap-year-status.csv"
        standard_path = rate_cap_data_dir() / "standard-statewide-rate-caps.csv"
        years = []
        with year_status_path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                years.append(dict(row))
        standards = {}
        with standard_path.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                standards[row["period_year_label"]] = row
        for year in years:
            standard = standards.get(year["financial_year"])
            year["standard_rate_cap_value"] = standard["rate_cap_value"] if standard else None
        return {"years": years}


def post_rate_cap_confirm(body: Any, deps: ScenarioGovernanceDependencies) -> dict[str, Any]:
    with scenario_governance_dependencies(deps):
        year_status_path = rate_cap_data_dir() / "rate-cap-year-status.csv"
        standard_path = rate_cap_data_dir() / "standard-statewide-rate-caps.csv"

        invalidate_rate_cap_caches()
        with year_status_path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or ["financial_year", "resolution_status", "confirmed_date", "notes"]
            rows = list(reader)
        found = False
        for row in rows:
            if row["financial_year"] == body.financial_year:
                row["resolution_status"] = "confirmed"
                row["confirmed_date"] = body.confirmed_date
                row["notes"] = body.notes or row.get("notes", "")
                found = True
                break
        if not found:
            rows.append({
                "financial_year": body.financial_year,
                "resolution_status": "confirmed",
                "confirmed_date": body.confirmed_date,
                "notes": body.notes or "",
            })
        with year_status_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        with standard_path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            standard_fieldnames = reader.fieldnames or [
                "period_year_label", "rate_cap_value", "source_reference", "source_type", "effective_date_or_applicable_year", "notes",
            ]
            standard_rows = list(reader)
        standard_found = False
        for row in standard_rows:
            if row["period_year_label"] == body.financial_year:
                row["rate_cap_value"] = f"{body.rate_cap_value}"
                row["source_reference"] = body.source_reference
                row["notes"] = body.notes or row.get("notes", "")
                standard_found = True
                break
        if not standard_found:
            standard_rows.append({
                "period_year_label": body.financial_year,
                "rate_cap_value": f"{body.rate_cap_value}",
                "source_reference": body.source_reference,
                "source_type": "public web page",
                "effective_date_or_applicable_year": body.financial_year,
                "notes": body.notes or "",
            })
        standard_rows.sort(key=lambda row: row["period_year_label"], reverse=True)
        with standard_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=standard_fieldnames)
            writer.writeheader()
            writer.writerows(standard_rows)

        invalidate_rate_cap_caches()
        return {
            "ok": True,
            "financial_year": body.financial_year,
            "rate_cap_value": body.rate_cap_value,
            "confirmed_date": body.confirmed_date,
        }
