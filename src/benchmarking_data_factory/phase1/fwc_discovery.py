from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Dict, List, Optional

import requests


def norm_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip())


def _extract_links(html: str) -> List[str]:
    return [unescape(x) for x in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)]


def _extract_attrs(html: str, pattern: str) -> List[str]:
    return [unescape(x) for x in re.findall(pattern, html, flags=re.I)]


def _extract_drupal_settings(html: str) -> Optional[Dict[str, Any]]:
    m = re.search(
        r'<script[^>]*data-drupal-selector=["\']drupal-settings-json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _find_wrapper_candidates(search_html: str, agreement_id: str, agreement_title: str) -> List[str]:
    agreement_id_l = agreement_id.lower()
    title_words = [w.lower() for w in re.findall(r'[A-Za-z]{4,}', agreement_title)[:8]]
    cues = ['agreement', 'enterprise', 'document', 'approved']
    scored = []

    articles = re.findall(r'<article[^>]*>(.*?)</article>', search_html, flags=re.I | re.S)
    for article in articles:
        links = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', article, flags=re.I | re.S)
        article_text = norm_text(re.sub(r'<[^>]+>', ' ', article)).lower()
        for href, inner in links:
            if not href.startswith('/'):
                continue
            link_l = href.lower()
            score = 0
            if '/document-view/agreements/' in link_l:
                score += 10
            elif '/document-view/' in link_l:
                score += 6
            elif '/node/' in link_l:
                score += 3
            if agreement_id_l in article_text or agreement_id_l in link_l:
                score += 6
            if any(word in article_text for word in title_words):
                score += 3
            if any(cue in article_text for cue in cues):
                score += 2
            if 'page' in article_text and 'agreement' not in article_text and '/document-view/' not in link_l:
                score -= 2
            if score > 0:
                scored.append((score, href))

    if not scored:
        links = _extract_links(search_html)
        for link in links:
            if not link.startswith('/'):
                continue
            score = 0
            link_l = link.lower()
            if '/document-view/agreements/' in link_l:
                score += 10
            elif '/document-view/' in link_l:
                score += 5
            elif '/node/' in link_l:
                score += 2
            if agreement_id_l in link_l:
                score += 5
            if any(word in link_l for word in title_words):
                score += 1
            if score > 0:
                scored.append((score, link))

    scored.sort(key=lambda x: (-x[0], x[1]))
    seen = []
    for _, link in scored:
        if link not in seen:
            seen.append(link)
    return seen[:10]


def _discover_from_wrapper_html(wrapper_url: str, html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        'document_discovery_url': wrapper_url,
        'document_download_url': '',
        'document_file_url': '',
        'file_name': '',
        'mime_type': '',
        'wrapper_resolved': True,
        'final_target_is_downloadable_document': False,
    }

    # priority a: direct download anchors
    for pat in [
        r'<a[^>]*class=["\'][^"\']*document-node__btn--download[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        r'<a[^>]*class=["\'][^"\']*document-viewer__btn--download[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        r'<a[^>]*href=["\']([^"\']*document-view/media/download/[^"\']+)["\']',
    ]:
        found = _extract_attrs(html, pat)
        if found:
            out['document_download_url'] = found[0] if found[0].startswith('http') else 'https://www.fwc.gov.au' + found[0]
            break

    settings = _extract_drupal_settings(html)
    if settings:
        settings_text = json.dumps(settings)
        m_file = re.search(r'"fileUrl"\s*:\s*"([^"]+)"', settings_text)
        m_name = re.search(r'"fileName"\s*:\s*"([^"]+)"', settings_text)
        m_mime = re.search(r'"mimeType"\s*:\s*"([^"]+)"', settings_text)
        if m_file:
            out['document_file_url'] = m_file.group(1)
            if not out['document_download_url']:
                out['document_download_url'] = m_file.group(1)
        if m_name:
            out['file_name'] = m_name.group(1)
        if m_mime:
            out['mime_type'] = m_mime.group(1)

    # priority c: iframe fallback
    if not out['document_file_url']:
        iframe = _extract_attrs(html, r'<iframe[^>]*class=["\'][^"\']*document-viewer__iframe[^"\']*["\'][^>]*src=["\']([^"\']+)["\']')
        if iframe:
            out['document_file_url'] = iframe[0] if iframe[0].startswith('http') else 'https://www.fwc.gov.au' + iframe[0]

    if out['mime_type'].lower() in {'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}:
        out['final_target_is_downloadable_document'] = True
    elif out['document_download_url'] and any(out['document_download_url'].lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx']):
        out['final_target_is_downloadable_document'] = True
    elif '/document-view/media/download/' in out['document_download_url']:
        out['final_target_is_downloadable_document'] = True

    return out


def discover_fwc_document_url(agreement_id: str, agreement_title: str, matter_number: str | None = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'agreement_id': agreement_id,
        'agreement_title': agreement_title,
        'cheap_probe_url': f'https://www.fwc.gov.au/documents/agreements/approved/{agreement_id.lower()}.pdf',
        'cheap_probe_status': None,
        'search_url': '',
        'result_count_found': 0,
        'document_discovery_url': '',
        'document_wrapper_url': '',
        'wrapper_resolved': False,
        'document_download_url': '',
        'document_file_url': '',
        'file_name': '',
        'mime_type': '',
        'download_fetch_status': None,
        'download_fetch_content_type': '',
        'final_target_is_downloadable_document': False,
        'response_state': '',
        'notes': '',
    }

    cheap = requests.get(result['cheap_probe_url'], timeout=20, allow_redirects=True)
    result['cheap_probe_status'] = cheap.status_code
    if cheap.status_code == 200 and any(x in cheap.headers.get('Content-Type', '').lower() for x in ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']):
        result['document_download_url'] = cheap.url
        result['mime_type'] = cheap.headers.get('Content-Type', '')
        result['download_fetch_status'] = cheap.status_code
        result['download_fetch_content_type'] = cheap.headers.get('Content-Type', '')
        result['final_target_is_downloadable_document'] = True
        result['response_state'] = 'direct_probe_success'
        result['notes'] = 'Direct AE-ID approved path worked.'
        return result

    search_url = f'https://www.fwc.gov.au/document-search?keyword={requests.utils.quote(agreement_id)}&search-ui=agreements'
    result['search_url'] = search_url
    result['document_discovery_url'] = search_url
    search_resp = requests.get(search_url, timeout=20, allow_redirects=True)
    if search_resp.status_code != 200:
        result['notes'] = 'Document-search page did not resolve successfully.'
        return result

    html = search_resp.text
    cards = re.findall(r'<[^>]*class=["\'][^"\']*fwc-results-item[^"\']*["\'][^>]*>(.*?)</(?:article|div)>', html, flags=re.I | re.S)
    if not cards:
        cards = re.findall(r'<article[^>]*>(.*?)</article>', html, flags=re.I | re.S)
    result['result_count_found'] = len(cards)

    candidates = []
    for card in cards:
        card_text = norm_text(re.sub(r'<[^>]+>', ' ', card)).lower()
        if agreement_id.lower() not in card_text and not any(w.lower() in card_text for w in re.findall(r'[A-Za-z]{4,}', agreement_title)[:6]):
            continue

        direct = _extract_attrs(card, r'<[^>]*class=["\'][^"\']*document-actions[^"\']*["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\']')
        icon_wrapper = _extract_attrs(card, r'<[^>]*class=["\'][^"\']*document-icon[^"\']*["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\']')
        wrapper = []
        if not direct:
            direct = _extract_attrs(card, r'<a[^>]*href=["\']([^"\']*document-view/media/download/[^"\']+)["\']')
        if icon_wrapper:
            wrapper = icon_wrapper
        if not wrapper:
            wrapper = _extract_attrs(card, r'<a[^>]*href=["\']([^"\']*document-view/agreements/[^"\']+)["\']')
        if not wrapper:
            wrapper = _extract_attrs(card, r'<a[^>]*href=["\']([^"\']*document-view/[^"\']+)["\']')
        candidates.append({
            'card_text': card_text,
            'direct': direct[0] if direct else '',
            'wrapper': wrapper[0] if wrapper else '',
        })

    for cand in candidates:
        if cand['direct']:
            url = cand['direct'] if cand['direct'].startswith('http') else 'https://www.fwc.gov.au' + cand['direct']
            result['document_download_url'] = url
            head = requests.get(url, timeout=20, allow_redirects=True)
            result['download_fetch_status'] = head.status_code
            result['download_fetch_content_type'] = head.headers.get('Content-Type', '')
            result['mime_type'] = head.headers.get('Content-Type', '')
            if head.status_code == 200 and any(x in head.headers.get('Content-Type', '').lower() for x in ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']):
                result['final_target_is_downloadable_document'] = True
                result['response_state'] = 'download_url_resolved'
                result['notes'] = 'Resolved directly from /document-search result card download link.'
                return result
            if head.status_code in {401, 403} or 'token' in (head.text[:400].lower() if 'text' in head.headers.get('Content-Type', '').lower() else ''):
                if cand['wrapper']:
                    wrapper_url = cand['wrapper'] if cand['wrapper'].startswith('http') else 'https://www.fwc.gov.au' + cand['wrapper']
                    result['document_wrapper_url'] = wrapper_url
                    try:
                        resp = requests.get(wrapper_url, timeout=20, allow_redirects=True)
                    except Exception:
                        resp = None
                    if resp is not None and resp.status_code == 200:
                        discovered = _discover_from_wrapper_html(wrapper_url, resp.text)
                        result.update(discovered)
                        result['document_wrapper_url'] = wrapper_url
                        fresh_target = result.get('document_file_url') or result.get('document_download_url')
                        if fresh_target:
                            final = requests.get(fresh_target, timeout=20, allow_redirects=True)
                            result['download_fetch_status'] = final.status_code
                            result['download_fetch_content_type'] = final.headers.get('Content-Type', '')
                            if not result.get('mime_type'):
                                result['mime_type'] = final.headers.get('Content-Type', '')
                            if final.status_code == 200 and any(x in final.headers.get('Content-Type', '').lower() for x in ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']):
                                result['final_target_is_downloadable_document'] = True
                                result['response_state'] = 'wrapper_secure_file_resolved'
                                result['notes'] = 'Initial media-download returned auth/state failure, but wrapper-derived fresh file target resolved successfully.'
                                return result
                result['response_state'] = 'download_url_resolved'
                result['notes'] = 'Initial result-card download URL resolved but returned auth/state failure; wrapper recovery did not resolve a fresh file target in this bounded pass.'
                return result
            result['response_state'] = 'download_url_resolved'
            result['notes'] = 'Resolved directly from /document-search result card download link, but final document validation did not succeed.'
            return result

        if cand['wrapper']:
            wrapper_url = cand['wrapper'] if cand['wrapper'].startswith('http') else 'https://www.fwc.gov.au' + cand['wrapper']
            result['document_wrapper_url'] = wrapper_url
            try:
                resp = requests.get(wrapper_url, timeout=20, allow_redirects=True)
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            discovered = _discover_from_wrapper_html(wrapper_url, resp.text)
            result.update(discovered)
            result['document_wrapper_url'] = wrapper_url
            fresh_target = result.get('document_file_url') or result.get('document_download_url')
            if fresh_target:
                final = requests.get(fresh_target, timeout=20, allow_redirects=True)
                result['download_fetch_status'] = final.status_code
                result['download_fetch_content_type'] = final.headers.get('Content-Type', '')
                if not result.get('mime_type'):
                    result['mime_type'] = final.headers.get('Content-Type', '')
                result['final_target_is_downloadable_document'] = final.status_code == 200 and any(x in final.headers.get('Content-Type', '').lower() for x in ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
                if result['final_target_is_downloadable_document']:
                    result['response_state'] = 'wrapper_secure_file_resolved'
                    result['notes'] = 'Resolved via wrapper-derived fresh file target.'
                    return result
            result['response_state'] = 'wrapper_resolved'
            result['notes'] = 'Resolved wrapper page, but no valid downloadable file target succeeded in this bounded pass.'
            return result

    result['response_state'] = 'public_dms_unresolved'
    result['notes'] = 'Document-search surface resolved, but no usable wrapper/download target was extracted in this bounded pass.'
    return result
