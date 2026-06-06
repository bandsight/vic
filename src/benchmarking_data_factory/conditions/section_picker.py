"""Keyword page picker for conditions and benefits extraction."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from benchmarking_data_factory.conditions.schema import ConditionCategory


SPECIALISED_COHORT_PATTERNS: tuple[str, ...] = (
    r"\bmaternal\s+and\s+child\s+health\b",
    r"\bimmunisation\s+nurses?\b",
    r"\bpool\s+services?\b",
    r"\blifeguard\b",
    r"\bchild\s+care\b",
    r"\bearly\s+years\b",
    r"\blibrary\s+employees?\b",
    r"\btourism\b",
    r"\bvisitor\s+services?\b",
    r"\bsenior\s+officers?\b",
    r"\bapprentices?\b",
    r"\btrainees?\b",
    r"\bcadets?\b",
    r"\bschool\s+crossing\s+supervisors?\b",
    r"\baged\s+care\b",
    r"\bhome\s+care\b",
)

CATEGORY_PATTERNS: dict[ConditionCategory, tuple[str, ...]] = {
    "overtime_penalties_rosters": (
        r"\bovertime\b",
        r"\btime\s+in\s+lieu\b",
        r"\bTOIL\b",
        r"\bpenalt(?:y|ies)\b",
        r"\bpublic\s+holiday\b",
        r"\bweekend\b",
        r"\bcall[- ]?back\b",
        r"\bon[- ]?call\b",
        r"\bstandby\b",
        r"\brostered\s+day\s+off\b",
        r"\bRDO\b",
    ),
    "allowances_reimbursements": (
        r"\ballowance\b",
        r"\bmeal\s+allowance\b",
        r"\bfirst\s+aid\b",
        r"\bvehicle\b",
        r"\bmileage\b",
        r"\bkilometre\b",
        r"\btool\s+allowance\b",
        r"\bindustry\s+allowance\b",
        r"\bhigher\s+duties\b",
        r"\breimburse(?:ment|ments)?\b",
        r"\buniform\b",
    ),
    "paid_parental_family_leave": (
        r"\bparental\s+leave\b",
        r"\bprimary\s+carer\b",
        r"\bsecondary\s+carer\b",
        r"\bmaternity\b",
        r"\bpaternity\b",
        r"\badoption\b",
        r"\bsurrogacy\b",
        r"\bpre[- ]?natal\b",
    ),
    "redundancy_redeployment": (
        r"\bredundan(?:cy|t)\b",
        r"\bredeployment\b",
        r"\bretraining\b",
        r"\bseverance\b",
        r"\bretrench(?:ment|ed)?\b",
        r"\bsalary\s+maintenance\b",
    ),
    "superannuation": (
        r"\bsuperannuation\b",
        r"\bsuper\s+guarantee\b",
        r"\bemployer\s+contribution\b",
        r"\bsalary\s+sacrific(?:e|ing)\b",
    ),
    "annual_leave_loading": (
        r"\bannual\s+leave\b",
        r"\bleave\s+loading\b",
        r"\bcash(?:ing)?\s+out\b",
        r"\bshiftworker\s+leave\b",
    ),
    "personal_carers_sick_leave": (
        r"\bpersonal(?:/carer'?s?)?\s+leave\b",
        r"\bsick\s+leave\b",
        r"\bcarer'?s?\s+leave\b",
        r"\bcompassionate\s+leave\b",
        r"\bbereavement\b",
    ),
    "long_service_leave": (
        r"\blong\s+service\s+leave\b",
        r"\bLSL\b",
    ),
    "family_domestic_violence_leave": (
        r"\bfamily\s+(?:and\s+)?domestic\s+violence\b",
        r"\bfamily\s+violence\b",
        r"\bFDV\b",
    ),
    "study_professional_development": (
        r"\bstudy\s+leave\b",
        r"\bprofessional\s+development\b",
        r"\btraining\s+leave\b",
        r"\bconference\b",
        r"\bseminar\b",
    ),
    "other_conditions_benefits": (
        r"\btransition\s+to\s+retirement\b",
        r"\bflexible\s+work\b",
        r"\baccident\s+make[- ]?up\b",
        r"\bincome\s+protection\b",
    ),
}

QUANTIFIER_PATTERN = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?\s?"
    r"(?:hours?|days?|weeks?|months?|years?)\b|time\s+and\s+a\s+half|double\s+time)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConditionPageCandidate:
    category: ConditionCategory
    page_number: int
    score: int
    matched_terms: tuple[str, ...]
    has_quantifier: bool


def is_likely_specialised_cohort_page(page_text: str) -> bool:
    return any(re.search(pattern, page_text or "", re.IGNORECASE) for pattern in SPECIALISED_COHORT_PATTERNS)


def score_condition_pages(
    pages: Iterable[str],
    *,
    max_pages_per_category: int = 8,
    exclude_specialised_cohorts: bool = True,
) -> list[ConditionPageCandidate]:
    """Rank likely pages for each conditions category.

    The scorer intentionally rewards nearby numeric language because the downstream
    schema is designed for quantifiable comparison, not just clause discovery.
    """

    candidates: dict[ConditionCategory, list[ConditionPageCandidate]] = {}
    for page_number, page_text in enumerate(pages, start=1):
        text = page_text or ""
        if exclude_specialised_cohorts and is_likely_specialised_cohort_page(text):
            continue
        for category, patterns in CATEGORY_PATTERNS.items():
            matches = []
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matches.append(pattern)
            if not matches:
                continue
            has_quantifier = bool(QUANTIFIER_PATTERN.search(text))
            score = len(matches) * 10 + (5 if has_quantifier else 0)
            candidates.setdefault(category, []).append(
                ConditionPageCandidate(
                    category=category,
                    page_number=page_number,
                    score=score,
                    matched_terms=tuple(matches),
                    has_quantifier=has_quantifier,
                )
            )

    ranked: list[ConditionPageCandidate] = []
    for category_candidates in candidates.values():
        ranked.extend(
            sorted(category_candidates, key=lambda item: (-item.score, item.page_number))[
                :max_pages_per_category
            ]
        )
    return sorted(ranked, key=lambda item: (item.category, -item.score, item.page_number))
