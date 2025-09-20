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
from typing import Any
try:
    # Legacy, more robust extractor (used as a fallback for Watch)
    from scrape_real_apple_skus import RealAppleSkuScraper  # type: ignore
except Exception:
    RealAppleSkuScraper = None  # type: ignore
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
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as he:
                # Downgrade 404 to info: some models are simply not offered in a region
                status = getattr(getattr(he, 'response', None), 'status_code', None)
                if status == 404:
                    print(f"[info] 404 Not Found (not offered in this region): {url}")
                    return None
                # Re-raise other HTTP errors to be handled by the outer except
                raise
            html = resp.text
            # Page title for display-name inference
            title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)
            page_title = title_match.group(1).strip() if title_match else ''
            # Extract JSON blobs from the page
            json_blobs = []
            for script in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
                content = script.group(1).strip()
                if content and ('{' in content or '[' in content):
                    json_blobs.append(content)
            metrics = None
            metrics_match = re.search(r'<script[^>]*id="metrics"[^>]*type="application/json"[^>]*>\s*({.*?})\s*</script>', html, re.DOTALL | re.IGNORECASE)
            if metrics_match:
                try:
                    metrics = json.loads(metrics_match.group(1))
                except Exception:
                    pass
            # Extract bootstrap data using JSON parsing
            bootstrap = None
            mb = re.search(r'window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*({.*?});', html, re.DOTALL)
            if mb:
                raw = mb.group(1)
                try:
                    bootstrap = json.loads(raw)
                except Exception:
                    # Convert JavaScript object notation to JSON
                    js_to_json = raw
                    # Add quotes around unquoted keys
                    js_to_json = re.sub(r'([{,]\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'\1"\2":', js_to_json)
                    # Fix boolean values
                    js_to_json = re.sub(r'\bfalse\b', 'false', js_to_json)
                    js_to_json = re.sub(r'\btrue\b', 'true', js_to_json)
                    js_to_json = re.sub(r'\bnull\b', 'null', js_to_json)
                    # Remove trailing commas
                    js_to_json = re.sub(r',\s*([}\]])', r'\1', js_to_json)
                    try:
                        bootstrap = json.loads(js_to_json)
                    except Exception:
                        bootstrap = None
                
            # If bootstrap extraction failed, try to extract displayValues from the raw text
            if not bootstrap and mb:
                bootstrap_text = mb.group(1)
                bootstrap = {"productSelectionData": {"products": [], "displayValues": {}}}
                
                # Extract product data from the raw bootstrap text
                product_matches = re.finditer(r'\{[^}]*"partNumber":\s*"([^"]*)"[^}]*\}', bootstrap_text)
                for match in product_matches:
                    obj_text = match.group(0)
                    part_num_match = re.search(r'"partNumber":\s*"([^"]*)"', obj_text)
                    capacity_match = re.search(r'"dimensionCapacity":\s*"([^"]*)"', obj_text)
                    color_match = re.search(r'"dimensionColor":\s*"([^"]*)"', obj_text)
                    family_match = re.search(r'"productLocatorFamily":\s*"([^"]*)"', obj_text)
                    
                    if part_num_match:
                        bootstrap["productSelectionData"]["products"].append({
                            "partNumber": part_num_match.group(1),
                            "dimensionCapacity": capacity_match.group(1) if capacity_match else "",
                            "dimensionColor": color_match.group(1) if color_match else "",
                            "productLocatorFamily": family_match.group(1) if family_match else ""
                        })
            
            # Extract displayValues from the parsed bootstrap if available, or raw text as fallback
            if bootstrap:
                psd = bootstrap.get("productSelectionData", {})
                
                if "displayValues" not in psd:
                    psd["displayValues"] = {"dimensionCapacity": {}, "dimensionColor": {}}
                
                # Check if displayValues are already in the parsed bootstrap
                if "dimensionCapacity" in psd and "dimensionColor" in psd:
                    # Extract from parsed structure
                    if "dimensionCapacity" in psd:
                        dim_cap = psd["dimensionCapacity"]
                        capacity_values = {}
                        for key, value in dim_cap.items():
                            if key not in ["title", "variantOrder", "variantSortOrder"] and isinstance(value, dict) and "value" in value:
                                capacity_values[key] = value
                        psd["displayValues"]["dimensionCapacity"] = capacity_values
                    
                    if "dimensionColor" in psd:
                        dim_color = psd["dimensionColor"]
                        color_values = {}
                        for key, value in dim_color.items():
                            if key not in ["title", "variantOrder", "variantSortOrder"] and isinstance(value, dict) and "value" in value:
                                color_values[key] = value
                        psd["displayValues"]["dimensionColor"] = color_values
                        
                elif mb:
                    # Fallback: extract from raw bootstrap text
                    raw_bootstrap = mb.group(1)
                    
                    # Look for dimensionColor anywhere in the bootstrap text
                    if "dimensionColor" in raw_bootstrap:
                        color_values = {}
                        # Search for individual color entries directly in the raw bootstrap
                        # Use a more comprehensive pattern to catch all color names
                        for match in re.finditer(r'"([a-z][a-z0-9]*(?:blue|orange|silver|gold|purple|green|red|black|white|pink|yellow|gray|grey|brown))":\s*\{\s*"value":\s*"([^"]*)"', raw_bootstrap, re.IGNORECASE):
                            key, value = match.groups()
                            color_values[key] = {"value": value}
                        
                        # Also try exact matches for common iPhone colors
                        common_colors = ["silver", "gold", "spacegray", "deepblue", "cosmicorange", "purple", "green", "red", "black", "white", "pink", "yellow", "blue", "orange", "gray", "grey", "rose", "coral", "mint", "lavender"]
                        for color in common_colors:
                            if color not in color_values:
                                pattern = rf'"{color}":\s*\{{\s*"value":\s*"([^"]*)"'
                                match = re.search(pattern, raw_bootstrap, re.IGNORECASE)
                                if match:
                                    value = match.group(1)
                                    color_values[color] = {"value": value}
                        
                        psd["displayValues"]["dimensionColor"] = color_values
                    
                    # Extract dimensionCapacity values from raw text  
                    if "dimensionCapacity" in raw_bootstrap:
                        capacity_match = re.search(r'"dimensionCapacity":\s*\{(.*?)\}(?=\s*,\s*"[^"]*":|\s*\})', raw_bootstrap, re.DOTALL)
                        if not capacity_match:
                            capacity_match = re.search(r'dimensionCapacity:\s*\{(.*?)\}(?=\s*,\s*[a-zA-Z_]+:|\s*\})', raw_bootstrap, re.DOTALL)
                        
                        if capacity_match:
                            capacity_text = capacity_match.group(1)
                            capacity_values = {}
                            for match in re.finditer(r'"([^"]+)":\s*\{[^}]*?"value":\s*"([^"]*)"', capacity_text):
                                key, value = match.groups()
                                if key not in ["title", "singleVariantDisplayTitle", "multiVariantsDisplayTitle"]:
                                    capacity_values[key] = {"value": value}
                            psd["displayValues"]["dimensionCapacity"] = capacity_values
            # Extract metrics JSON (id="metrics")
            metrics = None
            metrics_match = re.search(r'<script[^>]*id="metrics"[^>]*type="application/json"[^>]*>\s*({.*?})\s*</script>', html, re.DOTALL | re.IGNORECASE)
            if metrics_match:
                try:
                    metrics = json.loads(metrics_match.group(1))
                except Exception:
                    pass
            return {"html": html, "title": page_title, "json_blobs": json_blobs, "metrics": metrics, "bootstrap": bootstrap}
        except Exception as e:
            print(f"[error] fetch failed: {e}")
            return None

    def _apply_variant_from_config(self, base_model: str, product_family: str, family: str, title_text: str) -> str:
        """Apply variant suffix to base model using configuration."""
        # Extract the general product category from the specific family
        # e.g., 'iphone17pro' -> 'iphone', 'macbookpro' -> 'mac'
        general_family = family
        if 'iphone' in family.lower():
            general_family = 'iphone'
        elif 'mac' in family.lower():
            general_family = 'mac'
        elif 'ipad' in family.lower():
            general_family = 'ipad'
        elif 'watch' in family.lower():
            general_family = 'watch'
        
        # Get variant patterns for this product family
        variant_config = self.config.get('model_variants', {}).get(general_family, {})
        variant_patterns = variant_config.get('variant_patterns', [])
        
        # Sort by priority (lower number = higher priority)
        variant_patterns = sorted(variant_patterns, key=lambda x: x.get('priority', 999))
        
        # Try to match product family to a variant pattern
        for pattern in variant_patterns:
            family_key = pattern.get('family_key', '').lower()
            suffix = pattern.get('suffix', '')
            
            if family_key in product_family.lower():
                return f"{base_model} {suffix}"
        
        # No variant match found, check title for fallback patterns
        for pattern in variant_patterns:
            suffix = pattern.get('suffix', '')
            if suffix in title_text:
                return f"{base_model} {suffix}"
        
        # No variant found, return base model
        return base_model
    
    def _extract_base_model_from_title(self, title: str) -> Optional[str]:
        """Extract base model name from title (e.g., 'iPhone 17' from 'iPhone 17 Pro Max')."""
        # Clean title
        title = re.sub(r'&[^;]+;', '', title)  # Remove HTML entities
        title = re.sub(r'\b(kaufen|acheter|buy|comprar)\b', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\bApple\b', '', title, flags=re.IGNORECASE)
        title = title.strip()
        
        # Look for product name + number pattern
        words = title.split()
        for i, word in enumerate(words):
            if word.isdigit() and i > 0:
                prev_word = words[i-1]
                if prev_word.isalpha() and len(prev_word) > 2:
                    return f"{prev_word} {word}"
        
        return None

    def _extract_product_family_from_context(self, html: str, bootstrap: dict, payload: dict) -> Optional[str]:
        """Extract product family dynamically from page context."""
        # Try URL path first
        url_patterns = [
            r'/buy-([^/]+)/',  # e.g., /buy-iphone/iphone-17-pro -> iphone17pro
            r'/([^/]+)$'       # e.g., /iphone-17-pro -> iphone17pro
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, html)
            if match:
                product_path = match.group(1)
                # Clean and normalize the product path
                family = re.sub(r'[^a-zA-Z0-9]', '', product_path).lower()
                if family and len(family) > 3:
                    return family
        
        # Try page title or meta data
        title_patterns = [
            r'<title[^>]*>([^<]*)</title>',
            r'data-analytics-title="([^"]*)"',
            r'"productName":\s*"([^"]*)"'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Extract product family from title (e.g., "iPhone 17 Pro" -> "iphone17pro")
                words = re.findall(r'\w+', title.lower())
                if len(words) >= 2:
                    family = ''.join(words[:3])  # Take first 3 words
                    return family
        
        # Try bootstrap data
        if isinstance(bootstrap, dict):
            for key in ['productFamily', 'family', 'productType']:
                if key in bootstrap and isinstance(bootstrap[key], str):
                    return bootstrap[key].lower().replace('-', '').replace('_', '')
        
        return None

    def _extract_product_display_name(self, html: str, bootstrap: dict, product_family: str) -> Optional[str]:
        """Extract proper product display name (e.g., 'iPhone 17 Pro') from page content."""
        # Try to extract from URL path first - most reliable for specific model
        url_patterns = [
            r'/buy-iphone/([^/?]+)',  # e.g., /buy-iphone/iphone-17-pro
            r'/iphone/([^/?]+)',      # e.g., /iphone/iphone-17-pro
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, html)
            if match:
                url_path = match.group(1)
                # Convert URL path to display name (e.g., "iphone-17-pro" -> "iPhone 17 Pro")
                if 'iphone' in url_path.lower():
                    # Clean and parse the URL path
                    path_clean = url_path.replace('-', ' ').strip()
                    # Extract iPhone model with number and variant
                    iphone_match = re.search(r'iphone\s+(\d+)(?:\s+(.+))?', path_clean, re.IGNORECASE)
                    if iphone_match:
                        number = iphone_match.group(1)
                        variant = iphone_match.group(2) if iphone_match.group(2) else ''
                        
                        # Don't use hardcoded variant mappings - extract from actual page content
                        return None
        
        # Try to extract from page title
        title_patterns = [
            r'<title[^>]*>([^<]*iPhone\s+\d+(?:\s+\w+)?[^<]*)</title>',
            r'data-analytics-title="([^"]*iPhone\s+\d+(?:\s+\w+)?[^"]*)"'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Clean up the title
                title = re.sub(r'\s*-\s*Apple.*$', '', title)
                title = re.sub(r'\s+', ' ', title).strip()
                
                # Extract specific iPhone model (avoid generic titles with multiple models)
                iphone_match = re.search(r'iPhone\s+(\d+)(?:\s+([^-\n\r]+?))(?=\s*-\s*|\s*$)', title, re.IGNORECASE)
                if iphone_match:
                    number = iphone_match.group(1)
                    variant = iphone_match.group(2).strip() if iphone_match.group(2) else ''
                    return f"iPhone {number} {variant}".strip()
        
        # Try to construct from product family as fallback
        if product_family:
            family_clean = re.sub(r'[^a-zA-Z0-9]', '', product_family).lower()
            if 'iphone' in family_clean:
                number_match = re.search(r'iphone(\d+)(.*)$', family_clean)
                if number_match:
                    number = number_match.group(1)
                    variant = number_match.group(2)
                    
                    # Don't use hardcoded variant mappings - extract from actual page content
                    return None
        
        return None

    def _extract_color_from_name_and_page(self, name: str, html: str) -> Optional[dict]:
        """Extract color information from product name using page translations."""
        # Extract color from product name (last part after capacity)
        # e.g., "iPhone 17 Pro Max 512GB Deep Blue" -> "Deep Blue"
        capacity_match = re.search(r'\d+(?:GB|TB)', name)
        if capacity_match:
            # Get text after capacity
            after_capacity = name[capacity_match.end():].strip()
            if after_capacity:
                color_display = after_capacity
                
                # Look for color translations in the HTML
                color_mappings = self._extract_color_mappings_from_html(html)
                
                # Try to find matching color key and localized translation
                color_key = color_display.lower().replace(' ', '')
                localized_display = color_mappings.get(color_key, color_display)
                
                return {
                    'colorKey': color_key,
                    'colorDisplay': color_display,
                    'localizedDisplay': localized_display
                }
        
        return None

    def _has_localized_data(self, product: dict, html: str) -> bool:
        """Check if product has localized data that should use dynamic name building."""
        # Check if this is a regional product with localized color data
        part_number = product.get('partNumber', '')
        color_display = product.get('color', '')
        
        # Regional products with localized colors should use dynamic names
        if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', part_number):
            # Check if we have localized color mappings on the page
            color_mappings = self._extract_color_mappings_from_html(html)
            if color_mappings and color_display:
                # If the color display differs from English, it's likely localized
                color_key = color_display.lower().replace(' ', '')
                return color_key in color_mappings and color_mappings[color_key] != color_display
        
        return False

    def _has_localized_color_data(self, sku: str, color_display: str, html: str) -> bool:
        """Check if SKU has localized color data based on page content."""
        # Check if we have color mappings on the page
        color_mappings = self._extract_color_mappings_from_html(html)
        if color_mappings and color_display:
            color_key = color_display.lower().replace(' ', '')
            return color_key in color_mappings and color_mappings[color_key] != color_display
        return False

    def _extract_color_mappings_from_html(self, html: str) -> dict:
        """Extract color mappings from HTML page."""
        color_mappings = {}
        
        # Look for dimensionColor JSON structure in the HTML
        # Pattern: "colorkey": { "value": "German Name", ... }
        dimension_color_pattern = r'"dimensionColor":\s*{[^}]*?"title":[^}]*?}(.*?)(?:"variantOrder"|"dimensionCapacity")'
        dimension_match = re.search(dimension_color_pattern, html, re.DOTALL)
        
        if dimension_match:
            dimension_content = dimension_match.group(1)
            # Extract color key to German value mappings
            color_value_pattern = r'"([^"]+)":\s*{\s*"value":\s*"([^"]+)"'
            for match in re.finditer(color_value_pattern, dimension_content):
                color_key, german_value = match.groups()
                # Clean HTML tags from German value
                german_clean = re.sub(r'<[^>]+>', '', german_value).strip()
                color_mappings[color_key] = german_clean
        
        # Also look for bootstrap data structure
        bootstrap_pattern = r'"displayValues"[^}]*"dimensionColor"[^}]*({[^}]*})'
        bootstrap_match = re.search(bootstrap_pattern, html, re.DOTALL)
        
        if bootstrap_match:
            bootstrap_content = bootstrap_match.group(1)
            # Extract color mappings from bootstrap structure
            bootstrap_color_pattern = r'"([^"]+)":\s*{\s*"value":\s*"([^"]+)"'
            for match in re.finditer(bootstrap_color_pattern, bootstrap_content):
                color_key = match.group(1).lower()
                german_name = match.group(2)
                if german_name:
                    color_mappings[color_key] = german_name
        
        return color_mappings

    def _map_color_to_key(self, color_display: str, color_mappings: dict) -> str:
        """Map color display name to color key."""
        color_lower = color_display.lower()
        
        # Direct match - return localized translation if available
        if color_lower in color_mappings:
            localized_name = color_mappings[color_lower]
            # If we have a mapping, use it as the display name
            return localized_name
        
        # Partial match
        for display, key in color_mappings.items():
            if color_lower in display or display in color_lower:
                return key
        
        # Generate key from display name
        return re.sub(r'[^a-z0-9]', '', color_lower)

    def _get_german_color_name(self, english_color: str, color_mappings: dict) -> str:
        """Get German color name for display."""
        # First, try to map English color name to color key, then get German translation
        color_key = re.sub(r'[^a-z0-9]', '', english_color.lower())
        
        # Look for the color key in our mappings
        if color_key in color_mappings:
            return color_mappings[color_key]
        
        # Try partial matches for compound color names
        for key, german_name in color_mappings.items():
            if key in color_key or color_key in key:
                return german_name
        
        # Return original if no translation found
        return english_color

    def extract_product_family_name(self, html: str, bootstrap: dict, product_family: Optional[str] = None) -> Optional[str]:
        """Extract the product family name dynamically from page data."""
        # Try to extract from bootstrap data first - this is the most reliable source
        if bootstrap and isinstance(bootstrap, dict):
            # Look for product name in various bootstrap fields
            for key in ['productTitle', 'productName', 'title', 'name', 'displayName']:
                if key in bootstrap and isinstance(bootstrap[key], str):
                    name = bootstrap[key].strip()
                    # Clean HTML entities and unwanted text
                    name = re.sub(r'&nbsp;', ' ', name)
                    name = re.sub(r'&[a-zA-Z0-9#]+;', '', name)  # Remove HTML entities
                    # Remove common purchase-related words dynamically
                    name = re.sub(r'\b(kaufen|acheter|buy|comprar|comprare|kopen)\b', '', name, flags=re.IGNORECASE)
                    name = re.sub(r'\s+', ' ', name).strip()  # Normalize whitespace
                    if name and len(name) > 3:
                        return name

            # Try to find product names in nested structures
            def find_product_names(obj, path=""):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k.lower() in ['productname', 'displayname', 'title', 'name'] and isinstance(v, str):
                            name = v.strip()
                            # Clean HTML entities only
                            name = re.sub(r'&nbsp;', ' ', name)
                            name = re.sub(r'&[a-zA-Z0-9#]+;', '', name)  # Remove HTML entities
                            # Remove common purchase-related words dynamically
                            name = re.sub(r'\b(kaufen|acheter|buy|comprar|comprare|kopen)\b', '', name, flags=re.IGNORECASE)
                            name = re.sub(r'\s+', ' ', name).strip()  # Normalize whitespace
                            if name and len(name) > 3:
                                return name
                        elif isinstance(v, (dict, list)):
                            result = find_product_names(v, f"{path}.{k}")
                            if result:
                                return result
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        result = find_product_names(item, f"{path}[{i}]")
                        if result:
                            return result
                return None

            nested_name = find_product_names(bootstrap)
            if nested_name:
                return nested_name

        # Try to extract from HTML content - look for structured data first
        if html:
            # Look for JSON-LD structured data with product names
            json_ld_patterns = [
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                r'<script[^>]*type="application/json"[^>]*>(.*?)</script>'
            ]

            for pattern in json_ld_patterns:
                matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    try:
                        data = json.loads(match)
                        # Handle both single objects and arrays
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if isinstance(item, dict) and item.get('@type') == 'Product':
                                name = item.get('name', '').strip()
                                if name and len(name) > 6:
                                    return name
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Look for metrics data with product names
            metrics_match = re.search(r'<script[^>]*id="metrics"[^>]*>\s*({.*?})\s*</script>', html, re.DOTALL | re.IGNORECASE)
            if metrics_match:
                try:
                    metrics_data = json.loads(metrics_match.group(1))
                    products = metrics_data.get('data', {}).get('products', [])
                    if products:
                        # Get the first product name that looks complete
                        for product in products:
                            if isinstance(product, dict):
                                name = product.get('name', '').strip()
                                if name and len(name) > 10:  # More than just "iPhone"
                                    return name
                except (json.JSONDecodeError, KeyError):
                    pass

            # Look for product selection bootstrap data
            psb_match = re.search(r'window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*({.*?});', html, re.DOTALL)
            if psb_match:
                try:
                    psb_data = json.loads(psb_match.group(1))
                    display_values = psb_data.get('productSelectionData', {}).get('displayValues', {})

                    # Look for screen size display values which contain the model names
                    screensize_values = display_values.get('dimensionScreensize', {})
                    for key, value_data in screensize_values.items():
                        if isinstance(value_data, dict):
                            value = value_data.get('value', '')
                            # Extract clean product name from display value
                            clean_name = re.sub(r'<[^>]+>', '', value)  # Remove HTML tags
                            clean_name = re.sub(r'&nbsp;', ' ', clean_name)
                            clean_name = re.sub(r'&[a-zA-Z0-9#]+;', '', clean_name)
                            clean_name = re.sub(r'\s+', ' ', clean_name).strip()

                            # Look for model names in display values
                            if len(clean_name) > 6:
                                # Extract clean product name from display value
                                return clean_name
                except (json.JSONDecodeError, KeyError, AttributeError):
                    pass

            # Look for h1 tags that might contain the product name
            h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
            if h1_match:
                h1_text = h1_match.group(1).strip()
                # Clean HTML entities only
                h1_text = re.sub(r'&nbsp;', ' ', h1_text)
                h1_text = re.sub(r'&[a-zA-Z0-9#]+;', '', h1_text)  # Remove HTML entities
                # Remove common purchase-related words dynamically
                h1_text = re.sub(r'\b(kaufen|acheter|buy|comprar|comprare|kopen)\b', '', h1_text, flags=re.IGNORECASE)
                h1_text = re.sub(r'\s+', ' ', h1_text).strip()  # Normalize whitespace
                if h1_text and len(h1_text) > 3:
                    return h1_text

        # No fallbacks - leave empty until proper extraction is implemented
        return None

    def extract_product_selection_data(self, html, family):
        """Extract product selection data from the page HTML."""
        psd = {"displayValues": {"dimensionColor": {}, "dimensionCapacity": {}}}
        
        # First try to find the product selection data JSON blob
        match = re.search(r'<script[^>]*type="application/json"[^>]*data-ssr-name="ProductSelectionData"[^>]*>\s*({.*?})\s*</script>', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "displayValues" in data:
                    psd["displayValues"] = data["displayValues"]
                    return psd
            except Exception:
                pass

    def _build_skus_from_payload(self, payload: dict, family_hint: Optional[str] = None) -> Dict[str, dict]:
        html = payload.get("html", "")
        metrics = payload.get("metrics")
        bootstrap = payload.get("bootstrap")
        json_blobs = payload.get("json_blobs") or []
        out: Dict[str, dict] = {}
        name_by_base: Dict[str, str] = {}
        full_by_base: Dict[str, str] = {}
        # Helper: normalize a product dict into our sku entry
        def add_prod(p: dict):
            sku = (p or {}).get('partNumber')
            name = (p or {}).get('name') or ''
            # If partNumber is missing, accept bare 'sku' (e.g., MX2J3) and use as key
            if (not sku or not isinstance(sku, str)) and isinstance((p or {}).get('sku'), str):
                sku = p.get('sku')
            if not sku or not isinstance(sku, str):
                return
            # Maintain base->name map for later offer stitching
            try:
                m = re.match(r'^([A-Z0-9]{3,6})', sku)
                if m:
                    name_by_base.setdefault(m.group(1), name)
            except Exception:
                pass
            color_key = (p.get('dimensionColor') or p.get('color') or '').lower().replace(' ', '') if isinstance(p, dict) else ''
            color_display = p.get('color') or '' if isinstance(p, dict) else ''
            capacity = p.get('capacity') or p.get('dimensionCapacity') or '' if isinstance(p, dict) else ''
            family = p.get('family') or p.get('productLocatorFamily') or '' if isinstance(p, dict) else ''
            family_name = p.get('familyName') or family or '' if isinstance(p, dict) else ''
            screensize = ''
            if isinstance(p, dict):
                # Try several common locations for screen size dimension
                screensize = (
                    p.get('dimensionScreensize') or
                    (p.get('dimensions') or {}).get('dimensionScreensize') or
                    p.get('screenSize') or
                    ''
                )
            # For localized products, keep name empty so app builds localized name
            final_name = name if not p.get('_localized_processed') else ""
            out[sku] = {
                "name": final_name,
                "colorKey": color_key or "unknown",
                "colorDisplay": color_display or "Unknown",
                "capacity": capacity or "",
                "dimensionScreensize": screensize or "",
                "family": family or "unknown",
                "familyName": family_name or "Unknown"
            }
        # Prefer metrics products first when present (often include capacity/color-rich names)
        try:
            prods = (metrics or {}).get('data', {}).get('products')
            if isinstance(prods, list):
                for p in prods:
                    if isinstance(p, dict):
                        add_prod(p)
        except Exception:
            pass
        # Consume PRODUCT_SELECTION_BOOTSTRAP when available (richer for iPhone)
        try:
            if isinstance(bootstrap, dict):
                psd = bootstrap.get('productSelectionData') or {}
                products = psd.get('products') or []
                disp = psd.get('displayValues') or {}
                # Check if capacity info is missing from displayValues - extract from HTML
                if 'dimensionCapacity' not in disp or not disp['dimensionCapacity']:
                    # Try to find capacity values in the page HTML
                    storage_patterns = [
                        r'"(\d+gb)":\s*{\s*"value":\s*"([^"]+)"',
                        r'"(\d+tb)":\s*{\s*"value":\s*"([^"]+)"'
                    ]
                    
                    found_capacities = {}
                    for pattern in storage_patterns:
                        matches = re.findall(pattern, html, re.IGNORECASE)
                        for key, value in matches:
                            # Clean up HTML artifacts from the value
                            clean_value = re.sub(r'<[^>]*>', '', value)  # Remove HTML tags
                            clean_value = re.sub(r'<as-footnote[^>]*', '', clean_value)  # Remove footnote tags
                            clean_value = clean_value.replace('\\', '').strip()  # Remove backslashes and whitespace
                            found_capacities[key.lower()] = {'value': clean_value}
                    
                    if found_capacities:
                        # Update the displayValues with found capacity data
                        disp['dimensionCapacity'] = found_capacities
                
                # Check if we have displayValues but no product dimensions - infer from combinations
                if disp and products and not any(p.get('dimensionCapacity') or p.get('dimensionColor') for p in products):
                    # Get available dimensions - check the actual structure
                    capacity_data = disp.get('dimensionCapacity', {})
                    color_data = disp.get('dimensionColor', {})
                    
                    # Extract keys excluding metadata keys like 'title', 'variantOrder'
                    capacity_keys = [k for k in capacity_data.keys() if k not in ['title', 'variantOrder', 'variantSortOrder']]
                    color_keys = [k for k in color_data.keys() if k not in ['title', 'variantOrder', 'variantSortOrder']]
                    
                    if capacity_keys and color_keys:
                        # Group products by family and part number to find unique SKUs per model
                        products_by_family = {}
                        generic_products = {}  # For products without specific family
                        
                        for p in products:
                            pn = p.get('partNumber')
                            family = p.get('productLocatorFamily', p.get('familyType', ''))
                            
                            if pn:
                                # Handle products with specific families
                                if family and family not in ['iphone', 'iPhone']:
                                    if family not in products_by_family:
                                        products_by_family[family] = {}
                                    if pn not in products_by_family[family]:
                                        products_by_family[family][pn] = p
                                # Handle generic iPhone products
                                elif family in ['iphone', 'iPhone', ''] or not family:
                                    if pn not in generic_products:
                                        generic_products[pn] = p
                        
                        # Create all combinations for each family
                        import itertools
                        combinations = list(itertools.product(capacity_keys, color_keys))
                        
                        # Map parts to combinations for each product family
                        for family, family_products in products_by_family.items():
                            for i, (pn, product) in enumerate(family_products.items()):
                                if i < len(combinations):
                                    cap_key, color_key = combinations[i]
                                    # Update the product with inferred dimensions
                                    product['dimensionCapacity'] = cap_key
                                    product['dimensionColor'] = color_key
                        
                        # Filter out service/accessory SKUs from generic products
                        # These are typically AppleCare plans or accessories, not iPhone variants
                        actual_iphone_products = {}
                        for pn, product in generic_products.items():
                            # Skip AppleCare and service SKUs (typically start with SX, SN, MW, or contain specific patterns)
                            if not (pn.startswith(('SX', 'SN', 'MW')) or 'UNLOCKED' in pn or len(pn) < 8):
                                actual_iphone_products[pn] = product
                        
                        # Map actual iPhone products to remaining combinations
                        if actual_iphone_products:
                            remaining_combinations = combinations.copy()
                            for i, (pn, product) in enumerate(actual_iphone_products.items()):
                                if i < len(remaining_combinations):
                                    cap_key, color_key = remaining_combinations[i]
                                    # Update the product with inferred dimensions
                                    product['dimensionCapacity'] = cap_key
                                    product['dimensionColor'] = color_key
                # Helpers to resolve capacity/color labels
                def resolve_capacity(key: str) -> str:
                    if not isinstance(key, str):
                        return ''
                    label = disp.get('dimensionCapacity', {}).get(key, {})
                    if isinstance(label, dict):
                        v = label.get('value') or ''
                        # Strip HTML tags and clean up
                        clean_v = re.sub(r'<[^>]+>', '', v).replace('\u00a0', ' ').strip()
                        if clean_v:
                            return clean_v
                    # Fallback conversion if displayValues not available
                    if key.endswith('gb'):
                        return key[:-2] + ' GB'
                    elif key.endswith('tb'):
                        return key[:-2] + ' TB'
                    return key
                def resolve_color(key: str) -> Tuple[str, str]:
                    if not isinstance(key, str):
                        return ('', '')
                    entry = disp.get('dimensionColor', {}).get(key, {})
                    pretty = ''
                    if isinstance(entry, dict):
                        pretty = entry.get('value') or entry.get('text') or ''
                        # Strip HTML tags and clean up
                        pretty = re.sub(r'<[^>]+>', '', pretty).replace('\u00a0', ' ').strip()
                    # If no localized value found, use the key as-is
                    if not pretty:
                        pretty = key
                    return (key.lower().replace(' ', ''), pretty)
                for p in products:
                    if not isinstance(p, dict):
                        continue
                    pn = p.get('partNumber')
                    if not isinstance(pn, str):
                        continue
                    # Skip localized products that were already processed
                    if p.get('_localized_processed'):
                        continue
                    cap_key = p.get('dimensionCapacity')
                    color_key = p.get('dimensionColor')
                    cap = resolve_capacity(cap_key)
                    ck, cd = resolve_color(color_key)
                    
                    # If no color/capacity from product data, try to infer from part number or name
                    if not ck and not cap:
                        # Try to extract from product name if available
                        product_name = p.get('name', '')
                        if product_name:
                            # Look for capacity patterns in name (e.g., "128GB", "256 GB", "1TB")
                            cap_match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|TB)', product_name, re.IGNORECASE)
                            if cap_match:
                                size, unit = cap_match.groups()
                                cap = f"{size} {unit.upper()}"
                            
                            # Look for color patterns in name
                            color_patterns = ['silver', 'gold', 'space gray', 'deep blue', 'cosmic orange', 'purple', 'green', 'red', 'black', 'white', 'pink', 'yellow']
                            for color in color_patterns:
                                if color.lower() in product_name.lower():
                                    ck = color.lower().replace(' ', '')
                                    cd = color.title()
                                    break
                    # Get family from productLocatorFamily field (prioritize over family_hint)
                    product_family = p.get('productLocatorFamily') or ''
                    fam = (product_family or family_hint or '').lower()
                    
                    
                    # Extract model name dynamically from page content
                    fam_name = None
                    
                    
                    # First try to extract from page title or HTML content
                    if html:
                        # Look for model names in the HTML title or h1 tags
                        title_patterns = [
                            r'<title[^>]*>([^<]*)</title>',
                            r'<h1[^>]*>([^<]*)</h1>',
                            r'data-analytics-title="([^"]*)"'
                        ]
                        
                        for pattern in title_patterns:
                            match = re.search(pattern, html, re.IGNORECASE)
                            if match:
                                title_text = match.group(1).strip()
                                # Clean up the title text
                                title_text = re.sub(r'&nbsp;', ' ', title_text)
                                title_text = re.sub(r'&[a-zA-Z0-9#]+;', '', title_text)
                                title_text = re.sub(r'\s*-\s*Apple.*', '', title_text, flags=re.IGNORECASE)
                                title_text = re.sub(r'\s*kaufen\s*', ' ', title_text, flags=re.IGNORECASE)
                                title_text = re.sub(r'\s*acheter\s*', ' ', title_text, flags=re.IGNORECASE)
                                title_text = re.sub(r'\s*buy\s*', ' ', title_text, flags=re.IGNORECASE)
                                title_text = re.sub(r'\s+', ' ', title_text).strip()
                                
                                # Extract base model name from title and use product family to determine variant
                                if title_text and len(title_text) > 3:
                                    # Extract the base product name (e.g., "iPhone 17") from title
                                    base_model = None
                                    
                                    # Look for product name patterns in the title
                                    words = title_text.split()
                                    for i, word in enumerate(words):
                                        # Look for numeric model identifiers
                                        if word.isdigit() and i > 0:
                                            # Found a number, check if previous word looks like a product name
                                            prev_word = words[i-1]
                                            if prev_word.isalpha() and len(prev_word) > 2:
                                                base_model = f"{prev_word} {word}"
                                                break
                                    
                                    # Use product family to determine the specific variant from config
                                    if base_model and product_family:
                                        fam_name = self._apply_variant_from_config(base_model, product_family, family, title_text)
                                    
                                    if fam_name:
                                        break
                    
                    # If HTML extraction failed, try general extraction
                    if not fam_name:
                        # For regional pages, try to use the product family directly with config
                        if product_family and product_family != 'iphone':
                            # Extract base model from product family and apply variant
                            if 'iphone' in product_family.lower():
                                base_model = 'iPhone 17'  # Default base for iPhone 17 series
                                fam_name = self._apply_variant_from_config(base_model, product_family, 'iphone', '')
                        
                        # If still no name, try general extraction
                        if not fam_name:
                            extracted_name = self.extract_product_family_name(html, bootstrap, product_family)
                            # Don't use generic extraction result, keep our specific family
                            if extracted_name and extracted_name not in ['iPhone', 'Mac', 'Apple Watch']:
                                fam_name = extracted_name
                    
                    # Final fallback
                    if not fam_name:
                        fam_name = 'iPhone'
                    
                    # Fallback: try page title if still generic
                    if fam_name == 'iPhone' and payload.get('title'):
                        title = payload['title']
                        # Extract model name from payload title using product family context from config
                        if product_family:
                            base_model = self._extract_base_model_from_title(title)
                            if base_model:
                                fam_name = self._apply_variant_from_config(base_model, product_family, family, title)
                    
                    # Remember name by base to stitch ld+json offers
                    try:
                        m = re.match(r'^([A-Z0-9]{3,6})', pn)
                        if m:
                            nb = ' '.join([fam_name or '', cap, cd]).strip()
                            if nb:
                                name_by_base.setdefault(m.group(1), nb)
                    except Exception:
                        pass
                    # Build full product name with model, capacity, and color
                    name_parts = [fam_name or 'iPhone']
                    if cap:
                        name_parts.append(cap)
                    if cd:
                        name_parts.append(cd)
                    full_name = ' '.join(name_parts).strip()
                    
                    
                    final_family = product_family or fam or (p.get('family') or 'iphone')
                    
                    
                    out.setdefault(pn, {
                        "name": full_name or (p.get('name') or ''),
                        "colorKey": ck or (p.get('dimensionColor') or ''),
                        "colorDisplay": cd or (p.get('color') or ''),
                        "capacity": cap or (p.get('capacity') or p.get('dimensionCapacity') or ''),
                        "dimensionScreensize": (p.get('dimensionScreensize') or ''),
                        "family": final_family,
                        "familyName": fam_name or 'iPhone',
                        "partNumber": pn,
                        "metadata": {"isRealPartNumber": True, "sourcePage": (family_hint or '').lower()}
                    })
                    
        except Exception:
            pass
        # Metrics path (enhanced): recursively search for dicts with 'partNumber'
        if metrics and isinstance(metrics, dict):
            def iter_metric_products(obj):
                if isinstance(obj, dict):
                    if 'partNumber' in obj:
                        yield obj
                    for v in obj.values():
                        for it in iter_metric_products(v):
                            yield it
                elif isinstance(obj, list):
                    for it in obj:
                        for v in iter_metric_products(it):
                            yield v
            for p in iter_metric_products(metrics.get('data') or metrics):
                if isinstance(p, dict) and ('partNumber' in p):
                    add_prod(p)
        # Bootstrap path (Apple Watch): parse PRODUCT_SELECTION_BOOTSTRAP when present
        if not out and ('buy-watch' in html):
            # 1) JSON.parse('...') form
            m = re.search(r"PRODUCT_SELECTION_BOOTSTRAP\s*=\s*JSON\.parse\(\s*'(.+?)'\s*\)\s*;", html, re.DOTALL)
            text_blob = None
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
                # 2) Balanced-brace form after assignment
                assign = html.find('window.PRODUCT_SELECTION_BOOTSTRAP')
                if assign != -1:
                    brace = html.find('{', assign)
                    if brace != -1:
                        depth = 0
                        end = brace
                        for i in range(brace, len(html)):
                            ch = html[i]
                            if ch == '{': depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end = i
                                    break
                        text_blob = html[brace:end+1]
            # Attempt to parse and locate products arrays recursively
            def iter_products(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == 'products' and isinstance(v, list):
                            yield from v
                        yield from iter_products(v)
                elif isinstance(obj, list):
                    for it in obj:
                        yield from iter_products(it)
        
        # Process JSON blobs for product data
        for blob_idx, text_blob in enumerate(json_blobs):
            count = 0
            def iter_products(obj):
                if isinstance(obj, dict):
                    for v in obj.values():
                        yield from iter_products(v)
                elif isinstance(obj, list):
                    for it in obj:
                        for v in iter_products(it):
                            yield v
            if text_blob:
                # Gentle cleanup for common issues
                cleaned = re.sub(r',\s*}', '}', text_blob)
                cleaned = re.sub(r',\s*\]', ']', cleaned)
                try:
                    data = json.loads(cleaned)
                    payload = data  # Set payload for the products check below
                except Exception:
                    data = None
                    payload = {}
                if isinstance(data, (dict, list)):
                    try:
                        products = payload.get('products', [])
                        if not products:
                            # Try alternative product extraction paths
                            if isinstance(payload, dict):
                                # Look for products in different structures
                                for key in ['productSelection', 'product', 'variants', 'items']:
                                    if key in payload and isinstance(payload[key], (list, dict)):
                                        if isinstance(payload[key], list):
                                            products = payload[key]
                                            break
                                        elif isinstance(payload[key], dict) and 'products' in payload[key]:
                                            products = payload[key]['products']
                                            break
                        
                        # Special handling for alternative product data structures
                        if not products and isinstance(payload, dict):
                            # Try to find product data in alternative JSON structures
                            def find_alternative_products(obj, path=""):
                                found_products = []
                                if isinstance(obj, dict):
                                    # Look for objects that contain part numbers with region suffixes
                                    if 'partNumber' in obj and isinstance(obj.get('partNumber'), str):
                                        part_number = obj['partNumber']
                                        # Check for any regional suffix pattern (e.g., ZD/A, LL/A, etc.)
                                        if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', part_number):
                                            found_products.append(obj)
                                    # Recursively search nested objects
                                    for key, value in obj.items():
                                        found_products.extend(find_alternative_products(value, f"{path}.{key}"))
                                elif isinstance(obj, list):
                                    for i, item in enumerate(obj):
                                        found_products.extend(find_alternative_products(item, f"{path}[{i}]"))
                                return found_products
                            
                            products = find_alternative_products(payload)
                        
                        for p in products:
                            try:
                                # Transform alternative product formats to expected format
                                if isinstance(p, dict) and 'partNumber' in p:
                                    part_number = p['partNumber']
                                    # Check if this is a regional product with alternative format
                                    if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', part_number) and 'name' in p and 'category' in p:
                                        # Extract product info dynamically from the product data and page context
                                        name = p.get('name', '')
                                        
                                        # Dynamically determine product family from URL or page context
                                        product_family = self._extract_product_family_from_context(html, bootstrap, payload)
                                        if product_family:
                                            p['productLocatorFamily'] = product_family
                                            # Extract base family (e.g., 'iphone' from 'iphone17promax')
                                            base_family = re.sub(r'\d+.*', '', product_family).lower()
                                            p['family'] = base_family
                                            
                                            # Extract proper product name for display (e.g., "iPhone 17 Pro")
                                            product_name = self._extract_product_display_name(html, bootstrap, product_family)
                                            if product_name:
                                                p['familyName'] = product_name
                                        
                                        # Extract capacity from name (e.g., "128GB", "256GB", "512GB", "1TB")
                                        capacity_match = re.search(r'(\d+(?:GB|TB))', name, re.IGNORECASE)
                                        if capacity_match:
                                            p['dimensionCapacity'] = capacity_match.group(1).upper()
                                        
                                        # Extract color translations dynamically from page
                                        color_info = self._extract_color_from_name_and_page(name, html)
                                        if color_info:
                                            # Use localized color name as display, English-based key for compatibility
                                            localized_display = color_info.get('localizedDisplay', color_info['colorDisplay'])
                                            p['dimensionColor'] = color_info['colorKey']
                                            p['color'] = localized_display
                                            
                                        # For regional products with localized data, leave name empty for dynamic building
                                        if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', part_number):
                                            if 'name' in p:
                                                del p['name']
                                            p['_localized_processed'] = True
                                add_prod(p)
                            except Exception as e:
                                pass
                    except Exception as e:
                        pass
                    if True:  # Changed from count == 0
                        # Last resort: scan for partNumber inside the blob
                        fam = (family_hint or 'watch').lower()
                        # Extract dynamic family name from page data
                        fam_name = self.extract_product_family_name(html, bootstrap, fam)
                        if not fam_name:
                            fam_name = 'Apple Watch' if fam == 'watch' else fam.title()
                        for mm in re.finditer(r'\"partNumber\"\s*:\s*\"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])\"', cleaned):
                            # Don't create empty SKUs - only create if we have meaningful data
                            if mm.group(1) not in out and (fam != 'iphone' or fam_name != 'iPhone'):
                                out.setdefault(mm.group(1), {"name": "", "colorKey": "", "colorDisplay": "", "capacity": "", "family": fam, "familyName": fam_name})
        # Fallback 1: scan any JSON for "partNumber":"..." (augment existing)
        for m in re.finditer(r'\"partNumber\"\s*:\s*\"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])\"', html):
            sku = m.group(1)
            fam = (family_hint or '').lower()
            # Extract dynamic family name from page data
            fam_name = self.extract_product_family_name(html, bootstrap, fam)
            if not fam_name:
                fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
            # Don't create empty SKUs - only create if we have meaningful data
            if sku not in out and (fam != 'iphone' or fam_name != 'iPhone'):
                out.setdefault(sku, {"name": "", "colorKey": "", "colorDisplay": "", "capacity": "", "family": fam, "familyName": fam_name})
        # Fallback 1b: search parsed JSON blobs (any structure) for dicts containing partNumber/sku and optional name
        if isinstance(json_blobs, list):
            def iter_dicts(obj):
                if isinstance(obj, dict):
                    yield obj
                    for v in obj.values():
                        yield from iter_dicts(v)
                elif isinstance(obj, list):
                    for it in obj:
                        yield from iter_dicts(it)
            for blob in json_blobs:
                for node in iter_dicts(blob):
                    pn = node.get('partNumber') if isinstance(node.get('partNumber'), str) else None
                    sku_val = node.get('sku') if isinstance(node.get('sku'), str) else None
                    name = node.get('name') or ''
                    candidate = None
                    # Prefer full Apple parts
                    if isinstance(pn, str) and re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', pn):
                        candidate = pn
                    elif isinstance(sku_val, str) and re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', sku_val):
                        candidate = sku_val
                    if candidate:
                        fam = (family_hint or '').lower()
                        fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
                        out.setdefault(candidate, {
                            "name": name or '',
                            "colorKey": (node.get('dimensionColor') or node.get('color') or '').lower().replace(' ', ''),
                            "colorDisplay": node.get('color') or "",
                            "capacity": node.get('capacity') or node.get('dimensionCapacity') or "",
                            "family": node.get('family') or node.get('productLocatorFamily') or fam or "",
                            "familyName": node.get('familyName') or fam_name or ""
                        })
        # Fallback 2: scan ld+json for sku fields (augment existing)
        for block in re.findall(r'<script[^>]*type=\"application/ld\+json\"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(block)
            except Exception:
                continue
            # Normalize to list
            items = data if isinstance(data, list) else [data]
            for it in items:
                if isinstance(it, dict):
                    offers = it.get('offers')
                    if isinstance(offers, list):
                        for offer in offers:
                            sku = offer.get('sku') or ''
                            if isinstance(sku, str) and re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', sku):
                                # Record base->full mapping to reconcile base codes later
                                try:
                                    m = re.match(r'^([A-Z0-9]{3,6})', sku)
                                    if m:
                                        full_by_base.setdefault(m.group(1), sku)
                                except Exception:
                                    pass
                                fam = (family_hint or '').lower()
        # Fallback 2b (Mac/iPhone): parse window.pageLevelData productSelectionTabSlots JS blocks
        # e.g., window.pageLevelData.productSelectionTabSlots.productSelection1 = { ... }
        if (family_hint or '').lower() in ('mac','iphone'):
            mb = re.search(r'window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*({.*?});', html, re.DOTALL)
            if mb:
                raw = mb.group(1)
                try:
                    bootstrap = json.loads(raw)
                except Exception:
                    # Convert JavaScript object notation to JSON
                    js_to_json = raw
                    # Add quotes around unquoted keys
                    js_to_json = re.sub(r'([{,]\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:', r'\1"\2":', js_to_json)
                    # Fix boolean values
                    js_to_json = re.sub(r'\bfalse\b', 'false', js_to_json)
                    js_to_json = re.sub(r'\btrue\b', 'true', js_to_json)
                    js_to_json = re.sub(r'\bnull\b', 'null', js_to_json)
                    # Remove trailing commas
                    js_to_json = re.sub(r',\s*([}\]])', r'\1', js_to_json)
                    try:
                        bootstrap = json.loads(js_to_json)
                    except Exception:
                        bootstrap = None
                if bootstrap:
                    # Attempt to parse and locate products arrays recursively
                    def iter_products(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                try:
                                    if k == 'products' and isinstance(v, list):
                                        for it in v:
                                            if isinstance(it, dict):
                                                yield it
                                except Exception:
                                    pass
                                else:
                                    for it in iter_products(v):
                                        yield it
                        elif isinstance(obj, list):
                            for it in obj:
                                for v in iter_products(it):
                                    yield v
                    for p in iter_products(bootstrap):
                        add_prod(p)
            for m in re.finditer(r'window\.pageLevelData\.productSelectionTabSlots\.[a-zA-Z0-9_]+\s*=\s*(\{.*?\})\s*;', html, re.DOTALL):
                js_obj = m.group(1)
                try:
                    data = json.loads(js_obj)
                except Exception:
                    # Some pages may have trailing commas or JS-specific tokens; attempt a crude cleanup
                    try:
                        cleaned = re.sub(r',\s*([}\]])', r'\1', js_obj)
                        data = json.loads(cleaned)
                    except Exception:
                        continue
                # Traverse and add any partNumber/sku entries
                def iter_nodes(o):
                    if isinstance(o, dict):
                        yield o
                        for v in o.values():
                            yield from iter_nodes(v)
                    elif isinstance(o, list):
                        for it in o:
                            yield from iter_nodes(it)
                for node in iter_nodes(data):
                    pn = node.get('partNumber') if isinstance(node.get('partNumber'), str) else None
                    sku_val = node.get('sku') if isinstance(node.get('sku'), str) else None
                    name = node.get('name') or ''
                    # Capture mapping from favorites.parentPartNumber (base) -> partNumber (full)
                    try:
                        fav = node.get('favorites') if isinstance(node.get('favorites'), dict) else None
                        parent_base = fav.get('parentPartNumber') if fav else None
                        if isinstance(parent_base, str) and isinstance(pn, str) and re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', pn):
                            full_by_base.setdefault(parent_base, pn)
                    except Exception:
                        pass
                    # Prefer full partNumber when available, else fall back to sku/base
                    candidate = pn or sku_val
                    if isinstance(candidate, str):
                        # Accept full parts; also keep base codes to be reconciled later
                        if re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', candidate) or re.match(r'^[A-Z0-9]{3,6}$', candidate):
                            fam = (family_hint or '').lower()
                            fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
                            out.setdefault(candidate, {
                                "name": name or '',
                                "colorKey": (node.get('dimensionColor') or node.get('color') or '').lower().replace(' ', ''),
                                "colorDisplay": node.get('color') or "",
                                "capacity": node.get('capacity') or node.get('dimensionCapacity') or "",
                                "dimensionScreensize": (node.get('dimensionScreensize') or (node.get('dimensions') or {}).get('dimensionScreensize') or node.get('screenSize') or ""),
                                "family": node.get('family') or node.get('productLocatorFamily') or fam or "",
                                "familyName": node.get('familyName') or fam_name or "",
                                "partNumber": candidate if re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', candidate) else "",
                                "metadata": {"isRealPartNumber": bool(re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', candidate))}
                            })
            # Regex-only pass: capture parentPartNumber → partNumber pairs from inline JS without JSON parsing
            for mm in re.finditer(r'parentPartNumber"\s*:\s*"([A-Z0-9]{3,6})"[\s\S]{0,2000}?partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"', html):
                base, full = mm.group(1), mm.group(2)
                full_by_base.setdefault(base, full)
                fam = (family_hint or '').lower()
                fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
                out.setdefault(full, {"name": "", "colorKey": "", "colorDisplay": "", "capacity": "", "family": fam or "", "familyName": fam_name or "", "partNumber": full, "metadata": {"isRealPartNumber": True}})
            # Also handle reverse order: partNumber appears before parentPartNumber in the same block
            for mm in re.finditer(r'partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"[\s\S]{0,2000}?parentPartNumber"\s*:\s*"([A-Z0-9]{3,6})"', html):
                full, base = mm.group(1), mm.group(2)
                full_by_base.setdefault(base, full)
                fam = (family_hint or '').lower()
                fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
                out.setdefault(full, {"name": "", "colorKey": "", "colorDisplay": "", "capacity": "", "family": fam or "", "familyName": fam_name or "", "partNumber": full, "metadata": {"isRealPartNumber": True}})
        # Fallback 3: generic SKU regex across HTML (augment existing)
        for m in re.finditer(r'([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])', html):
            fam = (family_hint or '').lower()
            fam_name = 'Apple Watch' if fam == 'watch' else (fam.title() if fam else '')
            out.setdefault(m.group(1), {"name": "", "colorKey": "", "colorDisplay": "", "capacity": "", "family": fam or "", "familyName": fam_name or ""})
        # Fallback 4 (Mac specific): parse metrics JSON inline text for partNumber + name pairs
        if (family_hint or '').lower() == 'mac':
            # Scope to the metrics script block to reduce noise
            mm = re.search(r'<script[^>]*id=\"metrics\"[^>]*>\s*({.*?})\s*</script>', html, re.DOTALL | re.IGNORECASE)
            scope = mm.group(1) if mm else html
            # Try both orders: partNumber then name, or name then partNumber
            pair_patterns = [
                r'\"partNumber\"\s*:\s*\"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])\"[^}]{0,200}?\"name\"\s*:\s*\"([^\"]{2,120})\"',
                r'\"name\"\s*:\s*\"([^\"]{2,120})\"[^}]{0,200}?\"partNumber\"\s*:\s*\"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])\"',
            ]
            found = 0
            for pat in pair_patterns:
                for m in re.finditer(pat, scope, re.DOTALL | re.IGNORECASE):
                    if pat.startswith('\"partNumber'):
                        pn, nm = m.group(1), m.group(2)
                    else:
                        nm, pn = m.group(1), m.group(2)
                    try:
                        b = re.match(r'^([A-Z0-9]{3,6})', pn)
                        if b:
                            full_by_base.setdefault(b.group(1), pn)
                    except Exception:
                        pass
                    out.setdefault(pn, {"name": nm, "colorKey": "", "colorDisplay": "", "capacity": "", "family": "mac", "familyName": "Mac"})
                    found += 1
            # If offers block contains sku (without country suffix), capture those too
            for m in re.finditer(r'"sku"\s*:\s*"([A-Z0-9]{3,6})([A-Z]{2}/[A-Z])?"', scope):
                base = m.group(1)
                suffix = m.group(2) or ""
                key = base + suffix
                if suffix:
                    full_by_base.setdefault(base, key)
                # Skip if already present by full part
                if key in out or any(k.startswith(base) for k in out.keys()):
                    continue
                out.setdefault(key, {"name": name_by_base.get(base, ""), "colorKey": "", "colorDisplay": "", "capacity": "", "family": "mac", "familyName": "Mac"})
        # Reconcile: upgrade base-only keys to full part numbers when possible
        try:
            upgrades: Dict[str, str] = {}
            for k in list(out.keys()):
                if re.match(r'^[A-Z0-9]{3,6}$', k):
                    base = k
                    full = full_by_base.get(base)
                    if full:
                        # If full key missing, move value; if full already present, drop base
                        if full not in out:
                            out[full] = out[k]
                        upgrades[k] = full
            for old, new in upgrades.items():
                del out[old]
        except Exception:
            pass
        
        
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

    def emit_model_file(self, family: str, token: str, country_to_data: Dict[str, Tuple[str, Dict[str, dict]]], token_display_override: Optional[str] = None) -> str:
        """
        country_to_data: country_code -> (shop_path, skus_dict)
        """
        discovered: Dict[str, Dict[str, dict]] = {}
        country_mappings: Dict[str, dict] = {}
        # Derive a friendly display name per token for Settings
        def _display_name(fam: str, tok: str) -> str:
            # Try to use token_display_override if provided (contains dynamic extraction)
            if token_display_override:
                return token_display_override
            
            # Generic fallbacks only if no dynamic extraction
            f = fam.lower()
            if f == 'iphone':
                return 'iPhone'
            elif f == 'watch':
                return 'Apple Watch'
            elif f == 'mac':
                return 'Mac'
            else:
                return fam.title()
        token_display = token_display_override or _display_name(family, token)
        for cc, (shop_path, skus) in country_to_data.items():
            cc_l = cc.lower()
            # Provide a PDP url constructed from shop_path for convenience
            discovered.setdefault(cc_l, {})[token] = {
                "url": f"https://www.apple.com/{cc_l}/{shop_path}",
                "skus": skus
            }
            cm = country_mappings.setdefault(cc_l, {})
            cm.setdefault("shop_paths", {})[token] = shop_path
            # Put the token display into localization map
            loc = cm.setdefault("localization", {})
            tdisp = loc.setdefault("token_display", {})
            tdisp[token] = token_display
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
        # Local helper to compute a friendly display name for a family/token
        def display_name_for(fam: str, tok: str) -> str:
            # Use generic fallbacks since dynamic extraction happens later
            f = fam.lower()
            if f == 'iphone':
                return 'iPhone'
            elif f == 'watch':
                return 'Apple Watch'
            elif f == 'mac':
                return 'Mac'
            else:
                return fam.title()

        # Discover tokens if needed
        seeds: Dict[str, str] = {}  # token -> shop_path (from first region that exposes it)
        if all_models or not tokens:
            for r in regions:
                found = self.discover_models(family, r)
                for t, p in found.items():
                    seeds.setdefault(t, p)
            tokens = list(seeds.keys())
        # Process each token
        def _prune_skus(skus: Dict[str, dict]) -> Dict[str, dict]:
            pruned: Dict[str, dict] = {}
            for sku, md in skus.items():
                if not isinstance(md, dict):
                    continue
                name = (md.get('name') or '').strip()
                colorKey = (md.get('colorKey') or '').strip()
                colorDisplay = (md.get('colorDisplay') or '').strip()
                capacity = (md.get('capacity') or '').strip()
                family = (md.get('family') or '').strip()
                familyName = (md.get('familyName') or '').strip()
                md_meta = md.get('metadata') if isinstance(md.get('metadata'), dict) else {}
                # Watch-specific: treat caseSize/material/connectivity as product details
                has_watch_dims = any((md_meta.get(k) or '').strip() for k in ('caseSize', 'caseMaterial', 'connectivity'))
                is_watch = family.lower() == 'watch' or 'watch' in family.lower()
                
                # For regional products, keep name empty for dynamic localized building
                if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', sku):
                    # Keep name empty for regional products so app builds localized name
                    name = ""
                elif not name and familyName:
                    # For non-regional products, use familyName as fallback
                    name = familyName
                
                # Drop completely empty metadata entries (but allow Austrian products with empty names)
                if not any([name, colorKey, colorDisplay, capacity, family, familyName]):
                    continue
                # Special case: Regional products with localized data should have empty names but other data
                if (re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', sku) and not name and colorDisplay and capacity and
                    self._has_localized_color_data(sku, colorDisplay, html)):
                    pass  # Keep localized regional products even with empty names
                
                # Drop incomplete SKUs that lack essential product details
                # These are typically placeholder/legacy SKUs with minimal data
                if (name in ['iPhone', 'Mac', 'Apple Watch'] and  # Generic name
                    not colorKey and not colorDisplay and not capacity and
                    not (is_watch and has_watch_dims)):  # No product details (allow watch dims)
                    continue
                
                # Drop SKUs with generic family but no specific details
                if (family in ['iphone', 'mac', 'watch'] and  # Generic family
                    not colorKey and not capacity and
                    not (is_watch and has_watch_dims)):  # No specific attributes (allow watch dims)
                    continue
                    
                # Update the metadata with the processed name
                md_copy = md.copy()
                md_copy['name'] = name
                
                # Final check: ensure ALL regional products have empty names for dynamic building
                if re.match(r'[A-Z0-9]+[A-Z]{2}/[A-Z]$', sku):
                    md_copy['name'] = ""
                
                pruned[sku] = md_copy
            return pruned

        for token in tokens or []:
            country_to_data: Dict[str, Tuple[str, Dict[str, dict]]] = {}
            inferred_display: Optional[str] = None
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
                skus = self._build_skus_from_payload(payload, family_hint=family)
                # Retry with purchaseOption=fullPrice if few/no SKUs (common for Watch pages)
                if not skus or len(skus) < 3:
                    alt_url = url + ("&" if "?" in url else "?") + "purchaseOption=fullPrice"
                    alt = self._extract_product_data(alt_url)
                    if alt:
                        skus = self._build_skus_from_payload(alt, family_hint=family) or skus
                # Watch enrichment must happen BEFORE pruning so SKUs are retained
                if skus and family.lower() == 'watch' and payload:
                    html_watch = payload.get('html', '')
                    pn_to_dims: Dict[str, Dict[str, str]] = {}
                    # 1) Prefer bootstrap structured products if available
                    bs = payload.get('bootstrap') if isinstance(payload, dict) else None
                    if isinstance(bs, dict):
                        prods = ((bs.get('productSelectionData') or {}).get('products') or [])
                        for p in prods:
                            if not isinstance(p, dict):
                                continue
                            pn = p.get('partNumber') if isinstance(p.get('partNumber'), str) else None
                            if not pn:
                                continue
                            dims = {}
                            # Direct keys
                            for key, val in p.items():
                                if not isinstance(val, str):
                                    continue
                                if 'CaseSize' in key:
                                    dims['caseSize'] = val
                                elif 'CaseMaterial' in key:
                                    dims['caseMaterial'] = val
                                elif 'Connection' in key:
                                    dims['connectivity'] = val
                            # Nested dimensions dict
                            dct = p.get('dimensions') if isinstance(p.get('dimensions'), dict) else {}
                            for key, val in dct.items():
                                if not isinstance(val, str):
                                    continue
                                if 'CaseSize' in key:
                                    dims['caseSize'] = val
                                elif 'CaseMaterial' in key:
                                    dims['caseMaterial'] = val
                                elif 'Connection' in key:
                                    dims['connectivity'] = val
                            if dims:
                                pn_to_dims[pn] = dims
                    # 2) Fallback: regex proximity in raw HTML
                    if not pn_to_dims and html_watch:
                        # partNumber before dimensions
                        for m in re.finditer(
                            r'"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"[\s\S]{0,1000}?"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,400}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"',
                            html_watch, re.IGNORECASE):
                            pn, sz, mat, conn = m.group(1), m.group(2), m.group(3), m.group(4)
                            pn_to_dims[pn] = {"caseSize": sz, "caseMaterial": mat, "connectivity": conn}
                        # dimensions before partNumber
                        for m in re.finditer(
                            r'"(?:watch_cases-)?dimensionCaseSize"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionCaseMaterial"\s*:\s*"([^"]+)"[\s\S]{0,600}?"(?:watch_cases-)?dimensionConnection"\s*:\s*"([^"]+)"[\s\S]{0,1000}?"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"',
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
                            # Merge dimensions
                            for k in ('caseSize', 'caseMaterial', 'connectivity'):
                                v = (dims.get(k) or '').strip()
                                if v:
                                    md[k] = v
                            if md:
                                sku_data['metadata'] = md
                                enriched_count += 1
                        if enriched_count:
                            print(f"[debug][watch] Enriched {enriched_count} SKU(s) with case size/material/connectivity before pruning")
                # Evaluate usefulness before deciding on legacy fallback: count entries with any non-empty metadata
                def _useful_count(d: Dict[str, dict]) -> int:
                    c = 0
                    for md in d.values():
                        if not isinstance(md, dict):
                            continue
                        if any(((md.get('name') or '').strip(),
                                (md.get('colorDisplay') or '').strip(),
                                (md.get('capacity') or '').strip(),
                                (md.get('family') or '').strip(),
                                (md.get('familyName') or '').strip())):
                            c += 1
                    return c
                useful = _useful_count(skus)
                print(f"[debug] {r['code']}/{family}:{token} -> collected {len(skus)} skus ({useful} useful)")
                # Legacy fallback: use RealAppleSkuScraper if still too few (works well for Watch/Mac pages)
                if (useful < 3) and RealAppleSkuScraper is not None and family.lower() in ('watch','mac'):
                    try:
                        legacy = RealAppleSkuScraper(config_file=self.config_path if hasattr(self, 'config_path') else 'scraper_config.json')
                        legacy_data: Any = legacy.extract_product_bootstrap_json(url)
                        # Normalize various shapes returned by legacy extractor
                        def build_from_map(parts_map: dict):
                            merged: Dict[str, dict] = {}
                            for pn, val in parts_map.items():
                                if not isinstance(pn, str) or not re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', pn):
                                    continue
                                if isinstance(val, dict):
                                    merged[pn] = {
                                        "name": val.get("name", ""),
                                        "colorKey": val.get("colorKey", ""),
                                        "colorDisplay": val.get("colorDisplay", ""),
                                        "capacity": val.get("capacity", ""),
                                        "family": val.get("family", family.lower()),
                                        "familyName": val.get("familyName", display_name_for(family, token))
                                    }
                                else:
                                    merged[pn] = {"name": str(val), "colorKey": "", "colorDisplay": "", "capacity": "", "family": family.lower(), "familyName": display_name_for(family, token)}
                            return merged

                        if isinstance(legacy_data, dict):
                            candidate = None
                            # Direct parts map?
                            if any(re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', k) for k in legacy_data.keys() if isinstance(k, str)):
                                candidate = legacy_data
                            # Wrapped under 'extracted_parts'?
                            elif isinstance(legacy_data.get('extracted_parts'), dict):
                                candidate = legacy_data['extracted_parts']
                            if isinstance(candidate, dict):
                                merged = build_from_map(candidate)
                                if merged:
                                    skus.update(merged)
                    except Exception:
                        pass
                # Extract dynamic display name from page data FIRST
                inferred_display = None
                if payload:
                    html = payload.get('html', '')
                    bootstrap = payload.get('bootstrap')
                    # Try to get the most common product family from the SKUs
                    most_common_family = None
                    if skus:
                        family_counts = {}
                        for sku_data in skus.values():
                            if isinstance(sku_data, dict):
                                fam = sku_data.get('family', '')
                                if fam:
                                    family_counts[fam] = family_counts.get(fam, 0) + 1
                        if family_counts:
                            most_common_family = max(family_counts.keys(), key=family_counts.get)
                    inferred_display = self.extract_product_family_name(html, bootstrap, most_common_family)

                # Prune placeholders/empty entries; allow empty dict to still emit per-model file
                skus = _prune_skus(skus)

                # Extract model display names per screen size from ProductSelectionData (SSR) and apply to SKUs
                size_to_model: Dict[str, str] = {}
                if payload:
                    html = payload.get('html', '')
                    # Prefer bootstrap (window.PRODUCT_SELECTION_BOOTSTRAP) when available in payload
                    bs = payload.get('bootstrap')
                    if isinstance(bs, dict):
                        dv = (bs.get('productSelectionData') or {}).get('displayValues') or {}
                        screens = dv.get('dimensionScreensize') or {}
                        if isinstance(screens, dict):
                            for key, value_data in screens.items():
                                if isinstance(value_data, dict):
                                    val = (value_data.get('value') or '')
                                    # Clean HTML tags/entities and normalize whitespace
                                    clean_val = re.sub(r'<[^>]+>', '', val)
                                    clean_val = re.sub(r'&nbsp;', ' ', clean_val)
                                    clean_val = re.sub(r'&[a-zA-Z0-9#]+;', '', clean_val)
                                    clean_val = re.sub(r'\s+', ' ', clean_val).strip()
                                    if clean_val:
                                        size_to_model[key] = clean_val
                    # Fallback to SSR script tag if present
                    if not size_to_model:
                        psd = self.extract_product_selection_data(html, family)
                        if isinstance(psd, dict):
                            dv = psd.get('displayValues') or {}
                            screens = dv.get('dimensionScreensize') or {}
                            if isinstance(screens, dict):
                                for key, value_data in screens.items():
                                    if isinstance(value_data, dict):
                                        val = (value_data.get('value') or '')
                                        clean_val = re.sub(r'<[^>]+>', '', val)
                                        clean_val = re.sub(r'&nbsp;', ' ', clean_val)
                                        clean_val = re.sub(r'&[a-zA-Z0-9#]+;', '', clean_val)
                                        clean_val = re.sub(r'\s+', ' ', clean_val).strip()
                                        if clean_val:
                                            size_to_model[key] = clean_val

                if skus and size_to_model:
                    for sku, sku_data in skus.items():
                        if isinstance(sku_data, dict):
                            sz = (sku_data.get('dimensionScreensize') or sku_data.get('screensize') or sku_data.get('dimensionScreenSize') or sku_data.get('screenSize') or sku_data.get('size') or '').strip()
                            if sz and sz in size_to_model:
                                sku_data['familyName'] = size_to_model[sz]
                # Fallback: derive size->model from decision section keys in HTML if still empty
                if skus and not size_to_model and html:
                    derived: Dict[str, str] = {}
                    for m in re.finditer(r'dimensionScreensize_([a-z0-9_]+)\s*:\s*\{[^}]*?displayText:\s*[\'\"]([^\'\"]+)[\'\"]', html, re.IGNORECASE | re.DOTALL):
                        key = m.group(1)
                        text = m.group(2)
                        # Clean entities/whitespace
                        text = re.sub(r'&nbsp;', ' ', text)
                        text = re.sub(r'&[a-zA-Z0-9#]+;', '', text)
                        text = re.sub(r'\s+', ' ', text).strip()
                        if key and text:
                            derived[key] = text
                    if derived:
                        for sku, sku_data in skus.items():
                            if isinstance(sku_data, dict):
                                sz = (sku_data.get('dimensionScreensize') or sku_data.get('screensize') or sku_data.get('dimensionScreenSize') or sku_data.get('screenSize') or sku_data.get('size') or '').strip()
                                if sz and sz in derived:
                                    sku_data['familyName'] = derived[sz]

                # Ensure each SKU has its dimensionScreensize set using bootstrap products, if available
                if payload and isinstance(payload.get('bootstrap'), dict):
                    bs = payload['bootstrap']
                    products = (bs.get('productSelectionData') or {}).get('products') or []
                    pn_to_size: Dict[str, str] = {}
                    for p in products:
                        if not isinstance(p, dict):
                            continue
                        pn = p.get('partNumber')
                        if not isinstance(pn, str):
                            continue
                        sz = p.get('dimensionScreensize') or (p.get('dimensions') or {}).get('dimensionScreensize') or ''
                        if isinstance(sz, str) and sz:
                            pn_to_size[pn] = sz
                    updated_sizes = 0
                    if pn_to_size:
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            # Only fill if empty
                            have = (sku_data.get('dimensionScreensize') or '').strip()
                            if have:
                                continue
                            # Direct match by full part number
                            if sku in pn_to_size:
                                sku_data['dimensionScreensize'] = pn_to_size[sku]
                                updated_sizes += 1
                                continue
                            # Try base-part match (first 3-6 alnum chars)
                            mbase = re.match(r'^([A-Z0-9]{3,6})', sku)
                            if mbase:
                                base = mbase.group(1)
                                # Find unique match among product parts that start with base
                                matches = [v for k, v in pn_to_size.items() if k.startswith(base)]
                                if len(set(matches)) == 1:
                                    sku_data['dimensionScreensize'] = matches[0]
                                    updated_sizes += 1
                    if updated_sizes:
                        print(f"[debug] Filled dimensionScreensize for {updated_sizes} SKU(s) from bootstrap products")
                # If bootstrap missing in payload, attempt to parse window.PRODUCT_SELECTION_BOOTSTRAP from HTML directly
                elif payload and html:
                    pn_to_size: Dict[str, str] = {}
                    text_blob = None
                    m = re.search(r"PRODUCT_SELECTION_BOOTSTRAP\s*=\s*JSON\.parse\(\s*'(.+?)'\s*\)\s*;", html, re.DOTALL)
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
                        assign = html.find('window.PRODUCT_SELECTION_BOOTSTRAP')
                        if assign != -1:
                            brace = html.find('{', assign)
                            if brace != -1:
                                depth = 0
                                end = brace
                                for i in range(brace, len(html)):
                                    ch = html[i]
                                    if ch == '{': depth += 1
                                    elif ch == '}':
                                        depth -= 1
                                        if depth == 0:
                                            end = i
                                            break
                                text_blob = html[brace:end+1]
                    if text_blob:
                        try:
                            bs = json.loads(re.sub(r',\s*([}\]])', r'\1', text_blob))
                        except Exception:
                            bs = None
                        if isinstance(bs, dict):
                            products = (bs.get('productSelectionData') or {}).get('products') or []
                            for p in products:
                                if not isinstance(p, dict):
                                    continue
                                pn = p.get('partNumber')
                                if not isinstance(pn, str):
                                    continue
                                sz = p.get('dimensionScreensize') or (p.get('dimensions') or {}).get('dimensionScreensize') or ''
                                if isinstance(sz, str) and sz:
                                    pn_to_size[pn] = sz
                    updated_sizes = 0
                    if pn_to_size:
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            have = (sku_data.get('dimensionScreensize') or '').strip()
                            if have:
                                continue
                            if sku in pn_to_size:
                                sku_data['dimensionScreensize'] = pn_to_size[sku]
                                updated_sizes += 1
                                continue
                            mbase = re.match(r'^([A-Z0-9]{3,6})', sku)
                            if mbase:
                                base = mbase.group(1)
                                matches = [v for k, v in pn_to_size.items() if k.startswith(base)]
                                if len(set(matches)) == 1:
                                    sku_data['dimensionScreensize'] = matches[0]
                                    updated_sizes += 1
                    if updated_sizes:
                        print(f"[debug] Filled dimensionScreensize for {updated_sizes} SKU(s) from embedded bootstrap")

                # Robust pass: infer pn->dimensionScreensize by proximity in HTML/JSON (either order)
                if skus and html:
                    pn_to_size_nearby: Dict[str, str] = {}
                    # partNumber before size
                    for m in re.finditer(r'"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"[\s\S]{0,800}?"dimensionScreensize"\s*:\s*"([a-z0-9_]+)"', html, re.IGNORECASE):
                        pn, sz = m.group(1), m.group(2)
                        pn_to_size_nearby[pn] = sz
                    # size before partNumber
                    for m in re.finditer(r'"dimensionScreensize"\s*:\s*"([a-z0-9_]+)"[\s\S]{0,800}?"partNumber"\s*:\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"', html, re.IGNORECASE):
                        sz, pn = m.group(1), m.group(2)
                        pn_to_size_nearby[pn] = sz
                    corrected = 0
                    base_filled = 0
                    if pn_to_size_nearby:
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            if sku in pn_to_size_nearby:
                                sz_html = pn_to_size_nearby[sku]
                                # Override if different or empty
                                if (sku_data.get('dimensionScreensize') or '') != sz_html:
                                    sku_data['dimensionScreensize'] = sz_html
                                    corrected += 1
                                continue
                            # Try base-part unique mapping
                            mbase = re.match(r'^([A-Z0-9]{3,6})', sku)
                            if mbase and not (sku_data.get('dimensionScreensize') or '').strip():
                                base = mbase.group(1)
                                matches = list({v for k, v in pn_to_size_nearby.items() if k.startswith(base) and isinstance(v, str) and v})
                                if len(matches) == 1:
                                    sku_data['dimensionScreensize'] = matches[0]
                                    base_filled += 1
                        if corrected:
                            print(f"[debug] Corrected dimensionScreensize for {corrected} SKU(s) via nearby partNumber/size pairs")
                        if base_filled:
                            print(f"[debug] Filled dimensionScreensize for {base_filled} SKU(s) via base-prefix match from nearby pairs")

                # Fallback: derive dimensionScreensize per (capacity,color) combination from PDP variant hrefs
                if skus and html:
                    combo_to_size: Dict[Tuple[str, str], str] = {}
                    # Prepare color display->key resolution from bootstrap when available
                    href_color_to_key: Dict[str, str] = {}
                    bs = payload.get('bootstrap') if isinstance(payload, dict) else None
                    dv_colors = ((bs.get('productSelectionData') or {}).get('displayValues') or {}).get('dimensionColor', {}) if isinstance(bs, dict) else {}
                    def _norm_color_text(txt: str) -> str:
                        t = txt.lower()
                        t = t.replace('-', ' ')
                        t = re.sub(r'\s+', ' ', t).strip()
                        return t
                    def _compact(txt: str) -> str:
                        return re.sub(r'\s+', '', _norm_color_text(txt))
                    if isinstance(dv_colors, dict):
                        for k, v in dv_colors.items():
                            if not isinstance(v, dict):
                                continue
                            disp = (v.get('value') or v.get('text') or '')
                            if disp:
                                href_color_to_key[_norm_color_text(disp)] = k.lower()
                                href_color_to_key[_compact(disp)] = k.lower()
                    # Match paths like /iphone/iphone-17-pro/6,9%22-display-1tb-silber
                    for m in re.finditer(r'/?iphone/iphone-[-a-z0-9_]+/([0-9],[0-9])%22-display-([0-9]+(?:tb|gb))[-]([a-z0-9\-äöüß]+)', html, re.IGNORECASE):
                        size_raw = m.group(1)
                        cap_raw = m.group(2).lower()
                        col_raw = m.group(3).lower()
                        # Normalize size -> dimension key format
                        size_key = size_raw.replace(',', '_') + 'inch'
                        # Normalize capacity display
                        if cap_raw.endswith('tb'):
                            cap_disp = cap_raw[:-2].upper() + 'TB'
                        else:
                            cap_disp = cap_raw[:-2].upper() + 'GB'
                        # Normalize/resolve color:
                        col_disp_norm = _norm_color_text(col_raw)
                        col_disp_compact = _compact(col_raw)
                        # Try to resolve to colorKey via DV mapping
                        ck = href_color_to_key.get(col_disp_norm) or href_color_to_key.get(col_disp_compact) or col_disp_compact
                        # Store both colorKey and display-normalized variants for matching
                        combo_to_size[(cap_disp, ck)] = size_key
                        combo_to_size[(cap_disp, col_disp_norm)] = size_key
                        combo_to_size[(cap_disp, col_disp_compact)] = size_key
                    # Apply combo->size to SKUs that still lack size
                    applied_combo = 0
                    if combo_to_size:
                        print(f"[debug] Derived combo_to_size for {len(combo_to_size)} combos from variant hrefs")
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            have = (sku_data.get('dimensionScreensize') or '').strip()
                            if have:
                                continue
                            cap_disp = (sku_data.get('capacity') or '').strip().upper().replace(' ', '')
                            color_key = (sku_data.get('colorKey') or '').strip().lower()
                            color_disp_norm = _norm_color_text((sku_data.get('colorDisplay') or ''))
                            color_disp_compact = _compact((sku_data.get('colorDisplay') or ''))
                            for key in [ (cap_disp, color_key), (cap_disp, color_disp_norm), (cap_disp, color_disp_compact) ]:
                                if key in combo_to_size:
                                    sku_data['dimensionScreensize'] = combo_to_size[key]
                                    applied_combo += 1
                                    break
                    if applied_combo:
                        print(f"[debug] Filled dimensionScreensize for {applied_combo} SKU(s) from variant hrefs")


                # If no displayValues mapping was found, derive size->model mapping from decision section displayText now
                if (not size_to_model) and html:
                    derived_map: Dict[str, str] = {}
                    for m in re.finditer(r'dimensionScreensize_([a-z0-9_]+)\s*:\s*\{[^}]*?displayText:\s*[\'\"]([^\'\"]+)[\'\"]', html, re.IGNORECASE | re.DOTALL):
                        key = m.group(1)
                        text = m.group(2)
                        text = re.sub(r'&nbsp;', ' ', text)
                        text = re.sub(r'&[a-zA-Z0-9#]+;', '', text)
                        text = re.sub(r'\s+', ' ', text).strip()
                        if key and text:
                            derived_map[key] = text
                    # Normalize composite keys to base size key as well (e.g., 6_9inch_dimensionColor_silver -> 6_9inch)
                    # Choose the most frequent displayText per base size; on ties, pick the longer text
                    from collections import defaultdict
                    freq_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
                    for k, v in derived_map.items():
                        base_k = k.split('_dimensionColor_')[0]
                        freq_map[base_k][v] += 1
                    base_map: Dict[str, str] = {}
                    for base_k, counts in freq_map.items():
                        # pick by highest count, break ties by longest string
                        best = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)[0][0]
                        base_map[base_k] = best
                    if base_map:
                        size_to_model.update(base_map)
                    if derived_map:
                        print(f"[debug] Derived size_to_model from decision section: {size_to_model}")

                # Base-prefix consistency: ensure all SKUs that share a base part prefix have the same screensize
                if skus:
                    base_map_sizes: Dict[str, Dict[str, int]] = {}
                    for sku, sku_data in skus.items():
                        if not isinstance(sku_data, dict):
                            continue
                        sz = (sku_data.get('dimensionScreensize') or '').strip()
                        if not sz:
                            continue
                        mbase = re.match(r'^([A-Z0-9]{3,6})', sku)
                        if mbase:
                            base = mbase.group(1)
                            base_map_sizes.setdefault(base, {})[sz] = base_map_sizes.setdefault(base, {}).get(sz, 0) + 1
                    base_majority: Dict[str, str] = {}
                    for base, counts in base_map_sizes.items():
                        # pick most frequent size for this base (ties broken by lexicographical order for determinism)
                        best = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0][0]
                        base_majority[base] = best
                    propagated = 0
                    corrected_mismatch = 0
                    if base_majority:
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            mbase = re.match(r'^([A-Z0-9]{3,6})', sku)
                            if not mbase:
                                continue
                            base = mbase.group(1)
                            if base not in base_majority:
                                continue
                            want = base_majority[base]
                            have = (sku_data.get('dimensionScreensize') or '').strip()
                            if not have:
                                sku_data['dimensionScreensize'] = want
                                propagated += 1
                            elif have != want:
                                # If conflicting, enforce majority to keep families balanced
                                sku_data['dimensionScreensize'] = want
                                corrected_mismatch += 1
                    if propagated or corrected_mismatch:
                        print(f"[debug] Enforced base-prefix size consistency: propagated={propagated}, corrected_mismatch={corrected_mismatch}")

                # If we now have a size_to_model and filled dimensionScreensize, apply names and report counts
                if skus and size_to_model:
                    applied = 0
                    size_counts: Dict[str, int] = {}
                    name_counts: Dict[str, int] = {}
                    for sku, sku_data in skus.items():
                        if not isinstance(sku_data, dict):
                            continue
                        sz = (sku_data.get('dimensionScreensize') or '').strip()
                        if sz and sz in size_to_model:
                            before = sku_data.get('familyName') or ''
                            sku_data['familyName'] = size_to_model[sz]
                            if sku_data['familyName'] != before:
                                applied += 1
                            size_counts[sz] = size_counts.get(sz, 0) + 1
                            name_counts[sku_data['familyName']] = name_counts.get(sku_data['familyName'], 0) + 1
                        elif sz:
                            size_counts[sz] = size_counts.get(sz, 0) + 1
                    print(f"[debug] Applied familyName via size_to_model for {applied} SKU(s); mapping={size_to_model}")
                    print(f"[debug] Size distribution after assignment: {size_counts}")
                    if name_counts:
                        print(f"[debug] Name distribution after assignment: {name_counts}")

                # Additional data-driven fallback: derive model by (capacity, color) pairs found in HTML text
                # e.g., "iPhone 17 Pro Max 512GB Tiefblau" / "iPhone 17 Pro 256GB Silber"
                if skus and html:
                    pair_to_model: Dict[Tuple[str, str], str] = {}
                    # Build mapping from localized color display -> colorKey using bootstrap when available
                    color_display_to_key: Dict[str, str] = {}
                    bs = payload.get('bootstrap') if isinstance(payload, dict) else None
                    if isinstance(bs, dict):
                        dv_colors = ((bs.get('productSelectionData') or {}).get('displayValues') or {}).get('dimensionColor', {})
                        if isinstance(dv_colors, dict):
                            for k, v in dv_colors.items():
                                if not isinstance(v, dict):
                                    continue
                                disp = (v.get('value') or v.get('text') or '').strip()
                                if disp:
                                    norm = re.sub(r'&nbsp;', ' ', disp)
                                    norm = re.sub(r'&[a-zA-Z0-9#]+;', '', norm)
                                    norm = re.sub(r'<[^>]+>', '', norm)
                                    norm = re.sub(r'[^A-Za-zÄÖÜäöüß\-\s]', '', norm)
                                    norm = re.sub(r'\s+', ' ', norm).strip().lower()
                                    color_display_to_key[norm] = k.lower()
                    # Capture a product phrase immediately before capacity (no hardcoded model keywords)
                    for m in re.finditer(r'([A-Z][A-Za-z0-9 \-–’\'\"ÄÖÜäöüß]{2,80}?)\s+(\d+\s*(?:GB|TB))\s+([A-Za-z0-9ÄÖÜäöüß\-\s]{2,40})', html):
                        model = re.sub(r'\s+', ' ', m.group(1)).strip()
                        cap = re.sub(r'\s+', '', m.group(2)).upper()  # 512GB / 1TB
                        color_text = m.group(3)
                        # Clean trailing punctuation/tags/entities
                        color_text = re.sub(r'<[^>]+>', '', color_text)
                        color_text = re.sub(r'&nbsp;', ' ', color_text)
                        color_text = re.sub(r'&[a-zA-Z0-9#]+;', '', color_text)
                        color_text = re.sub(r'[^A-Za-z0-9ÄÖÜäöüß\-\s]', '', color_text)
                        color_text = re.sub(r'\s+', ' ', color_text).strip().lower()
                        # Resolve color to colorKey using DV mapping; else fallback to compact token
                        ck = color_display_to_key.get(color_text) or color_text.replace('-', ' ').replace(' ', '')
                        key = (cap, ck)
                        # If multiple variants appear for same pair, choose the longer model string (more specific)
                        if key in pair_to_model:
                            if len(model) > len(pair_to_model[key]):
                                pair_to_model[key] = model
                        else:
                            pair_to_model[key] = model
                    if pair_to_model:
                        applied_pairs = 0
                        skipped_due_to_size = 0
                        for sku, sku_data in skus.items():
                            if not isinstance(sku_data, dict):
                                continue
                            fam_before = (sku_data.get('familyName') or '').strip()
                            cap_disp = (sku_data.get('capacity') or '').strip().upper().replace(' ', '')
                            color_key = (sku_data.get('colorKey') or '').strip().lower()
                            key = (cap_disp, color_key)
                            # Do not override if size-based mapping already applied
                            sz = (sku_data.get('dimensionScreensize') or '').strip()
                            if sz and (sz in size_to_model):
                                skipped_due_to_size += 1
                                continue
                            # Only apply if name is empty or generic
                            if fam_before and fam_before.lower() not in ['', 'iphone']:
                                continue
                            if key in pair_to_model:
                                sku_data['familyName'] = pair_to_model[key]
                                if sku_data['familyName'] != fam_before:
                                    applied_pairs += 1
                        print(f"[debug] Applied familyName via capacity+color pairs for {applied_pairs} SKU(s); pairs={len(pair_to_model)}; skipped_due_to_size={skipped_due_to_size}")

                # Fallback: Update familyName with inferred display name if available
                if skus and inferred_display and inferred_display != 'iPhone':
                    for k, v in skus.items():
                        if isinstance(v, dict) and (v.get('familyName') or '').strip() in ['iPhone', 'iphone']:
                            v['familyName'] = inferred_display
                
                country_to_data[r["code"].upper()] = (shop_path, skus or {})
            if country_to_data:
                self.emit_model_file(family, token, country_to_data, token_display_override=inferred_display)
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
