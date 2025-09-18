#!/usr/bin/env python3
"""
Entry-point driven Apple models scraper (per-model JSON emitter)

- Config provides regions and category entrypoints (e.g., shop/buy-iphone)
- We discover model tokens by crawling entrypoints per region
- We scrape each model and emit one JSON per model token: <Family>Models-<token>-intl.json
- Supports targeted updates via CLI: --family, --token, --countries
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List, Tuple, Optional

import requests

DEFAULT_CONFIG_PATH = "scraper_config.json"
UA = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

class Scraper:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.session = requests.Session()
        self.session.headers.update(UA)
        self.config = self._load_config(config_path)

    def _load_config(self, path: str) -> dict:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[warn] failed to read config at {path}: {e}")
            # Minimal fallback
            return {
                "regions": [
                    {"name": "US", "code": "US", "url_prefix": "https://www.apple.com/"}
                ],
                "categories": [
                    {"family": "iphone", "entrypoints": ["shop/buy-iphone"]}
                ]
            }

    def _regions(self, codes: Optional[List[str]]) -> List[dict]:
        regions = self.config.get("regions", [])
        if not codes:
            return regions
        code_set = {c.upper() for c in codes}
        return [r for r in regions if r.get("code", "").upper() in code_set]

    def _categories(self, family: Optional[str]) -> List[dict]:
        cats = self.config.get("categories", [])
        if family:
            fam = family.lower()
            return [c for c in cats if c.get("family", "").lower() == fam]
        return cats

    def discover_models(self, family: str, region: dict) -> Dict[str, str]:
        """
        Return mapping: token -> shop_path for the given family in a region.
        """
        entrypoints = []
        for cat in self._categories(family):
            entrypoints.extend(cat.get("entrypoints", []))
        base = region["url_prefix"].rstrip('/') + '/'
        models: Dict[str, str] = {}
        for ep in entrypoints:
            url = base + ep.lstrip('/')
            try:
                print(f"[discover] GET {url}")
                html = self.session.get(url, timeout=15).text
            except Exception as e:
                print(f"[warn] failed to GET {url}: {e}")
                continue
            # Heuristic: find shop links under the entrypoint path
            # e.g., /shop/buy-iphone/iphone-17-pro
            family_slug = ep.split('/')[-1]
            rx = re.compile(rf"/shop/{re.escape(family_slug)}/([a-z0-9\-]+)", re.IGNORECASE)
            for m in rx.finditer(html):
                token = m.group(1).lower()
                path = f"shop/{family_slug}/{token}"
                models[token] = path
        print(f"[discover] {region['code']}/{family}: found {len(models)} models")
        return models

    def _extract_product_data(self, url: str) -> Optional[dict]:
        try:
            print(f"[scrape] GET {url}")
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            html = resp.text
            # Try metrics JSON first
            m = re.search(r'<script type="application/json" id="metrics">({.*?})</script>', html, re.DOTALL)
            if m:
                try:
                    metrics = json.loads(m.group(1))
                    return {"html": html, "metrics": metrics}
                except Exception:
                    pass
            # Fallback: provide raw html
            return {"html": html}
        except Exception as e:
            print(f"[error] fetch failed: {e}")
            return None

    def _build_skus_from_payload(self, payload: dict) -> Dict[str, dict]:
        html = payload.get("html", "")
        metrics = payload.get("metrics")
        out: Dict[str, dict] = {}
        # Metrics path
        if metrics and isinstance(metrics, dict):
            products = ((metrics.get('data') or {}).get('products')) or []
            for p in products:
                sku = p.get('partNumber')
                name = p.get('name') or ''
                if not sku or not name:
                    continue
                # color & capacity
                color_key = (p.get('dimensionColor') or p.get('color') or '').lower().replace(' ', '')
                color_display = p.get('color') or ''
                if not color_display:
                    mm = re.search(r'"dimensionColor"\s*:\s*"([a-z_]+)"', html)
                    if mm:
                        color_key = mm.group(1)
                        # Try to find display via nearby text
                        mt = re.search(rf'"{re.escape(color_key)}"\s*:\s*\{{[^}}]*?"text"\s*:\s*"([^"]+)"', html, re.DOTALL)
                        if mt:
                            color_display = mt.group(1)
                capacity = p.get('capacity') or p.get('dimensionCapacity') or ''
                family = p.get('family') or p.get('productLocatorFamily') or ''
                family_name = p.get('familyName') or family or ''
                out[sku] = {
                    "name": name,
                    "colorKey": color_key or "unknown",
                    "colorDisplay": color_display or "Unknown",
                    "capacity": capacity or "",
                    "family": family or "unknown",
                    "familyName": family_name or "Unknown"
                }
        # Fallback: scan HTML for part numbers
        if not out:
            for m in re.finditer(r'([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])', html):
                out[m.group(1)] = {"name": "Unknown", "colorKey": "", "colorDisplay": "", "capacity": "", "family": "", "familyName": ""}
        return out

    def _pretty_token_name(self, family: str, token: str) -> str:
        """Convert 'iphone-17-pro' -> '17Pro'; 'iphone-air' -> 'Air'."""
        t = token
        fam = family.lower()
        if t.lower().startswith(fam + "-"):
            t = t[len(fam) + 1:]
        parts = [p for p in t.split('-') if p]
        # TitleCase each segment, but keep numbers as-is
        pretty = ''.join(p.capitalize() for p in parts)
        return pretty or token

    def emit_model_file(self, family: str, token: str, country_to_data: Dict[str, Tuple[str, Dict[str, dict]]]) -> str:
        """
        country_to_data: country_code -> (shop_path, skus_dict)
        """
        discovered: Dict[str, Dict[str, dict]] = {}
        country_mappings: Dict[str, dict] = {}
        for cc, (shop_path, skus) in country_to_data.items():
            cc_l = cc.lower()
            discovered.setdefault(cc_l, {})[token] = {
                "url": None,  # optional PDP url, not required
                "skus": skus
            }
            country_mappings.setdefault(cc_l, {}).setdefault("shop_paths", {})[token] = shop_path
        root = {
            "discovered_models": discovered,
            "country_mappings": country_mappings
        }
        fam_map = {
            'iphone': 'iPhone',
            'watch': 'AppleWatch',
            'mac': 'Mac',
            'ipad': 'iPad',
            'accessories': 'Accessories'
        }
        famTitle = fam_map.get(family.lower(), family.capitalize())
        prettyToken = self._pretty_token_name(family, token)
        fname = f"{famTitle}-{prettyToken}-intl.json"
        # Prefer InventoryWatch/Catalogs/ for organization (avoid confusion with 'Model/')
        out_dir = "InventoryWatch"
        models_dir = os.path.join(out_dir, "Catalogs")
        try:
            if os.path.isdir(out_dir) and not os.path.isdir(models_dir):
                os.makedirs(models_dir, exist_ok=True)
        except Exception:
            pass
        out_path = os.path.join(models_dir if os.path.isdir(models_dir) else (out_dir if os.path.isdir(out_dir) else "."), fname)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False, indent=2)
        print(f"[write] {out_path}")
        return out_path

    def run(self, family: str, tokens: Optional[List[str]], all_models: bool, countries: Optional[List[str]]):
        regions = self._regions(countries)
        if not regions:
            print("[error] no regions configured or matched")
            sys.exit(2)
        # Discover tokens if needed
        seeds: Dict[str, str] = {}  # token -> shop_path (from first region that exposes it)
        if all_models or not tokens:
            for r in regions:
                found = self.discover_models(family, r)
                for t, p in found.items():
                    seeds.setdefault(t, p)
            tokens = list(seeds.keys())
        # Process each token
        for token in tokens or []:
            country_to_data: Dict[str, Tuple[str, Dict[str, dict]]] = {}
            for r in regions:
                shop_path = seeds.get(token)
                if not shop_path:
                    # Discover per-region if not found globally
                    local = self.discover_models(family, r)
                    shop_path = local.get(token)
                    if not shop_path:
                        continue
                base = r["url_prefix"].rstrip('/') + '/'
                url = base + shop_path
                payload = self._extract_product_data(url)
                if not payload:
                    continue
                skus = self._build_skus_from_payload(payload)
                if not skus:
                    continue
                country_to_data[r["code"].upper()] = (shop_path, skus)
            if country_to_data:
                self.emit_model_file(family, token, country_to_data)
            else:
                print(f"[warn] no data for token {token} in selected regions")


def main():
    ap = argparse.ArgumentParser(description="Entry-point driven Apple models scraper (per-model JSON)")
    ap.add_argument('--config', default=DEFAULT_CONFIG_PATH, help='Path to scraper_config.json')
    ap.add_argument('--family', choices=['iphone', 'watch', 'mac', 'ipad', 'accessories'], required=True)
    ap.add_argument('--token', action='append', help='Model token to update (repeatable)')
    ap.add_argument('--all-models', action='store_true', help='Discover and scrape all models for the family')
    ap.add_argument('--countries', help='Comma-separated list of country codes to scrape (e.g., US,AT,UK)')
    args = ap.parse_args()

    countries = [c.strip() for c in (args.countries.split(',') if args.countries else []) if c.strip()]
    s = Scraper(args.config)
    s.run(args.family, args.token, args.all_models, countries)

if __name__ == '__main__':
    main()
