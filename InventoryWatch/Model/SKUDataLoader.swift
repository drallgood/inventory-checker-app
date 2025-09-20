//
//  ModelLoader.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

// MARK: - Product Metadata Structures

struct ProductConfigData: Codable {
    let productPaths: [String: String]?
    let urlMappings: URLMappings?
    let recognizedMaterials: [String]?
    let metadata: ConfigMetadata?
}

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

    // Token-based accessor for Mac
    @MainActor func macSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogMac.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            // Accept full Apple part numbers e.g. MWUE3D/A
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$", options: .regularExpression) != nil { return true }
            // Interim: accept base codes (e.g., MX2J3) so UI can display while scrapers evolve
            if sku.range(of: "^[A-Z0-9]{3,6}$", options: .regularExpression) != nil { return true }
            return false
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            let (sku, meta) = tuple
            // Localized name fallback without depending on SKUDataLoader helper
            let base = (meta.familyName?.isEmpty == false) ? meta.familyName! : (meta.name.isEmpty ? "Mac" : meta.name)
            let cap = meta.capacity.isEmpty ? "" : " \(meta.capacity)"
            let color = meta.colorDisplay.isEmpty ? "" : " \(meta.colorDisplay)"
            result[sku] = base + cap + color
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
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
        var anyTokens: Set<String> = []
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                // Selected country
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                    for (token, node) in byCountry { if let skus = node.skus, !skus.isEmpty { tokens.insert(token) } }
                }
                // Any country (fallback)
                if let all = root.discovered_models {
                    for (_, dict) in all {
                        for (token, node) in dict { if let skus = node.skus, !skus.isEmpty { anyTokens.insert(token) } }
                    }
                }
            }
        }
        let result = tokens.isEmpty ? anyTokens : tokens
        return Array(result).sorted()
    }

    // Optional JSON-provided, per-country display name for a phone token
    @MainActor static func tokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                if let name = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] { return name }
                if let name = root.country_mappings?[uc]?.localization?.token_display?[sourcePage] { return name }
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

struct URLMappings: Codable {
    let connectivity: [String: String]?
    let materials: [String: String]?
    let colors: [String: String]?
}

struct ConfigMetadata: Codable {
    let source: String?
    let version: String?
    let extractedFromPages: Bool?
}

struct AWLocalization: Codable { let token_display: [String: String]? }
struct AWCountryShopPaths: Codable {
    let shop_paths: [String: String]?
    let localization: AWLocalization?
}

struct AppleWatchConfig: Codable {
    let urlMappings: URLMappings?
    let products: [String: [String: [String: ProductMetadata]]]?
    let country_mappings: [String: AWCountryShopPaths]?
    let metadata: ConfigMetadata?
}

class ProductConfiguration {
    @MainActor private static var configData: ProductConfigData?
    @MainActor private static var watchConfig: AppleWatchConfig?
    
    // MARK: - Configuration Loading
    @MainActor static func loadConfiguration() {
        guard let url = Bundle.main.url(forResource: "product-config", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let config = try? JSONDecoder().decode(ProductConfigData.self, from: data) else {
            return
        }
        configData = config
    }
    
    @MainActor static func loadAppleWatchConfiguration() {
        guard let url = Bundle.main.url(forResource: "AppleWatchModels-intl", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let config = try? JSONDecoder().decode(AppleWatchConfig.self, from: data) else {
            return
        }
        watchConfig = config
    }
    
    // MARK: - Helper Methods
    static func buildProductURL(countryPath: String, shopPath: String) -> String {
        return "https://www.apple.com/\(countryPath)shop/\(shopPath)"
    }
    
    // URL component normalization using Apple Watch mappings
    @MainActor static func normalizeConnectivity(_ connectivity: String) -> String {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        return watchConfig?.urlMappings?.connectivity?[connectivity.lowercased()] ?? connectivity.lowercased()
    }
    
    @MainActor static func normalizeMaterial(_ material: String) -> String {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        return watchConfig?.urlMappings?.materials?[material.lowercased()] ?? material.lowercased()
    }
    
    @MainActor static func normalizeColor(_ color: String) -> String {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        return watchConfig?.urlMappings?.colors?[color.lowercased()] ?? color.lowercased()
    }
    
    static var defaultSize: String { "42mm" }
    static var defaultMaterial: String { "aluminum" }
    static var defaultConnectivity: String { "gps" }

    // MARK: - Cached shop_paths accessors
    @MainActor static func watchShopPath(for country: Country, sourcePage: String) -> String? {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        guard let paths = watchConfig?.country_mappings?[country.shortcode.lowercased()]?.shop_paths else { return nil }
        // Find entry whose last path component equals sourcePage
        for (_, path) in paths {
            if URL(string: "https://apple.com/\(path)")?.lastPathComponent == sourcePage {
                return path
            }
        }
        return nil
    }

    @MainActor static func watchPDPBaseURL(for country: Country, sourcePage: String) -> URL? {
        guard let path = watchShopPath(for: country, sourcePage: sourcePage) else { return nil }
        let pathWithSlash = path.hasSuffix("/") ? path : path + "/"
        return URL(string: "https://www.apple.com/\(country.shortcode.lowercased())/\(pathWithSlash)")
    }

    // Optional JSON-provided, per-country display name for a watch token
    @MainActor static func watchTokenDisplayName(for country: Country, sourcePage: String) -> String? {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        if let name = watchConfig?.country_mappings?[lc]?.localization?.token_display?[sourcePage] {
            return name
        }
        if let name = watchConfig?.country_mappings?[uc]?.localization?.token_display?[sourcePage] {
            return name
        }
        return nil
    }

    // MARK: - iPhone token helpers (read from iPhone JSON files)
    @MainActor static func phonePDPBaseURL(for country: Country, sourcePage: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        let all = JSONCatalogiPhone.loadAll()
        for root in all.values {
            if let path = root.country_mappings?[lc]?.shop_paths?[sourcePage] ?? root.country_mappings?[uc]?.shop_paths?[sourcePage] {
                let withSlash = path.hasSuffix("/") ? path : path + "/"
                return URL(string: "https://www.apple.com/\(lc)/\(withSlash)")
            }
        }
        return nil
    }

    @MainActor static func phoneTokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        let all = JSONCatalogiPhone.loadAll()
        for root in all.values {
            if let name = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] ?? root.country_mappings?[uc]?.localization?.token_display?[sourcePage] {
                return name
            }
        }
        return nil
    }

    // MARK: - Apple Watch Products Accessors (read-only)
    @MainActor static func watchProducts(for country: Country) -> [String: [String: ProductMetadata]]? {
        if watchConfig == nil { loadAppleWatchConfiguration() }
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        return watchConfig?.products?[lc] ?? watchConfig?.products?[uc]
    }


}

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
        guard let md = JSONCatalogAppleWatch.metadata(for: partNumber, country: country), let slug = md.urlSlug, !slug.isEmpty else { return nil }
        var sourcePage = md.metadata?.sourcePage
        if sourcePage == nil { sourcePage = JSONCatalogAppleWatch.categoryForSKU(country: country, sku: partNumber) }
        var cleanSlug = slug
        while cleanSlug.hasPrefix("/") { cleanSlug.removeFirst() }
        if let sp = sourcePage, let base = JSONCatalogAppleWatch.pdpBaseURL(for: country, sourcePage: sp) {
            let final = base.absoluteString + cleanSlug
            if let url = URL(string: final) { return url }
        }
        // Fallback generic path
        let genericBase = "https://www.apple.com/\(country.shortcode.lowercased())/shop/buy-watch/"
        let final = genericBase + cleanSlug
        if let url = URL(string: final) { return url }
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
        // Filter valid entries: prefer metadata flag, else validate SKU format on the resolved sku
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            return sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$", options: .regularExpression) != nil
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            let (sku, meta) = tuple
            result[sku] = buildLocalizedProductName(from: meta)
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
            return sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$", options: .regularExpression) != nil
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
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
                return pn.range(of: "^[A-Z0-9]{4,8}[A-Z]{2}/[A-Z]$", options: .regularExpression) != nil
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
    
    @MainActor func phoneProductURL(for partNumber: String, country: Country) -> URL? {
        return PhoneResolver().productURL(for: partNumber, country: country)
    }

    @MainActor func phonePDPBaseURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogiPhone.pdpBaseURL(for: country, sourcePage: sourcePage)
    }
    
    // MARK: - JSON Loading Methods
    
    // Removed hardcoded category loaders for Mac/iPad/Accessories (clean slate)
}




