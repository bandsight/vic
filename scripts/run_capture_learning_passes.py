from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "capture-learning-passes"


PIPELINE_STEPS = [
    ("locator", ["scripts/build_entitlement_locator_experiment.py", "--all-cached"]),
    ("self_improvement", ["scripts/build_entitlement_self_improvement_pass.py"]),
    ("loop_intelligence", ["scripts/build_entitlement_loop_intelligence.py"]),
    ("apply_loop_findings", ["scripts/apply_entitlement_loop_findings.py"]),
    ("research_loop", ["scripts/build_entitlement_research_loop.py"]),
    ("apply_research_findings", ["scripts/apply_entitlement_research_findings.py"]),
    ("spine_clause_improvement", ["scripts/build_spine_clause_improvement_pass.py"]),
    ("apply_spine_clause_findings", ["scripts/apply_spine_clause_improvement_findings.py"]),
]


SUMMARY_PATHS = {
    "self_improvement": ROOT / "wiki" / "artifacts" / "entitlement-self-improvement" / "entitlement-self-improvement-pass-entitlement-locator-experiment-all-cached-79-offset-0.json",
    "loop_intelligence": ROOT / "wiki" / "artifacts" / "entitlement-loop-intelligence" / "entitlement-loop-intelligence-entitlement-locator-experiment-all-cached-79-offset-0.json",
    "research_loop": ROOT / "wiki" / "artifacts" / "entitlement-research-loop" / "entitlement-research-loop-entitlement-locator-experiment-all-cached-79-offset-0.json",
    "entitlement_rule_overrides": ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json",
    "spine_clause_improvement": ROOT / "wiki" / "artifacts" / "spine-clause-improvement" / "spine-clause-improvement-entitlement-locator-experiment-all-cached-79-offset-0.json",
    "spine_clause_process_rules": ROOT / "data" / "review" / "spine_clause_process_rules.json",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def snapshot_summary() -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for key, path in SUMMARY_PATHS.items():
        payload = read_json(path)
        snapshots[key] = {
            "path": str(path),
            "artifact_id": payload.get("artifact_id") if isinstance(payload, dict) else None,
            "generated_at": payload.get("generated_at") if isinstance(payload, dict) else None,
            "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        }
    return snapshots


def run_step(step_name: str, args: list[str]) -> None:
    command = [sys.executable, *args]
    print(json.dumps({
        "event": "capture_learning_step_started",
        "step": step_name,
        "command": command,
        "started_at": utc_now_iso(),
    }), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)
    print(json.dumps({
        "event": "capture_learning_step_completed",
        "step": step_name,
        "completed_at": utc_now_iso(),
    }), flush=True)


def run_pass(pass_number: int, output_dir: Path) -> dict[str, Any]:
    print(json.dumps({
        "event": "capture_learning_pass_started",
        "pass_number": pass_number,
        "started_at": utc_now_iso(),
    }), flush=True)
    for step_name, args in PIPELINE_STEPS:
        run_step(step_name, args)
    payload = {
        "schema_version": "wiki.capture_learning_pass.v1",
        "pass_number": pass_number,
        "generated_at": utc_now_iso(),
        "steps": [step_name for step_name, _args in PIPELINE_STEPS],
        "snapshots": snapshot_summary(),
    }
    write_json(output_dir / f"capture-learning-pass-{pass_number}.json", payload)
    print(json.dumps({
        "event": "capture_learning_pass_completed",
        "pass_number": pass_number,
        "completed_at": payload["generated_at"],
        "summary": payload["snapshots"]["spine_clause_process_rules"]["summary"],
    }), flush=True)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repeated all-council capture passes and bake findings into the next pass.")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    all_passes = [run_pass(pass_number, output_dir) for pass_number in range(1, max(args.passes, 1) + 1)]
    rollup = {
        "schema_version": "wiki.capture_learning_pass_rollup.v1",
        "generated_at": utc_now_iso(),
        "passes": len(all_passes),
        "pass_summaries": [
            {
                "pass_number": payload["pass_number"],
                "generated_at": payload["generated_at"],
                "spine_clause": payload["snapshots"]["spine_clause_process_rules"]["summary"],
                "entitlement_rules": payload["snapshots"]["entitlement_rule_overrides"]["summary"],
            }
            for payload in all_passes
        ],
    }
    write_json(output_dir / "capture-learning-pass-rollup.json", rollup)
    print(json.dumps({
        "schema_version": "wiki.capture_learning_pass_runner.v1",
        "generated_at": rollup["generated_at"],
        "passes": rollup["passes"],
        "rollup_path": str(output_dir / "capture-learning-pass-rollup.json"),
        "latest_summary": rollup["pass_summaries"][-1] if rollup["pass_summaries"] else {},
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
