"""Build a curated JSON bundle for report prototyping.

The bundle is intentionally report-shaped: it includes compact derived JSONs
for prototyping plus the heavier source JSONs for validation/drilldown.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
DOLLAR_RE = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
RATE_CAP_RE = re.compile(
    r"\b(rate\s*-?\s*cap|gazetted|esc|essential services|minister)\b",
    re.IGNORECASE,
)
CPI_RE = re.compile(r"\b(cpi|consumer price index|all groups)\b", re.IGNORECASE)
ONE_OFF_RE = re.compile(
    r"\b(one[- ]?off|once[- ]?off|lump\s*sum|gross payment|payment|sign[- ]?on|retention)\b",
    re.IGNORECASE,
)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def csv_to_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).replace("%", "").replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def financial_year(date_text: Any) -> str | None:
    if not date_text or not isinstance(date_text, str):
        return None
    try:
        year, month, _day = [int(part) for part in date_text[:10].split("-")]
    except (TypeError, ValueError):
        return None
    start = year if month >= 7 else year - 1
    return f"{start}-{str((start + 1) % 100).zfill(2)}"


def model_family(rule: dict[str, Any]) -> str:
    quantum = str(rule.get("quantum") or "")
    quantum_type = str(rule.get("quantum_type") or "").strip()
    external = str(rule.get("quantum_external_ref") or "")
    has_rate_cap = bool(RATE_CAP_RE.search(quantum) or RATE_CAP_RE.search(external))
    has_cpi = bool(CPI_RE.search(quantum) or CPI_RE.search(external))
    has_one_off = bool(ONE_OFF_RE.search(quantum))
    has_dollar = bool(DOLLAR_RE.search(quantum) or rule.get("quantum_floor"))
    has_pct = bool(PCT_RE.search(quantum))

    if quantum_type == "table_embedded":
        return "direct_table_or_embedded_schedule"
    if has_one_off and quantum_type == "flat":
        return "one_off_non_compounding_payment"
    if has_rate_cap or has_cpi or quantum_type == "conditional":
        return "external_or_hybrid_best_of"
    if quantum_type == "pct_OR_floor" or (has_pct and has_dollar):
        return "best_of_internal_pct_or_dollar_floor"
    if quantum_type == "percentage" or (has_pct and not has_dollar):
        return "single_percent_ongoing"
    if quantum_type == "flat" or (has_dollar and not has_pct):
        return "single_dollar_ongoing_or_allowance"
    return "unknown_or_unclassified"


def snippet_for_rule(
    ae_id: Any,
    source_page: Any,
    quantum: Any,
    warnings: list[str],
) -> str | None:
    if not ae_id or not source_page:
        return None
    page_path = ROOT / "cache" / str(ae_id) / "pages.json"
    if not page_path.exists():
        return None
    try:
        pages = load_json(page_path)
        page_index = int(source_page) - 1
        if not isinstance(pages, list) or page_index < 0 or page_index >= len(pages):
            return None
        text = str(pages[page_index])
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not read evidence page for {ae_id} page {source_page}: {exc}")
        return None

    quantum_text = str(quantum or "").strip()
    pos = text.lower().find(quantum_text[:60].lower()) if quantum_text else -1
    if pos < 0:
        for needle in ("wage", "salary", "increase", "rate cap", "pay"):
            pos = text.lower().find(needle)
            if pos >= 0:
                break
    if pos < 0:
        pos = 0
    start = max(0, pos - 650)
    end = min(len(text), pos + 1350)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def build_rate_cap_reference(out_dir: Path) -> dict[str, Any]:
    rate_cap_dir = ROOT / "src" / "benchmarking_data_factory" / "uplift_rules" / "external" / "rate-cap"
    reference = {
        "set_id": "rate_cap_reference",
        "label": "Victorian local government rate cap reference",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "standard_statewide_rate_caps": csv_to_rows(rate_cap_dir / "standard-statewide-rate-caps.csv"),
        "higher_cap_exceptions": csv_to_rows(rate_cap_dir / "higher-cap-exceptions.csv"),
        "rate_cap_year_status": csv_to_rows(rate_cap_dir / "rate-cap-year-status.csv"),
        "source_notes": {
            "esc_annual_council_rate_caps": (
                rate_cap_dir / "esc-annual-council-rate-caps-source-note.md"
            ).read_text(encoding="utf-8"),
            "higher_cap_exceptions": (rate_cap_dir / "higher-cap-exceptions-note.md").read_text(
                encoding="utf-8"
            ),
            "readme": (rate_cap_dir / "README.md").read_text(encoding="utf-8"),
        },
    }
    write_json(out_dir / "derived" / "06_rate_cap_reference.json", reference)
    return reference


def build_uplift_report(out_dir: Path, warnings: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    source_dir = ROOT / "data" / "cache" / "uplift_rules_suggestions"

    for path in sorted(source_dir.glob("*.json")):
        try:
            suggestion = load_json(path)
            doc = suggestion.get("document") or {}
            rules = doc.get("rules") or []
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not parse uplift suggestion {path}: {exc}")
            continue

        documents.append(
            {
                "suggestion_file": rel(path),
                "suggestion_id": suggestion.get("suggestion_id"),
                "ae_id": doc.get("ae_id"),
                "council": doc.get("council"),
                "covered_councils": doc.get("covered_councils") or [],
                "multi_employer": bool(doc.get("multi_employer")),
                "timing_pattern": doc.get("timing_pattern"),
                "rule_count": len(rules),
                "notes": doc.get("notes"),
                "extraction_status": ((suggestion.get("provenance") or {}).get("extraction_status")),
            }
        )

        for i, rule in enumerate(rules):
            quantum = str(rule.get("quantum") or "")
            pct_values = [float(value) for value in PCT_RE.findall(quantum)]
            dollar_values = [float(value.replace(",", "")) for value in DOLLAR_RE.findall(quantum)]
            external = str(rule.get("quantum_external_ref") or "")
            row = {
                "rule_id": f"{doc.get('ae_id')}::{rule.get('effective_date') or 'undated'}::{i + 1}",
                "suggestion_id": suggestion.get("suggestion_id"),
                "suggestion_file": rel(path),
                "ae_id": doc.get("ae_id"),
                "council": doc.get("council"),
                "covered_councils": doc.get("covered_councils") or [],
                "multi_employer": bool(doc.get("multi_employer")),
                "timing_pattern": doc.get("timing_pattern"),
                "period_label": rule.get("period_label"),
                "effective_date": rule.get("effective_date"),
                "financial_year": financial_year(rule.get("effective_date")),
                "quantum": rule.get("quantum"),
                "quantum_type": rule.get("quantum_type"),
                "model_family": model_family(rule),
                "source_page": rule.get("source_page"),
                "confidence": rule.get("confidence"),
                "has_pct": bool(pct_values),
                "pct_values": pct_values,
                "has_dollar_component": bool(dollar_values or rule.get("quantum_floor")),
                "dollar_values": dollar_values,
                "quantum_floor": rule.get("quantum_floor"),
                "quantum_ceiling": rule.get("quantum_ceiling"),
                "has_rate_cap": bool(RATE_CAP_RE.search(quantum) or RATE_CAP_RE.search(external)),
                "has_cpi": bool(CPI_RE.search(quantum) or CPI_RE.search(external)),
                "has_one_off_language": bool(ONE_OFF_RE.search(quantum)),
                "quantum_external_ref": rule.get("quantum_external_ref"),
                "quantum_external_definition": rule.get("quantum_external_definition"),
                "quantum_resolution": rule.get("quantum_resolution"),
                "timing_clause": rule.get("timing_clause"),
            }
            rows.append(row)

    report = {
        "set_id": "uplift_rules_report_set",
        "label": "Uplift Rules Report Set",
        "description": (
            "One report-friendly row per extracted uplift rule, normalized for pattern "
            "analysis and report prototyping."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_glob": "data/cache/uplift_rules_suggestions/*.json",
        "summary": {
            "suggestion_documents": len(documents),
            "rules": len(rows),
            "with_effective_date": sum(1 for row in rows if row.get("effective_date")),
            "with_rate_cap_language": sum(1 for row in rows if row.get("has_rate_cap")),
            "with_cpi_language": sum(1 for row in rows if row.get("has_cpi")),
            "with_dollar_component": sum(1 for row in rows if row.get("has_dollar_component")),
            "with_one_off_language": sum(1 for row in rows if row.get("has_one_off_language")),
            "model_family_counts": dict(Counter(row["model_family"] for row in rows)),
            "quantum_type_counts": dict(Counter(str(row.get("quantum_type") or "unknown") for row in rows)),
            "timing_pattern_counts": dict(Counter(str(row.get("timing_pattern") or "unknown") for row in rows)),
        },
        "documents": documents,
        "rows": rows,
    }
    write_json(out_dir / "derived" / "04_uplift_rules_report_set.json", report)
    return report


def build_pay_report(out_dir: Path, paytables: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in paytables.get("rows") or []:
        weekly = number(row.get("weekly_rate"))
        annual = number(row.get("annual_rate")) or (round(weekly * 52, 2) if weekly is not None else None)
        rows.append(
            {
                "row_id": f"{row.get('ae_id')}::{row.get('effective_from')}::{row.get('row_index')}",
                "ae_id": row.get("ae_id"),
                "agreement_name": row.get("agreement_name"),
                "canonical_lga_short_name": row.get("canonical_lga_short_name"),
                "effective_from": row.get("effective_from"),
                "to_date": row.get("to_date"),
                "financial_year": financial_year(row.get("effective_from")),
                "period_index": row.get("period_index"),
                "row_index": row.get("row_index"),
                "table_title": row.get("table_title"),
                "source_page": row.get("source_page"),
                "source_clause": row.get("source_clause"),
                "rate_kind": row.get("rate_kind"),
                "band": row.get("band"),
                "level": row.get("level"),
                "title": row.get("title"),
                "weekly_rate": weekly,
                "annual_equivalent": annual,
                "hourly_rate": number(row.get("hourly_rate")),
                "notes": row.get("notes"),
                "governed_at": row.get("governed_at"),
            }
        )

    by_council: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "rows": 0,
            "agreements": set(),
            "periods": set(),
            "min_weekly_rate": None,
            "max_weekly_rate": None,
        }
    )
    for row in rows:
        key = str(row.get("canonical_lga_short_name") or "(unknown)")
        summary = by_council[key]
        summary["rows"] += 1
        if row.get("ae_id"):
            summary["agreements"].add(row["ae_id"])
        if row.get("effective_from"):
            summary["periods"].add(row["effective_from"])
        weekly = row.get("weekly_rate")
        if weekly is not None:
            summary["min_weekly_rate"] = (
                weekly if summary["min_weekly_rate"] is None else min(summary["min_weekly_rate"], weekly)
            )
            summary["max_weekly_rate"] = (
                weekly if summary["max_weekly_rate"] is None else max(summary["max_weekly_rate"], weekly)
            )

    by_council_rows = [
        {
            "canonical_lga_short_name": key,
            "rows": value["rows"],
            "agreements": len(value["agreements"]),
            "periods": len(value["periods"]),
            "min_weekly_rate": value["min_weekly_rate"],
            "max_weekly_rate": value["max_weekly_rate"],
        }
        for key, value in sorted(by_council.items())
    ]

    report = {
        "set_id": "pay_table_report_set",
        "label": "Pay Table Report Set",
        "description": (
            "Report-facing pay table rows with weekly and annual-equivalent values "
            "normalized for prototype charts and council drilldowns."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "exports/paytables-analysis-set-20260427-141219/paytables-analysis-set.json",
        "source_summary": paytables.get("summary"),
        "summary": {
            "rows": len(rows),
            "agreements": len({row.get("ae_id") for row in rows if row.get("ae_id")}),
            "councils": len({row.get("canonical_lga_short_name") for row in rows if row.get("canonical_lga_short_name")}),
            "effective_periods": len({row.get("effective_from") for row in rows if row.get("effective_from")}),
            "min_weekly_rate": min([row["weekly_rate"] for row in rows if row["weekly_rate"] is not None], default=None),
            "max_weekly_rate": max([row["weekly_rate"] for row in rows if row["weekly_rate"] is not None], default=None),
        },
        "by_council": by_council_rows,
        "rows": rows,
    }
    write_json(out_dir / "derived" / "03_pay_table_report_set.json", report)
    return report


def build_distribution_report(out_dir: Path, distribution: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in distribution.get("rows") or []:
        rows.append(
            {
                "analysis_id": row.get("analysis_id"),
                "ae_id": row.get("ae_id") or row.get("agreement_id"),
                "agreement_name": row.get("agreement_name"),
                "canonical_lga_short_name": row.get("canonical_lga_short_name"),
                "council_category": row.get("council_category"),
                "council_type": row.get("council_type"),
                "effective_from": row.get("effective_from"),
                "financial_year": financial_year(row.get("effective_from")),
                "band": row.get("band"),
                "chart_band": row.get("chart_band"),
                "chart_basis": row.get("chart_basis"),
                "classification_label": row.get("classification_label"),
                "chart_min_level": row.get("chart_min_level"),
                "chart_max_level": row.get("chart_max_level"),
                "chart_min_weekly_rate": number(row.get("chart_min_weekly_rate")),
                "chart_max_weekly_rate": number(row.get("chart_max_weekly_rate")),
                "chart_mid_weekly_rate": number(row.get("chart_mid_weekly_rate")),
                "has_partial_band": row.get("has_partial_band"),
                "has_duplicate_levels": row.get("has_duplicate_levels"),
                "is_projected_value": row.get("is_projected_value"),
                "calculation_status": row.get("calculation_status"),
                "calculation_notes": row.get("calculation_notes"),
            }
        )

    report = {
        "set_id": "distribution_report_set",
        "label": "Distribution Report Set",
        "description": "Compact chart-ready distribution points for report prototypes.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data/analysis/distribution-point-analysis.json",
        "source_summary": distribution.get("summary"),
        "summary": {
            "rows": len(rows),
            "agreements": len({row.get("ae_id") for row in rows if row.get("ae_id")}),
            "councils": len({row.get("canonical_lga_short_name") for row in rows if row.get("canonical_lga_short_name")}),
            "bands": len({row.get("chart_band") for row in rows if row.get("chart_band")}),
            "projected_points": sum(1 for row in rows if row.get("is_projected_value")),
            "partial_band_points": sum(1 for row in rows if row.get("has_partial_band")),
        },
        "rows": rows,
    }
    write_json(out_dir / "derived" / "03b_distribution_report_set.json", report)
    return report


def build_council_index(
    out_dir: Path,
    council_master: dict[str, Any],
    pay_report: dict[str, Any],
    distribution_report: dict[str, Any],
    uplift_report: dict[str, Any],
) -> dict[str, Any]:
    pay_counts = {
        row["canonical_lga_short_name"].lower(): row
        for row in pay_report.get("by_council", [])
        if row.get("canonical_lga_short_name")
    }
    distribution_counts = Counter(
        str(row.get("canonical_lga_short_name") or "").lower()
        for row in distribution_report.get("rows", [])
        if row.get("canonical_lga_short_name")
    )
    uplift_counts = Counter(
        str(row.get("council") or "").lower()
        for row in uplift_report.get("rows", [])
        if row.get("council")
    )

    rows: list[dict[str, Any]] = []
    for council in council_master.get("rows") or []:
        short = str(council.get("short_name") or "")
        long_name = str(council.get("long_name") or council.get("official_name") or "")
        short_key = short.lower()
        pay = pay_counts.get(short_key, {})
        uplift_count = 0
        for text_key, count in uplift_counts.items():
            if (short and short.lower() in text_key) or (long_name and long_name.lower() in text_key):
                uplift_count += count
        rows.append(
            {
                "council_key": council.get("council_key"),
                "short_name": short,
                "long_name": long_name,
                "official_name": council.get("official_name"),
                "status": council.get("status"),
                "is_active": council.get("is_active"),
                "council_category": council.get("council_category"),
                "council_type": council.get("council_type"),
                "regional_partnership": council.get("regional_partnership"),
                "metropolitan_region": council.get("metropolitan_region"),
                "office_township": council.get("office_township"),
                "office_lat": number(council.get("office_lat")),
                "office_lon": number(council.get("office_lon")),
                "abs_area_albers_sqkm": number(council.get("abs_area_albers_sqkm")),
                "map_join_key": council.get("map_join_key"),
                "pay_table_rows": pay.get("rows", 0),
                "pay_table_agreements": pay.get("agreements", 0),
                "pay_table_periods": pay.get("periods", 0),
                "distribution_points": distribution_counts.get(short_key, 0),
                "uplift_rule_rows_name_matched": uplift_count,
                "has_report_data": bool(pay.get("rows") or distribution_counts.get(short_key, 0) or uplift_count),
            }
        )

    report = {
        "set_id": "council_index",
        "label": "Council Index",
        "description": (
            "Report spine joining council reference attributes to available pay-table, "
            "distribution, and uplift-rule coverage."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data/reference/victorian-council-master.json",
        "summary": {
            "councils": len(rows),
            "with_any_report_data": sum(1 for row in rows if row["has_report_data"]),
            "with_pay_tables": sum(1 for row in rows if row["pay_table_rows"]),
            "with_distribution_points": sum(1 for row in rows if row["distribution_points"]),
            "with_name_matched_uplift_rules": sum(1 for row in rows if row["uplift_rule_rows_name_matched"]),
        },
        "rows": rows,
    }
    write_json(out_dir / "derived" / "02_council_index.json", report)
    return report


def build_pattern_summary(
    out_dir: Path,
    uplift_report: dict[str, Any],
    pay_report: dict[str, Any],
    distribution_report: dict[str, Any],
) -> dict[str, Any]:
    uplift_rows = uplift_report.get("rows", [])
    summary = {
        "set_id": "pattern_summary",
        "label": "Pattern Summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formula_models_minimum": [
            {
                "model": "direct_table_override",
                "pseudo_excel": "=IF(TableRate>0, TableRate, Base+MAX(SourceIncrease1:SourceIncreaseX))",
                "covers": ["table_embedded", "classification schedules", "agreement-provided resulting rates"],
            },
            {
                "model": "max_candidate_ongoing_uplift",
                "pseudo_excel": "=Base + MAX(PctIncrease, DollarIncrease, RateCapIncrease, CPIIncrease, OtherIncrease)",
                "covers": [
                    "flat percentages",
                    "dollar floors",
                    "rate-cap tracking",
                    "CPI-linked rules",
                    "best-of hybrids",
                ],
            },
            {
                "model": "one_off_non_compounding_payment",
                "pseudo_excel": "=Base; Payment=LumpSum*FTE",
                "covers": ["gross one-off payments", "lump sums", "non-compounding sign-on/retention payments"],
            },
        ],
        "uplift_rule_counts": uplift_report.get("summary"),
        "pay_table_summary": pay_report.get("summary"),
        "distribution_summary": distribution_report.get("summary"),
        "top_rate_cap_external_refs": dict(
            Counter(
                str(row.get("quantum_external_ref") or "inline/unspecified")
                for row in uplift_rows
                if row.get("has_rate_cap")
            ).most_common(25)
        ),
        "rules_by_financial_year": dict(Counter(str(row.get("financial_year") or "undated") for row in uplift_rows)),
        "rules_by_model_family": dict(Counter(row["model_family"] for row in uplift_rows)),
        "rules_by_quantum_type": dict(Counter(str(row.get("quantum_type") or "unknown") for row in uplift_rows)),
    }
    write_json(out_dir / "derived" / "05_pattern_summary.json", summary)
    return summary


def build_evidence_pack(out_dir: Path, uplift_report: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    rows = uplift_report.get("rows", [])
    family_best: dict[str, dict[str, Any]] = {}
    sorted_rows = sorted(
        rows,
        key=lambda row: (-(number(row.get("confidence")) or 0), str(row.get("ae_id")), str(row.get("effective_date"))),
    )
    for row in sorted_rows:
        family = row["model_family"]
        if family not in family_best and row.get("source_page") and row.get("ae_id"):
            family_best[family] = row

    special_needles = {
        "rate_cap_best_of": lambda row: row.get("has_rate_cap") and row.get("has_dollar_component"),
        "rate_cap_share": lambda row: row.get("has_rate_cap")
        and any(value in str(row.get("quantum") or "").lower() for value in ("90%", "85%", "80%", "75%")),
        "dollar_floor": lambda row: row.get("has_dollar_component") and row.get("has_pct"),
        "direct_table": lambda row: row.get("model_family") == "direct_table_or_embedded_schedule",
        "one_off": lambda row: row.get("model_family") == "one_off_non_compounding_payment",
    }
    selected = list(family_best.values())
    for predicate in special_needles.values():
        match = next((row for row in rows if predicate(row) and row.get("source_page") and row.get("ae_id")), None)
        if match and match not in selected:
            selected.append(match)

    seen_ids: set[str] = set()
    examples: list[dict[str, Any]] = []
    for row in selected:
        rule_id = row["rule_id"]
        if rule_id in seen_ids:
            continue
        seen_ids.add(rule_id)
        examples.append(
            {
                "example_id": f"example_{len(examples) + 1:02d}",
                "model_family": row.get("model_family"),
                "ae_id": row.get("ae_id"),
                "council": row.get("council"),
                "period_label": row.get("period_label"),
                "effective_date": row.get("effective_date"),
                "source_page": row.get("source_page"),
                "quantum": row.get("quantum"),
                "quantum_type": row.get("quantum_type"),
                "quantum_external_ref": row.get("quantum_external_ref"),
                "confidence": row.get("confidence"),
                "source_snippet": snippet_for_rule(
                    row.get("ae_id"), row.get("source_page"), row.get("quantum"), warnings
                ),
            }
        )

    pack = {
        "set_id": "evidence_pack",
        "label": "Selected Uplift Rule Evidence Pack",
        "description": (
            "Representative source snippets for report prototypes that need citation/evidence "
            "drilldown UX. Snippets are short excerpts from cached page text, not full agreements."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "examples": examples,
    }
    write_json(out_dir / "evidence" / "07_evidence_pack.json", pack)
    return pack


def build_data_dictionary(out_dir: Path) -> dict[str, Any]:
    dictionary = {
        "set_id": "data_dictionary",
        "label": "Report Prototype Bundle Data Dictionary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": [
            {
                "file": "derived/02_council_index.json",
                "grain": "one row per Victorian council",
                "primary_keys": ["council_key"],
                "purpose": "Report spine, filters, map facets, council profile panels.",
                "important_fields": [
                    "short_name",
                    "long_name",
                    "council_category",
                    "council_type",
                    "regional_partnership",
                    "pay_table_rows",
                    "distribution_points",
                    "uplift_rule_rows_name_matched",
                ],
            },
            {
                "file": "derived/03_pay_table_report_set.json",
                "grain": "one row per governed pay-table classification/level point",
                "primary_keys": ["row_id"],
                "purpose": "Council/classification pay tables, period comparisons, weekly/annual rate charts.",
                "important_fields": [
                    "ae_id",
                    "canonical_lga_short_name",
                    "effective_from",
                    "band",
                    "level",
                    "weekly_rate",
                    "annual_equivalent",
                    "source_page",
                ],
            },
            {
                "file": "derived/03b_distribution_report_set.json",
                "grain": "one chart-ready distribution point by agreement, period and band",
                "primary_keys": ["analysis_id"],
                "purpose": "Distribution visuals, band min/max/midpoint charts, outlier detection.",
                "important_fields": [
                    "chart_band",
                    "chart_min_weekly_rate",
                    "chart_max_weekly_rate",
                    "chart_mid_weekly_rate",
                    "calculation_status",
                ],
            },
            {
                "file": "derived/04_uplift_rules_report_set.json",
                "grain": "one row per extracted uplift rule",
                "primary_keys": ["rule_id"],
                "purpose": "Uplift pattern reports, rate-cap exposure, increase timelines, evidence drilldowns.",
                "important_fields": [
                    "model_family",
                    "quantum_type",
                    "effective_date",
                    "quantum",
                    "has_rate_cap",
                    "quantum_external_ref",
                    "confidence",
                    "source_page",
                ],
            },
            {
                "file": "derived/05_pattern_summary.json",
                "grain": "bundle-level aggregate",
                "primary_keys": ["set_id"],
                "purpose": "Executive summary cards and prototype defaults for pattern analysis.",
            },
            {
                "file": "derived/06_rate_cap_reference.json",
                "grain": "rate-cap reference tables",
                "primary_keys": ["financial_year", "lga_short_name + financial_year"],
                "purpose": "Explaining and resolving rate-cap-linked uplift clauses.",
            },
            {
                "file": "evidence/07_evidence_pack.json",
                "grain": "selected representative source excerpt",
                "primary_keys": ["example_id"],
                "purpose": "Prototype citation panels and evidence-card interaction design.",
            },
        ],
        "join_hints": [
            {
                "left": "pay_table_report_set.rows.ae_id",
                "right": "uplift_rules_report_set.rows.ae_id",
                "relationship": "many-to-many by agreement",
            },
            {
                "left": "pay_table_report_set.rows.canonical_lga_short_name",
                "right": "council_index.rows.short_name",
                "relationship": "many-to-one by council short name",
            },
            {
                "left": "distribution_report_set.rows.canonical_lga_short_name",
                "right": "council_index.rows.short_name",
                "relationship": "many-to-one by council short name",
            },
            {
                "left": "uplift_rules_report_set.rows.financial_year",
                "right": "rate_cap_reference.standard_statewide_rate_caps.period_year_label",
                "relationship": "many-to-one for rate-cap context",
            },
        ],
    }
    write_json(out_dir / "derived" / "01_data_dictionary.json", dictionary)
    return dictionary


def build_report_blueprint(out_dir: Path) -> dict[str, Any]:
    blueprint = {
        "set_id": "report_blueprint",
        "label": "Prototype Report Blueprint",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommended_report_pages": [
            {
                "page_id": "executive_summary",
                "title": "Executive Summary",
                "question": "What is the shape of the EBA dataset and what patterns dominate?",
                "datasets": ["pattern_summary", "council_index"],
                "visuals": [
                    "coverage KPI cards",
                    "uplift model-family bar chart",
                    "effective-year timeline",
                    "data-quality callouts",
                ],
                "filters": ["council_category", "council_type", "financial_year"],
            },
            {
                "page_id": "council_comparator",
                "title": "Council Comparator",
                "question": "How does a selected council compare against peers?",
                "datasets": ["council_index", "pay_table_report_set", "distribution_report_set"],
                "visuals": [
                    "council selector",
                    "band min/max range chart",
                    "peer percentile strip",
                    "agreement period table",
                ],
                "filters": ["selected_council", "peer_group", "effective_from", "band"],
            },
            {
                "page_id": "uplift_rule_patterns",
                "title": "Uplift Rule Patterns",
                "question": (
                    "Which agreements use flat percentages, dollar floors, rate-cap links, "
                    "or table schedules?"
                ),
                "datasets": ["uplift_rules_report_set", "rate_cap_reference", "evidence_pack"],
                "visuals": [
                    "model family matrix",
                    "rate-cap exposure table",
                    "best-of formula explainer cards",
                    "confidence heatmap",
                ],
                "filters": ["model_family", "quantum_type", "has_rate_cap", "financial_year"],
            },
            {
                "page_id": "pay_distribution",
                "title": "Pay Distribution",
                "question": "Where do classification bands sit across councils and over time?",
                "datasets": ["distribution_report_set", "pay_table_report_set", "council_index"],
                "visuals": [
                    "band range beeswarm",
                    "min/mid/max line chart",
                    "classification drilldown table",
                    "outlier list",
                ],
                "filters": ["band", "council_category", "effective_from", "calculation_status"],
            },
            {
                "page_id": "evidence_drilldown",
                "title": "Evidence Drilldown",
                "question": "Can a report reader trace a number or pattern back to source text?",
                "datasets": ["evidence_pack", "uplift_rules_report_set", "pay_table_report_set"],
                "visuals": ["source snippet card", "rule row inspector", "pay table provenance panel"],
                "filters": ["ae_id", "source_page", "model_family"],
            },
        ],
        "prototype_notes": [
            "Use derived JSONs for first-pass UI prototyping; keep source JSONs for drilldown and validation.",
            (
                "Model ongoing uplift as Base + MAX(candidate increases), with direct table "
                "overrides and one-off payments handled separately."
            ),
            "Treat evidence snippets as UX samples, not a complete legal citation archive.",
        ],
    }
    write_json(out_dir / "derived" / "08_report_blueprint.json", blueprint)
    return blueprint


def copy_sources(out_dir: Path) -> dict[str, Any]:
    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "victorian-council-master.json": ROOT / "data" / "reference" / "victorian-council-master.json",
        "paytables-analysis-set.json": ROOT
        / "exports"
        / "paytables-analysis-set-20260427-141219"
        / "paytables-analysis-set.json",
        "distribution-point-analysis.json": ROOT / "data" / "analysis" / "distribution-point-analysis.json",
        "intake-decisions.json": ROOT / "registers" / "intake-decisions.json",
    }
    for dest_name, src in sources.items():
        shutil.copy2(src, source_dir / dest_name)

    source_register = ROOT / "registers" / "source-document-register.csv"
    decision_log = ROOT / "registers" / "decision-log.csv"
    multi_council = ROOT / "registers" / "multi-council-decisions.csv"
    write_json(source_dir / "source-document-register.json", {"rows": csv_to_rows(source_register), "source_csv": rel(source_register)})
    write_json(source_dir / "decision-log.json", {"rows": csv_to_rows(decision_log), "source_csv": rel(decision_log)})
    write_json(source_dir / "multi-council-decisions.json", {"rows": csv_to_rows(multi_council), "source_csv": rel(multi_council)})
    return sources


def build_manifest(
    out_dir: Path,
    bundle_name: str,
    source_inventory: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    files = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": rel(path),
                    "bundle_path": str(path.relative_to(out_dir)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "bundle_id": bundle_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(ROOT),
        "purpose": (
            "Curated JSON bundle for deep analysis and report prototyping around Victorian "
            "council EBA pay tables, uplift rules, distribution points, rate-cap exposure, "
            "and evidence drilldowns."
        ),
        "source_inventory": source_inventory,
        "recommended_start_here": [
            "derived/08_report_blueprint.json",
            "derived/01_data_dictionary.json",
            "derived/05_pattern_summary.json",
            "derived/02_council_index.json",
        ],
        "files": files,
        "warnings": warnings,
    }
    write_json(out_dir / "00_manifest.json", manifest)
    return manifest


def zip_bundle(out_dir: Path, bundle_name: str) -> Path:
    zip_path = ARTIFACTS / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    arcname=str(Path(bundle_name) / path.relative_to(out_dir)).replace("\\", "/"),
                )
    return zip_path


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_name = f"report-prototype-bundle-{stamp}"
    out_dir = ARTIFACTS / bundle_name
    (out_dir / "derived").mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence").mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    source_paths = copy_sources(out_dir)
    paytables = load_json(source_paths["paytables-analysis-set.json"])
    distribution = load_json(source_paths["distribution-point-analysis.json"])
    council_master = load_json(source_paths["victorian-council-master.json"])

    build_rate_cap_reference(out_dir)
    uplift_report = build_uplift_report(out_dir, warnings)
    pay_report = build_pay_report(out_dir, paytables)
    distribution_report = build_distribution_report(out_dir, distribution)
    build_council_index(out_dir, council_master, pay_report, distribution_report, uplift_report)
    build_pattern_summary(out_dir, uplift_report, pay_report, distribution_report)
    evidence_pack = build_evidence_pack(out_dir, uplift_report, warnings)
    build_data_dictionary(out_dir)
    build_report_blueprint(out_dir)

    source_inventory = {
        "pay_table_rows": pay_report["summary"]["rows"],
        "distribution_points": distribution_report["summary"]["rows"],
        "council_master_rows": len(council_master.get("rows") or []),
        "uplift_suggestion_documents": uplift_report["summary"]["suggestion_documents"],
        "uplift_rule_rows": uplift_report["summary"]["rules"],
        "evidence_examples": len(evidence_pack.get("examples") or []),
    }
    build_manifest(out_dir, bundle_name, source_inventory, warnings)
    # Rebuild so manifest also lists itself.
    build_manifest(out_dir, bundle_name, source_inventory, warnings)
    zip_path = zip_bundle(out_dir, bundle_name)

    print(
        json.dumps(
            {
                "bundle_dir": str(out_dir),
                "zip_path": str(zip_path),
                "zip_bytes": zip_path.stat().st_size,
                "files": len([path for path in out_dir.rglob("*") if path.is_file()]),
                **source_inventory,
                "warnings": len(warnings),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
