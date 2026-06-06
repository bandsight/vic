from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urljoin

import requests
from fastapi import HTTPException

from benchmarking_data_factory.workbench.source_documents import (
    SourceDocumentRegister,
    pdf_source_metadata_for_path,
    source_register_fields as source_document_register_fields,
)


@dataclass(frozen=True)
class SourceDocumentIntakeDependencies:
    registry_csv: Callable[[], Path]
    find_pdf: Callable[[str], Path | None]
    now_iso: Callable[[], str]


_source_document_register: SourceDocumentRegister | None = None
_source_register_cache: dict[str, dict[str, str]] | None = None


def clear_source_register_cache() -> None:
    global _source_register_cache
    _source_register_cache = None


def source_document_register(deps: SourceDocumentIntakeDependencies) -> SourceDocumentRegister:
    global _source_document_register, _source_register_cache
    registry_csv = deps.registry_csv()
    if _source_document_register is None or _source_document_register.path != registry_csv:
        _source_document_register = SourceDocumentRegister(registry_csv)
        _source_register_cache = None
    return _source_document_register


def load_registry(registry_csv: Path) -> dict[str, str]:
    registry: dict[str, str] = {}
    if not registry_csv.exists():
        return registry
    with registry_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw_ref = (row.get("discovery_reference") or "").strip()
            source_name = (row.get("source_name") or "").strip()
            if not raw_ref:
                continue
            ae_id = raw_ref.lower()
            if ae_id.endswith(".pdf"):
                ae_id = ae_id[:-4]
            registry[ae_id] = source_name or ae_id
    return registry


def load_source_register_by_ae_id(deps: SourceDocumentIntakeDependencies) -> dict[str, dict[str, str]]:
    global _source_register_cache
    if _source_register_cache is not None:
        return _source_register_cache
    _source_register_cache = source_document_register(deps).load_by_ae_id()
    return _source_register_cache


def source_register_fields() -> list[str]:
    return source_document_register_fields()


def load_source_register_rows(deps: SourceDocumentIntakeDependencies) -> list[dict[str, str]]:
    return source_document_register(deps).load_rows()


def write_source_register_rows(rows: list[dict[str, str]], deps: SourceDocumentIntakeDependencies) -> None:
    global _source_register_cache
    source_document_register(deps).write_rows(rows)
    _source_register_cache = None


def next_source_document_id(rows: list[dict[str, str]], deps: SourceDocumentIntakeDependencies) -> str:
    return source_document_register(deps).next_document_id(rows)


def pdf_source_metadata(ae_id: str, deps: SourceDocumentIntakeDependencies) -> dict[str, Any]:
    return pdf_source_metadata_for_path(deps.find_pdf(ae_id))


def record_frozen_source_document(
    ae_id: str,
    candidate: dict[str, Any],
    pdf_path: Path,
    content_hash: str,
    *,
    already_frozen: bool = False,
    deps: SourceDocumentIntakeDependencies,
) -> dict[str, str]:
    title = str(candidate.get("Agreement Title") or ae_id).strip()
    pdf_url = str(candidate.get("pdf_url") or "").strip()
    return source_document_register(deps).record_frozen_document(
        ae_id=ae_id,
        title=title,
        pdf_url=pdf_url,
        pdf_path=pdf_path,
        content_hash=content_hash,
        pipeline_status=str(candidate.get("pipeline_status") or ""),
        fetched_at=deps.now_iso(),
        already_frozen=already_frozen,
    )


FWC_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 Municipal Benchmark EBA Workbench/1.0"}


def fwc_get(url: str, **kwargs: Any) -> requests.Response:
    headers = {**FWC_REQUEST_HEADERS, **(kwargs.pop("headers", {}) or {})}
    try:
        return requests.get(url, headers=headers, **kwargs)
    except requests.exceptions.SSLError:
        if "://www.fwc.gov.au/" not in url:
            raise
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        return requests.get(url, headers=headers, verify=False, **kwargs)


def fwc_search_terms(ae_id: str, candidate: dict[str, Any] | None = None) -> list[str]:
    candidate = candidate or {}
    terms = [
        ae_id.upper().removesuffix(".PDF"),
        candidate.get("Matter Number"),
        candidate.get("Print ID"),
        candidate.get("Agreement Title"),
    ]
    seen: set[str] = set()
    clean_terms: list[str] = []
    for term in terms:
        clean = str(term or "").strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            clean_terms.append(clean)
    return clean_terms


def fwc_download_link_from_html(html: str) -> str | None:
    matches = re.findall(r'href=["\']([^"\']*/document-view/media/download/\d+[^"\']*)["\']', html, flags=re.I)
    if matches:
        return urljoin("https://www.fwc.gov.au", matches[0])
    settings_match = re.search(
        r'<script[^>]*data-drupal-selector=["\']drupal-settings-json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    if settings_match:
        try:
            settings = json.loads(settings_match.group(1))
            settings_text = json.dumps(settings)
            file_match = re.search(r'"fileUrl"\s*:\s*"([^"]+)"', settings_text)
            if file_match:
                return urljoin("https://www.fwc.gov.au", file_match.group(1))
        except Exception:
            pass
    return None


def find_fwc_document_download_url(
    ae_id: str,
    candidate: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> str | None:
    searched_terms = []
    for term in fwc_search_terms(ae_id, candidate):
        searched_terms.append(term)
        search_url = (
            "https://www.fwc.gov.au/document-search"
            f"?search-ui=agreements&keyword={quote(term)}"
        )
        response = fwc_get(search_url, timeout=(10, 45))
        response.raise_for_status()
        download_url = fwc_download_link_from_html(response.text)
        if download_url:
            return download_url
        wrappers = re.findall(r'href=["\']([^"\']*/document-view/[^"\']+)["\']', response.text, flags=re.I)
        for wrapper in wrappers[:5]:
            wrapper_url = urljoin("https://www.fwc.gov.au", wrapper)
            wrapper_response = fwc_get(wrapper_url, timeout=(10, 45))
            if wrapper_response.status_code != 200:
                continue
            download_url = fwc_download_link_from_html(wrapper_response.text)
            if download_url:
                return download_url
    if errors is not None and searched_terms:
        errors.append(f"FWC Document Search returned no public download for: {', '.join(searched_terms)}")
    return None


def download_pdf_to_path(url: str, destination: Path) -> None:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Candidate PDF URL is not an HTTP(S) address")

    max_bytes = 250 * 1024 * 1024
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    try:
        with fwc_get(
            url,
            stream=True,
            timeout=(10, 120),
        ) as response:
            response.raise_for_status()
            total = 0
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Candidate PDF exceeds the 250 MB intake limit")
                    handle.write(chunk)
        if tmp_path.stat().st_size == 0:
            raise ValueError("Fair Work returned an empty PDF response")
        with tmp_path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError("Fair Work response did not look like a PDF")
        tmp_path.replace(destination)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def freeze_intake_candidate_pdf(
    ae_id: str,
    *,
    force_refresh: bool,
    deps: Any,
) -> dict[str, Any]:
    normalised = ae_id.lower().removesuffix(".pdf")
    candidate = deps.load_candidate_agreements().get(normalised)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Intake candidate not found")

    deps.immutable_dir().mkdir(parents=True, exist_ok=True)
    existing_path = deps.find_pdf(normalised)
    if existing_path is not None and not force_refresh:
        content_hash = deps.sha256_file(existing_path)
        register_row = deps.record_frozen_source_document(
            normalised,
            candidate,
            existing_path,
            content_hash,
            already_frozen=True,
        )
        return {
            "ae_id": normalised,
            "already_frozen": True,
            "content_hash": content_hash,
            "frozen_path": str(existing_path),
            "pdf_source": deps.pdf_source_metadata(normalised),
            "source_register": register_row,
        }

    pdf_url = str(candidate.get("pdf_url") or "").strip()
    if not pdf_url:
        raise HTTPException(status_code=400, detail="Candidate does not include a Fair Work PDF URL")

    destination = deps.immutable_dir() / f"{normalised}.pdf"
    attempted_urls: list[str] = []
    errors: list[str] = []
    resolved_url = pdf_url
    download_urls = [pdf_url]

    try:
        fallback_url = deps.find_fwc_document_download_url(normalised, candidate=candidate, errors=errors)
    except requests.RequestException as exc:
        fallback_url = None
        errors.append(f"FWC Document Search lookup failed: {exc}")
    if fallback_url and fallback_url not in download_urls:
        download_urls.append(fallback_url)

    for download_url in download_urls:
        attempted_urls.append(download_url)
        try:
            deps.download_pdf_to_path(download_url, destination)
            resolved_url = download_url
            break
        except requests.RequestException as exc:
            errors.append(f"{download_url}: {exc}")
        except ValueError as exc:
            errors.append(f"{download_url}: {exc}")
    else:
        superseded_by = str(candidate.get("superseded_by_ae_id") or "").strip()
        superseded_note = ""
        if superseded_by:
            superseded_note = f" This candidate is marked as superseded by {superseded_by.upper()}."
            if deps.find_pdf(superseded_by):
                superseded_note += " The newer source PDF is already fetched locally."
        detail = (
            "Could not fetch this PDF from Fair Work. The saved PDF URL failed and Document Search did not "
            f"return a usable public download.{superseded_note}"
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": detail,
                "agreement_id": normalised.upper(),
                "superseded_by_ae_id": superseded_by.upper() if superseded_by else "",
                "attempted_urls": attempted_urls,
                "errors": errors[-3:],
            },
        )

    content_hash = deps.sha256_file(destination)
    register_row = deps.record_frozen_source_document(
        normalised,
        {**candidate, "pdf_url": resolved_url},
        destination,
        content_hash,
    )
    return {
        "ae_id": normalised,
        "already_frozen": False,
        "content_hash": content_hash,
        "frozen_path": str(destination),
        "pdf_source_url": resolved_url,
        "pdf_source": deps.pdf_source_metadata(normalised),
        "source_register": register_row,
    }
