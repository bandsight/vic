from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import requests
from fastapi.testclient import TestClient
from benchmarking_data_factory.phase1.pipeline import (
    build_victorian_lga_base,
    canonicalise_registry_rows,
    classify_and_match_registry_rows,
    fetch_registry_workbook,
    freeze_http_binary,
)


HEADER_RULES = {
    'title': ['Agreement Title', 'Title'],
    'agreement_id': ['Agreement ID', 'Agmnt ID'],
    'matter_number': ['Matter Number', 'Matter No'],
    'operative_date': ['Operative Date'],
    'expiry_date': ['Expiry Date'],
    'industry': ['Industry'],
    'version': ['Version'],
    'print_id': ['Print ID'],
}

MATCH_RULES = {
    'excluded_abs_lga_codes': ['29799', '29499', '29399'],
    'canonical_alias_overrides': [
        {
            'council': 'Merri-bek',
            'alias_type': 'rename_alias',
            'binds_when_present': [
                'merri-bek',
                'merri bek',
                'moreland',
                'moreland city council',
                'city of moreland',
                'moreland city',
            ],
        }
    ],
    'contradictions': [
        {
            'lga_short_name': 'Wyndham',
            'contradiction_phrase': 'east kimberley',
            'active_flag': True,
        }
    ],
    'specialist_keywords': ['nurse'],
    'shared_keywords': ['single interest'],
    'excluded_phrases': ['ventia'],
    'civic_context_phrases': ['council', 'shire council', 'city of'],
}


class Phase1PipelineTests(unittest.TestCase):
    def test_freeze_http_binary_retries_fwc_ssl_without_verification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / 'agreements2026.xlsx'
            first_error = requests.exceptions.SSLError('local issuer certificate')

            class Response:
                content = b'xlsx bytes'

                def raise_for_status(self):
                    return None

            with patch(
                'benchmarking_data_factory.phase1.pipeline.requests.get',
                side_effect=[first_error, Response()],
            ) as mocked_get, patch('benchmarking_data_factory.phase1.pipeline.log_fetch_hash'):
                result = freeze_http_binary(
                    'https://www.fwc.gov.au/documents/agreements/resources/agreements2026.xlsx',
                    target,
                    'agreements2026.xlsx',
                    'fwc_registry_2026',
                    'unit test',
                )

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), b'xlsx bytes')
        self.assertEqual(mocked_get.call_count, 2)
        self.assertTrue(mocked_get.call_args_list[1].kwargs['verify'] is False)

    def test_force_registry_does_not_silently_reuse_stale_cache_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bronze_root = Path(tmpdir)
            cached = bronze_root / 'fwc_registry' / 'agreements2026.xlsx'
            cached.parent.mkdir(parents=True)
            cached.write_bytes(b'old cache')
            year_ctx = {
                'published_year': 2026,
                'registry_url': 'https://www.fwc.gov.au/documents/agreements/resources/agreements2026.xlsx',
            }
            with patch('benchmarking_data_factory.phase1.pipeline.BRONZE_ROOT', bronze_root), patch(
                'benchmarking_data_factory.phase1.pipeline.freeze_http_binary',
                side_effect=requests.RequestException('network down'),
            ):
                with self.assertRaises(requests.RequestException):
                    fetch_registry_workbook(year_ctx, force_refresh=True)

    def test_header_harmonisation_builds_pdf_url(self):
        rows = [
            {
                'AGREEMENT TITLE': 'Example Shire Council Enterprise Agreement 2024',
                'Agmnt ID': 'AE123456',
                'Matter No': 'AG2024/1',
                'Operative Date': '45678',
                'Expiry Date': '46000',
                'INDUSTRY': 'Local Government Administration',
            }
        ]
        out = canonicalise_registry_rows(rows, {'published_year': 2024, 'registry_url': 'https://example.test/agreements2024.xlsx'}, HEADER_RULES)
        self.assertEqual(out[0]['Agreement ID'], 'AE123456')
        self.assertEqual(out[0]['agreement_id_status'], 'resolved')
        self.assertEqual(out[0]['pdf_url'], 'https://www.fwc.gov.au/documents/agreements/approved/ae123456.pdf')

    def test_victorian_lga_base_excludes_non_victoria_and_abs_exclusions(self):
        rows = [
            {'lga_name': 'Wyndham (C)', 'lga_code': '12345', 'state_name': 'Victoria', 'as_of_year': 2025},
            {'lga_name': 'Excluded Example', 'lga_code': '29799', 'state_name': 'Victoria', 'as_of_year': 2025},
            {'lga_name': 'Sydney', 'lga_code': '99999', 'state_name': 'New South Wales', 'as_of_year': 2025},
        ]
        out = build_victorian_lga_base(rows, MATCH_RULES)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['lga_short_name'], 'Wyndham')

    def test_title_only_evidence_remains_unresolved_scope(self):
        registry_rows = [
            {
                'Agreement Title': 'Example Shire Council Enterprise Agreement 2024',
                'Agreement ID': 'AE100001',
                'Matter Number': '',
                'Operative Date': '45678',
                'Expiry Date': '',
                'Industry': 'Miscellaneous',
                'published_year': 2024,
                'pdf_url': 'https://www.fwc.gov.au/documents/agreements/approved/ae100001.pdf',
                'agreement_id_status': 'resolved',
                'agreement_id_source_field': 'Agreement ID',
            }
        ]
        lgas = [
            {
                'lga_name': 'Example Shire Council',
                'lga_code': '11111',
                'state_name': 'Victoria',
                'as_of_year': 2025,
                'lga_original_name': 'Example Shire Council',
                'lga_short_name': 'Example',
            }
        ]
        out = classify_and_match_registry_rows(registry_rows, lgas, MATCH_RULES)
        self.assertEqual(out[0]['scope_resolution_status'], 'title_only_unresolved')
        self.assertEqual(out[0]['likely_most_current'], 'likely_current')
        self.assertEqual(out[0]['match_strength'], 'civic_strong')

    def test_plain_place_name_without_civic_context_does_not_match(self):
        registry_rows = [
            {
                'Agreement Title': 'Melbourne Metro Tunnel Agreement',
                'Agreement ID': 'AE299999',
                'Matter Number': '',
                'Operative Date': '45678',
                'Expiry Date': '',
                'Industry': 'Miscellaneous',
                'published_year': 2024,
                'pdf_url': '',
                'agreement_id_status': 'resolved',
                'agreement_id_source_field': 'Agreement ID',
            }
        ]
        lgas = [
            {
                'lga_name': 'Melbourne City Council',
                'lga_code': '33333',
                'state_name': 'Victoria',
                'as_of_year': 2025,
                'lga_original_name': 'Melbourne City Council',
                'lga_short_name': 'Melbourne',
            }
        ]
        out = classify_and_match_registry_rows(registry_rows, lgas, MATCH_RULES)
        self.assertEqual(out, [])

    def test_misc_without_civic_wording_is_excluded(self):
        registry_rows = [
            {
                'Agreement Title': 'Melbourne Metro Tunnel Agreement',
                'Agreement ID': 'AE399999',
                'Matter Number': '',
                'Operative Date': '45678',
                'Expiry Date': '',
                'Industry': 'Miscellaneous',
                'published_year': 2024,
                'pdf_url': '',
                'agreement_id_status': 'resolved',
                'agreement_id_source_field': 'Agreement ID',
            }
        ]
        lgas = [
            {
                'lga_name': 'Melbourne City Council',
                'lga_code': '33333',
                'state_name': 'Victoria',
                'as_of_year': 2025,
                'lga_original_name': 'Melbourne City Council',
                'lga_short_name': 'Melbourne',
            }
        ]
        out = classify_and_match_registry_rows(registry_rows, lgas, MATCH_RULES)
        self.assertEqual(out, [])

    def test_contradiction_rule_blocks_weak_match(self):
        registry_rows = [
            {
                'Agreement Title': 'East Kimberley Wyndham Council Agreement',
                'Agreement ID': 'AE200002',
                'Matter Number': '',
                'Operative Date': '45678',
                'Expiry Date': '',
                'Industry': 'Miscellaneous',
                'published_year': 2024,
                'pdf_url': '',
                'agreement_id_status': 'resolved',
                'agreement_id_source_field': 'Agreement ID',
            }
        ]
        lgas = [
            {
                'lga_name': 'Wyndham City Council',
                'lga_code': '22222',
                'state_name': 'Victoria',
                'as_of_year': 2025,
                'lga_original_name': 'Wyndham City Council',
                'lga_short_name': 'Wyndham',
            }
        ]
        out = classify_and_match_registry_rows(registry_rows, lgas, MATCH_RULES)
        self.assertEqual(out[0]['matched_lga_count'], 0)
        self.assertEqual(out[0]['lga_short_name'], '')

    def test_rename_alias_matches_moreland_to_merri_bek(self):
        registry_rows = [
            {
                'Agreement Title': 'Moreland City Council Enterprise Agreement 2021 (EA 2021)',
                'Agreement ID': 'AE516530',
                'Matter Number': '',
                'Operative Date': '44757',
                'Expiry Date': '45838',
                'Industry': 'Local government administration',
                'published_year': 2022,
                'pdf_url': 'https://www.fwc.gov.au/documents/agreements/approved/ae516530.pdf',
                'agreement_id_status': 'resolved',
                'agreement_id_source_field': 'Agreement ID',
            }
        ]
        lgas = [
            {
                'lga_name': 'Merri-bek',
                'lga_code': '24700',
                'state_name': 'Victoria',
                'as_of_year': 2025,
                'lga_original_name': 'Merri-bek',
                'lga_short_name': 'Merri-bek',
            }
        ]

        out = classify_and_match_registry_rows(registry_rows, lgas, MATCH_RULES)

        self.assertEqual(out[0]['matched_lga_names'], 'Merri-bek')
        self.assertEqual(out[0]['lga_short_name'], 'Merri-bek')
        self.assertEqual(out[0]['match_strength'], 'civic_strong')
        self.assertEqual(out[0]['scope_resolution_status'], 'rename_alias_resolved')


class MultiCouncilHelpersTests(unittest.TestCase):
    def test_lga_slug_lowercases_and_underscores(self):
        self.assertEqual(main.lga_slug('Central Goldfields'), 'central_goldfields')
        self.assertEqual(main.lga_slug('Ararat'), 'ararat')
        self.assertEqual(main.lga_slug('  Mornington Peninsula  '), 'mornington_peninsula')

    def test_sha256_file_returns_64_char_hex(self):
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(b'hello world')
            path = Path(f.name)
        try:
            h = main.sha256_file(path)
            self.assertEqual(len(h), 64)
            self.assertTrue(all(c in '0123456789abcdef' for c in h))
            self.assertEqual(h, 'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9')
        finally:
            path.unlink()

    def test_load_canonical_councils_returns_79(self):
        councils = main.load_canonical_councils()
        self.assertGreaterEqual(len(councils), 78)
        self.assertTrue(all('short_name' in c for c in councils))
        names = {c['short_name'] for c in councils}
        self.assertIn('Ararat', names)
        self.assertIn('Central Goldfields', names)

    def test_reference_councils_endpoint_returns_first_class_payload(self):
        response = TestClient(main.app).get('/api/reference/councils')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['set_id'], 'canonical_councils')
        self.assertGreaterEqual(body['summary']['total'], 78)
        self.assertEqual(body['summary']['total'], len(body['rows']))
        self.assertIn('ARARAT', body['lookup'])
        self.assertEqual(body['lookup']['ARARAT']['long_name'], 'Ararat Rural City Council')
        self.assertEqual(body['lookup']['ARARAT']['council_category'], 'Small shire')
        self.assertEqual(body['summary']['categories']['Metropolitan'], 22)

    def test_reference_council_master_endpoint_returns_dimension_payload(self):
        response = TestClient(main.app).get('/api/reference/council-master')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['set_id'], 'victorian_council_master')
        self.assertEqual(body['summary']['councils'], 79)
        self.assertEqual(body['summary']['coverage']['vec'], 79)
        self.assertIn('BALLARAT', body['lookup'])
        self.assertEqual(body['lookup']['BALLARAT']['vif_regional_partnership'], 'Central Highlands')

    def test_reference_council_job_sources_endpoint_returns_registry_payload(self):
        response = TestClient(main.app).get('/api/reference/council-job-sources')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['set_id'], 'victorian_council_jobs_source_registry')
        self.assertEqual(body['summary']['councils'], 79)
        self.assertEqual(body['summary']['poll_tiers'], {'A': 41, 'B': 19, 'C': 19})
        self.assertIn('restricted_sources', body)
        self.assertEqual(
            {source['source_id'] for source in body['restricted_sources']},
            {'indeed', 'linkedin', 'seek'},
        )

    def test_victorian_lga_base_preserves_greater_prefix(self):
        rows = [{
            'lga_name': 'Greater Bendigo',
            'lga_code': '325',
            'state_name': 'Victoria',
        }]
        result = build_victorian_lga_base(rows, MATCH_RULES)
        self.assertEqual(result[0]['lga_short_name'], 'Greater Bendigo')

    def test_resolve_lga_falls_back_to_original_when_short_name_is_stripped(self):
        meta = {
            'matched_lga_names': 'Bendigo',
            'lga_short_name': 'Bendigo',
            'lga_original_name': 'Greater Bendigo',
        }
        self.assertEqual(main.resolve_canonical_lga_short_name('ae-test', meta, {}), 'Greater Bendigo')

    def test_record_and_load_multi_council_decision_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            register = Path(tmpdir) / 'multi-council-decisions.csv'
            with patch.object(main, 'MULTI_COUNCIL_REGISTER', register):
                main._multi_council_cache = None
                main.record_multi_council_decision(
                    ae_id='ae999999',
                    is_multi=True,
                    lgas_assigned=['Ararat', 'Central Goldfields'],
                    parent_content_hash='a' * 64,
                    split_files=['ae999999__ararat.pdf', 'ae999999__central_goldfields.pdf'],
                    notes='unit test',
                )
                main._multi_council_cache = None
                loaded = main.load_multi_council_decisions()
            self.assertIn('ae999999', loaded)
            row = loaded['ae999999']
            self.assertTrue(row['is_multi'])
            self.assertEqual(row['lgas_assigned'], ['Ararat', 'Central Goldfields'])
            self.assertEqual(row['split_files'], ['ae999999__ararat.pdf', 'ae999999__central_goldfields.pdf'])
            self.assertEqual(row['parent_content_hash'], 'a' * 64)

    def test_record_replaces_existing_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            register = Path(tmpdir) / 'multi-council-decisions.csv'
            with patch.object(main, 'MULTI_COUNCIL_REGISTER', register):
                main._multi_council_cache = None
                main.record_multi_council_decision('ae888888', True, ['Ararat'], 'x' * 64, ['ae888888__ararat.pdf'], 'v1')
                main._multi_council_cache = None
                main.record_multi_council_decision('ae888888', False, ['Ararat'], 'y' * 64, [], 'v2')
                main._multi_council_cache = None
                loaded = main.load_multi_council_decisions()
            self.assertEqual(len(loaded), 1)
            self.assertFalse(loaded['ae888888']['is_multi'])
            self.assertEqual(loaded['ae888888']['notes'], 'v2')

    def test_api_councils_materialises_yaml_split_rows(self):
        decisions = {
            'ae999999': {
                'ae_id': 'ae999999',
                'is_multi': True,
                'lgas_assigned': ['Ararat', 'Central Goldfields'],
                'parent_content_hash': 'a' * 64,
                'split_files': ['ae999999__ararat.yaml', 'ae999999__central_goldfields.yaml'],
                'decided_by': 'human-ui',
                'decided_at': '2026-04-26T00:00:00+00:00',
                'notes': '',
            }
        }
        with patch.object(main, 'load_registry', return_value={'ae999999': 'Parent multi-council agreement'}), \
             patch.object(main, 'list_pdfs', return_value=['ae999999']), \
             patch.object(main, 'load_multi_council_decisions', return_value=decisions), \
             patch.object(main, 'load_source_register_by_ae_id', return_value={}):
            rows = main.api_councils(False)

        ids = {row['ae_id'] for row in rows}
        self.assertNotIn('ae999999', ids)
        self.assertIn('ae999999__ararat', ids)
        self.assertIn('ae999999__central_goldfields', ids)
        split_rows = [row for row in rows if row['ae_id'].startswith('ae999999__')]
        self.assertTrue(all(row['is_split_row'] for row in split_rows))

    def test_find_pdf_falls_back_to_parent_for_split_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            immutable = Path(tmpdir)
            parent_pdf = immutable / 'ae999999.pdf'
            parent_pdf.write_bytes(b'%PDF-1.4\n')
            with patch.object(main, 'IMMUTABLE_DIR', immutable):
                self.assertEqual(main.find_pdf('ae999999__ararat'), parent_pdf)


if __name__ == '__main__':
    unittest.main()
