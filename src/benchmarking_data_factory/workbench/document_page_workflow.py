from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable

from fastapi import HTTPException

from benchmarking_data_factory.workbench.document_pages import (
    DocumentPageService,
    PageOutOfRange,
    PdfDependencyMissing,
    PdfNotFound,
)


@dataclass(frozen=True)
class DocumentPageWorkflowDependencies:
    immutable_dir: Callable[[], Path]
    cache_dir: Callable[[], Path]
    page_render_dpi: Callable[[], int]
    score_pages: Callable[[list[str], re.Pattern[str]], list[int]]
    uplift_keywords: re.Pattern[str]


def document_page_service(deps: DocumentPageWorkflowDependencies) -> DocumentPageService:
    return DocumentPageService(
        pdf_dir=deps.immutable_dir(),
        cache_dir=deps.cache_dir(),
        page_render_dpi=deps.page_render_dpi(),
    )


def list_pdfs(deps: DocumentPageWorkflowDependencies) -> list[str]:
    pdf_dir = deps.immutable_dir()
    if not pdf_dir.exists():
        return []
    ae_ids = {
        path.stem.lower()
        for path in pdf_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    }
    return sorted(ae_ids)


def document_page_http_exception(exc: Exception, ae_id: str | None = None) -> HTTPException:
    if isinstance(exc, PdfDependencyMissing):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, PdfNotFound):
        detail = f"PDF not found for {ae_id}" if ae_id else "PDF not found"
        return HTTPException(status_code=404, detail=detail)
    if isinstance(exc, PageOutOfRange):
        return HTTPException(status_code=400, detail="page_num out of range")
    return HTTPException(status_code=500, detail=str(exc))


def ensure_cache_dir(ae_id: str, deps: DocumentPageWorkflowDependencies) -> Path:
    return document_page_service(deps).ensure_cache_dir(ae_id)


def require_fitz(deps: DocumentPageWorkflowDependencies) -> None:
    try:
        document_page_service(deps).require_fitz()
    except PdfDependencyMissing as exc:
        raise document_page_http_exception(exc) from exc


def find_pdf(ae_id: str, deps: DocumentPageWorkflowDependencies) -> Path | None:
    return document_page_service(deps).find_pdf(ae_id)


def pdf_path_for(ae_id: str, deps: DocumentPageWorkflowDependencies) -> Path:
    try:
        return document_page_service(deps).pdf_path_for(ae_id)
    except PdfNotFound as exc:
        raise HTTPException(status_code=404, detail="PDF not found") from exc


def get_page_count(ae_id: str, deps: DocumentPageWorkflowDependencies) -> int:
    try:
        return document_page_service(deps).get_page_count(ae_id)
    except (PdfDependencyMissing, PdfNotFound, PageOutOfRange) as exc:
        raise document_page_http_exception(exc, ae_id) from exc


def extract_page_text(ae_id: str, page_num: int, deps: DocumentPageWorkflowDependencies) -> str:
    try:
        return document_page_service(deps).extract_page_text(ae_id, page_num)
    except (PdfDependencyMissing, PdfNotFound, PageOutOfRange) as exc:
        raise document_page_http_exception(exc, ae_id) from exc


def extract_all_page_texts(ae_id: str, deps: DocumentPageWorkflowDependencies) -> list[str]:
    try:
        return document_page_service(deps).extract_all_page_texts(ae_id)
    except (PdfDependencyMissing, PdfNotFound, PageOutOfRange) as exc:
        raise document_page_http_exception(exc, ae_id) from exc


def extract_full_text(ae_id: str, deps: DocumentPageWorkflowDependencies) -> str:
    try:
        return document_page_service(deps).extract_full_text(ae_id)
    except (PdfDependencyMissing, PdfNotFound, PageOutOfRange) as exc:
        raise document_page_http_exception(exc, ae_id) from exc


def render_page_png(
    ae_id: str,
    page_num: int,
    deps: DocumentPageWorkflowDependencies,
    *,
    dpi: int | None = None,
) -> bytes:
    try:
        return document_page_service(deps).render_page_png(ae_id, page_num, dpi=dpi)
    except (PdfDependencyMissing, PdfNotFound, PageOutOfRange) as exc:
        raise document_page_http_exception(exc, ae_id) from exc


def find_candidate_pages(
    ae_id: str,
    pattern: re.Pattern[str],
    deps: DocumentPageWorkflowDependencies,
) -> list[int]:
    pages = extract_all_page_texts(ae_id, deps)
    return deps.score_pages(pages, pattern)


def collect_uplift_pages_text(
    ae_id: str,
    deps: DocumentPageWorkflowDependencies,
    *,
    max_pages: int = 6,
) -> list[dict[str, Any]]:
    pages = find_candidate_pages(ae_id, deps.uplift_keywords, deps)[:max_pages]
    blocks: list[dict[str, Any]] = []
    for page_num in pages:
        text = extract_page_text(ae_id, page_num, deps) or ""
        text = text.strip()
        if not text:
            continue
        blocks.append({"page": page_num, "text": text[:4000]})
    return blocks
