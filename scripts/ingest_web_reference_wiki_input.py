from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

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


DEFAULT_WIKI_ROOT = ROOT / "wiki"
BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "li"}
HEADING_TAGS = {"h1", "h2", "h3", "h4"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "form"}


class MainContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.main_seen = False
        self.skip_depth = 0
        self.current_tag = ""
        self.current_parts: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "main":
            self.blocks = []
            self.in_main = True
            self.main_seen = True
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self._collecting() and tag in BLOCK_TAGS:
            self._flush()
            self.current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == self.current_tag:
            self._flush()
        if tag == "main":
            self.in_main = False

    def handle_data(self, data: str) -> None:
        if not self._collecting() or self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text and self.current_tag:
            self.current_parts.append(text)

    def _collecting(self) -> bool:
        return self.in_main or not self.main_seen

    def _flush(self) -> None:
        if not self.current_tag:
            return
        text = re.sub(r"\s+", " ", " ".join(self.current_parts)).strip()
        if text:
            self.blocks.append((self.current_tag, text))
        self.current_tag = ""
        self.current_parts = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse an official web reference page into a wiki reference-input record.")
    parser.add_argument("url", help="Reference page URL to ingest.")
    parser.add_argument("--source-id", default="", help="Stable source id. Defaults to a slug from the page title.")
    parser.add_argument("--source-name", default="", help="Human-readable source name. Defaults to the page H1/title.")
    parser.add_argument("--wiki-root", type=Path, default=DEFAULT_WIKI_ROOT, help="Wiki directory to update.")
    parser.add_argument("--skip-language-map", action="store_true", help="Do not rebuild the clause-context language map.")
    return parser.parse_args()


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "eba-workbench-reference-ingest/1.0"})
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def slugify(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", value.lower()).strip("-")


def source_name_from_blocks(blocks: list[tuple[str, str]], fallback: str) -> str:
    for tag, text in blocks:
        if tag in HEADING_TAGS and len(text) > 4:
            return text[:160]
    return fallback


def blocks_to_page_texts(blocks: list[tuple[str, str]], *, max_chars: int = 5200) -> list[str]:
    page_texts: list[str] = []
    current: list[str] = []
    heading_count = 0
    for tag, text in blocks:
        if tag in HEADING_TAGS:
            heading_count += 1
            line = f"{heading_count}. {text}"
            if current:
                page_texts.append("\n".join(current))
                current = []
        elif tag == "li":
            line = f"- {text}"
        else:
            line = text
        if current and sum(len(item) + 1 for item in current) + len(line) > max_chars:
            page_texts.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        page_texts.append("\n".join(current))
    return [item for item in page_texts if item.strip()]


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
    for key, relative in {
        "document_maps": Path("wiki") / "document-maps",
        "reference_inputs": Path("wiki") / "reference-inputs",
        "pages": Path("wiki") / "pages",
        "language_maps": Path("wiki") / "language-maps",
        "patterns": Path("wiki") / "patterns",
        "issues": Path("wiki") / "issues",
        "learning_backlog": Path("wiki") / "learning-backlog",
        "questions": Path("wiki") / "questions",
        "runs": Path("wiki") / "runs",
        "artifacts": Path("wiki") / "artifacts",
    }.items():
        directories.setdefault(key, str(relative))
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
    generated_at = utc_now_iso()
    html = fetch_html(args.url)
    parser = MainContentParser()
    parser.feed(html)
    parser.close()
    source_name = args.source_name or source_name_from_blocks(parser.blocks, args.url)
    source_id = args.source_id or slugify(source_name)
    if not source_id:
        raise SystemExit("Could not resolve a source id for the web reference.")
    page_texts = blocks_to_page_texts(parser.blocks)
    if not page_texts:
        raise SystemExit("No page text could be extracted from the web reference.")

    wiki_root = args.wiki_root.resolve()
    reference_input_dir = wiki_root / "reference-inputs"
    artifact_dir = wiki_root / "artifacts"
    record = build_reference_input_map(
        source_id,
        page_texts,
        metadata={
            "source_name": source_name,
            "source_kind": "official_web_policy",
            "knowledge_role": "bargaining_process_reference",
            "text_source": "web_page_text",
            "source_url": args.url,
            "retrieved_at": generated_at,
        },
        generated_at=generated_at,
    )
    write_json(reference_input_dir / f"{source_id}.json", record)

    if not args.skip_language_map:
        maps = load_maps(wiki_root / "document-maps") + load_maps(reference_input_dir)
        language_map = build_language_map(maps, generated_at=generated_at)
        write_json(wiki_root / "language-maps" / f"{LANGUAGE_MAP_ID}.json", language_map)

    update_manifest(wiki_root, generated_at=generated_at)
    summary = {
        "schema_version": "wiki.web_reference_input_ingest.v1",
        "generated_at": generated_at,
        "source_url": args.url,
        "reference_input": {
            "source_id": record["source_id"],
            "source_name": record["source_name"],
            "source_kind": record["source_kind"],
            "knowledge_role": record["knowledge_role"],
            "pages_scanned": record["summary"]["pages_scanned"],
            "sections_detected": record["summary"]["sections_detected"],
            "language_candidates": record["summary"]["language_candidates"],
            "learning_backlog_items": record["summary"]["learning_backlog_items"],
        },
    }
    write_json(artifact_dir / "web-reference-input-ingest.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main_cli()
