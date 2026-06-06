"""Top-level suggest() orchestrator.

Inputs: ae_id + adapter + config. Output: UpliftRulesSuggestion.

Pipeline:
  1. Gather candidate pages (section_picker.rank_uplift_pages)
  2. Build deterministic ExtractionInputs
  3. Check cache. If hit, return cached result unchanged.
  4. Call LLM via adapter
  5. Parse response into RulesDocument
  6. Wrap with Provenance + write to cache
  7. Return UpliftRulesSuggestion

The function NEVER raises on LLM failure — it returns a suggestion whose
extraction_status is llm_error and rules is empty. Callers surface the
error via the provenance field.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from benchmarking_data_factory.uplift_rules.adapters import Adapter, sha256_text
from benchmarking_data_factory.uplift_rules.cache import (
    SuggestionCache,
    compute_suggestion_id,
)
from benchmarking_data_factory.uplift_rules.prompt import get_prompt
from benchmarking_data_factory.uplift_rules.schema import (
    CURRENT_PROMPT_VERSION,
    ExtractionInputs,
    Provenance,
    RulesDocument,
    UpliftRule,
    UpliftRulesSuggestion,
)
from benchmarking_data_factory.uplift_rules.section_picker import (
    rank_uplift_pages,
    rank_uplift_pages_with_continuation,
)


DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_PAGES = 16
DEFAULT_MAX_TOKENS = 4000


@dataclass(frozen=True)
class SuggestConfig:
    model: str = DEFAULT_MODEL
    max_pages: int = DEFAULT_MAX_PAGES
    max_tokens: int = DEFAULT_MAX_TOKENS
    prompt_version: str = CURRENT_PROMPT_VERSION
    cache_root: Optional[Path] = None   # defaults resolved at runtime
    force_refresh: bool = False          # if True, skip cache read
    include_continuation_pages: bool = True  # if True, append each primary page's successor
    code_git_sha: Optional[str] = None   # defaults to `git rev-parse HEAD` if None


def _default_cache_root() -> Path:
    here = Path(__file__).resolve()
    # <repo>/src/benchmarking_data_factory/uplift_rules/suggest.py
    # -> <repo>/data/cache/uplift_rules_suggestions
    repo_root = here.parents[3]
    return repo_root / "data" / "cache" / "uplift_rules_suggestions"


def _resolve_git_sha(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("ascii").strip()
    except Exception:
        return "unknown"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _strip_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        # drop the first line (which may be ```json) and the closing fence
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _parse_llm_response(raw: str, ae_id: str) -> tuple[RulesDocument, str]:
    """Parse the LLM JSON into a RulesDocument.

    Returns (document, status) where status is 'ok' or 'llm_error'. On error,
    document has empty rules and council='(unknown)'.
    """
    stripped = _strip_fences(raw)
    if not stripped:
        return (
            RulesDocument(
                ae_id=ae_id,
                council="(unknown)",
                timing_pattern="unknown",
                rules=(),
                notes="empty LLM response",
            ),
            "empty",
        )
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Try to recover the first {...} block
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return (
                RulesDocument(
                    ae_id=ae_id,
                    council="(unknown)",
                    timing_pattern="unknown",
                    rules=(),
                    notes="LLM returned non-JSON content",
                ),
                "llm_error",
            )
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return (
                RulesDocument(
                    ae_id=ae_id,
                    council="(unknown)",
                    timing_pattern="unknown",
                    rules=(),
                    notes="LLM JSON parse failed after recovery",
                ),
                "llm_error",
            )

    rules_raw = data.get("rules") or []
    rules: list[UpliftRule] = []
    for r in rules_raw:
        if not isinstance(r, dict):
            continue
        try:
            rules.append(
                UpliftRule(
                    period_label=str(r.get("period_label", "")),
                    quantum=str(r.get("quantum", "")),
                    quantum_type=r.get("quantum_type", "unknown"),
                    timing_clause=str(r.get("timing_clause", "")),
                    effective_date=r.get("effective_date"),
                    quantum_floor=r.get("quantum_floor"),
                    quantum_ceiling=r.get("quantum_ceiling"),
                    quantum_external_ref=r.get("quantum_external_ref"),
                    quantum_external_definition=r.get("quantum_external_definition"),
                    quantum_resolution=r.get("quantum_resolution"),
                    source_page=r.get("source_page"),
                    applies_to=r.get("applies_to"),
                    nearby_table_headings=tuple(str(item) for item in (r.get("nearby_table_headings") or []) if item),
                    extraction_warnings=tuple(str(item) for item in (r.get("extraction_warnings") or []) if item),
                    confidence=float(r.get("confidence", 0.0) or 0.0),
                )
            )
        except (TypeError, ValueError):
            continue

    covered = data.get("covered_councils") or []
    if isinstance(covered, list):
        covered_tuple = tuple(str(c) for c in covered)
    else:
        covered_tuple = ()

    doc = RulesDocument(
        ae_id=ae_id,
        council=str(data.get("council", "(unknown)")),
        timing_pattern=data.get("timing_pattern", "unknown"),
        rules=tuple(rules),
        notes=str(data.get("notes", "")),
        covered_councils=covered_tuple,
        multi_employer=bool(data.get("multi_employer", False)),
    )
    return doc, "ok"


def _build_user_text(ae_id: str, pages: list[tuple[int, str]]) -> str:
    """Compose the user message: ae_id + concatenated page blocks."""
    blocks = [f"Agreement id: {ae_id}"]
    blocks.append("")
    for page_num, text in pages:
        blocks.append(f"[Page {page_num}]")
        blocks.append(text.strip()[:4000])
        blocks.append("")
    return "\n".join(blocks).rstrip()


def suggest(ae_id: str, adapter: Adapter, config: Optional[SuggestConfig] = None) -> UpliftRulesSuggestion:
    """Run the full suggest pipeline. Never raises."""
    cfg = config or SuggestConfig()
    prompt = get_prompt(cfg.prompt_version)
    cache_root = cfg.cache_root or _default_cache_root()
    cache = SuggestionCache(cache_root)

    # 1. Candidate pages
    all_pages = adapter.all_page_texts(ae_id)
    ranked = rank_uplift_pages_with_continuation(
        all_pages, include_continuation=cfg.include_continuation_pages
    )[: cfg.max_pages]
    ranked.sort()  # canonical order for cache stability
    page_blocks = [(p, adapter.page_text(ae_id, p)) for p in ranked]
    user_text = _build_user_text(ae_id, page_blocks)

    # 2. Deterministic inputs
    page_text_concat = "\n---\n".join(text for _, text in page_blocks)
    inputs = ExtractionInputs(
        pdf_sha256=adapter.pdf_sha256(ae_id),
        page_numbers=tuple(ranked),
        page_text_sha256=sha256_text(page_text_concat),
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
        model=cfg.model,
    )
    suggestion_id = compute_suggestion_id(inputs)

    # 3. Cache lookup
    if not cfg.force_refresh:
        cached = cache.get(suggestion_id)
        if cached is not None:
            return cached

    # 4. LLM call
    t0 = _now_utc()
    try:
        raw = adapter.call_llm(
            prompt.system, user_text,
            max_tokens=cfg.max_tokens, model=cfg.model,
        )
        llm_ok = True
    except Exception as exc:  # noqa: BLE001
        raw = f"ERROR: {type(exc).__name__}: {exc}"
        llm_ok = False
    t1 = _now_utc()

    # 5. Parse
    if llm_ok and not raw.startswith("ERROR:"):
        document, parse_status = _parse_llm_response(raw, ae_id)
    else:
        document = RulesDocument(
            ae_id=ae_id,
            council="(unknown)",
            timing_pattern="unknown",
            rules=(),
            notes="LLM adapter raised an error",
        )
        parse_status = "llm_error"

    status_map = {"ok": "ok", "llm_error": "llm_error", "empty": "empty"}
    extraction_status = status_map.get(parse_status, "llm_error")

    # 6. Wrap with provenance and cache
    provenance = Provenance(
        inputs=inputs,
        code_git_sha=_resolve_git_sha(cfg.code_git_sha),
        run_started_at=t0,
        run_completed_at=t1,
        run_duration_ms=int((t1 - t0).total_seconds() * 1000),
        llm_raw_response=raw,
        extraction_status=extraction_status,
    )
    suggestion = UpliftRulesSuggestion(
        document=document,
        provenance=provenance,
        suggestion_id=suggestion_id,
    )
    cache.put(suggestion)
    return suggestion


__all__ = ["SuggestConfig", "suggest"]
