#!/usr/bin/env python3
"""
Apple SKU Scraper

Scrapes real Apple part numbers from Apple store pages and generates
JSON files for the InventoryWatch app.
"""

import requests
import json
import re
import urllib.parse
import time
import os
import argparse

class RealAppleSkuScraper:
    def __init__(self, config_file='scraper_config.json'):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.config = self.load_config(config_file)
    
    def load_config(self, config_file):
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f" Config file {config_file} not found. Using default configuration.")
            return self.get_default_config()
        except json.JSONDecodeError as e:
            print(f" Error parsing config file: {e}. Using default configuration.")
            return self.get_default_config()
    
    def get_default_config(self):
        """Return default configuration if config file is not available."""
        return {
            "regions": [
                {'url_prefix': 'https://www.apple.com/at/', 'suffix': 'ZD/A', 'name': 'Austria', 'code': 'at'},
                {'url_prefix': 'https://www.apple.com/', 'suffix': 'LL/A', 'name': 'US', 'code': 'us'},
                {'url_prefix': 'https://www.apple.com/uk/', 'suffix': 'QN/A', 'name': 'UK', 'code': 'uk'},
                {'url_prefix': 'https://www.apple.com/au/', 'suffix': 'X/A', 'name': 'Australia', 'code': 'au'}
            ],
            "product_categories": {
                "iphones": {
                    "products": [
                        {"path": "shop/buy-iphone/iphone-17-pro", "categories": ["pro17", "proMax17"]},
                        {"path": "shop/buy-iphone/iphone-17", "categories": ["regular17"]},
                        {"path": "shop/buy-iphone/iphone-air", "categories": ["air"]},
                        {"path": "shop/buy-iphone/iphone-16e", "categories": ["iphone16e"]}
                    ]
                }
            },
            "categorization_rules": {
                "air": ["air"],
                "regular17": ["iphone 17", "17 "],
                "pro17": ["17 pro", "pro 17"],
                "proMax17": ["17 pro max", "pro max 17"],
                "iphone16e": ["16e", "iphone 16e"]
            }
        }

    def extract_product_bootstrap_json(self, url):
        """Extract product data from Apple store pages using metrics JSON."""
        try:
            print(f"Fetching {url}...")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            html_content = response.text
            
            # First try to extract from PRODUCT_SELECTION_BOOTSTRAP (has localized data)
            pattern = r'window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*({.*?});'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                try:
                    json_str = match.group(1)
                    # More aggressive JSON cleaning for Apple Watch pages
                    json_str = re.sub(r',\s*}', '}', json_str)  # Remove trailing commas
                    json_str = re.sub(r',\s*]', ']', json_str)  # Remove trailing commas in arrays
                    json_str = re.sub(r'([{,]\s*)(\w+):', r'\1"\2":', json_str)  # Quote unquoted property names
                    json_str = re.sub(r':\s*([a-zA-Z_]\w*)\s*([,}])', r': "\1"\2', json_str)  # Quote unquoted string values
                    
                    bootstrap_data = json.loads(json_str)
                    extracted_data = self.extract_part_numbers_from_bootstrap(bootstrap_data, html_content)
                    if extracted_data:
                        print(f"Found {len(extracted_data)} products from PRODUCT_SELECTION_BOOTSTRAP")
                        return extracted_data
                except json.JSONDecodeError as e:
                    print(f"Bootstrap JSON decode error: {e}")
                    # Extract product data directly from HTML without JSON parsing
                    if 'buy-watch' in url:
                        print("[WatchHTML] Calling extract_apple_watch_from_raw_data…")
                        return self.extract_apple_watch_from_raw_data(html_content, url)
                    
                    # Try to extract localized colors even if JSON parsing fails
                    localized_colors = self.extract_localized_colors_from_html(html_content)
                    if localized_colors:
                        print(f"Found {len(localized_colors)} localized colors from HTML")
            
            # Fallback to metrics JSON (English names only) but use localized colors if available
            localized_colors = self.extract_localized_colors_from_html(html_content)
            
            metrics_pattern = r'<script type="application/json" id="metrics">({.*?})</script>'
            metrics_match = re.search(metrics_pattern, html_content, re.DOTALL)
            
            if metrics_match:
                try:
                    metrics_data = json.loads(metrics_match.group(1))
                    if 'data' in metrics_data and 'products' in metrics_data['data']:
                        part_numbers = {}
                        for product in metrics_data['data']['products']:
                            part_number = product.get('partNumber', '')
                            name = product.get('name', '')
                            if part_number and name:
                                # Extract enhanced metadata from metrics JSON
                                capacity = ''
                                color_key = ''
                                color_display = ''
                                family = ''
                                family_name = ''
                                
                                # Try to extract capacity
                                if 'capacity' in product:
                                    capacity = product['capacity']
                                elif 'dimensionCapacity' in product:
                                    capacity = product['dimensionCapacity']
                                else:
                                    # Extract from name
                                    capacity_match = re.search(r'(\d+(?:GB|TB))', name, re.IGNORECASE)
                                    if capacity_match:
                                        capacity = capacity_match.group(1).lower()
                                
                                # Try to extract color information
                                if 'color' in product:
                                    color_display = product['color']
                                    color_key = color_display.lower().replace(' ', '')
                                elif 'dimensionColor' in product:
                                    color_key = product['dimensionColor']
                                    # Use localized color name if available, otherwise use title case
                                    color_display = localized_colors.get(color_key.lower(), color_key.title())
                                else:
                                    # Extract color from name - handle multi-word colors
                                    # Pattern: "iPhone [model] [capacity] [color...]"
                                    # Remove iPhone model and capacity to get color
                                    name_parts = name.split()
                                    if len(name_parts) >= 4:  # iPhone, model, capacity, color(s)
                                        # Find capacity position and take everything after it as color
                                        capacity_idx = -1
                                        for i, part in enumerate(name_parts):
                                            if re.match(r'\d+(?:GB|TB)', part, re.IGNORECASE):
                                                capacity_idx = i
                                                break
                                        
                                        if capacity_idx >= 0 and capacity_idx < len(name_parts) - 1:
                                            # Everything after capacity is the color
                                            color_parts = name_parts[capacity_idx + 1:]
                                            color_display = ' '.join(color_parts)
                                            color_key = color_display.lower().replace(' ', '')
                                            # Use localized color name if available
                                            color_display = localized_colors.get(color_key, color_display)
                                        else:
                                            # Fallback: last word
                                            color_display = name_parts[-1]
                                            color_key = color_display.lower().replace(' ', '')
                                            # Use localized color name if available
                                            color_display = localized_colors.get(color_key, color_display)
                                    elif len(name_parts) > 2:
                                        color_display = name_parts[-1]
                                        color_key = color_display.lower().replace(' ', '')
                                        # Use localized color name if available
                                        color_display = localized_colors.get(color_key, color_display)
                                
                                # Extract family information directly from page data
                                if 'family' in product:
                                    family = product['family']
                                    family_name = product.get('familyName', family)
                                elif 'productLocatorFamily' in product:
                                    family = product['productLocatorFamily']
                                    family_name = product.get('familyName', family)
                                else:
                                    # Use the product name as-is from the page
                                    family = 'unknown'
                                    family_name = name.split()[0] if name else 'Unknown'
                                
                                if not family_name:
                                    family_name = name.split()[0] if name else 'Unknown'
                                
                                # Create enhanced metadata structure
                                part_numbers[part_number] = {
                                    "name": name,
                                    "colorKey": color_key or "unknown",
                                    "colorDisplay": color_display or "Unknown",
                                    "capacity": capacity or "",
                                    "family": family or "unknown",
                                    "familyName": family_name or "Unknown"
                                }
                        
                        if part_numbers:
                            print(f"Found {len(part_numbers)} products from metrics JSON")
                            return part_numbers
                except json.JSONDecodeError as e:
                    print(f"Metrics JSON decode error: {e}")
            
            # Fallback to PRODUCT_SELECTION_BOOTSTRAP
            pattern = r'window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*({.*?});'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                try:
                    data = json.loads(json_str)
                    return data
                except json.JSONDecodeError as e:
                    print(f"Bootstrap JSON decode error: {e}")
                    
                    # Regex fallback for bootstrap data
                    part_numbers = {}
                    part_pattern = r'"partNumber":\s*"([^"]+)"[^}]*"productLocatorFamily":\s*"([^"]*)"[^}]*"dimensionCapacity":\s*"([^"]*)"[^}]*"dimensionColor":\s*"([^"]*)"'
                    part_matches = re.findall(part_pattern, json_str)
                    
                    for part_num, family, capacity, color in part_matches:
                        description = f"{family} {capacity} {color}".strip()
                        part_numbers[part_num] = description
                    
                    if part_numbers:
                        return {"extracted_parts": part_numbers}
            
            # If JSON parsing completely failed, try HTML extraction for Apple Watch
            if 'buy-watch' in url:
                print("[WatchHTML] JSON parsing failed, invoking improved Apple Watch HTML extractor…")
                html_data = self.extract_apple_watch_from_raw_data(html_content, url)
                if html_data:
                    return html_data
            
            print("No product data found")
            return None
                
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def extract_localized_colors_from_html(self, html_content):
        """Extract localized color names from HTML content."""
        localized_colors = {}
        
        # Look for localized color names in the HTML content
        # Pattern: "LocalizedColorName","image" followed by finish-colorkey
        color_pattern = r'"([^"]+)","image":[^}]*finish-([a-z]+)'
        matches = re.findall(color_pattern, html_content, re.IGNORECASE)
        
        for localized_name, color_key in matches:
            # Clean up HTML entities and tags
            clean_name = re.sub(r'&nbsp;', ' ', localized_name)  # Replace &nbsp; with space
            clean_name = re.sub(r'<[^>]+>', '', clean_name)      # Remove HTML tags
            clean_name = clean_name.strip()
            
            # Filter out invalid matches (HTML fragments, footnotes, etc.)
            if (len(clean_name) > 2 and 
                not clean_name.startswith('>') and 
                'footnote' not in clean_name.lower() and
                'nota' not in clean_name.lower() and
                'fußnote' not in clean_name.lower() and
                len(clean_name) < 50):  # Reasonable color name length
                
                localized_colors[color_key.lower()] = clean_name
                print(f"Found localized color: {color_key} -> {clean_name}")
        
        return localized_colors

    def extract_watch_dimension_color_map(self, html_content: str) -> dict:
        """Extract the watch_cases-dimensionColor mapping from PRODUCT_SELECTION_BOOTSTRAP.
        This avoids parsing the entire (often invalid) bootstrap JSON by extracting a balanced
        JSON object that is typically valid on its own.
        Returns a dict mapping color keys (e.g., 'rosegold') to localized display names (e.g., 'Roségold').
        """
        if not html_content:
            return {}
        # First, isolate the PRODUCT_SELECTION_BOOTSTRAP payload to reduce noise (balanced-brace parsing)
        assign_idx = html_content.find('window.PRODUCT_SELECTION_BOOTSTRAP')
        source = None
        if assign_idx != -1:
            print(f"DimensionColor: found PRODUCT_SELECTION_BOOTSTRAP at index {assign_idx}")
            # Detect JSON.parse('...') encoded payload
            parse_idx = html_content.find('JSON.parse(', assign_idx)
            quote_idx = html_content.find("'", parse_idx) if parse_idx != -1 else -1
            if parse_idx != -1 and quote_idx != -1:
                print("DimensionColor: detected JSON.parse-encoded bootstrap, attempting to unescape…")
                # Extract until the matching closing single quote, handling escapes
                i = quote_idx + 1
                buf = []
                escaped = False
                while i < len(html_content):
                    ch = html_content[i]
                    if escaped:
                        buf.append(ch)
                        escaped = False
                    elif ch == '\\':
                        escaped = True
                    elif ch == "'":
                        break
                    else:
                        buf.append(ch)
                    i += 1
                encoded = ''.join(buf)
                # Attempt 1: decode JS escapes using unicode_escape
                try:
                    unescaped = bytes(encoded, 'utf-8').decode('unicode_escape')
                    source = unescaped
                except Exception as e1:
                    # Attempt 2: use JSON to unescape
                    try:
                        unescaped = json.loads('"' + encoded.replace('"', '\\"') + '"')
                        source = unescaped
                    except Exception as e2:
                        print(f"DimensionColor: failed to unescape JSON.parse payload: {e1}; {e2}")
                        # As a last resort, regex directly over the encoded payload for key->text
                        fallback_map = {}
                        block_match = re.search(r'\\"watch_cases-dimensionColor\\"\s*:\s*\{(.*?)\}\s*,\s*\\"variantOrder\\"', encoded, re.DOTALL)
                        if block_match:
                            block = block_match.group(1)
                            for m in re.finditer(r'\\"([a-z0-9_]+)\\"\s*:\s*\{[^}]*?\\"text\\"\s*:\s*\\"([^\"]+)\\"', block, re.IGNORECASE|re.DOTALL):
                                fallback_map[m.group(1)] = m.group(2)
                        if fallback_map:
                            print(f"Extracted dimensionColor map via encoded-regex with {len(fallback_map)} entries")
                            return fallback_map
            if source is None:
                # Try direct balanced JSON after assignment
                brace_start = html_content.find('{', assign_idx)
                if brace_start != -1:
                    depth = 0
                    end = brace_start
                    for i in range(brace_start, len(html_content)):
                        ch = html_content[i]
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                end = i
                                break
                    if end > brace_start:
                        source = html_content[brace_start:end+1]
        if source is None:
            print("DimensionColor: PRODUCT_SELECTION_BOOTSTRAP block not found via balanced parse, scanning full HTML")
            source = html_content

        # Prepare multiple normalized variants of the bootstrap string for robust matching
        variants = []
        try:
            variants.append(source)
            variants.append(source.replace('\\"', '"'))
            # unicode escape unescape
            variants.append(bytes(source, 'utf-8').decode('unicode_escape'))
        except Exception:
            variants.append(source)
        # Also add a whitespace-normalized variant
        variants = [re.sub(r"\s+", " ", v) for v in variants if isinstance(v, str)]

        search_space = None
        picked_variant = None
        for idx_variant, cand in enumerate(variants):
            dv_idx = cand.find('"displayValues"')
            if dv_idx != -1:
                print(f"DimensionColor: displayValues found in variant {idx_variant} at index {dv_idx}")
                search_space = cand[dv_idx:]
                picked_variant = idx_variant
                break
        if search_space is None:
            print("DimensionColor: displayValues not found in normalized variants, using first variant as search space")
            search_space = variants[0] if variants else source

        # Attempt direct JSON parse of the search_space to reach productSelectionData.displayValues
        try:
            obj = json.loads(search_space)
            psd = None
            if isinstance(obj, dict):
                psd = obj.get('productSelectionData') or obj
            dvals = psd.get('displayValues') if isinstance(psd, dict) else None
            if isinstance(dvals, dict) and 'watch_cases-dimensionColor' in dvals:
                cmap = {}
                for k, v in dvals['watch_cases-dimensionColor'].items():
                    if isinstance(v, dict) and 'text' in v:
                        cmap[k] = v['text']
                if cmap:
                    print(f"Extracted dimensionColor via direct JSON (search_space) with {len(cmap)} entries")
                    return cmap
        except Exception:
            pass

        # Primary key with quotes
        key = '"watch_cases-dimensionColor"'
        idx = search_space.find(key)
        if idx == -1:
            # Try unquoted key or escaped sequences as fallback
            alt_key_candidates = [
                'watch_cases-dimensionColor',
                '\\"watch_cases-dimensionColor\\"'
            ]
            for k in alt_key_candidates:
                idx = search_space.find(k)
                if idx != -1:
                    key = k
                    break
        if idx == -1:
            print("DimensionColor: key not found in PRODUCT_SELECTION_BOOTSTRAP")
            # Final regex-based fallback: attempt to extract pairs like "<key>": { "text": "<value>" } following the label
            fallback_map = {}
            block_match = re.search(r'watch_cases-dimensionColor\s*:\s*\{(.*?)\}', search_space, re.DOTALL)
            if block_match:
                block = block_match.group(1)
                # quoted keys
                for m in re.finditer(r'"([a-z0-9_]+)"\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"', block, re.IGNORECASE|re.DOTALL):
                    fallback_map[m.group(1)] = m.group(2)
                # unquoted keys
                for m in re.finditer(r'\b([a-z0-9_]+)\b\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"', block, re.IGNORECASE|re.DOTALL):
                    if m.group(1) not in fallback_map:
                        fallback_map[m.group(1)] = m.group(2)
            if fallback_map:
                print(f"Extracted dimensionColor map via regex with {len(fallback_map)} entries")
                return fallback_map
            # Broader fallback: match any *dimensionColor* map under displayValues
            any_block = re.search(r'"[^"]*dimensionColor"\s*:\s*\{(.*?)\}', search_space, re.DOTALL)
            if any_block:
                block = any_block.group(1)
                for m in re.finditer(r'"([a-z0-9_\-]+)"\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"', block, re.IGNORECASE|re.DOTALL):
                    fallback_map[m.group(1)] = m.group(2)
                for m in re.finditer(r'\b([a-z0-9_\-]+)\b\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"', block, re.IGNORECASE|re.DOTALL):
                    if m.group(1) not in fallback_map:
                        fallback_map[m.group(1)] = m.group(2)
            if fallback_map:
                print(f"Extracted dimensionColor via regex with {len(fallback_map)} entries")
                return fallback_map
            # VariantOrder-driven scan (tolerate single quotes)
            vo = re.search(r"[\"']variantOrder[\"']\s*:\s*\[(.*?)\]", search_space, re.DOTALL)
            if vo:
                print("DimensionColor: attempting variantOrder-driven scan…")
                keys_raw = vo.group(1)
                keys = re.findall(r"[\"']([a-z0-9_\-]+)[\"']", keys_raw, re.IGNORECASE)
                for k in keys:
                    # find a block for this key and pull its text (accept ' or ")
                    m_txt = re.search(rf"[\"']{re.escape(k)}[\"']\s*:\s*\{{[^}}]*?[\"']text[\"']\s*:\s*[\"']([^\"']+)[\"']", search_space, re.DOTALL)
                    if m_txt:
                        fallback_map[k] = m_txt.group(1)
                if fallback_map:
                    print(f"Extracted dimensionColor via variantOrder with {len(fallback_map)} entries")
                    return fallback_map
            # ImageName-driven heuristic: imageName contains color key, pair with nearest text
            img_fallback = {}
            tried_images = 0
            for m in re.finditer(r'"imageName"\s*:\s*"watch-case-[^"]*?-([a-z0-9_\-]+)-[^"]*?"', search_space, re.IGNORECASE):
                ckey = m.group(1)
                # find a text label within a small window after the image
                window = search_space[m.end(): m.end()+400]
                t = re.search(r'"text"\s*:\s*"([^"]{2,40})"', window)
                if t:
                    img_fallback[ckey] = t.group(1)
                tried_images += 1
            if img_fallback:
                print(f"Extracted dimensionColor via imageName heuristic with {len(img_fallback)} entries")
                return img_fallback
            else:
                print(f"DimensionColor: imageName heuristic tried {tried_images} candidates but found 0 labels")
            # As a last step, dump the bootstrap/search_space to a debug file for inspection
            try:
                debug_path = os.path.join('InventoryWatch', 'watch_product_selection.json')
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(search_space if isinstance(search_space, str) else '')
                print(f"DimensionColor: wrote debug payload to {debug_path}")
            except Exception as e:
                print(f"DimensionColor: failed to write debug payload: {e}")
            return {}
        # Find the first '{' after the key
        brace_start = search_space.find('{', idx)
        if brace_start == -1:
            print("DimensionColor: opening brace not found after key")
            return {}
        # Diagnostics: show a small window of the source around the key
        try:
            start_dbg = max(idx - 180, 0)
            end_dbg = min(idx + 320, len(search_space))
            snippet = search_space[start_dbg:end_dbg]
            print("DimensionColor snippet:", snippet[:500].replace('\n',' ')[:500])
        except Exception:
            pass
        # Extract a balanced JSON object starting at brace_start
        depth = 0
        end = brace_start
        for i in range(brace_start, len(search_space)):
            ch = search_space[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end <= brace_start:
            print("DimensionColor: failed to locate balanced braces for map")
            return {}
        obj_str = search_space[brace_start:end+1]
        # Clean minor issues
        obj_str = re.sub(r',\s*}', '}', obj_str)
        obj_str = re.sub(r',\s*\]', ']', obj_str)
        try:
            data = json.loads(obj_str)
            color_map = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and 'text' in v and isinstance(v['text'], str):
                        # Normalize key to the same format used elsewhere
                        color_map[str(k)] = v['text']
            if color_map:
                print(f"Extracted dimensionColor map with {len(color_map)} entries from PRODUCT_SELECTION_BOOTSTRAP")
            if color_map:
                return color_map
        except Exception as e:
            print(f"Failed to parse dimensionColor map: {e}")
        # Last-chance heuristic: scan for known color keys with text labels anywhere
        heuristic_map = {}
        known_keys = ['space_gray','silver','rosegold','jet_black','natural','gold','slate','midnight','starlight','black']
        pattern = r'"(' + '|'.join(known_keys) + r')"\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"'
        for m in re.finditer(pattern, source, re.IGNORECASE|re.DOTALL):
            heuristic_map[m.group(1)] = m.group(2)
        if heuristic_map:
            print(f"DimensionColor (heuristic): extracted {len(heuristic_map)} entries")
            return heuristic_map
        return {}

    def extract_localized_color_for_watch(self, html_content, color_key):
        """Extract localized color name for Apple Watch from HTML content."""
        if not color_key or not html_content:
            return None
            
        # Look for Apple Watch color mappings in the HTML
        # Pattern: "colorKey": {"text": "LocalizedName"}
        color_pattern = rf'"{re.escape(color_key)}":\s*{{[^}}]*"text":\s*"([^"]+)"'
        match = re.search(color_pattern, html_content)
        if match:
            localized_name = match.group(1)
            print(f"Found localized Apple Watch color: {color_key} -> {localized_name}")
            return localized_name
        
        # Alternative pattern for Apple Watch colors
        # Pattern: "dimensionColor": {..., "colorKey": {"text": "LocalizedName"}}
        alt_pattern = rf'"watch_cases-dimensionColor"[^}}]*"{re.escape(color_key)}":\s*{{[^}}]*"text":\s*"([^"]+)"'
        alt_match = re.search(alt_pattern, html_content, re.DOTALL)
        if alt_match:
            localized_name = alt_match.group(1)
            print(f"Found localized Apple Watch color (alt): {color_key} -> {localized_name}")
            return localized_name
            
        # No hardcoded fallbacks - all color data should come from page
        print(f"⚠️  Color '{color_key}' not found in page data - this should be extracted from JSON")
            
        return None

    def extract_color_from_product_context(self, html_content, part_number):
        """Extract color from product context and descriptions."""
        # Look for product descriptions that contain the part number and color info
        product_patterns = [
            rf'"{re.escape(part_number)}"[^}}]*"name":\s*"[^"]*\s+([A-Za-z\s]+)\s+(Aluminum|Titanium|Steel)',
            rf'"productTitle":\s*"[^"]*{re.escape(part_number)}[^"]*([A-Za-z\s]+)\s+(GPS|Cellular)"',
            rf'"description":\s*"[^"]*([A-Za-z\s]+)\s+Apple\s+Watch"'
        ]
        
        for pattern in product_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                potential_color = match.group(1).strip()
                # Filter out common non-color words
                non_colors = ['Apple', 'Watch', 'Series', 'Ultra', 'GPS', 'Cellular', 'mm', 'with']
                if potential_color and not any(word in potential_color for word in non_colors):
                    print(f"Extracted color from context: {potential_color}")
                    return potential_color
        
        return None

    def extract_watch_data_from_raw_html(self, html_content):
        """Extract Apple Watch data directly from HTML when JSON parsing fails."""
        # Extract all real Apple part numbers from the page
        part_numbers = {}
        
        # Find all Apple part numbers in the HTML
        part_number_pattern = r'([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])'
        found_parts = set(re.findall(part_number_pattern, html_content))
        
        print(f"Found {len(found_parts)} real part numbers: {list(found_parts)}")
        
        # Extract comprehensive color mappings from the page
        color_mappings = self.extract_comprehensive_color_mappings(html_content)
        
        for part_number in found_parts:
            # Extract product information for each part number
            product_info = self.extract_product_info_for_part(html_content, part_number, color_mappings)
            if product_info:
                part_numbers[part_number] = product_info
        
        return part_numbers

    def extract_comprehensive_color_mappings(self, html_content):
        """Extract all color mappings from Apple's page data."""
        color_mappings = {}
        
        # Pattern 1: Direct color text mappings in localization data
        color_text_pattern = r'"([a-z_]+)":\s*{\s*"text":\s*"([^"]+)"'
        for match in re.finditer(color_text_pattern, html_content):
            color_key, display_name = match.groups()
            if (len(color_key) > 2 and 
                not any(skip in display_name.lower() for skip in ['footnote', 'nota', 'fußnote', 'apple', 'watch']) and
                not display_name.isdigit()):
                color_mappings[color_key] = display_name
                
        # Pattern 2: Watch dimension color mappings with localized text
        dimension_pattern = r'"watch_cases-dimensionColor"[^}]*"([a-z_]+)"[^}]*"text":\s*"([^"]+)"'
        for match in re.finditer(dimension_pattern, html_content):
            color_key, display_name = match.groups()
            color_mappings[color_key] = display_name
            
        # Pattern 3: Product selection color data
        selection_pattern = r'"colorDisplay":\s*"([^"]+)"[^}]*"colorKey":\s*"([^"]+)"'
        for match in re.finditer(selection_pattern, html_content):
            display_name, color_key = match.groups()
            color_mappings[color_key] = display_name
            
        # Pattern 4: Color definitions in Apple's localization JSON
        localization_pattern = r'"([a-z_]+)":\s*"([^"]+)"[^}]*(?="[a-z_]+"|})' 
        for match in re.finditer(localization_pattern, html_content):
            color_key, display_name = match.groups()
            # Filter for likely color names
            if (len(color_key) > 2 and len(display_name) < 30 and
                any(color_word in color_key.lower() for color_word in ['gold', 'silver', 'black', 'white', 'blue', 'red', 'green', 'pink', 'purple', 'gray', 'grey', 'rose', 'space', 'midnight', 'starlight', 'natural', 'slate', 'jet']) and
                not any(skip in display_name.lower() for skip in ['footnote', 'nota', 'fußnote', 'apple', 'watch', 'series', 'ultra', 'se'])):
                color_mappings[color_key] = display_name
                
        # Pattern 5: Apple Watch specific color mappings - look for actual localized text
        specific_color_patterns = [
            # Pattern for localized color text in Apple's data structure
            r'"(natural|gold|rosegold|space_gray|jet_black|slate|silver|midnight|starlight)":\s*{\s*"text":\s*"([^"]+)"',
            # Pattern for color display names in product data
            r'"colorKey":\s*"(natural|gold|rosegold|space_gray|jet_black|slate|silver|midnight|starlight)"[^}]*"colorDisplay":\s*"([^"]+)"',
            # Pattern for German localization data
            r'"(natural|gold|rosegold|space_gray|jet_black|slate|silver|midnight|starlight)":\s*"([A-Za-zäöüÄÖÜß\s]+)"(?=\s*[,}])',
        ]
        
        for pattern in specific_color_patterns:
            for match in re.finditer(pattern, html_content):
                color_key, display_name = match.groups()
                if (len(display_name) > 2 and len(display_name) < 30 and
                    not any(skip in display_name.lower() for skip in ['footnote', 'nota', 'fußnote', 'gps', 'cellular', 'mm']) and
                    not display_name.startswith('{') and not display_name.endswith('}')):
                    color_mappings[color_key] = display_name
            
        print(f"Extracted {len(color_mappings)} color mappings: {color_mappings}")
        return color_mappings

    def extract_product_info_for_part(self, html_content, part_number, color_mappings):
        """Extract complete product information for a specific part number."""
        # Look for product data associated with this part number
        part_data_patterns = [
            rf'"{re.escape(part_number)}"[^}}]*?"dimensions":\s*{{([^}}]+)}}',
            rf'"{re.escape(part_number)}"[^}}]*?"name":\s*"([^"]+)"',
            rf'"partNumber":\s*"{re.escape(part_number)}"[^}}]*?}}'
        ]
        
        product_data = {}
        
        # Extract dimensions if available
        for pattern in part_data_patterns:
            match = re.search(pattern, html_content)
            if match:
                if 'dimensions' in pattern:
                    dimensions_str = match.group(1)
                    
                    # Extract individual dimensions
                    case_size = re.search(r'"watch_cases-dimensionCaseSize":\s*"([^"]+)"', dimensions_str)
                    case_material = re.search(r'"watch_cases-dimensionCaseMaterial":\s*"([^"]+)"', dimensions_str)
                    connectivity = re.search(r'"watch_cases-dimensionConnection":\s*"([^"]+)"', dimensions_str)
                    color = re.search(r'"watch_cases-dimensionColor":\s*"([^"]+)"', dimensions_str)
                    
                    product_data.update({
                        'case_size': case_size.group(1) if case_size else "42mm",
                        'case_material': case_material.group(1) if case_material else "aluminum", 
                        'connectivity': connectivity.group(1) if connectivity else "gps",
                        'color_key': color.group(1) if color else ""
                    })
                    break
        
        # If no dimensions found, try to extract from product name patterns
        if not product_data:
            name_patterns = [
                rf'"{re.escape(part_number)}"[^}}]*?"name":\s*"([^"]*(\d+mm)[^"]*)"',
                rf'"productTitle":\s*"[^"]*{re.escape(part_number)}[^"]*"'
            ]
            
            for pattern in name_patterns:
                match = re.search(pattern, html_content)
                if match:
                    name = match.group(1)
                    # Extract size from name
                    size_match = re.search(r'(\d+mm)', name)
                    product_data['case_size'] = size_match.group(1) if size_match else "42mm"
                    
                    # Guess material and connectivity from name
                    if 'titanium' in name.lower():
                        product_data['case_material'] = 'titanium'
                    elif 'steel' in name.lower():
                        product_data['case_material'] = 'steel'
                    else:
                        product_data['case_material'] = 'aluminum'
                        
                    if 'cellular' in name.lower() or 'gpscell' in name.lower():
                        product_data['connectivity'] = 'gpscell'
                    else:
                        product_data['connectivity'] = 'gps'
                    break
        
        if not product_data:
            return None
            
        # Ensure case_size has 'mm' suffix
        if not product_data['case_size'].endswith('mm'):
            product_data['case_size'] = product_data['case_size'] + 'mm'
            
        # Map connectivity for display
        connectivity_display = 'GPS'
        if product_data['connectivity'] == 'gpscell':
            connectivity_display = 'GPS + Cellular'
            
        # Get localized color name
        color_key = product_data.get('color_key', '')
        localized_color = self.extract_localized_color_for_watch(html_content, color_key)
        
        if localized_color:
            color_display = localized_color
        else:
            # Fallback to standard color names if not found in page data
            color_fallbacks = {
                'natural': 'Natural',
                'gold': 'Gold', 
                'rosegold': 'Rose Gold',
                'space_gray': 'Space Gray',
                'jet_black': 'Jet Black',
                'slate': 'Slate',
                'silver': 'Silver',
                'midnight': 'Midnight',
                'starlight': 'Starlight',
                'black': 'Black'
            }
            color_display = color_fallbacks.get(color_key, product_data['case_material'].title())
        
        # Extract price if available
        price_pattern = rf'"priceKey":\s*"[^"]*{re.escape(product_data["case_material"])}[^"]*{re.escape(product_data["case_size"].replace("mm", ""))}[^"]*{re.escape(product_data["connectivity"])}[^"]*"[^}}]*?"amount":\s*([0-9.]+)'
        price_match = re.search(price_pattern, html_content)
        price = float(price_match.group(1)) if price_match else 0.0
        
        # Generate product name
        name = f"Apple Watch {product_data['case_size']} {color_display} {product_data['case_material'].title()} {connectivity_display}"
        
        return {
            "name": name,
            "colorKey": color_key if color_key else product_data['case_material'],
            "colorDisplay": color_display,
            "capacity": "",
            "family": "apple_watch",
            "urlSlug": f"{product_data['case_material']}_{product_data['case_size']}_{product_data['connectivity']}",
            "price": price,
            "case_size": product_data['case_size'],
            "case_material": product_data['case_material'],
            "connectivity": connectivity_display
        }

    def extract_watch_dimensions_from_html(self, html_content):
        """Extract all available Apple Watch dimensions from HTML content."""
        dimensions = {
            'materials': {},
            'sizes': {},
            'colors': {},
            'connections': {}
        }
        
        try:
            # Extract materials
            material_pattern = r'"watch_cases-dimensionCaseMaterial"[^}]*"(\w+)":\s*{[^}]*"header":\s*"([^"]*)"'
            material_matches = re.findall(material_pattern, html_content)
            for key, header in material_matches:
                clean_header = re.sub(r'<[^>]+>', '', header).strip()
                dimensions['materials'][key] = clean_header
            
            # Extract sizes
            size_pattern = r'"watch_cases-dimensionCaseSize"[^}]*"(\w+)":\s*{[^}]*"header":\s*"([^"]*)"'
            size_matches = re.findall(size_pattern, html_content)
            for key, header in size_matches:
                clean_header = re.sub(r'&nbsp;', ' ', header).strip()
                dimensions['sizes'][key] = clean_header
            
            # Extract colors with localized names
            color_pattern = r'"watch_cases-dimensionColor"[^}]*"(\w+)":\s*{[^}]*"text":\s*"([^"]*)"'
            color_matches = re.findall(color_pattern, html_content)
            for key, text in color_matches:
                dimensions['colors'][key] = text
            
            # Extract connections
            conn_pattern = r'"watch_cases-dimensionConnection"[^}]*"(\w+)":\s*{[^}]*"header":\s*"([^"]*)"'
            conn_matches = re.findall(conn_pattern, html_content)
            for key, header in conn_matches:
                clean_header = re.sub(r'<[^>]+>', '', header).split('\n')[0].strip()
                dimensions['connections'][key] = clean_header
            
            print(f"Extracted dimensions: {len(dimensions['materials'])} materials, {len(dimensions['sizes'])} sizes, {len(dimensions['colors'])} colors, {len(dimensions['connections'])} connections")
            
        except Exception as e:
            print(f"Error extracting dimensions: {e}")
        
        return dimensions

    def extract_url_components_from_sample_urls(self, selection_data):
        """Extract URL components from Apple's sample URLs to understand the format."""
        url_components = {}
        
        # Look for sample URLs in the data
        if 'watchProductSelectionDataNoJS' in selection_data:
            for sample in selection_data['watchProductSelectionDataNoJS']:
                if 'url' in sample:
                    url = sample['url']
                    # Extract URL components directly from sample data instead of hardcoded parsing
                    if 'components' in sample:
                        # Use components directly from Apple's data if available
                        components = sample['components']
                    elif 'url' in sample and sample.get('text'):
                        # Parse from the descriptive text which contains the actual product info
                        text = sample['text']
                        components = self.extract_components_from_description(text)
                    else:
                        # Fallback: extract from URL structure
                        if '/buy-watch/' in url:
                            path_part = url.split('/buy-watch/')[-1]
                            components = path_part.split('-')
                        
                        if len(components) >= 4:
                            # Parse: 46mm-cellular-gold-titan-...
                            size = components[0]
                            connectivity = components[1]
                            color = components[2]
                            material = components[3]
                            
                            # Store the actual URL format used by Apple
                            key = f"{material}_{size}_{connectivity}_{color}"
                            url_components[key] = {
                                'size': size,
                                'connectivity': connectivity, 
                                'color': color,
                                'material': material
                            }
        
        return url_components

    # -----------------
    # iPhone helpers
    # -----------------
    def _iphone_token_for_category(self, category: str) -> str:
        """Map scraper category keys to sourcePage token strings for iPhone."""
        if not category:
            return ''
        c = category.lower()
        # 17 series
        if c == 'regular17':
            return 'iphone-17'
        if c == 'pro17':
            return 'iphone-17-pro'
        if c == 'promax17' or c == 'promax':
            return 'iphone-17-pro-max'
        # 16 series
        if c == 'iphone16':
            return 'iphone-16'
        if c == 'iphone16plus':
            return 'iphone-16-plus'
        if c == 'iphone16e':
            return 'iphone-16e'
        # Air
        if c == 'air' or c == 'iphoneair':
            return 'iphone-air'
        return ''

    def _iphone_display_for_token(self, token: str) -> str:
        """Derive a human-friendly display from the token. Prefer config when possible; otherwise prettify."""
        if not token:
            return ''
        # Try to use configured product names for known tokens
        cfg_products = self.config.get('product_categories', {}).get('iphones', {}).get('products', [])
        base = None
        # Map tokens to config names by suffix heuristics
        for p in cfg_products:
            path = p.get('path', '')
            name = p.get('name', '')
            last = path.strip('/').split('/')[-1]
            if last == token:
                base = name
                break
        if base:
            return base
        # Fallback: prettify token (e.g., iphone-16-plus -> iPhone 16 Plus)
        pretty = token.replace('-', ' ').title()
        # Ensure iPhone capitalization exact
        if pretty.lower().startswith('iphone'):
            pretty = 'iPhone' + pretty[6:]
        return pretty

    def extract_apple_watch_data(self, selection_data, localized_colors):
        """Extract Apple Watch data from productSelectionData with real part numbers."""
        part_numbers = {}
        
        try:
            # Extract URL components from sample URLs
            url_components = self.extract_url_components_from_sample_urls(selection_data)
            
            # Extract localized colors from dimensionColor
            colors = {}
            if 'dimensionColor' in selection_data:
                for key, color_data in selection_data['dimensionColor'].items():
                    if isinstance(color_data, dict) and 'name' in color_data:
                        localized_name = color_data['name']
                        colors[key] = localized_name
                        print(f"Found Apple Watch color: {key} -> {localized_name}")
            
            # Extract all products from the products array
            if 'products' in selection_data:
                for product in selection_data['products']:
                    part_number = product.get('partNumber', '')
                    dimensions = product.get('dimensions', {})
                    price_key = product.get('priceKey', '')
                    
                    if part_number and dimensions:
                        # Extract dimensions
                        case_size = dimensions.get('watch_cases-dimensionCaseSize', '')
                        case_material = dimensions.get('watch_cases-dimensionCaseMaterial', '')
                        color_key = dimensions.get('watch_cases-dimensionColor', '')
                        connectivity = dimensions.get('watch_cases-dimensionConnection', '')
                        
                        # Get localized color name
                        color_display = colors.get(color_key, color_key.replace('_', ' ').title())
                        
                        # Map connectivity to display format
                        connectivity_display = 'GPS'
                        if connectivity == 'gpscell':
                            connectivity_display = 'GPS + Cellular'
                        
                        # Build descriptive name with localized color
                        description = f"Apple Watch {case_size} {color_display} {case_material.title()} {connectivity_display}"
                        
                        # Create product key
                        product_key = f"watch_{case_material}_{case_size}_{connectivity}_{color_key}"
                        
                        # Try to get price from selection data
                        price = 0.0
                        if 'displayValues' in selection_data and 'prices' in selection_data['displayValues']:
                            price_data = selection_data['displayValues']['prices'].get(price_key, {})
                            price = price_data.get('amount', 0.0)
                        
                        # Get URL components for this configuration
                        url_key = f"{case_material}_{case_size}_{connectivity}_{color_key}"
                        url_format = url_components.get(url_key, {})
                        
                        # Extract metadata including case size, material, connectivity, and color
                        metadata = {
                            'caseSize': case_size,
                            'caseMaterial': case_material,
                            'connectivity': connectivity_display,
                            'color': color_display,
                            'sourcePage': 'apple-watch',
                            'isRealPartNumber': True,
                            'partNumber': part_number,
                            'urlFormat': url_format
                        }
                        
                        part_numbers[product_key] = {
                            "name": description,
                            "colorKey": color_key,
                            "colorDisplay": color_display,
                            "capacity": "",
                            "family": "apple_watch",
                            "familyName": "Apple Watch",
                            "urlSlug": f"{case_material}_{case_size}_{connectivity}_{color_key}",
                            "price": price,
                            "partNumber": part_number,
                            "metadata": metadata
                        }
                        
                        print(f"Found Apple Watch SKU: {description} - ${price:.2f} (Part: {part_number})")
            
            print(f"Generated {len(part_numbers)} Apple Watch configurations with real part numbers")
            return part_numbers
            
        except Exception as e:
            print(f"Error extracting Apple Watch data: {e}")
            return {}

    def extract_part_numbers_from_bootstrap(self, bootstrap_data, html_content=None):
        """Extract part numbers from various data sources."""
        part_numbers = {}
        color_mappings = {}
        
        # First, try to get localized color names from HTML content
        localized_colors = {}
        if html_content:
            localized_colors = self.extract_localized_colors_from_html(html_content)
        
        try:
            # Handle metrics JSON data first (cleanest format)
            if 'metrics_products' in bootstrap_data:
                return bootstrap_data['metrics_products']
            
            # Handle the regex-extracted parts
            if 'extracted_parts' in bootstrap_data:
                return bootstrap_data['extracted_parts']
            
            # Extract from displayValues structure (like in selection.json)
            if 'displayValues' in bootstrap_data and 'dimensionColor' in bootstrap_data['displayValues']:
                display_values = bootstrap_data['displayValues']['dimensionColor']
                for color_key, color_data in display_values.items():
                    if color_key not in ['title', 'variantOrder', 'variantSortOrder']:
                        # Remove HTML tags and clean up the display name
                        display_name = re.sub(r'<[^>]+>', '', color_data['value']).strip()
                        color_mappings[color_key] = display_name
                        print(f"Found color mapping: {color_key} -> {display_name}")
                
                # Also extract localized product names if available
                localized_product_names = {}
                if 'energyComplianceDictionary' in bootstrap_data:
                    for compliance_key, compliance_data in bootstrap_data['energyComplianceDictionary'].items():
                        if 'productName' in compliance_data:
                            product_name = compliance_data['productName']
                            localized_product_names[compliance_key] = product_name
                            print(f"Found localized product name: {compliance_key} -> {product_name}")
            
            # Also check productSelectionData structure
            elif 'productSelectionData' in bootstrap_data:
                selection_data = bootstrap_data['productSelectionData']
                
                # Handle Apple Watch format (no products array)
                if 'products' not in selection_data and 'displayValues' in selection_data:
                    return self.extract_apple_watch_data(selection_data, localized_colors)
                
                # Handle iPhone format (has products array)
                elif 'products' in selection_data:
                    # Extract color display values
                    display_values = selection_data['displayValues']
                    if 'dimensionColor' in display_values:
                        for color_key, color_data in display_values['dimensionColor'].items():
                            if color_key not in ['title', 'variantOrder', 'variantSortOrder']:
                                # Remove HTML tags and clean up the display name
                                display_name = re.sub(r'<[^>]+>', '', color_data['value']).strip()
                                
                                # Use localized name if available, otherwise use the extracted name
                                if color_key.lower() in localized_colors:
                                    display_name = localized_colors[color_key.lower()]
                                
                                color_mappings[color_key] = display_name
                
                for product in bootstrap_data['productSelectionData']['products']:
                    part_number = product.get('partNumber', '')
                    if part_number:
                        # Build description using the same fields as the JS snippet
                        family = product.get('productLocatorFamily', '')
                        capacity = product.get('dimensionCapacity', '')
                        color_key = product.get('dimensionColor', '')
                        
                        # Extract color display name from page data
                        color_display = self.extract_color_from_page_data(product) or color_key
                        
                        # Use family name directly from page data
                        family_name = metadata.get('familyName', family)
                        
                        # Format capacity
                        if capacity:
                            capacity_formatted = capacity.upper()
                        else:
                            capacity_formatted = ''
                        
                        description = f"{family_name} {capacity_formatted} {color_display}".strip()
                        
                        # Extract URL format from sample URLs for this specific product
                        url_format = self.extract_url_format_for_product(selection_data, case_size, case_material, connectivity, color_key)
                        
                        # Extract metadata including case size, material, connectivity, and color
                        metadata = {
                            'caseSize': case_size,
                            'caseMaterial': case_material,
                            'connectivity': connectivity_display,
                            'color': color_display,
                            'sourcePage': 'apple-watch',
                            'isRealPartNumber': True,
                            'partNumber': part_number,
                            'urlFormat': url_format
                        }
            
            # Fallback to other possible structures
            elif 'products' in bootstrap_data:
                for product in bootstrap_data['products']:
                    part_number = product.get('partNumber', '')
                    if part_number:
                        # Try different field combinations
                        name = product.get('productName', product.get('name', ''))
                        capacity = product.get('capacity', product.get('dimensionCapacity', ''))
                        color = product.get('color', product.get('dimensionColor', ''))
                        
                        if isinstance(capacity, dict):
                            capacity = capacity.get('raw', capacity.get('value', ''))
                        if isinstance(color, dict):
                            color = color.get('name', color.get('value', ''))
                        
                        # For fallback, create simple structure
                        description = f"{name} {capacity} {color}".strip()
                        part_numbers[part_number] = {
                            "name": description,
                            "colorKey": color.lower().replace(' ', '') if color else 'unknown',
                            "colorDisplay": color,
                            "capacity": capacity.lower() if capacity else '',
                            "family": 'unknown',
                            "familyName": name
                        }
            
            return part_numbers
            
        except Exception as e:
            print(f"Error extracting part numbers from bootstrap: {e}")
            return {}

    def extract_apple_watch_from_raw_data(self, html_content, url):
        """Extract Apple Watch data from raw HTML when bootstrap parsing fails"""
        part_numbers = {}
        
        try:
            print("[WatchHTML] Enter extract_apple_watch_from_raw_data")
            # Derive locale-specific material tokens from sample URLs on the page
            sample_urls = re.findall(r'https?://www\.apple\.com/[a-z\-]+/shop/buy-watch/apple-watch/([^\"]+)', html_content)
            aluminum_token = 'aluminum'
            titanium_token = 'titanium'
            for s in sample_urls:
                # Normalize path part only
                path = s.split('?')[0]
                # Detect aluminium vs aluminum
                if '-aluminium' in path:
                    aluminum_token = 'aluminium'
                # Detect titanium variants in order of specificity
                if re.search(r'-titanio(\b|-)', path):
                    titanium_token = 'titanio'
                elif re.search(r'-titane(\b|-)', path):
                    titanium_token = 'titane'
                elif re.search(r'-titan(\b|-)', path):
                    titanium_token = 'titan'
                elif re.search(r'-titanium(\b|-)', path):
                    titanium_token = 'titanium'
            # First, extract all available dimensions from the HTML to generate complete combinations
            dimensions = self.extract_watch_dimensions_from_html(html_content)
            print(f"[WatchHTML] Dimensions extracted: {list(dimensions.keys()) if isinstance(dimensions, dict) else type(dimensions)}")
            # Extract a precise color map from PRODUCT_SELECTION_BOOTSTRAP displayValues
            print("[WatchHTML] Building dimension_color_map…")
            dimension_color_map = self.extract_watch_dimension_color_map(html_content)
            print(f"[WatchHTML] dimension_color_map size: {len(dimension_color_map) if dimension_color_map else 0}")
            if not dimension_color_map:
                # Fallback 1: plain JSON structure anywhere in the HTML
                fb1 = {}
                m = re.search(r'"watch_cases-dimensionColor"\s*:\s*\{(.*?)\}\s*,\s*"variantOrder"', html_content, re.DOTALL)
                if m:
                    block = m.group(1)
                    for mm in re.finditer(r'"([a-z0-9_]+)"\s*:\s*\{[^}]*?"text"\s*:\s*"([^"]+)"', block, re.IGNORECASE|re.DOTALL):
                        fb1[mm.group(1)] = mm.group(2)
                if fb1:
                    print(f"DimensionColor (fb1): extracted {len(fb1)} entries")
                    dimension_color_map = fb1
                # Fallback 2: encoded structure inside JSON.parse
                if not dimension_color_map:
                    fb2 = {}
                    me = re.search(r'\\"watch_cases-dimensionColor\\"\s*:\s*\{(.*?)\}\s*,\s*\\"variantOrder\\"', html_content, re.DOTALL)
                    if me:
                        block = me.group(1)
                        for mm in re.finditer(r'\\"([a-z0-9_]+)\\"\s*:\s*\{[^}]*?\\"text\\"\s*:\s*\\"([^\"]+)\\"', block, re.IGNORECASE|re.DOTALL):
                            fb2[mm.group(1)] = mm.group(2)
                    if fb2:
                        print(f"DimensionColor (fb2): extracted {len(fb2)} entries from encoded payload")
                        dimension_color_map = fb2
            # Fallback 3: heuristic scan across entire HTML for localized colors
            localized_colors_html = self.extract_localized_colors_from_html(html_content)
            if not dimension_color_map and localized_colors_html:
                print(f"DimensionColor (fb3): reusing {len(localized_colors_html)} entries from localized colors scan")
                # normalize keys to lower-case to match color keys from dimensions
                dimension_color_map = {k.lower(): v for k, v in localized_colors_html.items()}
            
            # Look for part numbers in the raw HTML using regex patterns
            part_number_patterns = [
                r'"part":\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"',  # Bootstrap format
                r'"partNumber":\s*"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"',
                r'data-part-number="([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])"',
                r'"([A-Z0-9]{4,8}[A-Z]{2}/[A-Z])":\s*{[^}]*"dimensions"',
            ]
            
            found_parts = set()
            for pattern in part_number_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                found_parts.update(matches)
            
            print(f"Found {len(found_parts)} real part numbers: {list(found_parts)}")
            
            # Create a mapping of part numbers to their dimensions
            part_to_dimensions = {}
            for part_number in found_parts:
                # Simple validation for Apple part numbers (format: XXXXX/X or XXXXXX/X)
                if re.match(r'^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$', part_number):
                    # Try to find associated data for this part number
                    part_data_pattern = rf'"{re.escape(part_number)}"[^}}]*?"dimensions":\s*{{([^}}]+)}}'
                    part_match = re.search(part_data_pattern, html_content)
                    
                    if part_match:
                        dimensions_str = part_match.group(1)
                        
                        # Extract dimensions
                        case_size = re.search(r'"watch_cases-dimensionCaseSize":\s*"([^"]+)"', dimensions_str)
                        case_material = re.search(r'"watch_cases-dimensionCaseMaterial":\s*"([^"]+)"', dimensions_str)
                        connectivity = re.search(r'"watch_cases-dimensionConnection":\s*"([^"]+)"', dimensions_str)
                        color = re.search(r'"watch_cases-dimensionColor":\s*"([^"]+)"', dimensions_str)
                        
                        case_size = case_size.group(1) if case_size else "42mm"
                        case_material = case_material.group(1) if case_material else "aluminum"
                        connectivity = connectivity.group(1) if connectivity else "gps"
                        color = color.group(1) if color else ""
                        
                        # Ensure case_size has 'mm' suffix
                        if not case_size.endswith('mm'):
                            case_size = case_size + 'mm'
                        
                        # Map connectivity
                        connectivity_display = 'GPS'
                        if connectivity == 'gpscell':
                            connectivity_display = 'GPS + Cellular'
                        
                        # Try to find price
                        price_pattern = rf'"priceKey":\s*"[^"]*{re.escape(case_material)}[^"]*{re.escape(case_size.replace("mm", ""))}[^"]*{re.escape(connectivity)}[^"]*"[^}}]*?"amount":\s*([0-9.]+)'
                        price_match = re.search(price_pattern, html_content)
                        price = float(price_match.group(1)) if price_match else 0.0
                        
                        # Extract localized color using precise dimension color map first,
                        # then fall back to HTML regex methods
                        localized_color = None
                        if color and color in dimension_color_map:
                            localized_color = dimension_color_map[color]
                        if not localized_color:
                            localized_color = self.extract_localized_color_for_watch(html_content, color)
                        if not localized_color and color and localized_colors_html:
                            # try HTML scan map as last resort
                            localized_color = localized_colors_html.get(color.lower())
                        
                        # Generate name and key with localized color
                        if localized_color and localized_color != color:
                            name = f"Apple Watch {case_size} {localized_color} {case_material.title()} {connectivity_display}"
                            color_display = localized_color
                        else:
                            name = f"Apple Watch {case_size} {case_material.title()} {connectivity_display}"
                            color_display = case_material.title()
                        
                        # Determine source page (series, se, ultra) from URL for metadata/url formatting
                        if 'apple-watch-ultra' in url:
                            source_page = 'apple-watch-ultra'
                            url_format_key = 'watch_ultra'
                        elif 'apple-watch-se' in url:
                            source_page = 'apple-watch-se'
                            url_format_key = 'watch_se'
                        else:
                            source_page = 'apple-watch'
                            url_format_key = 'watch_series'

                        # Build urlSlug using optional template from config
                        url_slug = f"{case_material}_{case_size}_{connectivity}"
                        url_fmt = (
                            self.config.get('product_categories', {})
                                .get('apple_watch', {})
                                .get('url_format', {})
                                .get(url_format_key)
                        )
                        if isinstance(url_fmt, str) and url_fmt:
                            # Safe token replacement
                            # Prepare localized/slug tokens
                            slug_color = (color_display or '').strip().lower().replace(' ', '-').replace('_', '-')
                            # Map connectivity to URL token (gpscell -> cellular)
                            url_conn = 'cellular' if connectivity == 'gpscell' else 'gps'
                            # Choose localized material token from samples when possible
                            mat_token = (case_material or '').strip().lower()
                            if mat_token == 'aluminum':
                                mat_token = aluminum_token
                            elif mat_token == 'titanium':
                                mat_token = titanium_token

                            token_map = {
                                'size': case_size,
                                'caseSize': case_size,
                                'material': mat_token.replace(' ', '-'),
                                'connectivity': url_conn,
                                'color': urllib.parse.unquote(slug_color)
                            }
                            try:
                                url_slug = url_fmt.format(**token_map)
                            except Exception:
                                # Fallback to default if template didn't work
                                url_slug = f"{case_material}_{case_size}_{connectivity}"

                        # URL-encode the slug (keep hyphens)
                        url_slug = urllib.parse.quote(url_slug, safe='-')

                        # Use the real Apple part number as the key instead of synthetic key
                        part_numbers[part_number] = {
                            "name": name,
                            "colorKey": color if color else case_material,
                            "colorDisplay": color_display,
                            "capacity": "",
                            "family": "apple_watch",
                            "urlSlug": url_slug,
                            "price": price,
                            "partNumber": part_number,
                            "metadata": {
                                "caseSize": case_size,
                                "caseMaterial": case_material,
                                "connectivity": connectivity_display,
                                "color": color_display,
                                "sourcePage": source_page,
                                "isRealPartNumber": True,
                                "partNumber": part_number
                            }
                        }
            
            return part_numbers
            
        except Exception as e:
            print(f"Error extracting Apple Watch from raw data: {e}")
            return {}

    def discover_watch_models(self, region):
        """Discover all available watch models from the main watch page."""
        print(f"🔍 Discovering watch models for region: {region}")
        
        # Check the shop page to discover available models
        # Get shop URL from config or use default
        region_config = next((r for r in self.config.get('regions', []) if r['code'] == region), None)
        if region_config and 'shop_paths' in region_config:
            shop_path = region_config['shop_paths'].get('apple_watch', 'shop/buy-watch')
            shop_watch_url = f"{region_config['url_prefix']}{shop_path}"
        else:
            # Fallback to default structure
            shop_watch_url = f"https://www.apple.com/{region}/shop/buy-watch"
        
        discovered_models = {}
        
        try:
            print(f"Fetching {shop_watch_url}...")
            response = self.session.get(shop_watch_url, timeout=30)
            response.raise_for_status()
            
            # Look for links to individual watch product pages
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all watch product links
            watch_links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/shop/buy-watch/' in href and href != '/shop/buy-watch':
                    # Extract the watch model from the URL
                    if href.startswith('/'):
                        full_url = f"https://www.apple.com{href}"
                    else:
                        full_url = href
                    
                    # Extract model info from link data instead of URL parsing
                    model_path = link.get('data-model', href.split('/')[-1].split('?')[0])
                    if model_path and model_path != '':
                        watch_links.append({
                            'model': model_path,
                            'url': full_url,
                            'display_name': link.get_text(strip=True) or model_path
                        })
            
            # Remove duplicates
            unique_models = {}
            for link in watch_links:
                model = link['model']
                if model not in unique_models:
                    unique_models[model] = link
            
            print(f"🎯 Discovered {len(unique_models)} watch models:")
            for model, info in unique_models.items():
                print(f"  - {model}: {info['display_name']}")
            
            # Now scrape each individual model page
            for model, info in unique_models.items():
                print(f"\n📱 Scraping {model}...")
                model_data = self.scrape_watch_model_page(info['url'], model, region)
                if model_data:
                    discovered_models[model] = model_data
            
            return discovered_models
            
        except Exception as e:
            print(f"❌ Error discovering watch models for {region}: {e}")
            return {}

    def scrape_apple_watch(self, region):
        """Scrape Apple Watch models for a specific region using discovery approach."""
        print(f"🍎 Scraping Apple Watch for region: {region}")
        
        # Use the new discovery-based approach
        discovered_models = self.discover_watch_models(region)
        
        return discovered_models
    
    def scrape_watch_model_page(self, url, model_name, region):
        """Scrape a specific watch model page for all SKUs and configurations."""
        try:
            print(f"  Fetching {url}...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Extract JSON data from the page - use the existing working method
            bootstrap_data = self.extract_product_bootstrap_json(url)
            if not bootstrap_data:
                print(f"  ❌ No JSON data found for {model_name}")
                return None
            
            # Process the model data using the working extraction logic
            model_data = {
                'model_name': model_name,
                'url': url,
                'region': region,
                'skus': {},
                'configurations': {},
                'discovered_options': {}
            }
            
            # Use the existing working SKU extraction logic
            if isinstance(bootstrap_data, dict):
                # Convert the extracted part numbers to the expected format
                for part_number, md in bootstrap_data.items():
                    if isinstance(md, dict):
                        # Preserve full metadata when available
                        sku_data = {
                            'partNumber': part_number,
                            'name': md.get('name', ''),
                            'colorKey': md.get('colorKey', ''),
                            'colorDisplay': md.get('colorDisplay', ''),
                            'capacity': md.get('capacity', ''),
                            'family': md.get('family', ''),
                            'familyName': md.get('familyName', ''),
                            'region': region
                        }
                        # Optional fields from enriched extractor
                        if 'urlSlug' in md: sku_data['urlSlug'] = md.get('urlSlug')
                        if 'price' in md: sku_data['price'] = md.get('price')
                        if 'metadata' in md and isinstance(md['metadata'], dict):
                            sku_data['metadata'] = md['metadata']
                        model_data['skus'][part_number] = sku_data
                
                print(f"  ✅ Found {len(model_data['skus'])} SKUs for {model_name}")
            
            return model_data
            
        except Exception as e:
            print(f"  ❌ Error scraping {model_name}: {e}")
            return None
    
    def extract_all_skus_from_selection_data(self, selection_data, model_name, region):
        """Extract all available SKUs from the product selection data."""
        skus = {}
        
        # Look for SKU data in various places
        if 'products' in selection_data:
            products = selection_data['products']
            for product_key, product_data in products.items():
                if isinstance(product_data, dict):
                    sku_info = self.extract_sku_info(product_data, product_key, model_name, region)
                    if sku_info:
                        skus[product_key] = sku_info
        
        # Also check watchProductSelectionDataNoJS for additional URL patterns
        if 'watchProductSelectionDataNoJS' in selection_data:
            samples = selection_data['watchProductSelectionDataNoJS']
            for sample in samples:
                if 'url' in sample and 'text' in sample:
                    # Extract SKU info from sample URLs
                    sku_from_url = self.extract_sku_from_sample_url(sample, model_name, region)
                    if sku_from_url:
                        sku_key = f"url_sample_{len(skus)}"
                        skus[sku_key] = sku_from_url
        
        return skus
    
    def extract_sku_info(self, product_data, product_key, model_name, region):
        """Extract SKU information from product data using page JSON."""
        sku_info = {
            'product_key': product_key,
            'model': model_name,
            'region': region
        }
        
        # Extract all available fields from page data
        field_mappings = {
            'partNumber': 'part_number',
            'price': 'price', 
            'name': 'name',
            'colorKey': 'color_key',
            'colorDisplay': 'color_display',
            'dimensionColor': 'color_key',
            'dimensionCapacity': 'capacity',
            'family': 'family',
            'familyName': 'family_name',
            'productLocatorFamily': 'product_family'
        }
        
        for page_field, sku_field in field_mappings.items():
            if page_field in product_data:
                sku_info[sku_field] = product_data[page_field]
        
        # Extract color display name using page data
        if 'color_display' not in sku_info:
            color_display = self.extract_color_from_page_data(product_data)
            if color_display:
                sku_info['color_display'] = color_display
        
        # Extract metadata if available
        if 'metadata' in product_data:
            sku_info['metadata'] = product_data['metadata']
        
        return sku_info
    
    def extract_sku_from_sample_url(self, sample, model_name, region):
        """Extract SKU information from a sample URL."""
        url = sample['url']
        text = sample['text']
        
        # Parse URL components
        if '/buy-watch/' in url:
            path_part = url.split('/buy-watch/')[-1]
            components = path_part.split('-')
            
            if len(components) >= 4:
                return {
                    'model': model_name,
                    'region': region,
                    'url': url,
                    'description': text,
                    'url_components': {
                        'size': components[0],
                        'connectivity': components[1],
                        'color': components[2],
                        'material': components[3]
                    }
                }
        
        return None

    def scrape_apple_store_pages(self, product_category='iphones'):
        """Scrape real part numbers from Apple store pages by region."""
        
        # Get regions and products from config
        regions = self.config.get('regions', [])
        category_config = self.config.get('product_categories', {}).get(product_category, {})
        products = [product['path'] for product in category_config.get('products', [])]
        
        if not regions:
            print("❌ No regions configured")
            return {}
        
        if not products:
            print(f"❌ No products configured for category '{product_category}'")
            return {}
        
        # Organize by region
        regional_data = {}
        
        for region in regions:
            regional_data[region['code']] = {}
            
            for product in products:
                url = f"{region['url_prefix']}{product}/"
                bootstrap_data = self.extract_product_bootstrap_json(url)
                if bootstrap_data:
                    regional_data[region['code']].update(bootstrap_data)
                    print(f"Found {len(bootstrap_data)} part numbers from {url}")
                    
                time.sleep(2)  # Be respectful to Apple's servers
        
        return regional_data

    def categorize_regional_data(self, regional_data, product_category='iphones'):
        """Categorize part numbers by product model per region."""
        regional_categorized = {}
        categorization_rules = self.config.get('categorization_rules', {})
        
        # Get all possible categories for this product category
        category_config = self.config.get('product_categories', {}).get(product_category, {})
        all_categories = set()
        for product in category_config.get('products', []):
            all_categories.update(product.get('categories', []))
        
        for region_code, part_numbers in regional_data.items():
            # Initialize all categories for this region
            categorized = {category: {} for category in all_categories}
            
            for part_number, metadata in part_numbers.items():
                # Handle both old string format and new metadata format
                if isinstance(metadata, dict):
                    description = metadata.get('name', '')
                    description_lower = description.lower()
                else:
                    description = metadata
                    description_lower = description.lower()
                    # Convert old format to new metadata format
                    metadata = {
                        "name": description,
                        "colorKey": "unknown",
                        "colorDisplay": "Unknown",
                        "capacity": "",
                        "family": "unknown",
                        "familyName": description.split()[0] if description else "Unknown"
                    }
                
                # Try to categorize based on rules from config
                # Use exact matching to prevent cross-contamination
                categorized_item = False
                
                # First, check for exact iPhone model matches to prevent cross-contamination
                if "iphone" in description_lower:
                    # Check for iPhone 17 models first (most specific)
                    if "iphone 17 pro max" in description_lower:
                        if "proMax17" in all_categories:
                            categorized["proMax17"][part_number] = metadata
                            categorized_item = True
                    elif "iphone 17 pro" in description_lower:
                        if "pro17" in all_categories:
                            categorized["pro17"][part_number] = metadata
                            categorized_item = True
                    elif "iphone 17" in description_lower and "pro" not in description_lower:
                        if "regular17" in all_categories:
                            categorized["regular17"][part_number] = metadata
                            categorized_item = True
                    # Check for iPhone 16 models
                    elif "iphone 16 plus" in description_lower:
                        if "iphone16plus" in all_categories:
                            categorized["iphone16plus"][part_number] = metadata
                            categorized_item = True
                    elif "iphone 16e" in description_lower:
                        if "iphone16e" in all_categories:
                            categorized["iphone16e"][part_number] = metadata
                            categorized_item = True
                    elif "iphone 16" in description_lower and "plus" not in description_lower and "16e" not in description_lower:
                        if "iphone16" in all_categories:
                            categorized["iphone16"][part_number] = metadata
                            categorized_item = True
                    # Check for iPhone Air
                    elif "air" in description_lower:
                        if "air" in all_categories:
                            categorized["air"][part_number] = metadata
                            categorized_item = True
                
                # Handle Apple Watch categorization based on family and URL
                if not categorized_item and "apple_watch" in metadata.get("family", ""):
                    # Check if it's Apple Watch Ultra (49mm titanium)
                    if ("ultra" in description_lower or 
                        metadata.get("family") == "apple_watch_ultra" or
                        (metadata.get("metadata", {}).get("caseSize") == "49mm" and 
                         metadata.get("metadata", {}).get("caseMaterial") == "titanium")):
                        if "watch_ultra" in all_categories:
                            categorized["watch_ultra"][part_number] = metadata
                            categorized_item = True
                    # Check if it's from Apple Watch SE page (40mm, 44mm aluminum)
                    elif (metadata.get("metadata", {}).get("sourcePage") == "apple-watch-se" or
                          metadata.get("metadata", {}).get("caseSize") in ["40mm", "44mm"]):
                        if "watch_se" in all_categories:
                            categorized["watch_se"][part_number] = metadata
                            categorized_item = True
                    # Default to watch_series for regular Apple Watch (42mm, 46mm)
                    else:
                        if "watch_series" in all_categories:
                            categorized["watch_series"][part_number] = metadata
                            categorized_item = True
                
                # If not an iPhone or Apple Watch, use general rules
                if not categorized_item:
                    sorted_rules = sorted(categorization_rules.items(), 
                                        key=lambda x: max(len(kw) for kw in x[1]) if x[1] else 0, 
                                        reverse=True)
                    
                    for category, keywords in sorted_rules:
                        if category in all_categories:
                            for keyword in keywords:
                                if keyword.lower() in description_lower:
                                    categorized[category][part_number] = metadata
                                    categorized_item = True
                                    break
                            if categorized_item:
                                break
                
                # If not categorized, try to put in a default category
                if not categorized_item and all_categories:
                    default_category = list(all_categories)[0]
                    categorized[default_category][part_number] = metadata
            
            regional_categorized[region_code] = categorized
        
        return regional_categorized

    def extract_components_from_description(self, description):
        """Extract product components from Apple's descriptive text."""
        # This method extracts actual product info from Apple's text instead of URL parsing
        components = []
        
        # Extract size (e.g., "42mm", "46mm")
        import re
        size_match = re.search(r'(\d+)mm', description)
        if size_match:
            components.append(f"{size_match.group(1)}mm")
        
        # Extract connectivity info
        if 'GPS + Cellular' in description or 'Cellular' in description:
            components.append('cellular')
        elif 'GPS' in description:
            components.append('gps')
        
        # Extract material and color from description
        # This should ideally come from structured data, not text parsing
        return components
    def generate_json_files(self, regional_categorized, product_category='iphones'):
        """Generate JSON files for different product models organized by region."""
        category_config = self.config.get('product_categories', {}).get(product_category, {})
        output_files = category_config.get('output_files', [])

        for output_file in output_files:
            filename = output_file['filename']
            categories = output_file['categories']

            # Collect data for this output file
            file_data = {}
            for region, region_categories in regional_categorized.items():
                region_data = {}

                for category in categories:
                    if category in region_categories and region_categories[category]:
                        # Sort by part number for consistent ordering
                        sorted_items = dict(sorted(region_categories[category].items()))
                        # Inject token-driven metadata for each SKU (sourcePage, partNumber, isRealPartNumber)
                        token = self._iphone_token_for_category(category)
                        if token:
                            for pn, meta in list(sorted_items.items()):
                                # Normalize meta to dict
                                if not isinstance(meta, dict):
                                    meta = {'name': str(meta)}
                                    sorted_items[pn] = meta
                                md = meta.get('metadata') or {}
                                md['sourcePage'] = token
                                md['partNumber'] = md.get('partNumber') or pn
                                md['isRealPartNumber'] = True
                                # Ensure urlSlug is present for consistency (may be empty if unknown)
                                if 'urlSlug' not in meta or meta.get('urlSlug') is None:
                                    meta['urlSlug'] = ''
                                meta['metadata'] = md
                        region_data[category] = sorted_items

                if region_data:
                    file_data[region] = region_data

            # If explicitly enabled in config, emit Apple Watch-like structure with discovered_models and country_mappings
            unified = category_config.get('unified_output', False)
            if unified:
                country_mappings = {}
                discovered_models = {}
                # Build token set and discovered_models per region
                for region, region_categories in file_data.items():
                    tokens_used = set()
                    models_for_region = {}
                    for cat, skus in region_categories.items():
                        tok = self._iphone_token_for_category(cat)
                        if not tok:
                            continue
                        tokens_used.add(tok)
                        # Build PDP path using same normalization as shop_paths
                        def _pdp_path_for_token(tok: str) -> str:
                            if tok.endswith("-pro-max"):
                                return f"shop/buy-iphone/{tok[:-4]}"  # drop '-max'
                            return f"shop/buy-iphone/{tok}"
                        pdp_path = _pdp_path_for_token(tok)
                        # Construct per-token model block
                        models_for_region[tok] = {
                            'model_name': tok,
                            'url': f"https://www.apple.com/{region}/{pdp_path}",
                            'region': region,
                            'skus': skus,
                            'configurations': {},
                            'discovered_options': {}
                        }
                    if models_for_region:
                        discovered_models[region] = models_for_region
                    # Build per-region shop_paths and token_display
                    def _pdp_path_for_token(tok: str) -> str:
                        # Apple hosts Pro Max on the Pro PDP; normalize accordingly
                        if tok.endswith("-pro-max"):
                            return f"shop/buy-iphone/{tok[:-4]}"  # drop '-max'
                        return f"shop/buy-iphone/{tok}"
                    shop_paths = {tok: _pdp_path_for_token(tok) for tok in sorted(tokens_used)}
                    token_display = {tok: self._iphone_display_for_token(tok) for tok in sorted(tokens_used)}
                    country_mappings[region] = {
                        'shop_paths': shop_paths,
                        'localization': {
                            'token_display': token_display
                        }
                    }
                # Final unified structure for iPhone models (parity with Apple Watch)
                file_data = {
                    'urlMappings': {},
                    'recognizedMaterials': [],
                    'discovered_models': discovered_models,
                    'country_mappings': country_mappings,
                    'metadata': {
                        'scraping_method': 'discovery_based',
                        'source': 'scraper'
                    }
                }

            if file_data:
                self.save_to_json(file_data, filename)
                # Log whether unified or legacy written
                if isinstance(file_data, dict) and 'discovered_models' in file_data:
                    # Unified
                    total_items = sum(len(node.get('skus', {})) for region_models in file_data['discovered_models'].values() for node in region_models.values())
                    print(f"Generated (unified) {filename} with {total_items} SKUs")
                else:
                    total_items = sum(len(items) for region_data in file_data.values() for items in region_data.values())
                    print(f"Generated (legacy) {filename} with {total_items} models")
                # Ensure metadata/urlSlug even if upstream steps skipped injection (supports both legacy and unified)
                if product_category == 'iphones':
                    try:
                        self._enforce_iphone_metadata(filename, categories)
                        print(f"🔧 Enforced metadata/urlSlug in {filename}")
                    except Exception as e:
                        print(f"⚠️ Could not enforce metadata/urlSlug in {filename}: {e}")
    
    def extract_localization_from_models(self, models):
        """Extract localization data from discovered models"""
        localization = {
            'sizes': {},
            'colors': {},
            'materials': {},
            'connectivity': {}
        }
        
        for model_key, model_data in models.items():
            if isinstance(model_data, dict):
                # Extract size mappings
                if 'size' in model_data:
                    size_key = model_data.get('sizeKey', model_data['size'])
                    localization['sizes'][size_key] = model_data['size']
                
                # Extract color mappings
                if 'color' in model_data:
                    color_key = model_data.get('colorKey', model_data['color'])
                    localization['colors'][color_key] = model_data['color']
                
                # Extract material mappings
                if 'material' in model_data:
                    material_key = model_data.get('materialKey', model_data['material'])
                    localization['materials'][material_key] = model_data['material']
                
                # Extract connectivity mappings
                if 'connectivity' in model_data:
                    conn_key = model_data.get('connectivityKey', model_data['connectivity'])
                    localization['connectivity'][conn_key] = model_data['connectivity']
        
        return localization
    
    def extract_url_components_from_models(self, models):
        """Extract URL components from discovered models"""
        url_components = {
            'size_mappings': {},
            'color_mappings': {},
            'material_mappings': {}
        }
        
        for model_key, model_data in models.items():
            if isinstance(model_data, dict):
                # Extract URL size mappings
                if 'size' in model_data and 'sizeKey' in model_data:
                    url_components['size_mappings'][model_data['sizeKey']] = model_data['size']
                
                # Extract URL color mappings  
                if 'color' in model_data and 'colorKey' in model_data:
                    url_components['color_mappings'][model_data['colorKey']] = model_data['color']
                
                # Extract URL material mappings
                if 'material' in model_data and 'materialKey' in model_data:
                    url_components['material_mappings'][model_data['materialKey']] = model_data['material']
        
        return url_components

    def save_to_json(self, data, filename):
        """Save data to JSON file with proper formatting"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(data) if isinstance(data, dict) else 'data'} items to {filename}")
        except Exception as e:
            print(f"❌ Error saving to {filename}: {e}")

    def _enforce_iphone_metadata(self, filename, categories):
        """Ensure each SKU dict has metadata.sourcePage/partNumber/isRealPartNumber and urlSlug key."""
        import json
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        changed = False
        injected = 0
        # Unified structure?
        if isinstance(data, dict) and 'discovered_models' in data:
            disc = data.get('discovered_models', {})
            for region, models in disc.items():
                if not isinstance(models, dict):
                    continue
                for token, node in models.items():
                    skus = node.get('skus', {}) if isinstance(node, dict) else {}
                    for pn, meta in list(skus.items()):
                        if not isinstance(meta, dict):
                            meta = {'name': str(meta)}
                            skus[pn] = meta
                        md = meta.get('metadata') or {}
                        if token:
                            if md.get('sourcePage') != token:
                                md['sourcePage'] = token
                                changed = True
                        if not md.get('partNumber'):
                            md['partNumber'] = pn
                            changed = True
                        if md.get('isRealPartNumber') is not True:
                            md['isRealPartNumber'] = True
                            changed = True
                        if 'urlSlug' not in meta or meta.get('urlSlug') is None:
                            meta['urlSlug'] = ''
                            changed = True
                        if changed:
                            injected += 1
                        meta['metadata'] = md
        else:
            # Legacy structure: { region: { category: { sku: {..} } } }
            for region, region_categories in data.items():
                if not isinstance(region_categories, dict):
                    continue
                for category, skus in region_categories.items():
                    if category not in categories or not isinstance(skus, dict):
                        continue
                    token = self._iphone_token_for_category(category)
                    for pn, meta in list(skus.items()):
                        # Normalize to dict if needed
                        if not isinstance(meta, dict):
                            meta = {'name': str(meta)}
                            skus[pn] = meta
                        md = meta.get('metadata') or {}
                        # Inject metadata fields
                        if token:
                            if md.get('sourcePage') != token:
                                md['sourcePage'] = token
                                changed = True
                        if not md.get('partNumber'):
                            md['partNumber'] = pn
                            changed = True
                        if md.get('isRealPartNumber') is not True:
                            md['isRealPartNumber'] = True
                            changed = True
                        if 'urlSlug' not in meta or meta.get('urlSlug') is None:
                            meta['urlSlug'] = ''
                            changed = True
                        if changed:
                            injected += 1
                        meta['metadata'] = md
        if changed:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"📦 Injected/normalized metadata for ~{injected} SKUs in {os.path.basename(filename)}")
    
    def extract_url_format_for_product(self, selection_data, case_size, case_material, connectivity, color_key):
        """Extract URL format for a specific product configuration."""
        if 'watchProductSelectionDataNoJS' not in selection_data:
            return {}
            
        for sample in selection_data['watchProductSelectionDataNoJS']:
            if 'url' in sample:
                url = sample['url']
                if '/buy-watch/apple-watch/' in url:
                    path_part = url.split('/buy-watch/apple-watch/')[-1]
                    components = path_part.split('-')
                    
                    if len(components) >= 4:
                        url_size = components[0]
                        url_connectivity = components[1]
                        url_color = components[2]
                        url_material = components[3]
                        
                        # Check if this URL matches our product configuration
                        size_match = case_size and url_size == case_size
                        connectivity_match = (
                            (connectivity == 'gpscell' and url_connectivity == 'cellular') or
                            (connectivity == 'gps' and url_connectivity == 'gps')
                        )
                        material_match = (
                            (case_material == 'aluminum' and url_material == 'aluminium') or
                            (case_material == 'titanium' and url_material == 'titan') or
                            (case_material and url_material == case_material)
                        )
                        
                        if size_match and connectivity_match and material_match:
                            return {
                                'size': url_size,
                                'connectivity': url_connectivity,
                                'color': url_color,
                                'material': url_material
                            }
        
        return {}

    def discover_product_options_from_page(self, region, category_data):
        """Dynamically discover all product options from Apple's page data."""
        discovered_options = {
            "sizes": {},
            "connectivity": {},
            "materials": {},
            "colors": {},
            "url_patterns": []
        }
        
        print(f"🔍 Discovering product options for region: {region}")
        
        # Extract from productSelectionData if available
        if 'productSelectionData' in category_data:
            selection_data = category_data['productSelectionData']
            
            # Discover sizes from displayValues
            if 'displayValues' in selection_data:
                display_values = selection_data['displayValues']
                
                # Extract case sizes
                if 'watch_cases-dimensionCaseSize' in display_values:
                    size_data = display_values['watch_cases-dimensionCaseSize']
                    for size_key, size_info in size_data.items():
                        if size_key != 'variantOrder' and isinstance(size_info, dict):
                            display_name = size_info.get('header', size_key)
                            # Clean up display name (remove HTML)
                            display_name = display_name.replace('&nbsp;', ' ').replace('<div>', ' ').replace('</div>', '')
                            discovered_options["sizes"][size_key] = {
                                "url_component": size_key,
                                "display_name": display_name.strip()
                            }
                            print(f"  📏 Size: {size_key} -> {display_name.strip()}")
                
                # Extract materials
                if 'watch_cases-dimensionCaseMaterial' in display_values:
                    material_data = display_values['watch_cases-dimensionCaseMaterial']
                    for material_key, material_info in material_data.items():
                        if material_key != 'variantOrder' and isinstance(material_info, dict):
                            display_name = material_info.get('header', material_key)
                            # Clean up display name (remove HTML tags)
                            import re
                            display_name = re.sub(r'<[^>]+>', ' ', display_name).strip()
                            discovered_options["materials"][material_key] = {
                                "url_component": material_key,
                                "display_name": display_name
                            }
                            print(f"  🔧 Material: {material_key} -> {display_name}")
            
            # Discover connectivity and colors from sample URLs
            if 'watchProductSelectionDataNoJS' in selection_data:
                samples = selection_data['watchProductSelectionDataNoJS']
                print(f"  📱 Analyzing {len(samples)} sample URLs...")
                
                for sample in samples:
                    if 'url' in sample and 'text' in sample:
                        url = sample['url']
                        text = sample['text']
                        
                        # Extract URL pattern
                        if '/buy-watch/apple-watch/' in url:
                            path_part = url.split('/buy-watch/apple-watch/')[-1]
                            components = path_part.split('-')
                            
                            if len(components) >= 4:
                                size = components[0]
                                connectivity = components[1]
                                color = components[2]
                                material = components[3]
                                
                                # Store URL pattern
                                discovered_options["url_patterns"].append({
                                    "url": url,
                                    "text": text,
                                    "components": {
                                        "size": size,
                                        "connectivity": connectivity,
                                        "color": color,
                                        "material": material
                                    }
                                })
                                
                                # Discover connectivity options
                                if connectivity not in discovered_options["connectivity"]:
                                    # Extract connectivity from text
                                    if "GPS + Cellular" in text:
                                        discovered_options["connectivity"][connectivity] = {
                                            "url_component": connectivity,
                                            "display_name": "GPS + Cellular"
                                        }
                                    elif "GPS" in text and "Cellular" not in text:
                                        discovered_options["connectivity"][connectivity] = {
                                            "url_component": connectivity,
                                            "display_name": "GPS"
                                        }
                                    print(f"  📡 Connectivity: {connectivity} -> {discovered_options['connectivity'].get(connectivity, {}).get('display_name', 'Unknown')}")
                                
                                # Discover color options
                                if color not in discovered_options["colors"]:
                                    # Extract color from text description
                                    # Extract color from page data instead of text parsing
                                    color_display = self.extract_color_from_page_data({'dimensionColor': color}) or color
                                    discovered_options["colors"][color] = {
                                        "url_component": color,
                                        "display_name": color_display
                                    }
                                    print(f"  🎨 Color: {color} -> {color_display}")
        
        return discovered_options
    
    def extract_color_from_page_data(self, product_data):
        """Extract color information directly from page product data."""
        # Use the color data directly from the page JSON
        if 'colorDisplay' in product_data:
            return product_data['colorDisplay']
        elif 'dimensionColor' in product_data:
            return product_data['dimensionColor']
        elif 'color' in product_data:
            return product_data['color']
        
        # If no direct color field, try to extract from name
        if 'name' in product_data:
            return self.extract_color_from_name_fallback(product_data['name'])
        
        return None
    
    def extract_color_from_name_fallback(self, name):
        """Fallback color extraction from product name - only when page data unavailable."""
        # This should rarely be needed if page data is complete
        name_parts = name.split()
        if len(name_parts) > 2:
            return name_parts[-1]  # Last word is often the color
        return None

    def extract_url_mappings_from_scraped_data(self, regional_data):
        """Extract URL mappings from actual scraped Apple data."""
        url_mappings = {
            "connectivity": {},
            "materials": {},
            "colors": {}
        }
        
        print("🔍 Extracting URL mappings from scraped data...")
        
        # Load existing watch_product_selection.json for sample URLs
        selection_file = os.path.join(self.output_dir, 'watch_product_selection.json')
        if os.path.exists(selection_file):
            try:
                with open(selection_file, 'r', encoding='utf-8') as f:
                    selection_data = json.load(f)
                
                if 'productSelectionData' in selection_data and 'watchProductSelectionDataNoJS' in selection_data['productSelectionData']:
                    samples = selection_data['productSelectionData']['watchProductSelectionDataNoJS']
                    print(f"  Found {len(samples)} sample URLs in watch_product_selection.json")
                    
                    for sample in samples:
                        if 'url' in sample:
                            url = sample['url']
                            text = sample.get('text', '')
                            
                            # Extract URL components
                            if '/buy-watch/apple-watch/' in url:
                                path_part = url.split('/buy-watch/apple-watch/')[-1]
                                components = path_part.split('-')
                                
                                if len(components) >= 4:
                                    size = components[0]
                                    connectivity = components[1]
                                    color = components[2]
                                    material = components[3]
                                    
                                    print(f"    URL: {size}-{connectivity}-{color}-{material}")
                                    
                                    # Map connectivity
                                    if connectivity == "cellular":
                                        url_mappings["connectivity"]["gpscell"] = "cellular"
                                        url_mappings["connectivity"]["cellular"] = "cellular"
                                    elif connectivity == "gps":
                                        url_mappings["connectivity"]["gps"] = "gps"
                                    
                                    # Extract material mappings from text descriptions
                                    if "Aluminiumgehäuse" in text:
                                        if material == "aluminium":
                                            url_mappings["materials"]["aluminum"] = "aluminium"
                                        print(f"      Material: aluminum -> {material}")
                                    elif "Titangehäuse" in text:
                                        if material == "titan":
                                            url_mappings["materials"]["titanium"] = "titan"
                                        print(f"      Material: titanium -> {material}")
                                    
                                    # Store color mappings
                                    if "ros%C3%A9gold" in color and "Roségold" in text:
                                        url_mappings["colors"]["rosegold"] = color
                                        url_mappings["colors"]["rose_gold"] = color
                                        print(f"      Color: rosegold -> {color}")
                                    elif "space" in color.lower() and "Space Grau" in text:
                                        url_mappings["colors"]["spacegray"] = color
                                        url_mappings["colors"]["space_gray"] = color
                                        print(f"      Color: spacegray -> {color}")
                                    else:
                                        # Direct mapping for other colors
                                        url_mappings["colors"][color] = color
                                        print(f"      Color: {color} -> {color}")
            except Exception as e:
                print(f"  ❌ Error reading watch_product_selection.json: {e}")
        else:
            print("  ⚠️ watch_product_selection.json not found")
        
        print(f"✅ Extracted mappings:")
        print(f"  Connectivity: {url_mappings['connectivity']}")
        print(f"  Materials: {url_mappings['materials']}")
        print(f"  Colors: {len(url_mappings['colors'])} colors")
        
        return url_mappings

    def extract_product_paths_from_data(self, regional_data):
        """Extract product paths from scraped data."""
        product_paths = {}
        
        for region, data in regional_data.items():
            for category, category_data in data.items():
                # Extract base path from sample URLs
                if 'watchProductSelectionDataNoJS' in category_data:
                    for sample in category_data['watchProductSelectionDataNoJS']:
                        if 'url' in sample:
                            url = sample['url']
                            
                            # Extract the product path
                            if '/shop/' in url:
                                shop_part = url.split('/shop/')[-1]
                                base_path = shop_part.split('/')[0]  # e.g., "buy-watch"
                                
                                if 'apple-watch-ultra' in shop_part:
                                    product_paths["AppleWatchUltra"] = f"{base_path}/apple-watch-ultra"
                                elif 'apple-watch-se' in shop_part:
                                    product_paths["AppleWatchSE"] = f"{base_path}/apple-watch-se"
                                elif 'apple-watch' in shop_part:
                                    product_paths["AppleWatchSeries"] = f"{base_path}/apple-watch"
                                
                                # For other products, we can add similar logic
                                if 'buy-iphone' in shop_part:
                                    product_paths["iPhone"] = "buy-iphone"
                                elif 'buy-ipad' in shop_part:
                                    product_paths["iPad"] = "buy-ipad"
                                elif 'buy-mac' in shop_part:
                                    product_paths["Mac"] = "buy-mac"
        
        return product_paths

    def generate_product_configuration(self, regional_data, output_dir="InventoryWatch"):
        """Generate minimal product configuration - URL mappings go in product-specific files."""
        from datetime import datetime
        
        # Extract product paths only - URL mappings go in specific product files
        product_paths = self.extract_product_paths_from_data(regional_data)
        
        # Only include general configuration
        config = {
            "metadata": {
                "lastUpdated": datetime.now().isoformat(),
                "source": "scraper",
                "version": "1.0",
                "extractedFromPages": True
            }
        }
        
        # Only add product paths if we have them
        if product_paths:
            config["productPaths"] = product_paths
        
        # Save Apple Watch data with complete discovered models and SKUs
        print(f"🔍 Debug: product_paths = {product_paths}")
        print(f"🔍 Debug: regional_data keys = {list(regional_data.keys()) if regional_data else 'None'}")
        
        # Check if we have Apple Watch data (either from product_paths or regional_data)
        has_apple_watch_data = (
            any('apple_watch' in str(path).lower() for path in product_paths.values()) or
            any('apple-watch' in str(regional_data.get(region, {})).lower() for region in regional_data.keys() if regional_data)
        )
        
        if has_apple_watch_data or regional_data:  # Always save if we have regional_data for apple_watch category
            # Use the new discovery-based data structure with country-specific mappings
            # Extract country-specific mappings from scraped data
            country_mappings = {}
            # Aggregate urlMappings across countries
            colors_map = {}
            materials_map = {
                'aluminium': 'aluminum',
                'aluminum': 'aluminum',
                'titanium': 'titanium',
                'titangehäuse': 'titanium'
            }
            connectivity_map = {
                'gps + cellular': 'gpscell',
                'gps': 'gps'
            }
            # Build shop_paths map from scraper_config product categories (no hardcoding)
            watch_products = self.config.get('product_categories', {}).get('apple_watch', {}).get('products', [])
            config_shop_paths = {}
            for prod in watch_products:
                path = prod.get('path')
                for cat in prod.get('categories', []) or []:
                    # Use config keys directly e.g., watch_series, watch_ultra, watch_se
                    config_shop_paths[cat] = path

            # Helper: reverse parse urlSlug with template to capture localized tokens
            def parse_slug_with_template(slug, template):
                # Build a simple regex from template placeholders
                import re as _re
                # Escape hyphens and build capture groups
                pattern = _re.escape(template)
                # Replace placeholders with generic token patterns
                pattern = pattern.replace(_re.escape('{size}'), r'(?P<size>[^/]+)')
                pattern = pattern.replace(_re.escape('{caseSize}'), r'(?P<caseSize>[^/]+)')
                pattern = pattern.replace(_re.escape('{connectivity}'), r'(?P<connectivity>[^/]+)')
                pattern = pattern.replace(_re.escape('{color}'), r'(?P<color>[^/]+)')
                pattern = pattern.replace(_re.escape('{material}'), r'(?P<material>[^/]+)')
                # Hyphens are literal; match entire slug
                m = _re.match('^' + pattern + '$', slug)
                return m.groupdict() if m else {}

            # Build per-country url_components from SKU urlSlugs
            for region, models in regional_data.items():
                if models:
                    # Extract URL patterns and localization from the scraped data
                    country_mappings[region] = {
                        'shop_paths': config_shop_paths,
                        'localization': self.extract_localization_from_models(models),
                        'url_components': { 'colors': {}, 'materials': {}, 'connectivity': {}, 'sizes': {} }
                    }
                    # Build color normalization from SKUs: localized display -> canonical key
                    for model_key, model_data in models.items():
                        skus = model_data.get('skus', {}) if isinstance(model_data, dict) else {}
                        for _, meta in skus.items():
                            if isinstance(meta, dict):
                                ckey = meta.get('colorKey')
                                cdisp = meta.get('colorDisplay')
                                if ckey and cdisp:
                                    colors_map[cdisp.lower()] = ckey.lower()
                                # Reverse-derive localized slug tokens using template
                                url_slug = meta.get('urlSlug')
                                # Pick template based on model key
                                if 'ultra' in model_key:
                                    tmpl_key = 'watch_ultra'
                                elif 'se' in model_key:
                                    tmpl_key = 'watch_se'
                                else:
                                    tmpl_key = 'watch_series'
                                tmpl = self.config.get('product_categories', {}).get('apple_watch', {}).get('url_format', {}).get(tmpl_key)
                                if url_slug and tmpl:
                                    tokens = parse_slug_with_template(url_slug, tmpl)
                                    # Canonical references from metadata
                                    case_size = (meta.get('metadata') or {}).get('caseSize') or ''
                                    material_canon = (meta.get('metadata') or {}).get('caseMaterial') or ''
                                    conn_disp = (meta.get('metadata') or {}).get('connectivity') or ''
                                    # Map display to canonical connectivity
                                    conn_canon = 'gpscell' if 'cellular' in conn_disp.lower() else 'gps'
                                    color_canon = meta.get('colorKey') or ''
                                    # Update maps if tokens exist
                                    if tokens.get('color') and color_canon:
                                        country_mappings[region]['url_components']['colors'][color_canon] = tokens['color']
                                    if tokens.get('material') and material_canon:
                                        country_mappings[region]['url_components']['materials'][material_canon] = tokens['material']
                                    if tokens.get('connectivity') and conn_canon:
                                        country_mappings[region]['url_components']['connectivity'][conn_canon] = tokens['connectivity']
                                    if (tokens.get('size') or tokens.get('caseSize')) and case_size:
                                        size_token = tokens.get('size') or tokens.get('caseSize')
                                        country_mappings[region]['url_components']['sizes'][case_size] = size_token
            # Root-level urlMappings for normalization in app
            url_mappings = {
                'connectivity': connectivity_map,
                'materials': materials_map,
                'colors': colors_map
            }
            recognized_materials = sorted(list(set(materials_map.values())))

            apple_watch_complete = {
                'urlMappings': url_mappings,
                'recognizedMaterials': recognized_materials,
                'discovered_models': regional_data,
                'country_mappings': country_mappings,
                'metadata': {
                    'scraping_method': 'discovery_based',
                    'timestamp': config.get('metadata', {}).get('lastUpdated'),
                    'source': 'dynamic_discovery'
                }
            }
            
            apple_watch_filename = os.path.join(output_dir, 'AppleWatchModels-intl.json')
            self.save_to_json(apple_watch_complete, apple_watch_filename)
            print(f"✅ Saved discovery-based Apple Watch data to {apple_watch_filename}")
        else:
            print("❌ No Apple Watch data found to save")
        
        print(f"✅ Generated minimal product configuration in {output_dir}/")
        return config
    
    def print_summary(self, regional_categorized, product_category='iphones'):
        """Print summary of extracted models by region."""
        print(f"\nSummary of extracted {product_category} by region:")
        for region, categories in regional_categorized.items():
            print(f"  {region.upper()}:")
            for category, models in categories.items():
                if models:
                    print(f"    {category}: {len(models)} models")
                    for part_num, metadata in list(models.items())[:2]:  # Show first 2
                        if isinstance(metadata, dict):
                            desc = metadata.get('name', str(metadata))
                        else:
                            desc = metadata
                        print(f"      {part_num}: {desc}")
                    if len(models) > 2:
                        print(f"    ... and {len(models) - 2} more")
    
    def run(self, categories_to_scrape, output_dir="InventoryWatch"):
        """Main method to run the scraper for specified categories."""
        print("🍎 Starting Apple Product SKU scraping...")
        print("=" * 50)
        
        for category in categories_to_scrape:
            print(f"\n📱 Scraping {category.upper()}...")
            
            # For Apple Watch, use the new discovery-based approach
            if category == 'apple_watch':
                # Use discovery-based scraping for Apple Watch
                discovery_data = {}
                regions = self.config.get('regions', [])
                for region in regions:
                    region_code = region['code']
                    print(f"\n🌍 Scraping Apple Watch for region: {region_code}")
                    watch_models = self.scrape_apple_watch(region_code)
                    if watch_models:
                        discovery_data[region_code] = watch_models
                
                # Generate discovery-based JSON
                if discovery_data:
                    self.generate_product_configuration(discovery_data, output_dir)
                    self.print_summary(discovery_data, category)
                else:
                    print(f"No Apple Watch data discovered")
            else:
                # For other categories, use the legacy approach
                # Scrape Apple store pages for real part numbers
                regional_data = self.scrape_apple_store_pages(category)
                
                if not regional_data:
                    print(f"No data scraped for {category}")
                    continue
                
                regional_categorized = self.categorize_regional_data(regional_data, category)
                # IMPORTANT: pass product_category (e.g., 'iphones') so category_config/unified_output is applied
                self.generate_json_files(regional_categorized, category)
                self.print_summary(regional_categorized, category)
        
        print("\n🎉 All product categories completed!")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Apple Product SKU Scraper - Scrape Apple product SKUs from multiple regions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scrape_real_apple_skus.py                           # Scrape iPhones only (default)
  python3 scrape_real_apple_skus.py --categories all          # Scrape all product categories
  python3 scrape_real_apple_skus.py --categories iphones macs # Scrape iPhones and Macs
  python3 scrape_real_apple_skus.py --config custom.json      # Use custom config file
  python3 scrape_real_apple_skus.py --list-categories         # List available categories
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='scraper_config.json',
        help='Path to configuration file (default: scraper_config.json)'
    )
    
    parser.add_argument(
        '--categories',
        nargs='*',
        default=['iphones'],
        help='Product categories to scrape. Use "all" for all categories, or specify: iphones, macs, airpods, ipads, apple_watch (default: iphones)'
    )
    
    parser.add_argument(
        '--list-categories',
        action='store_true',
        help='List available product categories and exit'
    )
    
    parser.add_argument(
        '--regions',
        nargs='*',
        help='Specific regions to scrape (default: all regions from config). Use region codes like: us, uk, de, jp'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()


def main():
    """Main entry point with CLI argument parsing."""
    args = parse_args()
    
    # Initialize scraper with specified config file
    try:
        scraper = RealAppleSkuScraper(args.config)
    except Exception as e:
        print(f"❌ Error loading config file '{args.config}': {e}")
        return 1
    
    # List categories if requested
    if args.list_categories:
        categories = scraper.config.get('product_categories', {})
        print("📋 Available product categories:")
        for category, info in categories.items():
            print(f"  • {category}: {info.get('name', category)}")
            products = info.get('products', [])
            if products:
                print(f"    Products: {', '.join(p.get('name', p.get('path', '')) for p in products[:3])}{'...' if len(products) > 3 else ''}")
        return 0
    
    # Handle "all" categories
    available_categories = list(scraper.config.get('product_categories', {}).keys())
    if 'all' in args.categories:
        categories_to_scrape = available_categories
    else:
        # Validate categories
        invalid_categories = [cat for cat in args.categories if cat not in available_categories]
        if invalid_categories:
            print(f"❌ Invalid categories: {', '.join(invalid_categories)}")
            print(f"Available categories: {', '.join(available_categories)}")
            return 1
        categories_to_scrape = args.categories
    
    # Filter regions if specified
    if args.regions:
        original_regions = scraper.config.get('regions', [])
        filtered_regions = [r for r in original_regions if r['code'] in args.regions]
        if not filtered_regions:
            print(f"❌ No valid regions found. Available: {', '.join(r['code'] for r in original_regions)}")
            return 1
        scraper.config['regions'] = filtered_regions
        print(f"🌍 Filtering to regions: {', '.join(args.regions)}")
    
    print(f"🚀 Starting scraper with config: {args.config}")
    print(f"📱 Categories: {', '.join(categories_to_scrape)}")
    
    # Run the scraper
    try:
        scraper.run(categories_to_scrape, "InventoryWatch")
        return 0
    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
