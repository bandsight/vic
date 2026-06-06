from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Callable


MULTI_COUNCIL_REGISTER_FIELDS = [
    "ae_id",
    "is_multi",
    "lgas_assigned",
    "parent_content_hash",
    "split_files",
    "decided_by",
    "decided_at",
    "notes",
]


def multi_council_register_fields() -> list[str]:
    return list(MULTI_COUNCIL_REGISTER_FIELDS)


def ensure_multi_council_register(register_path: Path) -> None:
    register_path.parent.mkdir(parents=True, exist_ok=True)
    if register_path.exists():
        return
    with register_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=multi_council_register_fields())
        writer.writeheader()


def lga_slug(short_name: str) -> str:
    return re.sub(r"\s+", "_", short_name.strip().lower())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_multi_council_decisions(register_path: Path) -> dict[str, dict[str, Any]]:
    if not register_path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with register_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ae_id = (row.get("ae_id") or "").strip().lower()
            if not ae_id:
                continue
            rows[ae_id] = {
                "ae_id": ae_id,
                "is_multi": (row.get("is_multi") or "false").strip().lower() == "true",
                "lgas_assigned": [part.strip() for part in (row.get("lgas_assigned") or "").split("|") if part.strip()],
                "parent_content_hash": (row.get("parent_content_hash") or "").strip(),
                "split_files": [part.strip() for part in (row.get("split_files") or "").split("|") if part.strip()],
                "decided_by": (row.get("decided_by") or "human-ui").strip() or "human-ui",
                "decided_at": (row.get("decided_at") or "").strip(),
                "notes": row.get("notes") or "",
            }
    return rows


def write_multi_council_decisions(
    decisions: dict[str, dict[str, Any]],
    register_path: Path,
) -> None:
    ensure_multi_council_register(register_path)
    with register_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=multi_council_register_fields())
        writer.writeheader()
        for row_ae_id in sorted(decisions):
            row = decisions[row_ae_id]
            writer.writerow({
                "ae_id": row_ae_id,
                "is_multi": "true" if row.get("is_multi") else "false",
                "lgas_assigned": "|".join(row.get("lgas_assigned") or []),
                "parent_content_hash": row.get("parent_content_hash") or "",
                "split_files": "|".join(row.get("split_files") or []),
                "decided_by": row.get("decided_by") or "human-ui",
                "decided_at": row.get("decided_at") or "",
                "notes": row.get("notes") or "",
            })


def record_multi_council_decision(
    ae_id: str,
    is_multi: bool,
    lgas_assigned: list[str],
    parent_content_hash: str,
    split_files: list[str],
    notes: str,
    *,
    register_path: Path,
    load_decisions: Callable[[], dict[str, dict[str, Any]]],
    now_iso: Callable[[], str],
) -> None:
    ae_key = ae_id.lower()
    decisions = dict(load_decisions())
    decisions[ae_key] = {
        "ae_id": ae_key,
        "is_multi": is_multi,
        "lgas_assigned": lgas_assigned,
        "parent_content_hash": parent_content_hash,
        "split_files": split_files,
        "decided_by": "human-ui",
        "decided_at": now_iso(),
        "notes": notes,
    }
    write_multi_council_decisions(decisions, register_path)


def split_ae_id(ae_id: str) -> tuple[str, str | None]:
    value = ae_id.lower()
    if "__" not in value:
        return value, None
    parent, _, slug = value.partition("__")
    return parent, slug or None


def split_ae_ids_from_decisions(
    decisions: dict[str, dict[str, Any]],
    *,
    canonical_dir: Path,
) -> set[str]:
    split_ids: set[str] = set()
    for parent_ae_id, decision in decisions.items():
        if not decision.get("is_multi"):
            continue
        added_for_decision = False
        for filename in decision.get("split_files") or []:
            split_id = Path(str(filename)).stem.lower()
            if "__" in split_id:
                split_ids.add(split_id)
                added_for_decision = True
        if not added_for_decision:
            for lga in decision.get("lgas_assigned") or []:
                candidate_id = f"{parent_ae_id}__{lga_slug(lga)}"
                if (canonical_dir / f"{candidate_id}.yaml").exists():
                    split_ids.add(candidate_id)
    return split_ids


def resolve_assigned_lga(
    ae_id: str,
    decision: dict[str, Any] | None = None,
    *,
    decisions: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    parent_ae_id, split_slug = split_ae_id(ae_id)
    decision = decision or (decisions or {}).get(parent_ae_id)
    if split_slug and decision:
        for lga in decision.get("lgas_assigned") or []:
            if lga_slug(lga) == split_slug:
                return lga
    if decision and not decision.get("is_multi"):
        assigned = decision.get("lgas_assigned") or []
        if assigned:
            return assigned[0]
    return None


def resolve_canonical_lga_short_name(
    ae_id: str,
    fetch_metadata: dict[str, Any] | None,
    *,
    decisions: dict[str, dict[str, Any]],
    geography_for_lga: Callable[[str], Any],
) -> str | None:
    parent_ae_id, _ = split_ae_id(ae_id)
    decision = decisions.get(parent_ae_id)
    assigned_lga = resolve_assigned_lga(ae_id, decision, decisions=decisions)
    matched_names = fetch_metadata.get("matched_lga_names") if fetch_metadata else None
    if isinstance(matched_names, list):
        fallback_lga = matched_names[0] if matched_names else None
    elif isinstance(matched_names, str):
        fallback_lga = matched_names.split("|")[0].strip() if matched_names else None
    else:
        fallback_lga = None
    for candidate in [
        assigned_lga,
        fallback_lga,
        fetch_metadata.get("lga_original_name") if fetch_metadata else None,
        fetch_metadata.get("lga_short_name") if fetch_metadata else None,
    ]:
        if candidate and geography_for_lga(candidate):
            return candidate
    return assigned_lga or fallback_lga
