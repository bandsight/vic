# Configuration for scraper
TEST_MODE = True  # Set False for full 79 councils
MAX_JOBS_PER_COUNCIL = 10  # Limit per site
DELAY_BETWEEN_COUNCILS = 3  # Seconds
DELAY_AFTER_CLICK = 3  # Seconds for loads
RSS_DAYS_BACK = 30  # Jobs in RSS (filter by posted_date)
FALLBACK_COUNCILS_FILE = 'fallback_councils.json'  # Backup if directory fails
QUICK_TEST_COUNCILS = ['City of Ballarat']  # Run only these for debug (overrides TEST_MODE)
