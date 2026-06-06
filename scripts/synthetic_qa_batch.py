"""Run automated reviewer QA over active council agreements via the local API.

The runner is intentionally resilient: each agreement gets a result, blockers
are logged with options considered, and the batch moves on.
"""
from __future__ import annotations

import argparse
import json
import http.client
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "var" / "synthetic-qa-runs"
INTAKE_DECISIONS = ROOT / "registers" / "intake-decisions.json"
BASE_URL = "http://127.0.0.1:8765"
MAX_RULE_DATE_SNAP_DAYS = 92


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api(path: str, *, method: str = "GET", body: dict[str, Any] | None = None, timeout: int = 240) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        data = None
        headers = {"Content-Type": "application/json", "Connection": "close"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                ctype = resp.headers.get("content-type", "")
                if "application/json" in ctype:
                    return json.loads(raw or "{}")
                return raw
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(detail or f"HTTP {exc.code} {path}") from exc
        except (ConnectionResetError, TimeoutError, socket.timeout, http.client.IncompleteRead, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"API connection failed after retries for {path}: {exc}") from exc
    raise RuntimeError(f"API connection failed for {path}: {last_error}")


def intake_decision_statuses() -> dict[str, str]:
    if not INTAKE_DECISIONS.exists():
        return {}
    try:
        payload = json.loads(INTAKE_DECISIONS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    decisions = payload.get("decisions") if isinstance(payload, dict) else []
    return {
        str(item.get("ae_id") or "").lower(): str(item.get("status") or "").lower()
        for item in decisions or []
        if isinstance(item, dict) and item.get("ae_id")
    }


def page_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(part) for part in re.findall(r"\d+", value)]
    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            out.extend(page_list(item))
        return sorted(set(out))
    return []


def ordered_pages(*values: Any) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        for page in page_list(value):
            if page not in seen:
                seen.add(page)
                out.append(page)
    return out


def pay_table_page_count(overview: dict[str, Any] | None, record: dict[str, Any] | None) -> int | None:
    for source in (overview or {}, record or {}):
        for key in ("page_count", "pdf_pages", "pages", "total_pages"):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, int) and value > 0:
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def clamp_page(page: int, page_count: int | None = None) -> int | None:
    if page < 1:
        return None
    if page_count and page > page_count:
        return None
    return page


def pay_anchor_window(page: int, page_count: int | None = None) -> list[int]:
    """Image pay appendices are often discovered by a late page inside a run."""
    start = max(1, page - 12)
    end = page + 4
    if page_count:
        end = min(page_count, end)
    return [candidate for candidate in range(start, end + 1) if clamp_page(candidate, page_count)]


def pay_extraction_groups(
    overview_pages: list[int],
    ranked_pay_pages: list[int],
    candidate_pages: list[int],
    page_count: int | None = None,
) -> tuple[list[list[int]], list[list[int]]]:
    primary: list[list[int]] = []
    fallback: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()

    def add(group: list[int], target: list[list[int]]) -> None:
        clean = [page for page in ordered_pages(group) if clamp_page(page, page_count)]
        if not clean:
            return
        for contiguous in contiguous_groups(clean):
            key = tuple(contiguous)
            if key not in seen:
                seen.add(key)
                target.append(contiguous)

    for page in overview_pages:
        add(pay_anchor_window(page, page_count), primary)
    for group in contiguous_groups(ranked_pay_pages[:18]):
        add(group, primary)
    for page in candidate_pages[:30]:
        add([page], fallback)
    for page in ordered_pages(ranked_pay_pages[18:40], candidate_pages[30:60]):
        add(pay_anchor_window(page, page_count), fallback)
    return primary, fallback


def is_iso(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.strip())
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()))
    except ValueError:
        return False


def nearest_rule_date_iso(source_iso: str, rule_dates: list[str], *, max_days: int = MAX_RULE_DATE_SNAP_DAYS) -> tuple[str | None, str | None]:
    source_date = datetime.fromisoformat(source_iso).date()
    parsed = [datetime.fromisoformat(rule_date).date() for rule_date in rule_dates if is_iso(rule_date)]
    candidates = sorted(
        ((abs((rule_date - source_date).days), rule_date) for rule_date in parsed),
        key=lambda item: (item[0], item[1].isoformat()),
    )
    if not candidates:
        return None, None
    best_delta, best_date = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best_delta:
        return None, (
            f"source date {source_iso} is equidistant to uplift rule dates "
            f"{best_date.isoformat()} and {candidates[1][1].isoformat()}"
        )
    if best_delta > max_days:
        return None, f"nearest uplift rule date is {best_delta} days away, beyond the {max_days}-day snap guard"
    return best_date.isoformat(), None


def year_header_rule_dates(source_dates: list[str | None], rule_dates: list[str]) -> dict[int, str]:
    source_years: set[int] = set()
    for source_iso in source_dates:
        if not source_iso:
            continue
        source_date = date.fromisoformat(source_iso)
        if source_date.month == 1 and source_date.day == 1:
            source_years.add(source_date.year)
    rules_by_year: dict[int, list[str]] = defaultdict(list)
    for rule_date in rule_dates:
        if is_iso(rule_date):
            rules_by_year[date.fromisoformat(rule_date).year].append(rule_date)
    overlap = source_years & set(rules_by_year)
    if len(source_years) < 2 or len(overlap) < 2:
        return {}
    return {
        year: dates[0]
        for year, dates in rules_by_year.items()
        if year in overlap and len(dates) == 1
    }


def prepare_rule_anchored_dates(tables: list[dict[str, Any]], rule_dates: list[str]) -> list[str]:
    """Mirror backend rule_anchored date snapping before cohort QA groups tables."""
    decisions: list[str] = []
    clean_rule_dates = sorted({rule_date for rule_date in rule_dates if is_iso(rule_date)})
    if not clean_rule_dates:
        return decisions
    source_dates: list[tuple[int, dict[str, Any], str | None]] = []
    for index, table in enumerate(tables):
        source_iso = (
            str(table.get("source_date_iso") or "").strip()
            or str(table.get("source_date_raw") or "").strip()
            or str(table.get("effective_from") or "").strip()
        )
        source_iso = source_iso if is_iso(source_iso) else None
        source_dates.append((index, table, source_iso))
        if source_iso:
            table["source_date_iso"] = source_iso
            table.setdefault("source_date_raw", table.get("effective_from"))
    year_rules = year_header_rule_dates([source_iso for _, _, source_iso in source_dates], clean_rule_dates)
    for index, _, source_iso in source_dates:
        if not source_iso:
            continue
        source_date = date.fromisoformat(source_iso)
        if (
            year_rules
            and source_date.month == 1
            and source_date.day == 1
            and source_date.year in year_rules
        ):
            continue
        _, tie_issue = nearest_rule_date_iso(source_iso, clean_rule_dates)
        if tie_issue and "equidistant" in tie_issue:
            decisions.append(f"Skipped rule-anchored pre-save snapping because table {index} has a date tie: {tie_issue}.")
            return decisions
    for index, table, source_iso in source_dates:
        if not source_iso:
            continue
        source_date = date.fromisoformat(source_iso)
        same_year_rule = (
            year_rules.get(source_date.year)
            if source_date.month == 1 and source_date.day == 1
            else None
        )
        nearest_iso = same_year_rule
        snap_issue = None
        if nearest_iso is None:
            nearest_iso, snap_issue = nearest_rule_date_iso(source_iso, clean_rule_dates)
        if not nearest_iso:
            if snap_issue:
                decisions.append(f"Kept {table_label(table, index)} at source date {source_iso}: {snap_issue}.")
            continue
        if table.get("effective_from") != nearest_iso:
            if same_year_rule:
                decisions.append(f"Aligned year-labelled {table_label(table, index)} from source date {source_iso} to same-year uplift rule date {nearest_iso} before cohort QA.")
            else:
                decisions.append(f"Aligned {table_label(table, index)} from source date {source_iso} to uplift rule date {nearest_iso} before cohort QA.")
        table["canonical_date_iso"] = nearest_iso
        table["date_snapped"] = nearest_iso != source_iso
        table["snap_basis"] = "uplift_rule_year_header" if same_year_rule and nearest_iso != source_iso else "uplift_rule_event" if nearest_iso != source_iso else None
        table["snap_note"] = (
            f"Snapped year-labelled table {source_iso} to same-year uplift rule date {nearest_iso}"
            if same_year_rule and nearest_iso != source_iso
            else f"Snapped {source_iso} to uplift rule date {nearest_iso}"
            if nearest_iso != source_iso
            else "Already aligned to uplift rule date"
        )
        table["effective_from"] = nearest_iso
    return decisions


def contiguous_groups(pages: list[int]) -> list[list[int]]:
    pages = sorted(set(int(p) for p in pages if p))
    if not pages:
        return []
    groups = [[pages[0]]]
    for page in pages[1:]:
        if page == groups[-1][-1] + 1:
            groups[-1].append(page)
        else:
            groups.append([page])
    return groups


def table_text(table: dict[str, Any]) -> str:
    parts = [
        table.get("table_title"),
        table.get("source_clause"),
        table.get("effective_from_note"),
        table.get("period_label_source"),
        table.get("rate_kind"),
    ]
    for row in table.get("rows") or []:
        if isinstance(row, dict):
            parts.extend([row.get("title"), row.get("classification"), row.get("notes")])
    return " ".join(str(part or "") for part in parts).lower()


def cell_key(row: dict[str, Any]) -> str:
    band = str(row.get("band") or "").strip()
    level = str(row.get("level") or "").strip().upper()
    if not band or not level:
        return ""
    return f"{band}::{level}"


def table_cells(table: dict[str, Any]) -> set[str]:
    cells: set[str] = set()
    for row in table.get("rows") or []:
        if isinstance(row, dict):
            key = cell_key(row)
            if key:
                cells.add(key)
    return cells


def comparable_rate(row: dict[str, Any]) -> float | None:
    for key in ("weekly_rate", "annual_rate", "fortnightly_rate", "hourly_rate", "rate"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                return None
    return None


def same_rates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    b_rates: dict[str, float | None] = {}
    for row in b.get("rows") or []:
        if isinstance(row, dict):
            key = cell_key(row)
            if key:
                b_rates[key] = comparable_rate(row)
    compared = 0
    for row in a.get("rows") or []:
        if not isinstance(row, dict):
            continue
        key = cell_key(row)
        if not key or key not in b_rates:
            continue
        compared += 1
        if comparable_rate(row) != b_rates[key]:
            return False
    return compared > 0 and compared == min(len(table_cells(a)), len(table_cells(b)))


def normalised_title(table: dict[str, Any]) -> str:
    title = str(table.get("table_title") or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def overlap_rate_match(a: dict[str, Any], b: dict[str, Any]) -> tuple[int, int]:
    b_rates: dict[str, float | None] = {}
    for row in b.get("rows") or []:
        if isinstance(row, dict):
            key = cell_key(row)
            if key:
                b_rates[key] = comparable_rate(row)
    compared = 0
    matched = 0
    for row in a.get("rows") or []:
        if not isinstance(row, dict):
            continue
        key = cell_key(row)
        if not key or key not in b_rates:
            continue
        a_rate = comparable_rate(row)
        b_rate = b_rates[key]
        if a_rate is None or b_rate is None:
            continue
        compared += 1
        if a_rate == b_rate:
            matched += 1
    return compared, matched


def same_title_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_title = normalised_title(a)
    b_title = normalised_title(b)
    return bool(a_title and a_title == b_title)


def distinct_cohort_title_pair(a: dict[str, Any], b: dict[str, Any]) -> bool:
    titles = f"{normalised_title(a)} || {normalised_title(b)}"
    marker_pairs = [
        (r"\bschedule\s*1\b", r"\bschedule\s*2\b"),
        (r"\byear\s*1\b", r"\byear\s*2\b"),
    ]
    if any(re.search(left, titles) and re.search(right, titles) for left, right in marker_pairs):
        return True
    return bool(re.search(r"\bmchn\b|\bmaternal\b|\bcommunity transport\b|\bphysical and community\b", titles))


def lga_name_parts(lga: str | None) -> list[str]:
    raw = str(lga or "").lower()
    return [
        part for part in re.split(r"[^a-z0-9]+", raw)
        if len(part) >= 3 and part not in {"city", "shire", "rural", "council", "borough"}
    ]


def split_like_row(ae_id: str, row: dict[str, Any], canonical: dict[str, Any] | None = None) -> bool:
    if row.get("is_split_row") or "__" in str(ae_id):
        return True
    if len(multi_council_names(row, canonical)) >= 2:
        return True
    lga = str(row.get("canonical_lga_short_name") or "").lower()
    source = " ".join(str(part or "") for part in [
        row.get("source_name"),
        (canonical or {}).get("source_name") if isinstance(canonical, dict) else "",
        ((canonical or {}).get("overview") or {}).get("document_structure_notes") if isinstance((canonical or {}).get("overview"), dict) else "",
    ]).lower()
    return bool(
        lga
        and lga in source
        and re.search(
            r"\bsingle\s+interest\b|\bmulti[-\s]?council\b|\bmultiple\s+councils\b|\bseparate\s+(?:council|employer)\s+pay\s+tables\b",
            source,
        )
    )


def multi_council_names(row: dict[str, Any], canonical: dict[str, Any] | None = None) -> list[str]:
    overview = (canonical or {}).get("overview") if isinstance(canonical, dict) else {}
    text = " ".join(str(part or "") for part in [
        row.get("source_name"),
        (canonical or {}).get("source_name") if isinstance(canonical, dict) else "",
        (canonical or {}).get("title") if isinstance(canonical, dict) else "",
        (overview or {}).get("document_structure_notes") if isinstance(overview, dict) else "",
    ])
    names = [
        match.group(1).strip()
        for match in re.finditer(
            r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3})\s+(?:Rural\s+City\s+Council|City\s+Council|Shire\s+Council|Borough\s+Council)\b",
            text,
        )
    ]
    return list(dict.fromkeys(names))


def filter_split_pay_tables(
    tables: list[dict[str, Any]],
    row: dict[str, Any],
    canonical: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    lga = row.get("canonical_lga_short_name")
    active_parts = lga_name_parts(lga)
    if not active_parts:
        return tables, []
    names = multi_council_names(row, canonical)
    foreign_parts = [
        part
        for name in names
        if not any(active in lga_name_parts(name) for active in active_parts)
        for part in lga_name_parts(name)
    ]
    if not foreign_parts:
        return tables, []
    current: list[dict[str, Any]] = []
    unmarked: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for table in tables:
        text = table_text(table)
        if any(part in text for part in active_parts):
            current.append(table)
        elif any(part in text for part in foreign_parts):
            dropped.append(table)
        else:
            unmarked.append(table)
    filtered = [*current, *unmarked]
    if not dropped or not filtered:
        return tables, []
    decisions = [
        f"Split-agreement QA removed foreign council table {table_label(table, index)} before save."
        for index, table in enumerate(dropped)
    ]
    return filtered, decisions


def cohort(table: dict[str, Any], lga: str | None = None, *, split_row: bool = False) -> dict[str, str]:
    text = table_text(table)
    parts = lga_name_parts(lga)
    if split_row and parts and any(part in text for part in parts):
        return {"kind": "general", "label": "current LGA table", "confidence": "high"}
    if re.search(r"\ball employees except\b|\bexcept\s+(library|maternal|mch|nurs|pool|leisure|school crossing)", text):
        return {"kind": "general", "label": "general table excluding specialist cohorts", "confidence": "high"}
    if re.search(r"\bindoor\b|\bother than physical\b", text):
        return {"kind": "general", "label": "standard indoor benchmark bandings", "confidence": "high"}
    specialised = [
        ("casual rates", r"\bcasual\b"),
        ("maternal and child health", r"\b(maternal|mch|child health|immunisation|nurse|nursing)\b"),
        ("pool services", r"\b(pool|aquatic|lifeguard|swim|swimming)\b"),
        ("child care / early years", r"\b(child care|childcare|early years|kindergarten|preschool)\b"),
        ("library", r"\b(library|libraries|librarian)\b"),
        ("street cleaning", r"\bstreet cleaning\b|\bwaste collection\b"),
        ("art gallery annualised rates", r"\bart gallery\b|\bannualised rates\b"),
        ("allowance schedule", r"\ballowance(s)?\s+(table|schedule)\b|^allowance(s)?\b"),
        ("parks and gardens", r"\bparks?\s+and\s+gardens?\b"),
        ("arboriculture", r"\barboriculture\b|\barborist\b"),
        ("tourism / visitor services", r"\b(tourism|visitor information|visitor services)\b"),
        ("senior officers", r"\b(senior officer|executive|chief executive|ceo)\b"),
        ("apprentices / trainees", r"\b(apprentice|trainee|cadet|graduate)\b"),
        ("school crossing", r"\b(school crossing|crossing supervisor)\b"),
        ("community transport", r"\bcommunity transport\b|\btransport staff\b"),
        ("aged / disability / home care", r"\b(aged care|disability|home care|home/personal care|personal care|community care)\b"),
        ("loaded allowance rates", r"\b(including|inclusive of|with)\s+(industry\s+)?allowance\b|\bindustry allowance\b"),
        ("operational outdoor cohort", r"\b(outdoor\s+full\s+time|outdoor\s+[-–]|outdoor\b.{0,80}(physical\s*&\s*community services|physical and community services))\b"),
        ("physical services loaded cohort", r"\bphysical and community services\b|\bphysical\s*&\s*community services\b"),
        ("legacy council cohort", r"\b(ex[-\s]?(city|shire|council)|former\s+(city|shire|council)|pre[-\s]?amalgamation)\b"),
        ("leisure services", r"\bleisure\b"),
    ]
    for label, pattern in specialised:
        if re.search(pattern, text):
            return {"kind": "specialised", "label": label, "confidence": "high"}
    if re.search(r"\bgeneral classifications?\b|\bgeneral\s+classifications?\s+and\s+rates?\s+of\s+pay\b", text):
        return {"kind": "general", "label": "general classification benchmark table", "confidence": "high"}
    if re.search(r"\btechnical\b.{0,60}\bprofessional\b.{0,60}\badministrative\b|\bpay\s+rates?\s+20\d{2}\b", text):
        return {"kind": "general", "label": "standard technical/professional benchmark bandings", "confidence": "high"}
    cells = table_cells(table)
    general_signals = sum([
        bool(re.search(r"\bband(s)?\s*1\s*(-|to|through|&|and)?\s*8\b", text)),
        bool(re.search(r"\bclassification(s)?\b", text)),
        bool(re.search(r"\b(salary|wage|weekly|annual)\s+(rates|table)\b", text)),
        bool(re.search(r"\btechnical\b|\bprofessional\b|\badministrative\b", text)),
        bool(re.search(r"\bordinary\b|\bbase rate\b|\bgeneral employee\b|\bemployee classifications\b", text)),
        len(cells) >= 20,
    ])
    if general_signals >= 2 or len(cells) >= 24:
        return {"kind": "general", "label": "standard bandings", "confidence": "high" if general_signals >= 3 else "medium"}
    return {"kind": "unknown", "label": "unclear cohort", "confidence": "low"}


def out_of_scope_specialist_appendix(table: dict[str, Any]) -> bool:
    text = table_text(table)
    return bool(
        re.search(
            r"\b(maternal|m\s*&\s*ch|mch|child health|immunisation|nurse|nursing)\b",
            text,
        )
    )


def filter_out_of_scope_specialist_tables(tables: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    filtered: list[dict[str, Any]] = []
    decisions: list[str] = []
    for index, table in enumerate(tables):
        if out_of_scope_specialist_appendix(table):
            decisions.append(
                f"Source hygiene excluded specialist appendix pay table {table_label(table, index)} before benchmark QA."
            )
            continue
        filtered.append(table)
    if not filtered:
        return tables, []
    return filtered, decisions


def table_label(table: dict[str, Any], index: int) -> str:
    return " | ".join(str(part).strip() for part in [
        table.get("table_title") or f"Table {index + 1}",
        table.get("effective_from"),
        table.get("rate_kind"),
    ] if str(part or "").strip())


def standard_hours_rank(table: dict[str, Any]) -> int:
    text = table_text(table)
    if re.search(r"\b38\s*hours?\b|\b38\s*hour\b", text):
        return 0
    if re.search(r"\b35\s*hours?\b|\b35\s*hour\b", text):
        return 2
    return 1


def rate_kind_rank(table: dict[str, Any]) -> int:
    kind = str(table.get("rate_kind") or "").lower()
    return {"weekly": 0, "annual": 1, "fortnightly": 2}.get(kind, 3)


def benchmark_sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
    return (
        standard_hours_rank(item["table"]),
        rate_kind_rank(item["table"]),
        -len(item["cells"]),
    )


def pay_schedule_number(table: dict[str, Any]) -> int | None:
    match = re.search(r"\bpay\s+schedule\s+([12])\b", table_text(table), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def schedule_one_two_pair(items: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    schedule_one = [item for item in items if pay_schedule_number(item["table"]) == 1]
    schedule_two = [item for item in items if pay_schedule_number(item["table"]) == 2]
    if not schedule_one or not schedule_two:
        return None, []
    schedule_one.sort(key=benchmark_sort_key)
    keeper = schedule_one[0]
    alternates = [item for item in items if item["index"] != keeper["index"] and pay_schedule_number(item["table"]) == 2]
    if not alternates:
        return None, []
    return keeper, alternates


def indoor_benchmark_table(table: dict[str, Any]) -> bool:
    text = table_text(table)
    return bool(re.search(r"\bindoor\b|\bother than physical\b", text))


def outdoor_physical_loaded_table(table: dict[str, Any]) -> bool:
    text = table_text(table)
    return bool(
        re.search(r"\boutdoor\b", text)
        and re.search(r"\bphysical\s*(?:&|and)?\s*community services\b", text)
    )


def standard_hours_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ranks = {standard_hours_rank(a), standard_hours_rank(b)}
    return 0 in ranks and 2 in ranks


def merge_continuation(target: dict[str, Any], source: dict[str, Any]) -> bool:
    target_cells = table_cells(target)
    rows_to_add = []
    for row in source.get("rows") or []:
        if isinstance(row, dict):
            key = cell_key(row)
            if key and key not in target_cells:
                rows_to_add.append(row)
    if not rows_to_add:
        return False
    target["rows"] = [*(target.get("rows") or []), *rows_to_add]
    pages = page_list(target.get("source_pages")) + page_list(target.get("source_page")) + page_list(source.get("source_pages")) + page_list(source.get("source_page"))
    if pages:
        target["source_pages"] = sorted(set(pages))
    if not target.get("source_clause") and source.get("source_clause"):
        target["source_clause"] = source.get("source_clause")
    return True


def resolve_cohorts(
    tables: list[dict[str, Any]],
    lga: str | None = None,
    *,
    split_row: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    working = json.loads(json.dumps(tables))
    remove: set[int] = set()
    decisions: list[str] = []
    by_effective: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, table in enumerate(working):
        effective = str(table.get("effective_from") or "").strip()
        if effective:
            by_effective[effective].append((index, table))
    for _, dated_group in by_effective.items():
        indoor = [(index, table) for index, table in dated_group if indoor_benchmark_table(table)]
        outdoor = [(index, table) for index, table in dated_group if outdoor_physical_loaded_table(table)]
        if not indoor or not outdoor:
            continue
        indoor.sort(key=lambda item: benchmark_sort_key({"table": item[1], "cells": table_cells(item[1])}))
        keeper_index, keeper_table = indoor[0]
        for candidate_index, candidate_table in outdoor:
            if candidate_index == keeper_index or candidate_index in remove:
                continue
            same_kind = str(candidate_table.get("rate_kind") or "") == str(keeper_table.get("rate_kind") or "")
            added = merge_continuation(keeper_table, candidate_table) if same_kind else False
            remove.add(candidate_index)
            decisions.append(
                f"Indoor/Outdoor QA retained Indoor benchmark table {table_label(keeper_table, keeper_index)} "
                f"and {'merged missing lower-band cells from' if added else 'dropped loaded'} "
                f"Outdoor physical/community services table {table_label(candidate_table, candidate_index)}."
            )
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, table in enumerate(working):
        if index in remove:
            continue
        effective = str(table.get("effective_from") or "").strip()
        kind = str(table.get("rate_kind") or "__unknown__").strip()
        if effective:
            groups[f"{effective}::{kind}"].append((index, table))
    blockers: list[str] = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        assessed = [
            {"index": index, "table": table, "cohort": cohort(table, lga, split_row=split_row), "cells": table_cells(table)}
            for index, table in group
        ]
        current_lga = [item for item in assessed if split_row and item["cohort"]["label"] == "current LGA table"]
        if current_lga:
            current_lga.sort(key=lambda item: len(item["cells"]), reverse=True)
            keeper = current_lga[0]
            for item in assessed:
                if item["index"] == keeper["index"]:
                    continue
                remove.add(item["index"])
                decisions.append(f"Split-agreement QA retained current LGA table {table_label(keeper['table'], keeper['index'])} and dropped other council table {table_label(item['table'], item['index'])}.")
            continue
        general = [item for item in assessed if item["cohort"]["kind"] == "general"]
        specialised = [item for item in assessed if item["cohort"]["kind"] == "specialised"]
        if not general:
            by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in assessed:
                by_title[normalised_title(item["table"])].append(item)
            duplicate_title_groups = [items for title, items in by_title.items() if title and len(items) > 1]
            if duplicate_title_groups:
                for items in duplicate_title_groups:
                    items.sort(key=lambda item: len(item["cells"]), reverse=True)
                    keeper = items[0]
                    for candidate in items[1:]:
                        merge_continuation(keeper["table"], candidate["table"])
                        remove.add(candidate["index"])
                        decisions.append(f"Removed duplicate non-general pay table {table_label(candidate['table'], candidate['index'])} and retained the fuller same-title extraction {table_label(keeper['table'], keeper['index'])}.")
                remaining = [item for item in assessed if item["index"] not in remove]
                if len(remaining) <= 1:
                    continue
            labels = "; ".join(table_label(item["table"], item["index"]) for item in assessed)
            blockers.append(f"Duplicate pay tables need cohort review for {key}: {labels}")
            continue
        indoor = [item for item in general if indoor_benchmark_table(item["table"])]
        outdoor_loaded = [item for item in specialised if outdoor_physical_loaded_table(item["table"])]
        if indoor and outdoor_loaded:
            indoor.sort(key=benchmark_sort_key)
            keeper = indoor[0]
            for item in outdoor_loaded:
                added = merge_continuation(keeper["table"], item["table"])
                remove.add(item["index"])
                decisions.append(
                    f"Indoor/Outdoor QA retained Indoor benchmark table {table_label(keeper['table'], keeper['index'])} "
                    f"and {'merged missing lower-band cells from' if added else 'dropped overlapping loaded'} "
                    f"Outdoor physical/community services table {table_label(item['table'], item['index'])}."
                )
            general = [item for item in general if item["index"] not in remove]
            keeper["cells"] = table_cells(keeper["table"])
            specialised = [item for item in specialised if item["index"] not in remove]
        schedule_keeper, schedule_alternates = schedule_one_two_pair(general)
        if schedule_keeper and schedule_alternates:
            for item in schedule_alternates:
                remove.add(item["index"])
                decisions.append(
                    f"Pay Schedule QA retained general Schedule 1 {table_label(schedule_keeper['table'], schedule_keeper['index'])} "
                    f"and dropped alternate Schedule 2/depot allowance track {table_label(item['table'], item['index'])}."
                )
            general = [item for item in general if item["index"] not in remove]
        general.sort(key=benchmark_sort_key)
        keeper = general[0]
        unresolved = []
        for candidate in general[1:]:
            overlap = len(candidate["cells"] & keeper["cells"])
            if overlap > 0 and standard_hours_conflict(keeper["table"], candidate["table"]):
                remove.add(candidate["index"])
                decisions.append(f"Benchmark QA retained standard 38-hour table {table_label(keeper['table'], keeper['index'])} and dropped non-standard 35-hour table {table_label(candidate['table'], candidate['index'])}.")
            elif overlap > 0 and same_rates(keeper["table"], candidate["table"]):
                merge_continuation(keeper["table"], candidate["table"])
                remove.add(candidate["index"])
                decisions.append(f"Removed duplicate copy {table_label(candidate['table'], candidate['index'])} after matching it to {table_label(keeper['table'], keeper['index'])}.")
            elif overlap > 0 and same_title_duplicate(keeper["table"], candidate["table"]):
                merge_continuation(keeper["table"], candidate["table"])
                remove.add(candidate["index"])
                decisions.append(f"Removed same-title duplicate pay table {table_label(candidate['table'], candidate['index'])} and retained the fuller extraction {table_label(keeper['table'], keeper['index'])}.")
            elif (
                overlap > 0
                and not distinct_cohort_title_pair(keeper["table"], candidate["table"])
                and overlap / max(1, min(len(keeper["cells"]), len(candidate["cells"]))) >= 0.8
            ):
                merge_continuation(keeper["table"], candidate["table"])
                remove.add(candidate["index"])
                decisions.append(f"Removed overlapping generic duplicate pay table {table_label(candidate['table'], candidate['index'])} and retained fuller extraction {table_label(keeper['table'], keeper['index'])}.")
            elif overlap == 0 and merge_continuation(keeper["table"], candidate["table"]):
                remove.add(candidate["index"])
                decisions.append(f"Merged continuation pay table {table_label(candidate['table'], candidate['index'])} into {table_label(keeper['table'], keeper['index'])}.")
                keeper["cells"] = table_cells(keeper["table"])
            else:
                unresolved.append(candidate)
        if unresolved:
            labels = "; ".join(table_label(item["table"], item["index"]) for item in [keeper, *unresolved])
            blockers.append(f"Duplicate general pay tables need human selection for {key}: {labels}")
            continue
        for item in specialised:
            remove.add(item["index"])
            decisions.append(f"Cohort QA retained {table_label(keeper['table'], keeper['index'])} and dropped specialised {item['cohort']['label']} table {table_label(item['table'], item['index'])}.")
    if blockers:
        return tables, decisions, blockers
    return [table for index, table in enumerate(working) if index not in remove], decisions, blockers


def blocking_validations(validations: Any) -> list[dict[str, Any]]:
    out = []
    for item in validations or []:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or item.get("severity") or "").lower()
        if level in {"error", "critical", "blocker", "failed"}:
            out.append(item)
    return out


def scenario_eligible(scenario: dict[str, Any]) -> bool:
    return str(scenario.get("status") or "") in {"consistent", "table_resolved", "baseline"}


def scenario_pay_table_only(scenario: dict[str, Any]) -> bool:
    if str(scenario.get("status") or "") != "needs_attention":
        return False
    reason = str(scenario.get("reason") or "").lower()
    if "table exists for this period but no uplift rule covers it" in reason:
        return True
    if "rule did not cover any cells" in reason:
        return True
    return False


def computed_overrides(result: dict[str, Any]) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    overrides: dict[str, dict[str, dict[str, Any]]] = {}
    decisions: list[str] = []
    for scenario in result.get("scenarios") or []:
        if not isinstance(scenario, dict) or scenario_eligible(scenario):
            continue
        period = scenario.get("period_effective_from")
        if not period:
            continue
        deltas = scenario.get("cell_deltas") or []
        computed_candidates = [
            delta for delta in deltas
            if isinstance(delta, dict)
            and not delta.get("within_tolerance")
            and delta.get("override_action") is None
            and delta.get("computed_weekly") is not None
        ]
        use_computed = [
            delta for delta in computed_candidates
            if delta.get("recommended_action") == "use_computed"
        ]
        accept_table = [
            delta for delta in deltas
            if isinstance(delta, dict)
            and not delta.get("within_tolerance")
            and delta.get("override_action") is None
            and delta.get("recommended_action") == "accept_table"
            and delta.get("actual_weekly") is not None
            and delta.get("computed_weekly") is None
        ]
        unhandled_computed = [
            delta for delta in computed_candidates
            if delta.get("recommended_action") != "use_computed"
        ]
        if not computed_candidates and not accept_table:
            continue
        isolated = len(unhandled_computed) == 1 and len(deltas) >= 10
        if unhandled_computed and not isolated:
            continue
        overrides.setdefault(str(period), {})
        for delta in use_computed:
            key = f"{delta.get('band')}:{delta.get('level')}"
            overrides[str(period)][key] = {"action": "use_computed", "weekly": float(delta.get("computed_weekly"))}
        if isolated:
            delta = unhandled_computed[0]
            key = f"{delta.get('band')}:{delta.get('level')}"
            overrides[str(period)][key] = {"action": "use_computed", "weekly": float(delta.get("computed_weekly"))}
        for delta in accept_table:
            key = f"{delta.get('band')}:{delta.get('level')}"
            overrides[str(period)][key] = {"action": "accept", "weekly": float(delta.get("actual_weekly"))}
        if use_computed:
            decisions.append(f"Used computed values for {len(use_computed)} recommended variance cells in {period}.")
        if isolated:
            decisions.append(f"Used computed value for isolated variance {unhandled_computed[0].get('band')}:{unhandled_computed[0].get('level')} in {period}.")
        if accept_table:
            decisions.append(f"Accepted {len(accept_table)} introduced table row(s) without prior-period equivalents in {period}.")
    return overrides, decisions


def rule_extraction_review_blockers(result: dict[str, Any]) -> list[str]:
    def money(value: Any) -> str:
        try:
            return f"${float(value):,.2f}"
        except (TypeError, ValueError):
            return f"${value}"

    blockers: list[str] = []
    for scenario in result.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        decision = scenario.get("decision_recommendation")
        if not isinstance(decision, dict) or decision.get("action") != "needs_rule_extraction_review":
            continue
        period = scenario.get("period_effective_from") or "unknown period"
        rule_quantum = scenario.get("rule_quantum") or decision.get("rule_quantum") or "accepted uplift rule"
        affected = decision.get("affected_cells")
        covered = decision.get("covered_cells")
        mechanised = decision.get("mechanised_weekly_increase")
        implied = decision.get("implied_weekly_increase")
        pieces = [
            f"Uplift rule extraction review required for {period}",
            f"rule {rule_quantum}",
        ]
        if affected and covered:
            pieces.append(f"{affected}/{covered} cells conflict")
        if mechanised is not None and implied is not None:
            pieces.append(f"rule implies {money(mechanised)}/week but table implies {money(implied)}/week")
        blockers.append("; ".join(pieces) + ". Fix the uplift rule/table binding before scenario QA.")
    return blockers


def qa_note(section: str, lines: list[str]) -> dict[str, Any]:
    body = "\n".join(["Reviewer QA note", "", *[f"- {line}" for line in lines if line]])
    notes = "\n".join([f"Automated reviewer accepted {section}.", *[line for line in lines if line]])
    return {"enabled": True, "summary": body, "notes": notes}


def post_human_qa(ae_id: str, section: str, lines: list[str]) -> None:
    api(f"/api/councils/{urllib.parse.quote(ae_id)}/sections/{urllib.parse.quote(section)}/human-qa", method="PATCH", body=qa_note(section, lines), timeout=60)


def extract_pay_tables(ae_id: str, overview: dict[str, Any], record: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    candidates = api(f"/api/councils/{urllib.parse.quote(ae_id)}/pay-tables/find-candidates", method="POST", body={}, timeout=240)
    overview_pages = page_list((overview or {}).get("likely_pay_table_pages"))
    ranked_pay_pages = ordered_pages(overview_pages, candidates.get("pay_table_pages"))
    candidate_pages = page_list(candidates.get("candidate_pages"))
    page_count = pay_table_page_count(overview, record)
    tried: list[int] = []
    extractions: list[dict[str, Any]] = []
    primary_groups, fallback_groups = pay_extraction_groups(overview_pages, ranked_pay_pages, candidate_pages, page_count)

    def extract_group(group: list[int]) -> None:
        start, end = group[0], group[-1]
        tried.extend(group)
        result = api(f"/api/councils/{urllib.parse.quote(ae_id)}/pay-tables/extract-range", method="POST", body={"start_page": start, "end_page": end}, timeout=420)
        if len(group) > 1 and not result.get("tables"):
            for page in group:
                result = api(f"/api/councils/{urllib.parse.quote(ae_id)}/pay-tables/extract-range", method="POST", body={"start_page": page, "end_page": page}, timeout=420)
                extractions.append(result)
        else:
            extractions.append(result)

    for group in primary_groups:
        extract_group(group)
        tables = [table for result in extractions for table in result.get("tables") or [] if isinstance(table, dict)]
        if tables:
            break
    tables = [table for result in extractions for table in result.get("tables") or [] if isinstance(table, dict)]
    if not tables:
        for group in fallback_groups:
            extract_group(group)
            tables = [table for result in extractions for table in result.get("tables") or [] if isinstance(table, dict)]
            if tables:
                break
    return tables, [str(result.get("raw") or "") for result in extractions if result.get("raw")], sorted(set(tried))


def accepted_rule_dates(ae_id: str) -> set[str]:
    canonical = api(f"/api/councils/{urllib.parse.quote(ae_id)}", timeout=120)
    uplift = ((canonical.get("sections") or {}).get("uplift_rules") or {}).get("data") or {}
    accepted = uplift.get("accepted") or {}
    document = accepted.get("document") if isinstance(accepted, dict) else {}
    rules = document.get("rules") if isinstance(document, dict) else []
    dates = set()
    for rule in rules or []:
        if isinstance(rule, dict) and rule.get("effective_date"):
            dates.add(str(rule["effective_date"]))
    return dates


def empty_uplift_source_issue(suggestion_response: dict[str, Any]) -> str | None:
    suggestion = suggestion_response.get("suggestion") if isinstance(suggestion_response, dict) else None
    if not isinstance(suggestion, dict):
        return None
    document = suggestion.get("document") if isinstance(suggestion.get("document"), dict) else {}
    rules = document.get("rules") if isinstance(document, dict) else []
    if rules:
        return None
    provenance = suggestion.get("provenance") if isinstance(suggestion.get("provenance"), dict) else {}
    evidence = " ".join(
        str(value or "")
        for value in (
            document.get("notes") if isinstance(document, dict) else "",
            provenance.get("llm_raw_response") if isinstance(provenance, dict) else "",
        )
    ).lower()
    if "approval decision" in evidence and ("not the agreement" in evidence or "not the actual enterprise agreement" in evidence):
        return "Fetched PDF appears to be the Fair Work approval decision only, not the enterprise agreement text."
    return None


def process_one(row: dict[str, Any], *, clear: bool) -> dict[str, Any]:
    ae_id = row["ae_id"]
    result: dict[str, Any] = {
        "ae_id": ae_id,
        "lga": row.get("canonical_lga_short_name"),
        "source_name": row.get("source_name"),
        "started_at": utc_now(),
        "status": "running",
        "steps": [],
        "decisions": [],
        "system_improvements": [],
        "blockers": [],
    }

    def step(name: str, detail: str = "") -> None:
        print(f"[{ae_id}] {name} {detail}".strip(), flush=True)
        result["steps"].append({"at": utc_now(), "name": name, "detail": detail})

    try:
        if clear:
            step("clear", "archiving previous review state")
            api(f"/api/councils/{urllib.parse.quote(ae_id)}/clear-review-record", method="POST", body={"reason": "74-agreement synthetic QA learning run", "include_related": False}, timeout=240)

        step("overview", "generate/check source map")
        canonical = api(f"/api/councils/{urllib.parse.quote(ae_id)}/overview/generate", method="POST", body={}, timeout=240)
        post_human_qa(ae_id, "overview", ["Source map and metadata were available for downstream review."])

        step("uplift", "suggest and accept wage rules")
        suggestion_response = api(f"/api/councils/{urllib.parse.quote(ae_id)}/uplift-rules/suggest", method="POST", timeout=420)
        api(f"/api/councils/{urllib.parse.quote(ae_id)}/uplift-rules/accept", method="POST", body={}, timeout=120)
        rules = accepted_rule_dates(ae_id)
        if not rules:
            source_issue = empty_uplift_source_issue(suggestion_response)
            if source_issue:
                result["status"] = "skipped_source"
                result["source_issue"] = source_issue
                result["completed_at"] = utc_now()
                result["system_improvements"].append({
                    "stage": "Source intake quality gate",
                    "request": "Quarantine approval-decision-only PDFs before synthetic QA attempts.",
                    "judgement": [source_issue],
                })
                try:
                    api(
                        f"/api/intake/candidates/{urllib.parse.quote(ae_id)}/decision",
                        method="POST",
                        body={
                            "status": "needs_review",
                            "reason": "Approval decision PDF, not agreement text",
                            "notes": source_issue,
                        },
                        timeout=120,
                    )
                except Exception as intake_exc:  # noqa: BLE001
                    result["system_improvements"].append({
                        "stage": "Source intake quality gate",
                        "request": "Persist approval-decision-only source quarantine when intake row is available.",
                        "judgement": [f"Could not persist intake decision: {intake_exc}"],
                    })
                print(f"[{ae_id}] SKIPPED_SOURCE {source_issue}", flush=True)
                return result
            raise RuntimeError("No uplift rules were available to accept.")
        post_human_qa(ae_id, "uplift_rules", [f"Accepted {len(rules)} uplift rule dates for scenario testing."])

        step("pay", "extract, classify cohorts, save")
        canonical = api(f"/api/councils/{urllib.parse.quote(ae_id)}", timeout=120)
        tables, _, tried_pages = extract_pay_tables(ae_id, canonical.get("overview") or {}, canonical)
        result["pay_pages_tried"] = tried_pages
        if not tables:
            raise RuntimeError("No pay tables could be accepted synthetically after candidate and fallback pages.")
        tables, specialist_exclusion_decisions = filter_out_of_scope_specialist_tables(tables)
        result["decisions"].extend(specialist_exclusion_decisions)
        is_split_like = split_like_row(ae_id, row, canonical)
        if is_split_like:
            tables, split_filter_decisions = filter_split_pay_tables(tables, row, canonical)
            result["decisions"].extend(split_filter_decisions)
            if split_filter_decisions:
                result["system_improvements"].append({
                    "stage": "Pay QA multi-council guard",
                    "request": "Use council-name context around split-agreement pay appendices before saving tables.",
                    "judgement": split_filter_decisions,
                })
        resolved, cohort_decisions, cohort_blockers = resolve_cohorts(
            tables,
            row.get("canonical_lga_short_name"),
            split_row=is_split_like,
        )
        result["decisions"].extend(cohort_decisions)
        if cohort_decisions:
            result["system_improvements"].append({
                "stage": "Pay QA cohort judgement",
                "request": "Promote repeated cohort-selection decisions into backend pay-table cohort policy.",
                "judgement": cohort_decisions,
            })
        if cohort_blockers:
            raise RuntimeError(cohort_blockers[0])
        snap_decisions = prepare_rule_anchored_dates(resolved, sorted(accepted_rule_dates(ae_id)))
        if snap_decisions:
            result["decisions"].extend(snap_decisions)
            result["system_improvements"].append({
                "stage": "Pay QA rule-anchored date normalisation",
                "request": "Run cohort duplicate resolution after rule-anchored date snapping, not only before save.",
                "judgement": snap_decisions,
            })
        resolved, snapped_cohort_decisions, snapped_cohort_blockers = resolve_cohorts(
            resolved,
            row.get("canonical_lga_short_name"),
            split_row=is_split_like,
        )
        result["decisions"].extend(snapped_cohort_decisions)
        cohort_decisions.extend(snap_decisions)
        cohort_decisions.extend(snapped_cohort_decisions)
        if snapped_cohort_blockers:
            raise RuntimeError(snapped_cohort_blockers[0])
        save = api(
            f"/api/councils/{urllib.parse.quote(ae_id)}/pay-tables/save",
            method="POST",
            body={
                "action": "replace",
                "tables": resolved,
                "source_ref": f"Automated review pages {', '.join(map(str, tried_pages[:24]))}",
                "notes": "Automated reviewer accepted the extracted pay tables.\n" + " ".join(cohort_decisions),
                "status": "done",
                "timeline_policy": "rule_anchored",
            },
            timeout=240,
        )
        blockers = blocking_validations(save.get("validations"))
        if blockers:
            raise RuntimeError(f"{len(blockers)} pay-table validation blocker(s) remained after save.")
        post_human_qa(ae_id, "pay_tables", [
            f"Saved {len(resolved)} pay table(s) with no blocking validation errors.",
            "Checked duplicate dates by cohort and retained the general benchmark table set." if cohort_decisions else "",
        ])

        step("scenarios", "run checks and apply defensible computed overrides")
        scenario = api(
            f"/api/councils/{urllib.parse.quote(ae_id)}/uplift-rules/scenarios",
            method="POST",
            body={"overrides": {}, "change_context": {"scope": "synthetic_human_batch", "action": "run_scenarios"}},
            timeout=240,
        )
        rule_review_blockers = rule_extraction_review_blockers(scenario)
        if rule_review_blockers:
            result["system_improvements"].append({
                "stage": "Uplift QA rule/table binding",
                "request": "Stop scenario QA when the accepted uplift rule conflicts with a coherent published table pattern; send the record back to uplift-rule extraction review.",
                "judgement": rule_review_blockers,
            })
            raise RuntimeError(rule_review_blockers[0])
        overrides: dict[str, dict[str, dict[str, Any]]] = {}
        override_decisions: list[str] = []
        for _ in range(4):
            next_overrides, next_decisions = computed_overrides(scenario)
            if not next_overrides:
                break
            changed = False
            for period, cells in next_overrides.items():
                target = overrides.setdefault(period, {})
                for cell_key, override in cells.items():
                    if target.get(cell_key) != override:
                        target[cell_key] = override
                        changed = True
            if not changed:
                break
            override_decisions.extend(next_decisions)
            api(
                f"/api/councils/{urllib.parse.quote(ae_id)}/uplift-rules/scenarios/overrides",
                method="POST",
                body={"overrides": overrides, "change_context": {"scope": "synthetic_human_batch", "action": "use_computed_recommended"}},
                timeout=120,
            )
            scenario = api(
                f"/api/councils/{urllib.parse.quote(ae_id)}/uplift-rules/scenarios",
                method="POST",
                body={"overrides": overrides, "change_context": {"scope": "synthetic_human_batch", "action": "rerun_after_computed_overrides"}},
                timeout=240,
            )
            rule_review_blockers = rule_extraction_review_blockers(scenario)
            if rule_review_blockers:
                result["system_improvements"].append({
                    "stage": "Uplift QA rule/table binding",
                    "request": "Stop scenario QA when the accepted uplift rule conflicts with a coherent published table pattern; send the record back to uplift-rule extraction review.",
                    "judgement": rule_review_blockers,
                })
                raise RuntimeError(rule_review_blockers[0])
        if override_decisions:
            result["decisions"].extend(override_decisions)
            result["system_improvements"].append({
                "stage": "Scenario QA computed-value judgement",
                "request": "Bake repeated computed-value override decisions into scenario engine policy.",
                "judgement": override_decisions,
            })
        outstanding = [
            sc for sc in scenario.get("scenarios") or []
            if isinstance(sc, dict)
            and sc.get("period_effective_from")
            and not scenario_eligible(sc)
            and not scenario_pay_table_only(sc)
        ]
        if outstanding:
            raise RuntimeError(f"{len(outstanding)} scenario period(s) still need a human decision before governed promotion.")

        step("governed", "promote eligible assets")
        governed = api(f"/api/councils/{urllib.parse.quote(ae_id)}/governed-set", timeout=120)
        governed_by_period = {period.get("effective_from"): period for period in (governed.get("governed") or {}).get("periods") or [] if isinstance(period, dict)}
        promoted: list[str] = []
        for scenario_row in scenario.get("scenarios") or []:
            if not isinstance(scenario_row, dict) or not (scenario_eligible(scenario_row) or scenario_pay_table_only(scenario_row)):
                continue
            date = scenario_row.get("period_effective_from")
            if not date:
                continue
            existing = governed_by_period.get(date) or {}
            kinds = []
            if not existing.get("pay_table_governed_at"):
                kinds.append("pay_table")
            if scenario_eligible(scenario_row) and date in rules and not existing.get("uplift_rule_governed_at"):
                kinds.append("uplift_rule")
            for kind in kinds:
                api(f"/api/councils/{urllib.parse.quote(ae_id)}/governed-set/promote", method="POST", body={"period_effective_from": date, "kind": kind}, timeout=120)
                promoted.append(f"{kind} {date}")
        post_human_qa(ae_id, "scenarios", [
            f"Ran {len(scenario.get('scenarios') or [])} scenario period(s).",
            f"Promoted {len(promoted)} governed asset(s)." if promoted else "No additional governed promotions were needed.",
        ])
        post_human_qa(ae_id, "uplifts", [f"Accepted governed set after {len(promoted)} promotion(s)."])
        result["status"] = "completed"
        result["completed_at"] = utc_now()
        result["promoted"] = promoted
        return result
    except Exception as exc:
        message = str(exc)
        result["status"] = "blocked"
        result["blocked_at"] = utc_now()
        result["blockers"].append({
            "message": message,
            "options_considered": [
                "apply a safe cohort/scenario heuristic and rerun if the pattern is clear",
                "capture a backend policy improvement if the decision repeats",
                "leave the agreement blocked and continue the batch if judgement is not defensible",
            ],
        })
        print(f"[{ae_id}] BLOCKED {message}", flush=True)
        return result


def select_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    decision_statuses = intake_decision_statuses()
    selected = [
        row for row in rows
        if (row.get("fetch_metadata") or {}).get("pipeline_status") == "active"
        and row.get("canonical_lga_short_name")
        and row.get("pdf_frozen")
        and not row.get("processing_gated")
        and str(
            (row.get("intake_decision") or {}).get("status")
            or row.get("acceptance_state")
            or decision_statuses.get(str(row.get("ae_id") or "").lower())
            or ""
        ).lower() not in {"rejected", "needs_review"}
    ]
    selected.sort(key=lambda row: str(row.get("canonical_lga_short_name") or row.get("ae_id")))
    return selected[:limit]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=74)
    parser.add_argument("--no-clear", action="store_true")
    parser.add_argument("--resume-log", default="")
    parser.add_argument("--rerun-blocked", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.0)
    args = parser.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path(args.resume_log) if args.resume_log else LOG_DIR / f"{run_id}_synthetic_qa_74.json"
    rows = api("/api/councils", timeout=120)
    selected = select_rows(rows, args.limit)
    if args.resume_log and log_path.exists():
        run_log = json.loads(log_path.read_text(encoding="utf-8"))
        run_log.setdefault("resumed_at", []).append(utc_now())
    else:
        run_log = {
            "run_id": run_id,
            "started_at": utc_now(),
            "limit": args.limit,
            "selected_count": len(selected),
            "results": [],
        }
    if args.rerun_blocked:
        blocked_ids = {item.get("ae_id") for item in run_log.get("results") or [] if item.get("status") == "blocked"}
        run_log["results"] = [item for item in run_log.get("results") or [] if item.get("status") != "blocked"]
        remaining = [row for row in selected if row.get("ae_id") in blocked_ids]
    else:
        processed = {item.get("ae_id") for item in run_log.get("results") or []}
        remaining = [row for row in selected if row.get("ae_id") not in processed]
    print(f"Selected {len(selected)} active ready agreements for synthetic QA; {len(remaining)} remaining", flush=True)
    for index, row in enumerate(remaining, 1):
        print(f"\n=== {index}/{len(selected)} {row.get('canonical_lga_short_name')} {row.get('ae_id')} ===", flush=True)
        item = process_one(row, clear=not args.no_clear)
        run_log["results"].append(item)
        log_path.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
        if args.sleep:
            time.sleep(args.sleep)
    run_log["finished_at"] = utc_now()
    statuses = defaultdict(int)
    for item in run_log["results"]:
        statuses[item.get("status")] += 1
    run_log["summary"] = dict(statuses)
    log_path.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    print(f"\nWrote {log_path}", flush=True)
    print(json.dumps(run_log["summary"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
