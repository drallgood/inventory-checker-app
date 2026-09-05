#!/usr/bin/env python3
"""Per-family extraction and enrichment handlers for Apple product pages.

Each handler encapsulates family-specific logic that was previously
scattered across if/elif branches in scrape_models.py.
"""

from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Set, Tuple


# ---------------------------------------------------------------------------
# Module-level extraction utilities (moved from Scraper class)
# ---------------------------------------------------------------------------

def extract_display_value_mappings_from_html(html: str, dimension_key: str) -> dict:
    """
    Extract displayValues mappings from Apple buy pages.

    The page commonly contains JSON-ish structures like:
      "dimensionFinish": { "midnight": { "value": "Mitternacht" }, ... }

    We avoid hardcoding any translation; we just parse what's on the page.
    Returns a dict keyed by a normalized variant key (lowercased alnum only).
    """
    if not html or not dimension_key:
        return {}

    mappings: dict = {}
    dim_re = re.compile(r'"' + re.escape(dimension_key) + r'"\s*:\s*\{', re.IGNORECASE)
    kv_re = re.compile(r'"([^"]+)"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"', re.IGNORECASE)

    for m in dim_re.finditer(html):
        chunk = html[m.end(): m.end() + 80000]
        for km in kv_re.finditer(chunk):
            raw_key, raw_val = km.group(1), km.group(2)
            if not raw_key or not raw_val:
                continue
            if raw_key in ('title', 'variantOrder', 'variantSortOrder'):
                continue
            key_norm = re.sub(r'[^a-z0-9]', '', raw_key.lower())
            val_clean = re.sub(r'<[^>]+>', '', raw_val).strip()
            if key_norm and val_clean:
                mappings.setdefault(key_norm, val_clean)
        if mappings:
            break

    return mappings


def extract_select_header_mappings_from_html(html: str) -> dict:
    """
    Extract localized variant labels from Apple buy pages.

    Many pages embed swatch/selector metadata like:
      "midnight-select-202503_SW_COLOR" ... "header":"Mitternacht"

    We parse these (without hardcoding translations) into:
      { "midnight": "Mitternacht" }

    Keys are normalized to lowercase alnum.
    """
    if not html:
        return {}

    mappings: dict = {}
    sel_re = re.compile(
        r'"([a-z0-9_-]{3,40})-select-[^"]+"[\s\S]{0,500}?"header"\s*:\s*"([^"]{1,120})"',
        re.IGNORECASE
    )
    for m in sel_re.finditer(html):
        raw_key, raw_header = m.group(1), m.group(2)
        key_norm = re.sub(r'[^a-z0-9]', '', (raw_key or '').lower())
        header_clean = re.sub(r'<[^>]+>', '', (raw_header or '')).strip()
        if key_norm and header_clean:
            mappings.setdefault(key_norm, header_clean)

    return mappings


# ---------------------------------------------------------------------------
# Base Handler
# ---------------------------------------------------------------------------

class FamilyHandler:
    """No-op base for families that need no special treatment."""

    def __init__(self, family_config: dict):
        self.config = family_config

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        return skus

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        return skus

    def post_process_output(self, skus: dict, family: str) -> dict:
        return skus

    def validate(self, skus: dict, html: str, region_code: str,
                 family: str, token: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Watch Handler
# ---------------------------------------------------------------------------

class WatchHandler(FamilyHandler):
    """Apple Watch: dimension enrichment + familyName normalization."""

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        if not skus or not payload:
            return skus

        html_watch = payload.get('html', '')
        pn_to_dims: Dict[str, Dict[str, str]] = {}

        bs = payload.get('bootstrap') if isinstance(payload, dict) else None
        if not isinstance(bs, dict) and html_watch:
            text_blob = None
            m = re.search(r"PRODUCT_SELECTION_BOOTSTRAP\s*=\s*JSON\.parse\(\s*'(.+?)'\s*\)\s*;", html_watch, re.DOTALL)
            if m:
                encoded = m.group(1)
                try:
                    unescaped = bytes(encoded, 'utf-8').decode('unicode_escape')
                except Exception:
                    try:
                        unescaped = json.loads('"' + encoded.replace('"', '\\"') + '"')
                    except Exception:
                        unescaped = encoded
                text_blob = unescaped
            else:
                assign = html_watch.find('window.PRODUCT_SELECTION_BOOTSTRAP')
                if assign != -1:
                    brace = html_watch.find('{', assign)
                    if brace != -1:
                        depth = 0
                        end = brace
                        for i in range(brace, len(html_watch)):
                            ch = html_watch[i]
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end = i
                                    break
                        text_blob = html_watch[brace:end + 1]
            if text_blob:
                try:
                    bs = json.loads(re.sub(r',\s*([}\]])', r'\1', text_blob))
                except Exception:
                    bs = None
        if isinstance(bs, dict):
            psd = (bs.get('productSelectionData') or {})
            prods = (psd.get('products') or [])
            dv = psd.get('displayValues') or {}

            def _dv_maps(dim_key: str) -> list:
                return [dv.get(dim_key) or {}, dv.get(f'watch_cases-{dim_key}') or {}]

            def _resolve(dim_key: str, val: str) -> str:
                if not isinstance(val, str):
                    return ''
                for mp in _dv_maps(dim_key):
                    entry = mp.get(val)
                    if isinstance(entry, dict):
                        pretty = entry.get('value') or entry.get('text') or ''
                        pretty = re.sub(r'<[^>]+>', '', pretty).replace('\u00a0', ' ').strip()
                        if pretty:
                            return pretty
                return val

            def _first(obj: Dict[str, Any], keys: list) -> str:
                for k in keys:
                    v = obj.get(k)
                    if isinstance(v, str) and v:
                        return v
                for k, v in obj.items():
                    if not isinstance(v, str):
                        continue
                    for suf in keys:
                        suf0 = suf.split('-')[-1]
                        if suf0 in k:
                            return v
                return ''

            for p in prods:
                if not isinstance(p, dict):
                    continue
                pn = None
                if isinstance(p.get('partNumber'), str):
                    pn = p.get('partNumber')
                elif isinstance(p.get('part'), str):
                    pn = p.get('part')
                if not pn:
                    continue
                z = p.get('dimensions') if isinstance(p.get('dimensions'), dict) else {}
                cs = _first(p, ['dimensionCaseSize', 'watch_cases-dimensionCaseSize']) or _first(z, ['dimensionCaseSize', 'watch_cases-dimensionCaseSize'])
                cm = _first(p, ['dimensionCaseMaterial', 'watch_cases-dimensionCaseMaterial']) or _first(z, ['dimensionCaseMaterial', 'watch_cases-dimensionCaseMaterial'])
                co = _first(p, ['dimensionConnection', 'watch_cases-dimensionConnection']) or _first(z, ['dimensionConnection', 'watch_cases-dimensionConnection'])
                col_key = _first(p, ['dimensionColor', 'watch_cases-dimensionColor']) or _first(z, ['dimensionColor', 'watch_cases-dimensionColor'])
                dims: Dict[str, str] = {}
                if cs:
                    dims['caseSize'] = _resolve('dimensionCaseSize', cs)
                if cm:
                    dims['caseMaterial'] = _resolve('dimensionCaseMaterial', cm)
                if co:
                    dims['connectivity'] = _resolve('dimensionConnection', co)
                if dims:
                    pn_to_dims[pn] = dims
                if col_key:
                    ck = col_key.lower().replace(' ', '')
                    cd = _resolve('dimensionColor', col_key)
                    if pn in skus and isinstance(skus[pn], dict):
                        if not (skus[pn].get('colorKey') or '').strip():
                            skus[pn]['colorKey'] = ck
                        if not (skus[pn].get('colorDisplay') or '').strip():
                            skus[pn]['colorDisplay'] = cd
                        md = skus[pn].get('metadata') if isinstance(skus[pn].get('metadata'), dict) else {}
                        if not (md.get('color') or '').strip():
                            md['color'] = cd
                            skus[pn]['metadata'] = md
            if not pn_to_dims:
                sizes_map = dv.get('watch_cases-dimensionCaseSize') or dv.get('dimensionCaseSize') or {}
                size_keys = [k for k in sizes_map.keys() if k != 'variantOrder']
                if len(size_keys) == 1:
                    single_size = _resolve('dimensionCaseSize', size_keys[0])
                    applied = 0
                    for sku, sku_data in skus.items():
                        if not isinstance(sku_data, dict):
                            continue
                        md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
                        if not md.get('caseSize'):
                            md['caseSize'] = single_size
                            sku_data['metadata'] = md
                            applied += 1
                    if applied:
                        print(f"[debug][watch] Applied single-size default '{single_size}' to {applied} SKU(s)")
        # Fallback: regex proximity in raw HTML
        if not pn_to_dims and html_watch:
            for m in re.finditer(
                r'"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z])"[\s\S]{0,1000}?"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"',
                html_watch, re.IGNORECASE):
                pn, sz, mat, conn = m.group(1), m.group(2), m.group(3), m.group(4)
                pn_to_dims[pn] = {"caseSize": sz, "caseMaterial": mat, "connectivity": conn}
            for m in re.finditer(
                r'"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"[\s\S]{0,1000}?"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z])"',
                html_watch, re.IGNORECASE):
                sz, mat, conn, pn = m.group(1), m.group(2), m.group(3), m.group(4)
                pn_to_dims[pn] = {"caseSize": sz, "caseMaterial": mat, "connectivity": conn}
            for m in re.finditer(
                r'"part"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z])"[\s\S]{0,1000}?"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"',
                html_watch, re.IGNORECASE):
                pn, sz, mat, conn = m.group(1), m.group(2), m.group(3), m.group(4)
                pn_to_dims[pn] = {"caseSize": sz, "caseMaterial": mat, "connectivity": conn}
            for m in re.finditer(
                r'"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"[\s\S]{0,1000}?"part"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z])"',
                html_watch, re.IGNORECASE):
                sz, mat, conn, pn = m.group(1), m.group(2), m.group(3), m.group(4)
                pn_to_dims[pn] = {"caseSize": sz, "caseMaterial": mat, "connectivity": conn}
        if pn_to_dims:
            enriched_count = 0
            for sku, sku_data in skus.items():
                if not isinstance(sku_data, dict):
                    continue
                if sku not in pn_to_dims:
                    continue
                dims = pn_to_dims[sku]
                md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
                for k in ('caseSize', 'caseMaterial', 'connectivity'):
                    v = (dims.get(k) or '').strip()
                    if v:
                        md[k] = v
                if md:
                    sku_data['metadata'] = md
                    enriched_count += 1
            if enriched_count:
                print(f"[debug][watch] Enriched {enriched_count} SKU(s) with case size/material/connectivity before pruning")

        return skus

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        watch_display = inferred_display or _pretty_token_name(family_config.get('display_name', ''), token)
        if watch_display:
            for sku_key, sku_md in skus.items():
                if not isinstance(sku_md, dict):
                    continue
                cur_name = (sku_md.get('familyName') or '').strip()
                if not cur_name or cur_name == 'Apple Watch':
                    sku_md['familyName'] = watch_display
        return skus

    def post_process_output(self, skus: dict, family: str) -> dict:
        fixed: Dict[str, dict] = skus or {}
        try:
            names: List[str] = []
            for _, md in (fixed or {}).items():
                if isinstance(md, dict):
                    n = (md.get('familyName') or '').strip()
                    if n and n.lower() != 'apple watch':
                        names.append(n)
            majority = None
            if names:
                counts: Dict[str, int] = {}
                for n in names:
                    counts[n] = counts.get(n, 0) + 1
                majority = max(counts, key=counts.get) if counts else None
            if majority:
                tmp = {}
                for sku, md in (fixed or {}).items():
                    if not isinstance(md, dict):
                        tmp[sku] = md
                        continue
                    md2 = dict(md)
                    cur = (md2.get('familyName') or '').strip()
                    if not cur or cur.lower() == 'apple watch':
                        md2['familyName'] = majority
                    tmp[sku] = md2
                fixed = tmp
        except Exception:
            pass
        return fixed


# ---------------------------------------------------------------------------
# Mac Handler
# ---------------------------------------------------------------------------

class MacHandler(FamilyHandler):
    """Mac: build distinct, user-friendly per-SKU names."""

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        html = payload.get('html', '')
        base_name = (inferred_display or '').strip() or family_config.get('display_name', 'Mac')

        localized_finish_map = extract_display_value_mappings_from_html(html, 'dimensionFinish') if html else {}
        localized_color_map = extract_display_value_mappings_from_html(html, 'dimensionColor') if html else {}
        select_header_map = extract_select_header_mappings_from_html(html) if html else {}

        def _norm_key(s: str) -> str:
            return re.sub(r'[^a-z0-9]', '', (s or '').lower())

        def _pretty_size(raw: str) -> str:
            s = (raw or '').strip()
            m = re.match(r'^(\d{2})inch$', s, re.IGNORECASE)
            return f"{m.group(1)}-inch" if m else s

        def _pretty_proc(raw: str) -> str:
            p = (raw or '').strip()
            if not p:
                return ''
            parts = [x for x in p.split('-') if x]
            head = parts[0]
            tail = ' '.join(parts[1:])
            mh = re.match(r'^(m\d)(pro|max|ultra)?$', head, re.IGNORECASE)
            if mh:
                head_pretty = mh.group(1).upper() + (f" {mh.group(2).title()}" if mh.group(2) else '')
            else:
                head_pretty = head.upper()
            return (head_pretty + (f" {tail}" if tail else '')).strip()

        def _pretty_finish(raw: str) -> str:
            f = (raw or '').strip()
            if not f or f.lower() == 'standard':
                return ''
            fk = _norm_key(f)
            if fk and fk in select_header_map:
                return select_header_map[fk]
            return f.replace('_', ' ').replace('-', ' ').title()

        def _pretty_color(md: dict) -> str:
            candidates = []
            hint = (md.get('colorHint') or '').strip()
            if hint:
                candidates.append(hint)
            container = (md.get('containerPartNumber') or '').strip()
            if container:
                for tok in re.findall(r'\b[A-Z]{3,}(?:_[A-Z]{3,})+\b', container):
                    candidates.append(tok)
                candidates.append(container)
            for c in candidates:
                k = _norm_key(c)
                if not k:
                    continue
                if k in select_header_map:
                    return select_header_map[k]
                if k in localized_color_map:
                    return localized_color_map[k]
                if k in localized_finish_map:
                    return localized_finish_map[k]
            if hint:
                return hint.replace('-', ' ').title()
            return ''

        labels: Dict[str, str] = {}
        for sku, sku_data in skus.items():
            if not isinstance(sku_data, dict):
                continue
            md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
            size = _pretty_size(sku_data.get('dimensionScreensize') or '')
            proc = _pretty_proc(md.get('processor') or '')
            finish = _pretty_finish(md.get('displayFinish') or '')
            color = _pretty_color(md)

            parts = [base_name]
            if size:
                parts.append(size)
            if color:
                parts.append(color)
            if proc:
                parts.append(proc)
            if finish:
                parts.append(finish)
            label = ' '.join([p for p in parts if p]).strip()
            if not label or label == base_name:
                label = f"{base_name} ({sku})"
            labels[sku] = label

        inv: Dict[str, int] = {}
        for v in labels.values():
            inv[v] = inv.get(v, 0) + 1
        for sku, label in labels.items():
            if inv.get(label, 0) > 1 and f"({sku})" not in label:
                labels[sku] = f"{label} ({sku})"

        for sku, sku_data in skus.items():
            if isinstance(sku_data, dict):
                sku_data['name'] = labels.get(sku, sku_data.get('name', ''))

        return skus


# ---------------------------------------------------------------------------
# iPhone Handler
# ---------------------------------------------------------------------------

class IPhoneHandler(FamilyHandler):
    """iPhone: variant anchor validation (capacity,color -> size) checks."""

    def validate(self, skus: dict, html: str, region_code: str,
                 family: str, token: str) -> None:
        if not skus or not html:
            return

        expected_combo_sizes: Dict[Tuple[str, str], set] = {}
        for m in re.finditer(r'/(?:[a-z-]{2,5}/)?shop/buy-iphone/iphone-[-a-z0-9_]+/([0-9],[0-9])%22-display-([0-9]+(?:tb|gb))[-]([a-z0-9\-äöüß]+)', html, re.IGNORECASE):
            size_raw = m.group(1)
            cap_raw = m.group(2).lower()
            col_raw = m.group(3).lower()
            size_key = size_raw.replace(',', '_') + 'inch'
            cap_disp = (cap_raw[:-2].upper() + ('TB' if cap_raw.endswith('tb') else 'GB'))
            col_norm = re.sub(r'\s+', ' ', col_raw.replace('-', ' ')).strip().lower()
            expected_combo_sizes.setdefault((cap_disp, col_norm), set()).add(size_key)

        actual_combo_sizes: Dict[Tuple[str, str], set] = {}
        for sku, sku_data in skus.items():
            if not isinstance(sku_data, dict):
                continue
            cap = (sku_data.get('capacity') or '').strip().upper().replace(' ', '')
            col = (sku_data.get('colorDisplay') or '').strip().lower()
            col = re.sub(r'\s+', ' ', col)
            size = (sku_data.get('dimensionScreensize') or '').strip()
            if cap and col and size:
                actual_combo_sizes.setdefault((cap, col), set()).add(size)

        for key, sizes in expected_combo_sizes.items():
            have = actual_combo_sizes.get(key, set())
            if have != sizes:
                if not have:
                    print(f"[warn] missing_combo_for_region {region_code} {family}:{token} combo={key} expected_sizes={sorted(list(sizes))} but found none")
                else:
                    missing = sorted(list(sizes - have))
                    extra = sorted(list(have - sizes))
                    print(f"[warn] combo_size_difference {region_code} {family}:{token} combo={key} expected_sizes={sorted(list(sizes))} actual_sizes={sorted(list(have))} missing={missing} extra={extra}")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _pretty_token_name(display_name: str, token: str) -> str:
    """Convert display_name + token -> pretty name. e.g. 'Apple Watch' + 'apple-watch-ultra' -> 'Apple Watch Ultra'."""
    t = token
    fam_slug = display_name.lower().replace(' ', '')
    if t.lower().startswith(fam_slug + "-"):
        t = t[len(fam_slug) + 1:]
    parts = [p for p in t.split('-') if p]
    pretty = ''.join(p.capitalize() for p in parts)
    return f"{display_name} {pretty}".strip() if pretty else display_name


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, type] = {
    'IPhoneHandler': IPhoneHandler,
    'WatchHandler': WatchHandler,
    'MacHandler': MacHandler,
}


def get_handler(family_config: dict | None) -> FamilyHandler:
    name = (family_config or {}).get('handler')
    if name and name in _HANDLERS:
        return _HANDLERS[name](family_config or {})
    if name:
        print(f"[warn] No handler registered for '{name}' — using no-op base handler")
    return FamilyHandler(family_config or {})