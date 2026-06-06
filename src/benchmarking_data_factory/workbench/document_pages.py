from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - optional at import time
    fitz = None  # type: ignore[assignment]


class DocumentPageError(Exception):
    """Base error for PDF page access failures."""


class PdfDependencyMissing(DocumentPageError):
    """Raised when PyMuPDF is not installed."""


class PdfNotFound(DocumentPageError):
    """Raised when an agreement PDF cannot be found."""


class PageOutOfRange(DocumentPageError):
    """Raised when a requested page number is outside the PDF."""


class DocumentPageService:
    """Resolve agreement PDFs and provide cached page text/image access."""

    def __init__(
        self,
        *,
        pdf_dir: Path,
        cache_dir: Path,
        page_render_dpi: int,
        fitz_module: Any | None = None,
    ):
        self.pdf_dir = pdf_dir
        self.cache_dir = cache_dir
        self.page_render_dpi = page_render_dpi
        self._fitz = fitz if fitz_module is None else fitz_module

    def require_fitz(self) -> None:
        if self._fitz is None:
            raise PdfDependencyMissing("PyMuPDF (fitz) is not installed")

    def ensure_cache_dir(self, ae_id: str) -> Path:
        path = self.cache_dir / ae_id.lower()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def pages_cache_path(self, ae_id: str) -> Path:
        return self.ensure_cache_dir(ae_id) / "pages.json"

    def full_text_path(self, ae_id: str) -> Path:
        return self.ensure_cache_dir(ae_id) / "full_text.txt"

    @staticmethod
    def compose_full_text(page_texts: list[str]) -> str:
        blocks = []
        for page_num, text in enumerate(page_texts, start=1):
            blocks.append(f"===== PAGE {page_num:04d} =====\n{str(text or '').rstrip()}")
        return ("\n\n".join(blocks).rstrip() + "\n") if blocks else ""

    def write_full_text_cache(self, ae_id: str, page_texts: list[str], *, force: bool = False) -> Path:
        path = self.full_text_path(ae_id)
        if force or not path.exists():
            path.write_text(self.compose_full_text(page_texts), encoding="utf-8")
        return path

    def find_pdf(self, ae_id: str) -> Path | None:
        needle = ae_id.lower().removesuffix(".pdf")
        if not self.pdf_dir.exists():
            return None
        for path in self.pdf_dir.iterdir():
            if path.is_file() and path.suffix.lower() == ".pdf" and path.stem.lower() == needle:
                return path
        parent_ae_id, split_slug = self.split_ae_id(needle)
        if split_slug:
            for path in self.pdf_dir.iterdir():
                if path.is_file() and path.suffix.lower() == ".pdf" and path.stem.lower() == parent_ae_id:
                    return path
        return None

    @staticmethod
    def split_ae_id(ae_id: str) -> tuple[str, str | None]:
        value = ae_id.lower()
        if "__" not in value:
            return value, None
        parent, _, slug = value.partition("__")
        return parent, slug or None

    def pdf_path_for(self, ae_id: str) -> Path:
        path = self.find_pdf(ae_id)
        if path is None:
            raise PdfNotFound(f"PDF not found for {ae_id}")
        return path

    def get_page_count(self, ae_id: str) -> int:
        self.require_fitz()
        pdf_path = self.pdf_path_for(ae_id)
        with self._fitz.open(pdf_path) as doc:
            return doc.page_count

    def extract_page_text(self, ae_id: str, page_num: int) -> str:
        self.require_fitz()
        cache_path = self.ensure_cache_dir(ae_id) / f"page_{page_num:04d}.txt"
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")
        pdf_path = self.pdf_path_for(ae_id)
        with self._fitz.open(pdf_path) as doc:
            if page_num < 1 or page_num > doc.page_count:
                raise PageOutOfRange("page_num out of range")
            text = doc.load_page(page_num - 1).get_text("text")
        cache_path.write_text(text, encoding="utf-8")
        return text

    def extract_all_page_texts(self, ae_id: str, *, force: bool = False) -> list[str]:
        cache_path = self.pages_cache_path(ae_id)
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            pages = [str(page or "") for page in payload] if isinstance(payload, list) else []
            self.write_full_text_cache(ae_id, pages)
            return pages
        self.require_fitz()
        pdf_path = self.pdf_path_for(ae_id)
        pages: list[str] = []
        with self._fitz.open(pdf_path) as doc:
            for page in doc:
                pages.append(page.get_text("text"))
        cache_path.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        self.write_full_text_cache(ae_id, pages, force=True)
        return pages

    def extract_full_text(self, ae_id: str, *, force: bool = False) -> str:
        cache_path = self.full_text_path(ae_id)
        if cache_path.exists() and not force:
            return cache_path.read_text(encoding="utf-8")
        pages = self.extract_all_page_texts(ae_id, force=force)
        self.write_full_text_cache(ae_id, pages, force=True)
        return cache_path.read_text(encoding="utf-8")

    def render_page_png(self, ae_id: str, page_num: int, dpi: int | None = None) -> bytes:
        self.require_fitz()
        render_dpi = dpi or self.page_render_dpi
        cache_path = self.ensure_cache_dir(ae_id) / f"page_{page_num:04d}_{render_dpi}.png"
        if cache_path.exists():
            return cache_path.read_bytes()
        pdf_path = self.pdf_path_for(ae_id)
        with self._fitz.open(pdf_path) as doc:
            if page_num < 1 or page_num > doc.page_count:
                raise PageOutOfRange("page_num out of range")
            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(dpi=render_dpi, alpha=False)
            data = pix.tobytes("png")
        cache_path.write_bytes(data)
        return data


__all__ = [
    "DocumentPageError",
    "DocumentPageService",
    "PageOutOfRange",
    "PdfDependencyMissing",
    "PdfNotFound",
]
