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

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('scrape.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Hardcoded for Ballarat Pulse
PULSE_URL = "https://ballarat.pulsesoftware.com/Pulse/jobs"
COUNCIL_NAME = "City of Ballarat"
MAX_JOBS = 15  # Limit to match known
DELAY_SCROLL = 1  # Seconds between scrolls (shorter for speed)

all_new_jobs = []

def parse_date(text, field_type='closing'):
    """Robust date parsing."""
    if not text or text == "N/A":
        return "N/A"
    date_match = re.search(r'(\d{1,2}[a-z]?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})', text, re.I)
    if date_match:
        clean_text = date_match.group(1)
    elif "ongoing" in text.lower():
        return "N/A"
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
                   datetime.now() - timedelta(days=30)]
    
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'Victorian Councils Job Feed'
    ET.SubElement(channel, 'link').text = 'https://bandsight.github.io/vic/'
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
    
    rough_string = ET.tostring(rss, 'unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ')

# Main scrape for Pulse
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = context.new_page()

    logger.info(f"Starting scrape for {COUNCIL_NAME} at {PULSE_URL}")

    page.goto(PULSE_URL, timeout=90000)
    page.wait_for_load_state('domcontentloaded', timeout=30000)  # DOM ready, not networkidle
    page_title = page.title()
    logger.info(f"Page title: {page_title}")

    # Wait for job elements to load on Pulse
    try:
        page.wait_for_selector('.job-item, .listing-card, .vacancy-card, [class*="job"], [class*="listing"]', timeout=30000)
        logger.info("Job elements loaded.")
    except:
        logger.warning("Job elements not found after 30s—may be dynamic; continuing.")

    # Extra scrolls to load all 15 jobs
    for i in range(15):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(DELAY_SCROLL)
        logger.info(f"Scroll {i+1}/15 complete.")

    # Find job links on Pulse
    job_links = []
    try:
        # Primary Pulse locators (broad for cards)
        job_locator = page.locator('.job-item a, .job-title a, .listing a, .vacancy a, a[href*="/job/"], a:has-text("job")').all()[:MAX_JOBS]
        job_links = job_locator
        if len(job_links) == 0:
            # Fallback: Any a with "position" or "role" or "officer"
            job_links = page.locator('a:has-text("position"), a:has-text("role"), a:has-text("officer"), a:has-text("apply")').all()[:MAX_JOBS]

        logger.info(f"Found {len(job_links)} job links on Pulse.")

        for link_el in job_links:
            job_title = link_el.inner_text().strip() or "N/A"
            full_url = urljoin(PULSE_URL, link_el.get_attribute('href')) if link_el.get_attribute('href') else "N/A"
            if full_url == "N/A":
                continue

            # Follow to detail (Pulse job pages)
            detail_page = context.new_page()
            try:
                detail_page.goto(full_url, timeout=60000)
                detail_page.wait_for_load_state('domcontentloaded', timeout=30000)

                # Pulse-specific extraction (broad locators)
                description = detail_page.locator('text=/description|about|duties|overview/i, .job-description, .role-overview').first.inner_text()[:500] or "N/A"
                closing_text = detail_page.locator('text=/closing|due|apply by|date/i, .job-deadline, .application-deadline, .closing-date').first.inner_text().strip() or "N/A"
                closing_date = parse_date(closing_text, 'closing')
                location = detail_page.locator('text=/location|based in|workplace/i, .job-location').first.inner_text().strip() or "N/A"
                employment_type = detail_page.locator('text=/full-time|part-time|casual|contract/i').first.inner_text().strip() or "N/A"
                salary = detail_page.locator('text=/salary|pay|remuneration|band/i, .job-salary, .salary-range').first.inner_text().strip() or "N/A"
                band_level = detail_page.locator('text=/VPS|band|level|EO|ST|grade/i').first.inner_text().strip() or "N/A"
                requirements = [req.strip() for req in detail_page.locator('ul:has-text("requirements"), li:has-text("qualification"), .ksc, .job-requirements').all_inner_texts() if req.strip()] or []
                application_instructions = detail_page.locator('text=/apply|submit|how to/i, .application-section').first.inner_text().strip() or "N/A"
                contact_info = detail_page.locator('a[href^="mailto"], text=/contact|hr/i').first.inner_text().strip() or "N/A"
                ref_text = detail_page.locator('text=/reference|job id|req|advert/i').first.inner_text().strip()
                reference_number = ref_text or str(uuid.uuid4())
                department = detail_page.locator('text=/department|team|division/i').first.inner_text().strip() or "N/A"
                posted_text = detail_page.locator('text=/posted|advertised|published|opens|date advertised/i').first.inner_text().strip() or "N/A"
                posted_date = parse_date(posted_text, 'posted')

                all_new_jobs.append({
                    'title': job_title,
                    'council': COUNCIL_NAME,
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
                logger.info(f"Added job: {job_title} for {COUNCIL_NAME}")

            except Exception as detail_e:
                logger.error(f"Detail page error for {full_url}: {detail_e}")
            finally:
                detail_page.close()
            time.sleep(1)

    except Exception as e:
        logger.error(f"Error exploring Pulse page: {e}")

    browser.close()

# Dedup & Append
output_file = 'jobs_output.json'
existing_jobs = []
if os.path.exists(output_file):
    with open(output_file, 'r', encoding='utf-8') as f:
        existing_jobs = json.load(f)

combined_jobs = existing_jobs + all_new_jobs

if combined_jobs:
    df = pd.DataFrame(combined_jobs)
    df['scraped_at'] = pd.to_datetime(df['scraped_at'])
    df['unique_key'] = df['reference_number'].fillna(df['title'] + '|' + df['council'] + '|' + df['detail_url'])
    df_dedup = df.sort_values('scraped_at').drop_duplicates(subset=['unique_key'], keep='last')
    combined_jobs = df_dedup.drop('unique_key', axis=1).to_dict('records')

with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(combined_jobs, f, indent=2, default=str)

# Generate RSS
rss_xml = generate_rss(combined_jobs)
with open('rss.xml', 'w', encoding='utf-8') as f:
    f.write(rss_xml)

logger.info(f"Appended {len(all_new_jobs)} new jobs from Pulse. Total after dedup: {len(combined_jobs)}. RSS generated.")
