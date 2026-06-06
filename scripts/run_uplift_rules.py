#!/usr/bin/env python3
"""Batch CLI for uplift rules extraction.

Runs the same suggest() pipeline as the UI button, over many agreements.
Designed to be called from the pipeline onboarding step and from cron.

Examples:
  # Run for one agreement
  scripts/run_uplift_rules.py --ae-id ae513698

  # Run for every council that is missing a current suggestion
  scripts/run_uplift_rules.py --all-missing

  # After a rate cap refresh, re-run and write gold files
  scripts/run_uplift_rules.py --all-missing --write-gold --force-refresh

  # Dry run for diagnostics
  scripts/run_uplift_rules.py --all-missing --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_src_on_path() -> None:
    src = _repo_root() / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _log(msg: str, *, quiet: bool) -> None:
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


def _is_stale(canonical: dict, current_prompt_version: str, current_git_sha: str) -> bool:
    """Return True if the canonical suggestion needs re-running.

    Stale conditions:
      - No suggestion at all
      - suggestion.provenance.inputs.prompt_version != current_prompt_version
      - suggestion.provenance.code_git_sha != current_git_sha
      - suggestion.provenance.extraction_status != 'ok'  (we always retry errors)
    """
    section = (canonical.get("sections") or {}).get("uplift_rules") or {}
    data = section.get("data") if isinstance(section.get("data"), dict) else None
    if not data:
        return True
    suggestion = data.get("suggestion")
    if not isinstance(suggestion, dict):
        return True
    prov = suggestion.get("provenance") or {}
    inputs = prov.get("inputs") or {}
    if inputs.get("prompt_version") != current_prompt_version:
        return True
    if prov.get("code_git_sha") != current_git_sha:
        return True
    if prov.get("extraction_status") != "ok":
        return True
    return False


def _resolve_git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            stderr=subprocess.DEVNULL,
        ).decode("ascii").strip()
    except Exception:
        return "unknown"


def _process_one(
    ae_id: str,
    *,
    force_refresh: bool,
    write_gold_flag: bool,
    gold_dir: Path,
    quiet: bool,
) -> dict[str, Any]:
    """Run suggest() for a single ae_id; persist canonical; optionally write gold.

    Returns a status dict: {'ae_id', 'status', 'suggestion_id', 'error'?}
    """
    import main
    from benchmarking_data_factory.uplift_rules.suggest import SuggestConfig, suggest as run_suggest
    from benchmarking_data_factory.uplift_rules.gold_writer import write_gold

    try:
        adapter = main._uplift_adapter()
        cfg = SuggestConfig(
            model=main.ANTHROPIC_MODEL,
            force_refresh=force_refresh,
        )
        t0 = time.perf_counter()
        suggestion = run_suggest(ae_id, adapter, cfg)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        # Persist into canonical exactly as the /suggest endpoint does
        canonical = main.get_canonical(ae_id)
        section = canonical.setdefault("sections", {}).setdefault("uplift_rules", {})
        data = section.get("data") if isinstance(section.get("data"), dict) else {}
        data["suggestion"] = main._serialise_suggestion(suggestion)
        data["suggestion_generated_at"] = main.now_iso()
        section["data"] = data
        if section.get("status") in (None, "not_started"):
            section["status"] = "in_progress"
        main.save_canonical(ae_id, canonical)

        gold_path = None
        if write_gold_flag and suggestion.provenance.extraction_status == "ok":
            gold_path = write_gold(suggestion, gold_dir)

        _log(
            f"[{ae_id}] status={suggestion.provenance.extraction_status} "
            f"rules={len(suggestion.document.rules)} "
            f"{f'gold={gold_path.name}' if gold_path else ''} "
            f"({duration_ms}ms)",
            quiet=quiet,
        )
        return {
            "ae_id": ae_id,
            "status": suggestion.provenance.extraction_status,
            "suggestion_id": suggestion.suggestion_id,
            "rules_count": len(suggestion.document.rules),
            "gold_path": str(gold_path) if gold_path else None,
            "duration_ms": duration_ms,
        }
    except Exception as exc:  # noqa: BLE001
        _log(f"[{ae_id}] ERROR: {type(exc).__name__}: {exc}", quiet=False)
        return {
            "ae_id": ae_id,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


def main_cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Batch uplift rules extraction CLI")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--ae-id", help="Run for a single agreement id")
    target.add_argument("--all-missing", action="store_true",
                        help="Run for every council without a current suggestion")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Bypass the content-addressed cache")
    parser.add_argument("--write-gold", action="store_true",
                        help="Also write data/gold/rules/<ae_id>.rules.json for ok suggestions")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Cap the number of agreements processed")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print decisions without calling LLM or writing files")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-council log lines")
    parser.add_argument("--gold-dir", type=Path, default=None,
                        help="Gold output directory (default: <repo>/data/gold/rules)")
    args = parser.parse_args(argv)

    _ensure_src_on_path()

    from benchmarking_data_factory.uplift_rules.schema import CURRENT_PROMPT_VERSION

    gold_dir = args.gold_dir or (_repo_root() / "data" / "gold" / "rules")
    current_git_sha = _resolve_git_sha()

    # Resolve target list
    if args.ae_id:
        target_ids = [args.ae_id.lower()]
    else:
        if args.dry_run:
            # Dry runs still need main.list_pdfs + get_canonical; these don't touch LLM
            import main
        else:
            import main
        all_ids = main.list_pdfs()
        target_ids = []
        for ae_id in all_ids:
            canonical = main.get_canonical(ae_id)
            if _is_stale(canonical, CURRENT_PROMPT_VERSION, current_git_sha):
                target_ids.append(ae_id)
            else:
                _log(f"[{ae_id}] skip (current)", quiet=args.quiet)

    if args.max_items is not None:
        target_ids = target_ids[: args.max_items]

    if args.dry_run:
        summary = {
            "dry_run": True,
            "would_run": target_ids,
            "count": len(target_ids),
            "force_refresh": args.force_refresh,
            "write_gold": args.write_gold,
            "prompt_version": CURRENT_PROMPT_VERSION,
            "code_git_sha": current_git_sha,
        }
        print(json.dumps(summary, indent=2))
        return 0

    # Execute
    t0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    for ae_id in target_ids:
        results.append(_process_one(
            ae_id,
            force_refresh=args.force_refresh,
            write_gold_flag=args.write_gold,
            gold_dir=gold_dir,
            quiet=args.quiet,
        ))
    duration_ms = int((time.perf_counter() - t0) * 1000)

    # Determine counts: we already skipped stale-free ones pre-loop, so "ran" is len(results).
    # Skipped count = total PDFs minus targets (useful for ops).
    import main as _main
    total_pdfs = len(_main.list_pdfs()) if args.all_missing else 1

    ok = sum(1 for r in results if r["status"] == "ok")
    empty = sum(1 for r in results if r["status"] == "empty")
    llm_err = sum(1 for r in results if r["status"] == "llm_error")
    fatal = sum(1 for r in results if r["status"] == "error")
    gold_written = sum(1 for r in results if r.get("gold_path"))

    summary = {
        "ran": len(results),
        "skipped": total_pdfs - len(results),
        "errors": fatal,
        "gold_written": gold_written,
        "duration_ms": duration_ms,
        "by_status": {"ok": ok, "empty": empty, "llm_error": llm_err, "error": fatal},
        "prompt_version": CURRENT_PROMPT_VERSION,
        "code_git_sha": current_git_sha,
    }
    print(json.dumps(summary, indent=2))

    if fatal > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
