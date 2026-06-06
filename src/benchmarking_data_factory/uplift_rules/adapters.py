"""Adapter protocol between the suggest() pipeline and external I/O.

Production wires a `RealAdapter` (implemented later by main.py or a CLI
entry point). Tests wire a `FakeAdapter`. Keeping this boundary narrow
means suggest() stays a pure function of its inputs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Adapter(Protocol):
    """What suggest() needs from the outside world."""

    def pdf_sha256(self, ae_id: str) -> str: ...
    def page_count(self, ae_id: str) -> int: ...
    def page_text(self, ae_id: str, page_num: int) -> str: ...
    def all_page_texts(self, ae_id: str) -> list[str]: ...
    def call_llm(self, system: str, user_text: str, *, max_tokens: int, model: str) -> str: ...


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class FakeAdapter:
    """Deterministic in-memory adapter for tests.

    Construct with a dict {ae_id: {"pdf": bytes, "pages": [str, ...]}}
    and a canned LLM response string (or a callable `(system, user_text) -> str`).
    """

    documents: dict[str, dict]  # {ae_id: {"pdf": bytes, "pages": list[str]}}
    llm_response: object  # str | Callable[[str, str], str]

    def pdf_sha256(self, ae_id: str) -> str:
        return sha256_bytes(self.documents[ae_id]["pdf"])

    def page_count(self, ae_id: str) -> int:
        return len(self.documents[ae_id]["pages"])

    def page_text(self, ae_id: str, page_num: int) -> str:
        return self.documents[ae_id]["pages"][page_num - 1]

    def all_page_texts(self, ae_id: str) -> list[str]:
        return list(self.documents[ae_id]["pages"])

    def call_llm(self, system: str, user_text: str, *, max_tokens: int, model: str) -> str:
        if callable(self.llm_response):
            return self.llm_response(system, user_text)
        return str(self.llm_response)


__all__ = ["Adapter", "FakeAdapter", "sha256_bytes", "sha256_text"]
