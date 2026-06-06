from __future__ import annotations

import re
from typing import Any, Callable


_COUNCIL_AUDIT_RENAME_ALIASES: dict[str, str] = {
    "moreland": "merri bek",
    "moreland city": "merri bek",
    "city of moreland": "merri bek",
    "moreland city council": "merri bek",
}


def _audit_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _audit_compact_key(value: Any) -> str:
    return _audit_key(value).replace(" ", "")


def _audit_target_keys(value: Any) -> set[str]:
    base = _audit_key(value)
    keys = {base} if base else set()
    if base in _COUNCIL_AUDIT_RENAME_ALIASES:
        keys.add(_COUNCIL_AUDIT_RENAME_ALIASES[base])
    if "merri bek" in keys:
        keys.update(alias for alias, target in _COUNCIL_AUDIT_RENAME_ALIASES.items() if target == "merri bek")
    return {key for key in keys if key}


def _audit_matches_any_name(names: list[Any], target_keys: set[str]) -> bool:
    compact_targets = {_audit_compact_key(key) for key in target_keys if key}
    for name in names:
        key = _audit_key(name)
        if not key:
            continue
        if key in target_keys or _audit_compact_key(key) in compact_targets:
            return True
    return False


def audit_council_reference(
    council_name: str,
    *,
    load_canonical_councils: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    target_keys = _audit_target_keys(council_name)
    for row in load_canonical_councils():
        names = [row.get("short_name"), row.get("long_name")]
        if _audit_matches_any_name(names, target_keys):
            return {
                "short_name": row.get("short_name") or council_name,
                "long_name": row.get("long_name") or row.get("short_name") or council_name,
                "status": row.get("status") or "",
                "category": row.get("council_category") or "",
            }
    canonical_name = "Merri-bek" if "merri bek" in target_keys else council_name
    return {
        "short_name": canonical_name,
        "long_name": canonical_name,
        "status": "",
        "category": "",
    }


def audit_candidate_council_names(
    row: dict[str, Any],
    *,
    candidate_lgas: Callable[[dict[str, Any]], list[str]],
) -> list[str]:
    names = list(candidate_lgas(row))
    for key in ("lga_short_name", "lga_original_name", "Council", "council"):
        value = row.get(key)
        if value and str(value).strip() not in names:
            names.append(str(value).strip())
    return names


def audit_candidate_matches_council(
    row: dict[str, Any],
    target_keys: set[str],
    *,
    candidate_lgas: Callable[[dict[str, Any]], list[str]],
) -> bool:
    if _audit_matches_any_name(audit_candidate_council_names(row, candidate_lgas=candidate_lgas), target_keys):
        return True
    lineage_key = str(row.get("lineage_key") or "")
    if lineage_key:
        lineage_head = lineage_key.split("::", 1)[0]
        if _audit_matches_any_name([lineage_head], target_keys):
            return True
    return False
