#!/usr/bin/env python3
"""One-shot migration: apply snap_rule_dates_to_tables to every existing canonical.

Context: commit ca5b136 added rule-date snapping to api_pay_save. This script
retroactively applies the same snap to all 77 existing canonicals without
round-tripping through the HTTP endpoint. Idempotent — safe to rerun.

Run once from the project root:
    python scripts/backfill_rule_date_snap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from benchmarking_data_factory.uplift_rules import snap_rule_dates_to_tables  # noqa: E402

CANONICAL_DIR = ROOT / "canonical"


def main() -> int:
    total = 0
    touched = 0
    total_snaps = 0
    total_restores = 0
    total_warnings = 0
    per_file_summary: list[tuple[str, dict]] = []

    for path in sorted(CANONICAL_DIR.glob("*.yaml")):
        total += 1
        raw = path.read_text(encoding="utf-8")
        canonical = yaml.safe_load(raw)
        if not isinstance(canonical, dict):
            continue

        summary = snap_rule_dates_to_tables(canonical)
        changed = bool(summary["snapped"] or summary["restored"])
        if summary["warnings"]:
            total_warnings += len(summary["warnings"])
            per_file_summary.append((path.name, summary))
        if not changed:
            continue

        touched += 1
        total_snaps += len(summary["snapped"])
        total_restores += len(summary["restored"])
        per_file_summary.append((path.name, summary))

        # Write back with same dumper settings the app uses
        path.write_text(
            yaml.safe_dump(canonical, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )

    print(f"Canonicals scanned: {total}")
    print(f"Canonicals touched: {touched}")
    print(f"Total rule snaps:   {total_snaps}")
    print(f"Total restores:     {total_restores}")
    print(f"Total warnings:     {total_warnings}")
    print()

    for name, summary in per_file_summary:
        print(f"── {name} ──")
        for s in summary["snapped"]:
            print(f"  snap    {s['period_label']!r}: {s['from']} → {s['to']}")
        for r in summary["restored"]:
            print(f"  restore {r['period_label']!r}: {r['from']} → {r['to']}")
        for w in summary["warnings"]:
            print(f"  WARN   {w}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
