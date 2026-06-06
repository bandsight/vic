# External rate cap data — workbench-authoritative copies

This directory holds the rate cap data used by the rate cap resolver. Three files:

- `standard-statewide-rate-caps.csv` — annual statewide caps by FY, with source URLs.
- `higher-cap-exceptions.csv` — council-specific higher cap approvals (rare).
- `rate-cap-year-status.csv` — status per FY (final / TBA / projected).

See `*-note.md` files for source notes.

The resolver in `../../rate_cap/resolver.py` is the only supported reader of these files within application code. Refresh is handled by `../../rate_cap/refresh.py` (implemented in a later brief).
