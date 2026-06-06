"""Victorian council jobs source registry reference data."""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from benchmarking_data_factory.reference.council_master import load_council_master


ROOT = Path(__file__).resolve().parents[3]

SOURCE_MAP_CAPTURED_DATE = date(2026, 5, 11).isoformat()
VIC_COUNCILS_JOBS_DIRECTORY_URL = (
    "https://www.viccouncils.asn.au/work-for-council/council-careers/find-council-jobs"
)

SOURCE_PRIORITY = {
    "official_council_or_ats": 1,
    "sector_directory": 2,
    "sector_aggregator": 3,
    "broad_job_board": 9,
}

COUNCIL_GROUPING_SLUGS = {
    "Metropolitan": "metropolitan",
    "Interface": "interface",
    "Regional": "regional_city",
    "Regional city": "regional_city",
    "Large shire": "large_shire",
    "Small shire": "small_shire",
}

POLL_TIER_BY_GROUPING = {
    "metropolitan": "A",
    "interface": "A",
    "regional_city": "A",
    "large_shire": "B",
    "small_shire": "C",
}

POLL_CADENCE_BY_TIER = {
    "A": "PT1H",
    "B": "PT4H",
    "C": "P1D",
}

POLL_CADENCE_LABELS = {
    "A": "Every 30-60 minutes",
    "B": "Every 2-4 hours",
    "C": "Every 6-24 hours",
}

POLL_TIER_EXPLAINER = [
    {
        "tier": "A",
        "meaning": "Metropolitan, interface and regional-city councils. Highest expected job volume.",
        "cadence": POLL_CADENCE_LABELS["A"],
    },
    {
        "tier": "B",
        "meaning": "Large shires. Moderate expected job volume.",
        "cadence": POLL_CADENCE_LABELS["B"],
    },
    {
        "tier": "C",
        "meaning": "Small shires and low-volume/manual careers pages.",
        "cadence": POLL_CADENCE_LABELS["C"],
    },
]

ADAPTER_BY_PLATFORM = {
    "adlogic_martianlogic": "AggregatorFetcher",
    "applynow": "ApplyNowFetcher",
    "aurion_selfservice": "AggregatorFetcher",
    "bigredsky": "AggregatorFetcher",
    "dayforce": "AggregatorFetcher",
    "native_council": "NativeCouncilFetcher",
    "native_council_custom": "NativeCouncilFetcher",
    "oracle_hcm": "AggregatorFetcher",
    "pageup": "PageUpFetcher",
    "pulse": "PulseFetcher",
    "recruitmenthub": "RecruitmentHubFetcher",
    "smartrecruiters": "SmartRecruitersFetcher",
    "employmenthero": "AggregatorFetcher",
    "elmo_talent": "ElmoTalentFetcher",
    "successfactors": "AggregatorFetcher",
    "t1cloud": "AggregatorFetcher",
    "unknown_official": "NativeCouncilFetcher",
}

ENDPOINT_DISCOVERY_PATTERNS = [
    "pulse_subdomain",
    "recruitmenthub_vacancies",
    "recruitmenthub_current_vacancies",
    "aurion_candidate_portal",
    "bigredsky_page",
    "applynow_portal",
    "t1cloud_public_ext_function",
    "t1cloud_public_function",
    "smartrecruiters_company_api",
    "elmo_talent_portal",
    "pageup_careers_host",
    "adlogic_careers_host",
    "native_career_path",
]

# Current outbound links observed on the Vic Councils "Find council jobs" page.
# For many councils this is an official career landing page rather than the final
# machine-friendly vacancy listing. Platform overlays below identify known deep
# listing endpoints from the source-map brief.
DIRECTORY_CAREER_URLS = {
    "Alpine": "https://www.alpineshire.vic.gov.au",
    "Ararat": "https://www.ararat.vic.gov.au",
    "Ballarat": "https://www.ballarat.vic.gov.au",
    "Banyule": "https://www.banyule.vic.gov.au",
    "Bass Coast": "https://www.basscoast.vic.gov.au",
    "Baw Baw": "https://www.bawbawshire.vic.gov.au",
    "Bayside": "https://www.bayside.vic.gov.au",
    "Benalla": "https://www.benalla.vic.gov.au",
    "Boroondara": "https://www.boroondara.vic.gov.au",
    "Brimbank": "https://www.brimbank.vic.gov.au",
    "Buloke": "https://www.buloke.vic.gov.au",
    "Campaspe": "https://www.campaspe.vic.gov.au/Our-council/Employment-tenders/Careers",
    "Cardinia": "https://careers.cardinia.vic.gov.au",
    "Casey": "https://www.casey.vic.gov.au",
    "Central Goldfields": "https://centralgoldfieldscareers.com.au/Vacancies/",
    "Colac Otway": "https://www.colacotway.vic.gov.au",
    "Corangamite": "https://www.corangamite.vic.gov.au",
    "Darebin": "https://www.darebin.vic.gov.au",
    "East Gippsland": "https://www.eastgippsland.vic.gov.au",
    "Frankston": "https://www.frankston.vic.gov.au",
    "Gannawarra": "https://www.gannawarra.vic.gov.au",
    "Glen Eira": "https://www.gleneira.vic.gov.au",
    "Glenelg": "https://www.glenelg.vic.gov.au",
    "Golden Plains": "https://www.goldenplains.vic.gov.au",
    "Greater Bendigo": "https://www.bendigo.vic.gov.au/about-us/working-city",
    "Greater Dandenong": "https://jobs.greaterdandenong.vic.gov.au",
    "Greater Geelong": "https://www.geelongaustralia.com.au",
    "Greater Shepparton": "https://greatershepparton.com.au",
    "Hepburn": "https://www.hepburn.vic.gov.au/Council/Work-for-Council/Job-vacancies",
    "Hindmarsh": "https://www.hindmarsh.vic.gov.au",
    "Hobsons Bay": "https://www.hobsonsbay.vic.gov.au",
    "Horsham": "https://hrcc.recruitmenthub.com.au",
    "Hume": "https://www.hume.vic.gov.au",
    "Indigo": "https://indigo.pulsesoftware.com/Pulse/jobs",
    "Kingston": "https://www.kingston.vic.gov.au",
    "Knox": "https://www.knox.vic.gov.au",
    "Latrobe": "https://www.latrobe.vic.gov.au",
    "Loddon": "https://www.loddon.vic.gov.au",
    "Macedon Ranges": "https://www.mrsc.vic.gov.au",
    "Manningham": "https://www.manningham.vic.gov.au",
    "Mansfield": "https://www.mansfield.vic.gov.au",
    "Maribyrnong": "https://maribyrnong.recruitmenthub.com.au",
    "Maroondah": "https://www.maroondah.vic.gov.au",
    "Melbourne": "https://www.melbourne.vic.gov.au",
    "Melton": "https://www.melton.vic.gov.au",
    "Merri-bek": "https://www.merri-bek.vic.gov.au",
    "Mildura": "https://www.mildura.vic.gov.au",
    "Mitchell": "https://www.mitchellshire.vic.gov.au",
    "Moira": "https://www.moira.vic.gov.au/Our-Council/Careers-with-us",
    "Monash": "https://www.monash.vic.gov.au",
    "Moonee Valley": "https://mvcc.vic.gov.au",
    "Moorabool": "https://www.moorabool.vic.gov.au",
    "Mornington Peninsula": "https://www.mornpen.vic.gov.au",
    "Mount Alexander": "https://www.mountalexander.vic.gov.au",
    "Moyne": "https://www.moyne.vic.gov.au",
    "Murrindindi": "https://www.murrindindi.vic.gov.au",
    "Nillumbik": "https://www.nillumbik.vic.gov.au",
    "Northern Grampians": "https://www.ngshire.vic.gov.au",
    "Port Phillip": "https://www.portphillip.vic.gov.au",
    "Pyrenees": "https://www.pyrenees.vic.gov.au",
    "Queenscliffe": "https://www.queenscliffe.vic.gov.au",
    "South Gippsland": "https://www.southgippsland.vic.gov.au/homepage/50/vacant_positions",
    "Southern Grampians": "https://www.sthgrampians.vic.gov.au",
    "Stonnington": "https://www.stonnington.vic.gov.au",
    "Strathbogie": "https://www.strathbogie.vic.gov.au",
    "Surf Coast": "https://www.surfcoast.vic.gov.au",
    "Swan Hill": "https://www.swanhill.vic.gov.au",
    "Towong": "https://www.towong.vic.gov.au",
    "Wangaratta": "https://www.wangaratta.vic.gov.au",
    "Warrnambool": "https://www.warrnambool.vic.gov.au",
    "Wellington": "https://www.wellington.vic.gov.au/council/careers-at-wellington",
    "West Wimmera": "https://www.westwimmera.vic.gov.au",
    "Whitehorse": "https://www.whitehorse.vic.gov.au",
    "Whittlesea": "https://www.whittlesea.vic.gov.au",
    "Wodonga": "https://selfservice.wodonga.vic.gov.au/Prod/jobs/",
    "Wyndham": "https://www.wyndham.vic.gov.au",
    "Yarra": "https://jobs.yarracity.vic.gov.au",
    "Yarra Ranges": "https://www.yarraranges.vic.gov.au",
    "Yarriambiack": "https://www.yarriambiack.vic.gov.au",
}

VERIFIED_ENDPOINTS = {
    "Alpine": {
        "platform_family": "native_council",
        "listing_url": "https://www.alpineshire.vic.gov.au/about-us/careers/current-vacancies",
        "detail_pattern": "/about-us/careers/current-vacancies/{slug}",
        "notes": "Native CMS listing with filters and child job pages.",
    },
    "Ararat": {
        "platform_family": "native_council",
        "listing_url": "https://www.ararat.vic.gov.au/careers",
        "detail_pattern": "/council/careers/{slug}",
        "notes": "Native careers page; some roles may be manual email/PDF applications.",
    },
    "Ballarat": {
        "platform_family": "pulse",
        "listing_url": "https://ballarat.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pulse public listing and JSON feed expose current City of Ballarat vacancies.",
    },
    "Bass Coast": {
        "platform_family": "t1cloud",
        "listing_url": "https://basscoast.t1cloud.com/T1Default/CiAnywhere/Web/BASSCOAST/Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_GUEST?suite=CES",
        "detail_pattern": "/T1Default/CiAnywhere/Web/BASSCOAST/OrganisationManagement/JobBoardEnquiry/{job_id}",
        "notes": "Official careers page hands current vacancies through to TechnologyOne/T1Cloud public job board.",
    },
    "Baw Baw": {
        "platform_family": "native_council",
        "listing_url": "https://www.bawbawshire.vic.gov.au/About-Council/Our-Organisation/Join-us-and-lets-grow-together",
        "detail_pattern": "/About-Council/Our-Organisation/Join-us-and-lets-grow-together/{slug}",
        "notes": "Official council careers hub links to current opportunities and ApplyNow application pages.",
    },
    "Bayside": {
        "platform_family": "native_council_custom",
        "listing_url": "https://careers.bayside.vic.gov.au/jobs/search",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council careers host with current job detail pages.",
    },
    "Banyule": {
        "platform_family": "pulse",
        "listing_url": "https://banyule.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pattern-resolved Pulse public listing and JSON feed.",
    },
    "Boroondara": {
        "platform_family": "successfactors",
        "listing_url": "https://www.boroondara.vic.gov.au/your-council/jobs-and-careers/view-current-job-vacancies",
        "detail_pattern": "/sfcareer/jobreqcareer?jobId={job_id}",
        "notes": "Official council vacancy page links to SuccessFactors job requisitions.",
    },
    "Brimbank": {
        "platform_family": "pulse",
        "listing_url": "https://brimbank.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pulse public ads are search-indexed and structured.",
    },
    "Benalla": {
        "platform_family": "native_council",
        "listing_url": "https://www.benalla.vic.gov.au/council/careers-at-council/positions-vacant/",
        "detail_pattern": "/job-listing/{slug}",
        "notes": "Official positions-vacant listing exposes current jobs and job-listing detail pages.",
    },
    "Buloke": {
        "platform_family": "native_council",
        "listing_url": "https://www.buloke.vic.gov.au/employment",
        "detail_pattern": "/employment/{slug}",
        "notes": "Official council employment endpoint.",
    },
    "Cardinia": {
        "platform_family": "adlogic_martianlogic",
        "listing_url": "https://careers.cardinia.vic.gov.au/our-jobs/",
        "detail_pattern": "/job-details/query/{title}/in/Australia/{job_id}/",
        "notes": "Cardinia public careers board exposes structured job detail pages.",
    },
    "Campaspe": {
        "platform_family": "t1cloud",
        "listing_url": "https://campaspe.t1cloud.com/T1Default/CiAnywhere/Web/CAMPASPE/Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES",
        "detail_pattern": "/T1Default/CiAnywhere/Web/CAMPASPE/OrganisationManagement/JobBoardEnquiry/{job_id}",
        "notes": "Official careers page hands current opportunities through to TechnologyOne/T1Cloud RECRUIT_EXT public job board.",
    },
    "Casey": {
        "platform_family": "native_council",
        "listing_url": "https://www.casey.vic.gov.au/careers/jobs",
        "detail_pattern": "/careers/jobs/{slug}",
        "notes": "Official council careers endpoint; may have zero vacancies on a given scrape.",
    },
    "Central Goldfields": {
        "platform_family": "recruitmenthub",
        "listing_url": "https://centralgoldfieldscareers.com.au/Vacancies/",
        "detail_pattern": "/Vacancies/{job_id}/title/{slug}",
        "apply_pattern": "/applyjob/{job_id}",
        "notes": "Official standalone council careers site exposes RecruitmentHub-style vacancy routes.",
    },
    "Colac Otway": {
        "platform_family": "applynow",
        "listing_url": "https://colac-otway-shire-council-ext.applynow.net.au/",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Official current opportunities page links through to the Colac Otway ApplyNow public vacancy portal.",
    },
    "Corangamite": {
        "platform_family": "native_council",
        "listing_url": "https://www.corangamite.vic.gov.au/Council/Working-for-council",
        "detail_pattern": "/Council/Working-for-council/{slug}",
        "notes": "Official working-for-council endpoint; the linked Career Opportunities child route may return 404 when no current vacancies are published.",
    },
    "Darebin": {
        "platform_family": "native_council",
        "listing_url": "https://www.darebin.vic.gov.au/jobs",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council current-vacancies endpoint.",
    },
    "East Gippsland": {
        "platform_family": "pulse",
        "listing_url": "https://eastgippsland.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pattern-resolved Pulse public listing and JSON feed.",
    },
    "Frankston": {
        "platform_family": "native_council_custom",
        "listing_url": "https://careers.frankston.vic.gov.au/jobs/search",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council careers host; scraper may observe zero rows when edge protection returns an empty challenge.",
    },
    "Glen Eira": {
        "platform_family": "native_council_custom",
        "listing_url": "https://careers.gleneira.vic.gov.au/jobs/search",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council careers host with current job detail pages.",
    },
    "Glenelg": {
        "platform_family": "dayforce",
        "listing_url": "https://jobs.dayforcehcm.com/en-AU/glenelgshire/GLENELGCANDIDATEPORTAL",
        "detail_pattern": "/en-AU/glenelgshire/GLENELGCANDIDATEPORTAL/jobs/{job_id}",
        "notes": "Official current vacancies page links through to the Glenelg Shire Dayforce candidate portal.",
    },
    "Golden Plains": {
        "platform_family": "native_council",
        "listing_url": "https://www.goldenplains.vic.gov.au/council/careers/vacancies",
        "detail_pattern": "/council/careers/vacancies/{slug}",
        "notes": "Official council vacancies endpoint.",
    },
    "Greater Dandenong": {
        "platform_family": "native_council_custom",
        "listing_url": "https://jobs.greaterdandenong.vic.gov.au/jobs",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Custom official council jobs site with dedicated detail pages.",
    },
    "Greater Bendigo": {
        "platform_family": "applynow",
        "listing_url": "https://city-of-bendigo.applynow.net.au",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Official Working at the City page embeds the City of Bendigo ApplyNow public vacancy portal.",
    },
    "Greater Geelong": {
        "platform_family": "pageup",
        "listing_url": "https://careers.pageuppeople.com/887/cw/en/listing/",
        "detail_pattern": "/cw/en/job/{job_id}/{slug}",
        "notes": "Observed PageUp detail pages expose job number, classification, PD and dates.",
    },
    "Greater Shepparton": {
        "platform_family": "native_council",
        "listing_url": "https://greatershepparton.com.au/council/employment",
        "detail_pattern": "/council/employment/{slug}",
        "notes": "Official council employment endpoint.",
    },
    "Gannawarra": {
        "platform_family": "native_council",
        "listing_url": "https://www.gannawarra.vic.gov.au/Invest-in-the-Gannawarra/Relocate-to-the-Gannawarra/Employment-opportunities",
        "detail_pattern": "/Invest-in-the-Gannawarra/Relocate-to-the-Gannawarra/Employment-opportunities/{slug}",
        "notes": "Official council employment opportunities endpoint.",
    },
    "Hepburn": {
        "platform_family": "t1cloud",
        "listing_url": "https://hepburn.t1cloud.com/T1Default/CiAnywhere/Web/HEPBURN/Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES",
        "detail_pattern": "/T1Default/CiAnywhere/Web/HEPBURN/OrganisationManagement/JobBoardEnquiry/{job_id}",
        "notes": "Official job vacancies page hands current opportunities through to TechnologyOne/T1Cloud RECRUIT_EXT public job board.",
    },
    "Hindmarsh": {
        "platform_family": "native_council",
        "listing_url": "https://www.hindmarsh.vic.gov.au/Council/Working-With-Us/Work-In-Council",
        "detail_pattern": "/Council/Working-With-Us/Work-In-Council/{slug}",
        "notes": "Official council Work In Council page with current result cards.",
    },
    "Hobsons Bay": {
        "platform_family": "bigredsky",
        "listing_url": "https://hobsonsbay.bigredsky.com/page.php?pageID=106",
        "detail_pattern": "/page.php?pageID=160&AdvertID={job_id}",
        "notes": "Official council vacancy page links through to BigRedSky public job board.",
    },
    "Horsham": {
        "platform_family": "recruitmenthub",
        "listing_url": "https://hrcc.recruitmenthub.com.au/Vacancies/",
        "detail_pattern": "/Vacancies/{job_id}/title/{slug}",
        "apply_pattern": "/title/applyjob/{job_id}",
        "notes": "RecruitmentHub vacancy, detail and apply routes.",
    },
    "Hume": {
        "platform_family": "smartrecruiters",
        "listing_url": "https://www.hume.vic.gov.au/Your-Council/Careers-at-Hume/Jobs-and-Opportunities",
        "detail_pattern": "/HumeCityCouncil/{job_id}-{slug}",
        "company_code": "HumeCityCouncil",
        "notes": "Official Jobs and Opportunities page embeds the HumeCityCouncil SmartRecruiters public job widget.",
    },
    "Indigo": {
        "platform_family": "pulse",
        "listing_url": "https://indigo.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pattern-resolved Pulse public listing and JSON feed.",
    },
    "Knox": {
        "platform_family": "pageup",
        "listing_url": "https://careers.pageuppeople.com/1000/cw/en/listing/",
        "detail_pattern": "/1000/cw/en/job/{job_id}/{slug}",
        "notes": "Observed PageUp listing and detail patterns.",
    },
    "Kingston": {
        "platform_family": "native_council_custom",
        "listing_url": "https://careers.kingston.vic.gov.au/jobs/search",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council careers host with current job detail pages.",
    },
    "Latrobe": {
        "platform_family": "pulse",
        "listing_url": "https://latrobe.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Official council careers page links through to Pulse vacancies.",
    },
    "Loddon": {
        "platform_family": "pulse",
        "listing_url": "https://loddon.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Pattern-resolved Pulse public listing and JSON feed.",
    },
    "Macedon Ranges": {
        "platform_family": "applynow",
        "listing_url": "https://macedon-ranges-ext-shire-portal.applynow.net.au/",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Observed ApplyNow job-specific pages.",
    },
    "Manningham": {
        "platform_family": "applynow",
        "listing_url": "https://manningham.applynow.net.au/",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Observed ApplyNow job pages with job number, status and closing date.",
    },
    "Maribyrnong": {
        "platform_family": "recruitmenthub",
        "listing_url": "https://maribyrnong.recruitmenthub.com.au/Vacancies/",
        "detail_pattern": "/Vacancies/{job_id}/title/{slug}",
        "apply_pattern": "/applyjob/{job_id}",
        "notes": "RecruitmentHub public vacancy, detail and apply route family.",
    },
    "Mansfield": {
        "platform_family": "native_council",
        "listing_url": "https://www.mansfield.vic.gov.au/Council/Work-With-Us/Career-Job-Opportunities",
        "detail_pattern": "/Council/Work-With-Us/Career-Job-Opportunities/{slug}",
        "notes": "Official council career and job opportunities endpoint.",
    },
    "Melton": {
        "platform_family": "applynow",
        "listing_url": "https://meltoncity-external.applynow.net.au/",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "ApplyNow vacancies and job-specific application pages.",
    },
    "Mitchell": {
        "platform_family": "native_council_custom",
        "listing_url": "https://careers.mitchellshire.vic.gov.au/jobs/search",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council careers host with current job detail pages.",
    },
    "Merri-bek": {
        "platform_family": "native_council",
        "listing_url": "https://www.merri-bek.vic.gov.au/jobs",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Official council jobs page links to current ApplyNow detail pages.",
    },
    "Maroondah": {
        "platform_family": "native_council",
        "listing_url": "https://www.maroondah.vic.gov.au/About-Council/CareersMaroondah",
        "detail_pattern": "/About-Council/CareersMaroondah/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Melbourne": {
        "platform_family": "aurion_selfservice",
        "listing_url": "https://candidate.aurion.cloud/mcc/production/",
        "detail_pattern": "/vacancies/{job_id}/edit",
        "notes": "Official City of Melbourne work-with-us page links to Aurion candidate vacancies.",
    },
    "Mildura": {
        "platform_family": "native_council",
        "listing_url": "https://www.mildura.vic.gov.au/Council/Careers/Current-Job-Vacancies",
        "detail_pattern": "/Jobs-Listing/{slug}",
        "notes": "Official OpenCities current job vacancies page with /Jobs-Listing vacancy cards.",
    },
    "Moira": {
        "platform_family": "elmo_talent",
        "listing_url": "https://moira.elmotalent.com.au/careers/Moira/jobs?layout=full",
        "detail_pattern": "/careers/Moira/job/view/{job_id}",
        "portal_code": "Moira",
        "notes": "Official careers-with-us page links through to the Moira ELMO Talent vacancy portal.",
    },
    "Moonee Valley": {
        "platform_family": "native_council",
        "listing_url": "https://mvcc.vic.gov.au/jobs",
        "detail_pattern": "/jobs/{slug}",
        "notes": "Official council jobs endpoint.",
    },
    "Monash": {
        "platform_family": "pageup",
        "listing_url": "https://careers.pageuppeople.com/904/cw/en/listing/",
        "detail_pattern": "/904/cw/en/job/{job_id}/{slug}",
        "notes": "Observed PageUp listing pattern.",
    },
    "Moorabool": {
        "platform_family": "elmo_talent",
        "listing_url": "https://www.moorabool.vic.gov.au/About-Council/Careers/Vacancies",
        "embed_url": "https://moorabool.elmotalent.com.au/careers/msc/jobs",
        "detail_pattern": "/careers/msc/job/view/{job_id}",
        "portal_code": "msc",
        "notes": "Official vacancies page embeds the Moorabool ELMO Talent careers portal.",
    },
    "Mornington Peninsula": {
        "platform_family": "native_council",
        "listing_url": "https://www.mornpen.vic.gov.au/About-Us/Careers-Volunteering/Current-Vacancies",
        "detail_pattern": "/About-Us/Careers-Volunteering/Current-Vacancies/{slug}",
        "notes": "Official council current vacancies endpoint.",
    },
    "Mount Alexander": {
        "platform_family": "native_council",
        "listing_url": "https://www.mountalexander.vic.gov.au/Council/Work-with-us/Current-vacancies",
        "detail_pattern": "/Council/Work-with-us/Current-vacancies/{slug}",
        "notes": "Official council current vacancies endpoint.",
    },
    "Moyne": {
        "platform_family": "native_council",
        "listing_url": "https://www.moyne.vic.gov.au/Employment",
        "detail_pattern": "/Employment/{slug}",
        "notes": "Official council employment endpoint.",
    },
    "Murrindindi": {
        "platform_family": "native_council",
        "listing_url": "https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions",
        "detail_pattern": "/Council/Jobs-and-Tenders/Vacant-Positions/{slug}",
        "notes": "Official OpenCities vacant positions page with job cards and detail pages.",
    },
    "Nillumbik": {
        "platform_family": "recruitmenthub",
        "listing_url": "https://nillumbikshirecouncil.recruitmenthub.com.au/about/Current-vacancies/",
        "detail_pattern": "/Current-vacancies/{job_id}/title/{slug}",
        "notes": "Observed RecruitmentHub-style current-vacancies route family.",
    },
    "Northern Grampians": {
        "platform_family": "native_council",
        "listing_url": "https://www.ngshire.vic.gov.au/Careers",
        "detail_pattern": "/Careers/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Port Phillip": {
        "platform_family": "native_council",
        "listing_url": "https://www.portphillip.vic.gov.au/about-the-council/careers-at-the-city-of-port-phillip/",
        "detail_pattern": "/about-the-council/careers-at-the-city-of-port-phillip/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Pyrenees": {
        "platform_family": "native_council",
        "listing_url": "https://www.pyrenees.vic.gov.au/About-Pyrenees-Shire-Council/Work-For-Pyrenees-Shire-Council/Employment-Opportunities-with-Pyrenees-Shire-Council",
        "detail_pattern": "/About-Pyrenees-Shire-Council/Work-For-Pyrenees-Shire-Council/Employment-Opportunities-with-Pyrenees-Shire-Council/{slug}",
        "notes": "Official council employment opportunities endpoint.",
    },
    "Queenscliffe": {
        "platform_family": "native_council",
        "listing_url": "https://www.queenscliffe.vic.gov.au/Your-Council/Career-opportunities",
        "detail_pattern": "/Your-Council/Career-opportunities/{slug}",
        "notes": "Official Borough career opportunities endpoint.",
    },
    "South Gippsland": {
        "platform_family": "applynow",
        "listing_url": "https://southgippsland.applynow.net.au/",
        "detail_pattern": "/jobs/{job_no}-{slug}",
        "notes": "Official vacant positions page embeds the South Gippsland ApplyNow public vacancy portal.",
    },
    "Southern Grampians": {
        "platform_family": "native_council",
        "listing_url": "https://www.sthgrampians.vic.gov.au/Careers",
        "detail_pattern": "/Careers/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Stonnington": {
        "platform_family": "elmo_talent",
        "listing_url": "https://cos.elmotalent.com.au/careers/cosjobs/jobs",
        "detail_pattern": "/careers/cosjobs/job/view/{job_id}",
        "portal_code": "cosjobs",
        "notes": "Official Stonnington ELMO Talent careers portal.",
    },
    "Strathbogie": {
        "platform_family": "native_council",
        "listing_url": "https://www.strathbogie.vic.gov.au/council/our-council/careers-at-council/",
        "detail_pattern": "/council/our-council/careers-at-council/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Surf Coast": {
        "platform_family": "elmo_talent",
        "listing_url": "https://surfcoast.elmotalent.com.au/careers/surfcoast/jobs?layout=iframe",
        "detail_pattern": "/careers/surfcoast/job/view/{job_id}",
        "portal_code": "surfcoast",
        "notes": "Official employment page embeds the Surf Coast ELMO Talent vacancy portal.",
    },
    "Swan Hill": {
        "platform_family": "pulse",
        "listing_url": "https://swanhill.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Official careers page links through to the Swan Hill Pulse public vacancy portal.",
    },
    "Towong": {
        "platform_family": "employmenthero",
        "listing_url": "https://employmenthero.com/jobs/organisations/towongshirecouncil/",
        "detail_pattern": "/jobs/position/{slug}",
        "notes": "Official council careers page links through to Employment Hero job details.",
    },
    "Wangaratta": {
        "platform_family": "aurion_selfservice",
        "listing_url": "https://candidate.aurion.cloud/wangaratta/production/",
        "detail_pattern": "/vacancies/{job_id}/edit",
        "notes": "Official council careers page links to Aurion candidate vacancies.",
    },
    "Warrnambool": {
        "platform_family": "native_council",
        "listing_url": "https://www.warrnambool.vic.gov.au/careers",
        "detail_pattern": "/careers/{slug}",
        "notes": "Official council careers endpoint with native job detail pages.",
    },
    "Wellington": {
        "platform_family": "pulse",
        "listing_url": "https://wellingtonvic.pulsesoftware.com/Pulse/jobs",
        "detail_pattern": "/Pulse/job/{short_id}/{slug}?source=public",
        "notes": "Official Careers at Wellington page embeds the Wellington Pulse public vacancy portal.",
    },
    "West Wimmera": {
        "platform_family": "native_council",
        "listing_url": "https://www.westwimmera.vic.gov.au/Council/Employment",
        "detail_pattern": "/Council/Employment/{slug}",
        "notes": "Official council employment endpoint.",
    },
    "Whitehorse": {
        "platform_family": "oracle_hcm",
        "listing_url": "https://fa-evei-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs",
        "detail_pattern": "/hcmUI/CandidateExperience/en/sites/CX_1001/job/{job_id}",
        "site_number": "CX_1001",
        "notes": "Official council job opportunities page links to Oracle HCM Candidate Experience.",
    },
    "Whittlesea": {
        "platform_family": "bigredsky",
        "listing_url": "https://whittlesea.bigredsky.com/page.php?pageID=106",
        "detail_pattern": "/page.php?pageID=160&AdvertID={job_id}",
        "notes": "Official council jobs page links through to BigRedSky public job board.",
    },
    "Wodonga": {
        "platform_family": "aurion_selfservice",
        "listing_url": "https://selfservice.wodonga.vic.gov.au/Prod/jobs/",
        "detail_pattern": "/Prod/jobs/vacancies/{job_id}/edit",
        "notes": "Official council careers page links to Aurion self-service vacancies.",
    },
    "Wyndham": {
        "platform_family": "native_council",
        "listing_url": "https://www.wyndham.vic.gov.au/careers",
        "detail_pattern": "/careers/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Yarra": {
        "platform_family": "pageup",
        "listing_url": "https://careers.pageuppeople.com/817/cw/en/listing/",
        "detail_pattern": "/817/cw/en/job/{job_id}/{slug}",
        "notes": "PageUp public listing with applicant login and job alerts.",
    },
    "Yarra Ranges": {
        "platform_family": "native_council",
        "listing_url": "https://www.yarraranges.vic.gov.au/Our-Council/Careers-at-Yarra-Ranges",
        "detail_pattern": "/Our-Council/Careers-at-Yarra-Ranges/{slug}",
        "notes": "Official council careers endpoint.",
    },
    "Yarriambiack": {
        "platform_family": "native_council",
        "listing_url": "https://www.yarriambiack.vic.gov.au/Engage-With-Us/Jobs",
        "detail_pattern": "/Engage-With-Us/Jobs/{slug}",
        "notes": "Official council jobs endpoint.",
    },
}

SECONDARY_SOURCES = [
    {
        "source_id": "viccouncils_directory",
        "source_name": "Vic Councils council jobs directory",
        "source_family": "viccouncils",
        "url": VIC_COUNCILS_JOBS_DIRECTORY_URL,
        "source_priority": SOURCE_PRIORITY["sector_directory"],
        "best_use": "official council source registry and link validation",
        "monitoring_role": "seed_registry",
    },
    {
        "source_id": "careers_at_council_victoria",
        "source_name": "Careers at Council Victoria",
        "source_family": "careersatcouncil",
        "url": "https://www.careersatcouncil.com.au/victoria/",
        "source_priority": SOURCE_PRIORITY["sector_aggregator"],
        "best_use": "discovery, cross-checking and alert backstop",
        "monitoring_role": "secondary_signal",
    },
    {
        "source_id": "local_government_jobs_australia",
        "source_name": "Local Government Jobs Australia",
        "source_family": "localgovernmentjobs",
        "url": "https://www.localgovernmentjobs.com.au",
        "source_priority": SOURCE_PRIORITY["sector_aggregator"],
        "best_use": "discovery and missing-role detection",
        "monitoring_role": "secondary_signal",
    },
    {
        "source_id": "jora_victorian_council_search",
        "source_name": "Jora Victorian council search",
        "source_family": "jora",
        "url": "https://au.jora.com/Council-jobs-in-Victoria",
        "source_priority": SOURCE_PRIORITY["sector_aggregator"],
        "best_use": "broad public discovery backstop, cross-checking and missing-role detection",
        "monitoring_role": "secondary_signal",
    },
    {
        "source_id": "council_direct",
        "source_name": "Council Direct",
        "source_family": "councildirect",
        "url": "https://www.councildirect.com.au/jobs",
        "source_priority": SOURCE_PRIORITY["sector_aggregator"],
        "best_use": "sector-specific discovery and missing-role detection",
        "monitoring_role": "secondary_signal",
    },
]

RESTRICTED_BROAD_BOARD_SOURCES = [
    {
        "source_id": "seek",
        "source_name": "SEEK",
        "source_family": "seek",
        "source_priority": SOURCE_PRIORITY["broad_job_board"],
        "access_policy": "restricted_do_not_crawl_without_permission",
        "best_use": "manual discovery, QA or licensed partner integration",
    },
    {
        "source_id": "indeed",
        "source_name": "Indeed",
        "source_family": "indeed",
        "source_priority": SOURCE_PRIORITY["broad_job_board"],
        "access_policy": "restricted_do_not_crawl_without_permission",
        "best_use": "manual discovery, QA or approved partner integration",
    },
    {
        "source_id": "linkedin",
        "source_name": "LinkedIn",
        "source_family": "linkedin",
        "source_priority": SOURCE_PRIORITY["broad_job_board"],
        "access_policy": "restricted_do_not_crawl_without_permission",
        "best_use": "manual discovery, QA or approved partner integration",
    },
]

TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "session",
    "sessionid",
    "source",
}


def canonicalize_job_url(url: str) -> str:
    """Normalise a job URL for high-confidence URL-level dedupe."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))


def council_job_source_registry_payload(council_master: dict[str, Any] | None = None) -> dict[str, Any]:
    master = council_master or load_council_master()
    rows = [_council_source_row(row) for row in master.get("rows", [])]
    rows = sorted(rows, key=lambda row: (row["poll_tier"], row["council_name"]))
    platform_counts = Counter(row["platform_family"] for row in rows)
    tier_counts = Counter(row["poll_tier"] for row in rows)
    grouping_counts = Counter(row["council_grouping"] for row in rows)
    ready_count = sum(1 for row in rows if row["monitoring_status"] == "ready")
    return {
        "set_id": "victorian_council_jobs_source_registry",
        "label": "Victorian Council Jobs Source Registry",
        "description": (
            "URL-first monitoring registry for Victorian local-government job sources, "
            "seeded from the Vic Councils directory and structured for official-source polling."
        ),
        "source_map_captured_date": SOURCE_MAP_CAPTURED_DATE,
        "sources": {
            "viccouncils_directory": {
                "url": VIC_COUNCILS_JOBS_DIRECTORY_URL,
                "role": "statewide official career-link registry",
            },
            "council_master": {
                "set_id": master.get("set_id"),
                "label": master.get("label"),
            },
        },
        "summary": {
            "councils": len(rows),
            "ready_sources": ready_count,
            "needs_endpoint_discovery": len(rows) - ready_count,
            "platform_families": dict(sorted(platform_counts.items())),
            "poll_tiers": dict(sorted(tier_counts.items())),
            "council_groupings": dict(sorted(grouping_counts.items())),
            "endpoint_candidates": sum(len(row.get("endpoint_candidates") or []) for row in rows),
            "secondary_sources": len(SECONDARY_SOURCES),
            "restricted_sources": len(RESTRICTED_BROAD_BOARD_SOURCES),
        },
        "polling_policy": {
            "tier_cadence": POLL_CADENCE_BY_TIER,
            "tier_cadence_labels": POLL_CADENCE_LABELS,
            "tier_explainer": POLL_TIER_EXPLAINER,
            "default_headers": {
                "user_agent_policy": "identify_contact_and_purpose",
            },
            "retry_policy": "exponential_backoff_for_transient_failures_no_retry_loop_on_401_403",
            "robots_policy": "check_and_store_per_source_before_production_activation",
        },
        "dedupe_policy": {
            "canonical_preference": [
                "official council domain job URL",
                "official ATS subdomain linked by council",
                "sector directory or aggregator",
                "broad job board only with permission",
            ],
            "high_confidence_keys": [
                "canonical_url",
                "source_job_id",
                "job_number",
                "title+council+location+closing_at",
                "description_fingerprint_hash",
            ],
            "tracking_query_params_removed": sorted(TRACKING_QUERY_PARAMS | {"utm_*"}),
        },
        "rows": rows,
        "secondary_sources": SECONDARY_SOURCES,
        "restricted_sources": RESTRICTED_BROAD_BOARD_SOURCES,
    }


def _council_source_row(master_row: dict[str, Any]) -> dict[str, Any]:
    short_name = str(master_row.get("short_name") or "").strip()
    council_name = str(master_row.get("long_name") or master_row.get("council_name") or short_name).strip()
    grouping = COUNCIL_GROUPING_SLUGS.get(str(master_row.get("council_category") or "").strip(), "unknown")
    poll_tier = POLL_TIER_BY_GROUPING.get(grouping, "C")
    entry_url = DIRECTORY_CAREER_URLS.get(short_name)
    overlay = VERIFIED_ENDPOINTS.get(short_name, {})
    platform_family = overlay.get("platform_family") or _platform_family_from_url(entry_url)
    listing_url = overlay.get("listing_url") or entry_url
    monitoring_status = "ready" if short_name in VERIFIED_ENDPOINTS else "needs_endpoint_discovery"
    endpoint_candidates = [] if monitoring_status == "ready" else endpoint_discovery_candidates(
        short_name,
        council_name=council_name,
        entry_url=entry_url,
    )
    return {
        "council_key": master_row.get("council_key"),
        "short_name": short_name,
        "council_name": council_name,
        "council_grouping": grouping,
        "poll_tier": poll_tier,
        "suggested_cadence": POLL_CADENCE_BY_TIER[poll_tier],
        "suggested_cadence_label": POLL_CADENCE_LABELS[poll_tier],
        "official_careers_entry_url": entry_url,
        "listing_url": listing_url,
        "listing_url_confidence": "verified_deep_endpoint" if monitoring_status == "ready" else "directory_entry",
        "platform_family": platform_family,
        "adapter": ADAPTER_BY_PLATFORM.get(platform_family, "NativeCouncilFetcher"),
        "source_priority": SOURCE_PRIORITY["official_council_or_ats"],
        "monitoring_status": monitoring_status,
        "detail_pattern": overlay.get("detail_pattern"),
        "apply_pattern": overlay.get("apply_pattern"),
        "company_code": overlay.get("company_code"),
        "embed_url": overlay.get("embed_url"),
        "portal_code": overlay.get("portal_code"),
        "endpoint_candidates": endpoint_candidates,
        "robots_status": "not_checked",
        "terms_review_status": "not_checked",
        "notes": overlay.get("notes") or "Official Vic Councils directory career link; deep vacancy endpoint pending.",
    }


def endpoint_discovery_candidates(
    short_name: str,
    *,
    council_name: str | None = None,
    entry_url: str | None = None,
) -> list[dict[str, Any]]:
    variants = _candidate_endpoint_variants(short_name, council_name=council_name, entry_url=entry_url)
    compact_slugs = variants["compact"]
    hyphen_slugs = variants["hyphen"]
    hosts = variants["hosts"]
    first_compact = compact_slugs[0] if compact_slugs else ""
    first_hyphen = hyphen_slugs[0] if hyphen_slugs else first_compact
    candidates: list[dict[str, Any]] = []
    for slug in compact_slugs[:2]:
        _add_endpoint_candidate(
            candidates,
            "pulse_subdomain",
            "pulse",
            f"https://{slug}.pulsesoftware.com/Pulse/jobs",
            "/Pulse/job/{short_id}/{slug}?source=public",
            "Vendor subdomain from council name.",
        )
        _add_endpoint_candidate(
            candidates,
            "recruitmenthub_vacancies",
            "recruitmenthub",
            f"https://{slug}.recruitmenthub.com.au/Vacancies/",
            "/Vacancies/{job_id}/title/{slug}",
            "RecruitmentHub tenant plus Vacancies route.",
        )
        _add_endpoint_candidate(
            candidates,
            "recruitmenthub_current_vacancies",
            "recruitmenthub",
            f"https://{slug}.recruitmenthub.com.au/Current-vacancies/",
            "/Current-vacancies/{job_id}/title/{slug}",
            "RecruitmentHub tenant plus Current-vacancies route.",
        )
        for suffix in ("shirecouncil", "citycouncil"):
            _add_endpoint_candidate(
                candidates,
                f"recruitmenthub_{suffix}",
                "recruitmenthub",
                f"https://{slug}{suffix}.recruitmenthub.com.au/about/Current-vacancies/",
                "/Current-vacancies/{job_id}/title/{slug}",
                "RecruitmentHub council-name tenant plus Current-vacancies route.",
            )
        _add_endpoint_candidate(
            candidates,
            "aurion_candidate_portal",
            "aurion_selfservice",
            f"https://candidate.aurion.cloud/{slug}/production/",
            "/vacancies/{job_id}/edit",
            "Aurion candidate portal tenant from council name.",
        )
        _add_endpoint_candidate(
            candidates,
            "bigredsky_page",
            "bigredsky",
            f"https://{slug}.bigredsky.com/page.php?pageID=106",
            "/page.php?pageID=160&AdvertID={job_id}",
            "BigRedSky tenant plus View All Jobs page.",
        )
    for company_code in _smartrecruiters_company_codes(short_name, council_name):
        _add_endpoint_candidate(
            candidates,
            "smartrecruiters_company_api",
            "smartrecruiters",
            f"https://api.smartrecruiters.com/v1/companies/{company_code}/postings?limit=100&offset=0",
            f"/{company_code}/{{job_id}}-{{slug}}",
            "SmartRecruiters company postings API from council name.",
        )
    for portal_code in _elmo_portal_codes(short_name, council_name):
        _add_endpoint_candidate(
            candidates,
            "elmo_talent_portal",
            "elmo_talent",
            f"https://{first_compact}.elmotalent.com.au/careers/{portal_code}/jobs",
            f"/careers/{portal_code}/job/view/{{job_id}}",
            "ELMO Talent career portal from council name and council initials.",
        )
    for slug in compact_slugs[:2]:
        _add_endpoint_candidate(
            candidates,
            "applynow_tenant",
            "applynow",
            f"https://{slug}.applynow.net.au/",
            "/jobs/{job_no}-{slug}",
            "ApplyNow tenant from council name.",
        )
        for suffix in ("external", "vacancies"):
            _add_endpoint_candidate(
                candidates,
                f"applynow_{suffix}",
                "applynow",
                f"https://{slug}-{suffix}.applynow.net.au/",
                "/jobs/{job_no}-{slug}",
                "ApplyNow tenant with common council suffix.",
            )
        for suffix in ("city-external", "city-vacancies"):
            _add_endpoint_candidate(
                candidates,
                f"applynow_{suffix}",
                "applynow",
                f"https://{slug}{suffix}.applynow.net.au/",
                "/jobs/{job_no}-{slug}",
                "ApplyNow tenant with compact council-city suffix.",
            )
    for slug in hyphen_slugs[:2]:
        _add_endpoint_candidate(
            candidates,
            "applynow_city_of_hyphen",
            "applynow",
            f"https://city-of-{slug}.applynow.net.au/",
            "/jobs/{job_no}-{slug}",
            "ApplyNow tenant using common City of council-name form.",
        )
        for suffix in ("external", "vacancies", "ext-shire-portal", "shire-portal"):
            _add_endpoint_candidate(
                candidates,
                f"applynow_hyphen_{suffix}",
                "applynow",
                f"https://{slug}-{suffix}.applynow.net.au/",
                "/jobs/{job_no}-{slug}",
                "ApplyNow hyphenated council tenant with common suffix.",
            )
        _add_endpoint_candidate(
            candidates,
            "adlogic_jobboard_v3",
            "adlogic_martianlogic",
            f"https://jobboards.adlogic.com.au/{slug}-v3/our-jobs/",
            "/job-details/query/{title}/in/Australia/{job_id}/",
            "Adlogic/Martian Logic jobboard tenant pattern.",
        )
    if first_compact:
        _add_endpoint_candidate(
            candidates,
            "applynow_compact_ext_shire_portal",
            "applynow",
            f"https://{first_compact}-ext-shire-portal.applynow.net.au/",
            "/jobs/{job_no}-{slug}",
            "ApplyNow compact council tenant with shire portal suffix.",
        )
    if first_hyphen and "ranges" in first_hyphen:
        _add_endpoint_candidate(
            candidates,
            "applynow_ranges_ext_shire_portal",
            "applynow",
            f"https://{first_hyphen}-ext-shire-portal.applynow.net.au/",
            "/jobs/{job_no}-{slug}",
            "ApplyNow ranges shire portal suffix.",
        )
    for host in hosts[:2]:
        host_stem = host.split(".", 1)[0]
        _add_endpoint_candidate(
            candidates,
            "t1cloud_public_ext_function",
            "t1cloud",
            f"https://{host_stem}.t1cloud.com/T1Default/CiAnywhere/Web/{host_stem.upper()}/Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES",
            f"/T1Default/CiAnywhere/Web/{host_stem.upper()}/OrganisationManagement/JobBoardEnquiry/{{job_id}}",
            "TechnologyOne/T1Cloud public external recruitment function.",
        )
        _add_endpoint_candidate(
            candidates,
            "t1cloud_public_function",
            "t1cloud",
            f"https://{host_stem}.t1cloud.com/T1Default/CiAnywhere/Web/{host_stem.upper()}/Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_GUEST?suite=CES",
            f"/T1Default/CiAnywhere/Web/{host_stem.upper()}/OrganisationManagement/JobBoardEnquiry/{{job_id}}",
            "TechnologyOne/T1Cloud public recruitment function.",
        )
        _add_endpoint_candidate(
            candidates,
            "pageup_careers_host_cw",
            "pageup",
            f"https://careers.{host}/cw/en/listing/",
            "/cw/en/job/{job_id}/{slug}",
            "PageUp careers host on official council domain.",
        )
        _add_endpoint_candidate(
            candidates,
            "pageup_jobs_host_cw",
            "pageup",
            f"https://jobs.{host}/cw/en/listing/",
            "/cw/en/job/{job_id}/{slug}",
            "PageUp jobs host on official council domain.",
        )
        _add_endpoint_candidate(
            candidates,
            "adlogic_careers_host",
            "adlogic_martianlogic",
            f"https://careers.{host}/our-jobs/",
            "/job-details/query/{title}/in/Australia/{job_id}/",
            "Adlogic/Martian Logic careers host on official council domain.",
        )
        for path in (
            "/careers",
            "/jobs",
            "/current-vacancies",
            "/about-us/careers/current-vacancies",
            "/our-council/jobs-and-careers",
        ):
            _add_endpoint_candidate(
                candidates,
                "native_career_path",
                "native_council",
                f"https://www.{host}{path}",
                f"{path.rstrip('/')}" + "/{slug}",
                "Native council domain plus common careers path.",
            )
    return candidates


def _add_endpoint_candidate(
    candidates: list[dict[str, Any]],
    pattern_id: str,
    platform_family: str,
    listing_url: str,
    detail_pattern: str,
    notes: str,
) -> None:
    canonical_url = canonicalize_job_url(listing_url)
    if not canonical_url or any(item["listing_url"] == canonical_url for item in candidates):
        return
    candidates.append({
        "pattern_id": pattern_id,
        "platform_family": platform_family,
        "listing_url": canonical_url,
        "detail_pattern": detail_pattern,
        "confidence": "pattern_probe",
        "probe_priority": _endpoint_probe_priority(pattern_id, platform_family),
        "notes": notes,
    })


def _endpoint_probe_priority(pattern_id: str, platform_family: str) -> int:
    if platform_family in {"aurion_selfservice", "bigredsky"}:
        return 1
    if platform_family in {"pulse", "recruitmenthub"}:
        return 1
    if platform_family == "applynow":
        return 2
    if platform_family == "t1cloud":
        return 3
    if platform_family in {"pageup", "adlogic_martianlogic"}:
        return 3
    if platform_family == "smartrecruiters":
        return 3
    if platform_family == "elmo_talent":
        return 3
    if pattern_id == "native_career_path":
        return 4
    return 9


def _smartrecruiters_company_codes(short_name: str, council_name: str | None = None) -> list[str]:
    values: list[str] = []
    for raw in (council_name, short_name, f"{short_name} Council"):
        words = re.findall(r"[A-Za-z0-9]+", str(raw or ""))
        if not words:
            continue
        code = "".join(word[:1].upper() + word[1:] for word in words)
        if code not in values:
            values.append(code)
    return values


def _elmo_portal_codes(short_name: str, council_name: str | None = None) -> list[str]:
    values: list[str] = []
    for raw in (council_name, short_name):
        words = re.findall(r"[A-Za-z0-9]+", str(raw or "").lower())
        if not words:
            continue
        initials = "".join(word[0] for word in words)
        compact = "".join(words)
        for value in (initials, compact):
            if len(value) >= 2 and value not in values:
                values.append(value)
    return values


def _candidate_endpoint_variants(
    short_name: str,
    *,
    council_name: str | None = None,
    entry_url: str | None = None,
) -> dict[str, list[str]]:
    names = [short_name, council_name]
    clean_names: list[str] = []
    for name in names:
        raw = str(name or "").lower()
        if not raw:
            continue
        clean_names.append(raw)
        clean_names.append(re.sub(r"\b(city|shire|rural|borough|council|greater)\b", " ", raw))
    compact = _unique_slug_values(re.sub(r"[^a-z0-9]+", "", name) for name in clean_names)
    hyphen = _unique_slug_values(re.sub(r"[^a-z0-9]+", "-", name).strip("-") for name in clean_names)
    parsed = urlsplit(str(entry_url or ""))
    host = parsed.netloc.lower()
    host_variants = []
    host_stem_variants = []
    if host:
        host_full = host.removeprefix("www.")
        host_variants.append(host_full)
        host_stem = host_full
        for suffix in (".vic.gov.au", ".com.au", ".com"):
            if host_stem.endswith(suffix):
                host_stem_variants.append(host_stem.removesuffix(suffix))
    compact = _unique_slug_values([*compact, *(re.sub(r"[^a-z0-9]+", "", value) for value in host_stem_variants)])
    hyphen = _unique_slug_values([*hyphen, *(re.sub(r"[^a-z0-9]+", "-", value).strip("-") for value in host_stem_variants)])
    hosts = _unique_slug_values(host_variants)
    return {
        "compact": compact,
        "hyphen": hyphen,
        "hosts": hosts,
    }


def _unique_slug_values(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        slug = str(value or "").strip(".-")
        if len(slug) < 3 or slug in seen:
            continue
        seen.add(slug)
        result.append(slug)
    return result


def _platform_family_from_url(url: str | None) -> str:
    parsed = urlsplit(str(url or ""))
    host = parsed.netloc.lower()
    if "applynow.net.au" in host:
        return "applynow"
    if "candidate.aurion.cloud" in host or "selfservice" in host:
        return "aurion_selfservice"
    if "bigredsky.com" in host:
        return "bigredsky"
    if "dayforcehcm.com" in host:
        return "dayforce"
    if "oraclecloud.com" in host:
        return "oracle_hcm"
    if "recruitmenthub.com.au" in host:
        return "recruitmenthub"
    if "pulsesoftware.com" in host:
        return "pulse"
    if "t1cloud.com" in host:
        return "t1cloud"
    if "pageuppeople.com" in host or "yarracity.vic.gov.au" in host:
        return "pageup"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "elmotalent.com.au" in host:
        return "elmo_talent"
    if host.startswith("jobs.") or "careers" in host:
        return "native_council_custom"
    if host:
        return "unknown_official"
    return "unknown_official"
