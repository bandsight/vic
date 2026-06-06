from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

try:
    import fitz
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit("PyMuPDF (fitz) is required to ingest reference PDFs.") from exc

from benchmarking_data_factory.workbench.wiki_layer import (  # noqa: E402
    LANGUAGE_MAP_ID,
    LANGUAGE_MAP_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    REFERENCE_INPUT_SCHEMA_VERSION,
    WIKI_SCOPE_FOCUS,
    build_language_map,
    build_reference_input_map,
    utc_now_iso,
)


DEFAULT_SOURCE_DIR = ROOT / "documents" / "reference"
DEFAULT_WIKI_ROOT = ROOT / "wiki"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse operator-supplied reference PDFs into governed wiki reference-input records."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Folder containing reference PDFs. Defaults to documents/reference.",
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=DEFAULT_WIKI_ROOT,
        help="Wiki directory to update.",
    )
    parser.add_argument(
        "--pdf",
        action="append",
        default=[],
        help="Specific PDF filename or path to ingest. Can be passed more than once.",
    )
    parser.add_argument(
        "--skip-language-map",
        action="store_true",
        help="Do not rebuild the clause-context language map with reference inputs included.",
    )
    return parser.parse_args()


def source_id_for_pdf(path: Path) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", path.stem.lower()).strip("-")
    return slug or path.stem.lower()


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_pages(path: Path) -> list[str]:
    pages: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return pages


def copyright_notice_detected(page_texts: list[str]) -> bool:
    first_pages = "\n".join(page_texts[:4]).lower()
    return "copyright" in first_pages or "should not be copied" in first_pages


def pdfs_from_args(source_dir: Path, pdf_args: list[str]) -> list[Path]:
    if not pdf_args:
        return sorted(path for path in source_dir.glob("*.pdf") if path.is_file())
    paths: list[Path] = []
    for raw in pdf_args:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = source_dir / candidate
        paths.append(candidate)
    return sorted(paths, key=lambda item: item.name.lower())


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_manifest(wiki_root: Path, *, generated_at: str) -> None:
    path = wiki_root / "wiki-manifest.json"
    manifest = read_json(path) or {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "directories": {},
    }
    directories = manifest.setdefault("directories", {})
    directories.setdefault("document_maps", str(Path("wiki") / "document-maps"))
    directories.setdefault("reference_inputs", str(Path("wiki") / "reference-inputs"))
    directories.setdefault("pages", str(Path("wiki") / "pages"))
    directories.setdefault("language_maps", str(Path("wiki") / "language-maps"))
    directories.setdefault("patterns", str(Path("wiki") / "patterns"))
    directories.setdefault("issues", str(Path("wiki") / "issues"))
    directories.setdefault("learning_backlog", str(Path("wiki") / "learning-backlog"))
    directories.setdefault("questions", str(Path("wiki") / "questions"))
    directories.setdefault("runs", str(Path("wiki") / "runs"))
    directories.setdefault("artifacts", str(Path("wiki") / "artifacts"))
    manifest["generated_at"] = generated_at
    manifest["scope_focus"] = WIKI_SCOPE_FOCUS
    manifest["reference_input_schema_version"] = REFERENCE_INPUT_SCHEMA_VERSION
    manifest.setdefault("language_map_schema_version", LANGUAGE_MAP_SCHEMA_VERSION)
    write_json(path, manifest)


def load_maps(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    maps: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = read_json(path)
        if isinstance(payload, dict):
            maps.append(payload)
    return maps


def main_cli() -> None:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    wiki_root = args.wiki_root.resolve()
    generated_at = utc_now_iso()
    reference_input_dir = wiki_root / "reference-inputs"
    artifact_dir = wiki_root / "artifacts"

    pdf_paths = pdfs_from_args(source_dir, args.pdf)
    if not pdf_paths:
        raise SystemExit(f"No PDFs found in {source_dir}")

    records: list[dict[str, Any]] = []
    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            raise SystemExit(f"Reference PDF not found: {pdf_path}")
        page_texts = extract_pdf_pages(pdf_path)
        source_id = source_id_for_pdf(pdf_path)
        record = build_reference_input_map(
            source_id,
            page_texts,
            metadata={
                "source_name": pdf_path.stem,
                "source_kind": "reference_material",
                "knowledge_role": "interpretive_reference",
                "source_pdf": str(pdf_path),
                "source_pdf_hash": sha256_for_path(pdf_path),
                "copyright_notice_detected": copyright_notice_detected(page_texts),
            },
            generated_at=generated_at,
        )
        write_json(reference_input_dir / f"{source_id}.json", record)
        records.append(record)

    if not args.skip_language_map:
        maps = load_maps(wiki_root / "document-maps") + load_maps(reference_input_dir)
        language_map = build_language_map(maps, generated_at=generated_at)
        write_json(wiki_root / "language-maps" / f"{LANGUAGE_MAP_ID}.json", language_map)

    update_manifest(wiki_root, generated_at=generated_at)
    summary = {
        "schema_version": "wiki.reference_input_ingest.v1",
        "generated_at": generated_at,
        "source_dir": str(source_dir),
        "reference_inputs": [
            {
                "source_id": record["source_id"],
                "source_name": record["source_name"],
                "pages_scanned": record["summary"]["pages_scanned"],
                "sections_detected": record["summary"]["sections_detected"],
                "language_candidates": record["summary"]["language_candidates"],
                "learning_backlog_items": record["summary"]["learning_backlog_items"],
            }
            for record in records
        ],
    }
    write_json(artifact_dir / "reference-input-ingest.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main_cli()
