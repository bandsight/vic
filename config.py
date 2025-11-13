"""Configuration for the Pulse job scraper."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PulseTenancy:
    """Represents a single Pulse tenancy we can scrape."""
    name: str
    listing_url: str
    min_card_rows: int = 15


BALLARAT_TENANCY = PulseTenancy(
    name="City of Ballarat",
    listing_url="https://ballarat.pulsesoftware.com/Pulse/jobs",
    min_card_rows=15,
)

# The tenancy we currently target. This keeps the scraper flexible when we
# re-introduce multiple councils.
ACTIVE_TENANCY = BALLARAT_TENANCY

# Scraper tuning knobs
MAX_JOBS = 20
SCROLL_DELAY_SECONDS = 1
RSS_LOOKBACK_DAYS = 30
