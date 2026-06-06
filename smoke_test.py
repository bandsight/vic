"""Standalone smoke test for eba-workbench helpers. Does NOT start the server.
Run: python smoke_test.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
for path in (ROOT, SRC):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
from main import (
    PAY_KEYWORDS,
    extract_page_text,
    find_candidate_pages,
    find_pdf,
    get_canonical,
    get_page_count,
    list_pdfs,
    load_registry,
    render_page_png,
    save_canonical,
    validate_pay_tables,
)


def select_smoke_ae_id():
    for ae_id in list_pdfs():
        try:
            if get_page_count(ae_id) > 10 and find_candidate_pages(ae_id, PAY_KEYWORDS):
                return ae_id
        except Exception:
            continue
    return None


def main():
    print("=== Registry ===")
    reg = load_registry()
    print(f"  {len(reg)} entries")
    print(f"  Sample: {list(reg.items())[0]}")

    print("\n=== PDFs ===")
    pdfs = list_pdfs()
    print(f"  {len(pdfs)} PDFs")
    ae_id = select_smoke_ae_id()
    assert ae_id, "Expected at least one usable smoke-test PDF"
    print(f"  Smoke agreement: {ae_id}")

    print("\n=== find_pdf (case insensitive) ===")
    p = find_pdf(ae_id)
    print(f"  {p}")
    assert p and p.exists()

    print("\n=== Canonical round-trip ===")
    c = get_canonical(ae_id)
    assert c["agreement_id"] == ae_id
    assert "sections" in c
    assert "pay_tables" in c["sections"]
    print(f"  OK (sections: {list(c['sections'].keys())})")

    print("\n=== Page count ===")
    n = get_page_count(ae_id)
    print(f"  {ae_id}: {n} pages")
    assert n > 10

    print("\n=== Extract page 1 text ===")
    t = extract_page_text(ae_id, 1)
    print(f"  {len(t)} chars, starts: {t[:80]!r}")
    assert len(t) > 50

    print("\n=== Render page 1 PNG ===")
    png = render_page_png(ae_id, 1, dpi=100)
    print(f"  {len(png)} bytes")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    print("\n=== Find pay-table candidates ===")
    pages = find_candidate_pages(ae_id, PAY_KEYWORDS)
    print(f"  Candidates: {pages[:15]}...")
    assert len(pages) > 0

    print("\n=== Validation ===")
    v = validate_pay_tables([
        {"rows": [
            {"band": 1, "level": "1A", "weekly_rate": 1000, "annual_rate": 52000, "hourly_rate": None, "fortnightly_rate": None},
            {"band": 1, "level": "1B", "weekly_rate": 900, "annual_rate": 46800, "hourly_rate": None, "fortnightly_rate": None},
            {"band": 2, "level": "2A", "weekly_rate": None, "annual_rate": None, "hourly_rate": 30, "fortnightly_rate": None},
        ], "effective_from": "2024-07-01"}
    ])
    codes = {x["code"] for x in v}
    print(f"  Codes raised: {codes}")
    assert "monotonicity_break" in codes
    assert "hourly_only" in codes

    print("\nOK: All smoke tests passed")


if __name__ == "__main__":
    main()
