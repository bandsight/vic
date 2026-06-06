from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from benchmarking_data_factory.workbench.application_core import WikiLayerService


WikiLayerServiceFactory = Callable[[], WikiLayerService]


def build_wiki_router_for_service(
    wiki_layer: WikiLayerService | WikiLayerServiceFactory,
) -> APIRouter:
    router = APIRouter()

    def service() -> WikiLayerService:
        return wiki_layer() if callable(wiki_layer) else wiki_layer

    @router.get("/api/wiki/status")
    def api_wiki_status() -> dict[str, Any]:
        return service().status()

    @router.get("/api/wiki/catalog")
    def api_wiki_catalog() -> dict[str, Any]:
        return service().catalog()

    @router.get("/api/wiki/runs")
    def api_wiki_runs(limit: int | None = None) -> dict[str, Any]:
        return service().runs(limit=limit)

    @router.get("/api/wiki/runs/latest")
    def api_wiki_latest_run() -> dict[str, Any]:
        try:
            return service().latest_run()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/runs/{run_id}")
    def api_wiki_run(run_id: str) -> dict[str, Any]:
        try:
            return service().run(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/document-maps")
    def api_wiki_document_maps() -> dict[str, Any]:
        return service().document_maps()

    @router.get("/api/wiki/document-maps/{ae_id}")
    def api_wiki_document_map(ae_id: str) -> dict[str, Any]:
        try:
            return service().document_map(ae_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/reference-inputs")
    def api_wiki_reference_inputs() -> dict[str, Any]:
        return service().reference_inputs()

    @router.get("/api/wiki/reference-inputs/{source_id}")
    def api_wiki_reference_input(source_id: str) -> dict[str, Any]:
        try:
            return service().reference_input(source_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/clause-library")
    def api_wiki_clause_library() -> dict[str, Any]:
        return service().clause_library()

    @router.get("/api/wiki/tag-registry")
    def api_wiki_tag_registry() -> dict[str, Any]:
        return service().tag_registry()

    @router.get("/api/wiki/tagged-evidence")
    def api_wiki_tagged_evidence(
        tag: str | None = None,
        family: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        record_type: str | None = None,
        relevance: str | None = None,
        page_role: str | None = None,
        review_state: str | None = None,
        q: str | None = None,
        limit: int = 160,
        offset: int = 0,
    ) -> dict[str, Any]:
        return service().tagged_evidence(
            tag=tag,
            family=family,
            source_type=source_type,
            source_id=source_id,
            record_type=record_type,
            relevance=relevance,
            page_role=page_role,
            review_state=review_state,
            q=q,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/wiki/gold-comparator-target")
    def api_wiki_gold_comparator_target(
        artifact_id: str = "ballarat-entitlement-benchmark-exemplar",
    ) -> dict[str, Any]:
        try:
            return service().gold_comparator_target(artifact_id=artifact_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/questions")
    def api_wiki_questions(run_id: str | None = None) -> dict[str, Any]:
        try:
            return service().questions(run_id=run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/learning-backlog")
    def api_wiki_learning_backlog(run_id: str | None = None) -> dict[str, Any]:
        try:
            return service().learning_backlog(run_id=run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/language-map")
    def api_wiki_language_map(map_id: str = "clause-context-terms") -> dict[str, Any]:
        try:
            return service().language_map(map_id=map_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/wiki/artifacts")
    def api_wiki_artifacts() -> dict[str, Any]:
        return service().artifacts()

    @router.get("/api/wiki/clause-cards")
    def api_wiki_clause_cards() -> dict[str, Any]:
        return service().clause_cards()

    @router.get("/api/wiki/clause-intelligence")
    def api_wiki_clause_intelligence() -> dict[str, Any]:
        return service().clause_intelligence_review()

    @router.get("/api/wiki/entitlement-test-matrix")
    def api_wiki_entitlement_test_matrix() -> dict[str, Any]:
        return service().entitlement_test_matrix()

    return router
