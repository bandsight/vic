# Victorian Councils Job Scraper

Automated scraper using Playwright for intelligent browsing of Victorian council jobs. Dynamic fetch from MAV directory. Outputs JSON + CSV + XML (RSS + full dataset) for GitHub Pages.

## Features
- **Dynamic Councils:** Fetches 79 from https://www.viccouncils.asn.au/... (fallback included).
- **Fields:** Full schema (title, closing_date, salary, etc.).
- **Deduplication:** Appends historical data, keeps latest per job.
- **RSS Feed:** `rss.xml` for recent jobs (30 days); view at GitHub Pages.
- **Logging:** `scrape.log` for errors.

## Local Setup
1. `pip install -r requirements.txt && playwright install`
2. Edit `config.py` (e.g., TEST_MODE=False for full run).
3. `python scraper.py` → Generates `jobs_output.json`, `jobs_output.csv`, `jobs.xml` + `rss.xml`.

## GitHub Automation
- Actions: Daily scrape → Commits JSON/RSS.
- Pages: Settings > Pages > Source: main, / (root). Access: `https://yourusername.github.io/vic-councils-job-scraper/rss.xml` (update link in script).

## Usage
- **Data Source:** JSON for analysis; RSS for feeds (e.g., in readers/apps).
- **Customize:** Tweak locators in script for site changes; monitor logs.

Tested November 12, 2025.