from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class SuggestDatesRequest(BaseModel):
    tables: list[dict[str, Any]]


class ReviewHintsRequest(BaseModel):
    tables: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []
    candidate_pages: list[int] = []


class PayTableExtractRequest(BaseModel):
    page_num: int


class PayTableRangeRequest(BaseModel):
    start_page: int
    end_page: int


class PayTableSaveRequest(BaseModel):
    action: str
    tables: list[dict[str, Any]]
    source_ref: str = ""
    notes: str = ""
    status: str = "in_progress"
    timeline_policy: Literal["current", "rule_anchored"] = "rule_anchored"


class PayTableRecalcDatesRequest(BaseModel):
    timeline_policy: Literal["current", "rule_anchored"] = "rule_anchored"


class SplitCouncilRequest(BaseModel):
    lgas: list[str]
    notes: str = ""


class ConfirmSingleCouncilRequest(BaseModel):
    lga: str
    notes: str = ""


class IntakeDecisionRequest(BaseModel):
    status: Literal["accepted", "rejected", "needs_review"]
    reason: str = ""
    notes: str = ""


class ClearReviewRecordRequest(BaseModel):
    reason: str = ""
    include_related: bool = True


class SectionStatusRequest(BaseModel):
    status: str


class SectionHumanQaRequest(BaseModel):
    enabled: bool
    notes: str = ""
    summary: str = ""


class AcceptUpliftRulesRequest(BaseModel):
    """Payload accepted by /uplift-rules/accept; empty body allowed."""

    rules: Optional[list[dict[str, Any]]] = None

    model_config = {"extra": "forbid"}


class UpdateAcceptedRulesRequest(BaseModel):
    """Patch the accepted rules list, for example to delete individual rules."""

    rules: list[dict]


class LlmConnectionUpdateRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""


class CellOverride(BaseModel):
    action: str
    weekly: Optional[float] = None


class ScenarioRequest(BaseModel):
    overrides: dict[str, dict[str, CellOverride]] = {}
    change_context: Optional[dict[str, Any]] = None


class ScenarioNoteRequest(BaseModel):
    notes: str
    overrides: Optional[dict[str, Any]] = None
    change_context: Optional[dict[str, Any]] = None


class ConstructTableRequest(BaseModel):
    effective_date: str


class PromoteRequest(BaseModel):
    period_effective_from: str
    kind: str


class UnwindRequest(BaseModel):
    period_effective_from: str
    kind: str


class RateCapConfirmRequest(BaseModel):
    financial_year: str
    rate_cap_value: float
    confirmed_date: str
    notes: str = ""
    source_reference: str = "ESC annual council rate caps page (https://www.esc.vic.gov.au/local-government/annual-council-rate-caps)"


__all__ = [
    "AcceptUpliftRulesRequest",
    "CellOverride",
    "ClearReviewRecordRequest",
    "ConfirmSingleCouncilRequest",
    "ConstructTableRequest",
    "IntakeDecisionRequest",
    "LlmConnectionUpdateRequest",
    "PayTableExtractRequest",
    "PayTableRangeRequest",
    "PayTableRecalcDatesRequest",
    "PayTableSaveRequest",
    "PromoteRequest",
    "RateCapConfirmRequest",
    "ReviewHintsRequest",
    "ScenarioNoteRequest",
    "ScenarioRequest",
    "SectionHumanQaRequest",
    "SectionStatusRequest",
    "SplitCouncilRequest",
    "SuggestDatesRequest",
    "UnwindRequest",
    "UpdateAcceptedRulesRequest",
]
