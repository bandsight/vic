from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCATOR_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment"
EVALUATION_DIR = ROOT / "wiki" / "artifacts" / "exemplar-accuracy-evaluation"
ROLLUP_DIR = ROOT / "wiki" / "artifacts" / "exemplar-accuracy-improvement-loop"
SCHEMA_VERSION = "wiki.exemplar_accuracy_improvement_loop.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No files matching {pattern} in {directory}")
    return files[-1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_pass(index: int, target: float) -> dict[str, Any]:
    locator = run_command([
        sys.executable,
        "scripts/build_entitlement_locator_experiment.py",
        "--gold-exemplar-v2",
    ])
    locator_path = latest_file(LOCATOR_DIR, "entitlement-locator-experiment-gold-exemplar-v2-*.json")
    evaluation = run_command([
        sys.executable,
        "scripts/build_exemplar_accuracy_evaluation.py",
        "--locator",
        str(locator_path),
        "--target",
        str(target),
    ])
    evaluation_path = latest_file(
        EVALUATION_DIR,
        f"exemplar-accuracy-{locator_path.stem}.json",
    )
    payload = read_json(evaluation_path)
    return {
        "pass_index": index,
        "locator_exit_code": locator.returncode,
        "evaluation_exit_code": evaluation.returncode,
        "locator_artifact": str(locator_path),
        "evaluation_artifact": str(evaluation_path),
        "operational_accuracy": payload["summary"]["operational_accuracy"],
        "strict_reference_accuracy": payload["summary"]["strict_reference_accuracy"],
        "passes_target": payload["passes_target"],
        "remaining_failures": payload["summary"]["remaining_failures"],
        "locator_stdout": locator.stdout[-2000:],
        "locator_stderr": locator.stderr[-2000:],
        "evaluation_stdout": evaluation.stdout[-2000:],
        "evaluation_stderr": evaluation.stderr[-2000:],
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Exemplar Accuracy Improvement Loop",
        "",
        f"Target: {payload['target']:.0%}",
        f"Completed passes: {payload['summary']['passes_run']}",
        f"Best operational accuracy: {payload['summary']['best_operational_accuracy']:.1%}",
        f"Best strict reference accuracy: {payload['summary']['best_strict_reference_accuracy']:.1%}",
        f"Reached target: {'yes' if payload['summary']['passes_target'] else 'no'}",
        "",
        "| Pass | Operational | Strict | Remaining failures | Target? |",
        "| ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload["passes"]:
        lines.append(
            f"| {item['pass_index']} | {item['operational_accuracy']:.1%} | "
            f"{item['strict_reference_accuracy']:.1%} | {item['remaining_failures']} | "
            f"{'yes' if item['passes_target'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run focused processing passes until the exemplar accuracy gate reaches target.")
    parser.add_argument("--target", type=float, default=0.90)
    parser.add_argument("--max-passes", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    passes: list[dict[str, Any]] = []
    for index in range(1, args.max_passes + 1):
        result = run_pass(index, args.target)
        passes.append(result)
        if result["passes_target"]:
            break

    best = max(passes, key=lambda item: item["operational_accuracy"]) if passes else {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "target": args.target,
        "summary": {
            "passes_run": len(passes),
            "passes_target": bool(best.get("passes_target")),
            "best_operational_accuracy": best.get("operational_accuracy", 0),
            "best_strict_reference_accuracy": best.get("strict_reference_accuracy", 0),
            "best_evaluation_artifact": best.get("evaluation_artifact"),
            "best_locator_artifact": best.get("locator_artifact"),
        },
        "passes": passes,
    }
    ROLLUP_DIR.mkdir(parents=True, exist_ok=True)
    artifact_id = "exemplar-accuracy-improvement-loop"
    json_path = ROLLUP_DIR / f"{artifact_id}.json"
    md_path = ROLLUP_DIR / f"{artifact_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.exemplar_accuracy_improvement_loop_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_path": str(json_path),
        "passes_run": len(passes),
        "best_operational_accuracy": payload["summary"]["best_operational_accuracy"],
        "passes_target": payload["summary"]["passes_target"],
    }, indent=2))
    if not payload["summary"]["passes_target"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
