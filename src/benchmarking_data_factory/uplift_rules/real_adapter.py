"""Production adapter backing Adapter protocol with main.py helpers.

The RealAdapter is a thin shim. It knows nothing about business logic —
its only job is to translate between the protocol signatures and the
existing main.py helpers. Tests should use FakeAdapter instead.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable


class RealAdapter:
    """Adapter backed by main.py callables passed in at construction.

    We inject the callables rather than importing main.py directly so the
    adapter stays importable from pipeline code that doesn't load the web
    server (FastAPI, fitz, etc.).
    """

    def __init__(
        self,
        *,
        pdf_path_resolver: Callable[[str], Path],
        page_count_fn: Callable[[str], int],
        page_text_fn: Callable[[str, int], str],
        all_page_texts_fn: Callable[[str], list[str]],
        call_llm_fn: Callable[..., str],
        default_model: str,
    ):
        self._pdf_path = pdf_path_resolver
        self._page_count = page_count_fn
        self._page_text = page_text_fn
        self._all_pages = all_page_texts_fn
        self._call_llm = call_llm_fn
        self._default_model = default_model

    def pdf_sha256(self, ae_id: str) -> str:
        path = self._pdf_path(ae_id)
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def page_count(self, ae_id: str) -> int:
        return self._page_count(ae_id)

    def page_text(self, ae_id: str, page_num: int) -> str:
        return self._page_text(ae_id, page_num)

    def all_page_texts(self, ae_id: str) -> list[str]:
        return self._all_pages(ae_id)

    def call_llm(self, system: str, user_text: str, *, max_tokens: int, model: str) -> str:
        # main.py's call_llm accepts (system, user_blocks, max_tokens).
        # Wrap the user_text into a single-block message.
        user_blocks = [{"type": "text", "text": user_text}]
        # main.py's signature doesn't currently take `model`; we honour it
        # for forward-compatibility by recording it in the call but still
        # delegating. If the injected call_llm signature supports model=,
        # pass it; otherwise fall back.
        try:
            return self._call_llm(system, user_blocks, max_tokens=max_tokens, model=model)
        except TypeError:
            return self._call_llm(system, user_blocks, max_tokens=max_tokens)


__all__ = ["RealAdapter"]
