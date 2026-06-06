"""Lightweight official-source job intake preview."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Lock
from typing import Any, Callable
from urllib.parse import quote_plus, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zipfile

# Some local HTTPS inspection tools expose SSLKEYLOGFILE as a named pipe. If that
# handle goes stale, urllib3 can fail before a request is even issued.
os.environ.pop("SSLKEYLOGFILE", None)
import requests
from requests import RequestException
import urllib3

from benchmarking_data_factory.reference.council_jobs import (
    canonicalize_job_url,
    council_job_source_registry_payload,
    endpoint_discovery_candidates,
    POLL_TIER_EXPLAINER,
    SECONDARY_SOURCES,
)
from benchmarking_data_factory.workbench.job_schema import (
    enrich_job_with_pay_rows,
    html_to_text,
    normalize_council_job_record,
    normalize_whitespace,
)


JOB_INTAKE_USER_AGENT = "Mozilla/5.0 (compatible; CouncilJobsResearchBot/1.0; +contact@example.com)"
BROWSER_COMPAT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
}
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


JOB_INTAKE_SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "var" / "job_intake" / "scrape_preview_snapshot.json"
JOB_INTAKE_SECONDARY_SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "var" / "job_intake" / "secondary_preview_snapshot.json"
JOB_INTAKE_ACCUMULATOR_PATH = Path(__file__).resolve().parents[3] / "var" / "job_intake" / "checked_job_accumulator.json"
JOB_INTAKE_CANDIDATE_LEDGER_PATH = Path(__file__).resolve().parents[3] / "var" / "job_intake" / "observed_job_candidates.json"

STAGE1_REQUIRED_FIELDS = [
    {"id": "job_uid", "label": "Job UID", "paths": ("job_uid",)},
    {"id": "canonical_url", "label": "Canonical URL", "paths": ("canonical_url", "job_url")},
    {"id": "source_url", "label": "Source URL", "paths": ("source_url", "job_url")},
    {"id": "source_family", "label": "Source family", "paths": ("source_family",)},
    {"id": "council_name", "label": "Council", "paths": ("council_name", "short_name")},
    {"id": "council_grouping", "label": "Council grouping", "paths": ("council_grouping",)},
    {"id": "job_title", "label": "Job title", "paths": ("job_title",)},
    {"id": "job_status", "label": "Job status", "paths": ("job_status",)},
    {"id": "state", "label": "State", "paths": ("state",)},
    {"id": "classification_band", "label": "Classification band", "paths": ("classification_band",)},
    {"id": "standard_band_number", "label": "Standard band number", "paths": ("standard_band_number",)},
    {"id": "canonical_reference_month", "label": "Reference month", "paths": ("canonical_reference_month", "canonical_reference_yyyy_mm")},
    {"id": "closing_at", "label": "Closing date", "paths": ("closing_at", "closing_at_text")},
    {"id": "description", "label": "Description evidence", "paths": ("description_text", "detail_text", "position_description_text")},
]

STAGE1_OPTIONAL_FIELDS = [
    {"id": "source_job_id", "label": "Source job ID", "paths": ("source_job_id", "job_number")},
    {"id": "posted_at", "label": "Posted date", "paths": ("posted_at", "posted_at_text")},
    {"id": "work_type", "label": "Work type", "paths": ("work_type", "employment_status")},
    {"id": "location_text", "label": "Location", "paths": ("location_text", "suburb", "region")},
    {"id": "department", "label": "Department", "paths": ("department", "category")},
    {"id": "advertised_salary", "label": "Advertised salary", "paths": ("advertised_salary_min", "salary_min", "salary_text")},
    {"id": "advertised_salary_max", "label": "Advertised salary maximum", "paths": ("advertised_salary_max", "salary_max")},
    {"id": "advertised_salary_basis", "label": "Advertised salary basis", "paths": ("advertised_salary_basis", "salary_basis", "salary_period")},
    {"id": "enterprise_agreement_salary", "label": "Enterprise Agreement salary", "paths": ("enterprise_agreement_salary_min", "canonical_salary_min")},
    {"id": "enterprise_agreement_salary_basis", "label": "Enterprise Agreement salary basis", "paths": ("enterprise_agreement_salary_basis", "canonical_salary_basis")},
    {"id": "position_description_url", "label": "Position description", "paths": ("position_description_url",)},
    {"id": "apply_url", "label": "Apply URL", "paths": ("apply_url",)},
    {"id": "contact", "label": "Contact", "paths": ("contact_name", "contact_email", "contact_phone")},
    {"id": "checks_required", "label": "Checks required", "paths": ("checks_required",)},
]


COMPLETION_ACTION_DEFINITIONS = {
    "governed": {
        "label": "Governed",
        "description": "Band 1-8 evidence is already available on the canonical job record.",
        "priority": 90,
    },
    "confirm_inferred_band": {
        "label": "Confirm inferred band",
        "description": "The advertised salary maps to a governed band; keep the row visible for confirmation.",
        "priority": 20,
    },
    "infer_band_from_salary": {
        "label": "Infer band from salary",
        "description": "Use governed pay rows to infer the missing band from an advertised salary.",
        "priority": 25,
    },
    "fill_salary_from_band": {
        "label": "Fill EA salary from band",
        "description": "Use governed pay rows to fill Enterprise Agreement salary where the source states a band.",
        "priority": 30,
    },
    "parse_linked_documents": {
        "label": "Parse linked documents",
        "description": "Fetch position descriptions, PDFs, Word files, and application packs for missing band or salary evidence.",
        "priority": 10,
    },
    "mine_detail_page": {
        "label": "Mine detail page",
        "description": "Improve source-specific detail extraction for roles with no structured band evidence yet.",
        "priority": 40,
    },
    "match_secondary_sources": {
        "label": "Check secondary mirrors",
        "description": "Use sector aggregators to find missing official evidence or alternate application URLs.",
        "priority": 50,
    },
}


@dataclass(frozen=True)
class ListingLink:
    href: str
    text: str


class ListingLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[ListingLink] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        href = attr_map.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = " ".join(" ".join(self._current_text).split())
        self.links.append(ListingLink(href=self._current_href, text=text))
        self._current_href = None
        self._current_text = []


def _requests_get(url: str, **kwargs: Any) -> requests.Response:
    try:
        return requests.get(url, **kwargs)
    except RequestException as error:
        if _is_permission_denied_network_error(error) and os.environ.pop("SSLKEYLOGFILE", None):
            return requests.get(url, **kwargs)
        raise


def _is_permission_denied_network_error(error: BaseException) -> bool:
    if isinstance(error, PermissionError):
        return True
    if "PermissionError(13" in repr(error) or "Permission denied" in str(error):
        return True
    seen: set[int] = set()
    pending: list[BaseException | None] = [error.__cause__, error.__context__]
    while pending:
        nested = pending.pop()
        if nested is None or id(nested) in seen:
            continue
        seen.add(id(nested))
        if isinstance(nested, PermissionError):
            return True
        if "PermissionError(13" in repr(nested) or "Permission denied" in str(nested):
            return True
        pending.extend([nested.__cause__, nested.__context__])
    return False


def fetch_listing_html(url: str, *, timeout: int = 8) -> tuple[str, dict[str, Any]]:
    headers = {"User-Agent": JOB_INTAKE_USER_AGENT}
    verify_used: bool | str = True
    try:
        response = _requests_get(url, headers=headers, timeout=timeout)
    except requests.exceptions.SSLError:
        verify_used = False
        response = _requests_get(url, headers=headers, timeout=timeout, verify=False)
    user_agent_mode = "identified"
    if response.status_code in {403, 406}:
        try:
            response = _requests_get(url, headers=BROWSER_COMPAT_HEADERS, timeout=timeout, verify=verify_used)
            user_agent_mode = "browser_compat"
        except requests.exceptions.SSLError:
            verify_used = False
            response = _requests_get(url, headers=BROWSER_COMPAT_HEADERS, timeout=timeout, verify=False)
            user_agent_mode = "browser_compat"
    if response.status_code == 403 and _is_cloudflare_challenge(response):
        powershell_result = _fetch_with_powershell_browser(url, timeout=timeout)
        if powershell_result:
            return powershell_result
    if _is_aws_waf_challenge(response):
        try:
            response = _requests_get(url, headers=BROWSER_COMPAT_HEADERS, timeout=timeout, verify=verify_used)
            user_agent_mode = "browser_compat"
        except requests.exceptions.SSLError:
            verify_used = False
            response = _requests_get(url, headers=BROWSER_COMPAT_HEADERS, timeout=timeout, verify=False)
            user_agent_mode = "browser_compat"
        if _is_aws_waf_challenge(response):
            powershell_result = _fetch_with_powershell_browser(url, timeout=timeout)
            if powershell_result:
                return powershell_result
            raise requests.HTTPError(f"AWS WAF challenge returned for {url}", response=response)
    response.raise_for_status()
    if response.status_code == 202 and not response.content:
        headers = {**headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        response = _requests_get(url, headers=headers, timeout=timeout, verify=verify_used)
        response.raise_for_status()
        if _is_aws_waf_challenge(response):
            powershell_result = _fetch_with_powershell_browser(url, timeout=timeout)
            if powershell_result:
                return powershell_result
            raise requests.HTTPError(f"AWS WAF challenge returned for {url}", response=response)
    return response.text, {
        "http_status": response.status_code,
        "final_url": response.url,
        "content_type": response.headers.get("content-type"),
        "bytes": len(response.content),
        "ssl_verify": verify_used,
        "user_agent_mode": user_agent_mode,
    }


def fetch_binary_content(url: str, *, timeout: int = 8) -> tuple[bytes, dict[str, Any]]:
    headers = {
        "User-Agent": JOB_INTAKE_USER_AGENT,
        "Accept": (
            "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
            "application/msword,application/octet-stream,*/*;q=0.8"
        ),
    }
    verify_used: bool | str = True
    try:
        response = _requests_get(url, headers=headers, timeout=timeout)
    except requests.exceptions.SSLError:
        verify_used = False
        response = _requests_get(url, headers=headers, timeout=timeout, verify=False)
    user_agent_mode = "identified"
    if response.status_code in {403, 406}:
        browser_headers = {
            **BROWSER_COMPAT_HEADERS,
            "Accept": (
                "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
                "application/msword,application/octet-stream,text/html,*/*;q=0.8"
            ),
        }
        try:
            response = _requests_get(url, headers=browser_headers, timeout=timeout, verify=verify_used)
        except requests.exceptions.SSLError:
            verify_used = False
            response = _requests_get(url, headers=browser_headers, timeout=timeout, verify=False)
        user_agent_mode = "browser_compat"
    response.raise_for_status()
    return response.content, {
        "http_status": response.status_code,
        "final_url": response.url,
        "content_type": response.headers.get("content-type"),
        "bytes": len(response.content),
        "ssl_verify": verify_used,
        "user_agent_mode": user_agent_mode,
    }


def _is_cloudflare_challenge(response: requests.Response) -> bool:
    return (
        response.headers.get("cf-mitigated", "").lower() == "challenge"
        or "Just a moment..." in response.text[:1000]
    )


def _is_aws_waf_challenge(response: requests.Response) -> bool:
    body = response.text[:5000] if response.text else ""
    return (
        response.status_code == 202
        and (
            "window.awsWafCookieDomainList" in body
            or "window.gokuProps" in body
            or "aws-waf-token" in body.lower()
        )
    )


def _fetch_with_powershell_browser(url: str, *, timeout: int) -> tuple[str, dict[str, Any]] | None:
    safe_url = url.replace("'", "''")
    safe_timeout = max(1, int(timeout))
    script = rf"""
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$targetUrl = '{safe_url}'
$timeoutSeconds = {safe_timeout}
$headerSets = @(
  @{{}},
  @{{ 'User-Agent' = 'Mozilla/5.0' }},
  @{{ 'User-Agent' = 'Googlebot/2.1 (+http://www.google.com/bot.html)' }},
  @{{
    'User-Agent' = 'Mozilla/5.0 AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    'Accept-Language' = 'en-AU,en;q=0.9'
    'Accept-Encoding' = 'gzip, deflate, br'
    'Referer' = 'https://www.google.com/'
  }}
)
$response = $null
foreach ($headers in $headerSets) {{
  try {{
    $response = Invoke-WebRequest -Uri $targetUrl -Headers $headers -TimeoutSec $timeoutSeconds -UseBasicParsing
    break
  }} catch {{}}
}}
if ($null -eq $response) {{ exit 1 }}
@{{
  status_code = [int]$response.StatusCode
  final_url = $response.BaseResponse.ResponseUri.AbsoluteUri
  content_type = [string]$response.Headers['Content-Type']
  content = [string]$response.Content
}} | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout + 5,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None
    content = payload.get("content") or ""
    status_code = int(payload.get("status_code") or 0)
    if status_code >= 400 or not content:
        return None
    return content, {
        "http_status": status_code,
        "final_url": payload.get("final_url") or url,
        "content_type": payload.get("content_type"),
        "bytes": len(content.encode("utf-8", errors="ignore")),
        "ssl_verify": "powershell",
        "user_agent_mode": "powershell_browser_compat",
    }


def extract_job_summaries_from_listing(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    structured_jobs = _extract_opencities_job_list_jobs(source, html)
    if structured_jobs:
        return structured_jobs
    parser = ListingLinkParser()
    parser.feed(html or "")
    listing_url = source.get("listing_url") or source.get("official_careers_entry_url") or ""
    platform = source.get("platform_family") or "unknown_official"
    jobs_by_url: dict[str, dict[str, Any]] = {}
    for link in parser.links:
        absolute_url = canonicalize_job_url(_normalize_job_detail_url(platform, urljoin(listing_url, link.href)))
        if not _looks_like_job_detail_url(platform, source, absolute_url):
            continue
        explicit_title = _clean_job_title(link.text)
        title = explicit_title or _title_from_url(absolute_url)
        parse_confidence = "listing_link" if explicit_title else "url_slug"
        if _is_non_job_navigation_link(platform, title, absolute_url):
            continue
        if absolute_url in jobs_by_url:
            if explicit_title and jobs_by_url[absolute_url].get("parse_confidence") == "url_slug":
                jobs_by_url[absolute_url]["job_title"] = explicit_title
                jobs_by_url[absolute_url]["parse_confidence"] = "listing_link"
            continue
        jobs_by_url[absolute_url] = {
            "job_uid": _job_uid(source, absolute_url),
            "job_title": title,
            "job_url": absolute_url,
            "source_job_id": _source_job_id(platform, absolute_url),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": platform,
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": listing_url,
            "observed_status": "open_candidate",
            "parse_confidence": parse_confidence,
        }
    return list(jobs_by_url.values())


def extract_attachment_links_from_html(html: str, base_url: str) -> list[dict[str, Any]]:
    parser = ListingLinkParser()
    parser.feed(html or "")
    attachments_by_url: dict[str, dict[str, Any]] = {}
    for link in parser.links:
        absolute_url = _normalize_document_url(urljoin(base_url, unescape(link.href)), base_url)
        if not _looks_like_job_attachment_link(link.text, absolute_url):
            continue
        attachments_by_url[absolute_url] = {
            "url": absolute_url,
            "label": normalize_whitespace(link.text) or _attachment_label_from_url(absolute_url),
            "kind": _attachment_kind(link.text, absolute_url),
            "content_type": _document_content_type_hint(absolute_url),
        }
    for document_url in _embedded_document_urls(html, base_url):
        attachments_by_url.setdefault(document_url, {
            "url": document_url,
            "label": _attachment_label_from_url(document_url),
            "kind": _attachment_kind("", document_url),
            "content_type": _document_content_type_hint(document_url),
        })
    return list(attachments_by_url.values())


def extract_pdf_text(pdf_bytes: bytes, *, max_pages: int = 6, max_chars: int = 20000) -> str:
    if not pdf_bytes:
        return ""
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""
    try:
        parts: list[str] = []
        for index in range(min(max_pages, document.page_count)):
            parts.append(document.load_page(index).get_text("text"))
            if len(" ".join(parts)) >= max_chars:
                break
        return normalize_whitespace(" ".join(parts))[:max_chars]
    finally:
        document.close()


def extract_docx_text(docx_bytes: bytes, *, max_chars: int = 20000) -> str:
    if not docx_bytes:
        return ""
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
            xml_names = [
                "word/document.xml",
                *sorted(name for name in archive.namelist() if re.match(r"word/(?:header|footer)\d*\.xml$", name)),
            ]
            parts: list[str] = []
            for name in xml_names:
                try:
                    root = ET.fromstring(archive.read(name))
                except Exception:
                    continue
                for node in root.iter():
                    tag = node.tag.rsplit("}", 1)[-1]
                    if tag == "t" and node.text:
                        parts.append(node.text)
                    elif tag in {"p", "tr", "tbl"}:
                        parts.append(" ")
                    if len(" ".join(parts)) >= max_chars:
                        break
                if len(" ".join(parts)) >= max_chars:
                    break
            return normalize_whitespace(" ".join(parts))[:max_chars]
    except Exception:
        return ""


def extract_document_text(
    document_bytes: bytes,
    *,
    content_type: str = "",
    url: str = "",
) -> tuple[str, str]:
    if _bytes_look_like_pdf(document_bytes, content_type) or _url_looks_like_pdf(url):
        return extract_pdf_text(document_bytes), "pdf"
    if _bytes_look_like_docx(document_bytes, content_type) or _url_looks_like_docx(url):
        return extract_docx_text(document_bytes), "docx"
    return "", "unknown"


def enrich_job_from_detail_page(
    job: dict[str, Any],
    source: dict[str, Any],
    detail_html: str,
    *,
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]] | None = None,
    attachment_limit: int = 2,
) -> dict[str, Any]:
    detail_url = job.get("job_url") or source.get("listing_url") or ""
    detail_text = html_to_text(detail_html)
    attachments = extract_attachment_links_from_html(detail_html, detail_url)
    enriched = dict(job)
    if detail_text:
        enriched["detail_text"] = detail_text
        enriched.setdefault("detail_text_source", "detail_page")
    if attachments:
        enriched["attachments"] = attachments
        pd_attachment = next((item for item in attachments if item.get("kind") == "position_description"), attachments[0])
        enriched["position_description_url"] = pd_attachment.get("url")

    if not binary_fetcher or not attachments:
        return enriched

    attachment_texts: list[str] = []
    attachment_text_sources: list[str] = []
    attachment_results: list[dict[str, Any]] = []
    for attachment in attachments[:max(0, attachment_limit)]:
        attachment_url = str(attachment.get("url") or "")
        if not attachment_url or not _should_fetch_attachment(attachment):
            continue
        result = dict(attachment)
        try:
            document_bytes, fetch_meta = binary_fetcher(attachment_url)
            content_type = str(fetch_meta.get("content_type") or result.get("content_type") or "")
            final_url = str(fetch_meta.get("final_url") or attachment_url)
            document_text, document_kind = extract_document_text(
                document_bytes,
                content_type=content_type,
                url=final_url,
            )
            text_source = _document_text_source(attachment, document_kind)
            result.update({
                "http_status": fetch_meta.get("http_status"),
                "final_url": final_url,
                "content_type": content_type or None,
                "bytes": fetch_meta.get("bytes") or len(document_bytes),
                "document_kind": document_kind,
                "text_chars": len(document_text),
                "parse_status": "parsed" if document_text else "no_text",
            })
            if document_text:
                attachment_texts.append(document_text)
                attachment_text_sources.append(text_source)
                if attachment.get("kind") == "position_description" and not enriched.get("position_description_text"):
                    enriched["position_description_text"] = document_text
                    enriched["position_description_text_source"] = text_source
                    enriched["position_description_excerpt"] = document_text[:800]
        except Exception as error:
            result.update({
                "parse_status": "failed",
                "error": str(error),
            })
        attachment_results.append(result)
    if attachment_results:
        enriched["attachments"] = attachment_results
    if attachment_texts:
        attachment_text = normalize_whitespace(" ".join(attachment_texts))
        attachment_text_source = _combined_document_text_source(attachment_text_sources)
        enriched["attachment_text"] = attachment_text
        enriched["attachment_text_source"] = attachment_text_source
        enriched.setdefault("position_description_text", attachment_text)
        enriched.setdefault("position_description_text_source", attachment_text_source)
        enriched.setdefault("position_description_excerpt", attachment_text[:800])
    return enriched


def job_intake_scrape_preview(
    *,
    source_limit: int = 10,
    job_limit: int = 50,
    timeout: int = 8,
    max_workers: int = 3,
    registry_payload: dict[str, Any] | None = None,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]] | None = None,
    pay_table_rows: list[dict[str, Any]] | None = None,
    enrich_details: bool = True,
    detail_job_limit: int = 1000,
    enrich_attachments: bool = False,
    attachment_job_limit: int = 1000,
    resolve_missing_documents: bool = True,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    ready_sources = [
        row for row in registry.get("rows", [])
        if row.get("monitoring_status") == "ready" and row.get("listing_url")
    ]
    ready_sources = sorted(ready_sources, key=lambda row: (row.get("poll_tier") or "Z", row.get("council_name") or ""))
    if source_limit > 0:
        ready_sources = ready_sources[:source_limit]
    fetch = fetcher or (lambda url: fetch_listing_html(url, timeout=timeout))
    fetch_binary = binary_fetcher or (lambda url: fetch_binary_content(url, timeout=timeout))
    jobs: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    workers = max(1, min(max_workers, len(ready_sources) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_source, source, fetch): source for source in ready_sources}
        for future in as_completed(futures):
            result = future.result()
            source_results.append(result["source_result"])
            jobs.extend(result["jobs"])
    jobs = _dedupe_jobs(jobs)
    jobs = [normalize_council_job_record({**job, "fetched_at": job.get("fetched_at") or fetched_at}) for job in jobs]
    detail_enrichment = {
        "attempted": 0,
        "succeeded": 0,
        "details_parsed": 0,
        "document_attempted": 0,
        "document_succeeded": 0,
        "documents_parsed": 0,
    }
    if enrich_details or enrich_attachments:
        jobs, detail_enrichment = _enrich_jobs_from_detail_pages(
            jobs,
            fetcher=fetch,
            binary_fetcher=fetch_binary,
            detail_job_limit=detail_job_limit,
            attachment_job_limit=attachment_job_limit,
            max_workers=workers,
            fetch_linked_documents=enrich_attachments or resolve_missing_documents,
        )
        jobs = [normalize_council_job_record({**job, "fetched_at": job.get("fetched_at") or fetched_at}) for job in jobs]
    if pay_table_rows:
        jobs = [enrich_job_with_pay_rows(job, pay_table_rows) for job in jobs]
    else:
        jobs = [normalize_council_job_record(job) for job in jobs]
    scoped_jobs = [job for job in jobs if job.get("governance_status") != "auto_excluded"]
    excluded_jobs = len(jobs) - len(scoped_jobs)
    jobs = [
        _annotate_completion_action(job, pay_table_rows_available=bool(pay_table_rows))
        for job in scoped_jobs
    ]
    jobs = sorted(jobs, key=lambda row: (row.get("council_name") or "", row.get("job_title") or ""))
    if job_limit > 0:
        jobs = jobs[:job_limit]
    parsed_sources = sum(1 for item in source_results if item.get("parsed_jobs", 0) > 0)
    failed_sources = sum(1 for item in source_results if item.get("status") == "failed")
    councils_with_jobs = len({
        job.get("short_name") or job.get("council_name")
        for job in jobs
        if job.get("short_name") or job.get("council_name")
    })
    completion_actions = _completion_actions_for_jobs(jobs)
    completion_summary = _completion_summary(jobs)
    return {
        "set_id": "job_intake_scrape_preview",
        "label": "Job Intake Scrape Preview",
        "fetched_at": fetched_at,
        "scope": {
            "source_policy": "official_ready_sources_only",
            "job_scope_policy": "standard_band_1_to_8_or_needs_band_review",
            "pay_table_enrichment": "enabled" if pay_table_rows else "not_available",
            "source_limit": source_limit,
            "job_limit": job_limit,
            "timeout_seconds": timeout,
            "max_workers": workers,
            "detail_page_enrichment": "enabled" if enrich_details or enrich_attachments else "disabled",
            "linked_document_enrichment": "all_linked_documents" if enrich_attachments else ("missing_governance_only" if resolve_missing_documents else "disabled"),
        },
        "tier_explainer": POLL_TIER_EXPLAINER,
        "summary": {
            "sources_attempted": len(source_results),
            "sources_with_jobs": parsed_sources,
            "sources_failed": failed_sources,
            "jobs": len(jobs),
            "councils_with_jobs": councils_with_jobs,
            "standard_band_1_to_8_jobs": sum(1 for job in jobs if job.get("is_standard_band_1_to_8")),
            "jobs_needing_band_review": sum(1 for job in jobs if job.get("governance_status") in {"needs_band_review", "needs_band_confirmation"}),
            **completion_summary,
            "jobs_excluded_by_scope": excluded_jobs,
            "pay_table_rows_available": len(pay_table_rows or []),
            "detail_page_enrichment_attempted": detail_enrichment["attempted"],
            "detail_page_enrichment_succeeded": detail_enrichment["succeeded"],
            "detail_pages_parsed": detail_enrichment["details_parsed"],
            "linked_document_enrichment_attempted": detail_enrichment["document_attempted"],
            "linked_document_enrichment_succeeded": detail_enrichment["document_succeeded"],
            "linked_documents_parsed": detail_enrichment["documents_parsed"],
            "ready_sources_available": len([
                row for row in registry.get("rows", [])
                if row.get("monitoring_status") == "ready" and row.get("listing_url")
            ]),
        },
        "completion_actions": completion_actions,
        "rows": jobs,
        "source_results": sorted(source_results, key=lambda row: (row.get("poll_tier") or "Z", row.get("council_name") or "")),
    }


def job_intake_wide_fetch_preview(
    *,
    source_limit: int = 0,
    job_limit: int = 0,
    timeout: int = 8,
    max_workers: int = 8,
    registry_payload: dict[str, Any] | None = None,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]] | None = None,
    pay_table_rows: list[dict[str, Any]] | None = None,
    enrich_details: bool = True,
    detail_job_limit: int = 1000,
    enrich_attachments: bool = False,
    attachment_job_limit: int = 1000,
    resolve_missing_documents: bool = True,
    candidate_limit_per_council: int = 12,
    candidate_priority_limit: int = 3,
    include_generated_candidates: bool = True,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    wide_sources = _wide_fetch_source_rows(
        registry,
        candidate_limit_per_council=candidate_limit_per_council,
        candidate_priority_limit=candidate_priority_limit,
        include_generated_candidates=include_generated_candidates,
    )
    payload = job_intake_scrape_preview(
        source_limit=source_limit,
        job_limit=job_limit,
        timeout=timeout,
        max_workers=max_workers,
        registry_payload={**registry, "rows": wide_sources},
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
        pay_table_rows=pay_table_rows,
        enrich_details=enrich_details,
        detail_job_limit=detail_job_limit,
        enrich_attachments=enrich_attachments,
        attachment_job_limit=attachment_job_limit,
        resolve_missing_documents=resolve_missing_documents,
    )
    generated_sources = [source for source in wide_sources if source.get("source_role") == "generated_endpoint_candidate"]
    verified_sources = [source for source in wide_sources if source.get("source_role") != "generated_endpoint_candidate"]
    payload["set_id"] = "job_intake_wide_fetch_preview"
    payload["label"] = "Job Intake Wide Fetch Preview"
    payload["source_payload_set_id"] = "job_intake_wide_fetch_preview"
    scope = dict(payload.get("scope") or {})
    scope.update({
        "source_policy": "official_ready_sources_plus_generated_vendor_endpoint_candidates",
        "wide_fetch": "enabled",
        "candidate_limit_per_council": candidate_limit_per_council,
        "candidate_priority_limit": candidate_priority_limit,
        "generated_candidate_sources": len(generated_sources),
        "verified_ready_sources": len(verified_sources),
    })
    payload["scope"] = scope
    summary = dict(payload.get("summary") or {})
    summary.update({
        "wide_sources_available": len(wide_sources),
        "verified_ready_sources": len(verified_sources),
        "generated_candidate_sources": len(generated_sources),
    })
    payload["summary"] = summary
    return payload


def load_job_intake_snapshot(
    *,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    path = snapshot_path or JOB_INTAKE_SNAPSHOT_PATH
    if not path.exists():
        return _empty_job_intake_snapshot()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            **_empty_job_intake_snapshot(),
            "snapshot_status": "unreadable",
        }
    return _as_job_intake_snapshot(payload, saved_at=payload.get("saved_at"))


def save_job_intake_snapshot(
    payload: dict[str, Any],
    *,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    path = snapshot_path or JOB_INTAKE_SNAPSHOT_PATH
    snapshot = _as_job_intake_snapshot(payload, saved_at=datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return snapshot


def load_checked_job_accumulator(
    *,
    accumulator_path: Path | None = None,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = accumulator_path or JOB_INTAKE_ACCUMULATOR_PATH
    if not path.exists():
        return _empty_checked_job_accumulator(registry_payload=registry_payload)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            **_empty_checked_job_accumulator(registry_payload=registry_payload),
            "accumulator_status": "unreadable",
        }
    return _as_checked_job_accumulator(payload, registry_payload=registry_payload)


def save_checked_job_accumulator(
    payload: dict[str, Any],
    *,
    accumulator_path: Path | None = None,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = accumulator_path or JOB_INTAKE_ACCUMULATOR_PATH
    accumulator = _as_checked_job_accumulator(payload, registry_payload=registry_payload)
    accumulator["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(accumulator, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return accumulator


def accumulate_checked_jobs_from_payload(
    payload: dict[str, Any],
    *,
    accumulator_path: Path | None = None,
    registry_payload: dict[str, Any] | None = None,
    source_kind: str = "official",
    source_label: str | None = None,
    mark_missing_historical: bool = False,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    observed_at = str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat())
    source_payload_set_id = str(payload.get("source_payload_set_id") or payload.get("set_id") or "job_payload")
    payload_rows = payload.get("rows") or payload.get("jobs") or []
    run_seed = f"{source_payload_set_id}|{source_kind}|{observed_at}|{len(payload_rows)}"
    run_id = hashlib.sha1(run_seed.encode("utf-8")).hexdigest()[:16]
    accumulator = load_checked_job_accumulator(
        accumulator_path=accumulator_path,
        registry_payload=registry,
    )
    rows_by_key = {
        str(row.get("dedupe_key")): dict(row)
        for row in accumulator.get("rows", [])
        if row.get("dedupe_key")
    }
    relaxed_index = {
        relaxed_key: key
        for key, row in rows_by_key.items()
        if (relaxed_key := _relaxed_accumulator_key(row))
    }
    reject_summary: dict[str, int] = dict(accumulator.get("reject_summary") or {})
    run_rejects: dict[str, int] = {}
    accepted_keys: set[str] = set()
    new_rows = 0
    updated_rows = 0
    for raw_job in payload_rows:
        job_for_check = dict(raw_job)
        needs_payload_timestamp = not any(job_for_check.get(key) for key in (
            "canonical_reference_date",
            "canonical_reference_month",
            "canonical_reference_yyyy_mm",
            "posted_at",
            "posted_at_text",
            "closing_at",
            "closing_at_text",
            "fetched_at",
            "source_fetched_at",
        ))
        if needs_payload_timestamp:
            job_for_check["fetched_at"] = observed_at
            job_for_check["source_fetched_at"] = observed_at
        checked_row, reject_reason = _checked_accumulator_row(
            job_for_check,
            observed_at=observed_at,
            run_id=run_id,
            source_kind=source_kind,
            source_label=source_label or source_payload_set_id,
            registry_payload=registry,
        )
        if not checked_row:
            reason = reject_reason or "not_classified"
            reject_summary[reason] = reject_summary.get(reason, 0) + 1
            run_rejects[reason] = run_rejects.get(reason, 0) + 1
            continue
        dedupe_key = str(checked_row["dedupe_key"])
        relaxed_key = _relaxed_accumulator_key(checked_row)
        relaxed_existing_key = relaxed_index.get(relaxed_key) if relaxed_key else None
        if (
            relaxed_existing_key
            and relaxed_existing_key != dedupe_key
            and relaxed_existing_key in rows_by_key
            and _should_relaxed_merge_accumulator_rows(rows_by_key[relaxed_existing_key], checked_row)
        ):
            merged = _merge_checked_accumulator_row(rows_by_key[relaxed_existing_key], checked_row)
            merged_key = str(merged.get("dedupe_key") or relaxed_existing_key)
            if merged_key != relaxed_existing_key:
                rows_by_key.pop(relaxed_existing_key, None)
            rows_by_key[merged_key] = merged
            relaxed_index[relaxed_key] = merged_key
            accepted_keys.add(merged_key)
            updated_rows += 1
            continue
        accepted_keys.add(dedupe_key)
        if dedupe_key in rows_by_key:
            rows_by_key[dedupe_key] = _merge_checked_accumulator_row(
                rows_by_key[dedupe_key],
                checked_row,
            )
            if relaxed_key:
                relaxed_index[relaxed_key] = str(rows_by_key[dedupe_key].get("dedupe_key") or dedupe_key)
            updated_rows += 1
        else:
            rows_by_key[dedupe_key] = checked_row
            if relaxed_key and relaxed_key not in relaxed_index:
                relaxed_index[relaxed_key] = dedupe_key
            new_rows += 1
    if mark_missing_historical and source_kind == "official":
        for key, row in rows_by_key.items():
            if key in accepted_keys:
                continue
            source_kinds = set(row.get("source_kinds_seen") or [])
            if "official" not in source_kinds:
                continue
            row["observed_status"] = "historical_not_seen_latest"
            row["last_absent_at"] = observed_at
    run_record = {
        "run_id": run_id,
        "source_payload_set_id": source_payload_set_id,
        "source_kind": source_kind,
        "source_label": source_label or source_payload_set_id,
        "observed_at": observed_at,
        "jobs_seen": len(payload_rows),
        "jobs_accumulated": len(accepted_keys),
        "jobs_added": new_rows,
        "jobs_updated": updated_rows,
        "jobs_rejected": sum(run_rejects.values()),
        "reject_summary": run_rejects,
    }
    accumulator.update({
        "accumulator_exists": True,
        "accumulator_status": "ready",
        "updated_at": observed_at,
        "latest_run_id": run_id,
        "latest_official_run_id": run_id if source_kind == "official" else accumulator.get("latest_official_run_id"),
        "latest_secondary_run_id": run_id if source_kind == "secondary" else accumulator.get("latest_secondary_run_id"),
        "reject_summary": reject_summary,
        "runs": [run_record, *(accumulator.get("runs") or [])][:30],
        "rows": sorted(
            rows_by_key.values(),
            key=lambda row: (
                str(row.get("canonical_reference_month") or ""),
                str(row.get("council_name") or row.get("short_name") or ""),
                str(row.get("job_title") or ""),
            ),
            reverse=True,
        ),
    })
    return save_checked_job_accumulator(
        accumulator,
        accumulator_path=accumulator_path,
        registry_payload=registry,
    )


def accumulate_checked_jobs_from_snapshot(
    *,
    snapshot_path: Path | None = None,
    accumulator_path: Path | None = None,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = load_job_intake_snapshot(snapshot_path=snapshot_path)
    if not snapshot.get("snapshot_exists"):
        accumulator = load_checked_job_accumulator(
            accumulator_path=accumulator_path,
            registry_payload=registry_payload,
        )
        accumulator["last_message"] = "No saved intake snapshot is available to accumulate."
        return accumulator
    return accumulate_checked_jobs_from_payload(
        snapshot,
        accumulator_path=accumulator_path,
        registry_payload=registry_payload,
        source_kind="official",
        source_label="saved_intake_snapshot",
        mark_missing_historical=True,
    )


def refresh_checked_job_accumulator(
    *,
    source_limit: int = 0,
    job_limit: int = 0,
    timeout: int = 8,
    max_workers: int = 8,
    pay_table_rows: list[dict[str, Any]] | None = None,
    enrich_details: bool = True,
    detail_job_limit: int = 1000,
    enrich_attachments: bool = False,
    attachment_job_limit: int = 1000,
    resolve_missing_documents: bool = True,
    include_secondary: bool = True,
    secondary_job_limit: int = 0,
    wide_fetch: bool = True,
    candidate_limit_per_council: int = 12,
    candidate_priority_limit: int = 3,
    snapshot_path: Path | None = None,
    accumulator_path: Path | None = None,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    if wide_fetch:
        snapshot = save_job_intake_snapshot(
            job_intake_wide_fetch_preview(
                source_limit=source_limit,
                job_limit=job_limit,
                timeout=timeout,
                max_workers=max_workers,
                registry_payload=registry,
                pay_table_rows=pay_table_rows,
                enrich_details=enrich_details,
                detail_job_limit=detail_job_limit,
                enrich_attachments=enrich_attachments,
                attachment_job_limit=attachment_job_limit,
                resolve_missing_documents=resolve_missing_documents,
                candidate_limit_per_council=candidate_limit_per_council,
                candidate_priority_limit=candidate_priority_limit,
            ),
            snapshot_path=snapshot_path,
        )
    else:
        snapshot = refresh_job_intake_snapshot(
            source_limit=source_limit,
            job_limit=job_limit,
            timeout=timeout,
            max_workers=max_workers,
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=detail_job_limit,
            enrich_attachments=enrich_attachments,
            attachment_job_limit=attachment_job_limit,
            resolve_missing_documents=resolve_missing_documents,
            snapshot_path=snapshot_path,
        )
    accumulator = accumulate_checked_jobs_from_payload(
        snapshot,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
        source_label="wide_official_vendor_refresh" if wide_fetch else "aggressive_official_refresh",
        mark_missing_historical=True,
    )
    secondary_payload: dict[str, Any] | None = None
    if include_secondary:
        secondary_payload = job_intake_secondary_preview(
            source_limit=0,
            job_limit=secondary_job_limit,
            timeout=timeout,
            max_workers=max(3, min(max_workers, 10)),
            registry_payload=registry,
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=min(detail_job_limit, 1000),
            expand_sector_board_council_pages=True,
        )
        secondary_payload = save_job_intake_snapshot(
            secondary_payload,
            snapshot_path=JOB_INTAKE_SECONDARY_SNAPSHOT_PATH,
        )
        accumulator = accumulate_checked_jobs_from_payload(
            secondary_payload,
            accumulator_path=accumulator_path,
            registry_payload=registry,
            source_kind="secondary",
            source_label="secondary_sector_sources",
            mark_missing_historical=False,
        )
    accumulator["refresh_summary"] = {
        "official": snapshot.get("summary") or {},
        "secondary": secondary_payload.get("summary") if secondary_payload else None,
    }
    return accumulator


def refresh_job_intake_snapshot(
    *,
    source_limit: int = 0,
    job_limit: int = 500,
    timeout: int = 8,
    max_workers: int = 8,
    pay_table_rows: list[dict[str, Any]] | None = None,
    enrich_details: bool = True,
    detail_job_limit: int = 1000,
    enrich_attachments: bool = False,
    attachment_job_limit: int = 1000,
    resolve_missing_documents: bool = True,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    payload = job_intake_scrape_preview(
        source_limit=source_limit,
        job_limit=job_limit,
        timeout=timeout,
        max_workers=max_workers,
        pay_table_rows=pay_table_rows,
        enrich_details=enrich_details,
        detail_job_limit=detail_job_limit,
        enrich_attachments=enrich_attachments,
        attachment_job_limit=attachment_job_limit,
        resolve_missing_documents=resolve_missing_documents,
    )
    return save_job_intake_snapshot(payload, snapshot_path=snapshot_path)


def job_pipeline_stage1_payload(
    *,
    snapshot_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = snapshot_payload or load_job_intake_snapshot()
    rows = [
        _stage1_pipeline_row({**job, "fetched_at": job.get("fetched_at") or snapshot.get("fetched_at")})
        for job in snapshot.get("rows", [])
        if _job_can_enter_stage1(job)
    ]
    required_fields_total = len(rows) * len(STAGE1_REQUIRED_FIELDS)
    required_fields_present = sum(row["required_fields_present"] for row in rows)
    optional_fields_total = len(rows) * len(STAGE1_OPTIONAL_FIELDS)
    optional_fields_present = sum(row["optional_fields_present"] for row in rows)
    missing_counts: dict[str, int] = {}
    for row in rows:
        for field_id in row["missing_required_fields"]:
            missing_counts[field_id] = missing_counts.get(field_id, 0) + 1
    return {
        "set_id": "job_pipeline_stage1",
        "label": "Job Pipeline Stage 1",
        "snapshot_exists": bool(snapshot.get("snapshot_exists")),
        "snapshot_status": snapshot.get("snapshot_status") or "unknown",
        "snapshot_saved_at": snapshot.get("saved_at"),
        "source_snapshot_fetched_at": snapshot.get("fetched_at"),
        "stage_policy": {
            "entry_rule": "Band-governed jobs only: standard Band 1-8 evidence must be present.",
            "stage_1_goal": "Fill compulsory fields, derive the reference month, and keep advertised salary separate from Enterprise Agreement salary.",
            "required_fields": STAGE1_REQUIRED_FIELDS,
            "optional_fields": STAGE1_OPTIONAL_FIELDS,
        },
        "summary": {
            "snapshot_jobs": snapshot.get("summary", {}).get("jobs", len(snapshot.get("rows", []))),
            "governed_input_jobs": len(rows),
            "stage1_ready_jobs": sum(1 for row in rows if row["stage1_status"] == "stage1_ready"),
            "stage1_fill_required_jobs": sum(1 for row in rows if row["stage1_status"] == "stage1_fill_required"),
            "required_fields_present": required_fields_present,
            "required_fields_total": required_fields_total,
            "required_completion_rate": _completion_rate(required_fields_present, required_fields_total),
            "optional_fields_present": optional_fields_present,
            "optional_fields_total": optional_fields_total,
            "optional_completion_rate": _completion_rate(optional_fields_present, optional_fields_total),
            "top_missing_required_fields": sorted(
                (
                    {"field": field_id, "count": count}
                    for field_id, count in missing_counts.items()
                ),
                key=lambda item: (-int(item["count"]), str(item["field"])),
            )[:8],
        },
        "rows": sorted(rows, key=lambda row: (
            row["stage1_status"] != "stage1_fill_required",
            -len(row["missing_required_fields"]),
            row.get("council_name") or "",
            row.get("job_title") or "",
        )),
    }


def _empty_job_intake_snapshot() -> dict[str, Any]:
    return {
        "set_id": "job_intake_scrape_snapshot",
        "label": "Job Intake Snapshot",
        "snapshot_exists": False,
        "snapshot_status": "empty",
        "saved_at": None,
        "fetched_at": None,
        "scope": {
            "source_policy": "official_ready_sources_only",
            "refresh_policy": "manual_button_only",
        },
        "summary": {
            "sources_attempted": 0,
            "sources_with_jobs": 0,
            "sources_failed": 0,
            "jobs": 0,
            "councils_with_jobs": 0,
            "standard_band_1_to_8_jobs": 0,
            "jobs_needing_band_review": 0,
            "jobs_excluded_by_scope": 0,
            "pay_table_rows_available": 0,
            "detail_page_enrichment_attempted": 0,
            "detail_page_enrichment_succeeded": 0,
            "linked_document_enrichment_attempted": 0,
            "linked_documents_parsed": 0,
        },
        "tier_explainer": POLL_TIER_EXPLAINER,
        "completion_actions": [],
        "rows": [],
        "source_results": [],
    }


def _as_job_intake_snapshot(payload: dict[str, Any], *, saved_at: str | None) -> dict[str, Any]:
    snapshot = dict(payload or {})
    source_set_id = snapshot.get("source_payload_set_id") or snapshot.get("set_id")
    snapshot["set_id"] = "job_intake_scrape_snapshot"
    snapshot["source_payload_set_id"] = source_set_id
    snapshot["label"] = "Job Intake Snapshot"
    snapshot["snapshot_exists"] = True
    snapshot["snapshot_status"] = snapshot.get("snapshot_status") or "ready"
    snapshot["saved_at"] = saved_at
    scope = dict(snapshot.get("scope") or {})
    scope["refresh_policy"] = "manual_button_only"
    snapshot["scope"] = scope
    snapshot.setdefault("summary", {})
    snapshot.setdefault("rows", [])
    snapshot.setdefault("source_results", [])
    snapshot.setdefault("completion_actions", [])
    snapshot.setdefault("tier_explainer", POLL_TIER_EXPLAINER)
    return snapshot


def _wide_fetch_source_rows(
    registry_payload: dict[str, Any],
    *,
    candidate_limit_per_council: int,
    candidate_priority_limit: int,
    include_generated_candidates: bool,
) -> list[dict[str, Any]]:
    rows = list(registry_payload.get("rows") or [])
    source_rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def add_source(source: dict[str, Any]) -> None:
        url = canonicalize_job_url(str(source.get("listing_url") or ""))
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        row = dict(source)
        row["listing_url"] = url
        row["monitoring_status"] = "ready"
        row.setdefault("source_role", "verified_official_source")
        source_rows.append(row)

    for row in rows:
        if row.get("monitoring_status") == "ready" and row.get("listing_url"):
            add_source(row)
        entry_url = canonicalize_job_url(str(row.get("official_careers_entry_url") or ""))
        listing_url = canonicalize_job_url(str(row.get("listing_url") or ""))
        if entry_url and entry_url != listing_url:
            add_source({
                **row,
                "platform_family": "unknown_official",
                "listing_url": entry_url,
                "listing_url_confidence": "official_careers_entry_fallback",
                "candidate_pattern_id": "official_careers_entry",
                "candidate_notes": "Official council careers landing page fallback for embedded ATS discovery.",
                "candidate_probe_priority": 1,
                "source_role": "official_careers_entry_fallback",
            })
    if include_generated_candidates:
        per_council_limit = max(0, candidate_limit_per_council)
        priority_limit = max(1, candidate_priority_limit)
        for row in rows:
            candidates = endpoint_discovery_candidates(
                str(row.get("short_name") or row.get("council_name") or ""),
                council_name=row.get("council_name"),
                entry_url=row.get("official_careers_entry_url") or row.get("listing_url"),
            )
            candidates = [
                candidate for candidate in candidates
                if int(candidate.get("probe_priority") or 9) <= priority_limit
            ]
            candidates = sorted(candidates, key=lambda candidate: (
                int(candidate.get("probe_priority") or 9),
                candidate.get("platform_family") or "",
                candidate.get("pattern_id") or "",
                candidate.get("listing_url") or "",
            ))
            if per_council_limit > 0:
                candidates = _diverse_endpoint_candidates(candidates, per_council_limit)
            for candidate in candidates:
                add_source({
                    **row,
                    "platform_family": candidate.get("platform_family") or row.get("platform_family"),
                    "listing_url": candidate.get("listing_url"),
                    "detail_pattern": candidate.get("detail_pattern") or row.get("detail_pattern"),
                    "listing_url_confidence": candidate.get("confidence") or "pattern_probe",
                    "candidate_pattern_id": candidate.get("pattern_id"),
                    "candidate_notes": candidate.get("notes"),
                    "candidate_probe_priority": candidate.get("probe_priority", 9),
                    "source_role": "generated_endpoint_candidate",
                })
    return sorted(source_rows, key=lambda row: (
        0 if row.get("source_role") == "verified_official_source" else 1,
        int(row.get("candidate_probe_priority") or 0),
        row.get("poll_tier") or "Z",
        row.get("short_name") or row.get("council_name") or "",
        row.get("listing_url") or "",
    ))


def _diverse_endpoint_candidates(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0 or len(candidates) <= limit:
        return candidates
    platform_order = [
        "pulse",
        "recruitmenthub",
        "applynow",
        "pageup",
        "aurion_selfservice",
        "bigredsky",
        "smartrecruiters",
        "elmo_talent",
        "adlogic_martianlogic",
        "t1cloud",
        "native_council",
    ]
    remaining = list(candidates)
    selected: list[dict[str, Any]] = []
    while remaining and len(selected) < limit:
        added_this_round = False
        for platform in platform_order:
            if len(selected) >= limit:
                break
            match_index = next(
                (
                    index for index, candidate in enumerate(remaining)
                    if candidate.get("platform_family") == platform
                ),
                None,
            )
            if match_index is None:
                continue
            selected.append(remaining.pop(match_index))
            added_this_round = True
        if not added_this_round:
            selected.append(remaining.pop(0))
    return selected


def _empty_checked_job_accumulator(
    *,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    return _as_checked_job_accumulator({
        "set_id": "checked_job_accumulator",
        "label": "Checked Classified Job Accumulator",
        "accumulator_exists": False,
        "accumulator_status": "empty",
        "saved_at": None,
        "updated_at": None,
        "scope": {
            "entry_rule": "Accumulate jobs only after they have council, title, Band 1-8, and reference month evidence.",
            "dedupe_policy": "council_title_band_month",
            "target_policy": "Capture as many checked jobs as possible, with at least one checked job per council as the coverage sense check.",
            "source_policy": "official_sources_first_secondary_sources_as_gap_signals",
        },
        "summary": {},
        "coverage": {},
        "reject_summary": {},
        "runs": [],
        "rows": [],
    }, registry_payload=registry)


def _as_checked_job_accumulator(
    payload: dict[str, Any],
    *,
    registry_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    rows = [
        dict(row)
        for row in payload.get("rows", [])
        if isinstance(row, dict) and row.get("dedupe_key")
        and not _checked_accumulator_row_rejected(row)
        and _accumulator_council_identity(row, registry).get("is_known_council")
    ]
    rows = _collapse_relaxed_accumulator_duplicates(rows)
    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("canonical_reference_month") or ""),
            str(row.get("council_name") or row.get("short_name") or ""),
            str(row.get("job_title") or ""),
        ),
        reverse=True,
    )
    accumulator = dict(payload or {})
    accumulator["set_id"] = "checked_job_accumulator"
    accumulator["label"] = "Checked Classified Job Accumulator"
    accumulator["accumulator_exists"] = bool(accumulator.get("accumulator_exists") or rows)
    accumulator["accumulator_status"] = accumulator.get("accumulator_status") or ("ready" if rows else "empty")
    accumulator.setdefault("saved_at", None)
    accumulator.setdefault("updated_at", None)
    scope = dict(accumulator.get("scope") or {})
    scope.setdefault("entry_rule", "Accumulate jobs only after they have council, title, Band 1-8, and reference month evidence.")
    scope.setdefault("dedupe_policy", "council_title_band_month")
    scope.setdefault(
        "target_policy",
        "Capture as many checked jobs as possible, with at least one checked job per council as the coverage sense check.",
    )
    scope.setdefault("source_policy", "official_sources_first_secondary_sources_as_gap_signals")
    accumulator["scope"] = scope
    accumulator["rows"] = rows
    accumulator["runs"] = list(accumulator.get("runs") or [])[:30]
    accumulator["reject_summary"] = dict(accumulator.get("reject_summary") or {})
    accumulator["coverage"] = _checked_accumulator_coverage(rows, registry)
    accumulator["summary"] = _checked_accumulator_summary(rows, accumulator)
    return accumulator


def _checked_accumulator_row_rejected(row: dict[str, Any]) -> bool:
    latest_job = row.get("latest_job") if isinstance(row.get("latest_job"), dict) else {}
    source_family = str(latest_job.get("source_family") or row.get("source_family") or "").lower()
    if source_family == "applynow" and _looks_like_generated_generic_applynow_accumulator_row(row, latest_job):
        return True
    if _looks_like_native_non_job_navigation_accumulator_row(row, latest_job):
        return True
    return False


def _looks_like_native_non_job_navigation_accumulator_row(
    row: dict[str, Any],
    latest_job: dict[str, Any],
) -> bool:
    source_family = str(latest_job.get("source_family") or row.get("source_family") or "")
    title = str(latest_job.get("job_title") or row.get("job_title") or "")
    job_url = str(latest_job.get("job_url") or row.get("job_url") or row.get("canonical_url") or "")
    return _is_non_job_navigation_link(source_family or "unknown_official", title, job_url)


def _looks_like_generated_generic_applynow_accumulator_row(
    row: dict[str, Any],
    latest_job: dict[str, Any],
) -> bool:
    labels = {str(label) for label in row.get("source_labels_seen") or []}
    if "wide_official_vendor_refresh" not in labels:
        return False
    job_url = str(latest_job.get("job_url") or row.get("job_url") or "")
    if _looks_like_generic_applynow_job_url(job_url):
        return True
    source_url = str(latest_job.get("source_url") or row.get("canonical_url") or "")
    return _looks_like_generic_applynow_job_url(source_url)


def _checked_accumulator_summary(
    rows: list[dict[str, Any]],
    accumulator: dict[str, Any],
) -> dict[str, Any]:
    source_kind_sets = [set(row.get("source_kinds_seen") or []) for row in rows]
    current_run_id = accumulator.get("latest_official_run_id") or accumulator.get("latest_run_id")
    return {
        "jobs": len(rows),
        "checked_classified_jobs": len(rows),
        "current_official_jobs": sum(
            1 for row, source_kinds in zip(rows, source_kind_sets)
            if "official" in source_kinds and (
                row.get("last_seen_official_run_id") or row.get("last_seen_run_id")
            ) == current_run_id
        ),
        "historical_jobs": sum(
            1 for row in rows
            if row.get("observed_status") in {"historical_not_seen_latest", "historical_archive"}
        ),
        "secondary_signal_jobs": sum(1 for source_kinds in source_kind_sets if "secondary" in source_kinds),
        "confirmed_band_jobs": sum(1 for row in rows if row.get("classification_confidence") == "confirmed"),
        "inferred_band_jobs": sum(1 for row in rows if row.get("classification_confidence") == "inferred"),
        "councils_with_jobs": len({row.get("short_name") or row.get("council_name") for row in rows if row.get("short_name") or row.get("council_name")}),
        "reference_months": len({row.get("canonical_reference_month") for row in rows if row.get("canonical_reference_month")}),
        "first_seen_at": min((str(row.get("first_seen_at")) for row in rows if row.get("first_seen_at")), default=None),
        "last_seen_at": max((str(row.get("last_seen_at")) for row in rows if row.get("last_seen_at")), default=None),
        "latest_run_jobs_seen": (accumulator.get("runs") or [{}])[0].get("jobs_seen") if accumulator.get("runs") else 0,
        "latest_run_jobs_accumulated": (accumulator.get("runs") or [{}])[0].get("jobs_accumulated") if accumulator.get("runs") else 0,
        "latest_run_jobs_rejected": (accumulator.get("runs") or [{}])[0].get("jobs_rejected") if accumulator.get("runs") else 0,
    }


def _checked_accumulator_coverage(
    rows: list[dict[str, Any]],
    registry_payload: dict[str, Any],
) -> dict[str, Any]:
    registry_rows = registry_payload.get("rows") or []
    known = [
        {
            "short_name": row.get("short_name"),
            "council_name": row.get("council_name"),
            "poll_tier": row.get("poll_tier"),
        }
        for row in registry_rows
        if row.get("short_name") or row.get("council_name")
    ]
    covered_keys = {
        _normalise_accumulator_key(row.get("short_name") or row.get("council_name"))
        for row in rows
        if row.get("short_name") or row.get("council_name")
    }
    missing = [
        row for row in known
        if _normalise_accumulator_key(row.get("short_name") or row.get("council_name")) not in covered_keys
    ]
    target = len(known)
    covered = target - len(missing)
    return {
        "target_councils": target,
        "councils_with_checked_jobs": covered,
        "councils_without_checked_jobs": len(missing),
        "coverage_rate": round((covered / target) * 100) if target else 0,
        "missing_councils": missing,
    }


def _checked_accumulator_row(
    raw_job: dict[str, Any],
    *,
    observed_at: str,
    run_id: str,
    source_kind: str,
    source_label: str,
    registry_payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    job = normalize_council_job_record(raw_job)
    council = _accumulator_council_identity(job, registry_payload)
    title = normalize_whitespace(str(job.get("job_title") or ""))
    band_number = _accumulator_band_number(job)
    reference_month = str(job.get("canonical_reference_month") or job.get("canonical_reference_yyyy_mm") or "").strip()
    if not council["key"]:
        return None, "missing_council"
    if not council.get("is_known_council"):
        return None, "unknown_council"
    if not title:
        return None, "missing_title"
    if _is_non_job_navigation_link(str(job.get("source_family") or "unknown_official"), title, str(job.get("job_url") or "")):
        return None, "non_job_navigation_page"
    if band_number is None:
        return None, "missing_band_1_to_8"
    if not reference_month:
        return None, "missing_reference_month"
    if job.get("governance_status") == "auto_excluded":
        return None, "governance_excluded"
    classification_confidence = "confirmed" if job.get("standard_band_number") else "inferred"
    dedupe_parts = {
        "council": council["key"],
        "title": _normalise_accumulator_key(title),
        "band": str(band_number),
        "month": reference_month,
    }
    dedupe_seed = "|".join(dedupe_parts.values())
    dedupe_key = hashlib.sha1(dedupe_seed.encode("utf-8")).hexdigest()[:20]
    latest_job = {
        key: value
        for key, value in job.items()
        if key not in {"description_html", "detail_text", "position_description_text", "attachment_text"}
    }
    job_url = str(job.get("canonical_url") or job.get("job_url") or "")
    return {
        "dedupe_key": dedupe_key,
        "dedupe_key_parts": dedupe_parts,
        "job_title": title,
        "council_name": council["council_name"],
        "short_name": council["short_name"],
        "classification_band": job.get("classification_band") or f"Band {band_number}",
        "standard_band_number": band_number,
        "classification_confidence": classification_confidence,
        "canonical_reference_month": reference_month,
        "canonical_reference_date": job.get("canonical_reference_date"),
        "canonical_reference_date_source": job.get("canonical_reference_date_source"),
        "job_url": job_url,
        "canonical_url": job.get("canonical_url") or job_url,
        "source_family": job.get("source_family"),
        "source_name": job.get("source_name"),
        "source_job_id": job.get("source_job_id") or job.get("job_number"),
        "source_kind": source_kind,
        "source_kinds_seen": [source_kind],
        "source_labels_seen": [source_label],
        "job_urls_seen": [job_url] if job_url else [],
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "last_seen_run_id": run_id,
        "last_seen_official_at": observed_at if source_kind == "official" else None,
        "last_seen_official_run_id": run_id if source_kind == "official" else None,
        "last_seen_secondary_at": observed_at if source_kind == "secondary" else None,
        "last_seen_secondary_run_id": run_id if source_kind == "secondary" else None,
        "sighting_count": 1,
        "observed_status": _accumulator_observed_status(source_kind),
        "latest_job": latest_job,
    }, None


def _collapse_relaxed_accumulator_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    relaxed_index: dict[str, str] = {}
    for row in rows:
        dedupe_key = str(row.get("dedupe_key") or "")
        if not dedupe_key:
            continue
        relaxed_key = _relaxed_accumulator_key(row)
        existing_key = relaxed_index.get(relaxed_key) if relaxed_key else None
        if (
            existing_key
            and existing_key in rows_by_key
            and existing_key != dedupe_key
            and _should_relaxed_merge_accumulator_rows(rows_by_key[existing_key], row)
        ):
            merged = _merge_checked_accumulator_row(rows_by_key[existing_key], row)
            merged_key = str(merged.get("dedupe_key") or existing_key)
            if merged_key != existing_key:
                rows_by_key.pop(existing_key, None)
            rows_by_key[merged_key] = merged
            relaxed_index[relaxed_key] = merged_key
            continue
        rows_by_key[dedupe_key] = dict(row)
        if relaxed_key and relaxed_key not in relaxed_index:
            relaxed_index[relaxed_key] = dedupe_key
    return list(rows_by_key.values())


def _relaxed_accumulator_key(row: dict[str, Any]) -> str:
    parts = row.get("dedupe_key_parts") if isinstance(row.get("dedupe_key_parts"), dict) else {}
    council = str(parts.get("council") or _normalise_accumulator_key(row.get("short_name") or row.get("council_name"))).strip()
    title = str(parts.get("title") or _normalise_accumulator_key(row.get("job_title"))).strip()
    month = str(parts.get("month") or row.get("canonical_reference_month") or row.get("canonical_reference_yyyy_mm") or "").strip()
    if not (council and title and month):
        return ""
    return "|".join((council, title, month))


def _accumulator_source_kinds(row: dict[str, Any]) -> set[str]:
    kinds = {str(kind) for kind in row.get("source_kinds_seen") or [] if kind}
    if row.get("source_kind"):
        kinds.add(str(row.get("source_kind")))
    return kinds


def _accumulator_urls(row: dict[str, Any]) -> set[str]:
    latest_job = row.get("latest_job") if isinstance(row.get("latest_job"), dict) else {}
    candidates = [
        row.get("job_url"),
        row.get("canonical_url"),
        latest_job.get("job_url"),
        latest_job.get("canonical_url"),
        *(row.get("job_urls_seen") or []),
    ]
    return {str(url).strip() for url in candidates if str(url or "").strip()}


def _should_relaxed_merge_accumulator_rows(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _relaxed_accumulator_key(left) != _relaxed_accumulator_key(right):
        return False
    if _accumulator_urls(left) & _accumulator_urls(right):
        return True
    source_kinds = _accumulator_source_kinds(left) | _accumulator_source_kinds(right)
    return "secondary" in source_kinds


def _accumulator_row_preference(row: dict[str, Any]) -> tuple[int, int, int, str]:
    source_kinds = _accumulator_source_kinds(row)
    official = "official" in source_kinds
    status = str(row.get("observed_status") or "")
    if official and status == "current":
        source_rank = 0
    elif official:
        source_rank = 1
    elif status == "current":
        source_rank = 2
    elif status in {"historical_not_seen_latest", "historical_archive"}:
        source_rank = 3
    else:
        source_rank = 4
    confidence_rank = 0 if row.get("classification_confidence") == "confirmed" else 1
    url_rank = -len(_accumulator_urls(row))
    return (source_rank, confidence_rank, url_rank, str(row.get("last_seen_at") or ""))


def _preferred_accumulator_row(
    left: dict[str, Any],
    right: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    left_rank = _accumulator_row_preference(left)
    right_rank = _accumulator_row_preference(right)
    left_static_rank = left_rank[:3]
    right_static_rank = right_rank[:3]
    if left_static_rank < right_static_rank:
        return left, right
    if right_static_rank < left_static_rank:
        return right, left
    if right_rank[3] >= left_rank[3]:
        return right, left
    return left, right


def _first_timestamp(*values: Any) -> str | None:
    timestamps = sorted(str(value) for value in values if value)
    return timestamps[0] if timestamps else None


def _last_timestamp(*values: Any) -> str | None:
    timestamps = sorted(str(value) for value in values if value)
    return timestamps[-1] if timestamps else None


def _merge_checked_accumulator_row(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    primary, secondary = _preferred_accumulator_row(existing, incoming)
    merged = {**secondary, **primary}
    source_kinds = sorted(set(existing.get("source_kinds_seen") or []) | set(incoming.get("source_kinds_seen") or []))
    source_labels = sorted(set(existing.get("source_labels_seen") or []) | set(incoming.get("source_labels_seen") or []))
    job_urls = sorted(set(existing.get("job_urls_seen") or []) | set(incoming.get("job_urls_seen") or []))
    merged.update({
        "first_seen_at": _first_timestamp(existing.get("first_seen_at"), incoming.get("first_seen_at")),
        "last_seen_at": _last_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at")),
        "sighting_count": int(existing.get("sighting_count") or 0) + int(incoming.get("sighting_count") or 1),
        "source_kinds_seen": source_kinds,
        "source_labels_seen": source_labels,
        "job_urls_seen": [url for url in job_urls if url],
        "last_seen_official_at": _last_timestamp(existing.get("last_seen_official_at"), incoming.get("last_seen_official_at")),
        "last_seen_official_run_id": primary.get("last_seen_official_run_id") or secondary.get("last_seen_official_run_id"),
        "last_seen_secondary_at": _last_timestamp(existing.get("last_seen_secondary_at"), incoming.get("last_seen_secondary_at")),
        "last_seen_secondary_run_id": primary.get("last_seen_secondary_run_id") or secondary.get("last_seen_secondary_run_id"),
    })
    if primary.get("observed_status") == "current" and primary.get("source_kind") == "official":
        merged["observed_status"] = "current"
    elif existing.get("observed_status") == "current" and incoming.get("source_kind") != "official":
        merged["observed_status"] = "current"
    if "official" in source_kinds and incoming.get("source_kind") == "secondary":
        merged["observed_status"] = existing.get("observed_status") or "current"
    return merged


def _accumulator_observed_status(source_kind: str) -> str:
    if source_kind == "official":
        return "current"
    if source_kind == "secondary":
        return "secondary_signal"
    return "historical_archive"


def _accumulator_band_number(job: dict[str, Any]) -> int | None:
    for value in (
        job.get("standard_band_number"),
        job.get("inferred_standard_band_number"),
    ):
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= 8:
            return number
    return None


def _accumulator_council_identity(
    job: dict[str, Any],
    registry_payload: dict[str, Any],
) -> dict[str, Any]:
    lookup = _accumulator_council_lookup(registry_payload)
    raw_candidates = [
        job.get("short_name"),
        job.get("council_name"),
    ]
    for candidate in raw_candidates:
        key = _normalise_accumulator_key(candidate)
        if key and key in lookup:
            return lookup[key]
    short_name = normalize_whitespace(str(job.get("short_name") or ""))
    council_name = normalize_whitespace(str(job.get("council_name") or short_name))
    return {
        "key": _normalise_accumulator_key(short_name or council_name),
        "short_name": short_name or council_name,
        "council_name": council_name or short_name,
        "is_known_council": False,
    }


def _accumulator_council_lookup(registry_payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in registry_payload.get("rows") or []:
        short_name = normalize_whitespace(str(row.get("short_name") or ""))
        council_name = normalize_whitespace(str(row.get("council_name") or short_name))
        identity = {
            "key": _normalise_accumulator_key(short_name or council_name),
            "short_name": short_name or council_name,
            "council_name": council_name or short_name,
            "is_known_council": True,
        }
        for candidate in (short_name, council_name):
            key = _normalise_accumulator_key(candidate)
            if key:
                lookup[key] = identity
    return lookup


def _normalise_accumulator_key(value: Any) -> str:
    text = normalize_whitespace(str(value or "")).lower()
    text = re.sub(r"\b(city|shire|rural|borough|council|city council|shire council)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _job_can_enter_stage1(job: dict[str, Any]) -> bool:
    return bool(job.get("is_standard_band_1_to_8")) and job.get("governance_status") == "auto_included"


def _stage1_pipeline_row(job: dict[str, Any]) -> dict[str, Any]:
    job = normalize_council_job_record(job)
    missing_required = _missing_stage_fields(job, STAGE1_REQUIRED_FIELDS)
    missing_optional = _missing_stage_fields(job, STAGE1_OPTIONAL_FIELDS)
    required_present = len(STAGE1_REQUIRED_FIELDS) - len(missing_required)
    optional_present = len(STAGE1_OPTIONAL_FIELDS) - len(missing_optional)
    return {
        "job_uid": job.get("job_uid"),
        "canonical_url": job.get("canonical_url") or job.get("job_url"),
        "job_url": job.get("job_url"),
        "source_url": job.get("source_url") or job.get("job_url"),
        "source_family": job.get("source_family"),
        "source_job_id": job.get("source_job_id") or job.get("job_number"),
        "council_name": job.get("council_name") or job.get("short_name"),
        "short_name": job.get("short_name"),
        "council_grouping": job.get("council_grouping"),
        "job_title": job.get("job_title"),
        "classification_band": job.get("classification_band"),
        "classification_band_raw": job.get("classification_band_raw"),
        "standard_band_number": job.get("standard_band_number"),
        "classification_band_number": job.get("standard_band_number"),
        "canonical_reference_date": job.get("canonical_reference_date"),
        "canonical_reference_month": job.get("canonical_reference_month"),
        "canonical_reference_yyyy_mm": job.get("canonical_reference_yyyy_mm"),
        "canonical_reference_date_source": job.get("canonical_reference_date_source"),
        "posted_at": job.get("posted_at"),
        "fetched_at": job.get("fetched_at"),
        "closing_at": job.get("closing_at"),
        "work_type": job.get("work_type"),
        "location_text": job.get("location_text"),
        "salary_text": job.get("salary_text"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "salary_period": job.get("salary_period"),
        "salary_basis": job.get("salary_basis"),
        "advertised_salary_text": job.get("advertised_salary_text") or job.get("salary_text"),
        "advertised_salary_min": job.get("advertised_salary_min") or job.get("salary_min"),
        "advertised_salary_max": job.get("advertised_salary_max") or job.get("salary_max"),
        "advertised_salary_currency": job.get("advertised_salary_currency") or job.get("salary_currency"),
        "advertised_salary_period": job.get("advertised_salary_period") or job.get("salary_period"),
        "advertised_salary_basis": job.get("advertised_salary_basis") or job.get("salary_basis"),
        "enterprise_agreement_salary_min": job.get("enterprise_agreement_salary_min") or job.get("canonical_salary_min"),
        "enterprise_agreement_salary_max": job.get("enterprise_agreement_salary_max") or job.get("canonical_salary_max"),
        "enterprise_agreement_salary_currency": job.get("enterprise_agreement_salary_currency") or job.get("canonical_salary_currency"),
        "enterprise_agreement_salary_period": job.get("enterprise_agreement_salary_period") or job.get("canonical_salary_period"),
        "enterprise_agreement_salary_basis": job.get("enterprise_agreement_salary_basis") or job.get("canonical_salary_basis"),
        "enterprise_agreement_weekly_salary_min": job.get("enterprise_agreement_weekly_salary_min") or job.get("canonical_weekly_salary_min"),
        "enterprise_agreement_weekly_salary_max": job.get("enterprise_agreement_weekly_salary_max") or job.get("canonical_weekly_salary_max"),
        "enterprise_agreement_salary_effective_from": job.get("enterprise_agreement_salary_effective_from") or job.get("canonical_salary_effective_from"),
        "enterprise_agreement_salary_effective_to": job.get("enterprise_agreement_salary_effective_to") or job.get("canonical_salary_effective_to"),
        "enterprise_agreement_salary_source": job.get("enterprise_agreement_salary_source") or job.get("canonical_salary_source"),
        "enterprise_agreement_salary_comparator_rows": job.get("enterprise_agreement_salary_comparator_rows") or job.get("canonical_salary_comparator_rows"),
        "salary_enrichment_status": job.get("salary_enrichment_status"),
        "salary_band_validation_status": job.get("salary_band_validation_status"),
        "salary_band_validation": job.get("salary_band_validation"),
        "position_description_url": job.get("position_description_url"),
        "apply_url": job.get("apply_url"),
        "field_sources": job.get("field_sources") or {},
        "pipeline_stage": "stage_1_field_completion",
        "stage1_status": "stage1_ready" if not missing_required else "stage1_fill_required",
        "missing_required_fields": missing_required,
        "missing_optional_fields": missing_optional,
        "required_fields_present": required_present,
        "required_fields_total": len(STAGE1_REQUIRED_FIELDS),
        "required_completion_rate": _completion_rate(required_present, len(STAGE1_REQUIRED_FIELDS)),
        "optional_fields_present": optional_present,
        "optional_fields_total": len(STAGE1_OPTIONAL_FIELDS),
        "optional_completion_rate": _completion_rate(optional_present, len(STAGE1_OPTIONAL_FIELDS)),
        "next_action": "fill_missing_required_fields" if missing_required else "ready_for_stage_1_processing",
    }


def _missing_stage_fields(job: dict[str, Any], field_defs: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for field in field_defs:
        paths = tuple(field.get("paths") or ())
        if not any(_field_has_value(job.get(path)) for path in paths):
            missing.append(str(field.get("id") or paths[0]))
    return missing


def _field_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _completion_rate(present: int, total: int) -> int:
    if total <= 0:
        return 100
    return round((present / total) * 100)


def job_intake_endpoint_resolution_preview(
    *,
    candidate_limit: int = 20,
    job_limit: int = 100,
    timeout: int = 6,
    max_workers: int = 6,
    registry_payload: dict[str, Any] | None = None,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    candidates = _endpoint_candidate_sources(registry)
    if candidate_limit > 0:
        candidates = candidates[:candidate_limit]
    fetch = fetcher or (lambda url: fetch_listing_html(url, timeout=timeout))
    source_results: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    workers = max(1, min(max_workers, len(candidates) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_source, source, fetch): source for source in candidates}
        for future in as_completed(futures):
            result = future.result()
            source_result = result["source_result"]
            source_results.append(source_result)
            if source_result.get("status") == "ok" and source_result.get("parsed_jobs", 0) > 0:
                jobs.extend(result["jobs"])
    jobs = _dedupe_jobs(jobs)
    jobs = sorted(jobs, key=lambda row: (row.get("council_name") or "", row.get("job_title") or ""))
    if job_limit > 0:
        jobs = jobs[:job_limit]
    successful_sources = [
        result for result in source_results
        if result.get("status") == "ok" and result.get("parsed_jobs", 0) > 0
    ]
    successful_sources = sorted(successful_sources, key=lambda row: (row.get("poll_tier") or "Z", row.get("council_name") or ""))
    return {
        "set_id": "job_intake_endpoint_resolution_preview",
        "label": "Job Intake Endpoint Resolution Preview",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "candidate_policy": "pattern_generated_unready_sources",
            "candidate_limit": candidate_limit,
            "job_limit": job_limit,
            "timeout_seconds": timeout,
            "max_workers": workers,
        },
        "summary": {
            "candidates_available": len(_endpoint_candidate_sources(registry)),
            "candidates_checked": len(source_results),
            "sources_resolved": len(successful_sources),
            "jobs": len(jobs),
        },
        "rows": jobs,
        "resolved_sources": successful_sources,
    }


def job_intake_secondary_preview(
    *,
    source_limit: int = 0,
    job_limit: int = 100,
    timeout: int = 8,
    max_workers: int = 3,
    registry_payload: dict[str, Any] | None = None,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]] | None = None,
    pay_table_rows: list[dict[str, Any]] | None = None,
    enrich_details: bool = True,
    detail_job_limit: int = 250,
    expand_sector_board_council_pages: bool = False,
) -> dict[str, Any]:
    registry = registry_payload or council_job_source_registry_payload()
    sources = _secondary_sources_for_scrape(
        registry,
        expand_sector_board_council_pages=expand_sector_board_council_pages,
    )
    if source_limit > 0:
        sources = sources[:source_limit]
    fetch = fetcher or (lambda url: fetch_listing_html(url, timeout=timeout))
    fetch_binary = binary_fetcher or (lambda url: fetch_binary_content(url, timeout=timeout))
    fetched_at = datetime.now(timezone.utc).isoformat()
    jobs: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    workers = max(1, min(max_workers, len(sources) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_secondary_source, source, fetch): source for source in sources}
        for future in as_completed(futures):
            result = future.result()
            source_results.append(result["source_result"])
            jobs.extend(result["jobs"])
    jobs = _dedupe_jobs(jobs)
    jobs = [normalize_council_job_record({**job, "fetched_at": job.get("fetched_at") or fetched_at}) for job in jobs]
    detail_enrichment = {
        "attempted": 0,
        "succeeded": 0,
        "details_parsed": 0,
        "document_attempted": 0,
        "document_succeeded": 0,
        "documents_parsed": 0,
    }
    if enrich_details:
        jobs, detail_enrichment = _enrich_jobs_from_detail_pages(
            jobs,
            fetcher=fetch,
            binary_fetcher=fetch_binary,
            detail_job_limit=detail_job_limit,
            attachment_job_limit=0,
            max_workers=workers,
            fetch_linked_documents=False,
        )
    jobs = _infer_missing_councils_from_job_text(jobs, registry)
    if pay_table_rows:
        jobs = [enrich_job_with_pay_rows(job, pay_table_rows) for job in jobs]
    else:
        jobs = [normalize_council_job_record(job) for job in jobs]
    jobs = [
        _annotate_completion_action(job, pay_table_rows_available=bool(pay_table_rows))
        for job in jobs
    ]
    jobs = sorted(jobs, key=lambda row: (
        row.get("council_name") or "",
        row.get("job_title") or "",
        row.get("source_name") or "",
    ))
    if job_limit > 0:
        jobs = jobs[:job_limit]
    return {
        "set_id": "job_intake_secondary_preview",
        "label": "Job Intake Secondary Source Preview",
        "fetched_at": fetched_at,
        "scope": {
            "source_policy": "secondary_sector_sources_only",
            "canonical_policy": "discovery_and_gap_signal_only",
            "sector_board_council_pages": "expanded" if expand_sector_board_council_pages else "base_sources_only",
            "source_limit": source_limit,
            "job_limit": job_limit,
            "timeout_seconds": timeout,
            "max_workers": workers,
        },
        "summary": {
            "sources_attempted": len(source_results),
            "sources_with_jobs": sum(1 for item in source_results if item.get("parsed_jobs", 0) > 0),
            "sources_failed": sum(1 for item in source_results if item.get("status") == "failed"),
            "jobs": len(jobs),
            "secondary_sources_available": len(sources),
            "councils_seen": len({job.get("council_name") for job in jobs if job.get("council_name")}),
            "standard_band_1_to_8_jobs": sum(1 for job in jobs if job.get("is_standard_band_1_to_8")),
            "classified_band_1_to_8_jobs": sum(1 for job in jobs if _accumulator_band_number(job) is not None),
            "jobs_needing_band_review": sum(1 for job in jobs if job.get("governance_status") in {"needs_band_review", "needs_band_confirmation"}),
            **_completion_summary(jobs),
            "pay_table_rows_available": len(pay_table_rows or []),
            "detail_page_enrichment_attempted": detail_enrichment["attempted"],
            "detail_page_enrichment_succeeded": detail_enrichment["succeeded"],
            "detail_pages_parsed": detail_enrichment["details_parsed"],
        },
        "completion_actions": _completion_actions_for_jobs(jobs),
        "rows": jobs,
        "source_results": sorted(source_results, key=lambda row: row.get("source_name") or ""),
    }


def _endpoint_candidate_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_sources: list[dict[str, Any]] = []
    for row in registry.get("rows", []):
        if row.get("monitoring_status") == "ready":
            continue
        for candidate in row.get("endpoint_candidates") or []:
            candidate_sources.append({
                **row,
                "platform_family": candidate.get("platform_family") or row.get("platform_family"),
                "listing_url": candidate.get("listing_url"),
                "detail_pattern": candidate.get("detail_pattern"),
                "listing_url_confidence": candidate.get("confidence") or "pattern_probe",
                "monitoring_status": "pattern_probe",
                "candidate_pattern_id": candidate.get("pattern_id"),
                "candidate_notes": candidate.get("notes"),
                "candidate_probe_priority": candidate.get("probe_priority", 9),
            })
    return sorted(candidate_sources, key=lambda row: (
        row.get("candidate_probe_priority", 9),
        row.get("platform_family") or "",
        row.get("poll_tier") or "Z",
        row.get("council_name") or "",
        row.get("listing_url") or "",
    ))


def _scrape_source(
    source: dict[str, Any],
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    listing_url = source.get("listing_url") or ""
    base_result = {
        "short_name": source.get("short_name"),
        "council_name": source.get("council_name"),
        "poll_tier": source.get("poll_tier"),
        "platform_family": source.get("platform_family"),
        "listing_url": listing_url,
        "candidate_pattern_id": source.get("candidate_pattern_id"),
        "candidate_notes": source.get("candidate_notes"),
    }
    try:
        html, fetch_meta = fetcher(listing_url)
        jobs = _extract_pulse_jobs_from_listing_api(source, html, fetcher) if source.get("platform_family") == "pulse" else []
        if not jobs and source.get("platform_family") == "smartrecruiters":
            jobs = _extract_smartrecruiters_jobs_from_listing_api(source, html, fetcher)
        if not jobs and source.get("platform_family") == "elmo_talent":
            jobs = _extract_elmo_talent_jobs_from_listing(source, html, fetcher)
        if not jobs and source.get("platform_family") == "aurion_selfservice":
            jobs = _extract_aurion_jobs_from_listing(source, html)
        if not jobs and source.get("platform_family") == "bigredsky":
            jobs = _extract_bigredsky_jobs_from_listing(source, html)
        if not jobs and source.get("platform_family") == "oracle_hcm":
            jobs = _extract_oracle_hcm_jobs_from_listing_api(source, html, fetcher)
        if not jobs:
            jobs = extract_job_summaries_from_listing(source, html)
        embedded_sources = _embedded_listing_sources(source, html)
        if not jobs and embedded_sources:
            for embedded_source in embedded_sources:
                embedded_result = _scrape_source(embedded_source, fetcher)
                jobs.extend(embedded_result.get("jobs") or [])
        source_rejection_reason = _source_rejection_reason(source, html, jobs)
        if source_rejection_reason:
            jobs = []
        jobs = [normalize_council_job_record(job) for job in jobs]
        return {
            "jobs": jobs,
            "source_result": {
                **base_result,
                **fetch_meta,
                "status": "ok",
                "parsed_jobs": len(jobs),
                "embedded_sources_attempted": len(embedded_sources),
                "source_rejection_reason": source_rejection_reason or None,
            },
        }
    except RequestException as error:
        return {
            "jobs": [],
            "source_result": {
                **base_result,
                "status": "failed",
                "parsed_jobs": 0,
                "error": str(error),
            },
        }
    except Exception as error:  # pragma: no cover - defensive parser boundary
        return {
            "jobs": [],
            "source_result": {
                **base_result,
                "status": "failed",
                "parsed_jobs": 0,
                "error": str(error),
            },
        }


def _source_rejection_reason(source: dict[str, Any], html: str, jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return ""
    if (
        source.get("source_role") == "generated_endpoint_candidate"
        and source.get("platform_family") == "applynow"
        and _looks_like_generic_applynow_board(html, jobs)
    ):
        return "generic_applynow_board_not_council_affiliated"
    return ""


def _looks_like_generic_applynow_board(html: str, jobs: list[dict[str, Any]]) -> bool:
    text = html_to_text(html).lower()
    has_generic_shell = (
        "classifications - employment office" in text
        or ("employment office" in text and "classifications" in text)
    )
    if not has_generic_shell:
        return False
    return any(_looks_like_generic_applynow_job_url(str(job.get("job_url") or "")) for job in jobs)


def _looks_like_generic_applynow_job_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if host == "recruitshop.applynow.net.au":
        return True
    return bool(re.search(r"/jobs/(?:ni/)?RS\d+", path, re.I))


def _secondary_source_for_scrape(source: dict[str, Any]) -> dict[str, Any]:
    row = dict(source)
    if row.get("source_family") == "localgovernmentjobs":
        row["url"] = "https://www.localgovernmentjobs.com.au/jobs?state_id=3903"
        row["source_name"] = f"{row.get('source_name')} - Victoria"
    return row


def _secondary_sources_for_scrape(
    registry_payload: dict[str, Any],
    *,
    expand_sector_board_council_pages: bool,
) -> list[dict[str, Any]]:
    sources = [_secondary_source_for_scrape(source) for source in SECONDARY_SOURCES]
    if expand_sector_board_council_pages:
        sources.extend(_careers_at_council_council_page_sources(registry_payload))
        sources.extend(_council_direct_council_page_sources(registry_payload))
        sources.extend(_jora_council_search_sources(registry_payload))
        sources.extend(_local_government_jobs_council_search_sources(registry_payload))
    deduped: dict[str, dict[str, Any]] = {}
    for source in sources:
        url = canonicalize_job_url(str(source.get("url") or ""))
        key = f"{source.get('source_family')}|{url}"
        if key not in deduped:
            deduped[key] = source
    return list(deduped.values())


def _council_direct_council_page_sources(registry_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for row in registry_payload.get("rows") or []:
        council_name = normalize_whitespace(str(row.get("council_name") or row.get("short_name") or ""))
        short_name = normalize_whitespace(str(row.get("short_name") or council_name))
        if not council_name and not short_name:
            continue
        for slug in _council_direct_company_slugs(council_name or short_name, short_name):
            sources.append({
                "source_id": f"council_direct_{_normalise_accumulator_key(short_name).replace(' ', '_')}_{slug.replace('-', '_')}",
                "source_name": f"Council Direct - {council_name or short_name}",
                "source_family": "councildirect",
                "url": f"https://www.councildirect.com.au/jobs?company={slug}",
                "source_priority": 35,
                "best_use": "expanded public-board discovery by council company filter",
                "monitoring_role": "secondary_signal",
                "short_name": short_name,
                "council_name": council_name or short_name,
                "council_grouping": row.get("council_grouping"),
                "poll_tier": row.get("poll_tier"),
            })
    return sources


def _council_direct_company_slugs(council_name: str, short_name: str = "") -> list[str]:
    raw = normalize_whitespace(council_name)
    short = normalize_whitespace(short_name or raw)
    variants: list[str] = []

    def add(value: str) -> None:
        slug = re.sub(r"[^a-z0-9]+", "-", normalize_whitespace(value).lower()).strip("-")
        if slug and slug not in variants:
            variants.append(slug)

    add(raw)
    add(re.sub(r"\bCouncil\b$", "", raw, flags=re.I).strip())
    add(short)
    add(re.sub(r"\bCouncil\b$", "", short, flags=re.I).strip())

    city_match = re.match(r"City\s+of\s+(?P<name>.+)$", raw, re.I)
    if city_match:
        stem = city_match.group("name")
        add(f"city of {stem}")
        add(f"{stem} city council")
    city_suffix = None if re.search(r"\bRural\s+City\s+Council$", raw, re.I) else re.match(r"(?P<name>.+?)\s+City\s+Council$", raw, re.I)
    if city_suffix:
        stem = city_suffix.group("name")
        add(f"city of {stem}")
        add(f"{stem} city council")

    rural_city_suffix = re.match(r"(?P<name>.+?)\s+Rural\s+City\s+Council$", raw, re.I)
    if rural_city_suffix:
        stem = rural_city_suffix.group("name")
        add(f"{stem} rural city council")
        add(f"{stem} rural city")

    shire_suffix = re.match(r"(?P<name>.+?)\s+Shire\s+Council$", raw, re.I)
    if shire_suffix:
        stem = shire_suffix.group("name")
        add(f"{stem} shire council")
        add(f"{stem} shire")

    borough_suffix = re.match(r"(?P<name>.+?)\s+Borough\s+Council$", raw, re.I)
    if borough_suffix:
        stem = borough_suffix.group("name")
        add(f"{stem} borough council")
        add(f"{stem} borough")

    return variants[:5]


def _careers_at_council_council_page_sources(registry_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for row in registry_payload.get("rows") or []:
        council_name = normalize_whitespace(str(row.get("council_name") or row.get("short_name") or ""))
        short_name = normalize_whitespace(str(row.get("short_name") or council_name))
        slug = _careers_at_council_slug(council_name or short_name)
        if not slug:
            continue
        sources.append({
            "source_id": f"careers_at_council_{_normalise_accumulator_key(short_name).replace(' ', '_')}",
            "source_name": f"Careers at Council - {council_name or short_name}",
            "source_family": "careersatcouncil",
            "url": f"https://www.careersatcouncil.com.au/council-jobs/{slug}/",
            "source_priority": 45,
            "best_use": "expanded public-board discovery by council page",
            "monitoring_role": "secondary_signal",
        })
    return sources


def _careers_at_council_slug(council_name: str) -> str:
    text = normalize_whitespace(council_name)
    text = re.sub(r"\bCouncil\b$", "", text, flags=re.I).strip()
    text = re.sub(r"&", " and ", text)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    return slug


def _jora_council_search_sources(registry_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for row in registry_payload.get("rows") or []:
        council_name = normalize_whitespace(str(row.get("council_name") or row.get("short_name") or ""))
        short_name = normalize_whitespace(str(row.get("short_name") or council_name))
        if not council_name and not short_name:
            continue
        location_slug = _jora_slug(short_name or council_name)
        for search_slug in _jora_council_query_slugs(council_name or short_name, short_name):
            sources.append({
                "source_id": f"jora_{_normalise_accumulator_key(short_name).replace(' ', '_')}_{search_slug.replace('-', '_')}",
                "source_name": f"Jora - {council_name or short_name}",
                "source_family": "jora",
                "url": f"https://au.jora.com/{search_slug}-jobs-in-{location_slug}-VIC",
                "source_priority": 55,
                "best_use": "expanded public-board discovery by council search",
                "monitoring_role": "secondary_signal",
                "short_name": short_name,
                "council_name": council_name or short_name,
                "council_grouping": row.get("council_grouping"),
                "poll_tier": row.get("poll_tier"),
                "strict_council_match": True,
            })
    return sources


def _jora_council_query_slugs(council_name: str, short_name: str = "") -> list[str]:
    raw = normalize_whitespace(council_name)
    short = normalize_whitespace(short_name or raw)
    variants: list[str] = []

    def add(value: str) -> None:
        slug = _jora_slug(value)
        if slug and slug not in variants:
            variants.append(slug)

    add(f"{short} Council")
    add(raw)
    city_suffix = re.match(r"(?P<name>.+?)\s+City\s+Council$", raw, re.I)
    if city_suffix:
        add(f"City of {city_suffix.group('name')}")
    return variants[:3]


def _jora_slug(value: str) -> str:
    text = normalize_whitespace(value)
    text = text.replace("&", " and ")
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def _local_government_jobs_council_search_sources(registry_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for row in registry_payload.get("rows") or []:
        council_name = normalize_whitespace(str(row.get("council_name") or row.get("short_name") or ""))
        short_name = normalize_whitespace(str(row.get("short_name") or council_name))
        if not council_name and not short_name:
            continue
        query = quote_plus(council_name or short_name)
        sources.append({
            "source_id": f"local_government_jobs_{_normalise_accumulator_key(short_name).replace(' ', '_')}",
            "source_name": f"Local Government Jobs - {council_name or short_name}",
            "source_family": "localgovernmentjobs",
            "url": f"https://www.localgovernmentjobs.com.au/jobs?search={query}",
            "source_priority": 50,
            "best_use": "expanded public-board discovery by council keyword search",
            "monitoring_role": "secondary_signal",
            "short_name": short_name,
            "council_name": council_name or short_name,
            "council_grouping": row.get("council_grouping"),
            "poll_tier": row.get("poll_tier"),
            "strict_council_match": True,
        })
    return sources


def _scrape_secondary_source(
    source: dict[str, Any],
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    url = source.get("url") or ""
    base_result = {
        "source_id": source.get("source_id"),
        "source_name": source.get("source_name"),
        "source_family": source.get("source_family"),
        "url": url,
        "monitoring_role": source.get("monitoring_role"),
    }
    try:
        html, fetch_meta = fetcher(url)
        jobs = _extract_secondary_jobs(source, html)
        return {
            "jobs": jobs,
            "source_result": {
                **base_result,
                **fetch_meta,
                "status": "ok",
                "parsed_jobs": len(jobs),
            },
        }
    except RequestException as error:
        return {
            "jobs": [],
            "source_result": {
                **base_result,
                "status": "failed",
                "parsed_jobs": 0,
                "error": str(error),
            },
        }
    except Exception as error:
        return {
            "jobs": [],
            "source_result": {
                **base_result,
                "status": "failed",
                "parsed_jobs": 0,
                "error": str(error),
            },
        }


def _extract_secondary_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    family = source.get("source_family")
    if family == "careersatcouncil":
        return _extract_careers_at_council_jobs(source, html)
    if family == "localgovernmentjobs":
        return _extract_local_government_jobs(source, html)
    if family == "councildirect":
        return _extract_council_direct_jobs(source, html)
    if family == "jora":
        return _extract_jora_jobs(source, html)
    return []


def _extract_careers_at_council_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    current_date = datetime.now().date()
    blocks = _careers_at_council_card_blocks(html)
    for href, body in blocks:
        title = _clean_job_title(_html_class_text(body, "job-list__title"))
        council = normalize_whitespace(_html_class_text(body, "job-list__council"))
        location = normalize_whitespace(_html_class_text(body, "job-list__location"))
        tags = [item for item in _html_class_texts(body, "job-list__tag") if item]
        salary_text = next((item for item in tags if _looks_like_salary_text(item)), "")
        work_type = next((item for item in tags if item != salary_text), "")
        dates_text = html_to_text(body)
        if not title:
            continue
        job_url = canonicalize_job_url(href)
        year = _year_from_job_url(job_url) or current_date.year
        month_name = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        posted_match = re.search(rf"\bPosted:\s*((?:\d+\s+days?\s+ago)|(?:\d{{1,2}}\s+{month_name}))\b", dates_text, re.I)
        closing_match = re.search(rf"\bCloses:\s*(\d{{1,2}}\s+{month_name})\b", dates_text, re.I)
        jobs.append(normalize_council_job_record({
            "job_uid": _job_uid({"short_name": source.get("source_id")}, job_url),
            "job_title": title,
            "job_url": job_url,
            "canonical_url": job_url,
            "source_url": job_url,
            "source_family": source.get("source_family"),
            "source_name": source.get("source_name"),
            "source_priority": source.get("source_priority"),
            "source_role": "secondary_signal",
            "is_canonical": False,
            "match_status": "secondary_unmatched_until_official_check",
            "source_job_id": _source_job_id("secondary_job_slug", job_url),
            "council_name": council,
            "location_text": location,
            "work_type": work_type,
            "salary_text": salary_text,
            "posted_at_text": _careers_at_council_date_text(posted_match.group(1), year, current_date) if posted_match else None,
            "closing_at_text": f"{closing_match.group(1)} {year}" if closing_match else None,
            "observed_status": "secondary_candidate",
            "parse_confidence": "secondary_card",
        }))
    return jobs


def _extract_local_government_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    card_pattern = re.compile(r'<li class="[^"]*fade-in-bottom[^"]*"[^>]*>(?P<body>.*?)</li>', re.I | re.S)
    for match in card_pattern.finditer(html or ""):
        body = match.group("body")
        href_match = re.search(r'href="(?P<href>https://www\.localgovernmentjobs\.com\.au/job/(?!autocomplete)[^"]+)"', body, re.I)
        if not href_match:
            continue
        title_html = _html_class_text(body, "post-main-title")
        title = _clean_job_title(re.sub(r"\b(?:Full Time|Part Time|Casual|Contractual|Expression of Interest)\b", "", title_html, flags=re.I))
        card_text = html_to_text(body)
        if source.get("strict_council_match") and not _source_council_mentioned_in_text(source, card_text):
            continue
        salary_match = re.search(r"\b(?:Salary\s+)?((?:Competitive)|(?:\$[\d,]+(?:\s*(?:-|to)\s*\$?[\d,]+)?(?:\s*(?:pa|per annum|p/a|hour|weekly|fortnightly|monthly))?))\b", card_text, re.I)
        if not title:
            continue
        job_url = canonicalize_job_url(href_match.group("href"))
        jobs.append(normalize_council_job_record({
            "job_uid": _job_uid({"short_name": source.get("source_id")}, job_url),
            "job_title": title,
            "job_url": job_url,
            "canonical_url": job_url,
            "source_url": job_url,
            "source_family": source.get("source_family"),
            "source_name": source.get("source_name"),
            "source_priority": source.get("source_priority"),
            "source_role": "secondary_signal",
            "is_canonical": False,
            "match_status": "secondary_unmatched_until_official_check",
            "source_job_id": _source_job_id("secondary_job_slug", job_url),
            "council_name": source.get("council_name") if source.get("strict_council_match") else None,
            "short_name": source.get("short_name") if source.get("strict_council_match") else None,
            "location_text": "Victoria" if "VIC (Victoria)" in card_text or "Victoria" in card_text else "",
            "salary_text": salary_match.group(1) if salary_match and "$" in salary_match.group(1) else "",
            "description_text": card_text,
            "observed_status": "secondary_candidate",
            "parse_confidence": "secondary_card",
        }))
    return jobs


def _extract_jora_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    if not source.get("strict_council_match") and not (source.get("council_name") or source.get("short_name")):
        return []
    jobs: list[dict[str, Any]] = []
    current_date = datetime.now().date()
    for href, body, metadata in _jora_card_blocks(html):
        title = _clean_job_title(metadata.get("job_title") or _html_class_text(body, "job-title"))
        company = normalize_whitespace(metadata.get("company_name") or _html_class_text(body, "job-company"))
        card_text = html_to_text(body)
        if not title or not _jora_company_matches_council(source, company, card_text):
            continue
        job_url = _canonicalize_jora_job_url(urljoin(str(source.get("url") or "https://au.jora.com"), unescape(href)))
        if not job_url:
            continue
        posted_text = ""
        posted_match = re.search(r"\bPosted\s+((?:\d+\s*(?:d|day|days)|\d+\s*(?:mo|month|months))\s+ago)\b", card_text, re.I)
        if posted_match:
            posted_text = _relative_posted_date_text(posted_match.group(1), current_date)
        salary_text = _extract_jora_salary_text(card_text)
        jobs.append(normalize_council_job_record({
            "job_uid": _job_uid({"short_name": source.get("source_id")}, job_url),
            "job_title": title,
            "job_url": job_url,
            "canonical_url": job_url,
            "source_url": job_url,
            "source_family": source.get("source_family"),
            "source_name": source.get("source_name"),
            "source_priority": source.get("source_priority"),
            "source_role": "secondary_signal",
            "is_canonical": False,
            "match_status": "secondary_unmatched_until_official_check",
            "source_job_id": _source_job_id("jora_job", job_url),
            "council_name": source.get("council_name") or company,
            "short_name": source.get("short_name"),
            "location_text": normalize_whitespace(metadata.get("location") or ""),
            "salary_text": salary_text,
            "posted_at_text": posted_text or None,
            "description_text": card_text,
            "observed_status": "secondary_candidate",
            "parse_confidence": "jora_card",
        }))
    return jobs


def _extract_council_direct_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    parser = ListingLinkParser()
    parser.feed(html or "")
    seen_urls: set[str] = set()
    for link in parser.links:
        absolute_url = canonicalize_job_url(urljoin(str(source.get("url") or ""), unescape(link.href)))
        if "councildirect.com.au/job/" not in absolute_url or absolute_url in seen_urls:
            continue
        text = normalize_whitespace(unescape(link.text))
        if "VIC (Victoria)" not in text:
            continue
        seen_urls.add(absolute_url)
        work_type_match = re.search(r"\b(Full Time|Part Time|Contractual|Casual|Expression of Interest)\b", text, re.I)
        title_text = text[:work_type_match.start()] if work_type_match else re.split(r"\bSalary:\s*", text, maxsplit=1, flags=re.I)[0]
        salary_text = ""
        council_name = ""
        council_match = re.search(
            r"(?P<council>[A-Z][A-Za-z'&(). -]+?(?:City Council|Shire Council|Rural City Council|Borough Council|Council|Rural City|Shire|City))\s+VIC\s+\(Victoria\)",
            text,
        )
        if council_match:
            council_name = _clean_council_direct_council_name(council_match.group("council"))
            salary_match = re.search(r"\bSalary:\s*(?P<salary>.*?)\s+" + re.escape(council_name), text, re.I)
            if salary_match:
                salary_text = normalize_whitespace(salary_match.group("salary"))
        else:
            council_name = normalize_whitespace(str(source.get("council_name") or source.get("short_name") or ""))
        if not salary_text:
            salary_match = re.search(r"\bSalary:\s*(?P<salary>.*?)(?:\s+VIC\s+\(Victoria\)|$)", text, re.I)
            if salary_match:
                salary_text = normalize_whitespace(salary_match.group("salary"))
        salary_text = _clean_council_direct_salary_text(salary_text, council_name, source)
        jobs.append(normalize_council_job_record({
            "job_uid": _job_uid({"short_name": source.get("source_id")}, absolute_url),
            "job_title": _clean_job_title(title_text),
            "job_url": absolute_url,
            "canonical_url": absolute_url,
            "source_url": absolute_url,
            "source_family": source.get("source_family"),
            "source_name": source.get("source_name"),
            "source_priority": source.get("source_priority"),
            "source_role": "secondary_signal",
            "is_canonical": False,
            "match_status": "secondary_unmatched_until_official_check",
            "source_job_id": _source_job_id("secondary_job_slug", absolute_url),
            "council_name": council_name,
            "work_type": work_type_match.group(1) if work_type_match else "",
            "salary_text": salary_text if salary_text and salary_text.lower() != "competitive" else "",
            "description_text": text,
            "observed_status": "secondary_candidate",
            "parse_confidence": "council_direct_card",
        }))
    return [job for job in jobs if job.get("job_title")]


def _clean_council_direct_council_name(value: str) -> str:
    council_name = normalize_whitespace(value)
    return re.sub(
        r"^(?:\+?\s*)?(?:Super|Superannuation|Plus Super|Plus Superannuation)\s+",
        "",
        council_name,
        flags=re.I,
    ).strip()


def _clean_council_direct_salary_text(
    salary_text: str,
    council_name: str,
    source: dict[str, Any],
) -> str:
    cleaned = normalize_whitespace(salary_text)
    council_phrases = [
        council_name,
        str(source.get("council_name") or ""),
        str(source.get("short_name") or ""),
    ]
    short_name = normalize_whitespace(str(source.get("short_name") or ""))
    if short_name:
        council_phrases.extend([
            f"City of {short_name}",
            f"{short_name} City Council",
            f"{short_name} Shire Council",
            f"{short_name} Rural City Council",
        ])
    for phrase in sorted({normalize_whitespace(item) for item in council_phrases if item}, key=len, reverse=True):
        cleaned = re.sub(rf"\s+{re.escape(phrase)}\b.*$", "", cleaned, flags=re.I).strip()
    return cleaned


def _infer_missing_councils_from_job_text(
    jobs: list[dict[str, Any]],
    registry_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    council_patterns = _council_text_patterns(registry_payload)
    inferred_jobs: list[dict[str, Any]] = []
    for job in jobs:
        if job.get("council_name") or job.get("short_name"):
            inferred_jobs.append(job)
            continue
        haystack = normalize_whitespace(" ".join(str(job.get(key) or "") for key in (
            "job_title",
            "description_text",
            "detail_text",
            "position_description_text",
            "attachment_text",
        )))
        match = _match_council_text(haystack, council_patterns)
        if not match:
            inferred_jobs.append(job)
            continue
        inferred = dict(job)
        inferred["short_name"] = match["short_name"]
        inferred["council_name"] = match["council_name"]
        field_sources = dict(inferred.get("field_sources") or {})
        field_sources.setdefault("council_name", "detail_text_inference")
        inferred["field_sources"] = field_sources
        inferred_jobs.append(normalize_council_job_record(inferred))
    return inferred_jobs


def _council_text_patterns(registry_payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in registry_payload.get("rows") or []:
        short_name = normalize_whitespace(str(row.get("short_name") or ""))
        council_name = normalize_whitespace(str(row.get("council_name") or short_name))
        if not short_name and not council_name:
            continue
        candidate_phrases = {
            council_name,
            f"City of {short_name}" if short_name else "",
            f"{short_name} City Council" if short_name else "",
            f"{short_name} Shire Council" if short_name else "",
            f"{short_name} Rural City Council" if short_name else "",
            f"{short_name} Borough Council" if short_name else "",
        }
        for phrase in candidate_phrases:
            phrase = normalize_whitespace(phrase)
            if len(phrase) < 6:
                continue
            rows.append({
                "phrase": phrase,
                "short_name": short_name or council_name,
                "council_name": council_name or short_name,
            })
    return sorted(rows, key=lambda item: len(item["phrase"]), reverse=True)


def _match_council_text(
    text: str,
    council_patterns: list[dict[str, str]],
) -> dict[str, str] | None:
    if not text:
        return None
    for item in council_patterns:
        phrase = item["phrase"]
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", text, re.I):
            return item
    return None


def _careers_at_council_card_blocks(html: str) -> list[tuple[str, str]]:
    text = html or ""
    blocks: list[tuple[str, str]] = []
    markers = list(re.finditer(r'<div\s+class=["\']job-list\b[^"\']*["\'][^>]*>', text, re.I))
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        body = text[marker.start():end]
        href_match = re.search(
            r'<a[^>]+class=["\'][^"\']*\bjob-list__link\b[^"\']*["\'][^>]+href=["\'](?P<href>https://www\.careersatcouncil\.com\.au/job/[^"\']+)["\']',
            body,
            re.I | re.S,
        ) or re.search(
            r'<a[^>]+href=["\'](?P<href>https://www\.careersatcouncil\.com\.au/job/[^"\']+)["\'][^>]+class=["\'][^"\']*\bjob-list__link\b[^"\']*["\']',
            body,
            re.I | re.S,
        )
        if href_match:
            blocks.append((href_match.group("href"), body))
    if blocks:
        return blocks

    legacy_pattern = re.compile(
        r'<a\s+href=["\'](?P<href>https://www\.careersatcouncil\.com\.au/job/[^"\']+)["\'][^>]*class=["\'][^"\']*\bjob-list\b[^"\']*["\'][^>]*>(?P<body>.*?)</a>',
        re.I | re.S,
    )
    return [(match.group("href"), match.group("body")) for match in legacy_pattern.finditer(text)]


def _jora_card_blocks(html: str) -> list[tuple[str, str, dict[str, str]]]:
    text = html or ""
    blocks: list[tuple[str, str, dict[str, str]]] = []
    markers = list(re.finditer(r'<div\b[^>]*\bdata-job-card=["\']true["\'][^>]*>', text, re.I | re.S))
    for index, marker in enumerate(markers):
        balanced_end = _html_element_end(text, marker.start(), "div")
        next_marker_end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        end = min(balanced_end or len(text), next_marker_end)
        body = text[marker.start():end]
        attrs = marker.group(0)
        metadata: dict[str, str] = {}
        metadata_match = re.search(r'data-braze-job-panel-view=["\'](?P<json>[^"\']+)["\']', attrs, re.I | re.S)
        if metadata_match:
            try:
                decoded = json.loads(unescape(metadata_match.group("json")))
                metadata = {
                    key: normalize_whitespace(str(decoded.get(key) or ""))
                    for key in ("job_id", "job_title", "company_name", "location")
                }
            except Exception:
                metadata = {}
        href_match = re.search(
            r'<a[^>]+class=["\'][^"\']*\bjob-link\b[^"\']*\bdesktop-only\b[^"\']*["\'][^>]+href=["\'](?P<href>[^"\']+)["\']',
            body,
            re.I | re.S,
        ) or re.search(
            r'<a[^>]+href=["\'](?P<href>/job/[^"\']+)["\'][^>]+class=["\'][^"\']*\bjob-link\b[^"\']*["\']',
            body,
            re.I | re.S,
        )
        if href_match:
            blocks.append((href_match.group("href"), body, metadata))
    return blocks


def _html_element_end(html: str, start: int, tag_name: str) -> int | None:
    tag = re.escape(tag_name)
    pattern = re.compile(rf"</?{tag}\b[^>]*>", re.I | re.S)
    depth = 0
    for match in pattern.finditer(html or "", max(0, start)):
        if match.group(0).startswith("</"):
            depth -= 1
            if depth <= 0:
                return match.end()
        else:
            depth += 1
    return None


def _html_class_texts(html: str, class_name: str) -> list[str]:
    pattern = re.compile(
        rf'<[^>]+class=["\'][^"\']*\b{re.escape(class_name)}\b[^"\']*["\'][^>]*>(?P<body>.*?)</[^>]+>',
        re.I | re.S,
    )
    return [
        normalize_whitespace(html_to_text(match.group("body")))
        for match in pattern.finditer(html or "")
        if normalize_whitespace(html_to_text(match.group("body")))
    ]


def _looks_like_salary_text(value: str) -> bool:
    text = normalize_whitespace(value)
    return bool(re.search(r"\$|salary|remuneration|per annum|\bpa\b|\bp/a\b", text, re.I))


def _extract_jora_salary_text(card_text: str) -> str:
    match = re.search(
        r"\$[\d,]+(?:\.\d{1,2})?(?:\s*(?:-|to|–|—)\s*\$?[\d,]+(?:\.\d{1,2})?)?\s*(?:a year|per annum|pa|p/a|an hour|per hour|hour|weekly|per week)?",
        card_text or "",
        re.I,
    )
    return normalize_whitespace(match.group(0)) if match else ""


def _canonicalize_jora_job_url(url: str) -> str:
    parsed = urlsplit(url)
    if "jora.com" not in parsed.netloc.lower() or not parsed.path.startswith("/job/"):
        return ""
    return urlunsplit((parsed.scheme or "https", parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", ""))


def _jora_company_matches_council(source: dict[str, Any], company: str, card_text: str) -> bool:
    if not source.get("strict_council_match"):
        return True
    haystack = normalize_whitespace(f"{company} {card_text}")
    return _source_council_mentioned_in_text(source, haystack)


def _source_council_mentioned_in_text(source: dict[str, Any], text: str) -> bool:
    haystack = normalize_whitespace(text).lower()
    if not haystack:
        return False
    for phrase in _source_council_phrases(source):
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", haystack):
            return True
    return False


def _source_council_phrases(source: dict[str, Any]) -> list[str]:
    council_name = normalize_whitespace(str(source.get("council_name") or ""))
    short_name = normalize_whitespace(str(source.get("short_name") or ""))
    phrases = {
        council_name,
    }
    if short_name:
        phrases.update({
            f"{short_name} Council",
            f"{short_name} City Council",
            f"{short_name} Shire Council",
            f"{short_name} Rural City Council",
            f"City of {short_name}",
            f"Borough of {short_name}",
        })
    return [phrase for phrase in sorted(phrases, key=len, reverse=True) if len(phrase) >= 4]


def _year_from_job_url(url: str) -> int | None:
    match = re.search(r"(?<!\d)(20\d{2})(?:[01]\d[0-3]\d)?(?!\d)", url or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _careers_at_council_date_text(value: str, year: int, current_date: datetime.date) -> str:
    return _relative_posted_date_text(value, current_date, default_year=year)


def _relative_posted_date_text(value: str, current_date: datetime.date, *, default_year: int | None = None) -> str:
    text = normalize_whitespace(value)
    days_match = re.fullmatch(r"(\d+)\s*(?:d|day|days)\s+ago", text, re.I)
    if days_match:
        posted_date = current_date - timedelta(days=int(days_match.group(1)))
        return posted_date.strftime("%d %b %Y")
    months_match = re.fullmatch(r"(\d+)\s*(?:mo|month|months)\s+ago", text, re.I)
    if months_match:
        posted_date = current_date - timedelta(days=int(months_match.group(1)) * 30)
        return posted_date.strftime("%d %b %Y")
    if re.search(r"\b20\d{2}\b", text):
        return text
    return f"{text} {default_year or current_date.year}"


def _enrich_jobs_from_detail_pages(
    jobs: list[dict[str, Any]],
    *,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]],
    detail_job_limit: int,
    attachment_job_limit: int,
    max_workers: int,
    fetch_linked_documents: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    enriched_jobs: list[dict[str, Any]] = list(jobs)
    limit = max(0, detail_job_limit)
    candidates = [
        (index, job) for index, job in enumerate(jobs)
        if _job_needs_detail_enrichment(job)
    ]
    if limit > 0:
        candidates = candidates[:limit]
    if not candidates:
        return enriched_jobs, {
            "attempted": 0,
            "succeeded": 0,
            "details_parsed": 0,
            "document_attempted": 0,
            "document_succeeded": 0,
            "documents_parsed": 0,
        }

    document_budget = {"remaining": max(0, attachment_job_limit), "lock": Lock()}

    def enrich_one(job: dict[str, Any]) -> dict[str, Any]:
        detail_html, _fetch_meta = fetcher(str(job.get("job_url") or ""))
        limited_binary_fetcher = None
        if fetch_linked_documents:
            limited_binary_fetcher = lambda url: _budgeted_binary_fetch(url, binary_fetcher, document_budget)
        enriched = enrich_job_from_detail_page(
            job,
            job,
            detail_html,
            binary_fetcher=None,
        )
        normalized = normalize_council_job_record(enriched)
        if limited_binary_fetcher and _job_needs_document_enrichment(normalized):
            normalized = normalize_council_job_record(enrich_job_from_detail_page(
                normalized,
                normalized,
                detail_html,
                binary_fetcher=limited_binary_fetcher,
            ))
        return normalized

    succeeded = 0
    details_parsed = 0
    document_attempted = 0
    document_succeeded = 0
    documents_parsed = 0
    workers = max(1, min(max_workers, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(enrich_one, job): index
            for index, job in candidates
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                enriched = future.result()
            except Exception:
                continue
            enriched_jobs[index] = enriched
            if enriched.get("detail_text"):
                succeeded += 1
            if (
                enriched.get("classification_band")
                or enriched.get("salary_text")
                or enriched.get("posted_at")
                or enriched.get("closing_at")
            ):
                details_parsed += 1
            attachments = enriched.get("attachments") if isinstance(enriched.get("attachments"), list) else []
            parsed_document_attachments = [
                item for item in attachments
                if item.get("parse_status") == "parsed"
            ]
            attempted_document_attachments = [
                item for item in attachments
                if item.get("parse_status") in {"parsed", "no_text", "failed"}
            ]
            if attempted_document_attachments:
                document_attempted += 1
            if parsed_document_attachments:
                document_succeeded += 1
            if enriched.get("position_description_text") or enriched.get("attachment_text"):
                documents_parsed += 1
    return enriched_jobs, {
        "attempted": len(candidates),
        "succeeded": succeeded,
        "details_parsed": details_parsed,
        "document_attempted": document_attempted,
        "document_succeeded": document_succeeded,
        "documents_parsed": documents_parsed,
    }


def _budgeted_binary_fetch(
    url: str,
    binary_fetcher: Callable[[str], tuple[bytes, dict[str, Any]]],
    budget: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    with budget["lock"]:
        if budget["remaining"] <= 0:
            return b"", {"http_status": 0, "content_type": None, "bytes": 0, "parse_status": "skipped_limit"}
        budget["remaining"] -= 1
    return binary_fetcher(url)


def _job_needs_detail_enrichment(job: dict[str, Any]) -> bool:
    return (
        job.get("governance_status") in {"needs_band_review", "needs_band_confirmation"}
        or not job.get("classification_band")
        or not job.get("salary_text")
    )


def _job_needs_document_enrichment(job: dict[str, Any]) -> bool:
    attachments = job.get("attachments") if isinstance(job.get("attachments"), list) else []
    if not attachments and not job.get("position_description_url"):
        return False
    if any(item.get("kind") == "position_description" for item in attachments):
        return True
    return (
        job.get("governance_status") in {"needs_band_review", "needs_band_confirmation"}
        or not job.get("classification_band")
        or not job.get("salary_text")
    )


def _annotate_completion_action(
    job: dict[str, Any],
    *,
    pay_table_rows_available: bool,
) -> dict[str, Any]:
    action_id, reason = _completion_action_for_job(
        job,
        pay_table_rows_available=pay_table_rows_available,
    )
    definition = COMPLETION_ACTION_DEFINITIONS[action_id]
    annotated = dict(job)
    annotated["completion_action"] = action_id
    annotated["completion_action_label"] = definition["label"]
    annotated["completion_action_priority"] = definition["priority"]
    annotated["completion_reason"] = reason
    return annotated


def _completion_action_for_job(
    job: dict[str, Any],
    *,
    pay_table_rows_available: bool,
) -> tuple[str, str]:
    if job.get("governance_status") == "needs_band_confirmation":
        return "confirm_inferred_band", "Advertised salary produced a single governed band candidate."
    if job.get("is_standard_band_1_to_8"):
        if job.get("standard_band_number") and not job.get("salary_text"):
            return "fill_salary_from_band", "Band is known; Enterprise Agreement salary can be filled from governed pay rows."
        return "governed", "Band 1-8 evidence is present."
    if job.get("salary_min") and not job.get("standard_band_number"):
        return "infer_band_from_salary", "Salary is present; governed pay rows can narrow the band."
    if job.get("classification_band") and not job.get("salary_text"):
        return "fill_salary_from_band", "Band is present but salary is absent."
    if (
        job.get("position_description_url")
        and not (job.get("position_description_text") or job.get("attachment_text"))
    ):
        return "parse_linked_documents", "A linked position document exists but has not yielded text evidence yet."
    attachments = job.get("attachments") if isinstance(job.get("attachments"), list) else []
    if attachments and not (job.get("position_description_text") or job.get("attachment_text")):
        return "parse_linked_documents", "Attachment links exist and should be mined for classification and salary."
    if job.get("detail_text"):
        return "mine_detail_page", "Detail page text exists but band or salary evidence is still missing."
    return "match_secondary_sources", "Use secondary mirrors to locate richer official detail or alternate URLs."


def _completion_actions_for_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    examples: dict[str, list[dict[str, str]]] = {}
    for job in jobs:
        action = str(job.get("completion_action") or "match_secondary_sources")
        counts[action] = counts.get(action, 0) + 1
        bucket = examples.setdefault(action, [])
        if len(bucket) < 3:
            bucket.append({
                "job_title": str(job.get("job_title") or ""),
                "council_name": str(job.get("council_name") or job.get("short_name") or ""),
                "job_url": str(job.get("job_url") or ""),
            })
    rows: list[dict[str, Any]] = []
    for action, count in counts.items():
        definition = COMPLETION_ACTION_DEFINITIONS.get(action, COMPLETION_ACTION_DEFINITIONS["match_secondary_sources"])
        rows.append({
            "action_id": action,
            **definition,
            "count": count,
            "examples": examples.get(action, []),
        })
    return sorted(rows, key=lambda row: (int(row.get("priority") or 99), str(row.get("label") or "")))


def _completion_summary(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(jobs)
    governed = sum(1 for job in jobs if job.get("is_standard_band_1_to_8"))
    needing = [
        job for job in jobs
        if job.get("governance_status") in {"needs_band_review", "needs_band_confirmation"}
    ]
    with_documents = [
        job for job in needing
        if job.get("position_description_url") or job.get("attachments")
    ]
    with_salary = [job for job in needing if job.get("salary_min") and not job.get("standard_band_number")]
    banded_missing_salary = [
        job for job in jobs
        if job.get("standard_band_number") and not job.get("salary_text")
    ]
    return {
        "band_completion_rate": round((governed / total) * 100, 1) if total else 0,
        "jobs_with_posted_date": sum(1 for job in jobs if job.get("posted_at")),
        "unbanded_with_document_links": len(with_documents),
        "unbanded_with_salary": len(with_salary),
        "banded_missing_salary": len(banded_missing_salary),
    }


def _looks_like_job_attachment_link(text: str, url: str) -> bool:
    label = normalize_whitespace(text).lower()
    parsed = urlsplit(url)
    if parsed.scheme.lower() in {"javascript", "mailto", "tel"}:
        return False
    url_text = f"{parsed.path} {parsed.query}".lower()
    strong_labels = (
        "position description",
        "position profile",
        "position document",
        "role description",
        "job description",
        "candidate pack",
        "information pack",
    )
    if any(token in label for token in strong_labels):
        return True
    if not _url_looks_like_document(url):
        return False
    if re.search(r"\bpd\b", label) and re.search(r"\b(pd|position|description)\b", url_text):
        return True
    return any(token in url_text for token in (
        "position-description",
        "role-description",
        "job-description",
        "candidate-pack",
        "information-pack",
        "position_profile",
        "position-profile",
        "/pd-",
        "pd_",
    ))


def _embedded_document_urls(html: str, base_url: str) -> list[str]:
    if not html:
        return []
    decoded = unescape(html)
    candidates: list[str] = []
    url_pattern = re.compile(
        r"""(?P<url>(?:https?:)?//[^\s"'<>]+?(?:\.pdf|\.docx?|\.rtf|TransferFile\.ashx|gf-download=)[^\s"'<>]*)""",
        re.I,
    )
    for match in url_pattern.finditer(decoded):
        raw_url = match.group("url").strip(" \t\r\n)")
        if raw_url.startswith("//"):
            raw_url = f"{urlsplit(base_url).scheme or 'https'}:{raw_url}"
        absolute_url = _normalize_document_url(urljoin(base_url, raw_url), base_url)
        if _url_looks_like_document(absolute_url):
            candidates.append(absolute_url)
    return list(dict.fromkeys(candidates))


def _normalize_document_url(url: str, base_url: str = "") -> str:
    absolute_url = canonicalize_job_url(url)
    parsed = urlsplit(absolute_url)
    if "candidate.aurion.cloud" not in parsed.netloc.lower():
        return absolute_url
    aurion_match = re.match(
        r"(?P<prefix>/.+?)/(?:jobs/)?vacancies/[^/]+/(?P<file>file/(?:recadvert|temp)/.+)$",
        parsed.path,
        flags=re.I,
    )
    if not aurion_match:
        return absolute_url
    base_path = aurion_match.group("prefix")
    file_path = aurion_match.group("file")
    normalized_path = f"{base_path}/{file_path}"
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, ""))


def _attachment_kind(text: str, url: str) -> str:
    label = normalize_whitespace(text).lower()
    url_text = f"{urlsplit(url).path} {urlsplit(url).query}".lower()
    if (
        "position description" in label
        or "position-description" in url_text
        or re.search(r"\bpd\b", label)
        or "pd-" in url_text
        or "pd_" in url_text
        or re.search(r"(?:^|[/&=?._-])pd[-_]", url_text)
    ):
        return "position_description"
    if "role description" in label or "role-description" in url_text:
        return "position_description"
    return "job_attachment"


def _attachment_label_from_url(url: str) -> str:
    parsed = urlsplit(url)
    query_match = re.search(r"(?:^|[?&])gf-download=([^&]+)", parsed.query)
    raw = query_match.group(1) if query_match else parsed.path.rsplit("/", 1)[-1]
    raw = unescape(raw).split("/")[-1]
    raw = re.sub(r"\.(?:pdf|docx?|rtf)$", "", raw, flags=re.I)
    raw = re.sub(r"[-_]+", " ", raw)
    return normalize_whitespace(raw) or "Job attachment"


def _document_content_type_hint(url: str) -> str | None:
    if _url_looks_like_pdf(url):
        return "application/pdf"
    if _url_looks_like_docx(url):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None


def _url_looks_like_pdf(url: str) -> bool:
    parsed = urlsplit(url)
    return ".pdf" in parsed.path.lower() or ".pdf" in parsed.query.lower()


def _url_looks_like_docx(url: str) -> bool:
    parsed = urlsplit(url)
    haystack = f"{parsed.path} {parsed.query}".lower()
    return ".docx" in haystack or ".doc" in haystack


def _url_looks_like_document(url: str) -> bool:
    parsed = urlsplit(url)
    haystack = f"{parsed.path} {parsed.query}".lower()
    return any(token in haystack for token in (".pdf", ".docx", ".doc", ".rtf", "transferfile.ashx", "gf-download=", "/file/recadvert/"))


def _should_fetch_attachment(attachment: dict[str, Any]) -> bool:
    url = str(attachment.get("url") or "")
    return attachment.get("kind") == "position_description" or _url_looks_like_document(url)


def _bytes_look_like_pdf(content: bytes, content_type: str) -> bool:
    return "pdf" in content_type.lower() or content[:5] == b"%PDF-"


def _bytes_look_like_docx(content: bytes, content_type: str) -> bool:
    lowered = content_type.lower()
    return (
        "wordprocessingml" in lowered
        or "application/msword" in lowered
        or content[:2] == b"PK"
    )


def _document_text_source(attachment: dict[str, Any], document_kind: str) -> str:
    prefix = "position_description" if attachment.get("kind") == "position_description" else "linked_document"
    if document_kind in {"pdf", "docx"}:
        return f"{prefix}_{document_kind}"
    return prefix


def _combined_document_text_source(sources: list[str]) -> str:
    unique_sources = [source for source in dict.fromkeys(sources) if source]
    if len(unique_sources) == 1:
        return unique_sources[0]
    if any(source.endswith("_docx") for source in unique_sources):
        return "linked_document_mixed"
    if any(source.endswith("_pdf") for source in unique_sources):
        return "linked_document_mixed"
    return "linked_document"


def _looks_like_job_detail_url(platform: str, source: dict[str, Any], url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    listing_path = urlsplit(source.get("listing_url") or "").path.rstrip("/")
    listing_host = urlsplit(source.get("listing_url") or "").netloc.lower()
    if not parsed.netloc or path == listing_path:
        return False
    if platform == "pageup":
        return bool(re.search(r"/(?:cw/[a-z]{2}/|[a-z]{2}/)job/\d+/", path))
    if platform == "pulse":
        return "/Pulse/job/" in path
    if platform == "recruitmenthub":
        return bool(re.search(r"/(?:Vacancies|Current-vacancies)/\d+/title/", path))
    if platform == "applynow":
        host = parsed.netloc.lower()
        if "applynow.net.au" not in host or "/assets/" in path:
            return False
        return bool(re.search(r"/jobs/(?:ni/)?[A-Za-z0-9]+(?:-[^/]+)?$", path))
    if platform == "employmenthero":
        return parsed.netloc.lower() == "employmenthero.com" and path.startswith("/jobs/position/")
    if platform == "smartrecruiters":
        return parsed.netloc.lower() == "jobs.smartrecruiters.com" and bool(re.search(r"/[^/]+/\d+", path))
    if platform == "elmo_talent":
        return "elmotalent.com.au" in parsed.netloc.lower() and bool(re.search(r"/careers/[^/]+/job/view/[^/]+", path))
    if platform == "aurion_selfservice":
        return bool(re.search(r"/(?:jobs/)?vacancies/[^/]+/edit$", path))
    if platform == "bigredsky":
        return parsed.netloc.lower() == listing_host and path == "/page.php" and "AdvertID=" in parsed.query
    if platform == "oracle_hcm":
        return bool(re.search(r"/hcmUI/CandidateExperience/.+/job/[^/]+$", path))
    if platform == "dayforce":
        return "dayforcehcm.com" in parsed.netloc.lower() and bool(re.search(r"/jobs/[^/]+$", path))
    if platform == "successfactors":
        return "successfactors.com" in parsed.netloc.lower() and path == "/sfcareer/jobreqcareer"
    if platform == "adlogic_martianlogic":
        return "/job-details/" in path
    if platform == "native_council_custom":
        return path.startswith("/jobs/") and path.count("/") >= 2
    if platform == "native_council":
        pattern_prefix = _detail_pattern_prefix(source.get("detail_pattern"))
        if pattern_prefix:
            return path.startswith(pattern_prefix)
        listing_prefix = listing_path.rstrip("/") + "/"
        return path.startswith(listing_prefix) and not path.endswith("#main-content")
    return any(token in path for token in ("/job/", "/jobs/", "/Vacancies/", "/current-vacancies/"))


def _extract_pulse_jobs_from_listing_api(
    source: dict[str, Any],
    html: str,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    api_url = _pulse_api_url(source, html)
    if not api_url:
        return []
    try:
        payload_text, _fetch_meta = fetcher(api_url)
        payload = json.loads(payload_text)
    except Exception:
        return []
    jobs: list[dict[str, Any]] = []
    for item in payload.get("Jobs", []):
        job_info = item.get("JobInfo") or {}
        title = _clean_job_title(job_info.get("Title") or "")
        link_id = str(item.get("LinkId") or "").strip()
        job_url = _pulse_job_url(source, item, title)
        if not title or not job_url:
            continue
        absolute_url = canonicalize_job_url(job_url)
        jobs.append({
            "job_uid": _job_uid(source, absolute_url),
            "job_title": title,
            "job_url": absolute_url,
            "source_job_id": link_id or _source_job_id("pulse", absolute_url),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "pulse",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": source.get("listing_url"),
            "location_text": job_info.get("Location"),
            "department": job_info.get("Department"),
            "work_type": job_info.get("EmploymentType"),
            "posted_at_text": job_info.get("PostDate"),
            "closing_at_text": job_info.get("ClosingDate"),
            "salary_text": job_info.get("Compensation"),
            "description_html": job_info.get("Description"),
            "description_source": "pulse_json",
            "remote_mode": job_info.get("WorkArrangement"),
            "job_number": job_info.get("JobRef"),
            "observed_status": "open_candidate",
            "parse_confidence": "pulse_json",
            "field_sources": {
                "job_title": "pulse_json",
                "posted_at": "pulse_json",
                "closing_at": "pulse_json",
                "salary_text": "pulse_json",
                "description_text": "pulse_json",
            },
        })
    return jobs


def _extract_smartrecruiters_jobs_from_listing_api(
    source: dict[str, Any],
    html: str,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    company_code = _smartrecruiters_company_code(source, html)
    if not company_code:
        return []
    payload_text = html or ""
    if not _smartrecruiters_payload_items(payload_text):
        api_url = _smartrecruiters_api_url(company_code)
        try:
            payload_text, _fetch_meta = fetcher(api_url)
        except Exception:
            return []
    payload = _smartrecruiters_payload_items(payload_text)
    jobs: list[dict[str, Any]] = []
    for item in payload:
        title = _clean_job_title(item.get("name") or item.get("vacancyName") or item.get("jobTitle") or "")
        job_id = str(item.get("id") or item.get("publicationId") or "").strip()
        company_identifier = _smartrecruiters_item_company_identifier(item, company_code)
        if not title or not job_id or not company_identifier:
            continue
        job_url = canonicalize_job_url(
            str(item.get("postingUrl") or "")
            or _smartrecruiters_job_url(company_identifier, job_id, item.get("urlJobName") or title)
        )
        location = _smartrecruiters_location_text(item)
        jobs.append({
            "job_uid": _job_uid(source, job_url),
            "job_title": title,
            "job_url": job_url,
            "source_job_id": job_id,
            "job_number": item.get("refNumber"),
            "council_name": source.get("council_name") or _smartrecruiters_company_name(item),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "smartrecruiters",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": source.get("listing_url"),
            "location_text": location,
            "department": _smartrecruiters_label(item.get("department")),
            "work_type": _smartrecruiters_label(item.get("typeOfEmployment")),
            "posted_at": _smartrecruiters_released_at(item.get("releasedDate")),
            "posted_at_text": str(item.get("releasedDate") or ""),
            "remote_mode": _smartrecruiters_remote_mode(item),
            "apply_url": job_url,
            "apply_method": "external_ats",
            "observed_status": "open_candidate",
            "parse_confidence": "smartrecruiters_json",
            "field_sources": {
                "job_title": "smartrecruiters_json",
                "posted_at": "smartrecruiters_json",
                "work_type": "smartrecruiters_json",
                "location_text": "smartrecruiters_json",
            },
        })
    return jobs


def _smartrecruiters_company_code(source: dict[str, Any], html: str) -> str:
    explicit = str(source.get("company_code") or source.get("smartrecruiters_company_code") or "").strip()
    if explicit:
        return explicit
    for pattern in (
        r'"company_code"\s*:\s*"([^"]+)"',
        r"'company_code'\s*:\s*'([^']+)'",
        r"data-company-identifier=['\"]([^'\"]+)",
        r"/companies/([^/?#]+)/postings",
        r"/widgets/([^/?#]+)/postings",
        r"[?&]dcr_ci=([A-Za-z0-9_-]+)",
    ):
        match = re.search(pattern, html or "", re.I)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _smartrecruiters_api_url(company_code: str) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/{company_code}/postings?limit=100&offset=0"


def _smartrecruiters_payload_items(payload_text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(payload_text or "")
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("content") or payload.get("results") or []
    return [item for item in items if isinstance(item, dict)]


def _smartrecruiters_item_company_identifier(item: dict[str, Any], fallback: str) -> str:
    company = item.get("company")
    if isinstance(company, dict):
        return str(company.get("identifier") or fallback).strip()
    return str(item.get("companyIdentifier") or fallback).strip()


def _smartrecruiters_company_name(item: dict[str, Any]) -> str:
    company = item.get("company")
    if isinstance(company, dict):
        return str(company.get("name") or "").strip()
    return str(item.get("companyName") or "").strip()


def _smartrecruiters_job_url(company_identifier: str, job_id: str, title_or_slug: Any) -> str:
    slug = str(title_or_slug or "")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower() or "job"
    return f"https://jobs.smartrecruiters.com/{company_identifier}/{job_id}-{slug}"


def _smartrecruiters_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("name") or value.get("id") or "").strip()
    return str(value or "").strip()


def _smartrecruiters_location_text(item: dict[str, Any]) -> str:
    location = item.get("location")
    if isinstance(location, dict):
        return str(location.get("fullLocation") or ", ".join(
            part for part in (
                location.get("city"),
                location.get("region"),
                location.get("country"),
            )
            if part
        )).strip()
    parts = [str(item.get("location") or "").strip(), str(item.get("regionAbbreviation") or "").strip()]
    return ", ".join(part for part in parts if part)


def _smartrecruiters_remote_mode(item: dict[str, Any]) -> str:
    location = item.get("location")
    if isinstance(location, dict):
        if location.get("remote"):
            return "remote"
        if location.get("hybrid"):
            return "hybrid"
        return "onsite"
    if item.get("locationRemote"):
        return "remote"
    if item.get("locationHybrid"):
        return "hybrid"
    return "onsite"


def _smartrecruiters_released_at(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _extract_oracle_hcm_jobs_from_listing_api(
    source: dict[str, Any],
    html: str,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    api_url = _oracle_hcm_api_url(source, html)
    if not api_url:
        return []
    try:
        payload_text, _fetch_meta = fetcher(api_url)
        payload = json.loads(payload_text)
    except Exception:
        return []
    search_item = next((item for item in payload.get("items", []) if isinstance(item, dict)), {})
    requisitions = search_item.get("requisitionList") or search_item.get("RequisitionList") or []
    jobs: list[dict[str, Any]] = []
    for item in requisitions:
        if not isinstance(item, dict):
            continue
        title = _clean_job_title(str(item.get("Title") or item.get("title") or ""))
        job_id = str(item.get("Id") or item.get("id") or item.get("RequisitionNumber") or "").strip()
        if not title or not job_id:
            continue
        job_url = canonicalize_job_url(_oracle_hcm_job_url(source, job_id))
        location = normalize_whitespace(str(
            item.get("PrimaryLocation")
            or item.get("primaryLocation")
            or _oracle_hcm_work_location_text(item)
            or ""
        ))
        description = normalize_whitespace(" ".join(str(value or "") for value in (
            item.get("ShortDescriptionStr"),
            item.get("shortDescriptionStr"),
            item.get("ExternalDescriptionStr"),
            item.get("externalDescriptionStr"),
            item.get("ExternalResponsibilitiesStr"),
            item.get("externalResponsibilitiesStr"),
            item.get("ExternalQualificationsStr"),
            item.get("externalQualificationsStr"),
        )))
        jobs.append({
            "job_uid": _job_uid(source, job_url),
            "job_title": title,
            "job_url": job_url,
            "source_job_id": job_id,
            "job_number": job_id,
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "oracle_hcm",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": source.get("listing_url"),
            "location_text": location,
            "department": item.get("Department") or item.get("department"),
            "work_type": item.get("WorkerType") or item.get("workerType") or item.get("JobSchedule") or item.get("jobSchedule"),
            "posted_at_text": item.get("PostedDate") or item.get("postedDate"),
            "closing_at_text": item.get("PostingEndDate") or item.get("postingEndDate"),
            "description_text": description,
            "description_source": "oracle_hcm_json",
            "apply_url": job_url,
            "apply_method": "external_ats",
            "observed_status": "open_candidate",
            "parse_confidence": "oracle_hcm_json",
            "field_sources": {
                "job_title": "oracle_hcm_json",
                "posted_at": "oracle_hcm_json",
                "closing_at": "oracle_hcm_json",
                "description_text": "oracle_hcm_json",
                "location_text": "oracle_hcm_json",
            },
        })
    return jobs


def _oracle_hcm_api_url(source: dict[str, Any], html: str) -> str:
    listing_url = str(source.get("listing_url") or "")
    parsed = urlsplit(listing_url)
    if not parsed.netloc:
        return ""
    site_number = _oracle_hcm_site_number(source, html, listing_url)
    if not site_number:
        return ""
    query = urlencode({
        "onlyData": "true",
        "expand": (
            "requisitionList.workLocation,requisitionList.otherWorkLocations,"
            "requisitionList.secondaryLocations,flexFieldsFacet.values,"
            "requisitionList.requisitionFlexFields"
        ),
        "finder": (
            f"findReqs;siteNumber={site_number},"
            "facetsList=LOCATIONS;WORK_LOCATIONS;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;WORKPLACE_TYPES,"
            "limit=100,offset=0"
        ),
    })
    return urlunsplit((
        parsed.scheme or "https",
        parsed.netloc,
        "/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        query,
        "",
    ))


def _oracle_hcm_site_number(source: dict[str, Any], html: str, listing_url: str) -> str:
    explicit = str(source.get("site_number") or source.get("siteNumber") or "").strip()
    if explicit:
        return explicit
    haystack = f"{html or ''} {listing_url or ''}"
    for pattern in (
        r"siteNumber\s*:\s*['\"]([^'\"]+)",
        r"[?&]siteNumber=([^&\"']+)",
        r"/sites/(CX_[^/?#\"']+)",
    ):
        match = re.search(pattern, haystack, re.I)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _oracle_hcm_job_url(source: dict[str, Any], job_id: str) -> str:
    listing_url = str(source.get("listing_url") or "")
    parsed = urlsplit(listing_url)
    path = re.sub(r"/jobs/?$", "", parsed.path.rstrip("/"), flags=re.I) or parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme or "https", parsed.netloc, f"{path}/job/{job_id}", "", ""))


def _oracle_hcm_work_location_text(item: dict[str, Any]) -> str:
    locations: list[str] = []
    for key in ("workLocation", "WorkLocation", "otherWorkLocations", "OtherWorkLocations", "secondaryLocations", "SecondaryLocations"):
        value = item.get(key)
        if isinstance(value, dict):
            text = value.get("Address") or value.get("address") or value.get("Name") or value.get("name")
            if text:
                locations.append(str(text))
        elif isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                text = entry.get("Address") or entry.get("address") or entry.get("Name") or entry.get("name")
                if text:
                    locations.append(str(text))
    return ", ".join(dict.fromkeys(normalize_whitespace(value) for value in locations if normalize_whitespace(value)))


def _extract_elmo_talent_jobs_from_listing(
    source: dict[str, Any],
    html: str,
    fetcher: Callable[[str], tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    listing_url = source.get("listing_url") or ""
    embed_url = _elmo_talent_embed_url(source, html, listing_url)
    portal_html = html or ""
    portal_url = listing_url
    if embed_url and canonicalize_job_url(embed_url) != canonicalize_job_url(listing_url):
        try:
            portal_html, _fetch_meta = fetcher(embed_url)
            portal_url = embed_url
        except Exception:
            return []
    return _extract_elmo_talent_jobs_from_portal(source, portal_html, portal_url)


def _extract_elmo_talent_jobs_from_portal(source: dict[str, Any], html: str, portal_url: str) -> list[dict[str, Any]]:
    blocks = re.findall(
        r"<li\b(?=[^>]*\blist-group-item\b)[^>]*>(?P<body>.*?)</li>",
        html or "",
        re.I | re.S,
    )
    if not blocks and "section-list" in (html or ""):
        section = _first_html_match(
            html,
            r"<div[^>]+id=[\"']section-list[\"'][^>]*>(?P<body>.*?)</div>\s*<div[^>]+class=[\"'][^\"']*\belmo-pagination\b",
        )
        blocks = re.findall(r"<li[^>]*>(?P<body>.*?)</li>", section or "", re.I | re.S)
    jobs_by_url: dict[str, dict[str, Any]] = {}
    for block in blocks:
        link_match = re.search(r"<a\s+[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>", block, re.I | re.S)
        if not link_match:
            continue
        absolute_url = canonicalize_job_url(urljoin(portal_url, unescape(link_match.group("href"))))
        if not _looks_like_job_detail_url("elmo_talent", source, absolute_url):
            continue
        title = _clean_job_title(html_to_text(link_match.group("title")))
        if not title:
            continue
        card_fields = _elmo_talent_card_fields(block)
        body_text = _elmo_talent_card_summary(block, title) or html_to_text(block)
        jobs_by_url[absolute_url] = {
            "job_uid": _job_uid(source, absolute_url),
            "job_title": title,
            "job_url": absolute_url,
            "source_job_id": _source_job_id("elmo_talent", absolute_url),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "elmo_talent",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": source.get("listing_url") or portal_url,
            "apply_url": absolute_url,
            "apply_method": "external_ats",
            "location_text": card_fields.get("location_text") or _extract_labelled_inline_value(body_text, ("Location", "Job Location")),
            "work_type": card_fields.get("work_type") or _extract_labelled_inline_value(body_text, ("Job Type", "Employment Type")),
            "closing_at_text": card_fields.get("closing_at_text") or _extract_labelled_inline_value(body_text, ("Closing Date", "Applications close", "Closes")),
            "description_text": body_text,
            "description_source": "elmo_talent_listing_card",
            "observed_status": "open_candidate",
            "parse_confidence": "elmo_talent_listing_card",
            "field_sources": {
                "job_title": "elmo_talent_listing_card",
                "location_text": "elmo_talent_listing_card",
                "work_type": "elmo_talent_listing_card",
                "closing_at": "elmo_talent_listing_card",
            },
        }
    return list(jobs_by_url.values())


def _elmo_talent_card_fields(html: str) -> dict[str, str]:
    values = [
        html_to_text(match)
        for match in re.findall(
            r"<div[^>]+class=[\"'][^\"']*\bcol-md-10\b[^\"']*\bcol-sm-10\b[^\"']*\bcol-xs-10\b[^\"']*[\"'][^>]*>(?P<body>.*?)</div>",
            html or "",
            re.I | re.S,
        )
    ]
    values = [normalize_whitespace(value) for value in values if normalize_whitespace(value)]
    return {
        "location_text": values[0] if len(values) > 0 else "",
        "work_type": values[1] if len(values) > 1 else "",
        "closing_at_text": values[2] if len(values) > 2 else "",
    }


def _elmo_talent_card_summary(html: str, title: str) -> str:
    left_column = _first_html_match(
        html,
        r"<div[^>]+class=[\"'][^\"']*\bcol-md-8\b[^\"']*\brt-editor\b[^\"']*[\"'][^>]*>(?P<body>.*?)</div>\s*<div[^>]+class=[\"'][^\"']*\bcol-md-4\b",
    )
    if not left_column:
        return ""
    text = html_to_text(left_column)
    title_pattern = re.escape(normalize_whitespace(title))
    text = re.sub(rf"^{title_pattern}\s*", "", text, flags=re.I)
    return normalize_whitespace(text)


def _elmo_talent_embed_url(source: dict[str, Any], html: str, base_url: str) -> str:
    explicit = str(source.get("embed_url") or "").strip()
    if explicit:
        return explicit
    match = re.search(r"<iframe[^>]+src=[\"'](?P<src>[^\"']*elmotalent\.com\.au[^\"']*)[\"']", html or "", re.I)
    if match:
        return urljoin(base_url, unescape(match.group("src")))
    return ""


def _extract_labelled_inline_value(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})\s*:?\s*(?P<value>.+?)(?=\s+(?:Location|Job Location|Job Type|Employment Type|Closing Date|Applications close|Closes)\s*:|$)",
        normalize_whitespace(text),
        re.I,
    )
    return match.group("value").strip(" -|") if match else None


def _extract_aurion_jobs_from_listing(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    listing_url = source.get("listing_url") or ""
    row_pattern = re.compile(
        r'<tr[^>]+id="(?P<id>[^"]+)"[^>]+data-url="(?P<url>[^"]+)"[^>]*>(?P<body>.*?)</tr>',
        re.I | re.S,
    )
    for match in row_pattern.finditer(html or ""):
        body = match.group("body")
        title_match = re.search(r'data-th="Position"[^>]*>(?P<title>.*?)</td>', body, re.I | re.S)
        if not title_match:
            continue
        title = _clean_job_title(re.sub(r"<[^>]+>", " ", unescape(title_match.group("title"))))
        if not title:
            continue
        job_url = canonicalize_job_url(urljoin(listing_url, unescape(match.group("url"))))
        jobs.append({
            "job_uid": _job_uid(source, job_url),
            "job_title": title,
            "job_url": job_url,
            "source_job_id": _source_job_id("aurion_selfservice", job_url) or unescape(match.group("id")),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "aurion_selfservice",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": listing_url,
            "observed_status": "open_candidate",
            "parse_confidence": "aurion_table",
        })
    return jobs


def _extract_bigredsky_jobs_from_listing(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    listing_url = source.get("listing_url") or ""
    seen_urls: set[str] = set()
    row_pattern = re.compile(r'<tr\b[^>]*class=["\'][^"\']*(?:evenrow|oddrow)[^"\']*["\'][^>]*>(?P<body>.*?)</tr>', re.I | re.S)
    link_pattern = re.compile(
        r'<a\s+href="(?P<href>page\.php\?[^"]*AdvertID=(?P<id>\d+)[^"]*)"[^>]*>(?P<title>.*?)</a>',
        re.I | re.S,
    )

    for row_match in row_pattern.finditer(html or ""):
        row_body = row_match.group("body")
        link_match = link_pattern.search(row_body)
        if not link_match:
            continue
        title = _clean_job_title(re.sub(r"<[^>]+>", " ", unescape(link_match.group("title"))))
        if not title or _is_non_job_navigation_title("native_council", title):
            continue
        job_url = canonicalize_job_url(urljoin(listing_url, unescape(link_match.group("href"))))
        if not job_url or job_url in seen_urls:
            continue
        seen_urls.add(job_url)
        cells = [
            normalize_whitespace(re.sub(r"<[^>]+>", " ", unescape(cell.group("body"))))
            for cell in re.finditer(r"<td\b[^>]*>(?P<body>.*?)</td>", row_body, re.I | re.S)
        ]
        closing_text = cells[0] if cells else ""
        location_text = cells[2] if len(cells) >= 3 else ""
        field_sources = {
            "job_title": "bigredsky_table_row",
            "source_job_id": "bigredsky_table_row",
        }
        if closing_text:
            field_sources["closing_at"] = "bigredsky_table_row"
        if location_text:
            field_sources["location_text"] = "bigredsky_table_row"
        jobs.append({
            "job_uid": _job_uid(source, job_url),
            "job_title": title,
            "job_url": job_url,
            "source_job_id": link_match.group("id"),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "bigredsky",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": listing_url,
            "closing_at_text": closing_text or None,
            "location_text": location_text or None,
            "field_sources": field_sources,
            "observed_status": "open_candidate",
            "parse_confidence": "bigredsky_table_row",
        })

    for match in link_pattern.finditer(html or ""):
        title = _clean_job_title(re.sub(r"<[^>]+>", " ", unescape(match.group("title"))))
        if not title or _is_non_job_navigation_title("native_council", title):
            continue
        job_url = canonicalize_job_url(urljoin(listing_url, unescape(match.group("href"))))
        if not job_url or job_url in seen_urls:
            continue
        seen_urls.add(job_url)
        jobs.append({
            "job_uid": _job_uid(source, job_url),
            "job_title": title,
            "job_url": job_url,
            "source_job_id": match.group("id"),
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": source.get("platform_family") or "bigredsky",
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": listing_url,
            "observed_status": "open_candidate",
            "parse_confidence": "bigredsky_table_link",
        })
    return jobs


def _pulse_api_url(source: dict[str, Any], html: str) -> str:
    match = re.search(r"_webServiceUrl\s*=\s*['\"]([^'\"]+)", html or "")
    if match:
        base = match.group(1).rstrip("/") + "/"
    else:
        parsed = urlsplit(source.get("listing_url") or "")
        if not parsed.netloc:
            return ""
        base = urlunsplit((parsed.scheme or "https", parsed.netloc, "/WebServices/", "", ""))
    return urljoin(base, "RCM/Jobs/Jobs?internalOnly=false&workArrangement=&employmentType=")


def _embedded_listing_sources(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    listing_url = str(source.get("listing_url") or source.get("official_careers_entry_url") or "")
    listing_host = urlsplit(listing_url).netloc.lower()
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    attr_pattern = re.compile(
        r"\b(?:src|href|data-src|data-url)=['\"](?P<url>[^'\"]+)['\"]",
        re.I,
    )
    for match in attr_pattern.finditer(html or ""):
        absolute_url = canonicalize_job_url(urljoin(listing_url, unescape(match.group("url"))))
        if not absolute_url or absolute_url in seen_urls:
            continue
        parsed = urlsplit(absolute_url)
        host = parsed.netloc.lower()
        if host == listing_host:
            continue
        platform = _embedded_platform_family(host, parsed.path)
        if not platform:
            continue
        if not _looks_like_embedded_listing_url(platform, parsed.path):
            continue
        seen_urls.add(absolute_url)
        sources.append({
            **source,
            "platform_family": platform,
            "listing_url": absolute_url,
            "detail_pattern": _embedded_detail_pattern(platform),
            "listing_url_confidence": "embedded_ats_listing",
            "candidate_pattern_id": "embedded_ats_listing",
            "candidate_notes": f"Embedded ATS listing discovered on {listing_url}",
            "source_role": "embedded_official_ats",
        })
    return sources


def _embedded_platform_family(host: str, path: str) -> str:
    if "applynow.net.au" in host:
        return "applynow"
    if "pulsesoftware.com" in host:
        return "pulse"
    if "recruitmenthub.com.au" in host:
        return "recruitmenthub"
    if "bigredsky.com" in host:
        return "bigredsky"
    if "aurion.cloud" in host or "selfservice" in host:
        return "aurion_selfservice"
    if "elmotalent.com.au" in host:
        return "elmo_talent"
    if "pageuppeople.com" in host:
        return "pageup"
    if "smartrecruiters.com" in host and ("/postings" in path or "/jobs/" in path):
        return "smartrecruiters"
    if "dayforcehcm.com" in host:
        return "dayforce"
    return ""


def _looks_like_embedded_listing_url(platform: str, path: str) -> bool:
    normalized_path = (path or "/").rstrip("/") or "/"
    if platform == "applynow":
        return normalized_path in {"/", "/jobs"} or normalized_path.endswith("/jobs/search")
    if platform == "pulse":
        return normalized_path.lower() == "/pulse/jobs"
    if platform == "recruitmenthub":
        return bool(re.fullmatch(r"/(?:Vacancies|Current-vacancies)", normalized_path, re.I))
    if platform == "bigredsky":
        return normalized_path == "/page.php"
    if platform == "aurion_selfservice":
        return normalized_path.endswith("/production") or normalized_path.endswith("/Prod/jobs")
    if platform == "elmo_talent":
        return bool(re.search(r"/careers/[^/]+/jobs$", normalized_path))
    if platform == "pageup":
        return normalized_path.endswith("/listing") or normalized_path.endswith("/listing/")
    if platform == "smartrecruiters":
        return "/postings" in normalized_path
    if platform == "dayforce":
        return "candidateportal" in normalized_path.lower()
    return False


def _embedded_detail_pattern(platform: str) -> str:
    return {
        "applynow": "/jobs/{job_no}-{slug}",
        "pulse": "/Pulse/job/{short_id}/{slug}?source=public",
        "recruitmenthub": "/Vacancies/{job_id}/title/{slug}",
        "bigredsky": "/page.php?pageID=160&AdvertID={job_id}",
        "aurion_selfservice": "/vacancies/{job_id}/edit",
        "elmo_talent": "/careers/{portal_code}/job/view/{job_id}",
        "pageup": "/cw/en/job/{job_id}/{slug}",
        "smartrecruiters": "/{company_code}/{job_id}-{slug}",
        "dayforce": "/jobs/{job_id}",
    }.get(platform, "/jobs/{slug}")


def _pulse_job_url(source: dict[str, Any], item: dict[str, Any], title: str) -> str:
    apply_url = str(item.get("ApplyUrl") or "")
    link_id = str(item.get("LinkId") or "").strip()
    if apply_url:
        return apply_url.replace("/Pulse/apply/", "/Pulse/job/")
    parsed = urlsplit(source.get("listing_url") or "")
    if not parsed.netloc or not link_id:
        return ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-") or "job"
    return urlunsplit((parsed.scheme or "https", parsed.netloc, f"/Pulse/job/{link_id}/{slug}", "source=public", ""))


def _detail_pattern_prefix(detail_pattern: Any) -> str:
    pattern = str(detail_pattern or "")
    if not pattern.startswith("/"):
        return ""
    prefix = pattern.split("{", 1)[0].rstrip("/")
    return prefix + "/" if prefix else ""


def _clean_job_title(value: str) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"^Image\s+", "", text, flags=re.I)
    text = re.sub(r"\b(Read more|Apply now|View details|View Job|View)\b", "", text, flags=re.I)
    text = re.split(r"\s+Applications?\s+clos(?:e|ing)\s+on\b", text, maxsplit=1, flags=re.I)[0]
    text = re.split(r"\s+(?:Are you|We are|Council is seeking)\b", text, maxsplit=1)[0]
    text = re.split(r"\s+(?:Type|Duration|Salary)\s+", text, maxsplit=1)[0]
    text = re.split(r"\s+at\s+.+?•", text, maxsplit=1)[0]
    text = " ".join(text.split(" - ")) if text.lower() in {"read more", "apply now", "view"} else text
    text = " ".join(text.split()).strip(" -|")
    return "" if text in {"()", "( )"} else text


def _html_class_text(html: str, class_name: str) -> str:
    pattern = re.compile(
        rf'<[^>]+class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(?P<body>.*?)</[^>]+>',
        re.I | re.S,
    )
    match = pattern.search(html or "")
    if not match:
        return ""
    return html_to_text(match.group("body"))


def _extract_opencities_job_list_jobs(source: dict[str, Any], html: str) -> list[dict[str, Any]]:
    platform = source.get("platform_family") or "unknown_official"
    if platform not in {"native_council", "unknown_official"} or "job-list-container" not in (html or ""):
        return []
    listing_url = source.get("listing_url") or source.get("official_careers_entry_url") or ""
    jobs_by_url: dict[str, dict[str, Any]] = {}
    article_pattern = re.compile(
        r"<article[^>]*>\s*<a\s+href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<body>.*?)</a>\s*</article>",
        re.I | re.S,
    )
    for match in article_pattern.finditer(html or ""):
        absolute_url = canonicalize_job_url(_normalize_job_detail_url(platform, urljoin(listing_url, unescape(match.group("href")))))
        if not _looks_like_job_detail_url(platform, source, absolute_url):
            continue
        body = match.group("body")
        title_html = _first_html_match(
            body,
            r"<h[1-6][^>]*class=[\"'][^\"']*\blist-item-title\b[^\"']*[\"'][^>]*>(?P<body>.*?)</h[1-6]>",
        )
        title = _clean_job_title(html_to_text(title_html) if title_html else html_to_text(body))
        if not title or _is_non_job_navigation_link(platform, title, absolute_url):
            continue
        closing_html = _first_html_match(
            body,
            r"<p[^>]*class=[\"'][^\"']*\bapplications-closing\b[^\"']*[\"'][^>]*>(?P<body>.*?)</p>",
        )
        description_text = _opencities_card_description_text(body)
        job_number = _opencities_job_number(absolute_url)
        jobs_by_url[absolute_url] = {
            "job_uid": _job_uid(source, absolute_url),
            "job_title": title,
            "job_url": absolute_url,
            "source_job_id": job_number,
            "job_number": job_number,
            "council_name": source.get("council_name"),
            "short_name": source.get("short_name"),
            "council_grouping": source.get("council_grouping"),
            "poll_tier": source.get("poll_tier"),
            "source_family": platform,
            "source_name": f"{source.get('short_name')} job intake",
            "listing_url": listing_url,
            "closing_at_text": _opencities_closing_text(closing_html) if closing_html else None,
            "description_text": description_text,
            "description_source": "opencities_listing_card",
            "observed_status": "open_candidate",
            "parse_confidence": "opencities_job_list_card",
            "field_sources": {
                "job_title": "opencities_listing_card",
                "closing_at": "opencities_listing_card",
                "description_text": "opencities_listing_card",
            },
        }
    return list(jobs_by_url.values())


def _first_html_match(html: str, pattern: str) -> str:
    match = re.search(pattern, html or "", re.I | re.S)
    return match.group("body") if match else ""


def _opencities_card_description_text(html: str) -> str:
    paragraphs = re.findall(r"<p(?![^>]*\bapplications-closing\b)[^>]*>(.*?)</p>", html or "", re.I | re.S)
    return normalize_whitespace(" ".join(html_to_text(paragraph) for paragraph in paragraphs if paragraph))


def _opencities_closing_text(html: str) -> str:
    text = html_to_text(html)
    return re.sub(r"^Applications?\s+clos(?:e|ing)\s+on\s+", "", text, flags=re.I).strip()


def _opencities_job_number(url: str) -> str | None:
    match = re.search(r"(R\d+)(?:/?$|[?#])", url, re.I)
    return match.group(1).upper() if match else None


def _is_non_job_navigation_title(platform: str, title: str) -> bool:
    if platform not in {"native_council", "unknown_official"}:
        return False
    normalized = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    if not normalized:
        return False
    blocked_exact = {
        "all vacancies",
        "application process",
        "applying for a position",
        "back to top",
        "career job opportunities",
        "careers",
        "current vacancies",
        "current vacancies portal",
        "early years application information",
        "employee benefits",
        "explore our jobs",
        "employment pathways",
        "faq",
        "help",
        "key selection criteria",
        "job search",
        "jobs",
        "login",
        "print",
        "register",
        "recruitment and selection",
        "search jobs",
        "student placement and work experience",
        "student placements",
        "traineeships and apprenticeships",
        "inclusive employment in wyndham",
        "opportunity wyndham find work",
        "volunteers",
        "volunteering and work experience",
        "work experience",
        "view all job vacancies",
        "view all jobs",
        "view our current job opportunities",
        "view current roles",
        "volunteering at wyndham city council",
        "why choose wyndham city",
        "your recruitment journey",
    }
    return normalized in blocked_exact or normalized.startswith("why work")


def _is_non_job_navigation_link(platform: str, title: str, url: str) -> bool:
    if _is_non_job_navigation_title(platform, title):
        return True
    if platform not in {"native_council", "unknown_official"}:
        return False
    normalized_title = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    blocked_title_fragments = (
        "application process",
        "apply for a job",
        "apply for a position",
        "applying for a position",
        "applying for a job",
        "benefits of working",
        "careers in early years",
        "choose team",
        "click for a list",
        "current opportunities",
        "early years application information",
        "employee benefits",
        "employment opportunities",
        "how to apply",
        "information for applicants",
        "learn about careers",
        "our benefits",
        "our recruitment process",
        "positions vacant",
        "recruitment and selection",
        "select this as your preferred language",
        "skip to main content",
        "staff benefits",
        "student placement",
        "student placements",
        "traineeships and apprenticeships",
        "volunteering",
        "work experience",
        "working at northern grampians",
        "working at team",
        "why join",
    )
    if any(fragment in normalized_title for fragment in blocked_title_fragments):
        return True
    slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(url).path.rstrip("/").split("/")[-1].lower()).strip("-")
    blocked_slugs = {
        "application-process",
        "apply-for-a-job",
        "apply-for-a-job-with-us",
        "applying-for-a-position",
        "applying-for-a-job-with-us",
        "career-job-opportunities",
        "career-opportunities",
        "careers",
        "careers-in-early-years",
        "current-opportunities",
        "current-vacancies",
        "current-vacancies-portal",
        "early-years-application-information",
        "employee-benefits",
        "employment",
        "employment-opportunities",
        "how-to-apply",
        "addressing-the-key-selection-criteria",
        "positions-vacant",
        "our-benefits",
        "recruitment-and-selection",
        "staff-benefits",
        "student-placement-and-work-experience",
        "traineeships-and-apprenticeships",
        "volunteer",
        "volunteering",
        "volunteering-opportunities",
        "why-join-benalla-rural-city-council",
        "why-work-at-stonnington",
        "why-work-with-us",
        "work-experience",
        "work-experience-and-student-placements",
        "working-at-northern-grampians-shire-council",
        "working-at-team-baw-baw",
        "working-with-us",
    }
    return slug in blocked_slugs


def _normalize_job_detail_url(platform: str, url: str) -> str:
    if platform != "recruitmenthub":
        return url
    parsed = urlsplit(url)
    path = re.sub(r"^/about/(?=(?:Vacancies|Current-vacancies)/)", "/", parsed.path, flags=re.I)
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def _title_from_url(url: str) -> str:
    slug = urlsplit(url).path.rstrip("/").split("/")[-1]
    slug = re.sub(r"^[A-Za-z]{1,6}\d{2,}-", "", slug)
    words = [word for word in re.split(r"[-_+]+", slug) if word and not word.isdigit()]
    return " ".join(word.capitalize() for word in words) or "Untitled job"


def _source_job_id(platform: str, url: str) -> str | None:
    path = urlsplit(url).path
    patterns = {
        "pageup": r"/(?:cw/[a-z]{2}/|[a-z]{2}/)job/(\d+)/",
        "pulse": r"/Pulse/job/([^/]+)/",
        "recruitmenthub": r"/(?:Vacancies|Current-vacancies)/(\d+)/",
        "adlogic_martianlogic": r"/(\d+)/?$",
        "applynow": r"/jobs/([A-Za-z0-9]+)",
        "aurion_selfservice": r"/vacancies/([^/]+)/",
        "elmo_talent": r"/careers/[^/]+/job/view/([^/]+)",
        "employmenthero": r"/jobs/position/([^/]+)",
        "smartrecruiters": r"/[^/]+/(\d+)",
        "oracle_hcm": r"/job/([^/]+)$",
        "dayforce": r"/jobs/([^/]+)$",
    }
    pattern = patterns.get(platform)
    if platform == "successfactors":
        match = re.search(r"(?:^|[?&])jobId=([^&]+)", urlsplit(url).query)
        return match.group(1) if match else None
    if platform == "bigredsky":
        match = re.search(r"(?:^|[?&])AdvertID=([^&]+)", urlsplit(url).query)
        return match.group(1) if match else None
    if platform == "secondary_job_slug":
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        return slug or None
    if not pattern:
        return None
    match = re.search(pattern, path)
    return match.group(1) if match else None


def _job_uid(source: dict[str, Any], job_url: str) -> str:
    seed = f"{source.get('short_name') or ''}|{canonicalize_job_url(job_url)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for job in jobs:
        key = canonicalize_job_url(job.get("job_url") or "")
        if key and key not in deduped:
            deduped[key] = job
    return list(deduped.values())
