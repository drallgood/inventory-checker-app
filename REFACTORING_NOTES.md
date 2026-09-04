# SKU Data Refactoring Documentation

## Overview
This document describes the hardcoded data cleanup: externalizing country data to JSON, removing dead code (`ProductConfiguration`, `SafariFulfillmentFetcher`), and making the notification cooldown configurable.

## Changes Made

### 1. Hardcoded Data Removal & Externalization

**Problem**: Country data was hardcoded in Swift, `ProductConfiguration` referenced non-existent JSON files, and notification cooldown was a magic number.

**Solution**: Externalized countries to JSON, removed dead code, made cooldown configurable.

### 2. Country Data Externalization

#### Files Created/Modified:
- **NEW**: `InventoryWatch/Catalogs/countries.json` - Externalized country data (35 countries) replacing hardcoded list
- **DELETED**: `InventoryWatch/Model/WebViewFulfillmentFetcher.swift` - Dead code with zero callers
- **DELETED**: `InventoryWatch/watch_product_selection.json` - Debug dump with zero references
- **UPDATED**: `InventoryWatch/Countries.swift` - Loads country data from `countries.json` with USData fallback
- **UPDATED**: `InventoryWatch/Model/SKUDataLoader.swift` - Removed `ProductConfiguration` class and dead structs; simplified watch token display fallback
- **UPDATED**: `InventoryWatch/Model/FulfillmentModel.swift` - Removed hardcoded default store per country; defaults to first store
- **UPDATED**: `InventoryWatch/Model/DefaultsVendor.swift` - Added `notificationCooldownHours` and `ProductFamily.displayName`
- **UPDATED**: `InventoryWatch/Model/NotificationManager.swift` - Notification cooldown uses configurable hours instead of hardcoded 86400
- **UPDATED**: `InventoryWatch/SettingsView.swift` - Product picker uses `ProductFamily.allCases` + `displayName`
#### JSON Structure (`countries.json`):
```json
{
  "countries": [
    { "name": "United States", "shortcode": "US", "locale": "en_US", "skuCode": "LL" },
    ...
  ]
}
```

### 3. Dead Code Removal
- `ProductConfiguration` class (~117 lines) removed — referenced non-existent JSON files (`product-config.json`, `AppleWatchModels-intl.json`).
- `ProductConfigData`, `URLMappings`, `ConfigMetadata`, `AWCountryShopPaths`, `AppleWatchConfig` structs removed.
- `SafariFulfillmentFetcher` (`WebViewFulfillmentFetcher.swift`) deleted — zero callers.
- `watch_product_selection.json` deleted — debug dump with zero Swift references.
- Hardcoded default store numbers per country removed from `FulfillmentModel.swift` — defaults to first store.

### 4. Notification Cooldown Configurable
- Added `notificationCooldownHours` to `DefaultsVendor` (defaults to 24, reads from `UserDefaults`).
- `NotificationManager.sendNotification()` replaces hardcoded `86400` with `Double(defaultsVendor.notificationCooldownHours * 3600)`.

### 5. ProductFamily Extensibility
- Added `displayName` computed property to `ProductFamily` enum.
- `SettingsView` product picker now uses `ProductFamily.allCases` + `displayName` — adding iPad later only requires a new enum case.

### 6. Phase 3: Deduplication & Unification
- **Catalog deduplication**: `JSONCatalogiPad.swift` and `JSONCatalogMac.swift` reduced from 94+96 lines to 1-line conformances via `CategoryCatalog` protocol with default implementations in `CatalogTypes.swift`.
- **Store unification**: `FulfillmentStore` now wraps `RetailStore` instead of duplicating fields (`storeName`, `storeNumber`, `city`, `state` become computed properties).
- **Locale fix**: Store list API now uses `preferredCountry.locale` instead of hardcoded `en_US`.
- **R032 removal**: Default store number removed; `generateQueryString()` guards against empty store number.
- **Notification improvements**: Cooldown print message is now dynamic; name stripping is family-aware.

## Known Intentional Hardcodes

| Value | Location | Rationale |
|-------|----------|-----------|
| `timeoutInterval = 30` | `FulfillmentModel.swift:63,129` | Reasonable network timeout for Apple API |
| `httpMaximumConnectionsPerHost = 1` | `FulfillmentModel.swift:35` | Forces HTTP/1.1 to match curl behavior for Akamai |
| Apple API query params (`fae=true`, `little=false`, `mts.*`, `fts=true`) | `FulfillmentModel.swift:240-258` | Apple's pickup API protocol — these are API contract, not configuration |
| User-Agent / Accept headers | `FulfillmentModel.swift:60-62, 126-128` | Required to pass Akamai anti-bot checks |
| Notification history cleanup (7 days) | `NotificationManager.swift:47` | Reasonable default; low priority to externalize |

## Benefits

1. **Maintainability**: Country data can be updated without code changes
2. **Cleanliness**: 200+ lines of dead code removed
3. **Configurability**: Notification cooldown is now user-configurable
4. **Extensibility**: Adding new product families (iPad, AirPods) requires minimal changes
5. **Code Cleanliness**: Eliminated hardcoded strings and magic numbers

## Validation

- ✅ All JSON files are valid JSON format
- ✅ Country picker shows all 35 entries
- ✅ Store selection defaults to first store per country
- ✅ Watch/iPhone/Mac token selection works
- ✅ Notifications respect configured cooldown

## Future Considerations

1. **JSON Validation**: Consider adding runtime validation for JSON file integrity
2. **Automated Updates**: Could integrate with scraper to auto-update JSON files
3. **Localization**: Product descriptions could be localized per language variant
4. **Testing**: Add unit tests for JSON loading functionality

## Migration Notes

- Original hardcoded functions have been completely removed
- All product types now use the new JSON-based loading system
- iPhone and Apple Watch models already used JSON files (no changes needed)
- Country codes are case-insensitive in JSON lookups
