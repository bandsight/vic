import json
import time
import re
import uuid
import logging
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from xml.dom import minidom
from playwright.sync_api import sync_playwright
import pandas as pd
import os
from config import *  # Import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('scrape.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Fallback councils (expanded for testing)
FALLBACK_COUNCILS = [
    {"name": "City of Melbourne", "job_url": "https://www.melbourne.vic.gov.au/jobs-and-careers"},
    {"name": "City of Yarra", "job_url": "https://www.yarracity.vic.gov.au/about-us/work-with-us"},
    {"name": "City of Boroondara", "job_url": "https://www.boroondara.vic.gov.au/your-council/jobs-and-careers-boroondara"},
    {"name": "Bayside City Council", "job_url": "https://www.bayside.vic.gov.au/council/jobs-and-volunteering-bayside/jobs-and-careers"},
    {"name": "City of Port Phillip", "job_url": "https://www.portphillip.vic.gov.au/about-the-council/careers-at-the-city-of-port-phillip"}
]

DIRECTORY_URL = "https://www.viccouncils.asn.au/work-for-council/council-careers/find-council-jobs"

all_new_jobs = []

def fetch_councils(page):
    """Fetch from directory or fallback."""
    try:
        page.goto(DIRECTORY_URL, wait_until='networkidle', timeout=10000)
        council_links = page.locator('table a[href]').all()
        councils = []
        for link in council_links:
            name = link.inner_text().strip()
            url = link.get_attribute('href')
            if name and url and 'vic.gov.au' in url.lower():
                councils.append({"name": name, "job_url": url})
        logger.info(f"Fetched {len(councils)} councils from directory.")
        return councils[:5] if TEST_MODE else councils  # Limit for test
    except Exception as e:
        logger.warning(f"Directory fetch failed: {e}. Using fallback.")
        return FALLBACK_COUNCILS[:5] if TEST_MODE else FALLBACK_COUNCILS

def parse_date(text, field_type='closing'):
    """Robust date parsing: Extract date from phrase, then parse."""
    if not text or text == "N/A":
        return "N/A"
    # Extract date-like parts (e.g., "Friday, 28 November 2025" → "28 November 2025")
    # Regex for DD Month YYYY or similar
    date_match = re.search(r'(\d{1,2}[a-z]?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})', text, re.I)
    if date_match:
        clean_text = date_match.group(1)
    elif "ongoing" in text.lower() or "applications welcome" in text.lower():
        return "N/A"  # Treat ongoing as no date
    else:
        clean_text = text
    try:
        parsed = date_parser.parse(clean_text)
        return parsed.isoformat()
    except:
        logger.warning(f"Failed to parse {field_type} date: {text}")
        return "N/A"

def generate_rss(jobs):
    """Generate RSS XML from jobs (recent only)."""
    recent_jobs = [j for j in jobs if j['posted_date'] != "N/A" and 
                   datetime.fromisoformat(j['posted_date'].replace('Z', '+00:00')) > 
                   datetime.now() - timedelta(days=RSS_DAYS_BACK)]
    
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'Victorian Councils Job Feed'
    ET.SubElement(channel, 'link').text = 'https://yourusername.github.io/repo-name/'  # Update with your Pages URL
    ET.SubElement(channel, 'description').text = 'Latest jobs from Victorian councils.'
    ET.SubElement(channel, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    
    for job in recent_jobs:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = f"{job['council']} - {job['title']}"
        ET.SubElement(item, 'link').text = job['detail_url']
        ET.SubElement(item, 'description').text = job['description'][:200] + '...'
        ET.SubElement(item, 'pubDate').text = job['posted_date'] if job['posted_date'] != "N/A" else job['scraped_at']
        ET.SubElement(item, 'category').text = job['council']
        ET.SubElement(item, 'guid').text = job['reference_number']
    
    # Pretty XML
    rough_string = ET.tostring(rss, 'unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = context.new_page()

    # Fetch councils
    councils = fetch_councils(page)

    # Scrape each
    for council in councils:
        try:
            logger.info(f"Scraping {council['name']}...")
            page.goto(council['job_url'], timeout=60000)  # 60s timeout
            page.wait_for_load_state('networkidle', timeout=45000)

            # Load more
            while True:
                load_more = page.locator('button:has-text("Load More"), button:has-text("View All"), a:has-text("more jobs")').first
                if load_more.is_visible(timeout=2000):
                    load_more.click()
                    page.wait_for_timeout(DELAY_AFTER_CLICK * 1000)
                else:
                    break

            # Scroll fallback
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(DELAY_AFTER_CLICK)

            # Broader job links locator
            job_links = page.locator('a[href]:has-text("job|position|vacancy|career|role|available")/i').all()[:MAX_JOBS_PER_COUNCIL]

            for link_el in job_links:
                try:
                    job_title = link_el.inner_text().strip() or "N/A"
                    full_url = urljoin(council['job_url'], link_el.get_attribute('href')) if link_el.get_attribute('href') else "N/A"

                    if full_url == "N/A": continue

                    detail_page = context.new_page()
                    try:
                        detail_page.goto(full_url, timeout=60000)
                        detail_page.wait_for_load_state('networkidle', timeout=45000)

                        # Fields extraction
                        description = detail_page.locator('text=/description|about|duties|overview/i').first.inner_text()[:500] or "N/A"
                        closing_text = detail_page.locator('text=/closing|due|apply by|date/i').first.inner_text().strip() or "N/A"
                        closing_date = parse_date(closing_text, 'closing')
                        location = detail_page.locator('text=/location|based in|workplace/i').first.inner_text().strip() or "N/A"
                        employment_type = detail_page.locator('text=/full-time|part-time|casual|contract/i').first.inner_text().strip() or "N/A"
                        salary = detail_page.locator('text=/salary|pay|remuneration|band/i').first.inner_text().strip() or "N/A"
                        band_level = detail_page.locator('text=/VPS|band|level|EO|ST|grade/i').first.inner_text().strip() or "N/A"
                        requirements = [req.strip() for req in detail_page.locator('ul:has-text("requirements"), li:has-text("qualification"), .ksc').all_inner_texts() if req.strip()] or []
                        application_instructions = detail_page.locator('text=/apply|submit|how to/i').first.inner_text().strip() or "N/A"
                        contact_info = detail_page.locator('a[href^="mailto"], text=/contact|hr/i').first.inner_text().strip() or "N/A"
                        ref_text = detail_page.locator('text=/reference|job id|req|advert/i').first.inner_text().strip()
                        reference_number = ref_text or str(uuid.uuid4())
                        department = detail_page.locator('text=/department|team|division/i').first.inner_text().strip() or "N/A"
                        posted_text = detail_page.locator('text=/posted|advertised|published|opens|date advertised/i').first.inner_text().strip() or "N/A"
                        posted_date = parse_date(posted_text, 'posted')

                        all_new_jobs.append({
                            'title': job_title,
                            'council': council['name'],
                            'detail_url': full_url,
                            'closing_date': closing_date,
                            'location': location,
                            'employment_type': employment_type,
                            'salary': salary,
                            'band_level': band_level,
                            'description': description,
                            'requirements': requirements,
                            'application_instructions': application_instructions,
                            'contact_info': contact_info,
                            'reference_number': reference_number,
                            'department': department,
                            'posted_date': posted_date,
                            'scraped_at': datetime.now().isoformat()
                        })

                    except Exception as detail_e:
                        logger.error(f"Detail page timeout/error for {full_url}: {detail_e}")
                    finally:
                        detail_page.close()
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error on job for {council['name']}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to scrape {council['name']}: {e}")
            continue

        time.sleep(DELAY_BETWEEN_COUNCILS)

    browser.close()

# Dedup & Append (enhanced: fallback unique key)
output_file = 'jobs_output.json'
existing_jobs = []
if os.path.exists(output_file):
    with open(output_file, 'r', encoding='utf-8') as f:
        existing_jobs = json.load(f)

combined_jobs = existing_jobs + all_new_jobs

if combined_jobs:
    df = pd.DataFrame(combined_jobs)
    df['scraped_at'] = pd.to_datetime(df['scraped_at'])
    # Fallback key if ref missing
    df['unique_key'] = df['reference_number'].fillna(df['title'] + '|' + df['council'] + '|' + df['detail_url'])
    df_dedup = df.sort_values('scraped_at').drop_duplicates(subset=['unique_key'], keep='last')
    combined_jobs = df_dedup.drop('unique_key', axis=1).to_dict('records')

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(combined_jobs, f, indent=2, default=str)

# Generate RSS
rss_xml = generate_rss(combined_jobs)
with open('rss.xml', 'w', encoding='utf-8') as f:
    f.write(rss_xml)

logger.info(f"Appended {len(all_new_jobs)} new jobs. Total after dedup: {len(combined_jobs)}. RSS generated.")
