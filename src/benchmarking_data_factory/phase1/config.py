from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / 'data'
BRONZE_ROOT = DATA_ROOT / 'bronze' / 'phase1_source_build'
RULES_ROOT = PROJECT_ROOT / 'phase1_rules'
REGISTERS_ROOT = PROJECT_ROOT / 'registers'
DOCS_INCOMING = PROJECT_ROOT / 'documents' / 'incoming'
DOCS_IMMUTABLE = PROJECT_ROOT / 'documents' / 'immutable'

FWC_REGISTRY_RANGE = ('A', 5, 'Z', 10000)
ABS_LGA_URL = 'https://geo.abs.gov.au/arcgis/rest/services/ASGS2025/LGA/MapServer/0/query'
ABS_LGA_QUERY = {
    'where': '1=1',
    'returnGeometry': 'false',
    'outFields': '*',
    'f': 'json',
}

FETCH_HASH_LOG = REGISTERS_ROOT / 'fetch-hash-log.csv'
DOCUMENT_REGISTER = REGISTERS_ROOT / 'document-register.csv'
SOURCE_DOCUMENT_REGISTER = REGISTERS_ROOT / 'source-document-register.csv'
