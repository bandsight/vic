from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape as html_escape
import json
from pathlib import Path
import struct
from typing import Any, Callable
import zipfile
import zlib


REPORT_ASSET_REQUIRED_FIELDS = [
    "asset_id",
    "asset_type",
    "title",
    "report_title_candidate",
    "report_subtitle_candidate",
    "source_dataset",
    "source_dataset_version",
    "generated_at",
    "generated_by",
    "filters",
    "metric_definition",
    "pay_metric_set",
    "default_pay_metric",
    "available_pay_metrics",
    "blocked_pay_metrics",
    "metric_caveats",
    "visual_encoding",
    "quality_flags",
    "provenance",
    "operator_note",
    "export_targets",
    "status",
]

REPORT_ASSET_STATUS_ORDER = ["draft", "reviewed", "report_ready", "superseded", "rejected"]
REPORT_ASSET_STATUSES = set(REPORT_ASSET_STATUS_ORDER)
REPORT_ASSET_TYPES = {"chart", "table", "audit_extract", "observation", "image_export"}
REPORT_EXPORT_FORMATS = ["csv", "svg", "png", "xlsx", "docx", "pptx"]
REPORT_EXPORT_COLUMNS = [
    "analysis_id",
    "ae_id",
    "agreement_name",
    "canonical_lga_short_name",
    "quarter_start",
    "band",
    "min_level",
    "min_weekly_rate",
    "max_level",
    "max_weekly_rate",
    "midpoint_weekly_rate",
    "comparison_metric",
    "comparison_metric_label",
    "entry_weekly_rate",
    "capacity_weekly_rate",
    "service_year_1_weekly_rate",
    "service_year_2_weekly_rate",
    "service_year_3_weekly_rate",
    "service_year_4_weekly_rate",
    "service_year_5_weekly_rate",
    "service_year_6_weekly_rate",
    "max_level_point_weekly_rate",
    "calculation_status",
    "source_basis",
    "is_known_value",
    "is_projected_value",
]


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": "invalid_json",
            "path": path.name,
        }


def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
        }
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


@dataclass(frozen=True)
class ReportAssetService:
    paths: Any
    now: Callable[[], str] | None = None

    def _now_iso(self) -> str:
        if self.now is not None:
            return self.now()
        return datetime.now(timezone.utc).isoformat()

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.paths.root))
        except ValueError:
            return str(path)

    def contract_path(self) -> Path:
        return self.paths.root / "REPORT_ASSET_CONTRACT.md"

    def distribution_point_analysis_manifest_path(self) -> Path:
        return self.paths.distribution_point_analysis_json.with_name("distribution-point-analysis.asset.json")

    def required_fields(self) -> list[str]:
        return list(REPORT_ASSET_REQUIRED_FIELDS)

    def load_distribution_point_analysis_manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.distribution_point_analysis_manifest_path())

    def validate_manifest(self, manifest: dict[str, Any] | None) -> dict[str, Any]:
        if not manifest:
            return {
                "valid": False,
                "missing_required_fields": self.required_fields(),
                "invalid_fields": [],
            }
        missing = [field for field in self.required_fields() if field not in manifest]
        invalid: list[str] = []
        if manifest.get("asset_type") not in REPORT_ASSET_TYPES:
            invalid.append("asset_type")
        if manifest.get("status") not in REPORT_ASSET_STATUSES:
            invalid.append("status")
        if not isinstance(manifest.get("filters"), dict):
            invalid.append("filters")
        if not isinstance(manifest.get("visual_encoding"), dict):
            invalid.append("visual_encoding")
        if not isinstance(manifest.get("quality_flags"), list):
            invalid.append("quality_flags")
        if not isinstance(manifest.get("provenance"), dict):
            invalid.append("provenance")
        if not isinstance(manifest.get("export_targets"), list):
            invalid.append("export_targets")
        return {
            "valid": not missing and not invalid,
            "missing_required_fields": missing,
            "invalid_fields": invalid,
        }

    def distribution_point_analysis_manifest(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        summary = analysis_payload.get("summary") if isinstance(analysis_payload.get("summary"), dict) else {}
        asset = analysis_payload.get("asset") if isinstance(analysis_payload.get("asset"), dict) else {}
        patterns = analysis_payload.get("patterns") if isinstance(analysis_payload.get("patterns"), list) else []
        source_basis_counts = summary.get("source_basis_counts") if isinstance(summary.get("source_basis_counts"), dict) else {}
        status_counts = (
            summary.get("calculation_status_counts")
            if isinstance(summary.get("calculation_status_counts"), dict)
            else {}
        )
        row_count = summary.get("distribution_points")
        if row_count is None:
            rows = analysis_payload.get("rows")
            row_count = len(rows) if isinstance(rows, list) else None
        generated_at = analysis_payload.get("generated_at") or self._now_iso()
        materialized_at = asset.get("materialized_at") or generated_at
        asset_path = asset.get("path") or self._relative_path(self.paths.distribution_point_analysis_json)
        quality_flags = [
            "Projection and scenario override rows must remain visible or explicitly filtered before report use.",
            "Per-row fields retain duplicate level, partial band, missing level, known value, projected value, source page, and calculation status indicators.",
        ]
        if source_basis_counts:
            quality_flags.insert(
                0,
                "Source basis counts: "
                + ", ".join(f"{key}={value}" for key, value in sorted(source_basis_counts.items())),
            )
        if status_counts:
            quality_flags.append(
                "Calculation status counts: "
                + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
            )
        return {
            "asset_id": "distribution_point_analysis_default",
            "asset_type": "chart",
            "title": "Distribution Point Analysis",
            "report_title_candidate": "Governed Weekly Pay Distribution Points",
            "report_subtitle_candidate": "EBA pay table points by agreement, quarter, band, and level range",
            "source_dataset": "pay_service_horizon_curve_view",
            "source_dataset_version": analysis_payload.get("asset_version") or analysis_payload.get("generated_at"),
            "input_mart_version": "initial_datamart_suite.v2_2_service_horizon_curve_view",
            "generated_at": generated_at,
            "generated_by": "workbench-analysis-generator",
            "filters": {
                "cohort": "all governed agreements included in the distribution analysis build",
                "period_basis": "quarter_start",
                "classification_basis": "chart_band and chart level range",
                "status": "rows with calculation_status retained for downstream filtering",
            },
            "metric_definition": "Service-horizon curve/envelope view derived from pay_distribution_point_mart. Dots and comparator curve must come from the same service_horizon_window metric universe.",
            "pay_metric_set": "pay_structure_semantics_v1",
            "default_pay_metric": "range_midpoint_rate",
            "service_horizon_window_id": "entry_to_y6",
            "service_horizon_window_label": "Entry-to-Year-6 service-horizon distribution",
            "included_metric_points": [
                "entry_rate",
                "service_year_1_rate",
                "service_year_2_rate",
                "service_year_3_rate",
                "service_year_4_rate",
                "service_year_5_rate",
                "service_year_6_rate",
            ],
            "weighting_method": "observation_weighted",
            "curve_source": "pay_service_horizon_curve_view",
            "selected_council_points_source": "selected_council_points_json",
            "available_pay_metrics": [
                "entry_rate",
                "capacity_rate",
                "range_midpoint_rate",
                "service_year_1_rate",
                "service_year_2_rate",
                "service_year_3_rate",
                "service_year_4_rate",
                "service_year_5_rate",
                "service_year_6_rate",
            ],
            "blocked_pay_metrics": [],
            "metric_caveats": [
                "Midpoint is an explicit comparison metric, not the default analytical truth.",
                "Y1-Y6 values are service-horizon comparison points, not implied ordinal levels, and must be read with resolved_value_mode, calculation_status, and report_ready_status.",
                "Estimated service-horizon values use ordered governed pay points; later horizons carry capacity forward after the actual ladder is exhausted unless governed progression rules exist.",
                "Interactive curve/envelope views must use pay_service_horizon_curve_view so dots and curve share the same service_horizon_window.",
            ],
            "visual_encoding": {
                "chart_type": "service_horizon_distribution_curve",
                "x_axis": "weekly_rate",
                "y_axis": "classification band or selected cohort dimension",
                "comparison_metric": "range_midpoint_rate",
                "service_year_index": None,
                "service_horizon_year": None,
                "service_horizon_window_id": "entry_to_y6",
                "service_horizon_window_label": "Entry-to-Year-6 service-horizon distribution",
                "included_metric_points": [
                    "entry_rate",
                    "service_year_1_rate",
                    "service_year_2_rate",
                    "service_year_3_rate",
                    "service_year_4_rate",
                    "service_year_5_rate",
                    "service_year_6_rate",
                ],
                "weighting_method": "observation_weighted",
                "curve_source": "pay_service_horizon_curve_view",
                "selected_council_points_source": "selected_council_points_json",
                "resolved_value_mode": None,
                "input_mart_version": "initial_datamart_suite.v2_2_service_horizon_curve_view",
                "point_roles": [
                    "cohort_point",
                    "statewide_context",
                    "selected_council",
                    "projected_value",
                    "quality_warning",
                ],
                "colour_policy": "Use brand/report colour roles, not hard-coded one-off chart colours.",
            },
            "quality_flags": quality_flags,
            "provenance": {
                "endpoint": "/api/analysis/distribution-point-analysis",
                "asset_file": asset_path,
                "contract": "REPORT_ASSET_CONTRACT.md",
                "row_count": row_count,
                "materialized_at": materialized_at,
                "patterns": patterns,
            },
            "operator_note": "Use this as the proving asset for turning exploratory chart ideas into governed report-ready evidence objects.",
            "export_targets": list(REPORT_EXPORT_FORMATS),
            "status": "draft",
        }

    def materialize_distribution_point_analysis_manifest(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        manifest = self.distribution_point_analysis_manifest(analysis_payload)
        validation = self.validate_manifest(manifest)
        if not validation["valid"]:
            raise ValueError(f"Invalid distribution point report asset manifest: {validation}")
        path = self.distribution_point_analysis_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest

    def update_distribution_point_analysis_status(
        self,
        status: str,
        *,
        operator_note: str | None = None,
    ) -> dict[str, Any]:
        next_status = status.strip().lower()
        if next_status not in REPORT_ASSET_STATUSES:
            raise ValueError(f"Unsupported report asset status: {status}")
        manifest = self.load_distribution_point_analysis_manifest()
        validation = self.validate_manifest(manifest)
        if not validation["valid"]:
            raise ValueError(f"Distribution point report asset manifest is invalid: {validation}")
        assert manifest is not None
        manifest["status"] = next_status
        manifest["status_updated_at"] = self._now_iso()
        manifest["status_updated_by"] = "operator"
        if operator_note is not None:
            note = operator_note.strip()
            if note:
                manifest["operator_note"] = note
        validation = self.validate_manifest(manifest)
        if not validation["valid"]:
            raise ValueError(f"Updated distribution point report asset manifest is invalid: {validation}")
        path = self.distribution_point_analysis_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest

    def manifest_summary(self, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        current = manifest or self.load_distribution_point_analysis_manifest()
        return {
            "asset_id": (current or {}).get("asset_id"),
            "status": (current or {}).get("status"),
            "status_options": list(REPORT_ASSET_STATUS_ORDER),
            "status_updated_at": (current or {}).get("status_updated_at"),
            "status_updated_by": (current or {}).get("status_updated_by"),
            "manifest": file_info(self.distribution_point_analysis_manifest_path()),
            "validation": self.validate_manifest(current),
        }

    def status(self) -> dict[str, Any]:
        manifest = self.load_distribution_point_analysis_manifest()
        return {
            "contract": file_info(self.contract_path()),
            "required_fields": self.required_fields(),
            "distribution_point_analysis": self.manifest_summary(manifest),
        }

    def catalog(self) -> dict[str, Any]:
        manifest = self.load_distribution_point_analysis_manifest()
        return {
            "contract": file_info(self.contract_path()),
            "required_fields": self.required_fields(),
            "assets": [
                {
                    "asset_id": "distribution_point_analysis_default",
                    "asset_type": "chart",
                    "source_dataset": "pay_tables",
                    "raw_asset": file_info(self.paths.distribution_point_analysis_json),
                    "manifest": file_info(self.distribution_point_analysis_manifest_path()),
                    "validation": self.validate_manifest(manifest),
                    "endpoint": "/api/analysis/distribution-point-analysis",
                }
            ],
        }


def _xml_escape(value: Any) -> str:
    return html_escape("" if value is None else str(value), quote=True)


def _excel_column_name(index: int) -> str:
    name = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_simple_png(path: Path, *, width: int, height: int, bars: list[float]) -> None:
    background = (248, 251, 252)
    navy = (11, 29, 58)
    teal = (21, 155, 166)
    amber = (212, 144, 42)
    pixels = [[background for _ in range(width)] for _ in range(height)]
    margin_x = 72
    margin_y = 58
    plot_w = width - (margin_x * 2)
    plot_h = height - (margin_y * 2)
    for x in range(margin_x, margin_x + plot_w):
        pixels[height - margin_y][x] = navy
    for y in range(margin_y, height - margin_y + 1):
        pixels[y][margin_x] = navy
    if bars:
        max_value = max(max(bars), 1)
        bar_w = max(6, min(42, plot_w // max(len(bars) * 2, 1)))
        gap = max(4, (plot_w - (bar_w * len(bars))) // max(len(bars), 1))
        for index, value in enumerate(bars):
            bar_h = int((value / max_value) * (plot_h - 8))
            x0 = margin_x + gap // 2 + index * (bar_w + gap)
            x1 = min(width - margin_x, x0 + bar_w)
            y0 = height - margin_y - bar_h
            color = teal if index % 2 == 0 else amber
            for y in range(max(margin_y, y0), height - margin_y):
                for x in range(max(margin_x + 1, x0), x1):
                    pixels[y][x] = color
    raw = b"".join(bytes([0]) + b"".join(bytes(pixel) for pixel in row) for row in pixels)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


@dataclass(frozen=True)
class ReportExportService:
    paths: Any
    report_assets: ReportAssetService | None = None
    now: Callable[[], str] | None = None

    def _now_iso(self) -> str:
        if self.now is not None:
            return self.now()
        return datetime.now(timezone.utc).isoformat()

    def _report_assets(self) -> ReportAssetService:
        return self.report_assets or ReportAssetService(paths=self.paths, now=self.now)

    def export_root(self, asset_id: str = "distribution_point_analysis_default") -> Path:
        return self.paths.exports_dir / "report-assets" / asset_id

    def distribution_point_payload(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.distribution_point_analysis_json)

    def distribution_point_manifest(self) -> dict[str, Any] | None:
        return self._report_assets().load_distribution_point_analysis_manifest()

    def export_paths(self, asset_id: str = "distribution_point_analysis_default") -> dict[str, Path]:
        root = self.export_root(asset_id)
        stem = asset_id
        return {
            "csv": root / f"{stem}.csv",
            "svg": root / f"{stem}.svg",
            "png": root / f"{stem}.png",
            "xlsx": root / f"{stem}.xlsx",
            "docx": root / f"{stem}.docx",
            "pptx": root / f"{stem}.pptx",
            "manifest": root / f"{stem}.exports.json",
        }

    def export_targets(self) -> list[dict[str, Any]]:
        paths = self.export_paths()
        return [
            {
                "format": target,
                "implemented": True,
                "file": file_info(paths[target]),
            }
            for target in REPORT_EXPORT_FORMATS
        ]

    def export_file_path(self, format_name: str, asset_id: str = "distribution_point_analysis_default") -> Path:
        target = format_name.lower()
        if target not in REPORT_EXPORT_FORMATS and target != "manifest":
            raise ValueError(f"Unsupported report export format: {format_name}")
        path = self.export_paths(asset_id)[target]
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    def status(self) -> dict[str, Any]:
        manifest = self.distribution_point_manifest()
        payload = self.distribution_point_payload()
        validation = self._report_assets().validate_manifest(manifest)
        return {
            "asset_id": "distribution_point_analysis_default",
            "source_exists": self.paths.distribution_point_analysis_json.exists(),
            "manifest_valid": validation["valid"],
            "row_count": len(payload.get("rows", [])) if isinstance(payload, dict) and isinstance(payload.get("rows"), list) else 0,
            "implemented_formats": list(REPORT_EXPORT_FORMATS),
            "export_root": str(self.export_root()),
            "export_manifest": file_info(self.export_paths()["manifest"]),
            "exports": self.export_targets(),
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "service": "ReportExportService",
            "assets": [
                {
                    "asset_id": "distribution_point_analysis_default",
                    "source": file_info(self.paths.distribution_point_analysis_json),
                    "manifest": self._report_assets().manifest_summary(),
                    "export_root": str(self.export_root()),
                    "export_manifest": file_info(self.export_paths()["manifest"]),
                    "targets": self.export_targets(),
                }
            ],
        }

    def actions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "export_distribution_point_analysis",
                "label": "Export distribution point report asset",
                "kind": "report_export",
                "asset_id": "distribution_point_analysis_default",
                "formats": list(REPORT_EXPORT_FORMATS),
                "governance": "contract_valid_asset_required",
                "writes": ["exports/report-assets/distribution_point_analysis_default"],
            }
        ]

    def materialize_distribution_point_exports(self, *, row_limit: int | None = None) -> dict[str, Any]:
        payload = self.distribution_point_payload()
        if not isinstance(payload, dict):
            raise ValueError("Distribution point analysis asset is missing or invalid.")
        manifest = self.distribution_point_manifest()
        validation = self._report_assets().validate_manifest(manifest)
        if not validation["valid"]:
            raise ValueError(f"Distribution point report asset manifest is invalid: {validation}")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Distribution point analysis asset does not contain rows.")
        export_rows = rows[:row_limit] if row_limit is not None and row_limit >= 0 else rows
        asset_id = str((manifest or {}).get("asset_id") or "distribution_point_analysis_default")
        root = self.export_root(asset_id)
        root.mkdir(parents=True, exist_ok=True)
        paths = self.export_paths(asset_id)
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        self._write_csv(paths["csv"], export_rows)
        self._write_svg(paths["svg"], manifest or {}, summary, export_rows)
        self._write_png(paths["png"], summary)
        self._write_xlsx(paths["xlsx"], manifest or {}, summary, export_rows)
        self._write_docx(paths["docx"], manifest or {}, summary)
        self._write_pptx(paths["pptx"], manifest or {}, summary)
        export_manifest = {
            "asset_id": asset_id,
            "generated_at": self._now_iso(),
            "source_asset": str(self.paths.distribution_point_analysis_json),
            "source_dataset_version": (manifest or {}).get("source_dataset_version"),
            "row_count": len(export_rows),
            "row_limit": row_limit,
            "formats": {
                key: file_info(path)
                for key, path in paths.items()
                if key != "manifest"
            },
        }
        paths["manifest"].write_text(json.dumps(export_manifest, indent=2, sort_keys=True), encoding="utf-8")
        export_manifest["manifest"] = file_info(paths["manifest"])
        return export_manifest

    def _write_csv(self, path: Path, rows: list[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPORT_EXPORT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row if isinstance(row, dict) else {})

    def _write_svg(self, path: Path, manifest: dict[str, Any], summary: dict[str, Any], rows: list[Any]) -> None:
        title = manifest.get("report_title_candidate") or manifest.get("title") or "Distribution Point Analysis"
        subtitle = manifest.get("report_subtitle_candidate") or "Governed report asset"
        values = [
            float(row.get("midpoint_weekly_rate") or 0)
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("midpoint_weekly_rate"), (int, float))
        ][:24]
        max_value = max(values) if values else 1
        bars = []
        for index, value in enumerate(values):
            height = int((value / max_value) * 230)
            x = 72 + index * 40
            y = 420 - height
            color = "#159ba6" if index % 2 == 0 else "#d4902a"
            bars.append(f'<rect x="{x}" y="{y}" width="24" height="{height}" rx="3" fill="{color}" />')
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680">
  <rect width="1200" height="680" fill="#f8fbfc" />
  <rect x="42" y="38" width="1116" height="604" rx="12" fill="#ffffff" stroke="#d8e3eb" />
  <text x="72" y="96" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="#0b1d3a">{_xml_escape(title)}</text>
  <text x="72" y="132" font-family="Arial, sans-serif" font-size="18" fill="#40546a">{_xml_escape(subtitle)}</text>
  <text x="72" y="180" font-family="Arial, sans-serif" font-size="16" fill="#40546a">Rows: {_xml_escape(summary.get("distribution_points", len(rows)))} / Quarters: {_xml_escape(summary.get("quarters", ""))} / Bands: {_xml_escape(summary.get("bands", ""))}</text>
  <line x1="72" y1="420" x2="1088" y2="420" stroke="#0b1d3a" stroke-width="2" />
  <line x1="72" y1="190" x2="72" y2="420" stroke="#0b1d3a" stroke-width="2" />
  {''.join(bars)}
  <text x="72" y="500" font-family="Arial, sans-serif" font-size="15" fill="#617188">Preview bars show the first available midpoint weekly rates. Use CSV/XLSX for full row detail.</text>
  <text x="72" y="548" font-family="Arial, sans-serif" font-size="13" fill="#617188">Status: {_xml_escape(manifest.get("status", "draft"))} / Source: {_xml_escape(manifest.get("source_dataset", "pay_tables"))} / Version: {_xml_escape(manifest.get("source_dataset_version", ""))}</text>
</svg>
"""
        path.write_text(svg, encoding="utf-8")

    def _write_png(self, path: Path, summary: dict[str, Any]) -> None:
        counts = summary.get("source_basis_counts") if isinstance(summary.get("source_basis_counts"), dict) else {}
        bars = [float(value) for value in counts.values() if isinstance(value, (int, float))]
        if not bars:
            bars = [
                float(summary.get("known_points") or 0),
                float(summary.get("projected_points") or 0),
                float(summary.get("partial_band_points") or 0),
                float(summary.get("duplicate_level_points") or 0),
            ]
        _write_simple_png(path, width=960, height=540, bars=[value for value in bars if value >= 0])

    def _write_xlsx(self, path: Path, manifest: dict[str, Any], summary: dict[str, Any], rows: list[Any]) -> None:
        sheet_rows = [
            ["Asset", manifest.get("asset_id", "distribution_point_analysis_default")],
            ["Title", manifest.get("report_title_candidate", manifest.get("title", ""))],
            ["Status", manifest.get("status", "")],
            ["Source dataset", manifest.get("source_dataset", "")],
            ["Source version", manifest.get("source_dataset_version", "")],
            ["Distribution points", summary.get("distribution_points", len(rows))],
            [],
            REPORT_EXPORT_COLUMNS,
        ]
        for row in rows:
            record = row if isinstance(row, dict) else {}
            sheet_rows.append([record.get(column, "") for column in REPORT_EXPORT_COLUMNS])
        sheet_xml = self._worksheet_xml(sheet_rows)
        self._write_office_package(
            path,
            content_types="""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
            rels="""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
            parts={
                "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Distribution Points" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
                "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
                "xl/worksheets/sheet1.xml": sheet_xml,
                "docProps/core.xml": self._core_props_xml(manifest),
                "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>EBA Workbench</Application></Properties>""",
            },
        )

    def _worksheet_xml(self, rows: list[list[Any]]) -> str:
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                cell_ref = f"{_excel_column_name(column_index)}{row_index}"
                cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{_xml_escape(value)}</t></is></c>')
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(row_xml)}</sheetData>
</worksheet>"""

    def _write_docx(self, path: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
        title = manifest.get("report_title_candidate") or manifest.get("title") or "Distribution Point Analysis"
        paragraphs = [
            title,
            manifest.get("report_subtitle_candidate", ""),
            f"Status: {manifest.get('status', 'draft')}",
            f"Source dataset: {manifest.get('source_dataset', '')} / {manifest.get('source_dataset_version', '')}",
            f"Distribution points: {summary.get('distribution_points', '')}",
            str(manifest.get("operator_note", "")),
        ]
        body = "".join(f"<w:p><w:r><w:t>{_xml_escape(text)}</w:t></w:r></w:p>" for text in paragraphs if text)
        self._write_office_package(
            path,
            content_types="""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
            rels="""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
            parts={
                "word/document.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr/></w:body></w:document>""",
                "docProps/core.xml": self._core_props_xml(manifest),
                "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>EBA Workbench</Application></Properties>""",
            },
        )

    def _write_pptx(self, path: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
        title = manifest.get("report_title_candidate") or manifest.get("title") or "Distribution Point Analysis"
        subtitle = manifest.get("report_subtitle_candidate") or "Governed report asset"
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="685800"/><a:ext cx="7772400" cy="914400"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{_xml_escape(title)}</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:cNvPr id="3" name="Subtitle"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="1600200"/><a:ext cx="7772400" cy="914400"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{_xml_escape(subtitle)}</a:t></a:r></a:p><a:p><a:r><a:t>Distribution points: {_xml_escape(summary.get("distribution_points", ""))}</a:t></a:r></a:p></p:txBody></p:sp>
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""
        self._write_office_package(
            path,
            content_types="""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
            rels="""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
            parts={
                "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="9144000" cy="5143500" type="screen16x9"/></p:presentation>""",
                "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>""",
                "ppt/slides/slide1.xml": slide,
                "docProps/core.xml": self._core_props_xml(manifest),
                "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>EBA Workbench</Application></Properties>""",
            },
        )

    def _core_props_xml(self, manifest: dict[str, Any]) -> str:
        title = manifest.get("report_title_candidate") or manifest.get("title") or "Distribution Point Analysis"
        timestamp = self._now_iso()
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{_xml_escape(title)}</dc:title>
  <dc:creator>EBA Workbench</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{_xml_escape(timestamp)}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{_xml_escape(timestamp)}</dcterms:modified>
</cp:coreProperties>"""

    def _write_office_package(self, path: Path, *, content_types: str, rels: str, parts: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            for name, content in parts.items():
                archive.writestr(name, content)
