from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmarking_data_factory.workbench.pay_horizon_explorer import (  # noqa: E402
    compare_midpoint_parity,
    filter_curve_rows,
    selected_agreement_id,
    v1_midpoint_analytics,
    v2_midpoint_analytics,
)


def load_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("rows") or []


def candidate_rows(curve_rows: list[dict], args: argparse.Namespace) -> list[dict]:
    rows = filter_curve_rows(
        curve_rows,
        standard_band=args.band,
        effective_from=args.effective_from,
        selected_council_id=args.selected,
        service_horizon_window_id="range_midpoint_only",
    )
    return rows or filter_curve_rows(curve_rows, service_horizon_window_id="range_midpoint_only")


def run(args: argparse.Namespace) -> dict:
    root = args.root
    legacy_rows = load_rows(root / "data" / "analysis" / "distribution-point-analysis.json")
    curve_rows = load_rows(root / "data" / "datamarts" / "pay_service_horizon_curve_view.json")
    first_result: dict | None = None
    first_row: dict | None = None
    for row in candidate_rows(curve_rows, args):
        selected_ae = selected_agreement_id(row)
        if not selected_ae:
            continue
        v1 = v1_midpoint_analytics(
            legacy_rows,
            band=str(row.get("standard_band") or ""),
            effective_from=str(row.get("effective_from") or ""),
            selected_agreement_id_value=selected_ae,
        )
        v2 = v2_midpoint_analytics(row)
        parity = compare_midpoint_parity(v1, v2, tolerance=args.tolerance)
        result = {
            "ok": parity["ok"],
            "filters": {
                "view_mode": "single_point",
                "comparison_metric": "range_midpoint_rate",
                "service_horizon_window_id": "range_midpoint_only",
                "selected_agreement_id": selected_ae,
                "selected_council_id": row.get("selected_council_id"),
                "selected_council_name": row.get("selected_council_name"),
                "band": row.get("standard_band"),
                "effective_from": row.get("effective_from"),
                "cohort_id": row.get("cohort_id"),
            },
            "v1": v1,
            "v2": v2,
            "parity": parity,
        }
        if first_result is None:
            first_result = result
            first_row = row
        if parity["ok"]:
            return result
    if first_result is not None:
        if not any([args.band, args.effective_from, args.selected]):
            first_result["parity"]["likely_difference_reasons"].append(
                "No automatically discovered V2 midpoint row reproduced the legacy V1 row universe within tolerance."
            )
        return first_result
    return {
        "ok": False,
        "error": "No range_midpoint_only rows were available. Rebuild datamarts before running parity.",
        "root": str(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check V2 midpoint single-point parity against the legacy V1 chart.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--band")
    parser.add_argument("--effective-from")
    parser.add_argument("--selected", help="Selected council id or agreement id")
    parser.add_argument("--tolerance", type=float, default=0.0001)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
