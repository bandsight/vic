import json
import time
import re
import uuid
import logging
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from xml.etree import ElementTree as ET
from xml.dom import minidom
from playwright.sync_api import sync_playwright

from config import (
    ACTIVE_TENANCY,
    MAX_JOBS,
    RSS_LOOKBACK_DAYS,
    SCROLL_DELAY_SECONDS,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('scrape.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Derived shortcuts for readability
PULSE_URL = ACTIVE_TENANCY.listing_url
COUNCIL_NAME = ACTIVE_TENANCY.name

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

def slug_title(title):
    """Slug for URL from title."""
    return re.sub(r'[^a-zA-Z0-9\s-]', '', title).lower().strip().replace(' ', '-').replace('--', '-')

def generate_rss(jobs):
    """Generate RSS XML from jobs (recent only)."""
    recent_jobs = [
        j
        for j in jobs
        if j['posted_date'] != "N/A" and
        datetime.fromisoformat(j['posted_date'].replace('Z', '+00:00'))
        > datetime.now() - timedelta(days=RSS_LOOKBACK_DAYS)
    ]
    
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
    page.wait_for_load_state('domcontentloaded', timeout=30000)
    page_title = page.title()
    logger.info(f"Page title: {page_title}")

    # Trigger Vue load if defined
    try:
        page.evaluate("if (typeof load === 'function') load();")
        logger.info("Triggered Vue load().")
    except:
        logger.warning("No load() function found.")

    # Wait for Vue to mount and render jobs (check for .row.card-row from template)
    try:
        page.wait_for_function(
            f"document.querySelectorAll('.row.card-row').length >= {ACTIVE_TENANCY.min_card_rows}",
            timeout=60000,
        )
        logger.info("%s job rows loaded via Vue.", ACTIVE_TENANCY.min_card_rows)
    except:
        logger.warning(
            "Less than %s job rows after 60s—continuing with available.",
            ACTIVE_TENANCY.min_card_rows,
        )

    # Screenshot for debug
    page.screenshot(path='pulse_list.png')
    logger.info("Screenshot saved: pulse_list.png")

    # Extra scrolls to ensure full load
    for i in range(20):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(SCROLL_DELAY_SECONDS)
        logger.info(f"Scroll {i+1}/20 complete.")

    # Access Vue data directly via evaluate (wrapped in IIFE for scope)
    vue_jobs = []
    try:
        vue_jobs = page.evaluate("""
            (function() {
                try {
                    var vm = document.querySelector('#ctl00_ctl00_BodyContainer_BodyContainer_ctl00_JobsList').__vue__;
                    if (vm && vm.jobs && vm.jobs.length > 0) {
                        return vm.jobs.map(job => ({
                            linkId: job.LinkId,
                            title: job.JobInfo.Title,
                            closingDate: job.JobInfo.ClosingDate,
                            compensation: job.JobInfo.Compensation,
                            location: job.JobInfo.Location,
                            department: job.JobInfo.Department,
                            employmentType: job.JobInfo.EmploymentType,
                            workArrangement: job.JobInfo.WorkArrangement,
                            jobRef: job.JobInfo.JobRef
                        }));
                    }
                } catch (e) {
                    console.error('Vue access error:', e);
                }
                return [];
            })();
        """)
        logger.info(f"Accessed Vue data: {len(vue_jobs)} jobs.")
    except Exception as e:
        logger.error(f"Error accessing Vue data: {e}")

    # Fallback: Scrape from rendered DOM if Vue failed (simplified pure JS)
    if len(vue_jobs) == 0:
        try:
            dom_jobs = page.evaluate("""
                (function() {
                    try {
                        var rows = document.querySelectorAll('.row.card-row');
                        var jobs = [];
                        for (var i = 0; i < rows.length; i++) {
                            var row = rows[i];
                            var title = row.querySelector('.job-title span') ? row.querySelector('.job-title span').textContent.trim() : 'N/A';
                            if (title === 'N/A') continue;
                            var linkId = 'unknown';  // Derive from pattern or skip
                            var rowText = row.innerText;
                            // Regex for fields from row text (fixed backslashes)
                            var closingMatch = rowText.match(/Closing date:\\s*([\\w\\s,]+\\d{4})/i);
                            var compensationMatch = rowText.match(/Compensation:\\s*([\\$\\d,\\s-]+)/i);
                            var locationMatch = rowText.match(/Location:\\s*([\\w\\s,]+)/i);
                            var departmentMatch = rowText.match(/Department:\\s*([\\w\\s]+)/i);
                            var employmentMatch = rowText.match(/Employment type:\\s*([\\w\\s]+)/i);
                            jobs.push({
                                title: title,
                                linkId: linkId,
                                closingDate: closingMatch ? closingMatch[1].trim() : 'N/A',
                                compensation: compensationMatch ? compensationMatch[1].trim() : 'N/A',
                                location: locationMatch ? locationMatch[1].trim() : 'N/A',
                                department: departmentMatch ? departmentMatch[1].trim() : 'N/A',
                                employmentType: employmentMatch ? employmentMatch[1].trim() : 'N/A',
                                jobRef: linkId  // Derive from linkId for fallback
                            });
                        }
                        return jobs;
                    } catch (e) {
                        console.error('DOM fallback error:', e);
                    }
                    return [];
                })();
            """)
            logger.info(f"Fallback DOM scrape: {len(dom_jobs)} jobs.")
            vue_jobs = dom_jobs  # Use fallback
        except Exception as fallback_e:
            logger.error(f"Fallback DOM error: {fallback_e}")

    # Process jobs (from Vue or fallback)
    for job in vue_jobs[:MAX_JOBS]:
        job_title = job['title'] or "N/A"
        link_id = job['linkId'] or 'unknown'
        job_ref = job.get('jobRef', link_id) or str(uuid.uuid4())  # Safe get
        # Construct detail URL
        slug = slug_title(job_title)
        full_url = f"{PULSE_URL}/job/{link_id}/{slug}?source=public"
        
        # Extract from job dict
        closing_text = job.get('closingDate', "N/A") or "N/A"
        closing_date = parse_date(closing_text, 'closing')
        salary = job.get('compensation', "N/A") or "N/A"
        location = job.get('location', "N/A") or "N/A"
        employment_type = job.get('employmentType', "N/A") or "N/A"
        department = job.get('department', "N/A") or "N/A"
        posted_date = "N/A"  # Assume scraped_at

        # Goto detail for full description/requirements
        detail_page = context.new_page()
        try:
            detail_page.goto(full_url, timeout=60000)
            detail_page.wait_for_load_state('domcontentloaded', timeout=30000)
            description = detail_page.locator('.job-description, .role-overview, text=/duties|overview/i').first.inner_text()[:500] or "N/A"
            requirements = [req.strip() for req in detail_page.locator('ul:has-text("requirements"), li:has-text("qualification")').all_inner_texts() if req.strip()] or []
            application_instructions = detail_page.locator('text=/apply|submit/i').first.inner_text().strip() or "N/A"
            contact_info = detail_page.locator('a[href^="mailto"]').first.inner_text().strip() or "N/A"
            band_level = detail_page.locator('text=/VPS|band|level|EO|ST|grade/i').first.inner_text().strip() or "N/A"
        except Exception as detail_e:
            logger.error(f"Detail page error for {full_url}: {detail_e}")
            description = "N/A"
            requirements = []
            application_instructions = "N/A"
            contact_info = "N/A"
            band_level = "N/A"
        finally:
            detail_page.close()

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
            'reference_number': job_ref,
            'department': department,
            'posted_date': posted_date,
            'scraped_at': datetime.now().isoformat()
        })
        logger.info(f"Added job: {job_title} for {COUNCIL_NAME} (Ref: {job_ref})")
        time.sleep(1)

    browser.close()

# Full Overwrite JSON (no append/dedup for testing)
output_file = 'jobs_output.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_new_jobs, f, indent=2, default=str)

logger.info(f"Overwrote JSON with {len(all_new_jobs)} jobs from Pulse.")

# Generate RSS
rss_xml = generate_rss(all_new_jobs)
with open('rss.xml', 'w', encoding='utf-8') as f:
    f.write(rss_xml)

logger.info(f"RSS generated with {len(all_new_jobs)} jobs.")
