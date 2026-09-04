//
//  JSONCatalogAppleWatch.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

enum JSONCatalogAppleWatch {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct WatchRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: JSONCatalogiPhone.CountryMap]? }

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

    @MainActor static func categoriesSourcePages(for country: Country) -> [String] {
        var tokens: Set<String> = []
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in watchModelJSONFiles() {
            guard let data = try? Data(contentsOf: url), let root = try? JSONDecoder().decode(WatchRootLite.self, from: data) else { continue }
            if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc] {
                for (token, _) in byCountry { tokens.insert(token) }
            }
        }
        return Array(tokens).sorted()
    }

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

struct AppleWatchResolver: CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL? {
        guard let md = JSONCatalogAppleWatch.metadata(for: partNumber, country: country) else { return nil }
        var sourcePage = md.metadata?.sourcePage
        if sourcePage == nil { sourcePage = JSONCatalogAppleWatch.categoryForSKU(country: country, sku: partNumber) }

        if let slug = md.urlSlug, slug.isEmpty == false {
            var cleanSlug = slug
            while cleanSlug.hasPrefix("/") { cleanSlug.removeFirst() }
            if let sp = sourcePage, let base = JSONCatalogAppleWatch.pdpBaseURL(for: country, sourcePage: sp) {
                let final = base.absoluteString + cleanSlug
                if let url = URL(string: final) { return url }
            }
            let genericBase = "https://www.apple.com/\(country.shortcode.lowercased())/shop/buy-watch/"
            if let url = URL(string: genericBase + cleanSlug) { return url }
        }

        if let sp = sourcePage, let url = JSONCatalogAppleWatch.categoryURL(for: country, sourcePage: sp) {
            return url
        }

        return nil
    }
}