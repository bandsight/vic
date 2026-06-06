from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

SUSPECT_PDF_SIZE_BYTES = 500 * 1024

SOURCE_REGISTER_FIELDS = [
    "source_document_id",
    "source_name",
    "source_type",
    "source_origin",
    "fetched_at",
    "content_hash",
    "frozen_path",
    "file_size_bytes",
    "source_status",
    "serviceability_status",
    "discovery_reference",
    "notes",
]


def source_register_fields() -> list[str]:
    return list(SOURCE_REGISTER_FIELDS)


def serviceability_status_for_size(file_size_bytes: int) -> str:
    return "suspect_under_500kb" if file_size_bytes < SUSPECT_PDF_SIZE_BYTES else "fetched"


def pdf_source_metadata_for_path(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "frozen": False,
            "file_size_bytes": None,
            "size_status": "missing",
            "suspect": False,
            "suspect_reason": "",
        }
    size = path.stat().st_size
    suspect = size < SUSPECT_PDF_SIZE_BYTES
    return {
        "frozen": True,
        "file_size_bytes": size,
        "size_status": "suspect_under_500kb" if suspect else "ok",
        "suspect": suspect,
        "suspect_reason": (
            "Fetched PDF is under 500 KB; source may be incomplete and should be retried."
            if suspect
            else ""
        ),
    }


class SourceDocumentRegister:
    def __init__(self, path: Path):
        self.path = path
        self._cache_by_ae_id: dict[str, dict[str, str]] | None = None

    def load_by_ae_id(self) -> dict[str, dict[str, str]]:
        if self._cache_by_ae_id is not None:
            return self._cache_by_ae_id
        result: dict[str, dict[str, str]] = {}
        if not self.path.exists():
            self._cache_by_ae_id = result
            return result
        with self.path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ref = (row.get("discovery_reference") or "").strip().lower().removesuffix(".pdf")
                if ref:
                    result[ref] = row
        self._cache_by_ae_id = result
        return result

    def load_rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {field: row.get(field, "") for field in SOURCE_REGISTER_FIELDS}
                for row in csv.DictReader(handle)
            ]

    def write_rows(self, rows: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SOURCE_REGISTER_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in SOURCE_REGISTER_FIELDS})
        self._cache_by_ae_id = None

    def next_document_id(self, rows: list[dict[str, str]]) -> str:
        highest = 0
        for row in rows:
            match = re.match(r"SD-(\d+)$", str(row.get("source_document_id") or "").strip())
            if match:
                highest = max(highest, int(match.group(1)))
        return f"SD-{highest + 1:04d}"

    def record_frozen_document(
        self,
        *,
        ae_id: str,
        title: str,
        pdf_url: str,
        pdf_path: Path,
        content_hash: str,
        pipeline_status: str,
        fetched_at: str,
        already_frozen: bool = False,
    ) -> dict[str, str]:
        rows = self.load_rows()
        discovery_reference = f"{ae_id}.pdf"
        existing_index = next(
            (
                index
                for index, row in enumerate(rows)
                if (row.get("discovery_reference") or "").strip().lower().removesuffix(".pdf")
                == ae_id
            ),
            None,
        )
        previous = rows[existing_index] if existing_index is not None else {}
        note_prefix = "Existing fetched PDF registered" if already_frozen else "Fetched from Fair Work intake action"
        file_size_bytes = pdf_path.stat().st_size
        updated = {
            **previous,
            "source_document_id": previous.get("source_document_id") or self.next_document_id(rows),
            "source_name": title,
            "source_type": "EA PDF",
            "source_origin": pdf_url or previous.get("source_origin", ""),
            "fetched_at": (
                previous.get("fetched_at")
                if already_frozen and previous.get("fetched_at")
                else fetched_at
            ),
            "content_hash": content_hash,
            "frozen_path": str(pdf_path),
            "file_size_bytes": str(file_size_bytes),
            "source_status": "active" if pipeline_status == "active" else "candidate",
            "serviceability_status": serviceability_status_for_size(file_size_bytes),
            "discovery_reference": discovery_reference,
            "notes": previous.get("notes") or note_prefix,
        }
        if existing_index is None:
            rows.append(updated)
        else:
            rows[existing_index] = updated
        rows.sort(key=lambda row: (row.get("discovery_reference") or "").lower())
        self.write_rows(rows)
        return updated
