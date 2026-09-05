# SKU Data Refactoring & 2025 Update Documentation

## Overview

This document describes the major refactoring and modernization of InventoryWatch: externalizing all hardcoded data to JSON, migrating from a hardcoded Swift scraper to a config-driven Python scraper, and expanding product family support to all Apple product lines.

## Changes by Phase

### Phase 1: Cleanup & Country Data Externalization

**Problem**: Country data was hardcoded in Swift, `ProductConfiguration` referenced non-existent JSON files, and notification cooldown was a magic number. Over 200 lines of dead code existed.

**Solution**: Externalized countries to JSON, removed dead code, made cooldown configurable.

#### Files Created/Modified:
- **NEW**: `InventoryWatch/Catalogs/countries.json` - Externalized country data (35 countries) replacing hardcoded list
- **DELETED**: `InventoryWatch/Model/WebViewFulfillmentFetcher.swift` - Dead code with zero callers
- **DELETED**: `InventoryWatch/watch_product_selection.json` - Debug dump with zero references
- **UPDATED**: `InventoryWatch/Countries.swift` - Loads country data from `countries.json` with USData fallback
- **UPDATED**: `InventoryWatch/Model/SKUDataLoader.swift` - Removed `ProductConfiguration` class and dead structs
- **UPDATED**: `InventoryWatch/Model/FulfillmentModel.swift` - Removed hardcoded default store per country
- **UPDATED**: `InventoryWatch/Model/DefaultsVendor.swift` - Added `notificationCooldownHours` and `ProductFamily.displayName`
- **UPDATED**: `InventoryWatch/Model/NotificationManager.swift` - Configurable cooldown replaces hardcoded 86400
- **UPDATED**: `InventoryWatch/SettingsView.swift` - Product picker uses `ProductFamily.allCases` + `displayName`

### Phase 2: Per-Family SKU Loading & iPad Support

**Problem**: `SKUDataLoader.swift` was monolithic, handling all families in one file. iPad was not supported. `ContentView.swift` contained duplicated family logic.

**Solution**: Split SKU loading per family with new per-family catalog enums, deduplicated ContentView, added iPad support with scraper `_meta` fields.

#### Key Changes:
- **NEW**: `InventoryWatch/Model/JSONCatalogiPad.swift` - iPad catalog enum
- **NEW**: `InventoryWatch/Model/JSONCatalogMac.swift` - Mac catalog enum (split out)
- **NEW**: `InventoryWatch/Catalogs/iPad-*-intl.json` - iPad catalog JSONs (Pro, Air, Mini, iPad, 10.2)
- **UPDATED**: `InventoryWatch/Model/SKUDataLoader.swift` - Split into per-family loading methods
- **UPDATED**: `InventoryWatch/ContentView.swift` - Deduplicated family display logic with reusable components
- **UPDATED**: `InventoryWatch/SettingsView.swift` - Per-family token selection (watch, phone, Mac, iPad)
- Python scraper enhanced with `_meta` fields (metadata, sourcePage, token_display) in JSON output

### Phase 3: Deduplication & Unification

**Problem**: Per-family catalog enums had ~95 lines of duplicated protocol implementations. `FulfillmentStore` duplicated fields from `RetailStore`.

**Solution**: Introduced `CategoryCatalog` protocol with default implementations, unified store types.

#### Key Changes:
- **NEW**: `InventoryWatch/Model/CatalogTypes.swift` - `CategoryCatalog` protocol with default implementations (`categoriesSourcePages`, `tokenDisplayName`, `categoryData`, `metadata`, `pdpBaseURL`), shared structs (`CatalogRoot`, `CatalogNode`, `ProductMetadata`, etc.)
- **SIMPLIFIED**: `JSONCatalogiPad.swift` and `JSONCatalogMac.swift` - Reduced from 94+96 lines to 1-line conformances
- **UPDATED**: `FulfillmentStore` - Now wraps `RetailStore` instead of duplicating fields (`storeName`, `storeNumber`, `city`, `state` become computed properties)
- **UPDATED**: Store list API - Uses `preferredCountry.locale` instead of hardcoded `en_US`
- **UPDATED**: Notification system - Cooldown print message dynamic; name stripping family-aware

### Phase 4: AirPods, HomePod, Apple Vision Pro Support

**Problem**: Only iPhone, Apple Watch, Mac, and iPad were supported.

**Solution**: Added full support for AirPods, HomePod, and Apple Vision Pro.

#### Key Changes:
- **NEW**: `InventoryWatch/Model/JSONCatalogAirPods.swift` - AirPods catalog enum
- **NEW**: `InventoryWatch/Model/JSONCatalogHomePod.swift` - HomePod catalog enum
- **NEW**: `InventoryWatch/Model/JSONCatalogAVP.swift` - Apple Vision Pro catalog enum
- **NEW**: `InventoryWatch/Catalogs/AirPods-*-intl.json` - AirPods 4, Max, Pro 2, Pro 3 catalogs
- **NEW**: `InventoryWatch/Catalogs/HomePod-*-intl.json` - HomePod, Mini catalogs
- **NEW**: `InventoryWatch/Catalogs/AppleVisionPro-*-intl.json` - AVP and Zeiss inserts catalogs
- **UPDATED**: `SKUDataLoader.swift`, `SettingsView.swift` - Per-family token loading for all 7 families

### Phase 5: Python Scraper Rewrite

**Problem**: The app relied on legacy aggregated JSONs and had no maintainable scraping infrastructure for keeping catalog data current.

**Solution**: Complete rewrite of the product data pipeline with a config-driven Python scraper.

#### New Files:
- **`scraper_config.json`** - Central configuration: regions (30+ countries with Apple Store URLs and part number suffixes), categories (entrypoints per family), model_variants (display name inference patterns), families (per-family behavioral flags)
- **`scrape_models.py`** - Main scraper script: scrapes Apple.com buy pages, extracts SKU data (part numbers, colors, capacities, prices, screen sizes), outputs per-model catalog JSONs to `InventoryWatch/Catalogs/`
- **`family_handlers.py`** - Per-family extraction handlers: `IPhoneHandler`, `MacHandler`, `iPadHandler`, `WatchHandler`, `AirPodsHandler`, `HomePodHandler`, `AVPHandler`, each encapsulating family-specific HTML parsing, variant name extraction, and enrichment logic
- **`scrape_apple_stores.py`** - Standalone store list scraper: fetches Apple's `rsp-web/store-list` API and outputs `Stores_GlobalBootstrap.json` (536+ stores across 26 countries)
- **`scrape_all.sh`** - Convenience script to run scrapes for all families
- **`requirements.txt`** - Python dependencies (`requests`)

#### Scraper Features:
- Configurable HTTP headers to pass Akamai anti-bot detection
- Region-aware part number generation (suffix varies by country: `LL/A`, `ZD/A`, `FN/A`, etc.)
- Apple Watch case size/material/connectivity enrichment via bootstrap-first regex fallback
- iPhone partNumber→dimensionScreensize inference with base-prefix size consistency
- Build-to-order (BTO) part number extraction for Macs
- `manual_tokens` support for families where buy pages don't map cleanly to models (AirPods, HomePod)
- Per-model JSON output with `_meta` fields (token_display, shop_paths, sourcePage)
- `--all-models` flag for bulk scraping, `--countries` filter for targeted updates

### Phase 6: Multi-Language Store Support

**Problem**: Belgian and Swiss Apple Stores have dual-language variants (Dutch/French, German/French) that weren't supported.

**Solution**: Added multi-language country entries and dynamic language variant handling.

#### Key Changes:
- **NEW**: `Countries.swift` - `Country` struct with multi-language variant support
- **UPDATED**: `countries.json` - Added Belgian (`be-nl`, `be-fr`) and Swiss (`ch-de`, `ch-fr`) entries
- **UPDATED**: `scraper_config.json` regions - Language variant codes for Belgium and Switzerland
- **UPDATED**: All catalog JSONs - Multi-language region data with proper SKU codes per variant

### Phase 7: Akamai Anti-Bot Hardening

**Problem**: Apple's Akamai CDN was blocking scraper requests with HTTP 541 (bot detected) and occasionally blocking pickup API calls.

**Solution**: Multiple layers of bot-detection mitigation.

#### Key Changes:
- **UPDATED**: `FulfillmentModel.swift` - Forces HTTP/1.1 (`httpMaximumConnectionsPerHost = 1`), proper browser User-Agent and Accept headers
- **UPDATED**: `scrape_models.py` - Configurable HTTP headers in `scraper_config.json`, connection reuse, 404 downgrade to info-level (model not offered in region), exponential backoff on 541
- **NEW**: `ModelError.swift` - `botDetected`, `rateLimited`, `accessDenied`, `productNotAvailableInRegion` error cases with user-friendly messages

### Phase 8: UI & Architecture Improvements

- **NEW**: `InventoryWatch/Views/ProductAvailabilityList.swift` - Reusable product list component used across all families
- **UPDATED**: `ContentView.swift` - 308-line rewrite with unified family display
- **UPDATED**: `SettingsView.swift` - 1040-line rewrite with per-family token persistence (saved per-country in UserDefaults)
- **UPDATED**: `DefaultsVendor.swift` - Extended `ProductFamily` enum to 7 families
- **UPDATED**: `ModelTypes/ProductType.swift` - Removed, replaced by JSON-driven catalog types
- **DELETED**: `SKUData.swift` - 331 lines of hardcoded SKU functions removed
- **DELETED**: `InventoryWatch/AppleWatchUltra-intl.json` - Legacy aggregated JSON replaced by per-model `Catalogs/` files
- **DELETED**: `InventoryWatch/iPhoneModels13-intl.json`, `iPhoneModels14-intl.json` - Legacy aggregate JSONs
- **NEW**: `InventoryWatchTests/` - Tests added: `CatalogParsingTests`, `CountryJSONTests`, `ProductFamilyTests`, `SKUResolutionTests`

## Architecture Overview

```
Data Flow:
  Apple.com buy pages
       ↓ (scrape_models.py + scraper_config.json + family_handlers.py)
  Catalog JSONs (InventoryWatch/Catalogs/*-intl.json)
       ↓ (SKUDataLoader + CategoryCatalog protocol)
  SwiftUI app (ContentView + SettingsView + ProductAvailabilityList)
       ↓ (FulfillmentModel + Apple pickup API)
  Real-time inventory display + notifications

Store Data:
  Apple rsp-web/store-list API
       ↓ (scrape_apple_stores.py)
  Stores_GlobalBootstrap.json
       ↓ (FulfillmentModel)
  Store selection + inventory queries
```

## Product Families Supported

| Family     | Catalog Enum          | Source Pages                       |
|------------|----------------------|------------------------------------|
| iPhone     | JSONCatalogiPhone    | iPhone 16, 17, 17e, 17 Pro, Air   |
| iPad       | JSONCatalogiPad      | Pro, Air, Mini, iPad, 10.2         |
| Mac        | JSONCatalogMac       | MacBook Air, Pro, Neo, iMac, Mini, Studio, Studio Display, XDR |
| Apple Watch| JSONCatalogAppleWatch| SE, Series, Ultra, Hermes, Hermes Ultra |
| AirPods    | JSONCatalogAirPods   | 4, Max, Pro 2, Pro 3               |
| HomePod    | JSONCatalogHomePod   | HomePod, Mini                      |
| AVP        | JSONCatalogAVP       | Apple Vision Pro, Zeiss Inserts    |

## Known Intentional Hardcodes

| Value | Location | Rationale |
|-------|----------|-----------|
| `timeoutInterval = 30` | `FulfillmentModel.swift:63,129` | Reasonable network timeout for Apple API |
| `httpMaximumConnectionsPerHost = 1` | `FulfillmentModel.swift:35` | Forces HTTP/1.1 to match curl behavior for Akamai |
| Apple API query params (`fae=true`, `little=false`, `mts.*`, `fts=true`) | `FulfillmentModel.swift:240-258` | Apple's pickup API protocol — these are API contract, not configuration |
| User-Agent / Accept headers | `FulfillmentModel.swift:60-62, 126-128` | Required to pass Akamai anti-bot checks |
| Notification history cleanup (7 days) | `NotificationManager.swift:47` | Reasonable default; low priority to externalize |
| HTTP headers in `scraper_config.json` | `scraper_config.json:2-9` | Must match browser behavior to avoid Akamai 541 blocks |

## Benefits

1. **Maintainability**: All product and country data externalized to JSON — no code changes needed for new products or regions
2. **Data freshness**: Python scraper can regenerate all catalog JSONs on demand from Apple's live buy pages
3. **Cleanliness**: 350+ lines of dead code removed, 331 lines of hardcoded SKUs eliminated
4. **Configurability**: Notification cooldown configurable, scraper behavior driven by `scraper_config.json`
5. **Extensibility**: Adding a new product family requires only a catalog enum, JSON file, and config entries
6. **Anti-bot resilience**: Proper HTTP/1.1, headers, and backoff handling for Apple's Akamai CDN
7. **Multi-language**: Full support for dual-language stores (BE, CH)
8. **Test coverage**: New test suite for catalog parsing, country data, product families, SKU resolution

## Validation

- ✅ All JSON files are valid JSON format
- ✅ Country picker shows all 35+ entries including multi-language variants
- ✅ Store selection defaults to first store per country
- ✅ Per-family token selection works for all 7 product families
- ✅ Per-country token persistence (selection saved per country)
- ✅ Notifications respect configured cooldown
- ✅ Python scraper regenerates catalog JSONs from live Apple.com pages
- ✅ Akamai 541 responses handled with backoff/retry
- ✅ Swift test suite passes (`InventoryWatchTests/`)

## Future Considerations

1. **Automated scraping**: Run scraper on a schedule to keep catalogs current with new Apple products
2. **CI/CD integration**: Add scraper to GitHub Actions for periodic catalog updates
3. **Localization**: Product descriptions could be localized per language variant using scraped translations
4. **Incremental scraping**: Only scrape models that have changed since last run
5. **Store data freshness**: Periodically re-scrape `Stores_GlobalBootstrap.json` for new/closed stores

## Migration Notes

- Original hardcoded SKU functions in `SKUData.swift` have been completely removed
- All product types now use the JSON-based loading system via `CategoryCatalog` protocol
- Legacy aggregate JSONs (`iPhoneModels13-intl.json`, `iPhoneModels14-intl.json`, `AppleWatchUltra-intl.json`) removed — replaced by per-model files in `InventoryWatch/Catalogs/`
- Country codes are case-insensitive in JSON lookups
- `ProductType.swift` enum removed — product types are now defined by catalog JSON structure
- `FulfillmentStore` now wraps `RetailStore` — existing store references remain compatible via computed properties
- Python scraper requires `scraper_config.json` and `family_handlers.py` in the same directory as `scrape_models.py`