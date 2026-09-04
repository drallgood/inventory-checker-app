//
//  ModelLoader.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

// MARK: - Product Metadata Structures

// Minimal catalog facade over Mac JSON emitted by scraper (per-model files)
enum JSONCatalogMac {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct CountryMap: Codable { let shop_paths: [String: String]?; let localization: AWLocalization? }
    struct MacRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: CountryMap]? }

    @MainActor private static func macModelJSONFiles() -> [URL] {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let filtered = candidates.filter { url in
            let name = url.deletingPathExtension().lastPathComponent
            let lc = name.lowercased()
            // Per-model files like Mac-<Token>-intl.json
            return lc.hasPrefix("mac-") && lc.hasSuffix("-intl")
        }
        return filtered
    }

    @MainActor static func categoriesSourcePages(for country: Country) -> [String] {
        var tokens: Set<String> = []
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in macModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(MacRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                    // Include token regardless of skus emptiness; SKUs may be added later
                    for (token, _) in byCountry { tokens.insert(token) }
                }
            }
        }
        return Array(tokens).sorted()
    }

    @MainActor static func tokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in macModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(MacRootLite.self, from: data) else { continue }
            if let name = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] { return name }
            if let name = root.country_mappings?[uc]?.localization?.token_display?[sourcePage] { return name }
        }
        return nil
    }

    @MainActor static func categoryData(for country: Country, sourcePage: String) -> [String: ProductMetadata]? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in macModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(MacRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
                   let node = byCountry[sourcePage], let skus = node.skus, skus.isEmpty == false {
                    return skus
                }
            }
        }
        return nil
    }

    @MainActor static func metadata(for sku: String, country: Country) -> ProductMetadata? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in macModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(MacRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                    for (_, node) in byCountry { if let md = node.skus?[sku] { return md } }
                }
            }
        }
        return nil
    }

    @MainActor static func pdpBaseURL(for country: Country, sourcePage token: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in macModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(MacRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
                   let node = byCountry[token], let nodeURL = node.url, let u = URL(string: nodeURL) { return u }
                if let cm = root.country_mappings?[lc] ?? root.country_mappings?[uc], let path = cm.shop_paths?[token] {
                    let full = "https://www.apple.com/\(lc)/\(path)"
                    if let u = URL(string: full) { return u }
                }
            }
        }
        return nil
    }
}


struct PhoneResolver: CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL? {
        // Lookup metadata from iPhone catalogs
        guard let md = JSONCatalogiPhone.metadata(for: partNumber, country: country) else { return nil }
        // Use urlSlug if present
        guard let slug = md.urlSlug, slug.isEmpty == false else { return nil }
        let cleanSlug = slug.trimmingCharacters(in: CharacterSet(charactersIn: "/")).replacingOccurrences(of: " ", with: "-")
        // Determine sourcePage token
        let sourcePage = md.metadata?.sourcePage
        // Prefer token-aware base scraped from iPhone JSON
        if let sp = sourcePage, let base = JSONCatalogiPhone.pdpBaseURL(for: country, sourcePage: sp) {
            let final = base.absoluteString + cleanSlug
            if let url = URL(string: final) { return url }
        }
        // Conservative fallback: generic buy-iphone base
        let genericBase = "https://www.apple.com/\(country.shortcode.lowercased())/shop/buy-iphone/"
        let final = genericBase + cleanSlug
        if let url = URL(string: final) { return url }
        return nil
    }
}

// Minimal catalog facade over iPhone JSON emitted by scraper (AppleWatch-like shape)
enum JSONCatalogiPhone {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct CountryMap: Codable { let shop_paths: [String: String]?; let localization: AWLocalization? }
    struct PhoneRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: CountryMap]? }

    // Discover iPhone JSON files in the bundle dynamically (e.g., iPhoneModels*-intl.json)
    @MainActor private static func iphoneModelJSONFiles() -> [URL] {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let filtered = candidates.filter { url in
            let name = url.deletingPathExtension().lastPathComponent
            let lc = name.lowercased()
            // Accept both legacy aggregate files and per-model files
            let isLegacy = lc.hasPrefix("iphonemodels") && lc.hasSuffix("-intl")
            let isPerModel = lc.hasPrefix("iphone-") && lc.hasSuffix("-intl")
            return isLegacy || isPerModel
        }
        return filtered
    }

    // Resolve the PDP base URL for a given token using scraped JSON only (no hardcoded mapping)
    @MainActor static func pdpBaseURL(for country: Country, sourcePage token: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                // 1) Prefer discovered_models[country][token].url if present
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
                   let node = byCountry[token], let nodeURL = node.url, let u = URL(string: nodeURL) {
                    return u
                }
                // 2) Fall back to country_mappings.shop_paths token path
                if let cm = root.country_mappings?[lc] ?? root.country_mappings?[uc],
                   let path = cm.shop_paths?[token] {
                    let full = "https://www.apple.com/\(lc)/\(path)"
                    if let u = URL(string: full) { return u }
                }
            }
        }
        return nil
    }

    @MainActor static func loadAll() -> [String: PhoneRootLite] {
        var out: [String: PhoneRootLite] = [:]
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                out[url.lastPathComponent] = root
            }
        }
        return out
    }

    @MainActor static func categoriesSourcePages(for country: Country) -> [String] {
        var tokens: Set<String> = []
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        var fallbackTokens: Set<String> = []
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                // 1) Prefer explicit token keys in country_mappings.shop_paths
                if let paths = root.country_mappings?[lc]?.shop_paths ?? root.country_mappings?[uc]?.shop_paths {
                    for key in paths.keys { if key.lowercased().hasPrefix("iphone-") { tokens.insert(key) } }
                }
                // 2) Fallback: discovered_models keys that look like real tokens
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                    for (key, node) in byCountry {
                        if key.lowercased().hasPrefix("iphone-"), let skus = node.skus, !skus.isEmpty { tokens.insert(key) }
                        else if let skus = node.skus, !skus.isEmpty { fallbackTokens.insert(key) }
                    }
                }
            }
        }
        let result = tokens.isEmpty ? fallbackTokens : tokens
        return Array(result).sorted()
    }

    // Optional JSON-provided, per-country display name for a phone token
    @MainActor static func tokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                // Prefer per-country token display but sanitize away per-SKU noise (capacity)
                if let raw = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] ?? root.country_mappings?[uc]?.localization?.token_display?[sourcePage] {
                    let bad = raw.lowercased()
                    // Heuristics: reject if contains storage units; avoid hardcoded color lists
                    let hasStorage = bad.contains("gb") || bad.contains("tb") || bad.range(of: "\\b[0-9]{2,4}\\s?gb\\b", options: .regularExpression) != nil
                    if hasStorage { return nil }
                    return raw
                }
            }
        }
        return nil
    }

    @MainActor static func categoryData(for country: Country, sourcePage: String) -> [String: ProductMetadata]? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
                   let node = byCountry[sourcePage], let skus = node.skus, skus.isEmpty == false {
                    return skus
                }
            }
        }
        return nil
    }

    // Legacy mapping removed: UI is token-driven exclusively

    // Lookup metadata for a specific SKU by scanning discovered models (new) or legacy categories (old)
    @MainActor static func metadata(for sku: String, country: Country) -> ProductMetadata? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                    for (_, node) in byCountry {
                        if let md = node.skus?[sku] { return md }
                    }
                }
            }
        }
        return nil
    }
}

struct AWLocalization: Codable { let token_display: [String: String]? }

// MARK: - Category Resolver Protocols

// Minimal catalog facade over Apple Watch JSON emitted by the new scraper (per-model files)
enum JSONCatalogAppleWatch {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct WatchRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: JSONCatalogiPhone.CountryMap]? }

    // Discover Apple Watch JSON files: accept both per-model (AppleWatch-*-intl.json) and legacy aggregate (AppleWatchModels-intl.json)
    @MainActor private static func watchModelJSONFiles() -> [URL] {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        return candidates.filter { url in
            let name = url.deletingPathExtension().lastPathComponent
            let lc = name.lowercased()
            let isPerModel = lc.hasPrefix("applewatch-") && lc.hasSuffix("-intl")
            let isLegacy = lc == "applewatchmodels-intl"
            return isPerModel || isLegacy
        }
    }

    @MainActor static func pdpBaseURL(for country: Country, sourcePage token: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let path = root.country_mappings?[lc]?.shop_paths?[token] ?? root.country_mappings?[uc]?.shop_paths?[token] {
                let withSlash = path.hasSuffix("/") ? path : path + "/"
                return URL(string: "https://www.apple.com/\(lc)/\(withSlash)")
            }
        }
        return nil
    }

    /// Returns the per-category buy page URL (e.g. /shop/buy-watch/apple-watch-ultra)
    /// as provided by the scraper JSON (`discovered_models.<country>.<token>.url`).
    /// This is our primary fallback when per-SKU deep links are not present.
    @MainActor static func categoryURL(for country: Country, sourcePage: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
               let node = byCountry[sourcePage],
               let raw = node.url,
               let resolved = URL(string: raw) {
                return resolved
            }
        }
        return nil
    }

    // Returns the ProductMetadata for a given SKU by scanning models for the country
    @MainActor static func metadata(for sku: String, country: Country) -> ProductMetadata? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                for (_, node) in byCountry { if let md = node.skus?[sku] { return md } }
            }
        }
        return nil
    }

    // Access category data using sourcePage token (e.g., "apple-watch-ultra")
    @MainActor static func categoryData(for country: Country, sourcePage: String) -> [String: ProductMetadata]? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc], let node = byCountry[sourcePage], let skus = node.skus, skus.isEmpty == false {
                return skus
            }
        }
        return nil
    }

    // Determine which sourcePage token a given SKU belongs to
    @MainActor static func categoryForSKU(country: Country, sku: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                for (token, node) in byCountry { if node.skus?[sku] != nil { return token } }
            }
        }
        return nil
    }

    // Return available sourcePage tokens for country (e.g., "apple-watch", "apple-watch-ultra", "apple-watch-se")
    @MainActor static func categoriesSourcePages(for country: Country) -> [String] {
        var tokens: Set<String> = []
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                // Include token regardless of skus emptiness; SKUs may be added later
                for (token, _) in byCountry { tokens.insert(token) }
            }
        }
        return Array(tokens).sorted()
    }

    // Optional JSON-provided, per-country display name for a watch token
    @MainActor static func tokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let name = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] {
                return name
            }
            if let name = root.country_mappings?[uc]?.localization?.token_display?[sourcePage] {
                return name
            }
        }
        return nil
    }
}

protocol CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL?
}

struct AppleWatchResolver: CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL? {
        // Resolve metadata and sourcePage token
        guard let md = JSONCatalogAppleWatch.metadata(for: partNumber, country: country) else { return nil }
        var sourcePage = md.metadata?.sourcePage
        if sourcePage == nil { sourcePage = JSONCatalogAppleWatch.categoryForSKU(country: country, sku: partNumber) }

        // Preferred: per-SKU deep link if the JSON provides it.
        if let slug = md.urlSlug, slug.isEmpty == false {
            var cleanSlug = slug
            while cleanSlug.hasPrefix("/") { cleanSlug.removeFirst() }
            if let sp = sourcePage, let base = JSONCatalogAppleWatch.pdpBaseURL(for: country, sourcePage: sp) {
                let final = base.absoluteString + cleanSlug
                if let url = URL(string: final) { return url }
            }
            // Last-resort: generic path + slug
            let genericBase = "https://www.apple.com/\(country.shortcode.lowercased())/shop/buy-watch/"
            if let url = URL(string: genericBase + cleanSlug) { return url }
        }

        // Fallback: open the per-category buy page from JSON (token-based).
        if let sp = sourcePage, let url = JSONCatalogAppleWatch.categoryURL(for: country, sourcePage: sp) {
            return url
        }

        return nil
    }
}

struct ProductMetadata: Codable {
    let name: String
    let colorKey: String
    let colorDisplay: String
    let capacity: String
    let family: String
    let familyName: String?
    let urlSlug: String?
    let price: Double?
    let partNumber: String?
    let metadata: DeviceMetadata?
}

struct DeviceMetadata: Codable {
    let caseSize: String?
    let caseMaterial: String?
    let connectivity: String?
    let color: String?
    let isRealPartNumber: Bool?
    let urlFormat: [String: String]?
    let sourcePage: String?
}

actor SKUDataLoader {
    var defaultsManager = DefaultsVendor()
    
    var skuDataForPreferredProduct: SKUData {
        get async throws {
            // Token-driven app: fallback returns empty; callers primarily use token paths
            _ = defaultsManager.preferredProductFamily
            return SKUData(orderedSKUs: [], lookup: [:])
        }
    }
    
    // (Removed) productType→token mapping helper; use watchSKUData(forToken:country:) from UI

    // Token-based accessor: build SKUData directly from a sourcePage token (e.g., "apple-watch-ultra")
    @MainActor func watchSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: token) else { return nil }
        // Normalize to (sku, meta) where sku uses key if meta.partNumber is missing
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        // Filter valid entries: prefer metadata flag, else validate SKU format, and exclude non-watch accessories
        let valid = normalized.filter { (sku, meta) in
            // Require a real Apple part number OR explicit isRealPartNumber
            // Accept Apple part numbers with 1-3 letter regional suffixes before the slash.
            // Examples: MFYT4ZD/A (2 letters), MX2X3D/A (1 letter)
            let isRealPN = sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil
            let okPN = meta.metadata?.isRealPartNumber ?? isRealPN
            if okPN == false { return false }
            // Exclude accessories (e.g., bands/AppleCare) that slip into Apple Watch pages: keep SKUs that include a case size
            if let hasSize = meta.metadata?.caseSize, hasSize.isEmpty == false { return true }
            return false
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        // Determine a robust base display name for this token
        // Priority: (1) majority familyName across SKUs, (2) per-country token display from per-model JSON,
        // (3) per-country token display from legacy AppleWatchModels-intl.json, (4) generic "Apple Watch".
        let famNames = valid.compactMap { (_, meta) -> String? in
            if let fn = meta.familyName, fn.isEmpty == false, fn.lowercased() != "unknown" { return fn }
            return nil
        }
        let majorityFamilyName: String? = {
            guard famNames.isEmpty == false else { return nil }
            var counts: [String: Int] = [:]
            famNames.forEach { counts[$0, default: 0] += 1 }
            return counts.max(by: { $0.value < $1.value })?.key
        }()
        let tokenDisplayPrimary = JSONCatalogAppleWatch.tokenDisplayName(for: country, sourcePage: token)
        let baseDisplay = majorityFamilyName ?? tokenDisplayPrimary ?? "Apple Watch"

        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            let (sku, meta) = tuple
            let dm = meta.metadata
            // Use resolved base display consistently across the list
            let baseName = baseDisplay
            var parts: [String] = [baseName]
            if let size = dm?.caseSize, !size.isEmpty { parts.append(size) }
            // Prefer explicit color from metadata, then colorDisplay
            var colorName = ""
            if let c = dm?.color, !c.isEmpty { colorName = c.capitalized }
            else if meta.colorDisplay.isEmpty == false { colorName = meta.colorDisplay }
            if !colorName.isEmpty { parts.append(colorName) }
            if let material = dm?.caseMaterial, !material.isEmpty { parts.append(material.capitalized) }
            if let conn = dm?.connectivity, !conn.isEmpty {
                let connPretty = conn.lowercased() == "gpscell" ? "GPS + Cellular" : conn.uppercased()
                parts.append(connPretty)
            }
            let label = parts.joined(separator: " ").replacingOccurrences(of: "  ", with: " ").trimmingCharacters(in: .whitespaces)
            result[sku] = label
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    // Token-based accessor for iPhone: build SKUData directly from a sourcePage token (e.g., "iphone-17-pro")
    @MainActor func phoneSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogiPhone.categoryData(for: country, sourcePage: token) else { return nil }
        // Derive a normalized (sku, meta) tuple where sku uses the map key if meta.partNumber is missing
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        // Filter valid entries: prefer metadata flag, else validate SKU format
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            return sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            let (sku, meta) = tuple
            result[sku] = buildLocalizedProductName(from: meta)
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    // Token-based accessor for Mac: build SKUData directly from a sourcePage token (e.g., "macbook-pro")
    @MainActor func macSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogMac.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }

        // Keep entries that look like plausible Apple SKUs so the Settings UI can display them.
        // For inventory queries, callers should prefer full part numbers (contain a '/').
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            // Full Apple part numbers like MWUE3D/A
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
            // Base codes like MW2X3 (may exist in some catalogs but are not sufficient for pickup-message queries)
            if sku.range(of: "^[A-Z0-9]{3,6}$", options: .regularExpression) != nil { return true }
            return false
        }

        let orderedSKUs = valid
            .map { $0.0 }
            .sorted { a, b in
                let aIsFull = a.contains("/")
                let bIsFull = b.contains("/")
                if aIsFull != bIsFull { return aIsFull && !bIsFull }
                return a < b
            }

        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            let (sku, meta) = tuple
            result[sku] = buildLocalizedProductName(from: meta)
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }
    
    // Legacy ProductType-dependent paths removed. Use watchSKUData(forToken:country:) or phoneSKUData(forToken:country:).
    
    nonisolated private func buildLocalizedProductName(from metadata: ProductMetadata) -> String {
        // Replace the English color name in the product name with the localized color display
        let localizedColor = metadata.colorDisplay
        
        // Prefer the JSON-provided name universally if available (already localized and complete)
        if metadata.name.isEmpty == false {
            return metadata.name
        }
        
        // For Apple Watch, prefer the JSON-provided name if available (handled above)
        // Otherwise, build a descriptive name from metadata
        if let deviceMetadata = metadata.metadata {
            let caseSize = deviceMetadata.caseSize ?? ""
            let caseMaterial = deviceMetadata.caseMaterial ?? metadata.colorDisplay
            let connectivity = deviceMetadata.connectivity ?? ""
            
            if metadata.family.contains("apple_watch") {
                // Build a descriptive name using the metadata including color
                // Derive base name from JSON-provided familyName if available to avoid hardcoded model strings
                let baseName: String = metadata.familyName ?? "Apple Watch"
                
                // Get color from metadata, fallback to colorDisplay
                var colorName = ""
                if let color = deviceMetadata.color, !color.isEmpty {
                    colorName = color.capitalized
                } else if !metadata.colorDisplay.isEmpty && metadata.colorDisplay != caseMaterial.capitalized {
                    colorName = metadata.colorDisplay
                }
                
                // Build the full name with color if available
                if !colorName.isEmpty {
                    return "\(baseName) \(caseSize) \(colorName) \(caseMaterial.capitalized) \(connectivity)"
                } else {
                    return "\(baseName) \(caseSize) \(caseMaterial.capitalized) \(connectivity)"
                }
            }
        }
        
        // Extract the base product name without color for iPhones
        let familyName = metadata.familyName ?? metadata.name.components(separatedBy: " ").first ?? "Unknown"
        let capacity = metadata.capacity.uppercased()
        
        // Build localized name: "iPhone 17 256GB Tiefblau" instead of "iPhone 17 256GB Deep Blue"
        return "\(familyName) \(capacity) \(localizedColor)"
    }
    
    // Legacy iPhone model aggregators removed (generateiPhoneModelsByCountry)
    
    // Legacy iPhone aggregators removed (phoneModels, generateiPhoneModelsByCountry, loadIPhoneModels)
    
                                                                 // country: type:    model:   metadata
    // loadIPhoneModels removed (unified-only flow now)
    
    @MainActor private func appleWatchModels(for country: Country, category: String) throws -> SKUData {
        // Treat `category` as a sourcePage token and use token-based JSON accessors exclusively
        guard let categoryData = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: category) else {
            return SKUData(orderedSKUs: [], lookup: [:])
        }
        // Filter for real Apple part numbers if indicated, else validate part number format
        let validEntries = categoryData.filter { (_, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if let pn = meta.partNumber {
                return pn.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil
            }
            return false
        }
        let orderedSKUs = validEntries.compactMap { (_, meta) in meta.partNumber }.sorted()
        let skuLookup = validEntries.reduce(into: [String: String]()) { result, entry in
            let (_, meta) = entry
            if let part = meta.partNumber { result[part] = buildLocalizedProductName(from: meta) }
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    @MainActor func watchProductURL(for partNumber: String, country: Country) -> URL? {
        return AppleWatchResolver().productURL(for: partNumber, country: country)
    }

    /// Token/category-level buy page URL, derived entirely from our JSON catalogs.
    /// Useful fallback when per-SKU URLs are not present.
    @MainActor func watchCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogAppleWatch.categoryURL(for: country, sourcePage: sourcePage)
    }
    
    @MainActor func phoneProductURL(for partNumber: String, country: Country) -> URL? {
        return PhoneResolver().productURL(for: partNumber, country: country)
    }

    @MainActor func phonePDPBaseURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogiPhone.pdpBaseURL(for: country, sourcePage: sourcePage)
    }

    @MainActor func macCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogMac.pdpBaseURL(for: country, sourcePage: sourcePage)
    }
    
    // MARK: - JSON Loading Methods
    
    // Removed hardcoded category loaders for Mac/iPad/Accessories (clean slate)
}




