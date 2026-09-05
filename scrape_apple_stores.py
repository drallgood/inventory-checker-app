#!/usr/bin/env python3
"""
Apple Store Location Scraper

Scrapes Apple Store locations from https://www.apple.com/retail/storelist/
and generates a comprehensive store database JSON file.
"""

import requests
import json
import re
from bs4 import BeautifulSoup
import time


class AppleStoreLocationScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def scrape_store_list(self):
        """Scrape the Apple retail store list page and extract store data."""
        url = "https://www.apple.com/retail/storelist/"
        
        try:
            print(f"Fetching {url}...")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the __NEXT_DATA__ script tag
            next_data_script = soup.find('script', {'id': '__NEXT_DATA__', 'type': 'application/json'})
            
            if not next_data_script:
                print("❌ Could not find __NEXT_DATA__ script tag")
                return None
            
            # Parse the JSON data
            try:
                next_data = json.loads(next_data_script.string)
                store_list = next_data.get('props', {}).get('pageProps', {}).get('storeList', [])
                
                if not store_list:
                    print("❌ No store list found in __NEXT_DATA__")
                    return None
                
                print(f"✅ Found store data for {len(store_list)} locales")
                return store_list
                
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse __NEXT_DATA__ JSON: {e}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ Failed to fetch store list: {e}")
            return None
    
    def process_store_data(self, store_list):
        """Process and organize the store data into a structured format."""
        processed_stores = {}
        total_stores = 0
        
        for locale_data in store_list:
            locale = locale_data.get('locale', 'unknown')
            called_locale = locale_data.get('calledLocale', locale)
            states = locale_data.get('states', [])
            
            # Extract country code from locale (e.g., 'en_US' -> 'US')
            country_code = locale.split('_')[-1] if '_' in locale else locale.upper()
            
            locale_stores = {}
            locale_store_count = 0
            
            for state in states:
                state_name = state.get('name', 'Unknown')
                stores = state.get('store', [])
                
                state_stores = []
                for store in stores:
                    store_info = {
                        'id': store.get('id', ''),
                        'name': store.get('name', ''),
                        'slug': store.get('slug', ''),
                        'telephone': store.get('telephone', ''),
                        'address': {
                            'address1': store.get('address', {}).get('address1', ''),
                            'address2': store.get('address', {}).get('address2', ''),
                            'city': store.get('address', {}).get('city', ''),
                            'postalCode': store.get('address', {}).get('postalCode', ''),
                            'stateName': store.get('address', {}).get('stateName', state_name),
                            'stateCode': store.get('address', {}).get('stateCode', '')
                        }
                    }
                    state_stores.append(store_info)
                    locale_store_count += 1
                    total_stores += 1
                
                if state_stores:
                    locale_stores[state_name] = state_stores
            
            if locale_stores:
                processed_stores[country_code] = {
                    'locale': locale,
                    'calledLocale': called_locale,
                    'storeCount': locale_store_count,
                    'states': locale_stores
                }
                
                print(f"  {country_code}: {locale_store_count} stores across {len(locale_stores)} states/regions")
        
        print(f"\n✅ Processed {total_stores} stores across {len(processed_stores)} countries/regions")
        return processed_stores
    
    def generate_store_json(self, processed_stores):
        """Generate the final store JSON file."""
        output_file = 'InventoryWatch/Stores_GlobalBootstrap.json'
        
        # Create the structure matching the Swift app's StoreBootstrap format
        store_list_data = []
        
        # Convert to the format expected by the Swift app
        for country_code, country_info in processed_stores.items():
            # Create states array for this country
            states = []
            
            for state_name, stores in country_info['states'].items():
                # Convert stores to the expected format
                state_stores = []
                for store in stores:
                    state_stores.append({
                        'id': store['id'],
                        'name': store['name'],
                        'telephone': store['telephone'],
                        'slug': store['slug'],
                        'address': {
                            'address1': store['address']['address1'],
                            'address2': store['address']['address2'],
                            'city': store['address']['city'],
                            'postalCode': store['address']['postalCode'],
                            'stateName': store['address']['stateName'],
                            'stateCode': store['address']['stateCode']
                        }
                    })
                
                states.append({
                    'name': state_name,
                    'store': state_stores
                })
            
            # Determine if this country has multiple states or should be treated as having states
            has_states = len(states) > 1
            
            country_entry = {
                'locale': country_info['locale'],
                'hasStates': has_states
            }
            
            if has_states:
                # Countries with multiple states use the 'state' array
                country_entry['state'] = states
            else:
                # Countries with only one state put stores directly in 'store' array
                country_entry['store'] = states[0]['store'] if states else []
            
            store_list_data.append(country_entry)
        
        # Create the final JSON structure
        store_data = {
            'storeListData': store_list_data
        }
        
        # Write the JSON file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(store_data, f, indent=2, ensure_ascii=False)
            
            total_countries = len(store_list_data)
            total_stores = 0
            for country in store_list_data:
                if country['hasStates']:
                    total_stores += sum(len(state['store']) for state in country['state'])
                else:
                    total_stores += len(country['store'])
            
            print(f"✅ Generated {output_file}")
            print(f"   - {total_countries} countries")
            print(f"   - {total_stores} total stores")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to write {output_file}: {e}")
            return False
    
    def run(self):
        """Main execution method."""
        print("🍎 Apple Store Location Scraper")
        print("=" * 50)
        
        # Scrape the store list page
        store_list = self.scrape_store_list()
        if not store_list:
            return False
        
        # Process the store data
        processed_stores = self.process_store_data(store_list)
        if not processed_stores:
            print("❌ No stores processed")
            return False
        
        # Generate the JSON file
        success = self.generate_store_json(processed_stores)
        
        if success:
            print("\n🎉 Store scraping completed successfully!")
        else:
            print("\n❌ Store scraping failed")
        
        return success


if __name__ == "__main__":
    scraper = AppleStoreLocationScraper()
    scraper.run()
