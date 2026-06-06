"""Normalized schema helpers for council job intake records."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


COUNCIL_JOB_SCHEMA_VERSION = "council_job.v1"
try:
    VICTORIA_TZ = ZoneInfo("Australia/Melbourne")
except ZoneInfoNotFoundError:  # Windows test environments may not ship tzdata.
    VICTORIA_TZ = timezone(timedelta(hours=10), "AEST")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_name in {"br", "p", "li", "tr", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag_name in {"p", "li", "tr", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def text(self) -> str:
        return normalize_whitespace(unescape(" ".join(self.parts)))


def normalize_council_job_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a schema-versioned, governance-ready council job record."""
    normalized = dict(record)
    field_sources = dict(record.get("field_sources") or {})
    description_html = str(record.get("description_html") or "")
    description_text = str(record.get("description_text") or "").strip()
    if not description_text and description_html:
        description_text = html_to_text(description_html)
    detail_text = str(record.get("detail_text") or "").strip()
    position_description_text = str(record.get("position_description_text") or "").strip()
    attachment_text = str(record.get("attachment_text") or "").strip()
    document_parts: list[str] = []
    for value in (position_description_text, attachment_text):
        if value and value not in document_parts:
            document_parts.append(value)
    linked_document_text = normalize_whitespace(" ".join(document_parts))
    linked_document_source = first_present(
        record.get("position_description_text_source"),
        record.get("attachment_text_source"),
        "linked_document",
    )

    evidence_text = normalize_whitespace(" ".join(str(value or "") for value in (
        record.get("job_title"),
        record.get("classification_band"),
        record.get("salary_text"),
        record.get("work_type"),
        record.get("description_text"),
        description_text,
        detail_text,
        linked_document_text,
        html_to_text(description_html) if description_html and not description_text else "",
    )))
    detail_classification_band = extract_classification_band(detail_text)
    document_classification_band = extract_classification_band(linked_document_text)
    detail_classification_band_raw = _extract_classification_band_raw(detail_text)
    document_classification_band_raw = _extract_classification_band_raw(linked_document_text)
    classification_band_raw = first_present(
        record.get("classification_band_raw"),
        record.get("classification_band"),
        document_classification_band_raw,
        detail_classification_band_raw,
        _extract_classification_band_raw(evidence_text),
    )
    detail_salary_text = extract_salary_text(detail_text)
    document_salary_text = extract_salary_text(linked_document_text)

    posted_at_text = first_present(
        record.get("posted_at_text"),
        record.get("posted_date_text"),
        _extract_labeled_date(evidence_text, ("posted", "advertised", "date posted")),
    )
    closing_at_text = first_present(
        record.get("closing_at_text"),
        record.get("closing_date_text"),
        record.get("closing_date"),
        _extract_labeled_date(evidence_text, ("closing date", "closing", "applications close", "closes")),
        _extract_application_deadline(evidence_text),
    )
    job_number = first_present(
        record.get("job_number"),
        _extract_labeled_reference(evidence_text),
    )
    posted_at = record.get("posted_at") or parse_job_datetime(posted_at_text, end_of_day=False)
    closing_at = record.get("closing_at") or parse_job_datetime(closing_at_text, end_of_day=True)

    classification_band = extract_classification_band(str(classification_band_raw or ""))
    standard_band_number = extract_standard_band_number(classification_band or evidence_text)
    salary_text = first_present(
        record.get("salary_text"),
        document_salary_text,
        detail_salary_text,
        extract_salary_text(evidence_text),
    )
    salary = extract_salary_range(salary_text) if salary_text else {}
    scope = classify_standard_band_scope(
        title=str(record.get("job_title") or ""),
        work_type=str(record.get("work_type") or ""),
        evidence_text=evidence_text,
        standard_band_number=standard_band_number,
    )

    if description_text:
        normalized["description_text"] = description_text
        field_sources.setdefault("description_text", record.get("description_source") or "source_payload")
    if description_html:
        normalized["description_html"] = description_html
    if detail_text:
        normalized["detail_text"] = detail_text
        field_sources.setdefault("detail_text", record.get("detail_text_source") or "detail_page")
    if position_description_text:
        normalized["position_description_text"] = position_description_text
        normalized.setdefault("position_description_excerpt", position_description_text[:800])
        field_sources.setdefault(
            "position_description_text",
            linked_document_source,
        )
    if attachment_text:
        normalized["attachment_text"] = attachment_text
        field_sources.setdefault("attachment_text", record.get("attachment_text_source") or "linked_document")
    if posted_at:
        normalized["posted_at"] = posted_at
        field_sources.setdefault("posted_at", "source_payload" if record.get("posted_at_text") else "parsed_text")
    if posted_at_text:
        normalized["posted_at_text"] = posted_at_text
    if closing_at:
        normalized["closing_at"] = closing_at
        field_sources.setdefault("closing_at", "source_payload" if record.get("closing_at_text") else "parsed_text")
    if closing_at_text:
        normalized["closing_at_text"] = closing_at_text
    if job_number:
        normalized["job_number"] = job_number
        normalized.setdefault("source_job_id", job_number)
        field_sources.setdefault("job_number", "source_payload" if record.get("job_number") else "parsed_text")
    if classification_band:
        normalized["classification_band"] = classification_band
        if classification_band_raw and str(classification_band_raw) != classification_band:
            normalized["classification_band_raw"] = str(classification_band_raw)
        if not record.get("classification_band") and document_classification_band == classification_band:
            field_sources.setdefault("classification_band", linked_document_source)
        elif not record.get("classification_band") and detail_classification_band == classification_band:
            field_sources.setdefault("classification_band", "detail_page")
        else:
            field_sources.setdefault("classification_band", "parsed_text")
    if standard_band_number is not None:
        normalized["standard_band_number"] = standard_band_number
    if salary_text:
        normalized["salary_text"] = salary_text
        if record.get("salary_text"):
            field_sources.setdefault("salary_text", "source_payload")
        elif document_salary_text == salary_text:
            field_sources.setdefault("salary_text", linked_document_source)
        elif detail_salary_text == salary_text:
            field_sources.setdefault("salary_text", "detail_page")
        else:
            field_sources.setdefault("salary_text", "parsed_text")
    if salary:
        normalized.update(salary)
        for key in salary:
            field_sources.setdefault(key, "parsed_salary_text")

    normalized.update({
        "schema_version": COUNCIL_JOB_SCHEMA_VERSION,
        "canonical_url": record.get("canonical_url") or record.get("job_url"),
        "source_url": record.get("source_url") or record.get("job_url"),
        "job_status": record.get("job_status") or "open",
        "state": record.get("state") or "VIC",
        "is_standard_band_1_to_8": scope["band_scope"] == "standard_band_1_8",
        "band_scope": scope["band_scope"],
        "governance_status": scope["governance_status"],
        "governance_notes": scope["governance_notes"],
        "salary_band_validation_status": record.get("salary_band_validation_status") or "not_checked",
        "salary_band_validation": record.get("salary_band_validation") or {
            "status": "not_checked",
            "notes": "Salary has not been compared with governed pay-table data yet.",
        },
        "field_sources": field_sources,
    })
    _apply_reference_date_fields(normalized, field_sources, posted_at=posted_at, closing_at=closing_at)
    _normalise_salary_aliases(normalized)
    return normalized


def validate_salary_against_pay_rows(
    job: dict[str, Any],
    pay_rows: list[dict[str, Any]],
    *,
    tolerance_weekly: float = 2.0,
) -> dict[str, Any]:
    """Compare an advertised job salary against current governed pay-table rows."""
    band_number = job.get("standard_band_number")
    salary_min = _to_float(first_present(job.get("advertised_salary_min"), job.get("salary_min")))
    salary_max = _to_float(first_present(job.get("advertised_salary_max"), job.get("salary_max")))
    salary_period = _normalize_salary_period(first_present(job.get("advertised_salary_period"), job.get("salary_period")))
    if not band_number or salary_min is None:
        return _salary_validation("not_checkable", "Job is missing standard band or salary values.")
    advertised_weekly = _advertised_weekly_range(salary_min, salary_max, salary_period)
    if advertised_weekly is None:
        return _salary_validation("unsupported_salary_period", f"Salary period '{salary_period or 'unknown'}' cannot be compared to weekly governed rates.")

    comparator_rows = _current_band_comparator_rows(job, pay_rows, int(band_number))
    if not comparator_rows:
        return _salary_validation("no_comparator", "No governed pay-table rows matched this council and band.")
    comparator_values = [_to_float(row.get("weekly_rate")) for row in comparator_rows]
    comparator_values = [value for value in comparator_values if value is not None]
    if not comparator_values:
        return _salary_validation("no_comparator", "Matched pay-table rows did not carry weekly rates.")

    comparator_min = min(comparator_values)
    comparator_max = max(comparator_values)
    advertised_min, advertised_max = advertised_weekly
    within = (
        advertised_min >= comparator_min - tolerance_weekly
        and advertised_max <= comparator_max + tolerance_weekly
    )
    status = "match" if within else "mismatch"
    notes = "Advertised salary sits within the governed band range." if within else "Advertised salary falls outside the governed band range."
    return {
        "status": status,
        "notes": notes,
        "advertised_weekly_min": round(advertised_min, 2),
        "advertised_weekly_max": round(advertised_max, 2),
        "comparator_weekly_min": round(comparator_min, 2),
        "comparator_weekly_max": round(comparator_max, 2),
        "comparator_rows": len(comparator_rows),
        "comparator_effective_from": comparator_rows[0].get("effective_from"),
        "tolerance_weekly": tolerance_weekly,
    }


def with_salary_band_validation(job: dict[str, Any], pay_rows: list[dict[str, Any]]) -> dict[str, Any]:
    validation = validate_salary_against_pay_rows(job, pay_rows)
    return {
        **job,
        "salary_band_validation_status": validation["status"],
        "salary_band_validation": validation,
    }


def enrich_job_with_pay_rows(job: dict[str, Any], pay_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach Enterprise Agreement salary context and salary-to-band inference."""
    enriched = normalize_council_job_record(job)
    band_number = _to_int(enriched.get("standard_band_number"))
    if band_number is not None:
        comparator_rows = _current_band_comparator_rows(enriched, pay_rows, band_number)
        enterprise_salary = _enterprise_agreement_salary_from_rows(comparator_rows)
        if enterprise_salary:
            enriched.update(enterprise_salary)
            enriched["salary_enrichment_status"] = "enterprise_agreement_salary_available"
            enriched["salary_enrichment_notes"] = "Enterprise Agreement salary range filled from governed pay-table rows for the job band and reference date."
        else:
            enriched["salary_enrichment_status"] = "no_band_comparator"
            enriched["salary_enrichment_notes"] = "No governed pay-table rows matched the job band inside the job reference period."
        if first_present(enriched.get("advertised_salary_min"), enriched.get("salary_min")) is not None:
            validation = validate_salary_against_pay_rows(enriched, pay_rows)
            enriched["salary_band_validation_status"] = validation["status"]
            enriched["salary_band_validation"] = validation
        return enriched

    inferred = infer_band_candidates_from_salary(job, pay_rows)
    if inferred:
        enriched["band_inference_status"] = "candidate_bands_from_salary"
        enriched["inferred_standard_band_numbers"] = [item["standard_band_number"] for item in inferred]
        enriched["inferred_classification_bands"] = [f"Band {item['standard_band_number']}" for item in inferred]
        enriched["band_inference_candidates"] = inferred
        if len(inferred) == 1:
            enriched["inferred_standard_band_number"] = inferred[0]["standard_band_number"]
            enriched["inferred_classification_band"] = f"Band {inferred[0]['standard_band_number']}"
            enriched["band_scope"] = "inferred_standard_band_1_8"
            enriched["governance_status"] = "needs_band_confirmation"
            enriched["governance_notes"] = "Salary maps to one governed Band 1-8 range; source band still needs confirmation."
    else:
        enriched["band_inference_status"] = "no_salary_band_match" if job.get("salary_min") is not None else "not_checkable"
    return enriched


def infer_band_candidates_from_salary(
    job: dict[str, Any],
    pay_rows: list[dict[str, Any]],
    *,
    tolerance_weekly: float = 2.0,
) -> list[dict[str, Any]]:
    salary_min = _to_float(first_present(job.get("advertised_salary_min"), job.get("salary_min")))
    salary_max = _to_float(first_present(job.get("advertised_salary_max"), job.get("salary_max")))
    salary_period = _normalize_salary_period(first_present(job.get("advertised_salary_period"), job.get("salary_period")))
    if salary_min is None:
        return []
    advertised_weekly = _advertised_weekly_range(salary_min, salary_max, salary_period)
    if advertised_weekly is None:
        return []
    advertised_min, advertised_max = advertised_weekly
    rows = _effective_council_pay_rows(job, pay_rows)
    candidates: list[dict[str, Any]] = []
    for band_number in range(1, 9):
        band_rows = [
            row for row in rows
            if str(row.get("standard_band") or row.get("band") or "").lstrip("0") == str(band_number)
        ]
        weekly_values = [_to_float(row.get("weekly_rate")) for row in band_rows]
        weekly_values = [value for value in weekly_values if value is not None]
        if not weekly_values:
            continue
        comparator_min = min(weekly_values)
        comparator_max = max(weekly_values)
        within = (
            advertised_min >= comparator_min - tolerance_weekly
            and advertised_max <= comparator_max + tolerance_weekly
        )
        if within:
            candidates.append({
                "standard_band_number": band_number,
                "comparator_weekly_min": round(comparator_min, 2),
                "comparator_weekly_max": round(comparator_max, 2),
                "advertised_weekly_min": round(advertised_min, 2),
                "advertised_weekly_max": round(advertised_max, 2),
                "comparator_rows": len(band_rows),
                "comparator_effective_from": band_rows[0].get("effective_from") if band_rows else None,
            })
    return candidates


def classify_standard_band_scope(
    *,
    title: str,
    work_type: str,
    evidence_text: str,
    standard_band_number: int | None,
) -> dict[str, str]:
    haystack = normalize_whitespace(" ".join([title, work_type, evidence_text])).lower()
    role_scope_text = normalize_whitespace(" ".join([title, work_type])).lower()
    if re.search(r"\b(volunteer|voluntary|work experience|student placement|unpaid)\b", role_scope_text):
        return {
            "band_scope": "non_standard_or_unpaid",
            "governance_status": "auto_excluded",
            "governance_notes": "Excluded because the role appears unpaid, volunteer, or placement based.",
        }
    if standard_band_number is not None and 1 <= standard_band_number <= 8:
        return {
            "band_scope": "standard_band_1_8",
            "governance_status": "auto_included",
            "governance_notes": f"Included because source text references Band {standard_band_number}.",
        }
    if re.search(r"\bband\s*(?:9|10|11|12)\b", haystack) or re.search(r"\b(chief executive officer|chief executive|ceo|senior officer)\b", role_scope_text):
        return {
            "band_scope": "non_standard_or_unpaid",
            "governance_status": "auto_excluded",
            "governance_notes": "Excluded because the role appears outside standard Band 1-8 coverage.",
        }
    return {
        "band_scope": "unknown",
        "governance_status": "needs_band_review",
        "governance_notes": "Band 1-8 evidence was not found in the available source text.",
    }


def extract_classification_band(text: str) -> str | None:
    match = re.search(r"\bBand\s*(?P<band>[1-9](?:[A-Z])?)\b", text or "", re.I)
    if not match:
        return None
    number_match = re.search(r"[1-9]", match.group("band") or "")
    if not number_match:
        return None
    return f"Band {number_match.group(0)}"


def _extract_classification_band_raw(text: str) -> str | None:
    match = re.search(r"\bBand\s*(?P<band>[1-9](?:[A-Z])?)\b", text or "", re.I)
    if not match:
        return None
    return f"Band {match.group('band').upper()}"


def extract_standard_band_number(text: str | None) -> int | None:
    match = re.search(r"\bBand\s*(?P<band>[1-9])(?:[A-Z])?\b", text or "", re.I)
    if not match:
        return None
    return int(match.group("band"))


def extract_salary_text(text: str) -> str | None:
    match = re.search(
        r"(?P<salary>(?:Hourly Rate\s+)?AUD\s*)?\$[\d,]+(?:\.\d{1,2})?\s*k?"
        r"(?:\s*(?:-|to|\u2013|\u2014)\s*\$?[\d,]+(?:\.\d{1,2})?\s*k?)?"
        r"(?:\s*(?:per|p/?a|pa|annum|hour|year|weekly|week)[^.;<]*)?",
        text or "",
        re.I,
    )
    return normalize_whitespace(match.group(0)) if match else None


def extract_salary_range(text: str) -> dict[str, Any]:
    values: list[float] = []
    for match in re.finditer(
        r"(?P<dollar>\$?)\s*(?P<value>\d{2,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{2,3}\.\d{1,2}|\d{2,3})\s*(?P<k>k)?\b",
        text or "",
        re.I,
    ):
        if not match.group("dollar") and not match.group("k"):
            continue
        value = float(match.group("value").replace(",", ""))
        if match.group("k"):
            value *= 1000
        values.append(round(value, 2))
    if not values:
        return {}
    period = "year"
    lowered = (text or "").lower()
    if re.search(r"\b(hour|hourly|per hour|p/h)\b", lowered):
        period = "hour"
    elif re.search(r"\b(week|weekly|per week)\b", lowered):
        period = "week"
    salary_min = min(values)
    salary_max = max(values)
    if period == "year" and salary_max < 1000:
        period = "hour"
    return {
        "salary_min": round(salary_min, 2),
        "salary_max": round(salary_max, 2),
        "salary_currency": "AUD",
        "salary_period": period,
    }


def normalize_salary_basis(period: Any) -> str | None:
    normalized = _normalize_salary_period(period)
    if normalized == "hour":
        return "hourly"
    if normalized == "year":
        return "annual"
    if normalized == "week":
        return "weekly"
    if normalized == "fortnight":
        return "fortnightly"
    return None


def _normalize_salary_period(period: Any) -> str:
    text = normalize_whitespace(str(period or "")).lower()
    if not text:
        return ""
    if re.search(r"\b(hour|hourly|p/h|per hour)\b", text):
        return "hour"
    if re.search(r"\b(year|annual|annum|pa|p/a|per annum)\b", text):
        return "year"
    if re.search(r"\b(fortnight|fortnightly)\b", text):
        return "fortnight"
    if re.search(r"\b(week|weekly|per week)\b", text):
        return "week"
    return text


def parse_job_datetime(value: Any, *, end_of_day: bool) -> str | None:
    text = normalize_whitespace(str(value or ""))
    if not text:
        return None
    text = re.sub(r"\b(AUS Eastern Standard Time|AEST|AEDT)\b", "", text, flags=re.I).strip()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    text = re.sub(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+", "", text, flags=re.I)
    formats = (
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d %B %Y %I:%M %p",
        "%d %B %Y %H:%M",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y %I:%M %p",
        "%B %d %Y %H:%M",
        "%B %d %Y",
        "%b %d %Y",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if "%H" not in fmt and "%I" not in fmt:
                parsed = datetime.combine(parsed.date(), time(23, 59) if end_of_day else time(0, 0))
            return parsed.replace(tzinfo=VICTORIA_TZ).isoformat()
        except ValueError:
            continue
    return None


def _extract_labeled_date(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})(?:ing)?\b\s*(?:on)?\s*:?\s*(?P<date>\d{{1,2}}(?:/|-)\d{{1,2}}(?:/|-)\d{{4}}|\d{{1,2}}\s+[A-Z][a-z]+\s+\d{{4}}|[A-Z][a-z]+\s+\d{{1,2}}\s+\d{{4}})(?:,?\s*(?P<time>\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)))?",
        text or "",
        re.I,
    )
    if not match:
        return None
    time_text = _normalize_time_text(match.groupdict().get("time"))
    return normalize_whitespace(f"{match.group('date')} {time_text or ''}")


def _extract_application_deadline(text: str) -> str | None:
    match = re.search(
        r"\bApplications?\b.{0,80}?\bby\s+(?:(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*)?"
        r"(?:on\s*)?(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*)?"
        r"(?P<date>\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\d{1,2}(?:/|-)\d{1,2}(?:/|-)\d{4})",
        text or "",
        re.I,
    )
    if not match:
        return None
    time_text = _normalize_time_text(match.groupdict().get("time"))
    return normalize_whitespace(f"{match.group('date')} {time_text or ''}")


def _extract_labeled_reference(text: str) -> str | None:
    match = re.search(
        r"\b(?:reference(?:\s+number)?|job\s*(?:no|number|ref)|ref(?:erence)?)\b\s*:?\s*(?P<ref>[A-Z]{1,8}[-/A-Z0-9]{1,24})\b",
        text or "",
        re.I,
    )
    if not match:
        return None
    return match.group("ref").upper()


def _normalize_time_text(value: str | None) -> str | None:
    text = normalize_whitespace(value or "")
    if not text:
        return None
    match = re.fullmatch(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)", text, re.I)
    if not match:
        return text
    return f"{match.group('hour')}:{match.group('minute') or '00'} {match.group('ampm').upper()}"


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    return parser.text()


def normalize_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _apply_reference_date_fields(
    record: dict[str, Any],
    field_sources: dict[str, Any],
    *,
    posted_at: Any,
    closing_at: Any,
) -> None:
    reference = _canonical_reference_date(record, posted_at=posted_at, closing_at=closing_at)
    if not reference:
        return
    record["canonical_reference_date"] = reference["date"]
    record["canonical_reference_month"] = reference["month"]
    record["canonical_reference_yyyy_mm"] = reference["month"]
    record["canonical_reference_date_source"] = reference["source"]
    field_sources.setdefault("canonical_reference_date", reference["source"])


def _canonical_reference_date(
    record: dict[str, Any],
    *,
    posted_at: Any,
    closing_at: Any,
) -> dict[str, str] | None:
    candidates = (
        ("posted_at", posted_at),
        ("fetched_at", first_present(record.get("fetched_at"), record.get("source_fetched_at"))),
        ("closing_at", closing_at),
        ("canonical_reference_date", record.get("canonical_reference_date")),
    )
    for source, value in candidates:
        parsed = _date_from_any(value)
        if parsed:
            return {
                "date": parsed.isoformat(),
                "month": parsed.isoformat()[:7],
                "source": source,
            }
    return None


def _date_from_any(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize_whitespace(str(value))
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    parsed = parse_job_datetime(text, end_of_day=False)
    if parsed:
        try:
            return datetime.fromisoformat(parsed).date()
        except ValueError:
            return None
    return None


def _normalise_salary_aliases(record: dict[str, Any]) -> None:
    advertised_min = _to_float(first_present(record.get("advertised_salary_min"), record.get("salary_min")))
    advertised_max = _to_float(first_present(record.get("advertised_salary_max"), record.get("salary_max")))
    advertised_period = _normalize_salary_period(first_present(record.get("advertised_salary_period"), record.get("salary_period")))
    if advertised_min is not None:
        advertised_max = advertised_max if advertised_max is not None else advertised_min
        record["salary_min"] = round(advertised_min, 2)
        record["salary_max"] = round(advertised_max, 2)
        record["advertised_salary_min"] = round(advertised_min, 2)
        record["advertised_salary_max"] = round(advertised_max, 2)
        record["salary_currency"] = record.get("salary_currency") or "AUD"
        record["advertised_salary_currency"] = record.get("advertised_salary_currency") or record["salary_currency"]
    if advertised_min is not None and advertised_period:
        record["salary_period"] = advertised_period
        record["advertised_salary_period"] = advertised_period
        basis = normalize_salary_basis(advertised_period)
        if basis:
            record["salary_basis"] = basis
            record["advertised_salary_basis"] = basis
    if record.get("salary_text") and not record.get("advertised_salary_text"):
        record["advertised_salary_text"] = record.get("salary_text")

    enterprise_min = _to_float(first_present(record.get("enterprise_agreement_salary_min"), record.get("canonical_salary_min")))
    enterprise_max = _to_float(first_present(record.get("enterprise_agreement_salary_max"), record.get("canonical_salary_max")))
    enterprise_period = _normalize_salary_period(first_present(record.get("enterprise_agreement_salary_period"), record.get("canonical_salary_period")))
    if enterprise_min is not None:
        enterprise_max = enterprise_max if enterprise_max is not None else enterprise_min
        for prefix in ("enterprise_agreement", "canonical"):
            record[f"{prefix}_salary_min"] = round(enterprise_min, 2)
            record[f"{prefix}_salary_max"] = round(enterprise_max, 2)
            record[f"{prefix}_salary_currency"] = record.get(f"{prefix}_salary_currency") or "AUD"
            record[f"{prefix}_salary_period"] = enterprise_period or "year"
        basis = normalize_salary_basis(enterprise_period or "year")
        if basis:
            record["enterprise_agreement_salary_basis"] = basis
            record["canonical_salary_basis"] = basis
    weekly_min = _to_float(first_present(record.get("enterprise_agreement_weekly_salary_min"), record.get("canonical_weekly_salary_min")))
    weekly_max = _to_float(first_present(record.get("enterprise_agreement_weekly_salary_max"), record.get("canonical_weekly_salary_max")))
    if weekly_min is not None:
        weekly_max = weekly_max if weekly_max is not None else weekly_min
        record["enterprise_agreement_weekly_salary_min"] = round(weekly_min, 2)
        record["enterprise_agreement_weekly_salary_max"] = round(weekly_max, 2)
        record["canonical_weekly_salary_min"] = round(weekly_min, 2)
        record["canonical_weekly_salary_max"] = round(weekly_max, 2)


def _salary_validation(status: str, notes: str) -> dict[str, Any]:
    return {"status": status, "notes": notes}


def _advertised_weekly_range(
    salary_min: float,
    salary_max: float | None,
    salary_period: str,
) -> tuple[float, float] | None:
    upper = salary_max if salary_max is not None else salary_min
    if salary_period in {"year", "annual", "annum"}:
        return salary_min / 52.0, upper / 52.0
    if salary_period in {"week", "weekly"}:
        return salary_min, upper
    if salary_period in {"fortnight", "fortnightly"}:
        return salary_min / 2.0, upper / 2.0
    return None


def _current_band_comparator_rows(
    job: dict[str, Any],
    pay_rows: list[dict[str, Any]],
    band_number: int,
) -> list[dict[str, Any]]:
    rows = _effective_council_pay_rows(job, pay_rows)
    band = str(band_number)
    band_rows = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("standard_band") or row.get("band") or "").lstrip("0") == band
    ]
    if not band_rows:
        all_rows = _effective_council_pay_rows(job, [
            row for row in pay_rows
            if isinstance(row, dict)
            and str(row.get("standard_band") or row.get("band") or "").lstrip("0") == band
        ])
        return all_rows
    if not band_rows:
        return []
    return band_rows


def _effective_council_pay_rows(job: dict[str, Any], pay_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    council_needle = normalize_whitespace(str(job.get("short_name") or job.get("council_name") or "")).lower()
    rows = [
        row for row in pay_rows
        if isinstance(row, dict) and _pay_row_matches_council(row, council_needle)
    ]
    if not rows and council_needle:
        return []
    if not rows:
        rows = [row for row in pay_rows if isinstance(row, dict)]
    if not rows:
        return []
    reference_date = _date_from_any(first_present(
        job.get("canonical_reference_date"),
        job.get("posted_at"),
        job.get("fetched_at"),
        job.get("closing_at"),
    ))
    if reference_date:
        eligible = [
            row for row in rows
            if _pay_row_operates_on(row, reference_date)
        ]
        if not eligible:
            return []
        latest_effective = max(str(row.get("effective_from") or "") for row in eligible)
        return [row for row in eligible if str(row.get("effective_from") or "") == latest_effective]
    latest_effective = max(str(row.get("effective_from") or "") for row in rows)
    return [row for row in rows if str(row.get("effective_from") or "") == latest_effective]


def _pay_row_operates_on(row: dict[str, Any], reference_date: date) -> bool:
    effective_from = _date_from_any(row.get("effective_from"))
    if effective_from is None or effective_from > reference_date:
        return False
    effective_to = _date_from_any(first_present(row.get("to_date"), row.get("effective_to"), row.get("expires_at")))
    return effective_to is None or reference_date <= effective_to


def _enterprise_agreement_salary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_row_weekly_rate(row) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {}
    weekly_min = min(values)
    weekly_max = max(values)
    effective_to_values = [
        row.get("to_date") or row.get("effective_to")
        for row in rows
        if row.get("to_date") or row.get("effective_to")
    ]
    effective_to = min(str(value) for value in effective_to_values) if effective_to_values else None
    return {
        "enterprise_agreement_salary_min": round(weekly_min * 52, 2),
        "enterprise_agreement_salary_max": round(weekly_max * 52, 2),
        "enterprise_agreement_salary_currency": "AUD",
        "enterprise_agreement_salary_period": "year",
        "enterprise_agreement_salary_basis": "annual",
        "enterprise_agreement_weekly_salary_min": round(weekly_min, 2),
        "enterprise_agreement_weekly_salary_max": round(weekly_max, 2),
        "enterprise_agreement_salary_source": "governed_pay_tables",
        "enterprise_agreement_salary_effective_from": rows[0].get("effective_from"),
        "enterprise_agreement_salary_effective_to": effective_to,
        "enterprise_agreement_salary_comparator_rows": len(rows),
        "canonical_salary_min": round(weekly_min * 52, 2),
        "canonical_salary_max": round(weekly_max * 52, 2),
        "canonical_salary_currency": "AUD",
        "canonical_salary_period": "year",
        "canonical_salary_basis": "annual",
        "canonical_weekly_salary_min": round(weekly_min, 2),
        "canonical_weekly_salary_max": round(weekly_max, 2),
        "canonical_salary_source": "governed_pay_tables",
        "canonical_salary_effective_from": rows[0].get("effective_from"),
        "canonical_salary_effective_to": effective_to,
        "canonical_salary_comparator_rows": len(rows),
    }


def _row_weekly_rate(row: dict[str, Any]) -> float | None:
    weekly = _to_float(row.get("weekly_rate"))
    if weekly is not None:
        return weekly
    annual = _to_float(row.get("annual_rate"))
    if annual is not None:
        return annual / 52.0
    fortnightly = _to_float(row.get("fortnightly_rate"))
    if fortnightly is not None:
        return fortnightly / 2.0
    return None


def _pay_row_matches_council(row: dict[str, Any], council_needle: str) -> bool:
    if not council_needle:
        return True
    candidates = [
        row.get("canonical_lga_short_name"),
        row.get("agreement_name"),
        row.get("lga_short_name"),
    ]
    haystack = " ".join(normalize_whitespace(str(value or "")).lower() for value in candidates)
    compact_needle = re.sub(r"\b(city|shire|rural|borough|council|city council|shire council)\b", "", council_needle).strip()
    return council_needle in haystack or (compact_needle and compact_needle in haystack)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = normalize_whitespace(str(value))
    if not text:
        return None
    text = text.replace("$", "").replace(",", "")
    text = re.sub(r"\bAUD\b", "", text, flags=re.I).strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?\s*k?\b", text, re.I)
    if not match:
        return None
    try:
        raw = match.group(0)
        multiplier = 1000 if raw.lower().endswith("k") else 1
        raw = raw.rstrip("kK").strip()
        return round(float(raw) * multiplier, 2)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
