#!/usr/bin/env python3
"""
Apple SKU Scraper

Scrapes real Apple part numbers from Apple store pages and generates
JSON files for the InventoryWatch app.
"""

import requests
import json
import re
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
            
            # First try to extract from metrics JSON (cleaner data)
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
                                part_numbers[part_number] = name
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
            
            print("No product data found")
            return None
                
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def extract_part_numbers_from_bootstrap(self, bootstrap_data):
        """Extract part numbers from various data sources."""
        part_numbers = {}
        
        try:
            # Handle metrics JSON data first (cleanest format)
            if 'metrics_products' in bootstrap_data:
                return bootstrap_data['metrics_products']
            
            # Handle the regex-extracted parts
            if 'extracted_parts' in bootstrap_data:
                return bootstrap_data['extracted_parts']
            
            # Use the structure from the working JS snippet
            if 'productSelectionData' in bootstrap_data and 'products' in bootstrap_data['productSelectionData']:
                for product in bootstrap_data['productSelectionData']['products']:
                    part_number = product.get('partNumber', '')
                    if part_number:
                        # Build description using the same fields as the JS snippet
                        family = product.get('productLocatorFamily', '')
                        capacity = product.get('dimensionCapacity', '')
                        color = product.get('dimensionColor', '')
                        
                        description = f"{family} {capacity} {color}".strip()
                        part_numbers[part_number] = description
            
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
                        
                        description = f"{name} {capacity} {color}".strip()
                        part_numbers[part_number] = description
                        
        except Exception as e:
            print(f"Error extracting part numbers: {e}")
        
        return part_numbers

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
            
            for part_number, description in part_numbers.items():
                description_lower = description.lower()
                
                # Try to categorize based on rules from config
                # Sort categories by keyword length (longest first) to match more specific patterns first
                categorized_item = False
                sorted_rules = sorted(categorization_rules.items(), 
                                    key=lambda x: max(len(kw) for kw in x[1]) if x[1] else 0, 
                                    reverse=True)
                
                for category, keywords in sorted_rules:
                    if category in all_categories:
                        for keyword in keywords:
                            if keyword.lower() in description_lower:
                                categorized[category][part_number] = description
                                categorized_item = True
                                break
                        if categorized_item:
                            break
                
                # If not categorized, try to put in a default category
                if not categorized_item and all_categories:
                    default_category = list(all_categories)[0]
                    categorized[default_category][part_number] = description
            
            regional_categorized[region_code] = categorized
        
        return regional_categorized

    def generate_regional_variants(self, us_models):
        """Generate regional variants based on part number patterns."""
        regional_mapping = {
            'ca': ('LL/A', 'VC/A'),   # Canada
            'uk': ('LL/A', 'B/A'),    # United Kingdom
            'hk': ('LL/A', 'ZA/A'),   # Hong Kong
            'au': ('LL/A', 'ZP/A'),   # Australia
            'kr': ('LL/A', 'KH/A'),   # Korea
            'de': ('ZD/A', 'ZD/A'),   # Germany (already correct)
            'fr': ('LL/A', 'ZD/A'),   # France
            'it': ('LL/A', 'QL/A'),   # Italy
            'jp': ('LL/A', 'J/A'),    # Japan
            'at': ('ZD/A', 'ZD/A'),   # Austria (already correct)
            'nl': ('LL/A', 'ZD/A'),   # Netherlands
            'th': ('LL/A', 'ZP/A')    # Thailand
        }
        
        all_models = {'us': us_models}
        
        for region, (from_suffix, to_suffix) in regional_mapping.items():
            all_models[region] = {}
            for category, models in us_models.items():
                all_models[region][category] = {}
                for part_number, description in models.items():
                    # Only include one SKU per product - prefer region-specific ones
                    if from_suffix in part_number:
                        new_part_number = part_number.replace(from_suffix, to_suffix)
                        all_models[region][category][new_part_number] = description
                    # For regions like Germany/Austria that already have correct suffixes, keep original
                    elif region in ['de', 'at'] and part_number.endswith('ZD/A'):
                        all_models[region][category][part_number] = description
        
        return all_models
    
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
                        region_data[category] = sorted_items
                
                if region_data:
                    file_data[region] = region_data
            
            if file_data:
                self._write_json_file(filename, file_data)
                total_items = sum(len(items) for region_data in file_data.values() for items in region_data.values())
                print(f"Generated {filename} with {total_items} models")
    
    def _write_json_file(self, filepath, json_data):
        """Helper method to write JSON files."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error writing {filepath}: {e}")
    
    def print_summary(self, regional_categorized, product_category='iphones'):
        """Print summary of extracted models by region."""
        print(f"\nSummary of extracted {product_category} by region:")
        for region, categories in regional_categorized.items():
            print(f"  {region.upper()}:")
            for category, models in categories.items():
                if models:
                    print(f"    {category}: {len(models)} models")
                    for part_num, desc in list(models.items())[:2]:  # Show first 2
                        print(f"      {part_num}: {desc}")
                    if len(models) > 2:
                        print(f"    ... and {len(models) - 2} more")
    
    def run(self, product_categories=None):
        """Main execution method."""
        if product_categories is None:
            product_categories = list(self.config.get('product_categories', {}).keys())
        
        print("🍎 Starting Apple Product SKU scraping...")
        print("=" * 50)
        
        for category in product_categories:
            print(f"\n📱 Scraping {category.upper()}...")
            
            # Scrape Apple store pages for real part numbers
            regional_data = self.scrape_apple_store_pages(category)
            
            if not regional_data:
                print(f"No data scraped for {category}")
                continue
            
            # Categorize the scraped data by region
            regional_categorized = self.categorize_regional_data(regional_data, category)
            
            # Generate JSON files
            self.generate_json_files(regional_categorized, category)
            
            # Print summary
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
        scraper.run(categories_to_scrape)
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
