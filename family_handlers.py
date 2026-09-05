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
        chunk = html[m.end(): m.end() + 8000]
        for km in kv_re.finditer(chunk):
            raw_key, raw_val = km.group(1), km.group(2)
            if not raw_key or not raw_val:
                continue
            if raw_key in ('title', 'variantOrder', 'variantSortOrder'):
                continue
            key_norm = re.sub(r'[^a-z0-9]', '', raw_key.lower())
            val_clean = re.sub(r'<[^>]+>', '', raw_val).strip()
            val_clean = val_clean.split('\n')[0].strip()
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
        # Build unique display names from caseSize + caseMaterial + color + connectivity
        for sku_key, sku_md in skus.items():
            if not isinstance(sku_md, dict):
                continue
            md = sku_md.get('metadata') if isinstance(sku_md.get('metadata'), dict) else {}
            parts = [watch_display or (sku_md.get('familyName') or '').strip()]
            case_size = (sku_md.get('dimensionScreensize') or md.get('caseSize') or '').strip()
            if case_size:
                parts.append(case_size)
            conn = (md.get('connectivity') or '').strip()
            if conn:
                parts.append(conn)
            case_mat = (md.get('caseMaterial') or '').strip()
            if case_mat:
                parts.append(case_mat)
            color = (sku_md.get('colorDisplay') or '').strip()
            if color:
                parts.append(color)
            if len(parts) > 1:
                sku_md['name'] = ' '.join(p for p in parts if p)

        # Drop stray SKUs from cross-regional ld+json
        bs_products = set()
        bs = (payload.get('bootstrap') or {}) if isinstance(payload, dict) else {}
        for p in (bs.get('productSelectionData', {}) or {}).get('products', []):
            if isinstance(p, dict):
                pn = (p.get('partNumber') or p.get('btrOrFdPartNumber') or '').strip()
                if pn:
                    bs_products.add(pn)
                    base = p.get('basePartNumber') or pn[:6]
                    bs_products.add(base)
        if bs_products:
            kept = {k: skus[k] for k in skus if k in bs_products or any(k.startswith(bp) for bp in bs_products if len(bp) >= 4)}
            dropped = len(skus) - len(kept)
            if dropped:
                skus = kept
                print(f"[debug][watch] Dropped {dropped} stray SKU(s) — kept {len(skus)} matching bootstrap products")

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

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        """Enrich SKUs with dimensions (color, capacity, processor, etc.) from page bootstrap."""
        if not skus or not payload:
            return skus

        bs = payload.get('bootstrap')
        if not isinstance(bs, dict):
            return skus

        # Extract all dimension display value mappings from mainDisplayValues in raw HTML.
        # Returns { dimensionKey: { valueKey: header } }
        # e.g. {"chassis-dimensionColor": {"blush": "Rosa"}, "processor-dimensionChip": {"m6": "M6 Chip", ...}}
        dim_displays = self._extract_main_display_values(payload.get('html', ''))

        psd = bs.get('productSelectionData') or {}
        products = psd.get('products') or []

        pn_to_display: dict = {}  # pn -> { dimensionKey: displayValue }
        pn_to_processor: dict = {}
        pn_to_container: dict = {}

        for p in products:
            if not isinstance(p, dict):
                continue
            pn = p.get('btrOrFdPartNumber') or p.get('partNumber')
            if not isinstance(pn, str) or not pn:
                continue
            dims = p.get('dimensions') if isinstance(p.get('dimensions'), dict) else {}
            displays: dict = {}
            for dk, dv in dims.items():
                if not isinstance(dv, str) or not dv:
                    continue
                header = (dim_displays.get(dk) or {}).get(dv.lower())
                if header:
                    displays[dk] = header
            # Processor chip name from raw dimension value (e.g. m5pro -> "M5 Pro", m4_8c_cpu_8c_gpu -> "M4 (8C GPU)")
            proc_disp = ''
            chip_dim = dims.get('processor-dimensionChip') or ''
            core_dim = dims.get('processor-dimensionChip-cpuCoreCount-gpuCoreCount') or ''
            if chip_dim:
                m_chip = re.match(r'm(\d+)(pro|max|ultra)?(?:_(\d+)c_cpu_(\d+)c_gpu)?', chip_dim, re.IGNORECASE)
                if m_chip:
                    proc_disp = 'M' + m_chip.group(1)
                    if m_chip.group(2):
                        proc_disp += ' ' + m_chip.group(2).title()
                    if m_chip.group(4):
                        proc_disp += ' (' + m_chip.group(4) + 'C GPU)'
                    # If inline core count missing but detailed dim available, extract from it
                    if not m_chip.group(3) and core_dim:
                        m_core = re.match(r'm\d+(?:pro|max|ultra)?-(\d+)-(\d+)', core_dim, re.IGNORECASE)
                        if m_core:
                            proc_disp += ' (' + m_core.group(1) + '-Core CPU / ' + m_core.group(2) + '-Core GPU)'
            if not proc_disp:
                # Fallback: derive from cpuCoreCount-gpuCoreCount (e.g., "8-8" or "10-10")
                core_dim2 = core_dim or dims.get('processor-cpuCoreCount-gpuCoreCount') or ''
                if core_dim2 and '-' in core_dim2:
                    parts = core_dim2.split('-')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        proc_disp = f'{parts[0]}-Core CPU / {parts[1]}-Core GPU'
            if displays:
                pn_to_display.setdefault(pn, displays)
            if proc_disp:
                pn_to_processor.setdefault(pn, proc_disp)
            container = p.get('aosContainerPartNumber') or ''
            if container:
                pn_to_container.setdefault(pn, container)

        if not pn_to_display and not pn_to_processor:
            return skus

        applied = 0
        for sku, sku_data in list(skus.items()):
            if not isinstance(sku_data, dict):
                continue
            # Try direct match first, then base-part match
            displays = pn_to_display.get(sku)
            proc_disp = pn_to_processor.get(sku)
            container = pn_to_container.get(sku)
            if not displays and not proc_disp:
                m_base = re.match(r'^([A-Z0-9]{3,6})', sku)
                if m_base:
                    base = m_base.group(1)
                    for pn_key, disp_val in pn_to_display.items():
                        if pn_key.startswith(base):
                            displays = disp_val
                            break
                    for pn_key, proc_val in pn_to_processor.items():
                        if pn_key.startswith(base):
                            proc_disp = proc_val
                            break
                    for pn_key, cont_val in pn_to_container.items():
                        if pn_key.startswith(base):
                            container = cont_val
                            break
            changed = False
            md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}

            # Processor chip name (already resolved via direct or base-part lookup above)
            if proc_disp and not md.get('processorDisplay'):
                md['processorDisplay'] = proc_disp
                changed = True

            if container:
                md.setdefault('containerPartNumber', container)

            if not displays:
                if md:
                    sku_data['metadata'] = md
                if changed:
                    applied += 1
                continue

            # Color
            cd = displays.get('chassis-dimensionColor')
            if cd and not (sku_data.get('colorDisplay') or '').strip():
                sku_data['colorDisplay'] = cd
                sku_data['colorKey'] = re.sub(r'[^a-z0-9]', '', cd.lower())
                changed = True

            # Storage capacity — sanitize HTML entities and trailing text before matching
            cap = displays.get('storage-dimensionCapacity')
            if cap and not (sku_data.get('capacity') or '').strip():
                cap = re.sub(r'&nbsp;', ' ', cap)
                cap = re.sub(r'&[a-zA-Z0-9#]+;', '', cap)
                cap = re.sub(r'<[^>]+>', '', cap)
                cap = cap.strip()
                m_cap = re.match(r'(\d+)\s*(GB|TB)', cap, re.IGNORECASE)
                if m_cap:
                    sku_data['capacity'] = m_cap.group(1) + m_cap.group(2).upper()
                    changed = True

            if md:
                sku_data['metadata'] = md
            if changed:
                applied += 1

        if applied:
            print(f"[debug][mac] Enriched {applied} SKU(s) with color/capacity/processor from page data")

        return skus

    def _extract_main_display_values(self, html: str) -> dict:
        """Parse mainDisplayValues from raw HTML into {dim: {val: header}}."""
        result: dict = {}
        if not html:
            return result

        for m_mdv in re.finditer(r'"mainDisplayValues"\s*:\s*\{', html):
            brace = m_mdv.end() - 1
            mdv_block = self._extract_balanced_braces(html, brace)
            if not mdv_block:
                continue
            inner = mdv_block[1:-1]
            pos = 0
            while pos < len(inner):
                m_key = re.match(r'\s*"([^"]+)"\s*:\s*\{', inner[pos:])
                if not m_key:
                    pos += 1
                    continue
                dim_key = m_key.group(1)
                dim_brace = pos + m_key.end() - 1
                dim_block = self._extract_balanced_braces(inner, dim_brace)
                if dim_block:
                    dim_inner = dim_block[1:-1]
                    dim_pos = 0
                    values: dict = {}
                    while dim_pos < len(dim_inner):
                        m_val = re.match(r'\s*"([^"]+)"\s*:\s*\{', dim_inner[dim_pos:])
                        if not m_val:
                            dim_pos += 1
                            continue
                        val_key = m_val.group(1)
                        if val_key in ('variantOrder', 'title'):
                            dim_pos += m_val.end()
                            continue
                        val_entry = self._extract_balanced_braces(dim_inner, dim_pos + m_val.end() - 1)
                        if val_entry:
                            hdr = re.search(r'"header"\s*:\s*"((?:[^"\\]|\\.)*)"', val_entry)
                            if hdr:
                                raw_hdr = re.sub(r'<[^>]*>', '', hdr.group(1)).replace('&nbsp;', ' ').strip()
                                values[val_key.lower()] = raw_hdr
                            dim_pos = dim_pos + m_val.end() - 1 + len(val_entry)
                        else:
                            dim_pos += m_val.end()
                    if values:
                        result[dim_key] = values
                    pos = dim_brace + len(dim_block)
                else:
                    pos += m_key.end()
        return result

    def _extract_balanced_braces(self, text: str, start: int) -> str | None:
        """Return balanced { … } block starting at `start` (inclusive)."""
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        html = payload.get('html', '')
        base_name = (inferred_display or '').strip()
        if not base_name:
            base_name = family_config.get('display_name', 'Mac')
        # Clean "Shop "/"Buy "/"Kaufen " prefixes from inferred display
        base_name = re.sub(r'^(Shop|Buy|Kaufen|Acheter|Comprar|Comprare|Kopen|Köp|Osta|購買|購入|구매|选购|立即选购)\s+', '', base_name, flags=re.IGNORECASE).strip()

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

        def _pretty_color(md: dict, sku_data: dict | None = None) -> str:
            # Prefer colorDisplay already extracted from page by enrich_skus
            if sku_data and (sku_data.get('colorDisplay') or '').strip():
                return sku_data['colorDisplay'].strip()
            # Fallback: colorHint from metadata (set by BTO extraction)
            hint = (md.get('colorHint') or '').strip()
            if hint:
                return hint.replace('-', ' ').title()
            return ''

        labels: Dict[str, str] = {}
        color_info: Dict[str, str] = {}
        for sku, sku_data in skus.items():
            if not isinstance(sku_data, dict):
                continue
            md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
            size = _pretty_size(sku_data.get('dimensionScreensize') or '')
            proc_raw = _pretty_proc(md.get('processor') or '')
            proc = proc_raw or (md.get('processorDisplay') or '').replace(' Chip', '')

            finish = _pretty_finish(md.get('displayFinish') or '')
            color = _pretty_color(md, sku_data)
            cap = (sku_data.get('capacity') or '').strip()

            parts = [base_name]
            if size:
                parts.append(size)
            if color:
                parts.append(color)
            if cap:
                parts.append(cap)
            if proc:
                parts.append(proc)
            if finish:
                parts.append(finish)
            label = ' '.join([p for p in parts if p]).strip()
            if not label or label == base_name:
                label = base_name
            labels[sku] = label
            if color:
                color_info[sku] = color

        inv: Dict[str, int] = {}
        for v in labels.values():
            inv[v] = inv.get(v, 0) + 1
        for sku, label in labels.items():
            if inv.get(label, 0) > 1 and f"({sku})" not in label:
                labels[sku] = f"{label} ({sku})"

        for sku, sku_data in skus.items():
            if isinstance(sku_data, dict):
                sku_data['name'] = labels.get(sku, sku_data.get('name', ''))
                c = color_info.get(sku, '')
                if c and not (sku_data.get('colorDisplay') or '').strip():
                    sku_data['colorDisplay'] = c
                    sku_data['colorKey'] = _norm_key(c)

        return skus


# ---------------------------------------------------------------------------
# iPhone Handler
# ---------------------------------------------------------------------------

class IPhoneHandler(FamilyHandler):
    """iPhone: variant anchor validation + color translation."""

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        """Translate colorDisplay using dimensionColor mappings from page HTML."""
        if not skus or not payload:
            return skus
        html = payload.get('html', '')
        if not html:
            return skus

        color_map = {}
        for m in re.finditer(r'"dimensionColor"\s*:\s*\{', html):
            block = html[m.end(): m.end() + 4000]
            for kv in re.finditer(r'"([a-z0-9_]+)"\s*:\s*\{[^}]*?"(?:value|header)"\s*:\s*"([^"]+)"', block, re.IGNORECASE):
                key, val = kv.group(1), kv.group(2)
                if key not in ('title', 'variantOrder', 'variantSortOrder'):
                    color_map[key.lower()] = re.sub(r'&nbsp;', ' ', val)
                    color_map[key.lower()] = re.sub(r'<[^>]+>', '', color_map[key.lower()]).strip()

        applied = 0
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            cd = (v.get('colorDisplay') or '').strip()
            ck = (v.get('colorKey') or '').strip() or cd.lower().replace(' ', '')
            translated = color_map.get(ck) or color_map.get(cd.lower().replace(' ', ''))
            if translated and translated != cd:
                v['colorDisplay'] = translated
                v['colorKey'] = ck
                applied += 1

        if applied:
            print(f"[debug][iphone] Translated {applied} color(s) from page data")
        return skus

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
    # Also try the singular slug in case display_name has spaces
    disp_slug = display_name.lower().replace(' ', '-')
    if t.lower().startswith(disp_slug + "-"):
        t = t[len(disp_slug) + 1:]
    parts = [p for p in t.split('-') if p]
    pretty = ''.join(p.capitalize() for p in parts)
    return f"{display_name} {pretty}".strip() if pretty else display_name


# ---------------------------------------------------------------------------
# AVP Handler
# ---------------------------------------------------------------------------

class AVPHandler(FamilyHandler):
    """Apple Vision Pro: filter accessories, enrich with capacity names."""

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        # Filter out Zeiss inserts and accessories — it's not an actual AVP unless it has capacity
        before = len(skus)
        skus = {
            k: v for k, v in skus.items()
            if isinstance(v, dict) and (v.get('capacity') or '').strip()
        }
        dropped = before - len(skus)
        if dropped:
            print(f"[debug][avp] Dropped {dropped} accessory/Zeiss SKU(s) (no capacity)")

        # Enrich names with capacity
        display = inferred_display or family_config.get('display_name', 'Apple Vision Pro')
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            cap = (v.get('capacity') or '').strip()
            name = (v.get('name') or '').strip()
            if cap and (not name or name.lower() == display.lower()):
                v['name'] = f'{display} {cap}'

        return skus


# ---------------------------------------------------------------------------
# AirPods Handler
# ---------------------------------------------------------------------------

class AirPodsHandler(FamilyHandler):
    """AirPods: extract dimension from bootstrap + enrich names."""

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        """Pull dimensionActiveNoiseCancellation / dimensionColor from bootstrap products."""
        if not skus or not payload:
            return skus

        bs = payload.get('bootstrap')
        if not isinstance(bs, dict):
            return skus

        psd = bs.get('productSelectionData') or {}
        products = psd.get('products') or []
        dv = psd.get('displayValues') or {}
        html = payload.get('html', '')

        pn_to_dim: dict = {}  # pn -> dimension value string
        for p in products:
            if not isinstance(p, dict):
                continue
            pn = p.get('partNumber') or p.get('btrOrFdPartNumber')
            if not pn:
                continue
            # Extract dimension* keys directly from product (AirPods has top-level dims)
            dims = {k: v for k, v in p.items() if k.startswith('dimension') and isinstance(v, str)}
            if dims:
                pn_to_dim[pn] = dims

        if not pn_to_dim:
            return skus

        # Build dimension-key → human-readable header from displayValues
        dim_headers: Dict[str, Dict[str, str]] = {}
        for dk, dv_data in dv.items():
            if not dk.startswith('dimension') or not isinstance(dv_data, dict):
                continue
            headers: Dict[str, str] = {}
            for vk, vv in dv_data.items():
                if isinstance(vv, dict):
                    h = re.sub(r'&nbsp;', ' ', (vv.get('header') or vv.get('value') or ''))
                    h = re.sub(r'<[^>]+>', '', h).strip()
                    if h and vk not in ('title', 'variantOrder', 'variantSortOrder'):
                        headers[vk] = h
            if headers:
                dim_headers[dk] = headers

        applied = 0
        for sku, sku_data in list(skus.items()):
            if not isinstance(sku_data, dict):
                continue
            dims = pn_to_dim.get(sku)
            if not dims:
                # Try base-part match
                for pn, dims2 in pn_to_dim.items():
                    if sku.startswith(pn[:4]):
                        dims = dims2
                        break
            if not dims:
                continue

            for dk, dv_val in dims.items():
                if not isinstance(dv_val, str) or not dv_val:
                    continue
                headers = dim_headers.get(dk, {})
                header = headers.get(dv_val.lower(), '')
                if not header:
                    # Try fuzzy: withoutactivenoisecancellation or without-active-noise
                    for hk, hv in headers.items():
                        if dv_val.replace('-', '') == hk.replace('-', ''):
                            header = hv
                            break
                if not header:
                    # Fallback: title-case the raw dimension value (e.g., "midnight" → "Midnight")
                    header = dv_val.replace('_', ' ').replace('-', ' ').title()
                md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
                md[dk] = header
                sku_data['metadata'] = md
                applied += 1

        if applied:
            print(f"[debug][airpods] Enriched {applied} SKU(s) with dimension headers from bootstrap")
        return skus

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        display = inferred_display or family_config.get('display_name', 'AirPods')
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            name = (v.get('name') or '').strip()
            if not name or name.lower() == 'airpods':
                v['name'] = display

            # Override name with dimension header if available (e.g., "AirPods 4 with Active Noise Cancellation")
            md = v.get('metadata') if isinstance(v.get('metadata'), dict) else {}
            for dk, dv in sorted(md.items()):
                if dk.startswith('dimension') and isinstance(dv, str) and dv.strip():
                    v['name'] = dv
                    break

# Drop stray SKUs: if bootstrap has products, keep only matching SKUs
        bs_products = set()
        bs = (payload.get('bootstrap') or {}) if isinstance(payload, dict) else {}
        for p in (bs.get('productSelectionData', {}) or {}).get('products', []):
            if isinstance(p, dict):
                pn = (p.get('partNumber') or p.get('btrOrFdPartNumber') or '').strip()
                if pn:
                    bs_products.add(pn)
                    base = p.get('basePartNumber') or pn[:6]
                    bs_products.add(base)
        if bs_products and len(bs_products) > 1:
            kept = {}
            for k in skus:
                if k in bs_products or any(k.startswith(bp) for bp in bs_products if len(bp) >= 4):
                    kept[k] = skus[k]
            dropped = len(skus) - len(kept)
            if dropped:
                skus = kept
                print(f"[debug][airpods] Dropped {dropped} cross-regional stray SKU(s) — kept {len(skus)} matching bootstrap products")

        return skus


# ---------------------------------------------------------------------------
# HomePod Handler
# ---------------------------------------------------------------------------

class HomePodHandler(FamilyHandler):
    """HomePod: enrich colorDisplay from page data, then enrich name."""

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        """Translate colorDisplay using dimensionColor mappings from page HTML."""
        if not skus or not payload:
            return skus
        html = payload.get('html', '')
        if not html:
            return skus

        # Extract dimensionColor mappings from the page:
        # Apple pages embed mapped color names like {"midnight": {"value": "Mitternacht"}, ...}
        color_map = {}
        for m in re.finditer(r'"dimensionColor"\s*:\s*\{', html):
            block = html[m.end(): m.end() + 3000]
            for kv in re.finditer(r'"([a-z0-9_]+)"\s*:\s*\{[^}]*?\"(?:value|header)\"\s*:\s*\"([^"]+)"', block, re.IGNORECASE):
                key, val = kv.group(1), kv.group(2)
                if key not in ('title', 'variantOrder', 'variantSortOrder'):
                    color_map[key.lower()] = val

        applied = 0
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            cd = (v.get('colorDisplay') or '').strip()
            ck = (v.get('colorKey') or '').strip() or cd.lower()
            translated = color_map.get(ck.lower()) or color_map.get(cd.lower())
            if translated and translated != cd:
                v['colorDisplay'] = translated
                v['colorKey'] = ck
                applied += 1

        if applied:
            print(f"[debug][homepod] Translated {applied} colorDisplay(s) from page data")
        return skus

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        display = inferred_display or family_config.get('display_name', 'HomePod')
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            name = (v.get('name') or '').strip()
            color = (v.get('colorDisplay') or '').strip()
            if color and (not name or name.lower() == display.lower()):
                v['name'] = f'{display} {color}'

        # Drop stray SKUs from cross-regional ld+json
        bs_products = set()
        bs = (payload.get('bootstrap') or {}) if isinstance(payload, dict) else {}
        for p in (bs.get('productSelectionData', {}) or {}).get('products', []):
            if isinstance(p, dict):
                pn = (p.get('partNumber') or p.get('btrOrFdPartNumber') or '').strip()
                if pn:
                    bs_products.add(pn)
                    base = p.get('basePartNumber') or pn[:6]
                    bs_products.add(base)
        if bs_products:
            kept = {}
            for k in skus:
                if k in bs_products or any(k.startswith(bp) for bp in bs_products if len(bp) >= 4):
                    kept[k] = skus[k]
            dropped = len(skus) - len(kept)
            if dropped:
                skus = kept
                print(f"[debug][homepod] Dropped {dropped} stray SKU(s) — kept {len(skus)} matching bootstrap products")

        return skus


# ---------------------------------------------------------------------------
# iPad Handler
# ---------------------------------------------------------------------------

class IPadHandler(FamilyHandler):
    """iPad: translate colors/finishes/sizes from bootstrap displayValues, then build names."""

    def enrich_skus(self, skus: dict, payload: dict, region: dict) -> dict:
        """Extract dimensionColor/dimensionFinish/dimensionScreensize translations."""
        if not skus or not payload:
            return skus

        bs = (payload.get('bootstrap') or {}) if isinstance(payload, dict) else {}
        if not isinstance(bs, dict):
            return skus

        psd = bs.get('productSelectionData') or {}
        products = psd.get('products') or []
        dv = psd.get('displayValues') or {}

        dm_headers: Dict[str, Dict[str, str]] = {}
        for dk in ('dimensionColor', 'dimensionFinish', 'dimensionScreensize'):
            raw = dv.get(dk) if isinstance(dv, dict) else None
            if not isinstance(raw, dict):
                continue
            headers: Dict[str, str] = {}
            for vk, vv in raw.items():
                if isinstance(vv, dict) and vk not in ('title', 'variantOrder', 'variantSortOrder'):
                    h = (vv.get('header') or vv.get('value') or '')
                    h = re.sub(r'&nbsp;', ' ', h)
                    h = re.sub(r'<[^>]+>', '', h).strip()
                    h = h.split('\n')[0].strip()
                    # Truncate at stray HTML fragments
                    h = re.sub(r'<[^>]*$', '', h).strip()
                    if h:
                        headers[vk] = h
            if headers:
                dm_headers[dk] = headers

        # Fallback: extract select-header color translations from HTML
        html = payload.get('html', '') if isinstance(payload, dict) else ''
        sel_headers = extract_select_header_mappings_from_html(html) if html else {}
        if sel_headers:
            dm_headers.setdefault('dimensionColor', {}).update(sel_headers)

        # Additional fallback: extract dimensionColor from raw HTML (some translations only on page, not in bootstrap)
        html_dc = extract_display_value_mappings_from_html(html, 'dimensionColor') if html else {}
        if html_dc:
            dm_headers.setdefault('dimensionColor', {}).update(html_dc)

        # Product-level dims: pn -> {dimensionColor: spaceblack, dimensionFinish: glossy, ...}
        pn_to_dims: Dict[str, Dict[str, str]] = {}
        for p in products:
            if not isinstance(p, dict):
                continue
            pn = p.get('partNumber') or p.get('btrOrFdPartNumber')
            if not pn:
                continue
            dims = {k: v for k, v in p.items() if k.startswith('dimension') and isinstance(v, str)}
            if dims:
                pn_to_dims[pn] = dims

        applied = 0
        for sku, sku_data in skus.items():
            if not isinstance(sku_data, dict):
                continue
            pd = pn_to_dims.get(sku)
            if not pd:
                for pn, dims2 in pn_to_dims.items():
                    if sku.startswith(pn[:4]):
                        pd = dims2
                        break
            if not pd:
                continue

            for dk, raw_val in pd.items():
                headers = dm_headers.get(dk, {})
                translated = headers.get(raw_val.lower(), '')
                if translated and translated != raw_val:
                    if dk == 'dimensionColor':
                        sku_data['colorDisplay'] = translated
                        sku_data['colorKey'] = raw_val.lower()
                    elif dk == 'dimensionFinish':
                        md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
                        md['displayFinish'] = translated
                        sku_data['metadata'] = md
                    elif dk == 'dimensionScreensize':
                        md = sku_data.get('metadata') if isinstance(sku_data.get('metadata'), dict) else {}
                        md['displaySize'] = translated
                        sku_data['metadata'] = md
                    applied += 1

        # Direct colorDisplay translation (covers SKUs without product-level dims)
        color_headers = dm_headers.get('dimensionColor', {})
        if color_headers:
            # Normalize header keys for matching
            norm_headers = {re.sub(r'[^a-z0-9]', '', k): v for k, v in color_headers.items()}
            for sku, sku_data in skus.items():
                if not isinstance(sku_data, dict):
                    continue
                cd = (sku_data.get('colorDisplay') or '').strip()
                ck = (sku_data.get('colorKey') or '').strip()
                lookup = re.sub(r'[^a-z0-9]', '', (ck or cd).lower())
                translated = norm_headers.get(lookup) or color_headers.get(ck) or color_headers.get(cd.lower())
                if translated:
                    translated = re.sub(r'&nbsp;', ' ', translated)
                    translated = re.sub(r'<[^>]+>', '', translated).strip()
                    translated = translated.split('\n')[0].strip()
                if translated and translated != cd:
                    sku_data['colorDisplay'] = translated
                    applied += 1

        if applied:
            print(f"[debug][ipad] Translated {applied} dimension(s) from bootstrap data")
        return skus

    def post_process_skus(self, skus: dict, payload: dict, token: str,
                          inferred_display: str | None, family_config: dict) -> dict:
        if not skus:
            return skus

        display = inferred_display or family_config.get('display_name', 'iPad')
        # Strip any existing size prefix from display (e.g., "11\" iPad Air" → "iPad Air")
        display_clean = re.sub(r'^\d+["\u2033\u201d\u201c”“\-]+\s+', '', display).strip() or display
        # Extract SKU-to-connectivity mapping from page HTML
        html = payload.get('html', '') if isinstance(payload, dict) else ''
        pn_to_conn: Dict[str, str] = {}
        if html:
            for m in re.finditer(r'\"dimensionConnection\"\s*:\s*\"(wifi|wificell)\"', html, re.IGNORECASE):
                # Look for SKU nearby (within 600 chars after)
                window = html[m.end():m.end() + 600]
                for sku_m in re.finditer(r'"(MH[A-Z0-9]{2,7})(?:[A-Z]{1,3}/[A-Z])?"', window):
                    conn = 'Cellular' if m.group(1).lower() == 'wificell' else 'Wi-Fi'
                    pn_to_conn.setdefault(sku_m.group(1), conn)
        for k, v in skus.items():
            if not isinstance(v, dict):
                continue
            # Always rebuild name from dimensions for any SKU that has them — translatable fields
            size_raw = (v.get('dimensionScreensize') or '').strip()
            cap = (v.get('capacity') or '').strip()
            color = (v.get('colorDisplay') or '').strip()
            conn = pn_to_conn.get(k[:6], '')
            md = v.get('metadata') if isinstance(v.get('metadata'), dict) else {}
            finish = md.get('displayFinish', '')
            has_dims = bool(size_raw or cap or color or finish)

            if has_dims:
                size_label = ''
                if size_raw:
                    m_sz = re.match(r'^(\d+)inch$', size_raw, re.IGNORECASE)
                    if m_sz:
                        size_label = f'{m_sz.group(1)}-inch '
                cap = re.sub(r'\s+(GB|TB)', r'\1', cap, flags=re.IGNORECASE)
                cap = re.sub(r'\s+(?:Speicher|storage|Stockage|Memoria)', '', cap, flags=re.IGNORECASE).strip()
                cap = re.sub(r'&nbsp;', ' ', cap)
                cap = re.sub(r'<[^>]+>', '', cap).strip()
                parts = [size_label + display_clean if size_label else display_clean]
                if conn:
                    parts.append(conn)
                if cap:
                    parts.append(cap)
                if finish and finish.lower() != 'standardglas':
                    parts.append(finish)
                if color:
                    parts.append(color)
                v['name'] = ' '.join(parts)

        # Drop stray SKUs from cross-regional ld+json
        bs_products = set()
        bs = (payload.get('bootstrap') or {}) if isinstance(payload, dict) else {}
        if isinstance(bs, dict):
            if bs.get('productSelectionData', {}) or {}:
                sd = bs.get('productSelectionData', {}) or {}
                for p in sd.get('products', []) if isinstance(sd, dict) else []:
                    if isinstance(p, dict):
                        pn = (p.get('partNumber') or p.get('btrOrFdPartNumber') or '').strip()
                        if pn:
                            bs_products.add(pn)
                            bs_products.add(p.get('basePartNumber') or pn[:6])
                if bs_products:
                    kept = {k: skus[k] for k in skus if k in bs_products or any(k.startswith(bp) for bp in bs_products if len(bp) >= 4)}
                    dropped = len(skus) - len(kept)
                    if dropped:
                        skus = kept
                        print(f"[debug][ipad] Dropped {dropped} stray SKU(s) — kept {len(skus)} matching bootstrap products")

        return skus


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, type] = {
    'IPhoneHandler': IPhoneHandler,
    'WatchHandler': WatchHandler,
    'MacHandler': MacHandler,
    'AVPHandler': AVPHandler,
    'AirPodsHandler': AirPodsHandler,
    'HomePodHandler': HomePodHandler,
    'IPadHandler': IPadHandler,
}


def get_handler(family_config: dict | None) -> FamilyHandler:
    name = (family_config or {}).get('handler')
    if name and name in _HANDLERS:
        return _HANDLERS[name](family_config or {})
    if name:
        print(f"[warn] No handler registered for '{name}' — using no-op base handler")
    return FamilyHandler(family_config or {})