from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATAMART_DIR = ROOT / "data" / "datamarts"
CANONICAL_DIR = ROOT / "canonical"
OUTPUT_JSON = DATAMART_DIR / "pay_horizon_coverage_audit.json"
OUTPUT_MD = DATAMART_DIR / "pay_horizon_coverage_audit.md"


def read_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("rows") or []


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value.replace("'", '"'))
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            pass
        return [item.strip().strip("'\"") for item in value.strip("[]").split(",") if item.strip()]
    return []


def canonical_pay_signals(agreement_ids: list[str]) -> dict[str, Any]:
    signals = {
        "canonical_files_present": 0,
        "governed_pay_period_count": 0,
        "raw_pay_table_section_present": False,
        "raw_weekly_rate_present": False,
    }
    for agreement_id in agreement_ids:
        path = CANONICAL_DIR / f"{agreement_id}.yaml"
        if not path.exists():
            continue
        signals["canonical_files_present"] += 1
        text = path.read_text(encoding="utf-8")
        signals["raw_weekly_rate_present"] = signals["raw_weekly_rate_present"] or "weekly_rate" in text
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        sections = data.get("sections") or {}
        pay_tables = sections.get("pay_tables") or {}
        if pay_tables:
            signals["raw_pay_table_section_present"] = True
        periods = (((sections.get("uplifts") or {}).get("data") or {}).get("periods") or [])
        for period in periods:
            if isinstance(period, dict) and isinstance(period.get("pay_table"), dict) and period.get("pay_table_governed_at"):
                signals["governed_pay_period_count"] += 1
    return signals


def curve_counts() -> dict[str, int]:
    sqlite_path = DATAMART_DIR / "pay_service_horizon_curve_view.sqlite"
    if sqlite_path.exists():
        connection = sqlite3.connect(sqlite_path)
        try:
            return {
                str(council_id): int(count)
                for council_id, count in connection.execute(
                    "SELECT selected_council_id, COUNT(*) FROM curve_rows GROUP BY selected_council_id"
                )
                if council_id
            }
        finally:
            connection.close()
    rows = read_json_rows(DATAMART_DIR / "pay_service_horizon_curve_view.json")
    counts: dict[str, int] = {}
    for row in rows:
        council_id = str(row.get("selected_council_id") or "")
        if council_id:
            counts[council_id] = counts.get(council_id, 0) + 1
    return counts


def main() -> int:
    DATAMART_DIR.mkdir(parents=True, exist_ok=True)
    profile_rows = read_json_rows(DATAMART_DIR / "council_profile_mart.json")
    pay_rows = read_csv_rows(ROOT / "data" / "governed_canonical" / "pay_rows.csv")
    range_rows = read_csv_rows(DATAMART_DIR / "pay_range_summary_mart.csv")
    distribution_rows = read_csv_rows(DATAMART_DIR / "pay_distribution_point_mart.csv")

    pay_row_counts: dict[str, int] = {}
    for row in pay_rows:
        key = str(row.get("council_key") or "")
        if key:
            pay_row_counts[key] = pay_row_counts.get(key, 0) + 1
    range_counts: dict[str, int] = {}
    for row in range_rows:
        key = str(row.get("canonical_council_id") or "")
        if key:
            range_counts[key] = range_counts.get(key, 0) + 1
    distribution_counts: dict[str, int] = {}
    for row in distribution_rows:
        key = str(row.get("canonical_council_id") or "")
        if key:
            distribution_counts[key] = distribution_counts.get(key, 0) + 1
    curve_row_counts = curve_counts()

    rows = []
    for profile in sorted(profile_rows, key=lambda row: str(row.get("canonical_council_name") or "")):
        council_key = str(profile.get("council_key") or profile.get("canonical_council_id") or "")
        agreement_ids = as_list(profile.get("canonical_agreement_ids"))
        signals = canonical_pay_signals(agreement_ids)
        has_curve = curve_row_counts.get(council_key, 0) > 0
        if has_curve:
            coverage_status = "available_in_pay_horizon_curve"
            blocker_reason = None
            next_action = "Use V2 explorer; filter by metric/window/cohort as needed."
        elif signals["canonical_files_present"] and not signals["governed_pay_period_count"]:
            coverage_status = "blocked_missing_governed_pay_rows"
            blocker_reason = "Canonical agreement exists, but no governed pay table period with pay_table_governed_at is available."
            next_action = "Review/promote pay table rows into sections.uplifts.data.periods[].pay_table with pay_table_governed_at."
        else:
            coverage_status = "blocked_missing_pay_source"
            blocker_reason = "No usable governed pay source was found for V2 pay-horizon modelling."
            next_action = "Confirm source document coverage, then review/promote pay table rows."
        rows.append(
            {
                "council_key": council_key,
                "canonical_council_name": profile.get("canonical_council_name"),
                "canonical_agreement_ids": agreement_ids,
                "canonical_files_present": signals["canonical_files_present"],
                "governed_pay_period_count": signals["governed_pay_period_count"],
                "raw_pay_table_section_present": signals["raw_pay_table_section_present"],
                "raw_weekly_rate_present": signals["raw_weekly_rate_present"],
                "pay_row_count": pay_row_counts.get(council_key, 0),
                "pay_range_summary_count": range_counts.get(council_key, 0),
                "pay_distribution_point_count": distribution_counts.get(council_key, 0),
                "pay_service_horizon_curve_row_count": curve_row_counts.get(council_key, 0),
                "coverage_status": coverage_status,
                "blocker_reason": blocker_reason,
                "recommended_next_action": next_action,
            }
        )

    summary = {
        "schema_version": "pay_horizon_coverage_audit.v1",
        "total_councils": len(rows),
        "councils_with_governed_pay_rows": sum(1 for row in rows if row["pay_row_count"] > 0),
        "councils_with_curve_rows": sum(1 for row in rows if row["pay_service_horizon_curve_row_count"] > 0),
        "blocked_councils": sum(1 for row in rows if row["coverage_status"].startswith("blocked")),
        "blocked_missing_governed_pay_rows": [
            row["council_key"]
            for row in rows
            if row["coverage_status"] == "blocked_missing_governed_pay_rows"
        ],
    }
    payload = {
        **summary,
        "rows": rows,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lines = [
        "# Pay Horizon Coverage Audit",
        "",
        f"- Total councils: `{summary['total_councils']}`",
        f"- Councils with governed pay rows: `{summary['councils_with_governed_pay_rows']}`",
        f"- Councils with V2 curve rows: `{summary['councils_with_curve_rows']}`",
        f"- Blocked councils: `{summary['blocked_councils']}`",
        "",
        "## Blocked Councils",
        "",
    ]
    blocked = [row for row in rows if row["coverage_status"].startswith("blocked")]
    if blocked:
        for row in blocked:
            lines.extend(
                [
                    f"### {row['canonical_council_name']} (`{row['council_key']}`)",
                    f"- Agreement IDs: `{', '.join(row['canonical_agreement_ids'])}`",
                    f"- Raw pay table section present: `{row['raw_pay_table_section_present']}`",
                    f"- Raw weekly rate present: `{row['raw_weekly_rate_present']}`",
                    f"- Blocker: {row['blocker_reason']}",
                    f"- Next action: {row['recommended_next_action']}",
                    "",
                ]
            )
    else:
        lines.append("No blocked councils.")
    OUTPUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
