"""Rate cap refresh — fetches ESC page, diffs against CSVs, applies additions.

Ported from benchmarking project 2026-04-20. Self-contained: workbench owns
the CSVs under ../external/rate-cap/. The module is importable as a library
(use `run_refresh(...)`) and also runnable as a script entry point
(`python -m benchmarking_data_factory.uplift_rules.rate_cap.refresh ...`).

The refresh is idempotent: running it twice with the same upstream content
makes no additional changes.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

SOURCE_URL = "https://www.esc.vic.gov.au/local-government/annual-council-rate-caps"
# Anchors at this module; DATA_DIR is workbench's own rate-cap directory
RATE_CAP_MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = RATE_CAP_MODULE_DIR.parent / "external" / "rate-cap"
STANDARD_CAPS_PATH = DATA_DIR / "standard-statewide-rate-caps.csv"
EXCEPTIONS_PATH = DATA_DIR / "higher-cap-exceptions.csv"
YEAR_STATUS_PATH = DATA_DIR / "rate-cap-year-status.csv"
CAPTURED_DATE = date.today().isoformat()

STANDARD_HEADERS = [
    "period_year_label",
    "rate_cap_value",
    "source_reference",
    "source_type",
    "effective_date_or_applicable_year",
    "notes",
]
EXCEPTION_HEADERS = [
    "council_name",
    "lga_short_name",
    "financial_year",
    "approved_cap_pct",
    "source_url",
    "captured_date",
    "notes",
]
STATUS_HEADERS = ["financial_year", "resolution_status", "confirmed_date", "notes"]

COUNCIL_SUFFIXES = [
    " Shire Council",
    " City Council",
    " Rural City Council",
    " Borough Council",
    " Council",
    " Shire",
    " Rural City",
    " City",
    " Borough",
]


class RefreshError(Exception):
    pass


@dataclass(frozen=True)
class StandardCap:
    financial_year: str
    rate_cap_pct: str


@dataclass(frozen=True)
class HigherCapException:
    council_name: str
    lga_short_name: str
    financial_year: str
    approved_cap_pct: str


@dataclass(frozen=True)
class RefreshResult:
    standard_cap: StandardCap
    exceptions: tuple[HigherCapException, ...]
    referenced_years: tuple[str, ...]
    standard_messages: tuple[str, ...]
    exception_messages: tuple[str, ...]
    status_messages: tuple[str, ...]
    dry_run: bool
    files_written: tuple[Path, ...]  # empty when dry_run=True


def fetch_page() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; rate-cap-refresh/1.0; +https://www.esc.vic.gov.au/)"
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RefreshError(f"Fetch failed: {exc}") from exc


def _clean_html_text(html: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_pct(value: str) -> str:
    return f"{float(value):.2f}"


def derive_lga_short_name(council_name: str) -> str:
    name = " ".join(council_name.split())
    for suffix in sorted(COUNCIL_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip(" ,")


def parse_page(html: str) -> tuple[StandardCap, list[HigherCapException], list[str]]:
    text = _clean_html_text(html)

    standard_match = re.search(
        r"The\s+(\d{4}-\d{2})\s+rate cap is\s+([0-9]+(?:\.[0-9]+)?)\s+per cent",
        text,
        flags=re.IGNORECASE,
    )
    if not standard_match:
        raise RefreshError("Could not find current rate cap year on ESC page")

    current_year = standard_match.group(1)
    standard_cap = StandardCap(
        financial_year=current_year,
        rate_cap_pct=normalize_pct(standard_match.group(2)),
    )

    exceptions: list[HigherCapException] = []
    for match in re.finditer(
        r"\b([A-Z][A-Za-z'&\- ]+? Council)\s+has an approved higher cap of\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s+per cent\s+for\s+(\d{4}-\d{2})",
        text,
    ):
        council_name = " ".join(match.group(1).split())
        council_name = re.sub(r"^(?:Approved higher rate caps\s+|and\s+)", "", council_name)
        exceptions.append(
            HigherCapException(
                council_name=council_name,
                lga_short_name=derive_lga_short_name(council_name),
                financial_year=match.group(3),
                approved_cap_pct=normalize_pct(match.group(2)),
            )
        )

    referenced_years = sorted(set(re.findall(r"\b\d{4}-\d{2}\b", text)))
    if current_year not in referenced_years:
        referenced_years.append(current_year)
        referenced_years.sort()

    return standard_cap, exceptions, referenced_years


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, headers: list[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def refresh_standard_caps(rows: list[dict[str, str]], standard_cap: StandardCap) -> tuple[list[dict[str, str]], list[str]]:
    existing_years = {row["period_year_label"] for row in rows}
    messages: list[str] = []
    updated_rows = list(rows)
    if standard_cap.financial_year in existing_years:
        messages.append("No new standard cap")
    else:
        updated_rows.append(
            {
                "period_year_label": standard_cap.financial_year,
                "rate_cap_value": standard_cap.rate_cap_pct,
                "source_reference": f"ESC annual council rate caps page ({SOURCE_URL})",
                "source_type": "public web page",
                "effective_date_or_applicable_year": standard_cap.financial_year,
                "notes": "Standard statewide annual cap value",
            }
        )
        messages.append(
            f"Added standard cap {standard_cap.financial_year}={standard_cap.rate_cap_pct}%"
        )
    return updated_rows, messages


def refresh_exceptions(
    rows: list[dict[str, str]], exceptions: list[HigherCapException]
) -> tuple[list[dict[str, str]], list[str]]:
    known_keys = {(row["lga_short_name"], row["financial_year"]) for row in rows}
    updated_rows = list(rows)
    messages: list[str] = []
    for exception in exceptions:
        key = (exception.lga_short_name, exception.financial_year)
        if key in known_keys:
            messages.append(
                f"Already known exception {exception.lga_short_name} {exception.financial_year}={exception.approved_cap_pct}%"
            )
            continue
        updated_rows.append(
            {
                "council_name": exception.council_name,
                "lga_short_name": exception.lga_short_name,
                "financial_year": exception.financial_year,
                "approved_cap_pct": exception.approved_cap_pct,
                "source_url": SOURCE_URL,
                "captured_date": CAPTURED_DATE,
                "notes": f"Approved higher cap for {exception.financial_year} financial year",
            }
        )
        known_keys.add(key)
        messages.append(
            f"Added exception {exception.council_name} {exception.financial_year}={exception.approved_cap_pct}%"
        )
    if not exceptions:
        messages.append("No higher cap exceptions found on ESC page")
    return updated_rows, messages


def refresh_year_statuses(
    rows: list[dict[str, str]], referenced_years: list[str], current_year: str
) -> tuple[list[dict[str, str]], list[str]]:
    updated_rows = [dict(row) for row in rows]
    messages: list[str] = []
    referenced_set = set(referenced_years)

    for row in updated_rows:
        if row["resolution_status"] != "pending_exceptions_check":
            continue
        if row["financial_year"] in referenced_set:
            row["resolution_status"] = "confirmed"
            row["confirmed_date"] = CAPTURED_DATE
            row["notes"] = "Confirmed by ESC annual council rate caps page"
            messages.append(f"Confirmed year {row['financial_year']}")
        elif row["financial_year"] < current_year:
            row["resolution_status"] = "confirmed"
            row["confirmed_date"] = CAPTURED_DATE
            row["notes"] = "Confirmed by absence on ESC page - no exceptions for past year"
            messages.append(f"Confirmed year {row['financial_year']}")
    return updated_rows, messages


def run_refresh(dry_run: bool = False, data_dir: Path | None = None) -> RefreshResult:
    effective_data_dir = data_dir if data_dir is not None else DATA_DIR
    std_path = effective_data_dir / "standard-statewide-rate-caps.csv"
    exc_path = effective_data_dir / "higher-cap-exceptions.csv"
    status_path = effective_data_dir / "rate-cap-year-status.csv"

    html = fetch_page()
    standard_cap, exceptions, referenced_years = parse_page(html)

    standard_rows = read_csv_rows(std_path)
    exception_rows = read_csv_rows(exc_path)
    status_rows = read_csv_rows(status_path)

    standard_rows_updated, standard_messages = refresh_standard_caps(standard_rows, standard_cap)
    exception_rows_updated, exception_messages = refresh_exceptions(exception_rows, exceptions)
    status_rows_updated, status_messages = refresh_year_statuses(
        status_rows, referenced_years, standard_cap.financial_year
    )

    files_written: tuple[Path, ...] = ()
    if not dry_run:
        write_csv_rows(std_path, STANDARD_HEADERS, standard_rows_updated)
        write_csv_rows(exc_path, EXCEPTION_HEADERS, exception_rows_updated)
        write_csv_rows(status_path, STATUS_HEADERS, status_rows_updated)
        files_written = (std_path, exc_path, status_path)

    return RefreshResult(
        standard_cap=standard_cap,
        exceptions=tuple(exceptions),
        referenced_years=tuple(referenced_years),
        standard_messages=tuple(standard_messages),
        exception_messages=tuple(exception_messages),
        status_messages=tuple(status_messages),
        dry_run=dry_run,
        files_written=files_written,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing CSVs")
    args = parser.parse_args(argv)

    try:
        result = run_refresh(dry_run=args.dry_run)
    except RefreshError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"Parsed standard cap: {result.standard_cap.financial_year}={result.standard_cap.rate_cap_pct}%")
    if result.exceptions:
        for exception in result.exceptions:
            print(
                "Parsed exception: "
                f"{exception.council_name} | {exception.lga_short_name} | "
                f"{exception.financial_year} | {exception.approved_cap_pct}%"
            )
    else:
        print("Parsed exception: none")

    for message in result.standard_messages + result.exception_messages + result.status_messages:
        print(message)

    if args.dry_run:
        print("DRY RUN: no files written")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
