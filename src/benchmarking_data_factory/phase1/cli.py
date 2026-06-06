from __future__ import annotations

import argparse
import json

from .pipeline import run_phase1


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Benchmarking Data Factory Phase 1 source acquisition pipeline')
    parser.add_argument('--fetch-pdfs', action='store_true', help='Fetch/freeze candidate PDFs after candidate records are created')
    parser.add_argument('--pdf-limit', type=int, default=None, help='Optional limit for candidate PDF freezing during first-pass runs')
    parser.add_argument('--freeze-agreement-id', action='append', default=[], help='Freeze only the specified Agreement ID(s) while still rebuilding candidate outputs')
    parser.add_argument('--force-registry', action='store_true', help='Download fresh Fair Work registry workbooks even when cached copies exist')
    args = parser.parse_args()

    result = run_phase1(
        fetch_pdfs=args.fetch_pdfs,
        pdf_limit=args.pdf_limit,
        freeze_agreement_ids=args.freeze_agreement_id,
        force_registry=args.force_registry,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
