from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402
from benchmarking_data_factory.workbench.wiki_layer import build_wiki_pilot  # noqa: E402


DEFAULT_LOCATOR_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"


def metadata_for(ae_id: str) -> dict[str, Any]:
    canonical = main.get_canonical(ae_id)
    fetch_metadata = main.fetch_metadata_for_ae_id(ae_id) or {}
    source_pdf = main.find_pdf(ae_id)
    return {
        "agreement_name": canonical.get("source_name") or fetch_metadata.get("title") or ae_id,
        "source_name": canonical.get("source_name") or "",
        "source_pdf": str(source_pdf) if source_pdf is not None else "",
        "source_pdf_hash": fetch_metadata.get("content_hash") or fetch_metadata.get("sha256") or "",
    }


def load_cached_page_texts(ae_id: str) -> list[str]:
    path = ROOT / "cache" / ae_id.lower().removesuffix(".pdf") / "pages.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def locator_target_ae_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ae_ids: list[str] = []
    seen: set[str] = set()
    for row in payload.get("target_comparator_set") or []:
        if not isinstance(row, dict):
            continue
        ae_id = str(row.get("agreement_id") or "").lower().removesuffix(".pdf")
        if not ae_id or ae_id in seen:
            continue
        seen.add(ae_id)
        ae_ids.append(ae_id)
    return ae_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build first-pass wiki document maps for a small EBA pilot set.")
    parser.add_argument("--ae-id", action="append", default=[], help="Agreement ID to include. Can be passed more than once.")
    parser.add_argument("--limit", type=int, default=3, help="Number of PDFs to use when no --ae-id values are supplied.")
    parser.add_argument("--from-cache", action="store_true", help="Read cache/<ae-id>/pages.json instead of extracting PDFs.")
    parser.add_argument("--locator-input", type=Path, default=DEFAULT_LOCATOR_INPUT, help="Locator artifact used by --all-cached-targets.")
    parser.add_argument("--all-cached-targets", action="store_true", help="Use target comparator agreements from the all-cached locator artifact.")
    parser.add_argument("--missing-only", action="store_true", help="Only build document maps that do not already exist.")
    parser.add_argument("--skip-missing-cache", action="store_true", help="When --from-cache is used, skip agreements without cached pages.")
    return parser.parse_args()


def main_cli() -> None:
    args = parse_args()
    ae_ids = [item.lower().removesuffix(".pdf") for item in args.ae_id]
    if args.all_cached_targets:
        ae_ids = locator_target_ae_ids(args.locator_input.resolve())
    elif not ae_ids:
        ae_ids = main.list_pdfs()[: max(1, args.limit)]
    if args.missing_only:
        ae_ids = [
            ae_id
            for ae_id in ae_ids
            if not (ROOT / "wiki" / "document-maps" / f"{ae_id}.json").exists()
        ]
    if args.from_cache and args.skip_missing_cache:
        ae_ids = [
            ae_id
            for ae_id in ae_ids
            if (ROOT / "cache" / ae_id / "pages.json").exists()
        ]
    page_loader = load_cached_page_texts if args.from_cache else main.extract_all_page_texts
    result = build_wiki_pilot(
        root=main.ROOT,
        ae_ids=ae_ids,
        page_text_loader=page_loader,
        metadata_loader=metadata_for,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main_cli()
