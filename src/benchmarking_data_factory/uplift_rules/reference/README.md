# Reference data — workbench-authoritative copies

This directory contains authoritative copies of reference data used by the uplift rules subsystem. These files are **copies**, not imports. The workbench must never read reference data from outside this directory.

## Upstream sources

- `vic-average-rate-cap.csv` — Victorian statewide annual rate cap by FY. Upstream: Essential Services Commission Victoria, <https://www.esc.vic.gov.au/local-government/annual-council-rate-caps>. Refresh cadence: annual (ESC publishes in December for next FY). Refresh: `python3 scripts/refresh_rate_caps.py` (implemented in a later brief).
- `australia-cpi.csv` — ABS CPI data (Australia + Melbourne). Upstream: Australian Bureau of Statistics, <https://www.abs.gov.au/statistics/economy/price-indexes-and-inflation/consumer-price-index-australia>. Refresh cadence: quarterly. Refresh: manual for now.
- `victorian-councils.csv` — canonical 79-council list. Refresh cadence: rare (only when councils merge/split).

## How to update

Until the automated refresh is wired up (later brief), update these CSVs manually. Always include provenance in the row (source_url, captured_date) so the rate cap resolver can cite it.
