import argparse
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from dateutil import parser as date_parser
from xml.etree import ElementTree as ET
from xml.dom import minidom
from playwright.sync_api import sync_playwright

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('scrape.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Hardcoded for Ballarat Pulse
PULSE_URL = "https://ballarat.pulsesoftware.com/Pulse/jobs"
COUNCIL_NAME = "City of Ballarat"
MAX_JOBS = 20  # Buffer for 15+
DELAY_SCROLL = 1  # Seconds
DEFAULT_FIXTURE_PATH = Path("docs/pulse_fixture.json")

ERROR_TOKENS = {"most likely causes:", "404", "error"}

EXPAND_BUTTON_PATTERNS = [
    r"view more",
    r"show more",
    r"see more",
    r"read more",
    r"expand",
]

EMPLOYMENT_TYPE_MAP = {
    "fixed term": "Full Time",
    "temporary": "Full Time",
    "ongoing": "Full Time",
    "perm": "Full Time",
    "permanent": "Full Time",
    "casual": "Casual",
    "volunteer": "Volunteer",
    "part time": "Part Time",
}

DEPARTMENT_REPLACEMENTS = {
    "enviro": "Environment",
}

JOB_CATEGORY_MAP = {
    "economy and experience": "Arts & Culture",
    "infrastructure": "Infrastructure & Engineering",
    "community wellbeing": "Community Services",
    "development": "Planning & Development",
}


def safe_first_text(page, selector, default="N/A"):
    """Return first matching locator text if it exists, otherwise default."""
    try:
        loc = page.locator(selector)
        if loc.count() == 0:
            return default
        text = loc.first.inner_text().strip()
        return text if text else default
    except Exception as exc:
        logger.debug(f"safe_first_text failed for selector '{selector}': {exc}")
        return default


def safe_first_text_regex(page, pattern, default="N/A"):
    """Return first text node matching regex via get_by_text, else default."""
    try:
        loc = page.get_by_text(pattern, exact=False)
        if loc.count() == 0:
            return default
        text = loc.first.inner_text().strip()
        return text if text else default
    except Exception as exc:
        logger.debug(f"safe_first_text_regex failed for pattern '{pattern.pattern}': {exc}")
        return default


def clean_text(value, default="N/A"):
    """Trim whitespace, drop known error tokens, return default if empty."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    lowered = text.lower()
    if any(token in lowered for token in ERROR_TOKENS):
        return default
    return text


def clean_title(title):
    return clean_text(title)


def clean_council(council):
    council_text = clean_text(council, COUNCIL_NAME)
    return council_text or COUNCIL_NAME


def validate_url(url):
    url_text = clean_text(url)
    if url_text == "N/A":
        return url_text, True
    is_valid = not re.search(r"unknown", url_text, re.I)
    return url_text, is_valid


def parse_date_field(text):
    text = clean_text(text)
    if text == "N/A":
        return "N/A"
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return iso_match.group(1)
    if "ongoing" in text.lower():
        return "N/A"
    try:
        parsed = date_parser.parse(text)
        return parsed.date().isoformat()
    except Exception:
        logger.warning(f"Failed to parse closing date: {text}")
        return "N/A"


def parse_closing_time(text):
    text = clean_text(text)
    if text == "N/A":
        return "N/A"
    time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", text, re.I)
    return time_match.group(1).upper() if time_match else "N/A"


def clean_location(location):
    text = clean_text(location)
    if text == "N/A":
        return text
    first_line = text.split("\n")[0]
    first_line = re.split(r"\b(?:Department|Compensation|Employment type)\b", first_line, flags=re.I)[0]
    return first_line.strip().rstrip(",;-") or "N/A"


def normalize_employment_type(raw):
    text = clean_text(raw)
    if text == "N/A":
        return text
    first_piece = text.split("\n")[0].strip()
    lowered = first_piece.lower()
    for key, value in EMPLOYMENT_TYPE_MAP.items():
        if key in lowered:
            return value
    return first_piece.title()


def extract_work_arrangement(*parts):
    combined = " ".join(filter(None, [clean_text(part, "") for part in parts])).lower()
    for option in ("hybrid", "remote", "flexible", "onsite"):
        if option in combined:
            return option.title()
    return "N/A"


def expand_collapsible_sections(page):
    """Click any collapsible triggers so the DOM contains the full detail text."""
    for pattern in EXPAND_BUTTON_PATTERNS:
        try:
            buttons = page.get_by_role("button", name=re.compile(pattern, re.I))
            for index in range(buttons.count()):
                try:
                    buttons.nth(index).click(timeout=2000)
                    time.sleep(0.2)
                except Exception:
                    continue
        except Exception:
            continue
        try:
            links = page.get_by_role("link", name=re.compile(pattern, re.I))
            for index in range(links.count()):
                try:
                    links.nth(index).click(timeout=2000)
                    time.sleep(0.2)
                except Exception:
                    continue
        except Exception:
            continue


def parse_salary_fields(raw):
    text = clean_text(raw)
    if text == "N/A":
        return "N/A", "N/A"
    range_match = re.search(r"\$?[\d,]+k?(?:\s*-\s*\$?[\d,]+k?)?", text, re.I)
    salary = range_match.group(0).replace("  ", " ") if range_match else "N/A"
    type_match = re.search(r"\b(pa|per annum|ph|p/h|per hour)\b", text, re.I)
    salary_type = type_match.group(1).lower() if type_match else "N/A"
    if salary == "N/A":
        return "N/A", "N/A"
    salary = salary.replace("  ", " ")
    if salary_type in {"pa", "per annum"}:
        normalized_type = "per annum"
    elif salary_type in {"ph", "p/h", "per hour"}:
        normalized_type = "per hour"
    else:
        normalized_type = salary_type
    return salary, (normalized_type if normalized_type else "N/A")


def clean_department(raw):
    text = clean_text(raw)
    if text == "N/A":
        return text
    first_line = text.split("\n")[0]
    for short, proper in DEPARTMENT_REPLACEMENTS.items():
        first_line = re.sub(short, proper, first_line, flags=re.I)
    return first_line.strip()


def infer_job_category(department, band_level):
    if department and department != "N/A":
        lowered = department.lower()
        for key, value in JOB_CATEGORY_MAP.items():
            if key in lowered:
                return value
    if band_level and band_level != "N/A":
        digit = int(band_level[0])
        if digit <= 3:
            return "Entry Level"
        if digit <= 5:
            return "Mid Level"
        return "Senior Leadership"
    return "N/A"


def extract_section_bullets(page, keywords):
    """Use JS to capture list items that follow headings containing keywords."""
    try:
        items = page.evaluate(
            """
            (keywords) => {
                const lowered = keywords.map(k => k.toLowerCase());
                const matches = [];
                const headingSelectors = 'h1,h2,h3,h4,h5,strong,p';
                const nodes = Array.from(document.querySelectorAll(headingSelectors));
                nodes.forEach(node => {
                    const text = (node.textContent || '').trim().toLowerCase();
                    if (!text) return;
                    lowered.forEach(keyword => {
                        if (text.includes(keyword)) {
                            let sibling = node.nextElementSibling;
                            while (sibling && !(sibling.tagName === 'UL' || sibling.tagName === 'OL')) {
                                sibling = sibling.nextElementSibling;
                            }
                            if (sibling && (sibling.tagName === 'UL' || sibling.tagName === 'OL')) {
                                sibling.querySelectorAll('li').forEach(li => {
                                    const value = li.textContent.trim();
                                    if (value) matches.push(value);
                                });
                            }
                        }
                    });
                });
                return matches;
            }
            """,
            keywords,
        )
        return [item.strip() for item in items if item and item.strip()]
    except Exception as exc:
        logger.debug(f"extract_section_bullets failed for {keywords}: {exc}")
        return []


def extract_description(page):
    selectors = [
        '.job-description',
        '.role-overview',
        '.jobSummary',
        'article',
        'main',
        '.job-detail',
        '.job-details',
    ]
    parts = []
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if loc.count() > 0:
                parts.extend(loc.all_inner_texts())
        except Exception:
            continue
    if not parts:
        fallback = safe_first_text_regex(page, re.compile(r'(duties|overview|about the role)', re.I))
        if fallback != "N/A":
            parts.append(fallback)
    if not parts:
        try:
            body_text = page.inner_text('body')
            if body_text:
                parts.append(body_text)
        except Exception:
            pass
    description = " ".join(part.strip() for part in parts if part and part.strip()).strip()
    return description[:5000] if description else "N/A"


def extract_application_instructions(text):
    text = clean_text(text)
    if text == "N/A":
        return text
    match = re.search(r"(apply[\s\S]{0,120})", text, re.I)
    return match.group(1).strip() if match else "N/A"


def extract_contact_info(text):
    text = clean_text(text)
    if text == "N/A":
        return text
    emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
    phones = set(re.findall(r"\b\d{2,4}[-\s]?\d{3}[-\s]?\d{3,4}\b", text))
    contacts = sorted(emails | phones)
    return " | ".join(contacts) if contacts else "N/A"


def extract_band_level(text):
    text = clean_text(text)
    if text == "N/A":
        return text
    match = re.search(r"\b(?:band|level)\s*([1-8][A-Z]?)\b", text, re.I)
    if match:
        return match.group(1).upper()
    standalone = re.search(r"\b([1-8][A-Z]?)\b", text)
    return standalone.group(1).upper() if standalone else "N/A"


def extract_benefits(page, text):
    bullets = extract_section_bullets(page, ["benefits", "perks", "what we offer"])
    if bullets:
        return "; ".join(dict.fromkeys(bullets))
    text = clean_text(text)
    if text == "N/A":
        return text
    match = re.search(r"(11\.?\d?%\s*super.*)", text, re.I)
    return match.group(1).strip() if match else "N/A"


def extract_attachments(page):
    try:
        hrefs = page.eval_on_selector_all("a[href*='.pdf']", "elements => elements.map(a => a.getAttribute('href'))")
    except Exception as exc:
        logger.debug(f"extract_attachments failed: {exc}")
        hrefs = []
    attachments = []
    for href in hrefs:
        if not href:
            continue
        attachments.append(urljoin(page.url, href))
    return attachments


def extract_num_positions(text):
    text = clean_text(text)
    if text == "N/A":
        return 1
    match = re.search(r"(\d+)\s+position", text, re.I)
    if match:
        return max(1, int(match.group(1)))
    return 1


def extract_eeo(text):
    text = clean_text(text)
    if text == "N/A":
        return text
    match = re.search(r"(equal opportunity[\s\S]{0,120})", text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"(diverse[\s\S]{0,120})", text, re.I)
    return match.group(1).strip() if match else "N/A"


def extract_posted_date(text):
    text = clean_text(text)
    if text == "N/A":
        return text
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else "N/A"


def extract_label_value(text, labels):
    text = clean_text(text, "")
    if not text:
        return "N/A"
    for label in labels:
        pattern = re.compile(rf"{label}\s*(?:[:\-]\s*|\s+)([^\n\r]+)", re.I)
        match = pattern.search(text)
        if match:
            return clean_text(match.group(1))
    return "N/A"


def resolve_detail_url(job_dict, fallback_slug):
    """Best-effort resolver for the absolute job detail URL."""

    def _normalize(candidate):
        candidate = clean_text(candidate, "")
        if not candidate:
            return ""
        if candidate.startswith("http"):
            return candidate
        return urljoin(PULSE_URL + "/", candidate.lstrip("/"))

    for key in ("detailHref", "detailUrl", "detail_url", "url"):
        candidate = _normalize(job_dict.get(key, ""))
        if candidate:
            return candidate

    link_id = clean_text(job_dict.get('linkId', ''), '')
    slug_from_data = slug_title(job_dict.get('slug', '') or job_dict.get('title', '') or fallback_slug)
    slug = slug_from_data if slug_from_data else fallback_slug
    if link_id and link_id.lower() != 'unknown':
        return f"{PULSE_URL}/job/{link_id}/{slug}?source=public"

    href_from_dom = clean_text(job_dict.get('domHref', ''), '')
    candidate = _normalize(href_from_dom)
    if candidate:
        return candidate

    return "N/A"


def build_parse_flags(job_record):
    flags = []
    if "unknown" in job_record['detail_url']:
        flags.append("invalid_url")
    if job_record['salary'] == "N/A":
        flags.append("missing_salary")
    if job_record['benefits'] == "N/A":
        flags.append("missing_benefits")
    if not job_record['attachments']:
        flags.append("no_attachments")
    if not job_record['key_criteria']:
        flags.append("missing_key_criteria")
    if job_record['band_level'] == "N/A":
        flags.append("scraping_error_band")
    if isinstance(job_record['num_positions'], int) and job_record['num_positions'] < 1:
        flags.append("invalid_num_positions")
    return flags

def slug_title(title):
    """Slug for URL from title."""
    return re.sub(r'[^a-zA-Z0-9\s-]', '', title).lower().strip().replace(' ', '-').replace('--', '-')


def load_fixture_jobs(path):
    """Load pre-scraped jobs so tests can run without Playwright browsers."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    with path.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    jobs = payload if isinstance(payload, list) else payload.get('jobs', [])
    normalized = []
    for job in jobs:
        job = dict(job)
        job.setdefault('council', clean_council(job.get('council', COUNCIL_NAME)))
        job.setdefault('parse_flags', [])
        job['parse_flags'] = build_parse_flags(job)
        job.setdefault('scraped_at', datetime.utcnow().isoformat())
        normalized.append(job)
    logger.warning(f"Loaded {len(normalized)} jobs from fixture {path}")
    return normalized

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

def scrape_jobs():
    jobs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        logger.info(f"Starting scrape for {COUNCIL_NAME} at {PULSE_URL}")

        page.goto(PULSE_URL, timeout=90000)
        page.wait_for_load_state('domcontentloaded', timeout=30000)
        logger.info(f"Page title: {page.title()}")

        try:
            page.evaluate("if (typeof load === 'function') load();")
            logger.info("Triggered Vue load().")
        except Exception:
            logger.warning("No load() function found.")

        try:
            page.wait_for_function("document.querySelectorAll('.row.card-row').length >= 15", timeout=60000)
            logger.info("15+ job rows loaded via Vue.")
        except Exception:
            logger.warning("Less than 15 job rows after 60s—continuing with available.")

        page.screenshot(path='pulse_list.png')
        logger.info("Screenshot saved: pulse_list.png")

        for i in range(20):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(DELAY_SCROLL)
            logger.info(f"Scroll {i+1}/20 complete.")

        vue_jobs = []
        try:
            vue_jobs = page.evaluate("""
                (function() {
                    try {
                        var vm = document.querySelector('#ctl00_ctl00_BodyContainer_BodyContainer_ctl00_JobsList').__vue__;
                        var cards = Array.from(document.querySelectorAll('.row.card-row'));
                        if (vm && vm.jobs && vm.jobs.length > 0) {
                            return vm.jobs.map(function(job, index) {
                                var card = cards[index];
                                var anchor = card ? card.querySelector('a[href*="/Pulse/jobs/job/"]') : null;
                                var href = anchor ? anchor.href : '';
                                var slug = '';
                                if (href) {
                                    slug = href.split('?')[0].split('/').filter(Boolean).pop() || '';
                                }
                                return {
                                    linkId: job.LinkId,
                                    title: job.JobInfo.Title,
                                    closingDate: job.JobInfo.ClosingDate,
                                    compensation: job.JobInfo.Compensation,
                                    location: job.JobInfo.Location,
                                    department: job.JobInfo.Department,
                                    employmentType: job.JobInfo.EmploymentType,
                                    workArrangement: job.JobInfo.WorkArrangement,
                                    jobRef: job.JobInfo.JobRef,
                                    detailHref: href || 'N/A',
                                    domHref: href || 'N/A',
                                    slug: slug
                                };
                            });
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

        if len(vue_jobs) == 0:
            try:
                dom_jobs = page.evaluate("""
                    (function() {
                        try {
                            var rows = document.querySelectorAll('.row.card-row');
                            var jobs = [];
                            for (var i = 0; i < rows.length; i++) {
                                var row = rows[i];
                                var titleNode = row.querySelector('.job-title span, .job-title a, .job-title');
                                var linkNode = row.querySelector('a[href*="/Pulse/jobs/job/"]');
                                var title = titleNode ? titleNode.textContent.trim() : 'N/A';
                                if (title === 'N/A') continue;
                                var href = linkNode ? linkNode.getAttribute('href') : '';
                                var absoluteHref = '';
                                if (href) {
                                    var a = document.createElement('a');
                                    a.href = href;
                                    absoluteHref = a.href;
                                }
                                var linkId = 'unknown';
                                if (absoluteHref) {
                                    var match = absoluteHref.match(/job\/([^\/]+)\//i);
                                    if (match && match[1]) {
                                        linkId = match[1];
                                    }
                                }
                                var slug = '';
                                if (absoluteHref) {
                                    slug = absoluteHref.split('?')[0].split('/').filter(Boolean).pop() || '';
                                }
                                var rowText = row.innerText || '';
                                var closingMatch = rowText.match(/Closing date:\s*([\w\s,]+\d{4})/i);
                                var compensationMatch = rowText.match(/Compensation:\s*([\$\d,\s-]+)/i);
                                var locationMatch = rowText.match(/Location:\s*([\w\s,]+)/i);
                                var departmentMatch = rowText.match(/Department:\s*([\w\s]+)/i);
                                var employmentMatch = rowText.match(/Employment type:\s*([\w\s]+)/i);
                                jobs.push({
                                    title: title,
                                    linkId: linkId,
                                    closingDate: closingMatch ? closingMatch[1].trim() : 'N/A',
                                    compensation: compensationMatch ? compensationMatch[1].trim() : 'N/A',
                                    location: locationMatch ? locationMatch[1].trim() : 'N/A',
                                    department: departmentMatch ? departmentMatch[1].trim() : 'N/A',
                                    employmentType: employmentMatch ? employmentMatch[1].trim() : 'N/A',
                                    jobRef: linkId,
                                    workArrangement: '',
                                    detailHref: absoluteHref || href || 'N/A',
                                    domHref: absoluteHref || href || 'N/A',
                                    slug: slug
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
                vue_jobs = dom_jobs
            except Exception as fallback_e:
                logger.error(f"Fallback DOM error: {fallback_e}")

        for job in vue_jobs[:MAX_JOBS]:
            job_title = clean_title(job.get('title', 'N/A'))
            link_id = job.get('linkId') or 'unknown'
            raw_ref = clean_text(job.get('jobRef', link_id), 'N/A')
            reference_number = "N/A" if raw_ref.lower() == 'unknown' else raw_ref
            slug = slug_title(job_title if job_title != "N/A" else "role")
            full_url = resolve_detail_url(job, slug)
            detail_url, detail_url_valid = validate_url(full_url)

            closing_text = job.get('closingDate', "N/A") or "N/A"
            closing_date = parse_date_field(closing_text)
            closing_time = parse_closing_time(closing_text)
            salary, salary_type = parse_salary_fields(job.get('compensation', "N/A"))
            location = clean_location(job.get('location', "N/A"))
            employment_type = normalize_employment_type(job.get('employmentType', "N/A"))
            work_arrangement = extract_work_arrangement(job.get('employmentType', ''), job.get('workArrangement', ''))
            department = clean_department(job.get('department', "N/A"))

            detail_page = context.new_page()
            description = "N/A"
            requirements = []
            key_criteria = []
            application_instructions = "N/A"
            contact_info = "N/A"
            band_level = "N/A"
            benefits = "N/A"
            attachments = []
            num_positions = 1
            eeo_statement = "N/A"
            posted_date = "N/A"
            detail_text = ""
            try:
                if detail_url == "N/A" or not detail_url_valid:
                    raise ValueError("Detail URL missing or invalid")
                detail_page.goto(detail_url, timeout=60000)
                detail_page.wait_for_load_state('domcontentloaded', timeout=30000)
                expand_collapsible_sections(detail_page)
                description = extract_description(detail_page)
                requirements = extract_section_bullets(detail_page, ["requirements", "skills", "responsibilities", "experience"])
                key_criteria = extract_section_bullets(detail_page, ["key selection criteria"])
                detail_text = detail_page.inner_text('body')
                application_instructions = extract_application_instructions(detail_text)
                contact_info = extract_contact_info(detail_text)
                band_level = extract_band_level(detail_text)
                benefits = extract_benefits(detail_page, detail_text)
                attachments = extract_attachments(detail_page)
                num_positions = extract_num_positions(detail_text)
                eeo_statement = extract_eeo(detail_text)
                posted_date = extract_posted_date(detail_text)
            except Exception as detail_e:
                logger.error(f"Detail page error for {full_url}: {detail_e}")
            finally:
                detail_page.close()

            requirements = requirements[:10]
            key_criteria = key_criteria[:5]
            band_level = band_level if re.fullmatch(r"[1-8][A-Z]?", band_level or "") else "N/A"
            if salary == "N/A" and detail_text:
                detail_salary_raw = extract_label_value(detail_text, ["salary", "remuneration", "classification", "band", "pay rate"])
                detail_salary, detail_salary_type = parse_salary_fields(detail_salary_raw)
                if detail_salary != "N/A":
                    salary = detail_salary
                    salary_type = detail_salary_type
            if closing_date == "N/A" and detail_text:
                closing_raw = extract_label_value(detail_text, ["closing date", "applications close", "applications closing", "closes"])
                if closing_raw != "N/A":
                    closing_date = parse_date_field(closing_raw)
                    closing_time = parse_closing_time(closing_raw)
            if description == "N/A" and detail_text:
                description = " ".join(line.strip() for line in detail_text.splitlines() if line.strip())[:5000] or "N/A"

            job_category = infer_job_category(department, band_level)
            salary_type_value = salary_type if salary_type else "N/A"
            scraped_at = datetime.utcnow().isoformat()

            job_record = {
                'title': job_title,
                'council': clean_council(COUNCIL_NAME),
                'detail_url': detail_url,
                'closing_date': closing_date,
                'closing_time': closing_time,
                'location': location,
                'employment_type': employment_type,
                'work_arrangement': work_arrangement,
                'salary': salary,
                'salary_type': salary_type_value,
                'band_level': band_level,
                'description': description,
                'requirements': requirements,
                'key_criteria': key_criteria,
                'application_instructions': application_instructions,
                'contact_info': contact_info,
                'reference_number': reference_number,
                'department': department,
                'job_category': job_category,
                'benefits': benefits,
                'attachments': attachments,
                'num_positions': num_positions,
                'eeo_statement': eeo_statement,
                'posted_date': posted_date,
                'scraped_at': scraped_at,
                'parse_flags': [],
            }
            job_record['parse_flags'] = build_parse_flags(job_record)
            jobs.append(job_record)
            logger.info(f"Added job: {job_title} for {COUNCIL_NAME} (Ref: {reference_number})")
            time.sleep(1)

        browser.close()
    return jobs


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Ballarat Pulse jobs or replay a fixture.")
    parser.add_argument('--fixture', type=Path, default=None,
                        help='Optional path to fixture JSON to skip live scraping.')
    parser.add_argument('--fixture-fallback', type=Path, default=DEFAULT_FIXTURE_PATH,
                        help='Use this fixture when live scraping fails (default: docs/pulse_fixture.json).')
    parser.add_argument('--disable-fallback', action='store_true',
                        help='Raise errors instead of falling back to fixture data.')
    return parser.parse_args()


def main():
    args = parse_args()

    if args.fixture:
        jobs = load_fixture_jobs(args.fixture)
    else:
        try:
            jobs = scrape_jobs()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Live scrape failed: {exc}")
            if args.disable_fallback:
                raise
            fallback_path = args.fixture_fallback
            if fallback_path and Path(fallback_path).exists():
                logger.warning(f"Falling back to fixture at {fallback_path}")
                jobs = load_fixture_jobs(fallback_path)
            else:
                raise

    with open('jobs_output.json', 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, default=str)
    logger.info(f"Overwrote JSON with {len(jobs)} jobs from Pulse.")

    rss_xml = generate_rss(jobs)
    with open('rss.xml', 'w', encoding='utf-8') as f:
        f.write(rss_xml)
    logger.info(f"RSS generated with {len(jobs)} jobs.")


if __name__ == '__main__':
    main()
