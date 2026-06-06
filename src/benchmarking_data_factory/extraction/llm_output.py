from __future__ import annotations

import re


def strip_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
    lines = cleaned.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("tables:"):
            cleaned = "\n".join(lines[i:])
            break
    return cleaned.strip()


def strip_json_preamble(text: str) -> str:
    cleaned = strip_fences(text)
    if cleaned and cleaned[0] not in "{[":
        brace_idx = min(
            (cleaned.index(c) for c in "{[" if c in cleaned),
            default=None,
        )
        if brace_idx is not None and brace_idx > 0:
            cleaned = cleaned[brace_idx:]
    return cleaned.strip()


__all__ = ["strip_fences", "strip_json_preamble"]
