from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts import build_entitlement_card_repair_loop as repair_builder  # noqa: E402
from scripts import build_entitlement_cards as cards_builder  # noqa: E402
from scripts import build_entitlement_locator_experiment as locator_builder  # noqa: E402


LOCATOR_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment"
CARDS_DIR = ROOT / "wiki" / "artifacts" / "entitlement-cards"
REPAIR_DIR = ROOT / "wiki" / "artifacts" / "entitlement-card-repair-loop"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_artifact(directory: Path, pattern: str, fallback_name: str) -> Path:
    if directory.exists():
        files = sorted(
            (path for path in directory.glob(pattern) if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if files:
            return files[0]
    return directory / fallback_name


def write_json_and_markdown(
    *,
    payload: dict[str, Any],
    output_dir: Path,
    markdown: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    cards_builder.write_json(json_path, payload)
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def run_locator(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path]:
    scope = args.locator_scope.replace("-", "_")
    batch_size = None if scope in {"all_cached", "gold_exemplar_v2"} or args.all_eligible else args.batch_size
    payload = locator_builder.build_payload(
        batch_size,
        args.offset,
        utc_now_iso(),
        scope=scope,
        progress=True,
        entitlement_ids=set(args.entitlement_id) if args.entitlement_id else None,
    )
    json_path, md_path = write_json_and_markdown(
        payload=payload,
        output_dir=args.locator_output_dir.resolve(),
        markdown=locator_builder.markdown_for_payload(payload),
    )
    return payload, json_path, md_path


def run_cards(locator_payload: dict[str, Any], locator_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path, Path]:
    payload = cards_builder.build_payload(
        locator_payload,
        generated_at=utc_now_iso(),
        source_path=locator_path.resolve(),
    )
    json_path, md_path = write_json_and_markdown(
        payload=payload,
        output_dir=output_dir.resolve(),
        markdown=cards_builder.markdown_for_payload(payload),
    )
    return payload, json_path, md_path


def run_repair(
    *,
    locator_payload: dict[str, Any],
    locator_path: Path,
    cards_payload: dict[str, Any],
    cards_path: Path,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], Path, Path] | None:
    if args.repair_mode == "skip":
        return None
    env = repair_builder.load_env_file(ROOT / ".env")
    model = args.model or env.get("ANTHROPIC_MODEL") or env.get("EXTRACT_MODEL") or "claude-sonnet-4-20250514"
    payload = repair_builder.build_payload(
        locator_payload,
        cards_payload,
        generated_at=utc_now_iso(),
        source_path=locator_path.resolve(),
        cards_path=cards_path.resolve(),
        env=env,
        model=model,
        max_tokens=args.max_tokens,
        offline=args.repair_mode == "offline",
        sample_limit=args.sample_limit,
        entitlement_ids=set(args.entitlement_id) if args.entitlement_id else None,
    )
    json_path, md_path = write_json_and_markdown(
        payload=payload,
        output_dir=args.repair_output_dir.resolve(),
        markdown=repair_builder.markdown_for_payload(payload),
    )
    return payload, json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the clause pipeline in dependency order: locator, Entitlement Cards, repair loop."
    )
    parser.add_argument(
        "--run-locator",
        action="store_true",
        help="Rebuild the locator artifact before downstream stages. This can be slow for all-cached runs.",
    )
    parser.add_argument("--locator-scope", choices=["eligible-next", "all-cached", "gold-exemplar-v2"], default="all-cached")
    parser.add_argument("--locator-input", type=Path, default=None, help="Existing locator artifact to reuse when --run-locator is not set.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--all-eligible", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--repair-mode", choices=["offline", "llm", "skip"], default="offline")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument("--model", default="")
    parser.add_argument("--entitlement-id", action="append", default=[], help="Limit locator and repair-loop work to one or more entitlement ids.")
    parser.add_argument("--locator-output-dir", type=Path, default=LOCATOR_DIR)
    parser.add_argument("--cards-output-dir", type=Path, default=CARDS_DIR)
    parser.add_argument("--repair-output-dir", type=Path, default=REPAIR_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.run_locator:
        locator_payload, locator_path, locator_md_path = run_locator(args)
    else:
        locator_path = (args.locator_input or latest_artifact(
            LOCATOR_DIR,
            "entitlement-locator-experiment-*.json",
            "entitlement-locator-experiment-all-cached-79-offset-0.json",
        )).resolve()
        locator_payload = cards_builder.load_json(locator_path)
        locator_md_path = locator_path.with_suffix(".md")

    cards_payload, cards_path, cards_md_path = run_cards(locator_payload, locator_path, args.cards_output_dir)
    repair_result = run_repair(
        locator_payload=locator_payload,
        locator_path=locator_path,
        cards_payload=cards_payload,
        cards_path=cards_path,
        args=args,
    )

    summary: dict[str, Any] = {
        "schema_version": "wiki.clause_pipeline_refresh.v1",
        "generated_at": utc_now_iso(),
        "run_locator": args.run_locator,
        "repair_mode": args.repair_mode,
        "locator": {
            "artifact_id": locator_payload.get("artifact_id"),
            "artifact_path": str(locator_path),
            "markdown_path": str(locator_md_path),
            "generated_at": locator_payload.get("generated_at"),
        },
        "entitlement_cards": {
            "artifact_id": cards_payload.get("artifact_id"),
            "artifact_path": str(cards_path),
            "markdown_path": str(cards_md_path),
            "generated_at": cards_payload.get("generated_at"),
            "summary": cards_payload.get("summary"),
        },
    }
    if repair_result:
        repair_payload, repair_path, repair_md_path = repair_result
        summary["entitlement_card_repair_loop"] = {
            "artifact_id": repair_payload.get("artifact_id"),
            "artifact_path": str(repair_path),
            "markdown_path": str(repair_md_path),
            "generated_at": repair_payload.get("generated_at"),
            "summary": repair_payload.get("summary"),
        }
    else:
        summary["entitlement_card_repair_loop"] = {"skipped": True}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
