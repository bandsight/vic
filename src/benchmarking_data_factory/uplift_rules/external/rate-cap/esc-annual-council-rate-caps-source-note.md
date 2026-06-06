# ESC Annual Council Rate Caps Source Note

- Source title: Annual council rate caps | Essential Services Commission
- Source URL: https://www.esc.vic.gov.au/local-government/annual-council-rate-caps
- Source type: public web page
- Access date: 2026-04-08
- Freeze status: data captured into CSVs

## Methodology

Standard statewide caps captured from the ESC page directly.
Historical higher-cap exception data recovered via Wayback Machine snapshots.

## Standard cap history (complete, confirmed)

All statewide caps from 2016-17 through 2026-27 confirmed against live page and
archived snapshots. See standard-statewide-rate-caps.csv.

## Higher cap exception history (complete for 2016-17 to 2025-26)

Wayback Machine snapshots checked for each year:
- 2021-22 (Nov 2021 snapshot): "We received no applications"
- 2022-23 (Dec 2022 snapshot): "There are no councils with an existing higher rate cap"
- 2023-24 (Dec 2023 snapshot): "There are no councils with an existing higher rate cap"
- 2024-25 (Dec 2024 snapshot): "There are no councils with an existing higher rate cap"
- 2025-26 (May 2025 snapshot): Hepburn 10%, Indigo 7.54% -- approved after March 2025 deadline

No exceptions exist for any year before 2025-26. These are the first approvals since
rate capping began in 2016-17.

## Important: ESC page display ambiguity

The current live ESC page (April 2026) shows:
  "Hepburn Shire Council has an approved higher cap of 10 per cent for 2025-26
   and Indigo Shire Council has an approved higher cap of 7.54 per cent for 2025-26."

This appears under the "2026-27 rate cap is 2.75 per cent" heading -- but the year
referenced in the text is explicitly 2025-26. These are PRIOR YEAR approvals still
displayed as context, NOT 2026-27 approvals.

The 2026-27 application deadline was 31 March 2026. Any 2026-27 approvals would be
posted after that date. As of 2026-04-08, no 2026-27 exceptions have been announced.
The 2026-27 exception status for Hepburn and Indigo is UNKNOWN -- they may or may not
have applied again.

## 2026-27 exceptions: pending

Flag in higher-cap-exceptions.csv: no 2026-27 entries yet.
The annual January cron should check for 2026-27 approvals when it runs.
