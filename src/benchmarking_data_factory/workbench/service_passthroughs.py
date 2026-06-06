from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from benchmarking_data_factory.workbench import canonical_workflow as canonical_workflow_module
from benchmarking_data_factory.workbench import document_page_workflow as document_page_workflow_module
from benchmarking_data_factory.workbench import intake_state as intake_state_module
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import multi_council_decisions as multi_council_decisions_module
from benchmarking_data_factory.workbench import source_document_intake as source_document_intake_module


def bind_intake_state_passthroughs(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def invalidate_intake_quality(reason: str) -> None:
        service = getattr(ctx, "_intake_quality_service", None)
        if service is not None:
            service.invalidate(reason)

    def load_candidate_agreement_rows() -> list[dict[str, Any]]:
        ctx._candidate_agreement_rows_cache = intake_state_module.load_candidate_agreement_rows(
            ctx.CANDIDATE_AGREEMENTS_JSON,
            ctx._candidate_agreement_rows_cache,
        )
        return ctx._candidate_agreement_rows_cache

    def load_candidate_agreements() -> dict[str, dict[str, Any]]:
        ctx._candidate_agreements_cache = intake_state_module.load_candidate_agreements(
            ctx.load_candidate_agreement_rows()
        )
        return ctx._candidate_agreements_cache

    def clear_intake_source_caches() -> None:
        ctx._candidate_agreement_rows_cache = None
        ctx._candidate_agreements_cache = None
        ctx._source_register_cache = None
        source_document_intake_module.clear_source_register_cache()
        invalidate_intake_quality("intake_source_cache_clear")

    def load_intake_decisions() -> dict[str, dict[str, Any]]:
        ctx._intake_decisions_cache = intake_state_module.load_intake_decisions(
            ctx.INTAKE_DECISIONS_JSON,
            ctx._intake_decisions_cache,
        )
        return ctx._intake_decisions_cache

    def save_intake_decisions(decisions: dict[str, dict[str, Any]]) -> None:
        intake_state_module.save_intake_decisions(decisions, ctx.INTAKE_DECISIONS_JSON)
        ctx._intake_decisions_cache = decisions
        invalidate_intake_quality("intake_decision_save")

    def record_intake_decision(ae_id: str, status: str, reason: str = "", notes: str = "") -> dict[str, Any]:
        decisions, decision = intake_state_module.record_intake_decision(
            ae_id,
            status,
            reason,
            notes,
            ctx.load_intake_decisions(),
            now_iso=ctx.now_iso,
        )
        ctx.save_intake_decisions(decisions)
        return decision

    def fetch_metadata_for_ae_id(
        ae_id: str,
        decisions: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return intake_state_module.fetch_metadata_for_ae_id(
            ae_id,
            load_candidate_agreements=ctx.load_candidate_agreements,
            split_ae_id=ctx.split_ae_id,
            load_multi_council_decisions=ctx.load_multi_council_decisions,
            resolve_assigned_lga=ctx.resolve_assigned_lga,
            decisions=decisions,
        )

    namespace.update({
        "load_candidate_agreement_rows": load_candidate_agreement_rows,
        "load_candidate_agreements": load_candidate_agreements,
        "clear_intake_source_caches": clear_intake_source_caches,
        "load_intake_decisions": load_intake_decisions,
        "save_intake_decisions": save_intake_decisions,
        "record_intake_decision": record_intake_decision,
        "fetch_metadata_for_ae_id": fetch_metadata_for_ae_id,
    })


def bind_source_document_passthroughs(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def invalidate_intake_quality(reason: str) -> None:
        service = getattr(ctx, "_intake_quality_service", None)
        if service is not None:
            service.invalidate(reason)

    def source_document_register():
        return source_document_intake_module.source_document_register(ctx._source_document_intake_dependencies())

    def load_registry() -> dict[str, str]:
        return source_document_intake_module.load_registry(ctx.REGISTRY_CSV)

    def load_source_register_by_ae_id() -> dict[str, dict[str, str]]:
        if ctx._source_register_cache is not None:
            return ctx._source_register_cache
        ctx._source_register_cache = source_document_intake_module.load_source_register_by_ae_id(
            ctx._source_document_intake_dependencies()
        )
        return ctx._source_register_cache

    def source_register_fields() -> list[str]:
        return source_document_intake_module.source_register_fields()

    def load_source_register_rows() -> list[dict[str, str]]:
        return source_document_intake_module.load_source_register_rows(ctx._source_document_intake_dependencies())

    def write_source_register_rows(rows: list[dict[str, str]]) -> None:
        source_document_intake_module.write_source_register_rows(rows, ctx._source_document_intake_dependencies())
        ctx._source_register_cache = None

    def next_source_document_id(rows: list[dict[str, str]]) -> str:
        return source_document_intake_module.next_source_document_id(rows, ctx._source_document_intake_dependencies())

    def fwc_get(url: str, **kwargs: Any):
        return source_document_intake_module.fwc_get(url, **kwargs)

    def _fwc_search_terms(ae_id: str, candidate: dict[str, Any] | None = None) -> list[str]:
        return source_document_intake_module.fwc_search_terms(ae_id, candidate)

    def _fwc_download_link_from_html(html: str) -> str | None:
        return source_document_intake_module.fwc_download_link_from_html(html)

    def find_fwc_document_download_url(
        ae_id: str,
        candidate: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> str | None:
        return source_document_intake_module.find_fwc_document_download_url(ae_id, candidate, errors)

    def download_pdf_to_path(url: str, destination) -> None:
        source_document_intake_module.download_pdf_to_path(url, destination)

    def pdf_source_metadata(ae_id: str) -> dict[str, Any]:
        return source_document_intake_module.pdf_source_metadata(ae_id, ctx._source_document_intake_dependencies())

    def record_frozen_source_document(
        ae_id: str,
        candidate: dict[str, Any],
        pdf_path,
        content_hash: str,
        *,
        already_frozen: bool = False,
    ) -> dict[str, str]:
        result = source_document_intake_module.record_frozen_source_document(
            ae_id,
            candidate,
            pdf_path,
            content_hash,
            already_frozen=already_frozen,
            deps=ctx._source_document_intake_dependencies(),
        )
        invalidate_intake_quality("source_document_freeze")
        return result

    def freeze_intake_candidate_pdf(ae_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        return intake_workflow_module.freeze_intake_candidate_pdf(
            ae_id,
            force_refresh=force_refresh,
            deps=ctx._intake_workflow_dependencies(),
        )

    namespace.update({
        "source_document_register": source_document_register,
        "load_registry": load_registry,
        "load_source_register_by_ae_id": load_source_register_by_ae_id,
        "source_register_fields": source_register_fields,
        "load_source_register_rows": load_source_register_rows,
        "write_source_register_rows": write_source_register_rows,
        "next_source_document_id": next_source_document_id,
        "fwc_get": fwc_get,
        "_fwc_search_terms": _fwc_search_terms,
        "_fwc_download_link_from_html": _fwc_download_link_from_html,
        "find_fwc_document_download_url": find_fwc_document_download_url,
        "download_pdf_to_path": download_pdf_to_path,
        "pdf_source_metadata": pdf_source_metadata,
        "record_frozen_source_document": record_frozen_source_document,
        "freeze_intake_candidate_pdf": freeze_intake_candidate_pdf,
    })


def bind_multi_council_passthroughs(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def multi_council_register_fields() -> list[str]:
        return multi_council_decisions_module.multi_council_register_fields()

    def ensure_multi_council_register() -> None:
        multi_council_decisions_module.ensure_multi_council_register(ctx.MULTI_COUNCIL_REGISTER)

    def lga_slug(short_name: str) -> str:
        return multi_council_decisions_module.lga_slug(short_name)

    def sha256_file(path) -> str:
        return multi_council_decisions_module.sha256_file(path)

    def load_multi_council_decisions() -> dict[str, dict[str, Any]]:
        if ctx._multi_council_cache is not None:
            return ctx._multi_council_cache
        ctx._multi_council_cache = multi_council_decisions_module.load_multi_council_decisions(
            ctx.MULTI_COUNCIL_REGISTER
        )
        return ctx._multi_council_cache

    def record_multi_council_decision(
        ae_id: str,
        is_multi: bool,
        lgas_assigned: list[str],
        parent_content_hash: str,
        split_files: list[str],
        notes: str = "",
    ) -> None:
        multi_council_decisions_module.record_multi_council_decision(
            ae_id,
            is_multi,
            lgas_assigned,
            parent_content_hash,
            split_files,
            notes,
            register_path=ctx.MULTI_COUNCIL_REGISTER,
            load_decisions=ctx.load_multi_council_decisions,
            now_iso=ctx.now_iso,
        )
        ctx._multi_council_cache = None

    def split_ae_id(ae_id: str) -> tuple[str, str | None]:
        return multi_council_decisions_module.split_ae_id(ae_id)

    def split_ae_ids_from_decisions(decisions: dict[str, dict[str, Any]]) -> set[str]:
        return multi_council_decisions_module.split_ae_ids_from_decisions(
            decisions,
            canonical_dir=ctx.CANONICAL_DIR,
        )

    def resolve_assigned_lga(ae_id: str, decision: dict[str, Any] | None = None) -> str | None:
        return multi_council_decisions_module.resolve_assigned_lga(
            ae_id,
            decision,
            decisions=ctx.load_multi_council_decisions(),
        )

    def resolve_canonical_lga_short_name(
        ae_id: str,
        fetch_metadata: dict[str, Any] | None,
        decisions: dict[str, dict[str, Any]] | None = None,
    ) -> str | None:
        return multi_council_decisions_module.resolve_canonical_lga_short_name(
            ae_id,
            fetch_metadata,
            decisions=decisions or ctx.load_multi_council_decisions(),
            geography_for_lga=ctx.geography_for_lga,
        )

    def write_multi_council_decisions(decisions: dict[str, dict[str, Any]]) -> None:
        multi_council_decisions_module.write_multi_council_decisions(decisions, ctx.MULTI_COUNCIL_REGISTER)
        ctx._multi_council_cache = None

    namespace.update({
        "multi_council_register_fields": multi_council_register_fields,
        "ensure_multi_council_register": ensure_multi_council_register,
        "lga_slug": lga_slug,
        "sha256_file": sha256_file,
        "load_multi_council_decisions": load_multi_council_decisions,
        "record_multi_council_decision": record_multi_council_decision,
        "split_ae_id": split_ae_id,
        "split_ae_ids_from_decisions": split_ae_ids_from_decisions,
        "resolve_assigned_lga": resolve_assigned_lga,
        "resolve_canonical_lga_short_name": resolve_canonical_lga_short_name,
        "write_multi_council_decisions": write_multi_council_decisions,
    })


def bind_document_page_passthroughs(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def list_pdfs() -> list[str]:
        return document_page_workflow_module.list_pdfs(ctx._document_page_workflow_dependencies())

    def _document_page_service():
        return document_page_workflow_module.document_page_service(ctx._document_page_workflow_dependencies())

    def _document_page_http_exception(exc: Exception, ae_id: str | None = None):
        return document_page_workflow_module.document_page_http_exception(exc, ae_id)

    def find_pdf(ae_id: str):
        return document_page_workflow_module.find_pdf(ae_id, ctx._document_page_workflow_dependencies())

    def pdf_path_for(ae_id: str):
        return document_page_workflow_module.pdf_path_for(ae_id, ctx._document_page_workflow_dependencies())

    def ensure_cache_dir(ae_id: str):
        return document_page_workflow_module.ensure_cache_dir(ae_id, ctx._document_page_workflow_dependencies())

    def _require_fitz() -> None:
        document_page_workflow_module.require_fitz(ctx._document_page_workflow_dependencies())

    def get_page_count(ae_id: str) -> int:
        return document_page_workflow_module.get_page_count(ae_id, ctx._document_page_workflow_dependencies())

    def extract_page_text(ae_id: str, page_num: int) -> str:
        return document_page_workflow_module.extract_page_text(
            ae_id,
            page_num,
            ctx._document_page_workflow_dependencies(),
        )

    def extract_all_page_texts(ae_id: str) -> list[str]:
        return document_page_workflow_module.extract_all_page_texts(ae_id, ctx._document_page_workflow_dependencies())

    def extract_full_text(ae_id: str) -> str:
        return document_page_workflow_module.extract_full_text(ae_id, ctx._document_page_workflow_dependencies())

    def render_page_png(ae_id: str, page_num: int, dpi: int | None = None) -> bytes:
        return document_page_workflow_module.render_page_png(
            ae_id,
            page_num,
            ctx._document_page_workflow_dependencies(),
            dpi=ctx.PAGE_RENDER_DPI if dpi is None else dpi,
        )

    def find_candidate_pages(ae_id: str, pattern) -> list[int]:
        return document_page_workflow_module.find_candidate_pages(
            ae_id,
            pattern,
            ctx._document_page_workflow_dependencies(),
        )

    def collect_uplift_pages_text(ae_id: str, max_pages: int = 6) -> list[dict[str, Any]]:
        return document_page_workflow_module.collect_uplift_pages_text(
            ae_id,
            ctx._document_page_workflow_dependencies(),
            max_pages=max_pages,
        )

    namespace.update({
        "list_pdfs": list_pdfs,
        "_document_page_service": _document_page_service,
        "_document_page_http_exception": _document_page_http_exception,
        "find_pdf": find_pdf,
        "pdf_path_for": pdf_path_for,
        "ensure_cache_dir": ensure_cache_dir,
        "_require_fitz": _require_fitz,
        "get_page_count": get_page_count,
        "extract_page_text": extract_page_text,
        "extract_all_page_texts": extract_all_page_texts,
        "extract_full_text": extract_full_text,
        "render_page_png": render_page_png,
        "find_candidate_pages": find_candidate_pages,
        "collect_uplift_pages_text": collect_uplift_pages_text,
    })


def bind_canonical_passthroughs(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def fresh_canonical(ae_id: str, source_name: str) -> dict[str, Any]:
        return canonical_workflow_module.fresh_canonical(ae_id, source_name)

    def merge_defaults(data: dict[str, Any], ae_id: str, source_name: str) -> dict[str, Any]:
        return canonical_workflow_module.merge_defaults(data, ae_id, source_name)

    def _derive_governed_set_status(canonical: dict[str, Any]) -> None:
        canonical_workflow_module.derive_governed_set_status(canonical, ctx._canonical_workflow_dependencies())

    def _canonical_store():
        return canonical_workflow_module.canonical_store(ctx._canonical_workflow_dependencies(), ctx._canonical_cache)

    def _canonical_cache_entry(
        ae_id: str,
        source_name: str,
        path,
        *,
        actual_ae_id: str | None = None,
    ) -> dict[str, Any] | None:
        return canonical_workflow_module.cache_entry(
            ae_id,
            source_name,
            path,
            actual_ae_id=actual_ae_id,
            deps=ctx._canonical_workflow_dependencies(),
            cache=ctx._canonical_cache,
        )

    def get_canonical(ae_id: str) -> dict[str, Any]:
        return canonical_workflow_module.get_canonical(
            ae_id,
            ctx._canonical_workflow_dependencies(),
            ctx._canonical_cache,
        )

    def save_canonical(ae_id: str, data: dict[str, Any]) -> None:
        canonical_workflow_module.save_canonical(
            ae_id,
            data,
            ctx._canonical_workflow_dependencies(),
            ctx._canonical_cache,
        )

    namespace.update({
        "fresh_canonical": fresh_canonical,
        "merge_defaults": merge_defaults,
        "_derive_governed_set_status": _derive_governed_set_status,
        "_canonical_store": _canonical_store,
        "_canonical_cache_entry": _canonical_cache_entry,
        "get_canonical": get_canonical,
        "save_canonical": save_canonical,
    })
