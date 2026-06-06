from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
OUT_DIR = ROOT / "exports" / "product-memory-os"


CORE_DOCS = [
    ("product_architecture", ROOT / "PRODUCT_ARCHITECTURE.md", "North-star product architecture and module contracts."),
    ("current_state", ROOT / "CURRENT_STATE_AND_NEXT_ACTIONS.md", "Observed workspace state, counts, tests, and next actions."),
    ("wiki_goal", ROOT / "WIKI_LAYER_GOAL.md", "Clause Evidence Graph, wiki, and learning-loop doctrine."),
    ("report_asset_contract", ROOT / "REPORT_ASSET_CONTRACT.md", "Report-ready asset lifecycle and metadata contract."),
    ("agent_manifest", ROOT / "workbench-agent.json", "Agent I/O boundary, commands, safe paths, and discoverable datasets."),
    ("portable_manifest", ROOT / "PORTABLE_MANIFEST.json", "Packaging profiles and portability policy."),
    ("brand_register", PARENT / "brand-guide" / "09_notes" / "asset-register.md", "Municipal Benchmark brand-board custody and visual system register."),
    ("codex_topic_map", PARENT / "codex-desktop-topics" / "topic-map.json", "Extracted Codex Desktop thread and topic memory index."),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def doc_record(key: str, path: Path, role: str) -> dict[str, Any]:
    text = read_text(path)
    return {
        "key": key,
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "exists": path.exists(),
        "role": role,
        "heading": first_heading(text),
        "line_count": len(text.splitlines()) if text else 0,
        "word_count": len(text.split()) if text else 0,
        "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def datamart_statuses() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((ROOT / "data" / "datamarts").glob("*_status.json")):
        obj = load_json(path)
        rows.append(
            {
                "mart_id": obj.get("mart_id", path.stem.replace("_status", "")),
                "status": obj.get("status"),
                "row_count": obj.get("row_count"),
                "generated_at": obj.get("generated_at"),
                "contract": obj.get("contract"),
                "caveat_count": len(obj.get("caveats", []) or []),
                "recommended_next_action": obj.get("recommended_next_action"),
            }
        )
    return rows


def latest_files(base: Path, limit: int = 12) -> list[dict[str, Any]]:
    if not base.exists():
        return []
    files = sorted([p for p in base.rglob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [
        {
            "path": str(p.relative_to(ROOT)),
            "bytes": p.stat().st_size,
            "last_modified": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for p in files
    ]


def topic_summary() -> dict[str, Any]:
    topic_map = load_json(PARENT / "codex-desktop-topics" / "topic-map.json")
    return {
        "thread_count": len(topic_map.get("threads", []) or []),
        "topic_count": len(topic_map.get("topics", []) or []),
        "topics": topic_map.get("topics", []) or [],
        "threads": topic_map.get("threads", []) or [],
    }


def wiki_summary() -> dict[str, Any]:
    manifest = load_json(ROOT / "wiki" / "wiki-manifest.json")
    return {
        "manifest": manifest,
        "latest_run": manifest.get("latest_run_id"),
        "recent_artifacts": latest_files(ROOT / "wiki" / "artifacts", 10),
        "recent_questions": latest_files(ROOT / "wiki" / "questions", 5),
        "recent_runs": latest_files(ROOT / "wiki" / "runs", 5),
    }


def report_summary() -> dict[str, Any]:
    return {
        "master_report": latest_files(ROOT / "exports" / "ballarat-master-remuneration-report", 10),
        "report_assets": latest_files(ROOT / "exports" / "report-assets", 10),
        "executive_report_prototypes": latest_files(ROOT / "exports" / "ballarat-executive-report", 10),
    }


def operating_loops() -> list[dict[str, Any]]:
    return [
        {
            "loop": "Capture",
            "purpose": "Turn new chats, user corrections, decisions, and report learnings into durable memory records.",
            "cadence": "After each substantial work session.",
            "primary_surface": "docs/municipal-benchmark-product-memory-os.md plus optional Notion mirror.",
            "quality_gate": "Every captured item has a source, owner, status, and next action.",
        },
        {
            "loop": "Govern",
            "purpose": "Keep raw extraction, proposed knowledge, accepted wiki knowledge, governed datasets, and report-ready assets separate.",
            "cadence": "Before data is used in reports.",
            "primary_surface": "REPORT_ASSET_CONTRACT.md, WIKI_LAYER_GOAL.md, datamart status JSON.",
            "quality_gate": "No report claim without a declared source layer and caveat state.",
        },
        {
            "loop": "Index",
            "purpose": "Regenerate the product-memory index so agents can find the correct source of truth first.",
            "cadence": "Before long-running goals and after major artifact creation.",
            "primary_surface": "scripts/build_product_memory_os.py.",
            "quality_gate": "Generated index includes docs, datamarts, wiki, reports, topic memory, and artifacts.",
        },
        {
            "loop": "Produce",
            "purpose": "Convert governed evidence into report, deck, doc, workbook, and visual assets.",
            "cadence": "Per council/report objective.",
            "primary_surface": "exports, report asset manifests, report builders.",
            "quality_gate": "Rendered visual QA and data-pack audit pass before delivery.",
        },
        {
            "loop": "Improve",
            "purpose": "Use failures, corrections, and user criticism to update standards, prompts, profiles, and memory.",
            "cadence": "Weekly or after high-friction work.",
            "primary_surface": "wiki learning backlog, goal docs, future Linear/Notion task layer.",
            "quality_gate": "Every improvement has a concrete target artifact or workflow impact.",
        },
    ]


def goal_backlog() -> list[dict[str, Any]]:
    return [
        {
            "id": "goal.report_factory",
            "name": "World-class report factory",
            "status": "active",
            "next_action": "Promote the Ballarat master-report seed into a source-linked, costed, reusable report builder.",
        },
        {
            "id": "goal.memory_os",
            "name": "Municipal Benchmark Product and Memory OS",
            "status": "active",
            "next_action": "Use this generated index as the preflight map for every long-running goal.",
        },
        {
            "id": "goal.total_employment_value",
            "name": "Governed total employment value layer",
            "status": "queued",
            "next_action": "Convert entitlement draft takeaways into source-backed, reviewable profiles by standard-employee scope.",
        },
        {
            "id": "goal.notion_hub",
            "name": "Notion memory hub",
            "status": "queued",
            "next_action": "Mirror a slim executive hub into Notion after the local OS is stable.",
        },
        {
            "id": "goal.plugin_routes",
            "name": "Plugin usage routes",
            "status": "queued",
            "next_action": "Define when to use Browser, Documents, Presentations, Spreadsheets, Notion, Linear, and HyperFrames.",
        },
    ]


def build_index() -> dict[str, Any]:
    docs = [doc_record(*item) for item in CORE_DOCS]
    statuses = datamart_statuses()
    return {
        "schema_version": "municipal_benchmark.product_memory_os.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "north_star": "Municipal Benchmark is a governed civic intelligence workbench and report factory, not a loose collection of scripts or chats.",
        "authority_order": [
            "Frozen source PDFs and governed canonical data.",
            "Reviewed wiki knowledge, datamart status files, and report asset manifests.",
            "Product architecture, current-state notes, and goal command-center docs.",
            "Generated indexes and briefs.",
            "Notion mirrors and meeting/documentation pages.",
            "Raw chat memory and unreviewed suggestions.",
        ],
        "core_documents": docs,
        "datamart_statuses": statuses,
        "datamart_rollup": {
            "mart_count": len(statuses),
            "built": sum(1 for row in statuses if row.get("status") == "built"),
            "partial": sum(1 for row in statuses if row.get("status") == "partial"),
            "total_rows": sum(int(row.get("row_count") or 0) for row in statuses),
        },
        "topic_memory": topic_summary(),
        "wiki": wiki_summary(),
        "reports": report_summary(),
        "operating_loops": operating_loops(),
        "goal_backlog": goal_backlog(),
        "plugin_policy": {
            "notion": "Capture executive decisions, meeting-ready briefs, and a slim memory hub. Do not treat Notion as the governed data store.",
            "browser": "Run visual QA on local apps and report HTML/PDF surfaces.",
            "spreadsheets": "Create auditable workbooks, scenario models, and source-backed data tables.",
            "documents": "Produce polished DOCX artifacts after render-and-inspect QA.",
            "presentations": "Build executive decks from governed report assets.",
            "linear": "Track implementation tasks if the user wants product-management discipline.",
            "hyperframes": "Create high-end video/animated explainers from stable report or product assets.",
        },
    }


def write_brief(index: dict[str, Any]) -> str:
    lines = [
        "# Municipal Benchmark Product And Memory OS Brief",
        "",
        f"Generated: {index['generated_at']}",
        "",
        "## North Star",
        "",
        index["north_star"],
        "",
        "## Authority Order",
        "",
    ]
    lines.extend(f"{i}. {item}" for i, item in enumerate(index["authority_order"], start=1))
    lines.extend(["", "## Current Memory Surfaces", ""])
    for doc in index["core_documents"]:
        state = "present" if doc["exists"] else "missing"
        lines.append(f"- {doc['key']}: {state}, {doc['line_count']} lines. {doc['role']}")
    lines.extend(["", "## Datamart Rollup", ""])
    rollup = index["datamart_rollup"]
    lines.append(f"- {rollup['mart_count']} status files; {rollup['built']} built; {rollup['partial']} partial; {rollup['total_rows']:,} rows reported across status files.")
    lines.extend(["", "## Operating Loops", ""])
    for loop in index["operating_loops"]:
        lines.append(f"- {loop['loop']}: {loop['purpose']} Cadence: {loop['cadence']}")
    lines.extend(["", "## Goal Backlog", ""])
    for goal in index["goal_backlog"]:
        lines.append(f"- {goal['id']} [{goal['status']}]: {goal['next_action']}")
    lines.extend(["", "## Plugin Policy", ""])
    for plugin, policy in index["plugin_policy"].items():
        lines.append(f"- {plugin}: {policy}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = build_index()
    (OUT_DIR / "product-memory-os-index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "product-memory-os-brief.md").write_text(write_brief(index), encoding="utf-8")
    print(json.dumps({
        "index": str(OUT_DIR / "product-memory-os-index.json"),
        "brief": str(OUT_DIR / "product-memory-os-brief.md"),
        "datamart_marts": index["datamart_rollup"]["mart_count"],
        "core_docs": len(index["core_documents"]),
    }, indent=2))


if __name__ == "__main__":
    main()
