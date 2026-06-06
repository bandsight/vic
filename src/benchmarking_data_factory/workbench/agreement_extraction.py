from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from fastapi import HTTPException


@dataclass(frozen=True)
class AgreementExtractionDependencies:
    pay_keywords: Any
    uplift_keywords: Any
    alteration_keywords: Any
    overview_system: str
    get_page_count: Callable[[str], int]
    find_candidate_pages: Callable[[str, Any], list[int]]
    extract_page_text: Callable[[str, int], str]
    extract_all_page_texts: Callable[[str], list[str]]
    call_llm: Callable[..., str]
    is_llm_error: Callable[[str], bool]
    llm_http_failure: Callable[..., HTTPException]
    parse_overview_response: Callable[[str, int, list[int], list[int], list[int]], dict[str, Any]]
    now_iso: Callable[[], str]
    get_canonical: Callable[[str], dict[str, Any]]
    apply_section_status: Callable[..., Any]
    save_canonical: Callable[[str, dict[str, Any]], None]
    resolve_fwc: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any] | None]
    split_ae_id: Callable[[str], tuple[str, str | None]]
    find_pdf: Callable[[str], Any]
    load_registry: Callable[[], dict[str, str]]
    resolve_canonical_lga_short_name: Callable[..., str | None]
    score_condition_pages: Callable[..., list[Any]]
    empty_conditions_data: Callable[[], dict[str, Any]]
    validate_conditions_payload: Callable[[dict[str, Any]], list[Any]]
    build_conditions_extraction_prompt: Callable[[str, str], str]
    strip_json_preamble: Callable[[str], str]


def generate_overview(ae_id: str, deps: AgreementExtractionDependencies) -> dict[str, Any]:
    page_count = deps.get_page_count(ae_id)
    pay_pages = deps.find_candidate_pages(ae_id, deps.pay_keywords)[:10]
    uplift_pages = deps.find_candidate_pages(ae_id, deps.uplift_keywords)[:10]
    alteration_pages = deps.find_candidate_pages(ae_id, deps.alteration_keywords)[:10]
    seed_pages = {1, 2, 3, page_count // 2 if page_count else 1, page_count - 2, page_count - 1, page_count}
    seed_pages = {page for page in seed_pages if 1 <= page <= page_count}
    pages_to_sample = sorted(seed_pages | set(pay_pages) | set(uplift_pages) | set(alteration_pages))
    blocks: list[str] = []
    for page_num in pages_to_sample:
        text = deps.extract_page_text(ae_id, page_num)[:1500]
        blocks.append(f"[Page {page_num}]\n{text}")
    raw = deps.call_llm(deps.overview_system, [{"type": "text", "text": "\n\n".join(blocks)}], max_tokens=2500)
    if deps.is_llm_error(raw):
        raise deps.llm_http_failure(
            raw,
            action="generate_overview",
            message="Overview generation failed; no overview evidence was saved.",
        )
    overview = deps.parse_overview_response(raw, page_count, pay_pages, uplift_pages, alteration_pages)
    overview["generated_at"] = deps.now_iso()
    canonical = deps.get_canonical(ae_id)
    canonical["overview"] = overview
    overview_section = canonical.setdefault("sections", {}).setdefault("overview", {})
    deps.apply_section_status(overview_section, "done", overview["generated_at"])
    overview_section["source_ref"] = "Generated overview"
    overview_section["data"] = {
        "page_count": overview.get("page_count"),
        "likely_pay_table_pages": overview.get("likely_pay_table_pages") or [],
        "likely_uplift_pages": overview.get("likely_uplift_pages") or [],
    }
    deps.save_canonical(ae_id, canonical)
    canonical["fwc"] = deps.resolve_fwc(canonical, deps.fetch_metadata_for_ae_id(ae_id))
    return canonical


def conditions_candidate_page_blocks(
    ae_id: str,
    *,
    max_pages: int = 28,
    deps: AgreementExtractionDependencies,
) -> tuple[list[dict[str, Any]], list[int]]:
    pages = deps.extract_all_page_texts(ae_id)
    candidates = deps.score_condition_pages(pages, max_pages_per_category=4)
    ordered: list[int] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.page_number)):
        if candidate.page_number not in ordered:
            ordered.append(candidate.page_number)
        if len(ordered) >= max_pages:
            break
    blocks = [
        {"page": page_num, "text": (pages[page_num - 1] if 0 <= page_num - 1 < len(pages) else "")[:3200]}
        for page_num in sorted(ordered)
    ]
    return blocks, sorted(ordered)


def normalise_conditions_extraction_payload(
    parsed: Any,
    *,
    ae_id: str,
    council_name: str,
    candidate_pages: list[int],
    deps: AgreementExtractionDependencies,
) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Conditions extractor returned a non-object payload")
    empty_data = deps.empty_conditions_data()
    data = deps.empty_conditions_data()
    data.update({
        key: value
        for key, value in parsed.items()
        if key not in {"category_definitions", "categories", "big_ticket_categories", "excluded_specialised_cohorts"}
    })
    data["schema_version"] = data.get("schema_version") or empty_data["schema_version"]
    data["target_scope"] = empty_data["target_scope"]
    data["items"] = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    data["covered_councils"] = (
        parsed.get("covered_councils")
        if isinstance(parsed.get("covered_councils"), list) and parsed.get("covered_councils")
        else ([council_name] if council_name else [])
    )
    data["multi_employer"] = bool(parsed.get("multi_employer"))
    data["candidate_pages"] = candidate_pages
    data["extracted_at"] = deps.now_iso()
    data["extraction_notes"] = parsed.get("extraction_notes") or parsed.get("notes") or ""
    data["agreement_id"] = ae_id
    return data


def extract_entitlements(ae_id: str, deps: AgreementExtractionDependencies) -> dict[str, Any]:
    parent_ae_id, _ = deps.split_ae_id(ae_id)
    if deps.find_pdf(ae_id) is None and ae_id.lower() not in deps.load_registry() and parent_ae_id not in deps.load_registry():
        raise HTTPException(status_code=404, detail="Council not found")
    canonical = deps.get_canonical(ae_id)
    fetch_metadata = deps.fetch_metadata_for_ae_id(ae_id)
    council_name = deps.resolve_canonical_lga_short_name(ae_id, fetch_metadata) or canonical.get("source_name") or ae_id
    page_blocks, candidate_pages = conditions_candidate_page_blocks(ae_id, deps=deps)
    if not page_blocks:
        raise HTTPException(status_code=422, detail="No entitlement candidate pages found")

    prompt = deps.build_conditions_extraction_prompt(ae_id, str(council_name))
    evidence = "\n\n".join(
        f"[Page {block['page']}]\n{block['text']}"
        for block in page_blocks
    )
    raw = deps.call_llm(
        prompt,
        [{"type": "text", "text": f"Candidate entitlement pages:\n\n{evidence}\n\nReturn JSON only."}],
        max_tokens=20000,
    )
    if deps.is_llm_error(raw):
        raise deps.llm_http_failure(raw, action="extract_entitlements", message="Entitlement extraction failed; no records were saved.")
    try:
        parsed = json.loads(deps.strip_json_preamble(raw))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Conditions extractor returned invalid JSON: {exc}") from exc

    data = normalise_conditions_extraction_payload(
        parsed,
        ae_id=ae_id,
        council_name=str(council_name),
        candidate_pages=candidate_pages,
        deps=deps,
    )
    validation_errors = deps.validate_conditions_payload(data)
    if validation_errors:
        raise HTTPException(status_code=422, detail={"validation_errors": validation_errors, "candidate_pages": candidate_pages})

    section = canonical.setdefault("sections", {}).setdefault("clauses", {})
    section["data"] = data
    section["source_ref"] = f"Entitlement extraction pages {', '.join(map(str, candidate_pages[:12]))}"
    section["notes"] = data.get("extraction_notes") or section.get("notes", "")
    if section.get("status") in (None, "not_started"):
        deps.apply_section_status(section, "in_progress", None)
    deps.save_canonical(ae_id, canonical)
    return {
        "data": data,
        "items": data.get("items", []),
        "candidate_pages": candidate_pages,
        "section_status": section.get("status"),
        "validation_errors": [],
    }
