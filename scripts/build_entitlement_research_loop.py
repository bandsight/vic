from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_LOCATOR_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_LOOP_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-loop-intelligence" / "entitlement-loop-intelligence-entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-research-loop"
SCHEMA_VERSION = "wiki.entitlement_research_loop.v1"


OFFICIAL_SOURCES: dict[str, dict[str, Any]] = {
    "fwo_annual_leave": {
        "title": "Annual leave - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/leave/annual-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "Annual leave is a NES entitlement; registered agreements cannot provide less than the NES but can provide more annual leave.",
        "baseline_value": "NES minimum; agreement can provide more",
    },
    "fwo_annual_cash_out": {
        "title": "Cashing out annual leave - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/leave/annual-leave/cashing-out-annual-leave",
        "source_type": "official_rule_condition",
        "fact": "Annual leave cash-out under an enterprise agreement is only available if the agreement allows it and core safeguards are met.",
        "baseline_value": "agreement-enabled rule, at least 4 weeks remaining, written agreement, no coercion",
    },
    "fwo_fdv_leave": {
        "title": "Family and domestic violence leave - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/leave/family-and-domestic-violence-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "Eligible employees get 10 days paid family and domestic violence leave under the NES even if an agreement provides less.",
        "baseline_value": "10 days paid leave each year",
    },
    "fwo_compassionate_leave": {
        "title": "Compassionate and bereavement leave - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/leave/compassionate-and-bereavement-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "The NES provides compassionate leave, also known as bereavement leave; agreements can provide additional entitlements.",
        "baseline_value": "NES compassionate/bereavement leave floor",
    },
    "fwo_personal_carers_leave": {
        "title": "Sick and carer's leave and compassionate leave fact sheet - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/tools-and-resources/fact-sheets/minimum-workplace-entitlements/sick-and-carers-leave-and-compassionate-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "Personal/carer's leave and compassionate leave are NES leave categories.",
        "baseline_value": "NES personal/carer's leave floor",
    },
    "fwo_community_service_leave": {
        "title": "Community service leave fact sheet - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/tools-and-resources/fact-sheets/minimum-workplace-entitlements/community-service-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "Community service leave covers voluntary emergency management activity and jury duty; under the NES it is unpaid except jury duty make-up pay.",
        "baseline_value": "unpaid voluntary emergency management leave; jury duty make-up pay for eligible employees",
    },
    "fwo_parental_payment": {
        "title": "Payment during parental leave - Fair Work Ombudsman",
        "url": "https://www.fairwork.gov.au/leave/parental-leave/during-parental-leave/payment-during-parental-leave",
        "source_type": "official_minimum_entitlement",
        "fact": "Government Parental Leave Pay is separate from employer-funded paid parental leave; employer payments depend on the agreement, contract, or policy.",
        "baseline_value": "government PPL separate from employer-funded agreement entitlement",
    },
    "services_ppl_super": {
        "title": "Paid Parental Leave scheme changes - Services Australia",
        "url": "https://www.servicesaustralia.gov.au/paid-parental-leave-scheme-changes?context=64479",
        "source_type": "official_payment_rule",
        "fact": "Parental Leave Pay for a child born or adopted from 1 July 2025 attracts a 12% superannuation contribution paid by the ATO.",
        "baseline_value": "12% superannuation contribution on government Parental Leave Pay",
    },
    "lgia_award": {
        "title": "Local Government Industry Award 2020 [MA000112] - Fair Work Ombudsman",
        "url": "https://awards.fairwork.gov.au/MA000112.html",
        "source_type": "official_award_anchor",
        "fact": "The Local Government Industry Award provides award anchors for call-back, on-call, first aid, annual leave loading, and certain allowances.",
        "baseline_value": "3-hour call-back minimum; on-call and first-aid award allowance anchors",
    },
}


SOURCE_MAP: dict[str, list[str]] = {
    "leave-additional-annual-leave": ["fwo_annual_leave", "lgia_award"],
    "leave-family-and-domestic-violence-leave": ["fwo_fdv_leave"],
    "leave-natural-disaster-or-emergency-leave": ["fwo_community_service_leave"],
    "leave-compassionate-leave": ["fwo_compassionate_leave"],
    "leave-emergency-services-leave": ["fwo_community_service_leave"],
    "leave-parental-leave-primary-carer": ["fwo_parental_payment"],
    "leave-parental-leave-non-primary": ["fwo_parental_payment"],
    "leave-personal-and-carers-leave": ["fwo_personal_carers_leave"],
    "leave-volunteer-or-donor-leave": ["fwo_community_service_leave"],
    "conditions-call-out-minimum-engagement": ["lgia_award"],
    "financial-and-monetary-provisions-on-call-allowance": ["lgia_award"],
    "financial-and-monetary-provisions-first-aid-allowance": ["lgia_award"],
    "financial-and-monetary-provisions-plant-and-industry-allowances-values-and-parameters": ["lgia_award"],
    "financial-and-monetary-provisions-annual-leave-cash-out-rules": ["fwo_annual_cash_out"],
    "conditions-christmas-to-new-year-closure": ["fwo_annual_leave"],
    "leave-paid-shutdown-days-christmas-to-new-year": ["fwo_annual_leave"],
    "parental-and-family-related-enhancements-extended-caring-cohorts": ["fwo_parental_payment"],
    "parental-and-family-related-enhancements-fertility-treatment-leave": ["fwo_parental_payment"],
    "parental-and-family-related-enhancements-prenatal-leave": ["fwo_parental_payment"],
    "parental-and-family-related-enhancements-stillbirth-and-neonatal-loss-provisions": ["fwo_parental_payment", "fwo_compassionate_leave"],
    "parental-and-family-related-enhancements-surrogacy-and-intended-parent-support-leave": ["fwo_parental_payment"],
    "superannuation-superannuation-above-legislated-minimum": ["services_ppl_super"],
    "superannuation-superannuation-on-paid-parental-leave": ["fwo_parental_payment", "services_ppl_super"],
    "superannuation-superannuation-on-unpaid-parental-leave-fixed-super": ["fwo_parental_payment", "services_ppl_super"],
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact_unique(values: list[Any], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = clean_text(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def profile_by_id(locator_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        clean_text(profile.get("entitlement_id")): profile
        for profile in wiki_as_list(locator_payload.get("profiles"))
        if isinstance(profile, dict) and clean_text(profile.get("entitlement_id"))
    }


def loop_rows(loop_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in wiki_as_list(loop_payload.get("rows")) if isinstance(row, dict)]


def source_ids_for_entitlement(entitlement_id: str) -> list[str]:
    direct = SOURCE_MAP.get(entitlement_id)
    if direct:
        return direct
    if entitlement_id.startswith("superannuation-"):
        return ["services_ppl_super"]
    if "annual-leave" in entitlement_id:
        return ["fwo_annual_leave"]
    if "parental" in entitlement_id or "prenatal" in entitlement_id:
        return ["fwo_parental_payment"]
    if "emergency" in entitlement_id or "volunteer" in entitlement_id:
        return ["fwo_community_service_leave"]
    if "allowance" in entitlement_id or "call-out" in entitlement_id or "on-call" in entitlement_id:
        return ["lgia_award"]
    return []


def official_sources(entitlement_id: str) -> list[dict[str, Any]]:
    return [OFFICIAL_SOURCES[source_id] | {"source_id": source_id} for source_id in source_ids_for_entitlement(entitlement_id)]


def observed_values_from_profile(profile: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in wiki_as_list(profile.get("target_rows")):
        if not isinstance(row, dict):
            continue
        for value in wiki_as_list(row.get("normalised_values")):
            if not isinstance(value, dict):
                continue
            label = " ".join(part for part in [clean_text(value.get("value")), clean_text(value.get("unit"))] if part)
            if not label:
                label = clean_text(value.get("condition") or value.get("subclass_label") or "value_not_labelled")
            counts[label] += 1
    return dict(counts.most_common(10))


def validation_samples(loop_row: dict[str, Any]) -> list[dict[str, Any]]:
    samples = []
    for item in wiki_as_list(loop_row.get("validation_queue"))[:6]:
        if not isinstance(item, dict):
            continue
        samples.append({
            "council": item.get("council"),
            "agreement_id": item.get("agreement_id"),
            "reasons": wiki_as_list(item.get("reasons")),
            "value_labels": wiki_as_list(item.get("value_labels")),
            "evidence": item.get("evidence"),
            "review_question": item.get("review_question"),
        })
    return samples


def research_status(sources: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    green = sum(
        1
        for row in wiki_as_list(profile.get("target_rows"))
        if isinstance(row, dict) and row.get("value_extracted") and wiki_as_list(row.get("feature_cards"))
    )
    if any(source.get("source_type") == "official_minimum_entitlement" for source in sources):
        return "official_minimum_floor_attached"
    if any(source.get("source_type") == "official_award_anchor" for source in sources):
        return "official_award_anchor_attached"
    if any(source.get("source_type") == "official_payment_rule" for source in sources):
        return "official_payment_rule_attached"
    if green:
        return "enterprise_agreement_pattern_only"
    return "research_gap_no_feature_evidence"


def definition_candidate(loop_row: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    question = clean_text(loop_row.get("entitlement_question"))
    if not sources:
        return question
    source_terms = "; ".join(clean_text(source.get("baseline_value")) for source in sources[:2] if source.get("baseline_value"))
    return f"{question} External anchor: {source_terms}."


def value_model(loop_row: dict[str, Any], sources: list[dict[str, Any]], observed_values: dict[str, int]) -> dict[str, Any]:
    entitlement_id = clean_text(loop_row.get("entitlement_id"))
    answer_shape = loop_row.get("answer_shape") if isinstance(loop_row.get("answer_shape"), dict) else {}
    top_observed = clean_text(answer_shape.get("top_observed_value")) or next(iter(observed_values.keys()), "")
    official_baselines = [clean_text(source.get("baseline_value")) for source in sources if source.get("baseline_value")]
    official_expected = official_expected_value(entitlement_id, sources)
    conflict = official_value_conflict(entitlement_id, top_observed, official_expected)
    if conflict:
        interpretation = (
            "Official research conflicts with the observed value shape; do not promote the observed normal value until "
            "source context proves it belongs to this entitlement."
        )
    elif official_baselines and top_observed:
        interpretation = "Compare agreement value against external floor or award anchor; preserve source value when agreement is more generous or more specific."
    elif official_baselines:
        interpretation = "Use external floor or award anchor as context; mark agreement amount not stated unless source clause adds a value."
    elif top_observed:
        interpretation = "No official floor attached; use cross-council feature-card pattern as provisional normal value pending human validation."
    else:
        interpretation = "No value model yet; require source PDF review and external research before promotion."
    return {
        "top_observed_value": top_observed,
        "observed_values": observed_values,
        "official_baselines": official_baselines,
        "official_expected_value": official_expected,
        "value_conflict_with_official_anchor": conflict,
        "interpretation": interpretation,
    }


def official_expected_value(entitlement_id: str, sources: list[dict[str, Any]]) -> str:
    source_ids = {source.get("source_id") for source in sources}
    if entitlement_id == "leave-family-and-domestic-violence-leave":
        return "10 days paid leave NES floor; agreements can provide a higher local entitlement."
    if entitlement_id == "conditions-call-out-minimum-engagement":
        return "3 hours call-back minimum under the Local Government Industry Award call-back anchor."
    if entitlement_id == "financial-and-monetary-provisions-first-aid-allowance":
        return "First aid allowance payable when qualified and appointed; award rate is a weekly allowance anchor."
    if entitlement_id == "financial-and-monetary-provisions-on-call-allowance":
        return "On-call allowance is a daily award allowance anchor, with different weekday/Saturday/Sunday-public holiday rates."
    if "superannuation" in entitlement_id and "services_ppl_super" in source_ids:
        return "12% superannuation contribution on government Parental Leave Pay; employer-funded agreement super must be explicit."
    if "community_service" in source_ids or "fwo_community_service_leave" in source_ids:
        return "NES community service leave is unpaid except jury duty make-up pay."
    return ""


def official_value_conflict(entitlement_id: str, top_observed: str, official_expected: str) -> bool:
    observed = top_observed.lower()
    expected = official_expected.lower()
    if not top_observed or not official_expected:
        return False
    if "superannuation" in entitlement_id:
        return not any(term in observed for term in ["super", "12", "%", "percent", "contribution"])
    if entitlement_id == "conditions-call-out-minimum-engagement":
        return not ("3" in observed and "hour" in observed)
    if "community service" in expected and "paid" in observed and "jury" not in observed:
        return True
    return False


def research_risks(loop_row: dict[str, Any], sources: list[dict[str, Any]], value_model_row: dict[str, Any]) -> list[str]:
    risks = []
    status = clean_text(loop_row.get("loop_status"))
    if value_model_row.get("value_conflict_with_official_anchor"):
        risks.append("Observed normal value conflicts with the official research anchor.")
    if status in {"split_or_normalise_values", "repair_value_extraction"}:
        risks.append("Observed feature-card values need subclass or amount-not-stated handling before promotion.")
    if not sources:
        risks.append("No external official anchor attached; treat as enterprise-agreement-only entitlement until human/legal research confirms a standard definition.")
    if value_model_row.get("official_baselines") and value_model_row.get("top_observed_value"):
        risks.append("Agreement value may be above, below, or different from the external floor; compare rather than overwrite.")
    return risks[:5]


def feedback_actions(loop_row: dict[str, Any], sources: list[dict[str, Any]], value_model_row: dict[str, Any]) -> dict[str, Any]:
    source_titles = [source["title"] for source in sources]
    loop_value_rules = wiki_as_list((loop_row.get("rule_change_candidates") or {}).get("value_rules") if isinstance(loop_row.get("rule_change_candidates"), dict) else [])
    if value_model_row.get("value_conflict_with_official_anchor"):
        loop_value_rules = []
    value_rules = [
        value_model_row["interpretation"],
        *([f"Official expected value: {value_model_row['official_expected_value']}"] if value_model_row.get("official_expected_value") else []),
        *loop_value_rules,
    ]
    review_if = [
        "Feature-card value conflicts with official floor, award anchor, or research baseline.",
        "Source clause only cross-references an external entitlement and does not add a local value.",
        *research_risks(loop_row, sources, value_model_row),
    ]
    return {
        "append_value_rules": compact_unique(value_rules, limit=6),
        "append_review_if": compact_unique(review_if, limit=6),
        "research_source_titles": source_titles,
    }


def research_row(loop_row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    entitlement_id = clean_text(loop_row.get("entitlement_id"))
    sources = official_sources(entitlement_id)
    observed_values = observed_values_from_profile(profile)
    model = value_model(loop_row, sources, observed_values)
    return {
        "entitlement_id": entitlement_id,
        "label": loop_row.get("label"),
        "research_status": research_status(sources, profile),
        "loop_status": loop_row.get("loop_status"),
        "promotion_gate": loop_row.get("promotion_gate"),
        "definition_candidate": definition_candidate(loop_row, sources),
        "official_sources": sources,
        "source_pdf_samples": validation_samples(loop_row),
        "cross_council_value_model": model,
        "research_risks": research_risks(loop_row, sources, model),
        "feedback_actions": feedback_actions(loop_row, sources, model),
    }


def build_payload(locator_payload: dict[str, Any], loop_payload: dict[str, Any], *, generated_at: str, source_path: Path) -> dict[str, Any]:
    profiles = profile_by_id(locator_payload)
    rows = [
        research_row(row, profiles.get(clean_text(row.get("entitlement_id")), {}))
        for row in loop_rows(loop_payload)
    ]
    status_counts = Counter(row["research_status"] for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "artifact_id": f"entitlement-research-loop-{locator_payload.get('artifact_id', 'unknown')}",
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "loop_artifact_id": loop_payload.get("artifact_id"),
            "path": str(source_path),
        },
        "method": {
            "name": "official_source_and_feature_card_research_loop",
            "scope": "Combines official Fair Work/Services/Award anchors, cross-council feature-card value patterns, and source-PDF validation queues.",
            "external_research_status": "official_anchor_pass_completed",
        },
        "official_source_registry": OFFICIAL_SOURCES,
        "summary": {
            "entitlements": len(rows),
            "research_statuses": dict(sorted(status_counts.items())),
            "official_source_links": sum(len(row["official_sources"]) for row in rows),
            "source_pdf_samples": sum(len(row["source_pdf_samples"]) for row in rows),
            "feedback_rows": sum(1 for row in rows if row["feedback_actions"]["append_value_rules"]),
        },
        "rows": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Research Loop",
        "",
        payload["method"]["scope"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Entitlements", ""])
    for row in payload["rows"]:
        sources = ", ".join(source["title"] for source in row["official_sources"]) or "No official anchor attached"
        lines.extend([
            f"### {row['label']}",
            "",
            f"- Status: `{row['research_status']}`",
            f"- Sources: {sources}",
            f"- Definition: {row['definition_candidate']}",
            f"- Value model: {row['cross_council_value_model']['interpretation']}",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build official/source-PDF research loop over entitlement loop intelligence.")
    parser.add_argument("--locator-input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--loop-input", type=Path, default=DEFAULT_LOOP_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    locator_path = args.locator_input.resolve()
    loop_path = args.loop_input.resolve()
    payload = build_payload(load_json(locator_path), load_json(loop_path), generated_at=utc_now_iso(), source_path=loop_path)
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_research_loop_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
