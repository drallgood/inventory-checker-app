# SKU Data Refactoring Documentation

## Overview
This document describes the major refactoring completed to externalize hardcoded SKU data into JSON files and add multi-language support for Belgian and Swiss stores.

## Changes Made

### 1. SKU Data Externalization

**Problem**: All SKU data was hardcoded in Swift functions within `SKUData.swift`, making it difficult to maintain and update product information.

**Solution**: Moved all hardcoded SKU data to external JSON files.

#### Files Created/Modified:
- **NEW**: `InventoryWatch/iPadModels-intl.json` - Contains all iPad SKU data
- **NEW**: `InventoryWatch/AccessoryModels-intl.json` - Contains accessory SKU data
- **UPDATED**: `InventoryWatch/MacModels-intl.json` - Added missing Mac models from hardcoded functions
- **UPDATED**: `InventoryWatch/Model/SKUDataLoader.swift` - Refactored to load from JSON files
- **UPDATED**: `InventoryWatch/SKUData.swift` - Removed 300+ lines of hardcoded functions

#### JSON Structure:
```json
{
  "country_code": {
    "product_category": {
      "SKU_CODE": "Product Description"
    }
  }
}
```

### 2. Multi-Language Store Support

**Problem**: Belgian and Swiss Apple Stores have multiple language variants that weren't properly supported.

**Solution**: Added dedicated entries for each language variant.

#### Regions Added:
- `be-nl` - Belgium (Dutch)
- `be-fr` - Belgium (French) 
- `ch-de` - Switzerland (German)
- `ch-fr` - Switzerland (French)

#### Files Updated:
- **scraper_config.json**: Already contained multi-language configurations
- **All JSON files**: Added entries for `be-nl`, `be-fr`, `ch-de`, `ch-fr`
- **Countries.swift**: Added Country structs for multi-language variants

### 3. Technical Implementation Details

#### SKU Code Mapping:
- **US**: `LL/A`
- **UK**: `B/A` 
- **Belgium/Switzerland**: `ZD/A`
- **Other regions**: Various suffixes as configured

#### JSON Loading Method:
```swift
private func loadModelsFromJSON(fileName: String, country: Country, category: String) throws -> SKUData {
    // Loads JSON file and extracts data for specific country/category
    let countryKey = country.shortcode.lowercased()
    guard let countryData = jsonData[countryKey],
          let categoryData = countryData[category] else {
        throw AppError.invalidLocalModelStore
    }
    return SKUData(orderedSKUs: categoryData.keys.sorted(), lookup: categoryData)
}
```

## Benefits

1. **Maintainability**: SKU data can be updated without code changes
2. **Scalability**: Easy to add new regions and products
3. **Consistency**: Uniform JSON structure across all product categories
4. **Multi-language Support**: Proper handling of Belgian and Swiss language variants
5. **Code Cleanliness**: Eliminated 300+ lines of hardcoded data

## Validation

- ✅ All JSON files are valid JSON format
- ✅ Swift project builds successfully
- ✅ Multi-language regions recognized by scraper
- ✅ Backward compatibility maintained

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
