#!/usr/bin/env python3
"""CLI runner for the scenario_testing engine.

Reads a canonical YAML, runs scenarios, prints a human-readable summary.
Read-only: never writes to canonical, data, or cache.

Usage:
  .venv/bin/python scripts/run_scenarios.py <ae_id>
  .venv/bin/python scripts/run_scenarios.py --all
  .venv/bin/python scripts/run_scenarios.py --all --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_DIR = REPO_ROOT / "canonical"

# Make src/ importable
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from benchmarking_data_factory.scenario_testing import run_scenarios  # noqa: E402

STATUS_GLYPHS = {
    "consistent": "🟢",
    "needs_attention": "🟡",
    "awaiting_input": "🔵",
    "baseline": "⚪",
    "blocked": "⚫",
}


def _load_canonical(ae_id: str) -> dict:
    path = CANONICAL_DIR / f"{ae_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No canonical YAML at {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _lga_from_canonical(canonical: dict) -> str | None:
    """Resolve canonical_lga_short_name from the several places it can live.

    The canonical schema stores provenance on each pay-table entry rather than
    at the top level, so we check top-level fields first (cheap fallback) and
    then walk into sections.pay_tables.tables[*].provenance.
    """
    top = canonical.get("canonical_lga_short_name") or canonical.get("lga_short_name")
    if top:
        return top
    overview = canonical.get("overview") or {}
    ov = overview.get("canonical_lga_short_name") or overview.get("lga_short_name")
    if ov:
        return ov
    sections = canonical.get("sections") or {}
    pay_tables = (sections.get("pay_tables") or {}).get("tables") or []
    for table in pay_tables:
        if not isinstance(table, dict):
            continue
        provenance = table.get("provenance") or {}
        lga = provenance.get("canonical_lga_short_name") or provenance.get("lga_short_name")
        if lga:
            return lga
    return None


def _all_ae_ids() -> list[str]:
    return sorted(p.stem for p in CANONICAL_DIR.glob("*.yaml"))


def _format_result_human(r) -> str:
    glyph = STATUS_GLYPHS.get(r.status, "?")
    head = f"  {glyph} {r.period_effective_from or '(precondition)'} [{r.status}"
    if r.sub_status:
        head += f"/{r.sub_status}"
    head += "]"
    if r.rule_quantum:
        head += f" rule={r.rule_quantum}"
    lines = [head, f"      reason: {r.reason}"]
    if r.cell_deltas:
        n_total = len(r.cell_deltas)
        n_ok = sum(1 for c in r.cell_deltas if c.within_tolerance)
        lines.append(f"      cells: {n_ok}/{n_total} within tolerance")
        # Show up to 3 failing cells
        failing = [c for c in r.cell_deltas if not c.within_tolerance]
        for c in failing[:3]:
            if c.pct_delta is None:
                lines.append(
                    f"        band={c.band} level={c.level}: unmatched "
                    f"(prior={c.prior_weekly} computed={c.computed_weekly} actual={c.actual_weekly})"
                )
            else:
                lines.append(
                    f"        band={c.band} level={c.level}: "
                    f"computed={c.computed_weekly:.2f} actual={c.actual_weekly:.2f} "
                    f"(Δ={c.abs_delta:.2f}, {c.pct_delta*100:.3f}%)"
                )
        if len(failing) > 3:
            lines.append(f"        ... and {len(failing) - 3} more failing cells")
    return "\n".join(lines)


def _summarise(ae_id: str, results: tuple) -> str:
    buckets: dict[str, int] = {}
    for r in results:
        buckets[r.status] = buckets.get(r.status, 0) + 1
    parts = [f"{STATUS_GLYPHS.get(k, '?')} {v} {k}" for k, v in sorted(buckets.items())]
    return f"{ae_id}: " + "  ".join(parts) if parts else f"{ae_id}: (no results)"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ae_id", nargs="?", help="Agreement id (e.g. ae521669). Omit with --all.")
    p.add_argument("--all", action="store_true", help="Run every canonical YAML.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable output.")
    p.add_argument("--summary-only", action="store_true", help="One line per agreement; no per-period detail.")
    args = p.parse_args()

    if not args.all and not args.ae_id:
        p.error("Provide an ae_id or --all")

    targets = _all_ae_ids() if args.all else [args.ae_id]

    if args.json:
        out: dict[str, list[dict]] = {}
        for ae_id in targets:
            try:
                canonical = _load_canonical(ae_id)
            except FileNotFoundError as e:
                print(f"SKIP {ae_id}: {e}", file=sys.stderr)
                continue
            lga_short_name = _lga_from_canonical(canonical)
            results = run_scenarios(
                canonical,
                lga_short_name=lga_short_name,
            )
            out[ae_id] = [_asdict_with_tuple(r) for r in results]
        print(json.dumps(out, indent=2, default=str))
        return 0

    # Human mode
    for ae_id in targets:
        try:
            canonical = _load_canonical(ae_id)
        except FileNotFoundError as e:
            print(f"SKIP {ae_id}: {e}", file=sys.stderr)
            continue
        lga_short_name = _lga_from_canonical(canonical)
        results = run_scenarios(
            canonical,
            lga_short_name=lga_short_name,
        )
        if args.summary_only:
            print(_summarise(ae_id, results))
        else:
            print(f"\n=== {ae_id} ===")
            print(f"  {_summarise(ae_id, results)}")
            for r in results:
                print(_format_result_human(r))
    return 0


def _asdict_with_tuple(dc) -> dict:
    """dataclasses.asdict but converts tuples of dataclasses properly."""
    d = asdict(dc)
    return d


if __name__ == "__main__":
    raise SystemExit(main())
