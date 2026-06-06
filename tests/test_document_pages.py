from __future__ import annotations

import json

from benchmarking_data_factory.workbench.document_pages import DocumentPageService


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def get_text(self, _kind: str) -> str:
        return self.text


class FakeDocument:
    def __init__(self, texts: list[str]):
        self.pages = [FakePage(text) for text in texts]
        self.page_count = len(self.pages)

    def __enter__(self) -> "FakeDocument":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self):
        return iter(self.pages)

    def load_page(self, index: int) -> FakePage:
        return self.pages[index]


class FakeFitz:
    def __init__(self, texts: list[str]):
        self.texts = texts
        self.open_count = 0

    def open(self, _path):
        self.open_count += 1
        return FakeDocument(self.texts)


class FailingFitz:
    def open(self, _path):
        raise AssertionError("PDF should not be opened when pages.json is already cached")


def test_extract_all_page_texts_writes_full_text_cache(tmp_path):
    pdf_dir = tmp_path / "documents"
    cache_dir = tmp_path / "cache"
    pdf_dir.mkdir()
    (pdf_dir / "ae1.pdf").write_bytes(b"%PDF-1.4\n")
    service = DocumentPageService(
        pdf_dir=pdf_dir,
        cache_dir=cache_dir,
        page_render_dpi=150,
        fitz_module=FakeFitz(["First page\n", "Second page"]),
    )

    pages = service.extract_all_page_texts("AE1")

    assert pages == ["First page\n", "Second page"]
    assert json.loads((cache_dir / "ae1" / "pages.json").read_text(encoding="utf-8")) == pages
    assert (cache_dir / "ae1" / "full_text.txt").read_text(encoding="utf-8") == (
        "===== PAGE 0001 =====\nFirst page\n\n"
        "===== PAGE 0002 =====\nSecond page\n"
    )


def test_extract_all_page_texts_materialises_full_text_from_cached_pages(tmp_path):
    cache_dir = tmp_path / "cache"
    pages_dir = cache_dir / "ae1"
    pages_dir.mkdir(parents=True)
    (pages_dir / "pages.json").write_text(json.dumps(["Cached one", "Cached two"]), encoding="utf-8")
    service = DocumentPageService(
        pdf_dir=tmp_path / "documents",
        cache_dir=cache_dir,
        page_render_dpi=150,
        fitz_module=FailingFitz(),
    )

    pages = service.extract_all_page_texts("ae1")

    assert pages == ["Cached one", "Cached two"]
    assert (pages_dir / "full_text.txt").read_text(encoding="utf-8") == (
        "===== PAGE 0001 =====\nCached one\n\n"
        "===== PAGE 0002 =====\nCached two\n"
    )


def test_extract_full_text_force_reextracts_from_pdf(tmp_path):
    pdf_dir = tmp_path / "documents"
    cache_dir = tmp_path / "cache"
    pages_dir = cache_dir / "ae1"
    pdf_dir.mkdir()
    pages_dir.mkdir(parents=True)
    (pdf_dir / "ae1.pdf").write_bytes(b"%PDF-1.4\n")
    (pages_dir / "pages.json").write_text(json.dumps(["Old cached text"]), encoding="utf-8")
    (pages_dir / "full_text.txt").write_text("old full text", encoding="utf-8")
    service = DocumentPageService(
        pdf_dir=pdf_dir,
        cache_dir=cache_dir,
        page_render_dpi=150,
        fitz_module=FakeFitz(["Fresh text"]),
    )

    full_text = service.extract_full_text("ae1", force=True)

    assert full_text == "===== PAGE 0001 =====\nFresh text\n"
    assert json.loads((pages_dir / "pages.json").read_text(encoding="utf-8")) == ["Fresh text"]
