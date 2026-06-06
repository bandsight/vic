from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET

import requests
import yaml

from .config import (
    ABS_LGA_QUERY,
    ABS_LGA_URL,
    BRONZE_ROOT,
    DOCS_IMMUTABLE,
    DOCS_INCOMING,
    DOCUMENT_REGISTER,
    FETCH_HASH_LOG,
    FWC_REGISTRY_RANGE,
    PROJECT_ROOT,
    RULES_ROOT,
    SOURCE_DOCUMENT_REGISTER,
)


@dataclass
class FetchArtifact:
    artifact_name: str
    source: str
    version: str
    content_hash: str
    notes: str
    frozen_path: Optional[Path] = None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip())


def norm_key(value: Any) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower())).strip()


def load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text())


def build_registry_window(current_year: Optional[int] = None) -> List[Dict[str, Any]]:
    if current_year is None:
        current_year = datetime.now().year
    return [
        {
            'published_year': year,
            'registry_url': f'https://www.fwc.gov.au/documents/agreements/resources/agreements{year}.xlsx',
        }
        for year in range(current_year - 6, current_year + 1)
    ]


def ensure_dirs() -> None:
    for path in [BRONZE_ROOT, DOCS_INCOMING, DOCS_IMMUTABLE, RULES_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def append_csv_row(path: Path, header: Sequence[str], row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open('a', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header))
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, '') for k in header})


def next_log_id(path: Path, prefix: str) -> str:
    if not path.exists():
        return f'{prefix}-0001'
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return f'{prefix}-0001'
    last = rows[-1]
    digits = re.search(r'(\d+)$', last[next(iter(last))])
    n = int(digits.group(1)) + 1 if digits else len(rows) + 1
    return f'{prefix}-{n:04d}'


def log_fetch_hash(artifact: FetchArtifact) -> None:
    append_csv_row(
        FETCH_HASH_LOG,
        ['log_id', 'timestamp', 'artifact_name', 'source', 'version', 'hash', 'notes'],
        {
            'log_id': next_log_id(FETCH_HASH_LOG, 'FHL'),
            'timestamp': now_iso(),
            'artifact_name': artifact.artifact_name,
            'source': artifact.source,
            'version': artifact.version,
            'hash': artifact.content_hash,
            'notes': artifact.notes,
        },
    )


def freeze_http_binary(url: str, target_path: Path, artifact_name: str, version: str, notes: str) -> Path:
    try:
        response = requests.get(url, timeout=120)
    except requests.exceptions.SSLError:
        if '://www.fwc.gov.au/' not in url:
            raise
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, timeout=120, verify=False)
    response.raise_for_status()
    data = response.content
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)
    log_fetch_hash(
        FetchArtifact(
            artifact_name=artifact_name,
            source=url,
            version=version,
            content_hash=sha256_bytes(data),
            notes=notes,
            frozen_path=target_path,
        )
    )
    return target_path


def fetch_registry_workbook(year_ctx: Dict[str, Any], *, force_refresh: bool = False) -> Path:
    year = year_ctx['published_year']
    url = year_ctx['registry_url']
    target = BRONZE_ROOT / 'fwc_registry' / f'agreements{year}.xlsx'
    if target.exists() and not force_refresh:
        return target
    try:
        return freeze_http_binary(
            url=url,
            target_path=target,
            artifact_name=f'agreements{year}.xlsx',
            version=f'fwc_registry_{year}',
            notes='FWC registry workbook frozen for Phase 1 candidate-source build',
        )
    except requests.RequestException:
        if target.exists() and not force_refresh:
            return target
        raise


def fetch_abs_lga_json() -> Path:
    target = BRONZE_ROOT / 'abs_lga' / 'abs_lga_2025.json'
    if target.exists():
        return target
    response = requests.get(ABS_LGA_URL, params=ABS_LGA_QUERY, timeout=120)
    response.raise_for_status()
    data = response.content
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    log_fetch_hash(
        FetchArtifact(
            artifact_name='abs_lga_2025.json',
            source=f'{ABS_LGA_URL}?{requests.compat.urlencode(ABS_LGA_QUERY)}',
            version='abs_asgs_2025_lga',
            content_hash=sha256_bytes(data),
            notes='ABS LGA JSON frozen for Victorian LGA base build',
            frozen_path=target,
        )
    )
    return target


def _col_to_index(col: str) -> int:
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result


def _parse_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        raw = zf.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    root = ET.fromstring(raw)
    ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    values = []
    for si in root.findall('a:si', ns):
        text = ''.join(t.text or '' for t in si.findall('.//a:t', ns))
        values.append(text)
    return values


def _sheet_xml_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read('xl/workbook.xml'))
    ns = {
        'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    }
    first_sheet = workbook.find('a:sheets/a:sheet', ns)
    rel_id = first_sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
    rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rel_ns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    for rel in rels.findall('r:Relationship', rel_ns):
        if rel.attrib.get('Id') == rel_id:
            return 'xl/' + rel.attrib['Target']
    raise KeyError('Could not resolve first worksheet path')


def _cell_value(cell: ET.Element, shared: Sequence[str], ns: Dict[str, str]) -> str:
    cell_type = cell.attrib.get('t')
    if cell_type == 'inlineStr':
        return ''.join(t.text or '' for t in cell.findall('.//a:t', ns))
    value = cell.find('a:v', ns)
    if value is None:
        return ''
    text = value.text or ''
    if cell_type == 's':
        try:
            return shared[int(text)]
        except Exception:
            return ''
    return text


def read_registry_rows(xlsx_path: Path, range_hint: Tuple[str, int, str, int] = FWC_REGISTRY_RANGE) -> List[Dict[str, str]]:
    start_col, start_row, end_col, end_row = range_hint
    start_idx = _col_to_index(start_col)
    end_idx = _col_to_index(end_col)

    with zipfile.ZipFile(xlsx_path) as zf:
        shared = _parse_shared_strings(zf)
        sheet_path = _sheet_xml_path(zf)
        root = ET.fromstring(zf.read(sheet_path))

    ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rows = []
    header: List[str] = []

    for row in root.findall('.//a:sheetData/a:row', ns):
        row_num = int(row.attrib['r'])
        if row_num < start_row or row_num > end_row:
            continue
        row_map: Dict[int, str] = {}
        for cell in row.findall('a:c', ns):
            ref = cell.attrib.get('r', '')
            match = re.match(r'([A-Z]+)(\d+)', ref)
            if not match:
                continue
            col_letters = match.group(1)
            col_idx = _col_to_index(col_letters)
            if col_idx < start_idx or col_idx > end_idx:
                continue
            row_map[col_idx] = _cell_value(cell, shared, ns)
        values = [row_map.get(idx, '') for idx in range(start_idx, end_idx + 1)]
        if row_num == start_row:
            header = values
            continue
        if not any(norm_text(v) for v in values):
            continue
        if not header:
            raise ValueError('Header row not found in workbook range')
        rows.append({header[i]: values[i] for i in range(min(len(header), len(values)))})
    return rows


def pick_field(row: Dict[str, Any], candidates: Sequence[str]) -> Tuple[str, str]:
    key_map = {norm_key(k): k for k in row.keys()}
    for candidate in candidates:
        actual = key_map.get(norm_key(candidate))
        if actual is None:
            continue
        value = row.get(actual)
        if norm_text(value):
            return str(value), actual
    return '', ''


def canonicalise_registry_rows(rows: Sequence[Dict[str, Any]], year_ctx: Dict[str, Any], header_rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows:
        title, title_field = pick_field(row, header_rules['title'])
        agreement_id, agreement_id_field = pick_field(row, header_rules['agreement_id'])
        matter_number, matter_field = pick_field(row, header_rules['matter_number'])
        operative_date, _ = pick_field(row, header_rules['operative_date'])
        expiry_date, _ = pick_field(row, header_rules['expiry_date'])
        industry, _ = pick_field(row, header_rules['industry'])
        version, _ = pick_field(row, header_rules['version'])
        print_id, _ = pick_field(row, header_rules['print_id'])

        has_meaningful = any(norm_text(v) for v in [title, agreement_id, matter_number])
        if not has_meaningful:
            continue

        canonical_id = norm_text(agreement_id)
        pdf_url = f'https://www.fwc.gov.au/documents/agreements/approved/{canonical_id.lower()}.pdf' if canonical_id else ''
        output.append(
            {
                **row,
                'source_row_type': 'fwc_registry_row',
                'document_source': 'FWC',
                'published_year': year_ctx['published_year'],
                'registry_url': year_ctx['registry_url'],
                'Agreement Title': norm_text(title),
                'Agreement ID': canonical_id,
                'Matter Number': norm_text(matter_number),
                'Operative Date': norm_text(operative_date),
                'Expiry Date': norm_text(expiry_date),
                'Industry': norm_text(industry),
                'Version': norm_text(version),
                'Print ID': norm_text(print_id),
                'agreement_id_source_field': agreement_id_field,
                'agreement_title_source_field': title_field,
                'matter_number_source_field': matter_field,
                'agreement_id_status': 'resolved' if canonical_id else 'missing_after_harmonisation',
                'pdf_url': pdf_url,
            }
        )
    return output


def parse_abs_lga_rows(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text())
    return [feature['attributes'] for feature in payload['features']]


def map_lga_fields(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped = []
    for row in rows:
        mapped.append(
            {
                'lga_name': row.get('lga_name_2025', ''),
                'lga_code': row.get('lga_code_2025', ''),
                'state_name': row.get('state_name_2021', ''),
                'as_of_year': 2025,
            }
        )
    return mapped


def build_victorian_lga_base(rows: Sequence[Dict[str, Any]], match_rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    excluded_codes = set(match_rules['excluded_abs_lga_codes'])
    results = []
    for row in rows:
        if norm_text(row.get('state_name')).lower() != 'victoria':
            continue
        code = norm_text(row.get('lga_code'))
        if code in excluded_codes:
            continue
        original = norm_text(row.get('lga_name'))
        short = re.sub(r'\s+', ' ', re.sub(r'\s*\([^()]*\)\s*', ' ', original)).strip()
        results.append(
            {
                **row,
                'lga_original_name': original,
                'lga_short_name': short,
            }
        )
    return results


def has_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def extract_agreement_number(agreement_id: str) -> float:
    match = re.search(r'\d+', agreement_id or '')
    return float(match.group(0)) if match else float('-inf')


def date_num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return float('-inf')


def title_signature(value: str) -> str:
    return (
        norm_key(value)
        .replace(' no ', ' number ')
        .replace(' number ', ' number ')
        .replace(' enterprise bargaining agreement ', ' enterprise agreement ')
        .replace(' collective agreement ', ' agreement ')
        .replace(' application for approval of ', ' ')
    )


def classify_and_match_registry_rows(registry_rows: Sequence[Dict[str, Any]], lga_rows: Sequence[Dict[str, Any]], match_rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    civic_context = [norm_key(x) for x in match_rules['civic_context_phrases']]
    specialist_keywords = [norm_key(x) for x in match_rules['specialist_keywords']]
    shared_keywords = [norm_key(x) for x in match_rules['shared_keywords']]
    excluded_phrases = [norm_key(x) for x in match_rules['excluded_phrases']]
    explicit_local_gov_context = set(civic_context + [norm_key('local government'), norm_key('municipal')])

    contradiction_map: Dict[str, List[str]] = {}
    for rule in match_rules['contradictions']:
        if not rule.get('active_flag'):
            continue
        contradiction_map.setdefault(rule['lga_short_name'], []).append(norm_key(rule['contradiction_phrase']))

    disambiguation_map: Dict[str, Dict[str, Any]] = {}
    for rule in match_rules.get('disambiguation_overrides', []):
        disambiguation_map[rule['council']] = {
            'binds_only_when_present': [norm_key(x) for x in rule.get('binds_only_when_present', [])],
            'excludes_plain_place_binding_for': rule.get('excludes_plain_place_binding_for', []),
        }

    alias_override_map: Dict[str, Dict[str, Any]] = {}
    for rule in match_rules.get('canonical_alias_overrides', []):
        council = norm_text(rule.get('council'))
        if not council:
            continue
        alias_override_map[council] = {
            'alias_type': norm_text(rule.get('alias_type')),
            'binds_when_present': [norm_key(x) for x in rule.get('binds_when_present', [])],
        }

    lgas = []
    for lga in lga_rows:
        short = norm_key(lga['lga_short_name'])
        original = norm_key(lga['lga_original_name'])
        alias_override = alias_override_map.get(lga['lga_short_name'])
        rename_aliases = (
            alias_override.get('binds_when_present', [])
            if alias_override and alias_override.get('alias_type') == 'rename_alias'
            else []
        )
        civic_strong_aliases = sorted(
            {
                original,
                f'city of {short}',
                f'{short} city council',
                f'{short} shire council',
                f'{short} rural city council',
                f'borough of {short}',
                f'{short} council',
                *rename_aliases,
            },
            key=len,
            reverse=True,
        )
        place_name_aliases = sorted({short}, key=len, reverse=True)
        lgas.append(
            {
                **lga,
                'civic_strong_aliases': [x for x in civic_strong_aliases if x],
                'place_name_aliases': [x for x in place_name_aliases if x],
                'rename_aliases': [x for x in rename_aliases if x],
                'contradiction_phrases': contradiction_map.get(lga['lga_short_name'], []),
            }
        )

    staged: List[Dict[str, Any]] = []
    for row in registry_rows:
        title_raw = norm_text(row.get('Agreement Title'))
        title_norm = norm_key(title_raw)
        industry_norm = norm_key(row.get('Industry'))

        is_local_gov_admin = 'local government administration' in industry_norm
        is_local_gov = 'local government' in industry_norm
        is_blank_industry = industry_norm in {'', 'n a', 'unknown', '---'}
        is_misc = 'miscell' in industry_norm or industry_norm == 'miscellaneous'
        has_council_keyword = has_any(title_norm, [norm_key(x) for x in ['council', 'shire council', 'city council', 'rural city council', 'borough of', 'city of']])
        is_excluded = has_any(title_norm, excluded_phrases)

        candidate_matches = []
        for lga in lgas:
            has_civic_strong = any(alias in title_norm for alias in lga['civic_strong_aliases'])
            has_place_name = any(alias in title_norm for alias in lga['place_name_aliases'])
            has_rename_alias = any(alias in title_norm for alias in lga.get('rename_aliases', []))
            has_civic = has_any(title_norm, civic_context)
            has_explicit_local_gov = has_any(title_norm, explicit_local_gov_context)
            has_contradiction = has_any(title_norm, lga['contradiction_phrases'])
            if has_contradiction:
                continue

            council_name = lga['lga_short_name']
            override = disambiguation_map.get(council_name)
            if override:
                explicit_forms_present = has_any(title_norm, override['binds_only_when_present'])
                if not explicit_forms_present:
                    has_civic_strong = False
                    has_place_name = False

            if has_civic_strong:
                candidate_matches.append({**lga, 'match_strength': 'civic_strong', 'rename_alias_match': has_rename_alias})
                continue
            if has_place_name and (has_civic or is_local_gov or has_explicit_local_gov):
                candidate_matches.append({**lga, 'match_strength': 'place_name_strong', 'rename_alias_match': has_rename_alias})

        deduped = []
        seen = set()
        for match in candidate_matches:
            if match['lga_short_name'] in seen:
                continue
            seen.add(match['lga_short_name'])
            deduped.append(match)
        match_rank = {'civic_strong': 0, 'place_name_strong': 1}
        deduped.sort(key=lambda x: (match_rank.get(x['match_strength'], 9), x['lga_short_name']))

        matched_names = [m['lga_short_name'] for m in deduped]
        matched_count = len(matched_names)
        single = deduped[0] if matched_count == 1 else None

        hints = []
        if has_any(title_norm, specialist_keywords):
            hints.append('possible_specialist')
        if has_any(title_norm, shared_keywords) or matched_count > 1:
            hints.append('possible_multi_council_or_shared')
        if matched_count > 1:
            hints.append('multiple_lga_title_hits')
        if any(m['match_strength'] == 'place_name_strong' for m in deduped):
            hints.append('place_name_match')

        strong_local_gov_context = is_local_gov_admin
        civic_title_survival = has_council_keyword
        matched_survival = matched_count > 0 and (has_council_keyword or is_local_gov_admin)
        weak_industry_survival = (is_blank_industry or is_misc) and has_council_keyword

        should_keep = not is_excluded and (
            strong_local_gov_context
            or weak_industry_survival
            or matched_survival
        )
        if not should_keep:
            continue

        agreement_id = norm_text(row.get('Agreement ID'))
        agreement_num = extract_agreement_number(agreement_id)
        matter_number = norm_text(row.get('Matter Number'))
        normalized_title = title_signature(title_raw)
        context_key = single['lga_short_name'] if single else ('|'.join(sorted(matched_names)) if matched_count > 1 else '__unmatched__')
        lineage_basis = 'council_context+matter_number' if matter_number else 'council_context+normalized_title'
        lineage_key = f"{context_key}::matter::{norm_key(matter_number)}" if matter_number else f"{context_key}::title::{normalized_title}"
        scope_resolution_status = (
            'rename_alias_resolved'
            if single and single.get('rename_alias_match') and not any(hint.startswith('possible_multi') for hint in hints)
            else 'title_only_unresolved'
        )

        staged.append(
            {
                **row,
                'classification': 'core_local_gov' if is_local_gov_admin else ('council_related' if matched_count > 0 else 'misc_or_blank_council_like'),
                'title_scope_hints': '|'.join(hints),
                'scope_resolution_status': scope_resolution_status,
                'possible_multi_council_flag': matched_count > 1,
                'matched_lga_count': matched_count,
                'matched_lga_names': '|'.join(matched_names),
                'lga_short_name': single['lga_short_name'] if single else '',
                'lga_original_name': single['lga_original_name'] if single else '',
                'lga_code': single['lga_code'] if single else '',
                'state_name': single['state_name'] if single else '',
                'as_of_year': single['as_of_year'] if single else '',
                'match_strength': single['match_strength'] if single else '',
                'agreement_num_clean': '' if agreement_num == float('-inf') else int(agreement_num),
                'lineage_key': lineage_key,
                'lineage_basis': lineage_basis,
                'likely_most_current': None,
            }
        )

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in staged:
        groups.setdefault(row['lineage_key'], []).append(row)

    rank_key = lambda row: (
        0 if norm_text(row.get('Agreement ID')) else 1,
        -float(row.get('agreement_num_clean') or float('-inf')),
        -date_num(row.get('Operative Date')),
        -float(row.get('published_year') or float('-inf')),
    )

    for group in groups.values():
        group.sort(key=rank_key)
        if group:
            group[0]['likely_most_current'] = 'likely_current'

    for row in staged:
        if row.get('likely_most_current') == 'likely_current':
            row['pipeline_status'] = 'active'
            row['superseded_by_ae_id'] = ''
        else:
            row['pipeline_status'] = 'superseded_in_lineage'
            row['superseded_by_ae_id'] = ''

    council_current_map: Dict[str, List[Dict[str, Any]]] = {}
    for row in staged:
        if row.get('likely_most_current') != 'likely_current':
            continue
        councils = [norm_text(x) for x in norm_text(row.get('matched_lga_names')).split('|') if norm_text(x)]
        if not councils and norm_text(row.get('lga_short_name')):
            councils = [norm_text(row.get('lga_short_name'))]
        for council in councils:
            council_current_map.setdefault(council, []).append(row)

    for council_rows in council_current_map.values():
        if len(council_rows) <= 1:
            continue
        ranked = sorted(council_rows, key=rank_key)
        best = ranked[0]
        best_operative_date = date_num(best.get('Operative Date'))
        if len(ranked) > 1 and date_num(ranked[1].get('Operative Date')) == best_operative_date:
            continue
        superseding_ae_id = norm_text(best.get('Agreement ID'))
        for row in ranked[1:]:
            if date_num(row.get('Operative Date')) == best_operative_date:
                continue
            row['pipeline_status'] = 'superseded_by_newer'
            row['superseded_by_ae_id'] = superseding_ae_id

    return staged


FINAL_FIELDS = [
    'lga_short_name', 'lga_original_name', 'lga_code', 'state_name', 'Agreement Title', 'Agreement ID',
    'Version', 'Print ID',
    'agreement_id_source_field', 'agreement_id_status', 'agreement_num_clean', 'Matter Number',
    'Operative Date', 'Expiry Date', 'Industry', 'published_year', 'likely_most_current', 'pipeline_status',
    'superseded_by_ae_id', 'pdf_url', 'classification', 'title_scope_hints', 'scope_resolution_status',
    'possible_multi_council_flag', 'matched_lga_count', 'matched_lga_names', 'match_strength', 'lineage_key',
    'lineage_basis'
]


def finalise_candidate_fields(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{field: row.get(field, '') for field in FINAL_FIELDS} for row in rows]


def write_candidate_outputs(rows: Sequence[Dict[str, Any]]) -> None:
    out_dir = BRONZE_ROOT / 'candidate_agreements'
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / 'candidate_agreements.json'
    csv_path = out_dir / 'candidate_agreements.csv'
    projected = finalise_candidate_fields(rows)
    json_path.write_text(json.dumps(projected, indent=2))
    with csv_path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FINAL_FIELDS)
        writer.writeheader()
        writer.writerows(projected)


def freeze_candidate_pdfs(
    rows: Sequence[Dict[str, Any]],
    limit: Optional[int] = None,
    agreement_ids: Optional[Sequence[str]] = None,
) -> List[Path]:
    frozen: List[Path] = []
    count = 0
    allowed_ids = {norm_text(aid).upper() for aid in agreement_ids or [] if norm_text(aid)}
    for row in rows:
        if row.get('pipeline_status', 'active') not in ('active',):
            continue
        pdf_url = norm_text(row.get('pdf_url'))
        agreement_id = norm_text(row.get('Agreement ID'))
        if not pdf_url or not agreement_id:
            continue
        if allowed_ids and agreement_id.upper() not in allowed_ids:
            continue
        if limit is not None and count >= limit:
            break
        target_incoming = DOCS_INCOMING / f'{agreement_id.lower()}.pdf'
        target_immutable = DOCS_IMMUTABLE / f'{agreement_id.lower()}.pdf'
        if target_immutable.exists():
            frozen.append(target_immutable)
            continue
        response = requests.get(pdf_url, timeout=120)
        if response.status_code != 200 or 'application/pdf' not in response.headers.get('Content-Type', '').lower():
            continue
        data = response.content
        target_incoming.write_bytes(data)
        target_immutable.write_bytes(data)
        digest = sha256_bytes(data)
        log_fetch_hash(
            FetchArtifact(
                artifact_name=target_immutable.name,
                source=pdf_url,
                version='candidate_pdf_freeze',
                content_hash=digest,
                notes='Candidate agreement PDF fetched/frozen from Agreement ID derived URL',
                frozen_path=target_immutable,
            )
        )
        append_csv_row(
            SOURCE_DOCUMENT_REGISTER,
            ['source_document_id', 'source_name', 'source_type', 'source_origin', 'fetched_at', 'content_hash', 'frozen_path', 'source_status', 'serviceability_status', 'discovery_reference', 'notes'],
            {
                'source_document_id': '',
                'source_name': row.get('Agreement Title', target_immutable.name),
                'source_type': 'EA PDF',
                'source_origin': str(target_incoming),
                'fetched_at': now_iso(),
                'content_hash': digest,
                'frozen_path': str(target_immutable),
                'source_status': 'candidate',
                'serviceability_status': 'unreviewed',
                'discovery_reference': agreement_id,
                'notes': 'Phase 1 candidate PDF freeze from registry-derived PDF URL',
            },
        )
        append_csv_row(
            DOCUMENT_REGISTER,
            ['document_id', 'source_document_id', 'document_name', 'document_type', 'status', 'notes'],
            {
                'document_id': '',
                'source_document_id': '',
                'document_name': row.get('Agreement Title', target_immutable.name),
                'document_type': 'EA PDF',
                'status': 'candidate',
                'notes': f'Phase 1 candidate PDF frozen from {agreement_id}',
            },
        )
        frozen.append(target_immutable)
        count += 1

    status_by_ae = {
        norm_text(row.get('Agreement ID')).lower(): norm_text(row.get('pipeline_status'))
        for row in rows
        if norm_text(row.get('Agreement ID'))
    }
    superseded_dir = DOCS_IMMUTABLE / 'superseded'
    superseded_dir.mkdir(parents=True, exist_ok=True)
    for pdf_path in DOCS_IMMUTABLE.glob('*.pdf'):
        agreement_id = pdf_path.stem.lower()
        if status_by_ae.get(agreement_id) != 'superseded_by_newer':
            continue
        target_path = superseded_dir / pdf_path.name
        if target_path.exists():
            pdf_path.unlink()
        else:
            pdf_path.rename(target_path)
        print(f'Relocated superseded PDF: {pdf_path.name} -> superseded/')
    return frozen


def run_phase1(
    fetch_pdfs: bool = False,
    pdf_limit: Optional[int] = None,
    freeze_agreement_ids: Optional[Sequence[str]] = None,
    force_registry: bool = False,
) -> Dict[str, Any]:
    ensure_dirs()
    header_rules = load_yaml(RULES_ROOT / 'header_candidates.yml')
    match_rules = load_yaml(RULES_ROOT / 'vic_matching_rules.yml')

    registry_rows: List[Dict[str, Any]] = []
    for year_ctx in build_registry_window():
        workbook_path = fetch_registry_workbook(year_ctx, force_refresh=force_registry)
        raw_rows = read_registry_rows(workbook_path)
        registry_rows.extend(canonicalise_registry_rows(raw_rows, year_ctx, header_rules))

    abs_path = fetch_abs_lga_json()
    abs_rows = parse_abs_lga_rows(abs_path)
    lga_base = build_victorian_lga_base(map_lga_fields(abs_rows), match_rules)
    candidates = classify_and_match_registry_rows(registry_rows, lga_base, match_rules)
    write_candidate_outputs(candidates)

    active_candidates = [row for row in candidates if row.get('pipeline_status', 'active') == 'active']
    superseded_by_newer = [row for row in candidates if row.get('pipeline_status') == 'superseded_by_newer']
    superseded_in_lineage = [row for row in candidates if row.get('pipeline_status') == 'superseded_in_lineage']
    superseded_ids = [norm_text(row.get('Agreement ID')) for row in superseded_by_newer if norm_text(row.get('Agreement ID'))]
    print(f'Active agreements: {len(active_candidates)}')
    print(f"Superseded (by newer): {len(superseded_by_newer)}{' [' + ', '.join(superseded_ids) + ']' if superseded_ids else ''}")
    print(f'Superseded (in lineage): {len(superseded_in_lineage)}')

    frozen = []
    if fetch_pdfs:
        frozen = freeze_candidate_pdfs(candidates, limit=pdf_limit, agreement_ids=freeze_agreement_ids)

    return {
        'registry_rows': len(registry_rows),
        'victorian_lgas': len(lga_base),
        'candidate_agreements': len(candidates),
        'frozen_candidate_pdfs': len(frozen),
        'candidate_output_dir': str(BRONZE_ROOT / 'candidate_agreements'),
        'frozen_paths': [str(path) for path in frozen],
        'freeze_agreement_ids': list(freeze_agreement_ids or []),
        'force_registry': force_registry,
    }
