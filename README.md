# City of Ballarat Pulse Job Scraper

This repository now intentionally focuses on a single source: the City of Ballarat
job board that runs on Pulse. The goal is to prove out one reliable scraping
approach for a JavaScript-heavy Pulse tenancy before attempting the wider
Victorian councils directory again.

## Current capabilities
- ✅ **Single council scope** – `scraper.py` only targets
  `https://ballarat.pulsesoftware.com/Pulse/jobs` and exports the jobs to
  `jobs_output.json` plus a basic RSS feed.
- ✅ **Playwright-based rendering** – launches Chromium headlessly, waits for the
  Vue component to populate at least 15 cards, scrolls to trigger lazy loading,
  and then scrapes either the exposed Vue data or a DOM fallback.
- ✅ **Structured job details** – captures metadata from the listing, opens each
  job detail view for descriptions, requirements, application instructions,
  contact info, and an inferred band level snippet.
- ✅ **Static viewer** – `index.html` now loads `jobs_output.json` directly so
  the GitHub Pages site always shows the latest scrape (or the placeholder JSON
  committed in this repo until the first automated run).

## Setup
1. Install the dependencies and browsers:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
2. Run the scraper:
   ```bash
   python scraper.py
   ```
   If Chromium cannot be installed in your environment, run the offline fixture
   instead:
   ```bash
   python scraper.py --fixture docs/pulse_fixture.json
   ```
   The default command will also fall back to the bundled fixture whenever
   Playwright raises a launch/navigation error. Disable that behavior with
   `--disable-fallback`.
3. Review `jobs_output.json`, `rss.xml`, `scrape.log`, and the latest
  `pulse_list.png` screenshot for troubleshooting. The JSON file is also what
  powers the public viewer at `index.html`.

## Why Playwright (research summary)
Pulse renders its public job listings fully client-side via Vue and only exposes
minimal markup until the Vue instance finishes hydrating. Static HTTP requests
alone cannot reach the job data without reverse engineering the internal API
endpoints and authentication headers for each tenancy. For now Playwright gives
us:

- A predictable execution context where we can trigger `load()` if it exists and
  wait for `.row.card-row` nodes to appear.
- Full DOM access (or direct access to `__vue__`) so we can extract the `jobs`
  array without guessing undocumented REST endpoints.
- The ability to drive job detail pages, which Pulse loads on separate routes
  that lazy-load additional chunks.

### Alternative paths (to revisit later)
- **Network interception:** Inspecting the `fetch`/XHR traffic to Pulse can
  reveal a JSON API for search results. Capturing the request payloads in the
  Playwright session and replaying them manually would eliminate the need for
  headless browsers, but each tenancy may use unique IDs and auth tokens.
- **Server-side rendering or caching:** If latency becomes an issue, we can
  scrape with Playwright in CI, persist the JSON, and serve it statically (as we
  already do) while scheduling runs sparingly.

## Next steps
- Harden the DOM fallback so the scraper still works if the Vue structure
  changes.
- Capture the Pulse API calls and confirm whether authenticated requests are
  required.
- Once the Ballarat approach is stable, re-introduce multiple councils and the
  MAV directory with accurate documentation.
