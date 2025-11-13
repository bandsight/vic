from datetime import datetime, timedelta
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scraper import parse_date, slug_title, generate_rss


def test_parse_date_extracts_isoformat():
    assert parse_date("Closing date: 5 September 2024") == "2024-09-05T00:00:00"


def test_parse_date_returns_na_for_ongoing():
    assert parse_date("Ongoing position", field_type='closing') == "N/A"


def test_slug_title_strips_special_characters():
    assert slug_title("Senior Planner (FT)") == "senior-planner-ft"


def test_generate_rss_filters_recent_jobs():
    now = datetime(2024, 1, 31, 12, 0, 0)
    recent_posted = (now - timedelta(days=10)).isoformat()
    old_posted = (now - timedelta(days=40)).isoformat()

    jobs = [
        {
            'title': 'Recent Role',
            'council': 'City of Ballarat',
            'detail_url': 'https://example.com/recent',
            'description': 'Great role',
            'posted_date': recent_posted,
            'scraped_at': now.isoformat(),
            'reference_number': 'recent-ref'
        },
        {
            'title': 'Old Role',
            'council': 'City of Ballarat',
            'detail_url': 'https://example.com/old',
            'description': 'Old role',
            'posted_date': old_posted,
            'scraped_at': now.isoformat(),
            'reference_number': 'old-ref'
        }
    ]

    rss_xml = generate_rss(jobs, now=now)
    rss = ET.fromstring(rss_xml)
    items = rss.findall('./channel/item')

    assert len(items) == 1
    assert items[0].find('title').text == 'City of Ballarat - Recent Role'
