# InventoryWatch

macOS app to monitor Apple Store pickup availability for iPhone, Apple Watch, Mac, iPad, AirPods, HomePod, and Apple Vision Pro.

## Features

- Real-time inventory checking across Apple Store locations
- Per-country store selection (35+ countries, including multi-language stores in Belgium and Switzerland)
- Per-model token selection for all Apple product families (iPhone, iPad, Mac, Apple Watch, AirPods, HomePod, Apple Vision Pro)
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
│   ├── countries.json               # 35 countries with shortcodes, locales, multi-language variants
│   ├── Stores_GlobalBootstrap.json   # Store locations (536 stores, 26 countries)
│   └── *-intl.json                  # Per-model catalog files (35+ files covering all 7 product families)
├── Assets.xcassets/                 # App icon
└── InventoryWatchTests/             # Unit tests (catalog parsing, country data, SKU resolution)
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

Or use the convenience script to scrape all families at once:
```bash
bash scrape_all.sh
```

Configuration is in `scraper_config.json` (regions, categories, model variants, families). See [Scraper Config Reference](#scraper-config-reference) below.

### Scrape store data

```bash
python3 scrape_apple_stores.py
```

Outputs `Stores_GlobalBootstrap.json` to `InventoryWatch/`

## Configuration

All configuration is JSON-driven:

| Config | File | Purpose |
|---------|------|---------|
| Countries | `InventoryWatch/Catalogs/countries.json` | Country names, shortcodes, locales, SKU codes, multi-language variants (BE, CH) |
| Stores | `InventoryWatch/Catalogs/Stores_GlobalBootstrap.json` | Store locations (536 stores, 26 countries) |
| Products | `InventoryWatch/Catalogs/*-intl.json` | SKUs, names, colors, capacities per country |
| Scraper | `scraper_config.json` | Regions, categories, entrypoints, families with per-product-type behavior flags, and model variant patterns (Pro/Max/Air/etc.) used to derive display names from product codes |

## Testing

```bash
# Run tests from Xcode (Cmd+U)
# Or from command line:
xcodebuild test -project InventoryWatch.xcodeproj -scheme InventoryWatch
```

Tests cover catalog JSON parsing, country data loading, product family resolution, and SKU validation.

## Intentional Hardcodes

A few values are intentionally hardcoded because they represent Apple's API contract or operational defaults:

- Apple pickup API query params (`fae=true`, `little=false`, etc.) — API protocol, not configuration
- HTTP timeout (30s) and connection limit (HTTP/1.1) — required for Akamai anti-bot compatibility
- User-Agent and Accept headers — must match browser behavior to pass bot detection
- Notification cleanup window (7 days) — reasonable default
- Update interval default (5 minutes) — avoids excessive API calls

## Scraper Config Reference

`scraper_config.json` drives the Python scraper (`scrape_models.py`). It has five top-level sections:

### `http_headers`

HTTP headers sent with every request to pass Apple's bot detection. Change these only if the User-Agent or Accept headers become outdated and Apple starts blocking the scraper.

### `regions`

Array of country/region entries. Each entry defines an Apple Store regional domain.

| Field        | Description |
|--------------|-------------|
| `url_prefix` | Base URL of the regional Apple Store (e.g. `https://www.apple.com/de/`) |
| `suffix`     | Apple part number suffix for that region (e.g. `ZD/A` for Germany) |
| `name`       | Human-readable region name |
| `code`       | Short region code (matches URL path, e.g. `de`, `us`, `cn`) |

**To add a new region:** copy an existing entry, change `url_prefix` to the new country's Apple Store URL, set the correct part number suffix (look at a product page on that store and check the model number, e.g. `MXXXXLL/A`), and give it a unique `code`.

### `categories`

Maps product families to Apple.com entrypoint URLs. Each entry defines:

| Field           | Description |
|-----------------|-------------|
| `family`        | Internal family key (must match a key in `families`) |
| `entrypoints`   | URL paths to scrape under the regional domain (e.g. `shop/buy-iphone`) |
| `manual_tokens` | (Optional) Override token discovery. If set, only these URL path segments are scraped instead of auto-discovered tokens. Used for products like AirPods and HomePod where the buy page structure doesn't map cleanly to individual models. |

**To add a new product category:** add an entry with the family key, the Apple buy-page path(s) in `entrypoints`, and `manual_tokens` if the buy page has sub-pages for each model variant.

### `model_variants`

Maps product family keys to variant suffix patterns used to derive human-readable display names from product codes (e.g. `iphone17pro` → "iPhone 17 Pro"). Each variant pattern has:

| Field        | Description |
|--------------|-------------|
| `family_key` | Substring to match in the product family code (e.g. `promax`, `se`) |
| `suffix`     | Display label to append (e.g. `Pro Max`, `SE`) |
| `priority`   | Lower number = higher priority. Patterns are tried in priority order and the first match wins. |

**To add a new variant** (e.g. if Apple introduces an "iPhone Slim"): add a new entry under the relevant family with a unique `family_key` (a token to match in the product code) and `suffix` (the display label). Set `priority` to control which variant is preferred when multiple match.

If the product family code does not match any `family_key`, the fallback also checks the page title text for the `suffix` string. If neither matches, the base model name is returned without a suffix.

Families like `airpods`, `homepod`, and `avp` have no variant entries because their model names are self-describing (e.g. "AirPods Pro 3").

### `families`

Per-family behavioral flags that control scraping, extraction, and output. Each family entry has:

| Field                       | Description |
|-----------------------------|-------------|
| `display_name`              | Human-readable label used in logs and output filenames |
| `file_prefix`               | Prefix for the output JSON catalog file (e.g. `iPhone-intl.json`) |
| `part_number_prefix`        | (Optional) Single-letter prefix for part number extraction (e.g. `M` for Mac). Only needed when the page references part numbers like `MXXXXLL/A`. Set to `null` if not applicable. |
| `retry_full_price`          | If `true`, re-request the buy page with `purchaseOption=fullPrice` to surface higher-tier configs (e.g. Apple Watch Edition models) |
| `skip_screensize_extraction` | If `true`, skip extracting screen sizes from the page. Use for Mac where sizes aren't relevant. |
| `prune_keep_incomplete`     | If `true`, keep products with missing price data instead of dropping them. Use for families where part numbers alone are sufficient. |
| `prune_keep_regional_name`  | If `true`, keep region-specific variant names instead of normalizing to a single canonical name. Use for Mac where config names differ by region. |
| `post_filter_keep_minimal`  | If `true`, keep only the minimal set of required fields (`partNumber`, `modelDisplayName`, `sizes`). Reduces output size for families with large buy pages. |
| `bto_extraction`            | If `true`, extract build-to-order (BTO) part numbers from the page's metrics JSON. Only Mac needs this. |
| `handler`                   | (Optional) Python class name for family-specific extraction logic (e.g. `IPhoneHandler`, `MacHandler`). Set to `null` to use the generic handler. |

**To add a new product family:** add a new key to `families` with the behavioral flags above, add a matching `categories` entry with entrypoints, and (optionally) add `model_variants` if the family has variant suffixes. If the product needs custom extraction logic, create a handler class in `family_handlers.py` and reference it here.