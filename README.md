# InventoryWatch

macOS app to monitor Apple Store pickup availability for iPhone, Apple Watch, Mac, iPad, AirPods, HomePod, and Apple Vision Pro.

## Features

- Real-time inventory checking across Apple Store locations
- Per-country store selection (35+ countries)
- Per-model token selection (e.g., iPhone 17 Pro, Apple Watch Ultra, MacBook Pro)
- Configurable update intervals with notifications
- All product data is scraped from Apple's official buy pages — no hardcoded SKUs

## Architecture

- **SwiftUI** macOS app with MVVM + Actor model
- Product/SKU data loaded from JSON catalog files (`InventoryWatch/Catalogs/`)
- Python scraper (`scrape_models.py`) generates catalog JSONs from Apple's regional buy pages
- Store data from Apple's `rsp-web/store-list` API with local JSON fallback
- All configuration driven by JSON: product families, countries, SKU data, store locations

## Project Structure

```
InventoryWatch/
├── Model/
│   ├── SKUDataLoader.swift          # Actor that loads SKU data from catalog JSONs
│   ├── FulfillmentModel.swift       # Apple pickup API queries
│   ├── DefaultsVendor.swift         # User preferences (ProductFamily enum)
│   ├── ViewModel.swift              # SwiftUI ViewModel (MainActor)
│   ├── NotificationManager.swift    # macOS notifications
│   ├── NotificationSender.swift     # Notification logic
│   ├── CatalogTypes.swift           # Shared types (CategoryCatalog protocol)
│   ├── JSONCatalog*.swift           # Per-family catalog enums
│   └── ModelTypes/                  # Data structures
├── Views/
│   └── ProductAvailabilityList.swift # Reusable product list component
├── SettingsView.swift               # Preferences window
├── ContentView.swift                # Main inventory display
├── Countries.swift                  # Country data (loaded from countries.json)
├── Catalogs/
│   ├── countries.json               # 35 countries with shortcodes, locales
│   ├── Stores_GlobalBootstrap.json   # Store locations
│   └── *-intl.json                  # Per-product catalog files (25+)
└── Assets.xcassets/                 # App icon
```

## Setup

### Build the app

```bash
open InventoryWatch.xcodeproj
# Build (Cmd+B) then Run (Cmd+R) in Xcode
```

Requires Xcode 15+ and macOS 14+.

### Scrape product data

```bash
# Install Python dependencies
pip install requests

# Scrape all iPhone models across all regions
python3 scrape_models.py --family iphone --all-models

# Scrape a specific family
python3 scrape_models.py --family ipad --all-models

# Targeted scrape for specific countries
python3 scrape_models.py --family mac --all-models --countries US,UK,DE
```

Available families: `iphone`, `watch`, `mac`, `ipad`, `airpods`, `homepod`, `avp`

Configuration is in `scraper_config.json` (regions, categories, model variants).

### Scrape store data

```bash
python3 scrape_apple_stores.py
```

Outputs `Stores_GlobalBootstrap.json` to `InventoryWatch/`

## Configuration

All configuration is JSON-driven:

| Config | File | Purpose |
|---------|------|---------|
| Countries | `InventoryWatch/Catalogs/countries.json` | Country names, shortcodes, locales, SKU codes |
| Stores | `InventoryWatch/Catalogs/Stores_GlobalBootstrap.json` | Store locations (536 stores, 26 countries) |
| Products | `InventoryWatch/Catalogs/*-intl.json` | SKUs, names, colors, capacities per country |
| Scraper | `scraper_config.json` | Regions, categories, entrypoints for the Python scraper |

## Testing

```bash
# Run tests from Xcode (Cmd+U)
# Or from command line:
xcodebuild test -project InventoryWatch.xcodeproj -scheme InventoryWatch
```

## Intentional Hardcodes

A few values are intentionally hardcoded because they represent Apple's API contract or operational defaults:

- Apple pickup API query params (`fae=true`, `little=false`, etc.) — API protocol, not configuration
- HTTP timeout (30s) and connection limit (HTTP/1.1) — required for Akamai anti-bot compatibility
- User-Agent and Accept headers — must match browser behavior to pass bot detection
- Notification cleanup window (7 days) — reasonable default
- Update interval default (5 minutes) — avoids excessive API calls