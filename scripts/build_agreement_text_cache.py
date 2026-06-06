"""Materialise full-text agreement caches for the governed pipeline set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from benchmarking_data_factory.workbench.document_pages import (  # noqa: E402
    DocumentPageService,
)


DEFAULT_DATASET = ROOT / "data" / "governed_canonical" / "council_agreements.json"


def normalise_agreement_id(value: Any) -> str:
    return str(value or "").strip().lower().removesuffix(".pdf")


def add_unique(values: list[str], seen: set[str], value: Any) -> None:
    agreement_id = normalise_agreement_id(value)
    if agreement_id and agreement_id not in seen:
        seen.add(agreement_id)
        values.append(agreement_id)


def load_pipeline_agreement_ids(dataset_path: Path) -> list[str]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else []
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            add_unique(values, seen, row.get("agreement_id"))
    return values


def pdf_agreement_ids(pdf_dir: Path) -> list[str]:
    if not pdf_dir.exists():
        return []
    return sorted(
        path.stem.lower()
        for path in pdf_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def cache_agreement_ids(cache_dir: Path) -> list[str]:
    if not cache_dir.exists():
        return []
    return sorted(path.name.lower() for path in cache_dir.iterdir() if path.is_dir() and path.name.lower().startswith("ae"))


def page_count_for(cache_dir: Path, agreement_id: str) -> int | None:
    path = cache_dir / agreement_id / "pages.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return len(payload) if isinstance(payload, list) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build cache/<agreement_id>/full_text.txt from cached or extracted agreement page text."
    )
    parser.add_argument("--agreement-id", "--ae-id", action="append", default=[], help="Agreement ID to process.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Governed pipeline dataset to read.")
    parser.add_argument("--include-all-pdfs", action="store_true", help="Also include every PDF in documents/immutable.")
    parser.add_argument("--include-cache-dirs", action="store_true", help="Also include every existing cache directory.")
    parser.add_argument("--force", action="store_true", help="Re-extract page text from PDFs and rewrite full_text.txt.")
    parser.add_argument("--skip-errors", action="store_true", help="Exit successfully even if some agreements fail.")
    return parser.parse_args()


def target_agreement_ids(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for agreement_id in args.agreement_id:
        add_unique(values, seen, agreement_id)
    if not values:
        for agreement_id in load_pipeline_agreement_ids(args.dataset):
            add_unique(values, seen, agreement_id)
    if args.include_all_pdfs:
        for agreement_id in pdf_agreement_ids(ROOT / "documents" / "immutable"):
            add_unique(values, seen, agreement_id)
    if args.include_cache_dirs:
        for agreement_id in cache_agreement_ids(ROOT / "cache"):
            add_unique(values, seen, agreement_id)
    return values


def main() -> int:
    args = parse_args()
    service = DocumentPageService(
        pdf_dir=ROOT / "documents" / "immutable",
        cache_dir=ROOT / "cache",
        page_render_dpi=150,
    )
    agreement_ids = target_agreement_ids(args)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for agreement_id in agreement_ids:
        try:
            full_text_path = service.full_text_path(agreement_id)
            existed = full_text_path.exists()
            text = service.extract_full_text(agreement_id, force=args.force)
            results.append({
                "agreement_id": agreement_id,
                "status": "rewritten" if args.force else ("existing" if existed else "written"),
                "full_text_path": str(full_text_path.relative_to(ROOT)).replace("\\", "/"),
                "page_count": page_count_for(ROOT / "cache", agreement_id),
                "character_count": len(text),
            })
        except Exception as exc:  # noqa: BLE001 - batch job should report all failures.
            failures.append({
                "agreement_id": agreement_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    summary = {
        "target_count": len(agreement_ids),
        "materialised_count": len(results),
        "failure_count": len(failures),
        "results": results,
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failures or args.skip_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
