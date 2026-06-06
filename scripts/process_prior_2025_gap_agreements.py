from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import fitz
import yaml


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "documents" / "immutable"
CANONICAL_DIR = ROOT / "canonical"
CANDIDATES_JSON = ROOT / "data" / "bronze" / "phase1_source_build" / "candidate_agreements" / "candidate_agreements.json"


LEVELS_BY_BAND = {
    "1": ["A", "B", "C", "D"],
    "2": ["A", "B", "C"],
    "3": ["A", "B", "C", "D"],
    "4": ["A", "B", "C", "D"],
    "5": ["A", "B", "C", "D"],
    "6": ["A", "B", "C"],
    "7": ["A", "B", "C", "D"],
    "8": ["A", "B", "C", "D"],
}


TO_DATES_BY_EFFECTIVE_FROM = {
    "2022-07-01": "2023-06-30",
    "2023-07-01": "2024-06-30",
    "2024-07-01": "2025-06-30",
    "2022-09-01": "2023-08-31",
    "2023-09-01": "2024-08-31",
    "2024-09-01": "2025-08-31",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def excel_serial_date(value: Any) -> str | None:
    try:
        serial = int(float(value))
    except (TypeError, ValueError):
        return None
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()


def number(value: str) -> float:
    return float(value.replace(",", ""))


def numbers_from_text(value: str) -> list[float]:
    return [number(match) for match in re.findall(r"\d[\d,]*\.\d+", value)]


def pdf_page_text(ae_id: str, page_number: int) -> str:
    with fitz.open(PDF_DIR / f"{ae_id}.pdf") as document:
        return document[page_number - 1].get_text() or ""


def standard_row(band: str, level: str, weekly_rate: float, *, notes: str | None = None) -> dict[str, Any]:
    band_text = str(band)
    level_text = str(level)
    row = {
        "band": int(band_text),
        "level": level_text,
        "weekly_rate": round(float(weekly_rate), 2),
        "title": None,
        "notes": notes,
        "standard_band": band_text,
        "standard_level": level_text,
        "classification_key": f"band_{int(band_text):02d}_level_{level_text}",
        "classification_label": f"Band {int(band_text)} Level {level_text}",
        "classification_sort": int(band_text) * 100 + (ord(level_text.upper()) - 64),
    }
    return row


def period_table(
    *,
    title: str,
    source_pages: list[int],
    source_clause: str,
    effective_from: str,
    rows: list[dict[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    table = {
        "table_title": title,
        "source_pages": source_pages,
        "source_clause": source_clause,
        "effective_from": effective_from,
        "rate_kind": "weekly",
        "to_date": TO_DATES_BY_EFFECTIVE_FROM[effective_from],
        "date_snapped": False,
        "snap_basis": None,
        "snap_note": "Already aligned to uplift rule date",
        "row_scope": "standard_band_level",
        "standard_rows_count": len(rows),
        "rows": rows,
    }
    if notes:
        table["notes"] = notes
    return table


def accepted_rule(
    *,
    label: str,
    effective_date: str,
    timing_clause: str,
    quantum: str,
    quantum_type: str,
    source_page: int,
    source_clause: str,
    pct_component: float | None = None,
    dollar_component: float | None = None,
    resolved_pct: float | None = None,
    resolved_basis: str = "internal_pct",
) -> dict[str, Any]:
    rule = {
        "period_label": label,
        "quantum": quantum,
        "quantum_type": quantum_type,
        "timing_clause": timing_clause,
        "effective_date": effective_date,
        "source_page": source_page,
        "source_clause": source_clause,
        "confidence": 1.0,
    }
    if pct_component is not None:
        rule["pct_component"] = pct_component
    if dollar_component is not None:
        rule["dollar_component"] = dollar_component
        rule["dollar_basis"] = "weekly"
    if resolved_pct is not None:
        rule["resolved_pct"] = resolved_pct
        rule["resolved_basis"] = resolved_basis
    return rule


def governed_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "effective_date": rule["effective_date"],
        "source_rule_id": f"{rule['effective_date']}::{rule['period_label']}",
        "source_quantum": rule["quantum"],
        "source_quantum_type": rule["quantum_type"],
        "pattern_variant": rule["quantum"],
        "pct_component": rule.get("pct_component"),
        "dollar_component": rule.get("dollar_component"),
        "dollar_basis": rule.get("dollar_basis"),
        "resolved_pct": rule.get("resolved_pct") or rule.get("pct_component"),
        "resolved_basis": rule.get("resolved_basis") or "internal_pct",
    }


def candidate_by_ae() -> dict[str, dict[str, Any]]:
    rows = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    return {str(row.get("Agreement ID") or "").lower(): row for row in rows}


def candidate_dates(ae_id: str, candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate = candidates[ae_id]
    return {
        "matter_number": candidate.get("Matter Number") or None,
        "print_id": candidate.get("Print ID") or None,
        "operative_date": excel_serial_date(candidate.get("Operative Date")),
        "expiry_date": excel_serial_date(candidate.get("Expiry Date")),
        "version": candidate.get("Version") or None,
        "superseded_by_ae_id": str(candidate.get("superseded_by_ae_id") or "").lower() or None,
    }


def parse_hindmarsh_rows() -> dict[str, list[dict[str, Any]]]:
    text = pdf_page_text("ae520153", 72)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    periods = {
        "2022-07-01": [],
        "2023-07-01": [],
        "2024-07-01": [],
    }
    current_band: str | None = None
    i = 0
    while i < len(lines):
        band_match = re.fullmatch(r"BAND\s+(\d+)", lines[i], flags=re.I)
        if band_match:
            current_band = band_match.group(1)
            i += 1
            continue
        if current_band and re.fullmatch(r"[A-D]\s*", lines[i]):
            level = lines[i].strip()
            chunk: list[str] = []
            i += 1
            while i < len(lines) and not re.fullmatch(r"[A-D]\s*", lines[i]) and not re.fullmatch(r"BAND\s+\d+", lines[i], flags=re.I):
                chunk.append(lines[i])
                i += 1
            values = numbers_from_text(" ".join(chunk))
            if len(values) < 9:
                raise ValueError(f"Hindmarsh row {current_band}{level} had {len(values)} numeric values")
            for date, weekly in zip(periods, [values[1], values[4], values[7]], strict=True):
                periods[date].append(standard_row(current_band, level, weekly))
            continue
        i += 1
    for date, rows in periods.items():
        if len(rows) != 30:
            raise ValueError(f"Hindmarsh {date} expected 30 rows, found {len(rows)}")
    return periods


def parse_whitehorse_2022_rows() -> list[dict[str, Any]]:
    text = pdf_page_text("ae516762", 66)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if lines[i] in LEVELS_BY_BAND:
            band = lines[i]
            levels = LEVELS_BY_BAND[band]
            while i < len(lines) and lines[i] != "Rate":
                i += 1
            if i >= len(lines):
                raise ValueError(f"Whitehorse band {band} missing Rate marker")
            i += 1
            chunk: list[str] = []
            while i < len(lines) and lines[i] not in LEVELS_BY_BAND:
                chunk.append(lines[i])
                i += 1
            values = numbers_from_text(" ".join(chunk))
            expected = len(levels) * 3
            if len(values) < expected:
                raise ValueError(f"Whitehorse band {band} expected {expected} numeric values, found {len(values)}")
            for index, level in enumerate(levels):
                rows.append(standard_row(band, level, values[(index * 3) + 1]))
            continue
        i += 1
    if len(rows) != 30:
        raise ValueError(f"Whitehorse expected 30 rows, found {len(rows)}")
    return rows


def whitehorse_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    rows_2022 = parse_whitehorse_2022_rows()
    rows_2023: list[dict[str, Any]] = []
    rows_2024: list[dict[str, Any]] = []
    for row in rows_2022:
        band = str(row["standard_band"])
        level = str(row["standard_level"])
        rate_2022 = float(row["weekly_rate"])
        rate_2023 = round(rate_2022 * 1.02975, 2)
        rate_2024 = round(rate_2023 * 1.023375, 2)
        rows_2023.append(standard_row(band, level, rate_2023, notes="Calculated from September 2022 source rate using the 2023 clause 7.1.1 uplift: 85% of the 2023-24 rate cap (2.975%), which is greater than 1.85% or $26/week."))
        rows_2024.append(standard_row(band, level, rate_2024, notes="Calculated from September 2023 rate using the 2024 clause 7.1.1 uplift: 85% of the 2024-25 rate cap (2.3375%), which is greater than 2.00% or $26/week."))
    return {
        "2022-09-01": rows_2022,
        "2023-09-01": rows_2023,
        "2024-09-01": rows_2024,
    }


def gannawarra_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    raw = {
        "2022-07-01": [
            ("1", "A", 1024.79), ("1", "B", 1035.64), ("1", "C", 1046.38), ("1", "D", 1057.11),
            ("2", "A", 1072.81), ("2", "B", 1086.52), ("2", "C", 1101.68),
            ("3", "A", 1115.94), ("3", "B", 1141.86), ("3", "C", 1169.53), ("3", "D", 1191.45),
            ("4", "A", 1203.05), ("4", "B", 1228.07), ("4", "C", 1259.74), ("4", "D", 1283.13),
            ("5", "A", 1321.18), ("5", "B", 1388.20), ("5", "C", 1460.61), ("5", "D", 1529.49),
            ("6", "A", 1605.67), ("6", "B", 1676.98), ("6", "C", 1748.51),
            ("7", "A", 1801.94), ("7", "B", 1870.00), ("7", "C", 1941.32), ("7", "D", 2012.85),
            ("8", "A", 2091.36), ("8", "B", 2169.87), ("8", "C", 2253.24), ("8", "D", 2341.27),
        ],
        "2023-07-01": [
            ("1", "A", 1054.79), ("1", "B", 1065.64), ("1", "C", 1076.38), ("1", "D", 1087.11),
            ("2", "A", 1102.81), ("2", "B", 1116.52), ("2", "C", 1131.68),
            ("3", "A", 1145.94), ("3", "B", 1171.86), ("3", "C", 1199.53), ("3", "D", 1221.45),
            ("4", "A", 1233.13), ("4", "B", 1258.77), ("4", "C", 1291.23), ("4", "D", 1315.21),
            ("5", "A", 1354.20), ("5", "B", 1422.90), ("5", "C", 1497.12), ("5", "D", 1567.73),
            ("6", "A", 1645.82), ("6", "B", 1718.91), ("6", "C", 1792.23),
            ("7", "A", 1846.99), ("7", "B", 1916.75), ("7", "C", 1989.85), ("7", "D", 2063.17),
            ("8", "A", 2143.64), ("8", "B", 2224.11), ("8", "C", 2309.57), ("8", "D", 2399.80),
        ],
        "2024-07-01": [
            ("1", "A", 1084.79), ("1", "B", 1095.64), ("1", "C", 1106.38), ("1", "D", 1117.11),
            ("2", "A", 1132.81), ("2", "B", 1146.52), ("2", "C", 1161.68),
            ("3", "A", 1175.94), ("3", "B", 1201.86), ("3", "C", 1229.53), ("3", "D", 1251.99),
            ("4", "A", 1263.95), ("4", "B", 1290.24), ("4", "C", 1323.51), ("4", "D", 1348.09),
            ("5", "A", 1388.06), ("5", "B", 1458.48), ("5", "C", 1534.55), ("5", "D", 1606.92),
            ("6", "A", 1686.96), ("6", "B", 1761.88), ("6", "C", 1837.03),
            ("7", "A", 1893.17), ("7", "B", 1964.67), ("7", "C", 2039.59), ("7", "D", 2114.75),
            ("8", "A", 2197.23), ("8", "B", 2279.72), ("8", "C", 2367.31), ("8", "D", 2459.79),
        ],
    }
    return {date: [standard_row(band, level, weekly) for band, level, weekly in rows] for date, rows in raw.items()}


def canonical_payload(
    *,
    ae_id: str,
    source_name: str,
    council_name: str,
    fwc: dict[str, Any],
    overview: dict[str, Any],
    pay_tables: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    periods = []
    rule_by_date = {rule["effective_date"]: rule for rule in rules}
    for table in pay_tables:
        effective_from = table["effective_from"]
        periods.append(
            {
                "effective_from": effective_from,
                "to_date": table["to_date"],
                "pay_table": table,
                "pay_table_governed_at": generated_at,
                "uplift_rule": governed_rule(rule_by_date[effective_from]),
                "uplift_rule_governed_at": generated_at,
                "progression_basis": "not_reviewed",
                "progression_rule_status": "not_reviewed",
            }
        )
    return {
        "agreement_id": ae_id,
        "source_name": source_name,
        "fwc": fwc,
        "overview": overview,
        "sections": {
            "overview": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": "Prior-agreement 2025 gap processing",
                "data": overview,
                "notes": "Processed to restore predecessor agreement coverage for early 2025.",
            },
            "pay_tables": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": "Prior-agreement 2025 gap processing",
                "tables": pay_tables,
                "notes": "Focused extraction of the standard Band 1-8 weekly pay matrix for periods covering 2025.",
            },
            "uplift_rules": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": "Prior-agreement 2025 gap processing",
                "data": {
                    "accepted": {
                        "document": {
                            "ae_id": ae_id,
                            "council": council_name,
                            "covered_councils": [council_name],
                            "multi_employer": False,
                            "timing_pattern": "annual_fixed_date",
                            "rules": rules,
                            "notes": "Rules captured from the wage uplift clause for predecessor agreement coverage.",
                        },
                        "suggestion_id": "prior_2025_gap_processing",
                        "prompt_version": "local_processor_v1",
                        "model": "codex",
                        "code_git_sha": "unknown",
                    }
                },
                "notes": "",
            },
            "uplifts": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": "Prior-agreement 2025 gap processing",
                "data": {"periods": periods},
                "notes": "Governed pay tables and uplift rules promoted by local processor from frozen PDF evidence.",
            },
        },
    }


def repair_warrnambool_2024_to_date() -> dict[str, Any]:
    path = CANONICAL_DIR / "ae518214.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    changed_paths: list[str] = []

    for index, table in enumerate(((data.get("sections") or {}).get("pay_tables") or {}).get("tables") or []):
        if table.get("effective_from") == "2024-07-01" and table.get("to_date") != "2025-06-30":
            table["to_date"] = "2025-06-30"
            changed_paths.append(f"sections.pay_tables.tables[{index}].to_date")

    periods = ((((data.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
    for index, period in enumerate(periods):
        if period.get("effective_from") != "2024-07-01":
            continue
        if period.get("to_date") != "2025-06-30":
            period["to_date"] = "2025-06-30"
            changed_paths.append(f"sections.uplifts.data.periods[{index}].to_date")
        pay_table = period.get("pay_table")
        if isinstance(pay_table, dict) and pay_table.get("to_date") != "2025-06-30":
            pay_table["to_date"] = "2025-06-30"
            changed_paths.append(f"sections.uplifts.data.periods[{index}].pay_table.to_date")

    if changed_paths:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    return {"agreement_id": "ae518214", "path": str(path.relative_to(ROOT)), "changed_paths": changed_paths}


def build() -> dict[str, Any]:
    generated_at = now_iso()
    candidates = candidate_by_ae()
    outputs: list[dict[str, Any]] = []

    configs = [
        {
            "ae_id": "ae518669",
            "council_name": "Gannawarra Shire Council",
            "overview": {
                "page_count": 148,
                "likely_pay_table_pages": [122],
                "likely_uplift_pages": [38],
                "estimated_earliest_commencing": "2022-07-01",
                "estimated_latest_commencing": "2024-07-01",
                "document_structure_notes": "Standard Band 1-8 wage rates are in Appendix 7. The PDF text layer omits the table cells, so the table was read from the rendered source page.",
                "red_flags": ["Appendix 7 table is image-only in the PDF text layer."],
            },
            "rows_by_period": gannawarra_rows_by_period(),
            "table_title": "All Staff (except Depot, Kindergarten Teachers, Nurses and Pool Employees)",
            "source_pages": [122],
            "source_clause": "Appendix 7",
            "rules": [
                accepted_rule(label="First Increase", effective_date="2022-07-01", timing_clause="Payable for the first full pay period on or after 1st July 2022", quantum="2.0% or $25, whichever is greater", quantum_type="pct_OR_floor", source_page=38, source_clause="Clause 11", pct_component=2.0, dollar_component=25.0, resolved_pct=2.0),
                accepted_rule(label="Second Increase", effective_date="2023-07-01", timing_clause="Payable for the first full pay period on or after 1st July 2023", quantum="2.5% or $30, whichever is greater", quantum_type="pct_OR_floor", source_page=38, source_clause="Clause 11", pct_component=2.5, dollar_component=30.0, resolved_pct=2.5),
                accepted_rule(label="Third Increase", effective_date="2024-07-01", timing_clause="Payable for the first full pay period on or after 1st July 2024", quantum="2.5% or $30, whichever is greater", quantum_type="pct_OR_floor", source_page=38, source_clause="Clause 11", pct_component=2.5, dollar_component=30.0, resolved_pct=2.5),
            ],
        },
        {
            "ae_id": "ae520153",
            "council_name": "Hindmarsh Shire Council",
            "overview": {
                "page_count": 90,
                "likely_pay_table_pages": [72],
                "likely_uplift_pages": [10],
                "estimated_earliest_commencing": "2022-07-01",
                "estimated_latest_commencing": "2024-07-01",
                "document_structure_notes": "Clause 75 contains the Band 1-8 classification table with weekly rates for the 2022, 2023 and 2024 increases.",
                "red_flags": [],
            },
            "rows_by_period": parse_hindmarsh_rows(),
            "table_title": "Classification Table - Bands 1 to 8",
            "source_pages": [72],
            "source_clause": "Clause 75",
            "rules": [
                accepted_rule(label="1 July 2022", effective_date="2022-07-01", timing_clause="First full pay period on or after 1 July 2022", quantum="2.5%", quantum_type="percentage", source_page=10, source_clause="Clause 7.2", pct_component=2.5, resolved_pct=2.5),
                accepted_rule(label="1 July 2023", effective_date="2023-07-01", timing_clause="First full pay period on or after 1 July 2023", quantum="2.75%", quantum_type="percentage", source_page=10, source_clause="Clause 7.2", pct_component=2.75, resolved_pct=2.75),
                accepted_rule(label="1 July 2024", effective_date="2024-07-01", timing_clause="First full pay period on or after 1 July 2024", quantum="2.75%", quantum_type="percentage", source_page=10, source_clause="Clause 7.2", pct_component=2.75, resolved_pct=2.75),
            ],
        },
        {
            "ae_id": "ae516762",
            "council_name": "Whitehorse City Council",
            "overview": {
                "page_count": 192,
                "likely_pay_table_pages": [66],
                "likely_uplift_pages": [34],
                "estimated_earliest_commencing": "2022-09-01",
                "estimated_latest_commencing": "2024-09-01",
                "document_structure_notes": "Appendix 4 provides the September 2022 Band 1-8 pay scale. Clause 7.1.1 provides explicit September 2023 and September 2024 uplift formulas.",
                "red_flags": ["2023 and 2024 standard band rates are calculated from the source table and explicit uplift clause rather than printed as separate tables."],
            },
            "rows_by_period": whitehorse_rows_by_period(),
            "table_title": "Rates Table",
            "source_pages": [66],
            "source_clause": "Appendix 4; Clause 7.1.1",
            "rules": [
                accepted_rule(label="September 2022", effective_date="2022-09-01", timing_clause="First pay period on or after 1 September 2022", quantum="1.75% or $26/week, whichever is greater", quantum_type="pct_OR_floor", source_page=34, source_clause="Clause 7.1.1", pct_component=1.75, dollar_component=26.0, resolved_pct=1.75),
                accepted_rule(label="September 2023", effective_date="2023-09-01", timing_clause="First pay period on or after 1 September 2023", quantum="1.85% or $26/week or 85% of the rate cap, whichever is greater", quantum_type="conditional", source_page=34, source_clause="Clause 7.1.1", pct_component=1.85, dollar_component=26.0, resolved_pct=2.975, resolved_basis="external_rate_cap_85pct"),
                accepted_rule(label="September 2024", effective_date="2024-09-01", timing_clause="First pay period on or after 1 September 2024", quantum="2.00% or $26/week or 85% of the rate cap, whichever is greater", quantum_type="conditional", source_page=34, source_clause="Clause 7.1.1", pct_component=2.0, dollar_component=26.0, resolved_pct=2.3375, resolved_basis="external_rate_cap_85pct"),
            ],
        },
    ]

    for config in configs:
        ae_id = config["ae_id"]
        candidate = candidates[ae_id]
        pay_tables = [
            period_table(
                title=f"{config['table_title']} - {date}",
                source_pages=config["source_pages"],
                source_clause=config["source_clause"],
                effective_from=date,
                rows=rows,
            )
            for date, rows in config["rows_by_period"].items()
        ]
        payload = canonical_payload(
            ae_id=ae_id,
            source_name=candidate["Agreement Title"],
            council_name=config["council_name"],
            fwc={
                "lga_code": candidate.get("lga_code"),
                **candidate_dates(ae_id, candidates),
            },
            overview=config["overview"],
            pay_tables=pay_tables,
            rules=config["rules"],
            generated_at=generated_at,
        )
        output_path = CANONICAL_DIR / f"{ae_id}.yaml"
        output_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
        outputs.append({"agreement_id": ae_id, "path": str(output_path.relative_to(ROOT)), "periods": len(pay_tables), "rows": sum(len(table["rows"]) for table in pay_tables)})

    repair = repair_warrnambool_2024_to_date()
    return {"generated_at": generated_at, "outputs": outputs, "repairs": [repair]}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
