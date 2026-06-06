from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List, Optional

from playwright.sync_api import ConsoleMessage, Error, Page, TimeoutError, sync_playwright

BASE_URL = "http://localhost:8765/"
PDF_LOAD_TIMEOUT_MS = 10_000
PAGE_LOAD_TIMEOUT_MS = 15_000


@dataclass
class CouncilResult:
    ae_id: str
    status: str
    details: str = ""


@dataclass
class CouncilTracker:
    current_ae_id: Optional[str] = None
    console_errors: List[str] = field(default_factory=list)
    page_errors: List[str] = field(default_factory=list)

    def begin(self, ae_id: str) -> None:
        self.current_ae_id = ae_id
        self.console_errors = []
        self.page_errors = []

    def on_console(self, message: ConsoleMessage) -> None:
        if message.type == "error" and self.current_ae_id:
            self.console_errors.append(message.text)

    def on_page_error(self, error: Error) -> None:
        if self.current_ae_id:
            self.page_errors.append(str(error))

    def failures(self) -> List[str]:
        return [*self.console_errors, *self.page_errors]


def get_pdf_state(page: Page) -> dict:
    return page.evaluate(
        """
        () => {
          const canvas = document.querySelector('#pdf-canvas');
          const indicator = document.querySelector('#pdf-page-indicator');
          return {
            canvasWidth: canvas ? canvas.width : 0,
            canvasHeight: canvas ? canvas.height : 0,
            indicator: indicator ? indicator.textContent : ''
          };
        }
        """
    )


def pdf_loaded(page: Page) -> bool:
    state = get_pdf_state(page)
    indicator = (state.get("indicator") or "").strip()
    return (
        int(state.get("canvasWidth") or 0) > 0
        and int(state.get("canvasHeight") or 0) > 0
        and "/" in indicator
        and not indicator.startswith("–")
    )


def fetch_pdf_status(page: Page, ae_id: str) -> Optional[int]:
    status = page.evaluate(
        """
        async (aeId) => {
          try {
            const response = await fetch(`/api/councils/${aeId}/pdf`, { method: 'HEAD' });
            return response.status;
          } catch {
            return null;
          }
        }
        """,
        ae_id,
    )
    return int(status) if isinstance(status, (int, float)) else None


def option_values(page: Page) -> List[str]:
    values = page.eval_on_selector_all(
        "#council-select option",
        "elements => elements.map(e => e.value).filter(Boolean)",
    )
    return [str(value) for value in values]


def test_council(page: Page, tracker: CouncilTracker, ae_id: str) -> CouncilResult:
    tracker.begin(ae_id)
    page.select_option("#council-select", value=ae_id)

    pdf_status = fetch_pdf_status(page, ae_id)
    if pdf_status is not None and pdf_status != 200:
        return CouncilResult(ae_id=ae_id, status="SKIP", details=f"pdf HTTP {pdf_status}")

    try:
        page.wait_for_function(
            """
            () => {
              const canvas = document.querySelector('#pdf-canvas');
              const indicator = document.querySelector('#pdf-page-indicator');
              const indicatorText = indicator ? indicator.textContent || '' : '';
              return canvas && canvas.width > 0 && canvas.height > 0 && indicatorText.includes('/') && !indicatorText.trim().startsWith('–');
            }
            """,
            timeout=PDF_LOAD_TIMEOUT_MS,
        )
    except TimeoutError:
        return CouncilResult(
            ae_id=ae_id,
            status="FAIL",
            details=f"PDF did not load within {PDF_LOAD_TIMEOUT_MS // 1000}s, state={get_pdf_state(page)}",
        )

    failures = tracker.failures()
    if failures:
        return CouncilResult(ae_id=ae_id, status="FAIL", details=" | ".join(failures))

    return CouncilResult(ae_id=ae_id, status="PASS")


def main() -> int:
    results: List[CouncilResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)

        tracker = CouncilTracker()
        page.on("console", tracker.on_console)
        page.on("pageerror", tracker.on_page_error)

        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#council-select", state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)

        ae_ids = option_values(page)
        if not ae_ids:
            print("FAIL no councils found in #council-select")
            browser.close()
            return 1

        for ae_id in ae_ids:
            result = test_council(page, tracker, ae_id)
            results.append(result)
            if result.details:
                print(f"{result.status} {result.ae_id} {result.details}")
            else:
                print(f"{result.status} {result.ae_id}")

        browser.close()

    passed = sum(1 for r in results if r.status == "PASS")
    failed = [r for r in results if r.status == "FAIL"]
    skipped = sum(1 for r in results if r.status == "SKIP")

    print(f"SUMMARY {passed} passed, {len(failed)} failed, {skipped} skipped, {len(results)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
