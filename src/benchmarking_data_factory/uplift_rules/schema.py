"""Canonical data model for the uplift rules subsystem.

All structures are immutable dataclasses. The provenance wrapper records
enough metadata to reproduce any suggestion deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

# Canonical enums — changes require a prompt version bump and migration
QuantumType = Literal[
    "percentage",
    "pct_OR_floor",
    "conditional",
    "flat",
    "table_embedded",
    "unknown",
]

TimingPattern = Literal[
    "annual_fixed_date",
    "annual_specific_pp",
    "annual_anniversary",
    "irregular_multi_date",
    "biannual_fixed",
    "one_time",
    "performance_based",
    "external_confirmation",
    "unknown",
]


@dataclass(frozen=True)
class UpliftRule:
    """A single uplift rule as extracted from an agreement."""
    period_label: str
    quantum: str
    quantum_type: QuantumType
    timing_clause: str
    effective_date: Optional[str] = None  # ISO YYYY-MM-DD where possible
    quantum_floor: Optional[str] = None
    quantum_ceiling: Optional[str] = None
    quantum_external_ref: Optional[str] = None
    quantum_external_definition: Optional[str] = None
    quantum_resolution: Optional[str] = None
    source_page: Optional[int] = None
    applies_to: Optional[str] = None
    nearby_table_headings: tuple[str, ...] = ()
    extraction_warnings: tuple[str, ...] = ()
    confidence: float = 0.0  # 0.0–1.0


@dataclass(frozen=True)
class RulesDocument:
    """All uplift rules extracted from one agreement, plus document-level metadata."""
    ae_id: str
    council: str
    timing_pattern: TimingPattern
    rules: tuple[UpliftRule, ...]
    notes: str = ""
    covered_councils: tuple[str, ...] = ()
    multi_employer: bool = False


@dataclass(frozen=True)
class ExtractionInputs:
    """Exact inputs to the extraction — used for cache keys and replay."""
    pdf_sha256: str
    page_numbers: tuple[int, ...]   # which pages were sent to LLM
    page_text_sha256: str           # hash of concatenated page text
    prompt_version: str             # e.g. "pass1_system_v1"
    prompt_sha256: str              # hash of actual prompt string
    model: str                      # e.g. "claude-sonnet-4-20250514"


@dataclass(frozen=True)
class Provenance:
    """Everything needed to explain or reproduce a suggestion."""
    inputs: ExtractionInputs
    code_git_sha: str               # workbench git HEAD at run time
    run_started_at: datetime        # UTC
    run_completed_at: datetime      # UTC
    run_duration_ms: int
    llm_raw_response: str           # full response body for replay
    extraction_status: Literal["ok", "llm_error", "regex_fallback", "empty"]


@dataclass(frozen=True)
class UpliftRulesSuggestion:
    """A complete suggestion: the extracted document + its provenance."""
    document: RulesDocument
    provenance: Provenance
    suggestion_id: str  # cache key; content-hash derived


# Prompt version registry — increment when the prompt changes
CURRENT_PROMPT_VERSION = "pass1_system_v2"
