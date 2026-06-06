from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from benchmarking_data_factory.workbench.canonical_agreement import (
    fresh_canonical as canonical_fresh_canonical,
    merge_defaults as canonical_merge_defaults,
)
from benchmarking_data_factory.workbench.canonical_store import CanonicalCache, CanonicalStore


@dataclass(frozen=True)
class CanonicalWorkflowDependencies:
    canonical_dir: Callable[[], Path]
    load_registry: Callable[[], dict[str, str]]
    split_ae_id: Callable[[str], tuple[str, str | None]]
    derive_governed_set_status: Callable[[dict[str, Any]], None]


def fresh_canonical(ae_id: str, source_name: str) -> dict[str, Any]:
    return canonical_fresh_canonical(ae_id, source_name)


def merge_defaults(data: dict[str, Any], ae_id: str, source_name: str) -> dict[str, Any]:
    return canonical_merge_defaults(data, ae_id, source_name)


def derive_governed_set_status(canonical: dict[str, Any], deps: CanonicalWorkflowDependencies) -> None:
    deps.derive_governed_set_status(canonical)


def canonical_store(deps: CanonicalWorkflowDependencies, cache: CanonicalCache) -> CanonicalStore:
    return CanonicalStore(
        canonical_dir=deps.canonical_dir(),
        registry_lookup=deps.load_registry,
        split_ae_id=deps.split_ae_id,
        fresh_canonical=fresh_canonical,
        merge_defaults=merge_defaults,
        derive_governed_status=lambda canonical: derive_governed_set_status(canonical, deps),
        cache=cache,
    )


def cache_entry(
    ae_id: str,
    source_name: str,
    path: Path,
    *,
    actual_ae_id: str | None,
    deps: CanonicalWorkflowDependencies,
    cache: CanonicalCache,
) -> dict[str, Any] | None:
    return canonical_store(deps, cache).cache_entry(ae_id, source_name, path, actual_ae_id=actual_ae_id)


def get_canonical(ae_id: str, deps: CanonicalWorkflowDependencies, cache: CanonicalCache) -> dict[str, Any]:
    return canonical_store(deps, cache).get(ae_id)


def save_canonical(
    ae_id: str,
    data: dict[str, Any],
    deps: CanonicalWorkflowDependencies,
    cache: CanonicalCache,
) -> None:
    canonical_store(deps, cache).save(ae_id, data)
