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

# Fallback councils
FALLBACK_COUNCILS = [
    {"name": "City of Ballarat", "job_url": "https://www.ballarat.vic.gov.au/careers"},
    {"name": "City of Melbourne", "job_url": "https://www.melbourne.vic.gov.au/jobs-and-careers"},
    {"name": "City of Yarra", "job_url": "https://www.yarracity.vic.gov.au/about-us/work-with-us"},
    {"name": "City of Boroondara", "job_url": "https://www.boroondara.vic.gov.au/your-council/jobs-and-careers-boroondara"},
    {"name": "Bayside City Council", "job_url": "https://www.bayside.vic.gov.au/council/jobs-and-volunteering-bayside/jobs-and-careers"}
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
        if QUICK_TEST_COUNCILS:
            # Filter to quick test
            councils = [c for c in councils if c['name'] in QUICK_TEST_COUNCILS]
            logger.info(f"Quick test mode: Running only {QUICK_TEST_COUNCILS}")
        return councils[:5] if TEST_MODE and not QUICK_TEST_COUNCILS else councils
    except Exception as e:
        logger.warning(f"Directory fetch failed: {e}. Using fallback.")
        fallback = FALLBACK_COUNCILS
        if QUICK_TEST_COUNCILS:
            fallback = [c for c in fallback if c['name'] in QUICK_TEST_COUNCILS]
        return fallback[:5] if TEST_MODE else fallback

def parse_date(text, field_type='closing'):
    """Robust date parsing: Extract date from phrase, then parse."""
    if not text or text == "N/A":
        return "N/A"
    # Extract date-like parts
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
                   datetime.now() - timedelta(days=RSS_DAYS_BACK)]
    
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

def explore_page(page, current_url, depth, max_depth, council_name, visited_urls):
    """Recursive exploration: Click buttons/links, find jobs."""
    if depth > max_depth or current_url in visited_urls:
        return []

    visited_urls.add(current_url)
    logger.info(f"Exploring level {depth} for {council_name} at {current_url}")

    page.goto(current_url, timeout=90000)
    page.wait_for_load_state('networkidle', timeout=90000)
    page_title = page.title()
    logger.info(f"Page title: {page_title}")

    # Load more/scroll
    try:
        while True:
            load_more = page.locator('button:has-text("Load More"), button:has-text("View All"), a:has-text("more jobs")').first
            if load_more.is_visible(timeout=2000):
                load_more.click()
                page.wait_for_timeout(DELAY_AFTER_CLICK * 1000)
            else:
                break
    except Exception as load_e:
        logger.warning(f"Load more error: {load_e}")

    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(DELAY_AFTER_CLICK)

    # Look for job links at this level
    jobs_found = []
    try:
        # Primary: Links with job-related text (OR chain)
        job_locator = page.locator('a[href]:has-text("job")').or_(page.locator('a[href]:has-text("position")')).or_(page.locator('a[href]:has-text("vacancy")')).or_(page.locator('a[href]:has-text("career")')).or_(page.locator('a[href]:has-text("role")')).or_(page.locator('a[href]:has-text("available")')).or_(page.locator('a[href]:has-text("opening")'))
        job_links = job_locator.all()[:MAX_JOBS_PER_COUNCIL]
        if len(job_links) == 0:
            # Fallback 1: Href paths
            job_links = page.locator('a[href*="/job/"], a[href*="/vacancy/"], a[href*="/career/"], a[href*="/position/"]').all()[:MAX_JOBS_PER_COUNCIL]
        if len(job_links) == 0:
            # Fallback 2: "Apply" or "Position" text
            job_links = page.locator('a:has-text("apply"), a:has-text("position")').all()[:MAX_JOBS_PER_COUNCIL]
        # Portal-specific (e.g., Pulse)
        if "pulse" in current_url.lower():
            job_links = page.locator('.job-item a, .job-title a').all()[:MAX_JOBS_PER_COUNCIL]

        logger.info(f"Level {depth}: Found {len(job_links)} potential job links.")

        if len(job_links) == 0:
            logger.info(f"No jobs found at level {depth} for {council_name}—page may be empty.")

        for link_el in job_links:
            job_title = link_el.inner_text().strip() or "N/A"
            full_url = urljoin(current_url, link_el.get_attribute('href')) if link_el.get_attribute('href') else "N/A"
            if full_url == "N/A":
                continue

            # Extract details if this is a job detail page
            detail_page = page
            try:
                if '/job/' in full_url.lower() or 'vacancy' in full_url.lower() or 'pulse' in full_url.lower():
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
                        'council': council_name,
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
                    logger.info(f"Added job: {job_title} for {council_name}")
                else:
                    # Recurse to sub-page
                    sub_jobs = explore_page(page, full_url, depth + 1, max_depth, council_name, visited_urls.copy())
                    jobs_found.extend(sub_jobs)
            except Exception as e:
                logger.error(f"Error extracting job details for {full_url}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error exploring page {current_url}: {e}")

    # Look for navigation buttons/links to deeper levels (enhanced for "Current Vacancies")
    try:
        # OR chain for nav text (case-insensitive)
        nav_locator = page.locator('a:has-text("current vacancies")').or_(page.locator('a:has-text("view jobs")')).or_(page.locator('a:has-text("job portal")')).or_(page.locator('a:has-text("vacancy")')).or_(page.locator('a:has-text("position")')).or_(page.locator('a:has-text("job list")')).or_(page.locator('a:has-text("current roles")')).or_(page.locator('a:has-text("opportunities")')).or_(page.locator('button:has-text("view")')).or_(page.locator('button:has-text("show")')).or_(page.locator('button:has-text("see all")'))
        nav_links = nav_locator.all()[:3]  # Limit to 3
        for nav_el in nav_links:
            nav_text = nav_el.inner_text().strip().lower()
            if 'current vacanc' in nav_text or 'view jobs' in nav_text or 'job portal' in nav_text:
                nav_url = urljoin(current_url, nav_el.get_attribute('href')) if nav_el.get_attribute('href') else current_url
                if nav_url not in visited_urls and nav_text:
                    logger.info(f"Clicked nav '{nav_text}' for deeper exploration.")
                    if nav_el.tag_name() == 'button':
                        nav_el.click()
                    else:
                        page.goto(nav_url)
                    page.wait_for_timeout(DELAY_AFTER_CLICK * 1000)
                    sub_jobs = explore_page(page, nav_url, depth + 1, max_depth, council_name, visited_urls.copy())
                    jobs_found.extend(sub_jobs)
    except Exception as nav_e:
        logger.warning(f"Navigation error for {council_name}: {nav_e}")

    return jobs_found

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = context.new_page()

    # Fetch councils
    councils = fetch_councils(page)

    # Scrape each with recursion (max_depth=3)
    for council in councils:
        visited_urls = set()
        council_jobs = explore_page(page, council['job_url'], 1, 3, council['name'], visited_urls)
        logger.info(f"Total jobs for {council['name']}: {len(council_jobs)}")
        all_new_jobs.extend(council_jobs)
        time.sleep(DELAY_BETWEEN_COUNCILS)

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

logger.info(f"Appended {len(all_new_jobs)} new jobs. Total after dedup: {len(combined_jobs)}. RSS generated.")
