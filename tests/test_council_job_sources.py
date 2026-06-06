import json

from benchmarking_data_factory.reference.council_jobs import (
    canonicalize_job_url,
    council_job_source_registry_payload,
    endpoint_discovery_candidates,
)
from benchmarking_data_factory.workbench.job_intake import (
    accumulate_checked_jobs_from_payload,
    accumulate_checked_jobs_from_snapshot,
    enrich_job_from_detail_page,
    extract_attachment_links_from_html,
    extract_job_summaries_from_listing,
    _extract_secondary_jobs,
    job_pipeline_stage1_payload,
    job_intake_secondary_preview,
    job_intake_scrape_preview,
    load_checked_job_accumulator,
    load_job_intake_snapshot,
    save_job_intake_snapshot,
    _council_direct_council_page_sources,
    _jora_council_search_sources,
    _local_government_jobs_council_search_sources,
)
from benchmarking_data_factory.workbench.job_schema import (
    enrich_job_with_pay_rows,
    extract_salary_range,
    extract_salary_text,
    normalize_council_job_record,
)


def test_council_job_source_registry_covers_all_victorian_councils():
    payload = council_job_source_registry_payload()

    assert payload["set_id"] == "victorian_council_jobs_source_registry"
    assert payload["summary"]["councils"] == 79
    assert len(payload["rows"]) == 79
    assert len({row["short_name"] for row in payload["rows"]}) == 79
    assert payload["summary"]["poll_tiers"] == {"A": 41, "B": 19, "C": 19}


def test_council_job_source_registry_marks_verified_official_sources():
    rows = {row["short_name"]: row for row in council_job_source_registry_payload()["rows"]}

    assert all(row["monitoring_status"] == "ready" for row in rows.values())

    assert rows["Greater Dandenong"]["listing_url"] == "https://jobs.greaterdandenong.vic.gov.au/jobs"
    assert rows["Greater Dandenong"]["platform_family"] == "native_council_custom"
    assert rows["Greater Dandenong"]["monitoring_status"] == "ready"

    assert rows["Brimbank"]["platform_family"] == "pulse"
    assert rows["Brimbank"]["adapter"] == "PulseFetcher"
    assert rows["Brimbank"]["poll_tier"] == "A"

    assert rows["Ballarat"]["platform_family"] == "pulse"
    assert rows["Ballarat"]["listing_url"] == "https://ballarat.pulsesoftware.com/Pulse/jobs"
    assert rows["Ballarat"]["monitoring_status"] == "ready"

    assert rows["Greater Bendigo"]["platform_family"] == "applynow"
    assert rows["Greater Bendigo"]["listing_url"] == "https://city-of-bendigo.applynow.net.au"

    assert rows["Campaspe"]["platform_family"] == "t1cloud"
    assert rows["Campaspe"]["listing_url"] == (
        "https://campaspe.t1cloud.com/T1Default/CiAnywhere/Web/CAMPASPE/"
        "Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES"
    )

    assert rows["Central Goldfields"]["platform_family"] == "recruitmenthub"
    assert rows["Central Goldfields"]["adapter"] == "RecruitmentHubFetcher"
    assert rows["Central Goldfields"]["listing_url"] == "https://centralgoldfieldscareers.com.au/Vacancies/"
    assert rows["Central Goldfields"]["detail_pattern"] == "/Vacancies/{job_id}/title/{slug}"

    assert rows["Hepburn"]["platform_family"] == "t1cloud"
    assert rows["Hepburn"]["listing_url"] == (
        "https://hepburn.t1cloud.com/T1Default/CiAnywhere/Web/HEPBURN/"
        "Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES"
    )

    assert rows["Hobsons Bay"]["platform_family"] == "bigredsky"
    assert rows["Hobsons Bay"]["listing_url"] == "https://hobsonsbay.bigredsky.com/page.php?pageID=106"

    assert rows["Melbourne"]["platform_family"] == "aurion_selfservice"
    assert rows["Wodonga"]["platform_family"] == "aurion_selfservice"

    assert rows["Maribyrnong"]["platform_family"] == "recruitmenthub"
    assert rows["Maribyrnong"]["adapter"] == "RecruitmentHubFetcher"

    assert rows["Merri-bek"]["platform_family"] == "native_council"
    assert rows["Merri-bek"]["listing_url"] == "https://www.merri-bek.vic.gov.au/jobs"

    assert rows["South Gippsland"]["platform_family"] == "applynow"
    assert rows["South Gippsland"]["listing_url"] == "https://southgippsland.applynow.net.au/"

    assert rows["Bayside"]["listing_url"] == "https://careers.bayside.vic.gov.au/jobs/search"
    assert rows["Bayside"]["detail_pattern"] == "/jobs/{slug}"

    assert rows["Alpine"]["platform_family"] == "native_council"
    assert rows["Alpine"]["poll_tier"] == "C"

    assert rows["Benalla"]["listing_url"] == "https://www.benalla.vic.gov.au/council/careers-at-council/positions-vacant/"
    assert rows["Benalla"]["detail_pattern"] == "/job-listing/{slug}"

    assert rows["Mildura"]["listing_url"] == "https://www.mildura.vic.gov.au/Council/Careers/Current-Job-Vacancies"
    assert rows["Mildura"]["detail_pattern"] == "/Jobs-Listing/{slug}"

    assert rows["Moorabool"]["platform_family"] == "elmo_talent"
    assert rows["Moorabool"]["adapter"] == "ElmoTalentFetcher"
    assert rows["Moorabool"]["listing_url"] == "https://www.moorabool.vic.gov.au/About-Council/Careers/Vacancies"
    assert rows["Moorabool"]["embed_url"] == "https://moorabool.elmotalent.com.au/careers/msc/jobs"
    assert rows["Moorabool"]["portal_code"] == "msc"

    assert rows["Murrindindi"]["listing_url"] == "https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions"
    assert rows["Murrindindi"]["detail_pattern"] == "/Council/Jobs-and-Tenders/Vacant-Positions/{slug}"

    assert rows["Stonnington"]["platform_family"] == "elmo_talent"
    assert rows["Stonnington"]["adapter"] == "ElmoTalentFetcher"
    assert rows["Stonnington"]["listing_url"] == "https://cos.elmotalent.com.au/careers/cosjobs/jobs"
    assert rows["Stonnington"]["portal_code"] == "cosjobs"

    assert rows["Hume"]["platform_family"] == "smartrecruiters"
    assert rows["Hume"]["adapter"] == "SmartRecruitersFetcher"
    assert rows["Hume"]["listing_url"] == "https://www.hume.vic.gov.au/Your-Council/Careers-at-Hume/Jobs-and-Opportunities"
    assert rows["Hume"]["company_code"] == "HumeCityCouncil"

    assert rows["Whittlesea"]["platform_family"] == "bigredsky"
    assert rows["Whittlesea"]["adapter"] == "AggregatorFetcher"
    assert rows["Whittlesea"]["listing_url"] == "https://whittlesea.bigredsky.com/page.php?pageID=106"
    assert rows["Whittlesea"]["detail_pattern"] == "/page.php?pageID=160&AdvertID={job_id}"


def test_council_job_source_registry_keeps_broad_boards_restricted():
    payload = council_job_source_registry_payload()
    restricted = {source["source_id"]: source for source in payload["restricted_sources"]}

    assert set(restricted) == {"indeed", "linkedin", "seek"}
    assert all(
        source["access_policy"] == "restricted_do_not_crawl_without_permission"
        for source in restricted.values()
    )
    assert {source["source_id"] for source in payload["secondary_sources"]} == {
        "careers_at_council_victoria",
        "council_direct",
        "jora_victorian_council_search",
        "local_government_jobs_australia",
        "viccouncils_directory",
    }


def test_endpoint_discovery_candidates_include_pulse_subdomain_pattern():
    candidates = endpoint_discovery_candidates("Ballarat")

    assert candidates[0]["platform_family"] == "pulse"
    assert candidates[0]["listing_url"] == "https://ballarat.pulsesoftware.com/Pulse/jobs"


def test_endpoint_discovery_candidates_include_recruitmenthub_name_patterns():
    urls = {candidate["listing_url"] for candidate in endpoint_discovery_candidates("Nillumbik")}

    assert "https://nillumbik.recruitmenthub.com.au/Vacancies" in urls
    assert "https://nillumbikshirecouncil.recruitmenthub.com.au/about/Current-vacancies" in urls


def test_endpoint_discovery_candidates_include_bigredsky_page_pattern():
    urls = {candidate["listing_url"] for candidate in endpoint_discovery_candidates("Whittlesea")}

    assert "https://whittlesea.bigredsky.com/page.php?pageID=106" in urls


def test_endpoint_discovery_candidates_include_t1cloud_ext_pattern():
    urls = {
        candidate["listing_url"]
        for candidate in endpoint_discovery_candidates(
            "Campaspe",
            council_name="Campaspe Shire Council",
            entry_url="https://www.campaspe.vic.gov.au/Our-council/Employment-tenders/Careers",
        )
    }

    assert (
        "https://campaspe.t1cloud.com/T1Default/CiAnywhere/Web/CAMPASPE/"
        "Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_EXT?suite=CES"
    ) in urls
    assert (
        "https://campaspe.t1cloud.com/T1Default/CiAnywhere/Web/CAMPASPE/"
        "Public/Function/%24ORG.REC.EXJOBB.ENQ/RECRUIT_GUEST?suite=CES"
    ) in urls


def test_endpoint_discovery_candidates_include_smartrecruiters_company_api_pattern():
    urls = {
        candidate["listing_url"]
        for candidate in endpoint_discovery_candidates("Hume", council_name="Hume City Council")
    }

    assert "https://api.smartrecruiters.com/v1/companies/HumeCityCouncil/postings?limit=100&offset=0" in urls


def test_endpoint_discovery_candidates_include_elmo_talent_initials_pattern():
    urls = {
        candidate["listing_url"]
        for candidate in endpoint_discovery_candidates("Moorabool", council_name="Moorabool Shire Council")
    }

    assert "https://moorabool.elmotalent.com.au/careers/msc/jobs" in urls


def test_endpoint_discovery_candidates_include_city_of_applynow_pattern():
    urls = {
        candidate["listing_url"]
        for candidate in endpoint_discovery_candidates("Greater Bendigo", council_name="Greater Bendigo City Council")
    }

    assert "https://city-of-greater-bendigo.applynow.net.au/" in urls


def test_canonicalize_job_url_removes_tracking_params_and_normalises_host():
    assert (
        canonicalize_job_url(
            "HTTPS://Brimbank.PulseSoftware.com/Pulse/job/DaSHt4/Spatial-and-Data-Analyst/"
            "?utm_source=seek&source=public&page=2"
        )
        == "https://brimbank.pulsesoftware.com/Pulse/job/DaSHt4/Spatial-and-Data-Analyst?page=2"
    )


def test_extract_job_summaries_from_server_rendered_listing_links():
    source = {
        "short_name": "Yarra",
        "council_name": "Yarra City Council",
        "council_grouping": "metropolitan",
        "poll_tier": "A",
        "platform_family": "pageup",
        "listing_url": "https://jobs.yarracity.vic.gov.au/cw/en/listing/",
    }
    html = """
    <a href="/cw/en/job/496802/north-carlton-team-leader">North Carlton Team Leader</a>
    <a href="/cw/en/job/496802/north-carlton-team-leader">North Carlton Team Leader</a>
    <a href="/cw/en/listing/">Back to listing</a>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "North Carlton Team Leader"
    assert jobs[0]["source_job_id"] == "496802"
    assert jobs[0]["job_url"] == "https://jobs.yarracity.vic.gov.au/cw/en/job/496802/north-carlton-team-leader"


def test_extract_job_summaries_from_benalla_positions_vacant_cards():
    source = {
        "short_name": "Benalla",
        "council_name": "Benalla Rural City Council",
        "council_grouping": "small_shire",
        "poll_tier": "C",
        "platform_family": "native_council",
        "listing_url": "https://www.benalla.vic.gov.au/council/careers-at-council/positions-vacant/",
        "detail_pattern": "/job-listing/{slug}",
    }
    html = """
    <h4 class="h5">School Crossing Supervisors</h4>
    <a href="https://www.benalla.vic.gov.au/job-listing/school-crossing-supervisors/" class="btn">Read more</a>
    <h4 class="h5">Project Manager - Community Development Fund</h4>
    <a href="https://www.benalla.vic.gov.au/job-listing/project-manager-community-development-fund-2/" class="btn">Read more</a>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert [job["job_title"] for job in jobs] == [
        "School Crossing Supervisors",
        "Project Manager Community Development Fund",
    ]
    assert jobs[0]["job_url"] == "https://www.benalla.vic.gov.au/job-listing/school-crossing-supervisors"


def test_extract_job_summaries_from_mildura_opencities_job_cards():
    source = {
        "short_name": "Mildura",
        "council_name": "Mildura Rural City Council",
        "council_grouping": "regional_city",
        "poll_tier": "A",
        "platform_family": "native_council",
        "listing_url": "https://www.mildura.vic.gov.au/Council/Careers/Current-Job-Vacancies",
        "detail_pattern": "/Jobs-Listing/{slug}",
    }
    html = """
    <div class="list-container job-list-container left">
      <article>
        <a href="https://www.mildura.vic.gov.au/Jobs-Listing/Finance-Team-Leader-R2748">
          <h2 class="list-item-title">Finance Team Leader</h2>
          <p class="applications-closing small-text">Applications closing on Thursday, 21 May 2026</p>
          <p>An exciting opportunity is now available, join our Finance team and make a real impact.</p>
        </a>
      </article>
      <article>
        <a href="https://www.mildura.vic.gov.au/Council/Careers/Working-at-Council">
          <h2 class="list-item-title">Working at Council</h2>
        </a>
      </article>
    </div>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "Finance Team Leader"
    assert jobs[0]["source_job_id"] == "R2748"
    assert jobs[0]["job_number"] == "R2748"
    assert jobs[0]["closing_at_text"] == "Thursday, 21 May 2026"
    assert jobs[0]["description_text"] == "An exciting opportunity is now available, join our Finance team and make a real impact."
    assert jobs[0]["parse_confidence"] == "opencities_job_list_card"


def test_extract_job_summaries_from_murrindindi_vacant_position_cards():
    source = {
        "short_name": "Murrindindi",
        "council_name": "Murrindindi Shire Council",
        "council_grouping": "small_shire",
        "poll_tier": "C",
        "platform_family": "native_council",
        "listing_url": "https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions",
        "detail_pattern": "/Council/Jobs-and-Tenders/Vacant-Positions/{slug}",
    }
    html = """
    <div class="list-container job-list-container">
      <article>
        <a href="https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions/Occupational-Health-Safety-Coordinator">
          <h2 class="list-item-title">Occupational Health &amp; Safety Coordinator</h2>
          <p class="applications-closing small-text">Applications closing on Thursday, 14 May 2026</p>
          <p>Full Time</p>
          <p>Murrindindi Shire Council has an exciting opportunity for an Occupational Health and Safety Coordinator.</p>
        </a>
      </article>
      <article>
        <a href="https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/How-to-apply">
          <h2 class="list-item-title">How to apply</h2>
        </a>
      </article>
    </div>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "Occupational Health & Safety Coordinator"
    assert jobs[0]["closing_at_text"] == "Thursday, 14 May 2026"
    assert jobs[0]["description_text"] == "Full Time Murrindindi Shire Council has an exciting opportunity for an Occupational Health and Safety Coordinator."
    assert jobs[0]["job_url"] == "https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions/Occupational-Health-Safety-Coordinator"


def test_extract_job_summaries_from_recruitmenthub_custom_domain():
    source = {
        "short_name": "Central Goldfields",
        "council_name": "Central Goldfields Shire Council",
        "council_grouping": "small_shire",
        "poll_tier": "C",
        "platform_family": "recruitmenthub",
        "listing_url": "https://centralgoldfieldscareers.com.au/Vacancies/",
        "detail_pattern": "/Vacancies/{job_id}/title/{slug}",
    }
    html = """
    <a href="/Vacancies/6889721/title/Immunisation-Nurse">Immunisation Nurse</a>
    <a href="/applyjob/6889721">Apply now</a>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "Immunisation Nurse"
    assert jobs[0]["source_job_id"] == "6889721"
    assert jobs[0]["job_url"] == "https://centralgoldfieldscareers.com.au/Vacancies/6889721/title/Immunisation-Nurse"


def test_extract_job_summaries_skips_native_jobs_guidance_pages():
    source = {
        "short_name": "Yarriambiack",
        "council_name": "Yarriambiack Shire Council",
        "council_grouping": "small_shire",
        "poll_tier": "C",
        "platform_family": "native_council",
        "listing_url": "https://www.yarriambiack.vic.gov.au/Engage-With-Us/Jobs",
        "detail_pattern": "/Engage-With-Us/Jobs/{slug}",
    }
    html = """
    <a href="/Engage-With-Us/Jobs/Recruitment-and-Selection">Recruitment and Selection</a>
    <a href="/Engage-With-Us/Jobs/Addressing-The-Key-Selection-Criteria">Addressing The Key Selection Criteria</a>
    <a href="/Engage-With-Us/Jobs/Traineeships-and-Apprenticeships">Traineeships and Apprenticeships</a>
    """

    jobs = extract_job_summaries_from_listing(source, html)

    assert jobs == []


def test_job_intake_scrape_preview_reports_jobs_and_source_statuses():
    registry = {
        "rows": [
            {
                "short_name": "Greater Dandenong",
                "council_name": "Greater Dandenong City Council",
                "council_grouping": "metropolitan",
                "poll_tier": "A",
                "platform_family": "native_council_custom",
                "monitoring_status": "ready",
                "listing_url": "https://jobs.greaterdandenong.vic.gov.au/jobs",
            },
            {
                "short_name": "Pending",
                "council_name": "Pending Shire Council",
                "poll_tier": "C",
                "platform_family": "unknown_official",
                "monitoring_status": "needs_endpoint_discovery",
                "listing_url": "https://example.test/careers",
            },
        ]
    }

    def fetcher(url):
        assert url == "https://jobs.greaterdandenong.vic.gov.au/jobs"
        return (
            '<a href="/jobs/festivals-and-events-officer">Festivals and Events Officer</a>',
            {"http_status": 200, "final_url": url, "bytes": 100},
        )

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher)

    assert payload["set_id"] == "job_intake_scrape_preview"
    assert payload["summary"]["sources_attempted"] == 1
    assert payload["summary"]["councils_with_jobs"] == 1
    assert payload["summary"]["jobs"] == 1
    assert payload["rows"][0]["job_title"] == "Festivals and Events Officer"
    assert payload["source_results"][0]["parsed_jobs"] == 1
    assert payload["tier_explainer"][0]["tier"] == "A"


def test_job_intake_scrape_preview_follows_embedded_applynow_iframe():
    registry = {
        "rows": [
            {
                "short_name": "Greater Bendigo",
                "council_name": "Greater Bendigo City Council",
                "council_grouping": "regional_city",
                "poll_tier": "A",
                "platform_family": "unknown_official",
                "monitoring_status": "ready",
                "listing_url": "https://www.bendigo.vic.gov.au/about-us/working-city",
            },
        ]
    }

    def fetcher(url):
        if url == "https://www.bendigo.vic.gov.au/about-us/working-city":
            return (
                '<h2>Current vacancies</h2><iframe src="https://city-of-bendigo.applynow.net.au"></iframe>',
                {"http_status": 200, "bytes": 100},
            )
        if url == "https://city-of-bendigo.applynow.net.au/":
            return (
                '<a href="https://city-of-bendigo.applynow.net.au/jobs/6040526-project-manager-capital-works">Project Manager (Capital Works)</a>',
                {"http_status": 200, "bytes": 100},
            )
        raise AssertionError(f"unexpected url {url}")

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 1
    assert payload["rows"][0]["job_title"] == "Project Manager (Capital Works)"
    assert payload["rows"][0]["source_family"] == "applynow"
    assert payload["source_results"][0]["embedded_sources_attempted"] == 1


def test_generated_applynow_probe_rejects_generic_employment_office_board():
    listing_url = "https://ballaratcity-external.applynow.net.au/"
    registry = {
        "rows": [
            {
                "short_name": "Ballarat",
                "council_name": "Ballarat City Council",
                "council_grouping": "regional_city",
                "poll_tier": "A",
                "platform_family": "applynow",
                "monitoring_status": "ready",
                "listing_url": listing_url,
                "source_role": "generated_endpoint_candidate",
            },
        ]
    }

    def fetcher(url):
        assert url == listing_url
        return (
            """
            <h1>Classifications - Employment Office</h1>
            <a href="https://applynow.net.au/jobs/RS312213-assistant-manager">Assistant Manager</a>
            """,
            {"http_status": 200, "final_url": url, "bytes": 200},
        )

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 0
    assert payload["source_results"][0]["parsed_jobs"] == 0
    assert payload["source_results"][0]["source_rejection_reason"] == "generic_applynow_board_not_council_affiliated"


def test_extract_council_direct_victorian_jobs():
    source = {
        "source_id": "council_direct",
        "source_name": "Council Direct",
        "source_family": "councildirect",
        "url": "https://www.councildirect.com.au/jobs",
        "source_priority": 2,
    }
    html = """
    <a href="https://www.councildirect.com.au/job/municipal-fire-prevention-officer">
      Municipal Fire Prevention Officer Part Time Salary: Band 6, $88,515 pa (pro-rata) + Super Mount Alexander Shire Council VIC (Victoria)
    </a>
    <a href="https://www.councildirect.com.au/job/work-health-and-safety-advisor">
      Work Health and Safety Advisor Full Time Salary: $108,134 Uralla Shire Council NSW (New South Wales)
    </a>
    """

    jobs = _extract_secondary_jobs(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "Municipal Fire Prevention Officer"
    assert jobs[0]["council_name"] == "Mount Alexander Shire Council"
    assert jobs[0]["classification_band"] == "Band 6"
    assert jobs[0]["standard_band_number"] == 6


def test_council_direct_expands_per_council_company_filters():
    registry = {
        "rows": [
            {
                "short_name": "Greater Bendigo",
                "council_name": "Greater Bendigo City Council",
                "poll_tier": "A",
            },
            {
                "short_name": "Horsham",
                "council_name": "Horsham Rural City Council",
                "poll_tier": "B",
            },
        ]
    }

    urls = {source["url"] for source in _council_direct_council_page_sources(registry)}

    assert "https://www.councildirect.com.au/jobs?company=city-of-greater-bendigo" in urls
    assert "https://www.councildirect.com.au/jobs?company=horsham-rural-city-council" in urls


def test_council_direct_company_filter_uses_source_council_when_card_omits_name():
    source = {
        "source_id": "council_direct_greater_bendigo",
        "source_name": "Council Direct - Greater Bendigo City Council",
        "source_family": "councildirect",
        "url": "https://www.councildirect.com.au/jobs?company=city-of-greater-bendigo",
        "council_name": "Greater Bendigo City Council",
        "source_priority": 35,
    }
    html = """
    <a href="https://www.councildirect.com.au/job/civil-construction-worker">
      Civil Construction Worker Full Time Salary: Band 3, $68,201 VIC (Victoria)
    </a>
    """

    jobs = _extract_secondary_jobs(source, html)

    assert len(jobs) == 1
    assert jobs[0]["council_name"] == "Greater Bendigo City Council"
    assert jobs[0]["classification_band"] == "Band 3"


def test_jora_expands_per_council_search_pages():
    registry = {
        "rows": [
            {
                "short_name": "Bass Coast",
                "council_name": "Bass Coast Shire Council",
                "poll_tier": "B",
            },
        ]
    }

    urls = {source["url"] for source in _jora_council_search_sources(registry)}

    assert "https://au.jora.com/Bass-Coast-Council-jobs-in-Bass-Coast-VIC" in urls
    assert "https://au.jora.com/Bass-Coast-Shire-Council-jobs-in-Bass-Coast-VIC" in urls


def test_jora_parser_keeps_matching_council_cards_only():
    source = {
        "source_id": "jora_bass_coast",
        "source_name": "Jora - Bass Coast Shire Council",
        "source_family": "jora",
        "url": "https://au.jora.com/Bass-Coast-Council-jobs-in-Bass-Coast-VIC",
        "short_name": "Bass Coast",
        "council_name": "Bass Coast Shire Council",
        "strict_council_match": True,
    }
    html = """
    <div id="r_1" class="job-card result organic-job"
      data-braze-job-panel-view="{&quot;job_id&quot;:&quot;abc123&quot;,&quot;job_title&quot;:&quot;Open Space Maintenance Team Member&quot;,&quot;location&quot;:&quot;Cowes VIC&quot;,&quot;company_name&quot;:&quot;Bass Coast Shire Council&quot;}"
      data-job-card="true">
      <h2 class="job-title"><a class="job-link -no-underline -desktop-only show-job-description" href="/job/Open-Space-Maintenance-abc123?sp=serp">Open Space Maintenance Team Member</a></h2>
      <span>Bass Coast Shire Council</span><span>Cowes VIC</span><span>$68,951 - $68,951 a year</span><span>Posted 4d ago</span>
    </div>
    <div id="r_2" class="job-card result organic-job"
      data-braze-job-panel-view="{&quot;job_id&quot;:&quot;def456&quot;,&quot;job_title&quot;:&quot;Nurse&quot;,&quot;location&quot;:&quot;Wonthaggi VIC&quot;,&quot;company_name&quot;:&quot;Bass Coast Health&quot;}"
      data-job-card="true">
      <h2 class="job-title"><a class="job-link -no-underline -desktop-only show-job-description" href="/job/Nurse-def456?sp=serp">Nurse</a></h2>
      <span>Bass Coast Health</span>
    </div>
    """

    jobs = _extract_secondary_jobs(source, html)

    assert len(jobs) == 1
    assert jobs[0]["job_title"] == "Open Space Maintenance Team Member"
    assert jobs[0]["council_name"] == "Bass Coast Shire Council"
    assert jobs[0]["salary_min"] == 68951
    assert jobs[0]["job_url"] == "https://au.jora.com/job/Open-Space-Maintenance-abc123"


def test_local_government_jobs_expands_strict_council_search_pages():
    registry = {
        "rows": [
            {
                "short_name": "Mitchell",
                "council_name": "Mitchell Shire Council",
                "poll_tier": "B",
            },
        ]
    }

    sources = _local_government_jobs_council_search_sources(registry)

    assert sources[0]["url"] == "https://www.localgovernmentjobs.com.au/jobs?search=Mitchell+Shire+Council"
    assert sources[0]["strict_council_match"] is True


def test_checked_job_accumulator_drops_generated_generic_applynow_rows(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Ballarat", "council_name": "Ballarat City Council", "poll_tier": "A"},
        ]
    }
    payload = {
        "set_id": "job_intake_scrape_preview",
        "fetched_at": "2026-05-22T00:00:00+00:00",
        "rows": [
            {
                "short_name": "Ballarat",
                "council_name": "Ballarat City Council",
                "job_title": "Assistant Manager",
                "job_url": "https://applynow.net.au/jobs/RS312213-assistant-manager",
                "source_family": "applynow",
                "inferred_standard_band_number": 6,
                "salary_text": "$95,000",
                "fetched_at": "2026-05-22T00:00:00+00:00",
            },
        ],
    }

    accumulated = accumulate_checked_jobs_from_payload(
        payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_label="wide_official_vendor_refresh",
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 0
    assert accumulated["rows"] == []


def test_checked_job_accumulator_rejects_native_guidance_pages(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Yarriambiack", "council_name": "Yarriambiack Shire Council", "poll_tier": "C"},
        ]
    }
    payload = {
        "set_id": "job_intake_scrape_preview",
        "fetched_at": "2026-05-22T00:00:00+00:00",
        "rows": [
            {
                "short_name": "Yarriambiack",
                "council_name": "Yarriambiack Shire Council",
                "job_title": "Recruitment and Selection",
                "job_url": "https://www.yarriambiack.vic.gov.au/Engage-With-Us/Jobs/Recruitment-and-Selection",
                "source_family": "native_council",
                "classification_band": "Band 2",
                "canonical_reference_month": "2026-05",
            },
        ],
    }

    accumulated = accumulate_checked_jobs_from_payload(
        payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 0
    assert accumulated["reject_summary"]["non_job_navigation_page"] == 1
    assert accumulated["rows"] == []



def test_job_intake_snapshot_persists_preview_payload(tmp_path):
    snapshot_path = tmp_path / "job-intake-snapshot.json"
    assert load_job_intake_snapshot(snapshot_path=snapshot_path)["snapshot_status"] == "empty"

    saved = save_job_intake_snapshot(
        {
            "set_id": "job_intake_scrape_preview",
            "summary": {"jobs": 1, "standard_band_1_to_8_jobs": 1},
            "rows": [{"job_title": "Governance Officer"}],
            "source_results": [],
        },
        snapshot_path=snapshot_path,
    )
    loaded = load_job_intake_snapshot(snapshot_path=snapshot_path)

    assert saved["snapshot_exists"] is True
    assert loaded["set_id"] == "job_intake_scrape_snapshot"
    assert loaded["source_payload_set_id"] == "job_intake_scrape_preview"
    assert loaded["summary"]["jobs"] == 1
    assert loaded["scope"]["refresh_policy"] == "manual_button_only"


def test_checked_job_accumulator_dedupes_on_council_title_band_month(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Example", "council_name": "Example City Council", "poll_tier": "A"},
            {"short_name": "Other", "council_name": "Other Shire Council", "poll_tier": "C"},
        ]
    }

    payload = {
        "set_id": "job_intake_scrape_preview",
        "fetched_at": "2026-04-15T00:00:00+00:00",
        "rows": [
            {
                "job_title": "Governance Officer",
                "job_url": "https://example.test/jobs/1",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 5",
                "canonical_reference_month": "2026-04",
            },
            {
                "job_title": "Governance Officer",
                "job_url": "https://example.test/jobs/duplicate",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 5",
                "canonical_reference_month": "2026-04",
            },
            {
                "job_title": "Unclassified Officer",
                "job_url": "https://example.test/jobs/no-band",
                "short_name": "Other",
                "council_name": "Other Shire Council",
                "canonical_reference_month": "2026-04",
            },
        ],
    }

    accumulated = accumulate_checked_jobs_from_payload(
        payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 1
    assert accumulated["summary"]["confirmed_band_jobs"] == 1
    assert accumulated["rows"][0]["dedupe_key_parts"] == {
        "council": "example",
        "title": "governance officer",
        "band": "5",
        "month": "2026-04",
    }
    assert accumulated["rows"][0]["sighting_count"] == 2
    assert accumulated["coverage"]["councils_with_checked_jobs"] == 1
    assert accumulated["coverage"]["councils_without_checked_jobs"] == 1
    assert accumulated["reject_summary"]["missing_band_1_to_8"] == 1


def test_checked_job_accumulator_merges_secondary_conflicting_band_into_official(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Banyule", "council_name": "Banyule City Council", "poll_tier": "A"},
        ]
    }
    official_payload = {
        "set_id": "official",
        "fetched_at": "2026-05-22T00:00:00+00:00",
        "rows": [
            {
                "job_title": "Sports Turf Groundsperson & Tractor Operator",
                "job_url": "https://banyule.pulsesoftware.com/Pulse/job/65FSB9/Sports-Turf-Groundsperson---Tractor-Operator",
                "short_name": "Banyule",
                "council_name": "Banyule City Council",
                "source_family": "pulse",
                "inferred_standard_band_number": 4,
                "salary_text": "Annual AUD $75,614.10 - $75,614.10",
                "canonical_reference_month": "2026-05",
            },
        ],
    }
    secondary_payload = {
        "set_id": "secondary",
        "fetched_at": "2026-05-22T01:00:00+00:00",
        "rows": [
            {
                "job_title": "Sports Turf Groundsperson & Tractor Operator",
                "job_url": "https://www.councildirect.com.au/job/sports-turf-groundsperson-tractor-operator",
                "short_name": "Banyule",
                "council_name": "Banyule City Council",
                "source_family": "councildirect",
                "classification_band": "Band 8",
                "salary_text": "Annual AUD $75,614.10 - $75,614.10",
                "canonical_reference_month": "2026-05",
            },
        ],
    }

    accumulate_checked_jobs_from_payload(
        official_payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
    )
    accumulated = accumulate_checked_jobs_from_payload(
        secondary_payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="secondary",
        source_label="Council Direct - Banyule City Council",
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 1
    row = accumulated["rows"][0]
    assert row["standard_band_number"] == 4
    assert row["classification_confidence"] == "inferred"
    assert row["observed_status"] == "current"
    assert row["latest_job"]["source_family"] == "pulse"
    assert row["source_kinds_seen"] == ["official", "secondary"]
    assert sorted(row["job_urls_seen"]) == [
        "https://banyule.pulsesoftware.com/Pulse/job/65FSB9/Sports-Turf-Groundsperson---Tractor-Operator",
        "https://www.councildirect.com.au/job/sports-turf-groundsperson-tractor-operator",
    ]


def test_checked_job_accumulator_keeps_distinct_official_same_title_jobs(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Example", "council_name": "Example City Council", "poll_tier": "A"},
        ]
    }
    payload = {
        "set_id": "official",
        "fetched_at": "2026-05-22T00:00:00+00:00",
        "rows": [
            {
                "job_title": "Project Officer",
                "job_url": "https://example.test/jobs/project-officer-band-5",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 5",
                "canonical_reference_month": "2026-05",
            },
            {
                "job_title": "Project Officer",
                "job_url": "https://example.test/jobs/project-officer-band-6",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 6",
                "canonical_reference_month": "2026-05",
            },
        ],
    }

    accumulated = accumulate_checked_jobs_from_payload(
        payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 2
    assert sorted(row["standard_band_number"] for row in accumulated["rows"]) == [5, 6]


def test_checked_job_accumulator_keeps_history_when_official_job_disappears(tmp_path):
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Example", "council_name": "Example City Council", "poll_tier": "A"},
            {"short_name": "Other", "council_name": "Other Shire Council", "poll_tier": "C"},
        ]
    }
    first_payload = {
        "set_id": "job_intake_scrape_preview",
        "fetched_at": "2026-04-15T00:00:00+00:00",
        "rows": [
            {
                "job_title": "Governance Officer",
                "job_url": "https://example.test/jobs/1",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 5",
                "canonical_reference_month": "2026-04",
            },
            {
                "job_title": "Works Officer",
                "job_url": "https://other.test/jobs/2",
                "short_name": "Other",
                "council_name": "Other Shire Council",
                "classification_band": "Band 3",
                "canonical_reference_month": "2026-04",
            },
        ],
    }
    second_payload = {
        "set_id": "job_intake_scrape_preview",
        "fetched_at": "2026-05-15T00:00:00+00:00",
        "rows": [
            {
                "job_title": "Governance Officer",
                "job_url": "https://example.test/jobs/1",
                "short_name": "Example",
                "council_name": "Example City Council",
                "classification_band": "Band 5",
                "canonical_reference_month": "2026-04",
            },
        ],
    }

    accumulate_checked_jobs_from_payload(
        first_payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
        mark_missing_historical=True,
    )
    accumulated = accumulate_checked_jobs_from_payload(
        second_payload,
        accumulator_path=accumulator_path,
        registry_payload=registry,
        source_kind="official",
        mark_missing_historical=True,
    )

    statuses = {row["job_title"]: row["observed_status"] for row in accumulated["rows"]}
    assert statuses["Governance Officer"] == "current"
    assert statuses["Works Officer"] == "historical_not_seen_latest"
    assert accumulated["summary"]["checked_classified_jobs"] == 2
    assert accumulated["summary"]["current_official_jobs"] == 1
    assert accumulated["summary"]["historical_jobs"] == 1


def test_checked_job_accumulator_ingests_saved_snapshot(tmp_path):
    snapshot_path = tmp_path / "job-intake-snapshot.json"
    accumulator_path = tmp_path / "checked-jobs.json"
    registry = {
        "rows": [
            {"short_name": "Example", "council_name": "Example City Council", "poll_tier": "A"},
        ]
    }
    save_job_intake_snapshot(
        {
            "set_id": "job_intake_scrape_preview",
            "fetched_at": "2026-04-15T00:00:00+00:00",
            "summary": {"jobs": 1},
            "rows": [
                {
                    "job_title": "Governance Officer",
                    "job_url": "https://example.test/jobs/1",
                    "short_name": "Example",
                    "council_name": "Example City Council",
                    "classification_band": "Band 5",
                    "canonical_reference_month": "2026-04",
                },
            ],
            "source_results": [],
        },
        snapshot_path=snapshot_path,
    )

    accumulated = accumulate_checked_jobs_from_snapshot(
        snapshot_path=snapshot_path,
        accumulator_path=accumulator_path,
        registry_payload=registry,
    )
    loaded = load_checked_job_accumulator(
        accumulator_path=accumulator_path,
        registry_payload=registry,
    )

    assert accumulated["summary"]["checked_classified_jobs"] == 1
    assert loaded["rows"][0]["job_title"] == "Governance Officer"
    assert loaded["coverage"]["coverage_rate"] == 100


def test_job_pipeline_stage1_admits_only_band_governed_jobs():
    snapshot = {
        "snapshot_exists": True,
        "saved_at": "2026-05-12T01:00:00+00:00",
        "summary": {"jobs": 2},
        "rows": [
            {
                "job_uid": "job-1",
                "job_url": "https://example.test/jobs/1",
                "source_family": "bigredsky",
                "council_name": "Example Council",
                "council_grouping": "metropolitan",
                "job_title": "Governance Officer",
                "job_status": "open",
                "state": "VIC",
                "classification_band": "Band 5",
                "standard_band_number": 5,
                "closing_at": "2026-05-20T23:59:00+10:00",
                "description_text": "Band governed role.",
                "is_standard_band_1_to_8": True,
                "governance_status": "auto_included",
            },
            {
                "job_uid": "job-2",
                "job_url": "https://example.test/jobs/2",
                "job_title": "Executive Officer",
                "governance_status": "needs_band_review",
            },
        ],
    }

    payload = job_pipeline_stage1_payload(snapshot_payload=snapshot)

    assert payload["summary"]["governed_input_jobs"] == 1
    assert payload["summary"]["stage1_ready_jobs"] == 1
    assert payload["summary"]["stage1_fill_required_jobs"] == 0
    assert payload["rows"][0]["pipeline_stage"] == "stage_1_field_completion"
    assert payload["rows"][0]["stage1_status"] == "stage1_ready"


def test_job_intake_scrape_preview_extracts_hume_smartrecruiters_widget_jobs():
    hume_url = "https://www.hume.vic.gov.au/Your-Council/Careers-at-Hume/Jobs-and-Opportunities"
    registry = {
        "rows": [
            {
                "short_name": "Hume",
                "council_name": "Hume City Council",
                "council_grouping": "interface",
                "poll_tier": "A",
                "platform_family": "smartrecruiters",
                "monitoring_status": "ready",
                "listing_url": hume_url,
            },
        ]
    }

    def fetcher(url):
        if url == hume_url:
            return (
                '<script class="job_widget">widget({"company_code": "HumeCityCouncil"});</script>',
                {"http_status": 200, "final_url": url, "bytes": 100},
            )
        if url.startswith("https://api.smartrecruiters.com/v1/companies/HumeCityCouncil/postings"):
            return (
                json.dumps({
                    "content": [
                        {
                            "id": "744000125618155",
                            "name": "Early Childhood Educator Assistant",
                            "refNumber": "REF834U",
                            "company": {"identifier": "HumeCityCouncil", "name": "Hume City Council"},
                            "releasedDate": "2026-05-10T23:44:26.187Z",
                            "location": {"fullLocation": "Broadmeadows, VIC, Australia"},
                            "department": {"label": "Family, Youth & Children"},
                            "typeOfEmployment": {"label": "Part-time"},
                        },
                    ],
                }),
                {"http_status": 200, "final_url": url, "bytes": 500},
            )
        raise AssertionError(url)

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 1
    assert payload["summary"]["councils_with_jobs"] == 1
    job = payload["rows"][0]
    assert job["job_title"] == "Early Childhood Educator Assistant"
    assert job["job_url"] == "https://jobs.smartrecruiters.com/HumeCityCouncil/744000125618155-early-childhood-educator-assistant"
    assert job["source_job_id"] == "744000125618155"
    assert job["job_number"] == "REF834U"
    assert job["work_type"] == "Part-time"
    assert job["location_text"] == "Broadmeadows, VIC, Australia"
    assert job["posted_at"].startswith("2026-05-10T23:44:26")
    assert payload["source_results"][0]["parsed_jobs"] == 1


def test_job_intake_scrape_preview_extracts_whittlesea_bigredsky_rows():
    listing_url = "https://whittlesea.bigredsky.com/page.php?pageID=106"
    registry = {
        "rows": [
            {
                "short_name": "Whittlesea",
                "council_name": "City of Whittlesea",
                "council_grouping": "interface",
                "poll_tier": "A",
                "platform_family": "bigredsky",
                "monitoring_status": "ready",
                "listing_url": listing_url,
            },
        ]
    }

    def fetcher(url):
        assert url == listing_url
        return (
            """
            <table>
              <tr class="evenrow">
                <td><input value="24/05/2026">24/05/2026</td>
                <td><a href="page.php?pageID=160&windowUID=0&AdvertID=908712">Principal Data Analyst</a></td>
                <td>Northern Suburbs</td>
              </tr>
            </table>
            """,
            {"http_status": 200, "final_url": url, "bytes": 500},
        )

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 1
    assert payload["summary"]["councils_with_jobs"] == 1
    job = payload["rows"][0]
    assert job["job_title"] == "Principal Data Analyst"
    assert job["source_job_id"] == "908712"
    assert job["job_url"] == "https://whittlesea.bigredsky.com/page.php?AdvertID=908712&pageID=160&windowUID=0"
    assert job["closing_at"].startswith("2026-05-24")
    assert job["location_text"] == "Northern Suburbs"
    assert job["parse_confidence"] == "bigredsky_table_row"
    assert payload["source_results"][0]["parsed_jobs"] == 1


def test_job_intake_scrape_preview_extracts_moorabool_elmo_iframe_jobs():
    listing_url = "https://www.moorabool.vic.gov.au/About-Council/Careers/Vacancies"
    embed_url = "https://moorabool.elmotalent.com.au/careers/msc/jobs"
    registry = {
        "rows": [
            {
                "short_name": "Moorabool",
                "council_name": "Moorabool Shire Council",
                "council_grouping": "large_shire",
                "poll_tier": "B",
                "platform_family": "elmo_talent",
                "monitoring_status": "ready",
                "listing_url": listing_url,
                "embed_url": embed_url,
            },
        ]
    }

    def fetcher(url):
        if url == listing_url:
            return (
                f'<iframe id="elmo-recruitment-embed" src="{embed_url}"></iframe>',
                {"http_status": 200, "final_url": url, "bytes": 100},
            )
        if url == embed_url:
            return (
                """
                <div id="section-list">
                  <ul class="list-group">
                    <li class="list-group-item">
                      <a href="/careers/msc/job/view/9812">Infrastructure Maintenance Officer</a>
                      <span>Location: Ballan</span>
                      <span>Job Type: Full Time</span>
                      <span>Closing Date: 21 May 2026</span>
                    </li>
                  </ul>
                </div>
                """,
                {"http_status": 200, "final_url": url, "bytes": 500},
            )
        raise AssertionError(url)

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 1
    job = payload["rows"][0]
    assert job["job_title"] == "Infrastructure Maintenance Officer"
    assert job["job_url"] == "https://moorabool.elmotalent.com.au/careers/msc/job/view/9812"
    assert job["source_job_id"] == "9812"
    assert job["location_text"] == "Ballan"
    assert job["work_type"] == "Full Time"
    assert job["closing_at"].startswith("2026-05-21")
    assert payload["source_results"][0]["parsed_jobs"] == 1


def test_job_intake_scrape_preview_extracts_elmo_icon_row_fields():
    listing_url = "https://cos.elmotalent.com.au/careers/cosjobs/jobs"
    registry = {
        "rows": [
            {
                "short_name": "Stonnington",
                "council_name": "Stonnington City Council",
                "council_grouping": "metropolitan",
                "poll_tier": "A",
                "platform_family": "elmo_talent",
                "monitoring_status": "ready",
                "listing_url": listing_url,
            },
        ]
    }

    def fetcher(url):
        assert url == listing_url
        return (
            """
            <div id="section-list">
              <ul class="list-group">
                <li class="list-group-item">
                  <div class="row">
                    <div class="col-md-8 col-sm-8 col-xs-12 break_word rt-editor">
                      <p><a href="/careers/cosjobs/job/view/1432">People &amp; Culture Business Partner</a></p>
                      <p>Work with senior leaders to shape people outcomes.</p>
                    </div>
                    <div class="col-md-4 col-sm-4 col-xs-12">
                      <div class="row"><div class="col-md-10 col-sm-10 col-xs-10">Stonnington City Centre + Working from home</div></div>
                      <div class="row"><div class="col-md-10 col-sm-10 col-xs-10">Permanent - Full Time</div></div>
                      <div class="row"><div class="col-md-10 col-sm-10 col-xs-10">15/05/2026</div></div>
                    </div>
                  </div>
                </li>
              </ul>
            </div>
            """,
            {"http_status": 200, "final_url": url, "bytes": 1000},
        )

    payload = job_intake_scrape_preview(registry_payload=registry, fetcher=fetcher, enrich_details=False)

    assert payload["summary"]["jobs"] == 1
    job = payload["rows"][0]
    assert job["job_title"] == "People & Culture Business Partner"
    assert job["job_url"] == "https://cos.elmotalent.com.au/careers/cosjobs/job/view/1432"
    assert job["source_job_id"] == "1432"
    assert job["location_text"] == "Stonnington City Centre + Working from home"
    assert job["work_type"] == "Permanent - Full Time"
    assert job["closing_at"].startswith("2026-05-15")
    assert job["description_text"] == "Work with senior leaders to shape people outcomes."


def test_job_intake_secondary_preview_extracts_sector_aggregator_cards():
    def fetcher(url):
        if "careersatcouncil" in url:
            return (
                """
                <a href="https://www.careersatcouncil.com.au/job/information-management-officer-20260511/" class="job-list">
                  <div class="job-list__title">Information Management Officer</div>
                  <div class="job-list__council">Manningham City Council</div>
                  <div class="job-list__location">Doncaster, Victoria</div>
                  <div class="job-list__tag">Full-time</div>
                  <div class="job-list__dates">Posted: 11 May<br>Closes: 24 May</div>
                </a>
                """,
                {"http_status": 200, "bytes": 100},
            )
        if "localgovernmentjobs" in url:
            return (
                """
                <li class="d-block fade-in-bottom">
                  <a href="https://www.localgovernmentjobs.com.au/job/volunteer-animal-shelter" class="iconbox-content">
                    <div class="post-main-title">Volunteer - Animal Shelter <span>Full Time</span></div>
                    <span>Victoria</span><span>Salary Competitive Monthly Based</span>
                  </a>
                </li>
                """,
                {"http_status": 200, "bytes": 100},
            )
        return ("<html></html>", {"http_status": 200, "bytes": 20})

    payload = job_intake_secondary_preview(fetcher=fetcher)

    assert payload["set_id"] == "job_intake_secondary_preview"
    assert payload["summary"]["sources_attempted"] == len(
        council_job_source_registry_payload()["secondary_sources"]
    )
    assert payload["summary"]["sources_with_jobs"] == 2
    assert payload["summary"]["jobs"] == 2
    first = next(row for row in payload["rows"] if row["source_family"] == "careersatcouncil")
    assert first["job_title"] == "Information Management Officer"
    assert first["council_name"] == "Manningham City Council"
    assert first["closing_at"].startswith("2026-05-24")
    assert first["is_canonical"] is False


def test_normalized_job_schema_extracts_posted_date_salary_and_standard_band_scope():
    job = normalize_council_job_record({
        "job_title": "Health Club Officer",
        "job_url": "https://ballarat.pulsesoftware.com/Pulse/job/28PA4g/Health-Club-Officer",
        "short_name": "Ballarat",
        "council_name": "Ballarat City Council",
        "source_family": "pulse",
        "posted_at_text": "11 May 2026",
        "closing_at_text": "9/08/2026 11:59 PM AUS Eastern Standard Time",
        "salary_text": "Hourly Rate AUD $33.29 - $35.38",
        "description_html": "<p><strong>Casual Opportunities - Band 3 Salary from $33.29 - $35.38 per hour</strong></p>",
    })

    assert job["schema_version"] == "council_job.v1"
    assert job["posted_at"].startswith("2026-05-11T00:00:00")
    assert job["closing_at"].startswith("2026-08-09T23:59:00")
    assert job["classification_band"] == "Band 3"
    assert job["standard_band_number"] == 3
    assert job["salary_min"] == 33.29
    assert job["salary_max"] == 35.38
    assert job["salary_period"] == "hour"
    assert job["advertised_salary_min"] == 33.29
    assert job["advertised_salary_max"] == 35.38
    assert job["advertised_salary_basis"] == "hourly"
    assert job["canonical_reference_month"] == "2026-05"
    assert job["canonical_reference_date_source"] == "posted_at"
    assert job["is_standard_band_1_to_8"] is True
    assert job["governance_status"] == "auto_included"


def test_normalized_job_schema_keeps_advertised_and_reference_lanes_explicit():
    job = normalize_council_job_record({
        "job_title": "Strategic Planner",
        "job_url": "https://example.test/jobs/strategic-planner",
        "fetched_at": "2026-05-12T06:48:13+00:00",
        "closing_at_text": "1 June 2026",
        "description_text": "Band 6A Salary AUD $100,440.08 per annum.",
    })

    assert job["classification_band"] == "Band 6"
    assert job["classification_band_raw"] == "Band 6A"
    assert job["standard_band_number"] == 6
    assert job["advertised_salary_min"] == 100440.08
    assert job["advertised_salary_basis"] == "annual"
    assert job["canonical_reference_date"] == "2026-05-12"
    assert job["canonical_reference_month"] == "2026-05"
    assert job["canonical_reference_date_source"] == "fetched_at"


def test_salary_parser_expands_k_salary_ranges():
    salary_text = extract_salary_text("Permanent Full time Opportunity $126k - $140k per annum plus Superannuation")

    assert salary_text == "$126k - $140k per annum plus Superannuation"
    assert extract_salary_range(salary_text) == {
        "salary_min": 126000.0,
        "salary_max": 140000.0,
        "salary_currency": "AUD",
        "salary_period": "year",
    }


def test_normalized_schema_extracts_benalla_application_deadline():
    job = normalize_council_job_record({
        "job_title": "School Crossing Supervisors",
        "job_url": "https://www.benalla.vic.gov.au/job-listing/school-crossing-supervisors/",
        "description_text": "Package Band 1 Applications addressing key selection should reach us by 5pm Monday 25 May 2026.",
    })

    assert job["classification_band"] == "Band 1"
    assert job["closing_at"].startswith("2026-05-25T17:00:00")


def test_normalized_schema_extracts_reference_number_from_detail_text():
    job = normalize_council_job_record({
        "job_title": "Occupational Health & Safety Coordinator",
        "job_url": "https://www.murrindindi.vic.gov.au/Council/Jobs-and-Tenders/Vacant-Positions/Occupational-Health-Safety-Coordinator",
        "detail_text": "Applications closing on 14 May 2026, 11:45 PM Reference Number SF/5421 Job Type Full Time Package Band 6 plus 12% Superannuation",
    })

    assert job["job_number"] == "SF/5421"
    assert job["source_job_id"] == "SF/5421"
    assert job["classification_band"] == "Band 6"
    assert job["standard_band_number"] == 6


def test_normalized_schema_extracts_bayside_month_first_closing_date():
    job = normalize_council_job_record({
        "job_title": "Domestic Cleaner",
        "job_url": "https://careers.bayside.vic.gov.au/jobs/domestic-cleaner",
        "description_text": "Part time Closing on: May 14 2026 Salary $32.36 p/h.",
    })

    assert job["closing_at"].startswith("2026-05-14T23:59:00")
    assert job["salary_min"] == 32.36
    assert job["salary_period"] == "hour"


def test_pay_table_enrichment_fills_enterprise_agreement_salary_when_job_has_band_only():
    job = normalize_council_job_record({
        "job_title": "Governance Officer",
        "job_url": "https://example.test/jobs/governance-officer",
        "short_name": "Example",
        "council_name": "Example Council",
        "fetched_at": "2026-05-12T00:00:00+00:00",
        "description_text": "Permanent full time Band 5 role.",
    })
    pay_rows = [
        {"canonical_lga_short_name": "Example", "effective_from": "2025-07-01", "to_date": "2026-06-30", "standard_band": "5", "weekly_rate": "$1,200"},
        {"canonical_lga_short_name": "Example", "effective_from": "2025-07-01", "to_date": "2026-06-30", "standard_band": "5", "weekly_rate": "$1,300"},
        {"canonical_lga_short_name": "Example", "effective_from": "2026-07-01", "standard_band": "5", "weekly_rate": 1500},
    ]

    enriched = enrich_job_with_pay_rows(job, pay_rows)

    assert enriched["salary_enrichment_status"] == "enterprise_agreement_salary_available"
    assert enriched["enterprise_agreement_salary_min"] == 62400
    assert enriched["enterprise_agreement_salary_max"] == 67600
    assert enriched["enterprise_agreement_salary_source"] == "governed_pay_tables"
    assert enriched["enterprise_agreement_salary_effective_from"] == "2025-07-01"
    assert enriched["enterprise_agreement_salary_effective_to"] == "2026-06-30"
    assert enriched["canonical_salary_min"] == 62400
    assert enriched["canonical_salary_max"] == 67600
    assert enriched["canonical_salary_source"] == "governed_pay_tables"


def test_pay_table_enrichment_does_not_use_other_councils_rows_when_council_is_missing():
    job = normalize_council_job_record({
        "job_title": "Principal Urban Designer",
        "job_url": "https://example.test/jobs/principal-urban-designer",
        "short_name": "Bayside",
        "council_name": "Bayside City Council",
        "fetched_at": "2026-05-22T00:00:00+00:00",
        "description_text": "Band 8 role. Salary $133,367 - $149,592 per annum.",
    })
    pay_rows = [
        {"canonical_lga_short_name": "Campaspe", "agreement_name": "Campaspe Shire Council Enterprise Agreement 2025", "effective_from": "2026-02-16", "to_date": "2027-02-15", "standard_band": "8", "weekly_rate": 2516.35},
        {"canonical_lga_short_name": "Campaspe", "agreement_name": "Campaspe Shire Council Enterprise Agreement 2025", "effective_from": "2026-02-16", "to_date": "2027-02-15", "standard_band": "8", "weekly_rate": 2816.92},
    ]

    enriched = enrich_job_with_pay_rows(job, pay_rows)

    assert enriched["salary_enrichment_status"] == "no_band_comparator"
    assert "enterprise_agreement_salary_min" not in enriched
    assert enriched["salary_band_validation_status"] == "no_comparator"


def test_pay_table_enrichment_infers_candidate_band_when_job_has_salary_only():
    job = normalize_council_job_record({
        "job_title": "Governance Officer",
        "job_url": "https://example.test/jobs/governance-officer",
        "short_name": "Example",
        "council_name": "Example Council",
        "salary_text": "$62,400 - $67,600 per annum",
    })
    pay_rows = [
        {"canonical_lga_short_name": "Example", "effective_from": "2026-07-01", "standard_band": "4", "weekly_rate": 1000},
        {"canonical_lga_short_name": "Example", "effective_from": "2026-07-01", "standard_band": "5", "weekly_rate": 1200},
        {"canonical_lga_short_name": "Example", "effective_from": "2026-07-01", "standard_band": "5", "weekly_rate": 1300},
    ]

    enriched = enrich_job_with_pay_rows(job, pay_rows)

    assert enriched["band_inference_status"] == "candidate_bands_from_salary"
    assert enriched["inferred_standard_band_number"] == 5
    assert enriched["governance_status"] == "needs_band_confirmation"


def test_normalized_schema_does_not_treat_unlabelled_pdf_numbers_as_salary():
    job = normalize_council_job_record({
        "job_title": "Coordinator Management Accounting",
        "job_url": "https://example.test/jobs/15074",
        "short_name": "Boroondara",
        "council_name": "Boroondara City Council",
        "position_description_text": "CLASSIFICATION: Band 8 Budget adopted by 30 June. Manage 16 departments and 170000 residents.",
    })

    assert job["classification_band"] == "Band 8"
    assert "salary_min" not in job
    assert job["governance_status"] == "auto_included"


def test_normalized_schema_keeps_paid_unknown_band_roles_in_review():
    job = normalize_council_job_record({
        "job_title": "Executive Assistant",
        "job_url": "https://example.test/jobs/executive-assistant",
        "description_text": "Work with contractors and senior leaders. Salary $78,000 per annum.",
    })

    assert job["governance_status"] == "needs_band_review"
    assert job["salary_min"] == 78000


def test_linked_position_description_pdf_becomes_schema_evidence():
    pdf_bytes = _pdf_bytes_with_text(
        "Position Description\n"
        "Classification: Band 6\n"
        "Salary: $103,897.99 - $116,244.43 per annum plus superannuation\n"
    )
    detail_url = "https://career10.successfactors.com/sfcareer/jobreqcareer?company=cityofboroP&jobId=15074"
    pdf_url = "https://forms.boroondara.vic.gov.au/index.php?gf-download=2026/05/PD-Finance-Coordinator.pdf&form-id=146"
    source = {
        "short_name": "Boroondara",
        "council_name": "Boroondara City Council",
        "council_grouping": "metropolitan",
        "platform_family": "successfactors",
        "listing_url": "https://www.boroondara.vic.gov.au/jobs",
    }
    job = {
        "job_title": "Coordinator Management Accounting",
        "job_url": detail_url,
        "short_name": "Boroondara",
        "council_name": "Boroondara City Council",
        "source_family": "successfactors",
    }

    def binary_fetcher(url):
        assert url == canonicalize_job_url(pdf_url)
        return pdf_bytes, {"http_status": 200, "content_type": "application/pdf", "bytes": len(pdf_bytes)}

    enriched = enrich_job_from_detail_page(
        job,
        source,
        f'<a href="{pdf_url}">Position Description</a>',
        binary_fetcher=binary_fetcher,
    )
    normalized = normalize_council_job_record(enriched)

    assert normalized["position_description_url"] == canonicalize_job_url(pdf_url)
    assert normalized["attachments"][0]["parse_status"] == "parsed"
    assert normalized["classification_band"] == "Band 6"
    assert normalized["field_sources"]["classification_band"] == "position_description_pdf"
    assert normalized["salary_min"] == 103897.99
    assert normalized["salary_max"] == 116244.43
    assert normalized["salary_period"] == "year"
    assert normalized["governance_status"] == "auto_included"


def test_position_description_gateway_pdf_becomes_schema_evidence():
    pdf_bytes = _pdf_bytes_with_text(
        "Position Description\n"
        "Classification: Band 2\n"
        "Salary: $32.36 per hour\n"
    )
    detail_url = "https://careers.bayside.vic.gov.au/jobs/domestic-cleaner"
    gateway_url = "https://secure.dc2.pageuppeople.com/apply/1139/gateway/default.aspx?sData=abc123"
    job = {
        "job_title": "Domestic Cleaner",
        "job_url": detail_url,
        "short_name": "Bayside",
        "council_name": "Bayside City Council",
        "source_family": "native_council_custom",
    }

    def binary_fetcher(url):
        assert url == gateway_url
        return pdf_bytes, {
            "http_status": 200,
            "final_url": "https://secure.dc2.pageuppeople.com/apply/1139/applicationForm/TransferFile.ashx?sData=abc123",
            "content_type": "application/pdf",
            "bytes": len(pdf_bytes),
        }

    enriched = enrich_job_from_detail_page(
        job,
        {"listing_url": "https://careers.bayside.vic.gov.au/jobs/search"},
        f'<a href="{gateway_url}">Position Description</a>',
        binary_fetcher=binary_fetcher,
    )
    normalized = normalize_council_job_record(enriched)

    assert normalized["position_description_url"] == gateway_url
    assert normalized["attachments"][0]["parse_status"] == "parsed"
    assert normalized["classification_band"] == "Band 2"
    assert normalized["salary_period"] == "hour"
    assert normalized["governance_status"] == "auto_included"


def test_scrape_preview_fetches_position_description_pdf_even_when_detail_has_band():
    pdf_bytes = _pdf_bytes_with_text(
        "Position Description\n"
        "Classification: Band 8\n"
        "Total remuneration package $119.2K to $133.3K plus superannuation\n"
    )
    listing_url = "https://careers.mitchellshire.vic.gov.au/jobs/search"
    detail_url = "https://careers.mitchellshire.vic.gov.au/jobs/ict-coordinator-melbourne-vic-australia"
    gateway_url = "https://secure.dc2.pageuppeople.com/apply/838/gateway/default.aspx?sData=abc123"
    registry = {
        "rows": [
            {
                "short_name": "Mitchell",
                "council_name": "Mitchell Shire Council",
                "council_grouping": "large_shire",
                "poll_tier": "B",
                "platform_family": "native_council_custom",
                "monitoring_status": "ready",
                "listing_url": listing_url,
                "detail_pattern": "/jobs/{slug}",
            },
        ]
    }

    def fetcher(url):
        if url == listing_url:
            return (f'<a href="{detail_url}">ICT Coordinator</a>', {"http_status": 200, "bytes": 100})
        if url == detail_url:
            return (
                f'''
                <p>The total remuneration package on offer is $119.2K to $133.3K (Band 8) plus superannuation.</p>
                <a href="{gateway_url}">Position Description</a>
                ''',
                {"http_status": 200, "bytes": 100},
            )
        raise AssertionError(f"unexpected url {url}")

    def binary_fetcher(url):
        assert url == gateway_url
        return pdf_bytes, {
            "http_status": 200,
            "final_url": "https://secure.dc2.pageuppeople.com/apply/838/applicationForm/TransferFile.ashx?sData=abc123",
            "content_type": "application/pdf",
            "bytes": len(pdf_bytes),
        }

    payload = job_intake_scrape_preview(
        registry_payload=registry,
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
    )

    row = payload["rows"][0]
    assert row["classification_band"] == "Band 8"
    assert row["position_description_text_source"] == "position_description_pdf"
    assert row["attachments"][0]["parse_status"] == "parsed"
    assert payload["summary"]["linked_document_enrichment_attempted"] == 1
    assert payload["summary"]["linked_documents_parsed"] == 1


def test_linked_position_description_docx_becomes_schema_evidence():
    docx_bytes = _docx_bytes_with_text(
        "Position Description\n"
        "Classification: Band 4\n"
        "Salary: $82,000 - $88,000 per annum\n"
    )
    detail_url = "https://www.benalla.vic.gov.au/job-listing/school-crossing-supervisors/"
    docx_url = "https://www.benalla.vic.gov.au/files/Position-Description-Information-Pack.docx"
    job = {
        "job_title": "School Crossing Supervisors",
        "job_url": detail_url,
        "short_name": "Benalla",
        "council_name": "Benalla Rural City Council",
        "source_family": "native_council",
    }

    def binary_fetcher(url):
        assert url == docx_url
        return docx_bytes, {
            "http_status": 200,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "bytes": len(docx_bytes),
        }

    enriched = enrich_job_from_detail_page(
        job,
        {"listing_url": "https://www.benalla.vic.gov.au/council/careers-at-council/positions-vacant/"},
        f'<a href="{docx_url}">Position Description</a>',
        binary_fetcher=binary_fetcher,
    )
    normalized = normalize_council_job_record(enriched)

    assert normalized["attachments"][0]["document_kind"] == "docx"
    assert normalized["attachments"][0]["parse_status"] == "parsed"
    assert normalized["classification_band"] == "Band 4"
    assert normalized["field_sources"]["classification_band"] == "position_description_docx"
    assert normalized["salary_min"] == 82000
    assert normalized["salary_max"] == 88000
    assert normalized["governance_status"] == "auto_included"


def test_docx_information_pack_links_are_attachment_candidates():
    links = extract_attachment_links_from_html(
        '<a href="/files/Casual-School-Crossing-Information-Pack.docx">Information Pack</a>',
        "https://www.benalla.vic.gov.au/job-listing/school-crossing-supervisors/",
    )

    assert len(links) == 1
    assert links[0]["url"] == "https://www.benalla.vic.gov.au/files/Casual-School-Crossing-Information-Pack.docx"
    assert links[0]["kind"] == "job_attachment"
    assert links[0]["content_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_embedded_document_urls_are_attachment_candidates():
    pdf_url = "https://forms.boroondara.vic.gov.au/index.php?gf-download=2026%2F05%2FPD-CT-Data-Visualisation-Specialist-.pdf&form-id=146"

    links = extract_attachment_links_from_html(
        f'<script>window.jobDocument="{pdf_url}"</script>',
        "https://career10.successfactors.com/sfcareer/jobreqcareer?company=cityofboroP&jobId=15071",
    )

    assert len(links) == 1
    assert links[0]["url"] == canonicalize_job_url(pdf_url)
    assert links[0]["kind"] == "position_description"


def test_aurion_recadvert_links_are_normalized_to_portal_file_endpoint():
    links = extract_attachment_links_from_html(
        '<a href="file/recadvert/T303~|~2912315474772099~1~|~00H2MEO7RZ1FDPFC~|~PDF~|~2~|~Position Description - 1514 - Business Systems Officer.pdf">Position Description - 1514 - Business Systems Officer.pdf</a>',
        "https://candidate.aurion.cloud/wangaratta/production/vacancies/2912315474772099~1/edit",
    )

    assert len(links) == 1
    assert links[0]["url"] == (
        "https://candidate.aurion.cloud/wangaratta/production/file/recadvert/"
        "T303~|~2912315474772099~1~|~00H2MEO7RZ1FDPFC~|~PDF~|~2~|~"
        "Position Description - 1514 - Business Systems Officer.pdf"
    )
    assert links[0]["kind"] == "position_description"
    assert links[0]["content_type"] == "application/pdf"


def test_scrape_preview_can_enrich_successfactors_jobs_from_linked_pdfs():
    pdf_bytes = _pdf_bytes_with_text(
        "Classification Band 6\n"
        "Salary range $103,897.99 - $116,244.43 per annum\n"
    )
    listing_url = "https://www.boroondara.vic.gov.au/your-council/jobs-and-careers/view-current-job-vacancies"
    detail_url = "https://career10.successfactors.com/sfcareer/jobreqcareer?company=cityofboroP&jobId=15074"
    pdf_url = "https://forms.boroondara.vic.gov.au/index.php?gf-download=2026/05/PD-Finance-Coordinator.pdf&form-id=146"
    registry = {
        "rows": [
            {
                "short_name": "Boroondara",
                "council_name": "Boroondara City Council",
                "council_grouping": "metropolitan",
                "poll_tier": "A",
                "platform_family": "successfactors",
                "monitoring_status": "ready",
                "listing_url": listing_url,
            },
        ]
    }

    def fetcher(url):
        if url == listing_url:
            return (f'<a href="{detail_url}">Coordinator Management Accounting</a>', {"http_status": 200, "bytes": 100})
        if url == canonicalize_job_url(detail_url):
            return (f'<a href="{pdf_url}">Position Description</a>', {"http_status": 200, "bytes": 100})
        raise AssertionError(f"unexpected url {url}")

    def binary_fetcher(url):
        assert url == canonicalize_job_url(pdf_url)
        return pdf_bytes, {"http_status": 200, "content_type": "application/pdf", "bytes": len(pdf_bytes)}

    payload = job_intake_scrape_preview(
        registry_payload=registry,
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
        enrich_attachments=True,
    )

    row = payload["rows"][0]
    assert row["classification_band"] == "Band 6"
    assert row["salary_min"] == 103897.99
    assert row["field_sources"]["salary_text"] == "position_description_pdf"
    assert payload["summary"]["linked_document_enrichment_attempted"] == 1
    assert payload["summary"]["linked_documents_parsed"] == 1


def test_scrape_preview_resolves_missing_band_from_one_level_down_document_by_default():
    pdf_bytes = _pdf_bytes_with_text(
        "Position Description\n"
        "Classification: Band 8\n"
        "Salary range $132,478 - $148,328 per annum\n"
    )
    listing_url = "https://www.boroondara.vic.gov.au/your-council/jobs-and-careers/view-current-job-vacancies"
    detail_url = "https://career10.successfactors.com/sfcareer/jobreqcareer?company=cityofboroP&jobId=15071"
    pdf_url = "https://forms.boroondara.vic.gov.au/index.php?gf-download=2026/05/PD-CT-Data-Visualisation-Specialist-.pdf&form-id=146"
    registry = {
        "rows": [
            {
                "short_name": "Boroondara",
                "council_name": "Boroondara City Council",
                "council_grouping": "metropolitan",
                "poll_tier": "A",
                "platform_family": "successfactors",
                "monitoring_status": "ready",
                "listing_url": listing_url,
            },
        ]
    }

    def fetcher(url):
        if url == listing_url:
            return (f'<a href="{detail_url}">Data Visualisation Specialist</a>', {"http_status": 200, "bytes": 100})
        if url == canonicalize_job_url(detail_url):
            return (
                f'<p>$132,478 - $148,328 pa</p><p>Review the <a href="{pdf_url}">position description</a>.</p>',
                {"http_status": 200, "bytes": 100},
            )
        raise AssertionError(f"unexpected url {url}")

    def binary_fetcher(url):
        assert url == canonicalize_job_url(pdf_url)
        return pdf_bytes, {"http_status": 200, "content_type": "application/pdf", "bytes": len(pdf_bytes)}

    payload = job_intake_scrape_preview(
        registry_payload=registry,
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
    )

    row = payload["rows"][0]
    assert row["classification_band"] == "Band 8"
    assert row["salary_min"] == 132478
    assert row["field_sources"]["classification_band"] == "position_description_pdf"
    assert payload["scope"]["linked_document_enrichment"] == "missing_governance_only"
    assert payload["summary"]["linked_document_enrichment_attempted"] == 1
    assert payload["summary"]["linked_documents_parsed"] == 1


def test_scrape_preview_resolves_aurion_band_from_recadvert_pdf():
    pdf_bytes = _pdf_bytes_with_text(
        "Position Description\n"
        "Classification Band 5\n"
        "Salary $76,232 per annum\n"
    )
    listing_url = "https://candidate.aurion.cloud/wangaratta/production/"
    detail_url = "https://candidate.aurion.cloud/wangaratta/production/vacancies/2912315474772099~1/edit"
    normalized_pdf_url = (
        "https://candidate.aurion.cloud/wangaratta/production/file/recadvert/"
        "T303~|~2912315474772099~1~|~00H2MEO7RZ1FDPFC~|~PDF~|~2~|~"
        "Position Description - 1514 - Business Systems Officer.pdf"
    )
    registry = {
        "rows": [
            {
                "short_name": "Wangaratta",
                "council_name": "Rural City of Wangaratta",
                "council_grouping": "regional_city",
                "poll_tier": "A",
                "platform_family": "aurion_selfservice",
                "monitoring_status": "ready",
                "listing_url": listing_url,
            },
        ]
    }

    def fetcher(url):
        if url == listing_url:
            return (
                f'''
                <table><tr id="2912315474772099~1" data-url="/wangaratta/production/vacancies/2912315474772099~1/edit">
                  <td data-th="Position">Business Systems Officer</td>
                </tr></table>
                ''',
                {"http_status": 200, "bytes": 100},
            )
        if url == detail_url:
            return (
                '''
                <p>$76,232 per annum + super</p>
                <a href="file/recadvert/T303~|~2912315474772099~1~|~00H2MEO7RZ1FDPFC~|~PDF~|~2~|~Position Description - 1514 - Business Systems Officer.pdf">
                  Position Description - 1514 - Business Systems Officer.pdf
                </a>
                ''',
                {"http_status": 200, "bytes": 100},
            )
        raise AssertionError(f"unexpected url {url}")

    def binary_fetcher(url):
        assert url == normalized_pdf_url
        return pdf_bytes, {"http_status": 200, "content_type": "application/pdf", "bytes": len(pdf_bytes)}

    payload = job_intake_scrape_preview(
        registry_payload=registry,
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
    )

    row = payload["rows"][0]
    assert row["classification_band"] == "Band 5"
    assert row["salary_min"] == 76232
    assert row["governance_status"] == "auto_included"
    assert row["position_description_text_source"] == "position_description_pdf"


def _pdf_bytes_with_text(text):
    import pytest

    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes_with_text(text):
    from io import BytesIO
    from html import escape
    import zipfile

    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>"
        for line in text.splitlines()
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body>"
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()
