from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml


YAML_SAFE_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

CanonicalCache = dict[str, tuple[str, int, int, dict[str, Any]]]
RegistryLookup = Callable[[], dict[str, str]]
SplitAeId = Callable[[str], tuple[str, str | None]]
FreshCanonical = Callable[[str, str], dict[str, Any]]
MergeDefaults = Callable[[dict[str, Any], str, str], dict[str, Any]]
DeriveGovernedStatus = Callable[[dict[str, Any]], None]


class CanonicalStore:
    """Read/write canonical agreement YAML with split-agreement fallback."""

    def __init__(
        self,
        *,
        canonical_dir: Path,
        registry_lookup: RegistryLookup,
        split_ae_id: SplitAeId,
        fresh_canonical: FreshCanonical,
        merge_defaults: MergeDefaults,
        derive_governed_status: DeriveGovernedStatus,
        cache: CanonicalCache,
    ):
        self.canonical_dir = canonical_dir
        self.registry_lookup = registry_lookup
        self.split_ae_id = split_ae_id
        self.fresh_canonical = fresh_canonical
        self.merge_defaults = merge_defaults
        self.derive_governed_status = derive_governed_status
        self.cache = cache

    def cache_entry(
        self,
        ae_id: str,
        source_name: str,
        path: Path,
        *,
        actual_ae_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not path.exists():
            return None
        stat = path.stat()
        path_key = str(path)
        cache_key = ae_id.lower()
        cached = self.cache.get(cache_key)
        if cached and cached[0] == path_key and cached[1] == stat.st_mtime_ns and cached[2] == stat.st_size:
            return deepcopy(cached[3])
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=YAML_SAFE_LOADER) or {}
        resolved_ae_id = actual_ae_id or ae_id
        if actual_ae_id:
            data["agreement_id"] = resolved_ae_id
            data["source_name"] = source_name
        merged = self.merge_defaults(data, resolved_ae_id, source_name)
        self.derive_governed_status(merged)
        self.cache[cache_key] = (path_key, stat.st_mtime_ns, stat.st_size, deepcopy(merged))
        return merged

    def get(self, ae_id: str) -> dict[str, Any]:
        ae_id = ae_id.lower()
        registry = self.registry_lookup()
        source_name = registry.get(ae_id, ae_id)
        path = self.canonical_dir / f"{ae_id}.yaml"
        if not path.exists() and "__" in ae_id:
            parent_ae_id, _ = self.split_ae_id(ae_id)
            parent_path = self.canonical_dir / f"{parent_ae_id}.yaml"
            parent_entry = self.cache_entry(ae_id, source_name, parent_path, actual_ae_id=ae_id)
            if parent_entry:
                return parent_entry
        if not path.exists():
            merged = self.fresh_canonical(ae_id, source_name)
            self.derive_governed_status(merged)
            return merged
        cached_entry = self.cache_entry(ae_id, source_name, path)
        if cached_entry:
            return cached_entry
        merged = self.fresh_canonical(ae_id, source_name)
        self.derive_governed_status(merged)
        return merged

    def save(self, ae_id: str, data: dict[str, Any]) -> None:
        self.canonical_dir.mkdir(parents=True, exist_ok=True)
        ae_key = ae_id.lower()
        path = self.canonical_dir / f"{ae_key}.yaml"
        self.derive_governed_status(data)
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
        for key in list(self.cache):
            if key == ae_key or key.startswith(f"{ae_key}__"):
                self.cache.pop(key, None)


__all__ = ["CanonicalCache", "CanonicalStore"]
