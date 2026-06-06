from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
CANONICAL_DIR = ROOT / "canonical"
CANDIDATES_JSON = ROOT / "data" / "bronze" / "phase1_source_build" / "candidate_agreements" / "candidate_agreements.json"

PROCESS_LABEL = "Screenshot-history predecessor agreement processing"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def excel_serial_date(value: Any) -> str | None:
    try:
        serial = int(float(value))
    except (TypeError, ValueError):
        return None
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()


def money(value: str) -> float:
    return float(re.sub(r"[$,\s]", "", value))


def money_values(text: str) -> list[float]:
    return [money(match.group(0)) for match in re.finditer(r"\$?\s*\d[\d,]*\.\d{2}", text)]


def page_count(ae_id: str) -> int | None:
    path = CACHE_DIR / ae_id / "pages.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return len(payload) if isinstance(payload, list) else None


def read_cache_page(ae_id: str, page_number: int) -> str:
    return (CACHE_DIR / ae_id / f"page_{page_number:04d}.txt").read_text(encoding="utf-8")


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
    to_date: str,
    rows: list[dict[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    table = {
        "table_title": title,
        "source_pages": source_pages,
        "source_clause": source_clause,
        "effective_from": effective_from,
        "rate_kind": "weekly",
        "to_date": to_date,
        "date_snapped": False,
        "snap_basis": None,
        "snap_note": None,
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
    resolved_basis: str = "source_table",
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
        "resolved_basis": rule.get("resolved_basis") or "source_table",
    }


def candidate_by_ae() -> dict[str, dict[str, Any]]:
    rows = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    return {str(row.get("Agreement ID") or "").lower(): row for row in rows}


def candidate_dates(ae_id: str, candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate = candidates[ae_id]
    return {
        "lga_code": candidate.get("lga_code") or None,
        "matter_number": candidate.get("Matter Number") or None,
        "print_id": candidate.get("Print ID") or None,
        "operative_date": excel_serial_date(candidate.get("Operative Date")),
        "expiry_date": excel_serial_date(candidate.get("Expiry Date")),
        "version": candidate.get("Version") or None,
        "superseded_by_ae_id": str(candidate.get("superseded_by_ae_id") or "").lower() or None,
    }


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
                "source_ref": PROCESS_LABEL,
                "data": overview,
                "notes": "Processed to restore predecessor agreement coverage for the screenshot council batch.",
            },
            "pay_tables": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": PROCESS_LABEL,
                "tables": pay_tables,
                "notes": "Focused extraction of the standard Band 1-8 weekly pay matrix.",
            },
            "uplift_rules": {
                "status": "done",
                "completed_at": generated_at,
                "source_ref": PROCESS_LABEL,
                "data": {
                    "accepted": {
                        "document": {
                            "ae_id": ae_id,
                            "council": council_name,
                            "covered_councils": [council_name],
                            "multi_employer": False,
                            "timing_pattern": "annual_fixed_date",
                            "rules": rules,
                            "notes": "Rules captured from source pay schedules and wage uplift clauses.",
                        },
                        "suggestion_id": "screenshot_history_processing",
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
                "source_ref": PROCESS_LABEL,
                "data": {"periods": periods},
                "notes": "Governed pay tables and uplift rules promoted by local processor from frozen PDF evidence.",
            },
        },
    }


def grid_rows(grid: list[tuple[int, list[float | None]]], levels: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for band, rates in grid:
        for index, weekly in enumerate(rates):
            if weekly is not None:
                rows.append(standard_row(str(band), levels[index], weekly))
    return rows


def moonee_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    text = read_cache_page("ae515061", 61)
    chunks = re.split(r"\bBAND", text)
    rows_by_code: list[tuple[str, str, list[float]]] = []
    for chunk in chunks[1:]:
        match = re.match(r"([1-8])([A-E])\s+", chunk)
        if not match:
            continue
        amounts = money_values(chunk)
        if len(amounts) < 9:
            raise ValueError(f"Moonee Valley {match.group(1)}{match.group(2)} had {len(amounts)} values")
        rows_by_code.append((match.group(1), match.group(2), [amounts[1], amounts[4], amounts[7]]))
    if len(rows_by_code) != 38:
        raise ValueError(f"Moonee Valley expected 38 rows, found {len(rows_by_code)}")
    dates = ["2021-12-01", "2022-12-01", "2023-12-01"]
    return {
        date: [standard_row(band, level, rates[index]) for band, level, rates in rows_by_code]
        for index, date in enumerate(dates)
    }


def band_block_rows(ae_id: str, page_number: int) -> list[dict[str, Any]]:
    lines = [line.strip() for line in read_cache_page(ae_id, page_number).splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not re.fullmatch(r"[1-8]", line):
            continue
        try:
            weekly_index = next(i for i in range(index + 1, len(lines)) if lines[i].lower() == "weekly")
            annual_index = next(i for i in range(weekly_index + 1, len(lines)) if lines[i].lower() == "annually")
        except StopIteration:
            continue
        rates = [money(value) for value in lines[weekly_index + 1 : annual_index] if re.search(r"\d", value)]
        if len(rates) not in {3, 4}:
            continue
        for level_index, weekly in enumerate(rates):
            rows.append(standard_row(line, ["A", "B", "C", "D"][level_index], weekly))
    if len(rows) != 30:
        raise ValueError(f"{ae_id} page {page_number} expected 30 rows, found {len(rows)}")
    return rows


def coded_rows(raw_rows: list[tuple[str, float, float, float]]) -> dict[str, list[dict[str, Any]]]:
    dates = ["2020-07-01", "2021-07-01", "2022-07-01"]
    output = {date: [] for date in dates}
    for code, *rates in raw_rows:
        match = re.fullmatch(r"([1-8])([A-E])", code)
        if not match:
            raise ValueError(f"Invalid band-level code: {code}")
        for date, rate in zip(dates, rates, strict=True):
            output[date].append(standard_row(match.group(1), match.group(2), rate))
    return output


def wellington_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    grids = {
        "2019-11-04": [[1, [1019.80, 1029.10, 1038.30, 1047.84]], [2, [1061.67, 1074.39, 1088.23, None]], [3, [1101.84, 1127.13, 1153.06, 1171.98]], [4, [1181.82, 1202.61, 1229.63, 1249.91]], [5, [1282.72, 1344.05, 1411.01, 1474.41]], [6, [1547.04, 1615.27, 1683.93, None]], [7, [1733.99, 1801.33, 1870.58, 1940.17]], [8, [2016.50, 2092.73, 2173.81, 2259.53]]],
        "2020-11-02": [[1, [1044.80, 1054.10, 1063.30, 1072.84]], [2, [1086.67, 1099.39, 1113.23, None]], [3, [1126.84, 1152.13, 1178.06, 1196.98]], [4, [1206.82, 1227.61, 1254.63, 1274.91]], [5, [1308.38, 1370.94, 1439.23, 1503.89]], [6, [1577.99, 1647.57, 1717.61, None]], [7, [1768.67, 1837.36, 1907.99, 1978.97]], [8, [2056.83, 2134.59, 2217.28, 2304.72]]],
        "2021-11-01": [[1, [1069.80, 1079.10, 1088.30, 1097.84]], [2, [1111.67, 1124.39, 1138.23, None]], [3, [1151.84, 1177.13, 1203.06, 1221.98]], [4, [1231.82, 1252.61, 1279.72, 1300.41]], [5, [1334.54, 1398.35, 1468.01, 1533.97]], [6, [1609.54, 1680.52, 1751.96, None]], [7, [1804.04, 1874.11, 1946.15, 2018.55]], [8, [2097.97, 2177.28, 2261.63, 2350.81]]],
    }
    return {date: grid_rows([(band, rates) for band, rates in grid], ["A", "B", "C", "D"]) for date, grid in grids.items()}


def mildura_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    base = grid_rows([
        (1, [1016.54, 1026.88, 1037.11, 1047.34]), (2, [1062.14, 1074.72, 1088.92, None]), (3, [1102.01, 1126.76, 1154.36, 1176.76]), (4, [1188.78, 1215.33, 1250.07, 1275.40]), (5, [1314.03, 1378.61, 1446.56, 1513.01]), (6, [1589.31, 1660.69, 1732.37, None]), (7, [1784.67, 1853.99, 1925.40, 1997.04]), (8, [2075.65, 2154.28, 2237.80, 2325.95]),
    ], ["A", "B", "C", "D"])
    rows_2020 = [{**row, "weekly_rate": round(float(row["weekly_rate"]) * 1.02, 2), "notes": "Calculated from prior period by applying the 2% increase under Clause 16."} for row in base]
    rows_2021 = [{**row, "weekly_rate": round(float(row["weekly_rate"]) * 1.02, 2), "notes": "Calculated from prior period by applying the 2% increase under Clause 16."} for row in rows_2020]
    return {"2019-11-22": base, "2020-11-03": rows_2020, "2021-11-03": rows_2021}


def yarra_ranges_rows_by_period() -> dict[str, list[dict[str, Any]]]:
    base = grid_rows([
        (1, [1113.13, 1123.17, 1133.10, 1143.04, 1153.43]), (2, [1157.40, 1169.60, 1182.88, None, 1193.26]), (3, [1195.08, 1217.75, 1243.09, 1262.56, 1276.42]), (4, [1274.19, 1298.89, 1332.96, 1359.84, 1380.73]), (5, [1402.45, 1478.42, 1558.23, 1632.78, 1673.92]), (6, [1715.07, 1792.16, 1869.45, None, 1897.70]), (7, [1925.93, 2000.73, 2077.78, 2155.10, 2197.53]), (8, [2239.92, 2324.79, 2414.88, 2510.00, 2529.33]),
    ], ["A", "B", "C", "D", "E"])
    rows_2022 = [{**row, "weekly_rate": round(float(row["weekly_rate"]) * 1.0125, 2), "notes": "Calculated from prior period under Clause 5.1: 2022-23 rate cap 1.75% less 0.5 percentage point SG increase = 1.25%."} for row in base]
    rows_2023 = [{**row, "weekly_rate": round(float(row["weekly_rate"]) * 1.03, 2), "notes": "Calculated from prior period under Clause 5.1: 2023-24 rate cap 3.50% less 0.5 percentage point SG increase = 3.00%."} for row in rows_2022]
    return {"2021-10-01": base, "2022-10-01": rows_2022, "2023-10-01": rows_2023}


def build() -> dict[str, Any]:
    generated_at = now_iso()
    candidates = candidate_by_ae()
    outputs: list[dict[str, Any]] = []

    configs = [
        {
            "ae_id": "ae515061",
            "council_name": "Moonee Valley City Council",
            "rows_by_period": moonee_rows_by_period(),
            "to_dates": {"2021-12-01": "2022-11-30", "2022-12-01": "2023-11-30", "2023-12-01": "2024-11-30"},
            "table_title": "Classification Table - Bands 1 to 8",
            "source_pages": [61],
            "source_clause": "Clause 83",
            "overview": {
                "page_count": page_count("ae515061"),
                "likely_pay_table_pages": [61],
                "likely_uplift_pages": [61],
                "estimated_earliest_commencing": "2021-12-01",
                "estimated_latest_commencing": "2023-12-01",
                "document_structure_notes": "Clause 83 contains source weekly rates for December 2021, December 2022 and December 2023.",
                "red_flags": [],
            },
            "rules": [
                accepted_rule(label="December 2021", effective_date="2021-12-01", timing_clause="December 2021 source table", quantum="source table rate", quantum_type="source_table", source_page=61, source_clause="Clause 83"),
                accepted_rule(label="December 2022", effective_date="2022-12-01", timing_clause="December 2022 source table", quantum="source table rate; footnote adjusts if rate cap exceeds 1.5%", quantum_type="source_table", source_page=61, source_clause="Clause 83"),
                accepted_rule(label="December 2023", effective_date="2023-12-01", timing_clause="December 2023 source table", quantum="source table rate; footnote adjusts if rate cap exceeds 1.5%", quantum_type="source_table", source_page=61, source_clause="Clause 83"),
            ],
        },
        {
            "ae_id": "ae508450",
            "council_name": "Wellington Shire Council",
            "rows_by_period": wellington_rows_by_period(),
            "to_dates": {"2019-11-04": "2020-11-01", "2020-11-02": "2021-10-31", "2021-11-01": "2022-11-13"},
            "table_title": "Base Weekly Wage Rates",
            "source_pages": [9, 10],
            "source_clause": "Section 2.1; Tables A-C",
            "overview": {
                "page_count": page_count("ae508450"),
                "likely_pay_table_pages": [9, 10],
                "likely_uplift_pages": [9],
                "estimated_earliest_commencing": "2019-11-04",
                "estimated_latest_commencing": "2021-11-01",
                "document_structure_notes": "Section 2.1 contains Tables A-C for November 2019, November 2020 and November 2021.",
                "red_flags": [],
            },
            "rules": [
                accepted_rule(label="November 2019", effective_date="2019-11-04", timing_clause="Monday of the first full fortnightly pay period November 2019", quantum="2% or $25 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=9, source_clause="Section 2.1", pct_component=2.0, dollar_component=25.0, resolved_pct=2.0, resolved_basis="source_table"),
                accepted_rule(label="November 2020", effective_date="2020-11-02", timing_clause="Monday of the first full fortnightly pay period November 2020", quantum="2% or $25 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=9, source_clause="Section 2.1", pct_component=2.0, dollar_component=25.0, resolved_pct=2.0, resolved_basis="source_table"),
                accepted_rule(label="November 2021", effective_date="2021-11-01", timing_clause="Monday of the first full fortnightly pay period November 2021", quantum="2% or $25 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=9, source_clause="Section 2.1", pct_component=2.0, dollar_component=25.0, resolved_pct=2.0, resolved_basis="source_table"),
            ],
        },
        {
            "ae_id": "ae508703",
            "council_name": "Mildura Rural City Council",
            "rows_by_period": mildura_rows_by_period(),
            "to_dates": {"2019-11-22": "2020-11-02", "2020-11-03": "2021-11-02", "2021-11-03": "2022-11-02"},
            "table_title": "Appendix 2 Salary Increases - Indoor/Outdoor Staff Banding Levels",
            "source_pages": [50, 51],
            "source_clause": "Clause 16; Appendix 2",
            "overview": {
                "page_count": page_count("ae508703"),
                "likely_pay_table_pages": [50, 51],
                "likely_uplift_pages": [37],
                "estimated_earliest_commencing": "2019-11-22",
                "estimated_latest_commencing": "2021-11-03",
                "document_structure_notes": "Appendix 2 gives the source table effective F/E 22/11/2019. Later periods are calculated from Clause 16's 2% increases.",
                "red_flags": ["2020 and 2021 standard band rates are calculated from explicit uplift clauses rather than printed as separate standard tables."],
            },
            "rules": [
                accepted_rule(label="First instalment", effective_date="2019-11-22", timing_clause="Appendix 2 source table effective F/E 22/11/2019", quantum="source table rate", quantum_type="source_table", source_page=50, source_clause="Appendix 2"),
                accepted_rule(label="Second instalment", effective_date="2020-11-03", timing_clause="First full pay period on or after 3 November 2020", quantum="2%", quantum_type="percentage", source_page=37, source_clause="Clause 16.2", pct_component=2.0, resolved_pct=2.0, resolved_basis="internal_pct"),
                accepted_rule(label="Third instalment", effective_date="2021-11-03", timing_clause="First full pay period on or after 3 November 2021", quantum="2%", quantum_type="percentage", source_page=37, source_clause="Clause 16.3", pct_component=2.0, resolved_pct=2.0, resolved_basis="internal_pct"),
            ],
        },
        {
            "ae_id": "ae513946",
            "council_name": "Mount Alexander Shire Council",
            "rows_by_period": {"2020-09-22": band_block_rows("ae513946", 54), "2021-09-22": band_block_rows("ae513946", 55), "2022-09-22": band_block_rows("ae513946", 56), "2023-09-22": band_block_rows("ae513946", 57)},
            "to_dates": {"2020-09-22": "2021-09-21", "2021-09-22": "2022-09-21", "2022-09-22": "2023-09-21", "2023-09-22": "2024-09-21"},
            "table_title": "Appendix E Pay Schedules",
            "source_pages": [54, 55, 56, 57],
            "source_clause": "Appendix E",
            "overview": {
                "page_count": page_count("ae513946"),
                "likely_pay_table_pages": [54, 55, 56, 57],
                "likely_uplift_pages": [54, 55, 56, 57],
                "estimated_earliest_commencing": "2020-09-22",
                "estimated_latest_commencing": "2023-09-22",
                "document_structure_notes": "Appendix E contains Year 1 to Year 4 weekly rate schedules.",
                "red_flags": [],
            },
            "rules": [
                accepted_rule(label="Year 1", effective_date="2020-09-22", timing_clause="First full pay day on or after 22 September 2020", quantum="1.50% or $23 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=54, source_clause="Appendix E", pct_component=1.5, dollar_component=23.0, resolved_pct=1.5, resolved_basis="source_table"),
                accepted_rule(label="Year 2", effective_date="2021-09-22", timing_clause="First full pay day on or after 22 September 2021", quantum="1.50% or $23 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=55, source_clause="Appendix E", pct_component=1.5, dollar_component=23.0, resolved_pct=1.5, resolved_basis="source_table"),
                accepted_rule(label="Year 3", effective_date="2022-09-22", timing_clause="First full pay day on or after 22 September 2022", quantum="1.50% or $23 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=56, source_clause="Appendix E", pct_component=1.5, dollar_component=23.0, resolved_pct=1.5, resolved_basis="source_table"),
                accepted_rule(label="Year 4", effective_date="2023-09-22", timing_clause="First full pay day on or after 22 September 2023", quantum="1.50% or $23 per week, whichever is greater", quantum_type="pct_OR_floor", source_page=57, source_clause="Appendix E", pct_component=1.5, dollar_component=23.0, resolved_pct=1.5, resolved_basis="source_table"),
            ],
        },
        {
            "ae_id": "ae513237",
            "council_name": "Alpine Shire Council",
            "rows_by_period": {"2020-07-01": band_block_rows("ae513237", 78), "2021-07-01": band_block_rows("ae513237", 79), "2022-07-01": band_block_rows("ae513237", 80)},
            "to_dates": {"2020-07-01": "2021-06-30", "2021-07-01": "2022-06-30", "2022-07-01": "2023-06-30"},
            "table_title": "Appendix 1 Salary Schedules",
            "source_pages": [78, 79, 80],
            "source_clause": "Appendix 1",
            "overview": {
                "page_count": page_count("ae513237"),
                "likely_pay_table_pages": [78, 79, 80],
                "likely_uplift_pages": [78, 79, 80],
                "estimated_earliest_commencing": "2020-07-01",
                "estimated_latest_commencing": "2022-07-01",
                "document_structure_notes": "Appendix 1 provides Year 1 to Year 3 band/level salary schedules from 1 July 2020, 1 July 2021 and 1 July 2022.",
                "red_flags": [],
            },
            "rules": [
                accepted_rule(label="Year 1", effective_date="2020-07-01", timing_clause="Appendix 1 schedule from 1 July 2020", quantum="source table rate", quantum_type="source_table", source_page=78, source_clause="Appendix 1"),
                accepted_rule(label="Year 2", effective_date="2021-07-01", timing_clause="Appendix 1 schedule from 1 July 2021", quantum="source table rate", quantum_type="source_table", source_page=79, source_clause="Appendix 1"),
                accepted_rule(label="Year 3", effective_date="2022-07-01", timing_clause="Appendix 1 schedule from 1 July 2022", quantum="source table rate", quantum_type="source_table", source_page=80, source_clause="Appendix 1"),
            ],
        },
        {
            "ae_id": "ae507026",
            "council_name": "Baw Baw Shire Council",
            "rows_by_period": coded_rows([
                ("1A", 1010.98, 1040.98, 1070.98), ("1B", 1021.26, 1051.26, 1081.26), ("1C", 1031.71, 1061.71, 1091.71), ("1D", 1042.08, 1072.08, 1102.08),
                ("2A", 1057.84, 1087.84, 1117.84), ("2B", 1071.78, 1101.78, 1131.78), ("2C", 1087.44, 1117.44, 1147.44),
                ("3A", 1102.28, 1132.28, 1162.28), ("3B", 1131.18, 1161.18, 1191.18), ("3C", 1163.22, 1193.22, 1223.22), ("3D", 1188.33, 1218.33, 1248.33),
                ("4A", 1201.40, 1231.40, 1261.40), ("4B", 1229.92, 1259.92, 1289.92), ("4C", 1266.63, 1296.63, 1326.63), ("4D", 1293.23, 1323.23, 1353.23),
                ("5A", 1333.94, 1363.94, 1393.94), ("5B", 1403.98, 1433.98, 1463.98), ("5C", 1476.82, 1506.82, 1536.96), ("5D", 1545.45, 1576.36, 1607.89),
                ("6A", 1623.37, 1655.84, 1688.96), ("6B", 1696.32, 1730.25, 1764.86), ("6C", 1769.50, 1804.89, 1840.99),
                ("7A", 1822.95, 1859.41, 1896.60), ("7B", 1893.77, 1931.65, 1970.28), ("7C", 1966.70, 2006.03, 2046.15), ("7D", 2039.89, 2080.69, 2122.30),
                ("8A", 2120.18, 2162.58, 2205.83), ("8B", 2200.49, 2244.50, 2289.39), ("8C", 2285.77, 2331.49, 2378.12), ("8D", 2375.82, 2423.34, 2471.81),
            ]),
            "to_dates": {"2020-07-01": "2021-06-30", "2021-07-01": "2022-06-30", "2022-07-01": "2023-06-30"},
            "table_title": "Appendix B Weekly Rates of Pay",
            "source_pages": [83],
            "source_clause": "Appendix B",
            "overview": {
                "page_count": page_count("ae507026"),
                "likely_pay_table_pages": [83],
                "likely_uplift_pages": [83],
                "estimated_earliest_commencing": "2020-07-01",
                "estimated_latest_commencing": "2022-07-01",
                "document_structure_notes": "Appendix B contains weekly rates of pay for 1 July 2020, 1 July 2021 and 1 July 2022.",
                "red_flags": [],
            },
            "rules": [
                accepted_rule(label="1 July 2020", effective_date="2020-07-01", timing_clause="1 July 2020", quantum="2% or $30, whichever is greater", quantum_type="pct_OR_floor", source_page=83, source_clause="Appendix B", pct_component=2.0, dollar_component=30.0, resolved_pct=2.0, resolved_basis="source_table"),
                accepted_rule(label="1 July 2021", effective_date="2021-07-01", timing_clause="1 July 2021", quantum="2% or $30, whichever is greater", quantum_type="pct_OR_floor", source_page=83, source_clause="Appendix B", pct_component=2.0, dollar_component=30.0, resolved_pct=2.0, resolved_basis="source_table"),
                accepted_rule(label="1 July 2022", effective_date="2022-07-01", timing_clause="1 July 2022", quantum="2% or $30, whichever is greater", quantum_type="pct_OR_floor", source_page=83, source_clause="Appendix B", pct_component=2.0, dollar_component=30.0, resolved_pct=2.0, resolved_basis="source_table"),
            ],
        },
        {
            "ae_id": "ae514112",
            "council_name": "Yarra Ranges Shire Council",
            "rows_by_period": yarra_ranges_rows_by_period(),
            "to_dates": {"2021-10-01": "2022-09-30", "2022-10-01": "2023-09-30", "2023-10-01": "2024-09-30"},
            "table_title": "Yarra Ranges Council - Rates of Pay (Weekly)",
            "source_pages": [182],
            "source_clause": "Clause 5.1; Section 9.1",
            "overview": {
                "page_count": 217,
                "likely_pay_table_pages": [182],
                "likely_uplift_pages": [51, 52],
                "estimated_earliest_commencing": "2021-10-01",
                "estimated_latest_commencing": "2023-10-01",
                "document_structure_notes": "The FWC-frozen PDF for AE514112 is an approval decision only. Pay data was sourced from the full official Yarra Ranges Council-published agreement PDF.",
                "official_council_pdf_url": "https://www.yarraranges.vic.gov.au/files/assets/public/v/1/webdocuments/council/careers/agreement-yarra-ranges-council-consolidated-enterprise-agreement-2021.pdf",
                "red_flags": ["Local FWC freeze is decision-only; source pay table is from the official council PDF."],
            },
            "rules": [
                accepted_rule(label="1 October 2021", effective_date="2021-10-01", timing_clause="First full pay period commencing on or after 1 October 2021", quantum="source table rate", quantum_type="source_table", source_page=182, source_clause="Clause 5.1; Section 9.1"),
                accepted_rule(label="1 October 2022", effective_date="2022-10-01", timing_clause="First full pay period commencing on or after 1 October 2022", quantum="Average Rate Cap less SG increase: 1.75% - 0.5% = 1.25%", quantum_type="external_rate_cap_less_sg", source_page=51, source_clause="Clause 5.1", pct_component=1.25, resolved_pct=1.25, resolved_basis="external_rate_cap_less_sg"),
                accepted_rule(label="1 October 2023", effective_date="2023-10-01", timing_clause="First full pay period commencing on or after 1 October 2023", quantum="Average Rate Cap less SG increase: 3.50% - 0.5% = 3.00%", quantum_type="external_rate_cap_less_sg", source_page=51, source_clause="Clause 5.1", pct_component=3.0, resolved_pct=3.0, resolved_basis="external_rate_cap_less_sg"),
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
                to_date=config["to_dates"][date],
                rows=rows,
            )
            for date, rows in config["rows_by_period"].items()
        ]
        payload = canonical_payload(
            ae_id=ae_id,
            source_name=candidate.get("Agreement Title") or config["table_title"],
            council_name=config["council_name"],
            fwc=candidate_dates(ae_id, candidates),
            overview=config["overview"],
            pay_tables=pay_tables,
            rules=config["rules"],
            generated_at=generated_at,
        )
        output_path = CANONICAL_DIR / f"{ae_id}.yaml"
        output_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
        outputs.append(
            {
                "agreement_id": ae_id,
                "path": str(output_path.relative_to(ROOT)),
                "periods": len(pay_tables),
                "rows": sum(len(table["rows"]) for table in pay_tables),
            }
        )

    return {"generated_at": generated_at, "outputs": outputs}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
