//
//  JSONCatalogiPhone.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

struct PhoneResolver: CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL? {
        guard let md = JSONCatalogiPhone.metadata(for: partNumber, country: country) else { return nil }
        guard let slug = md.urlSlug, slug.isEmpty == false else { return nil }
        let cleanSlug = slug.trimmingCharacters(in: CharacterSet(charactersIn: "/")).replacingOccurrences(of: " ", with: "-")
        let sourcePage = md.metadata?.sourcePage
        if let sp = sourcePage, let base = JSONCatalogiPhone.pdpBaseURL(for: country, sourcePage: sp) {
            let final = base.absoluteString + cleanSlug
            if let url = URL(string: final) { return url }
        }
        let genericBase = "https://www.apple.com/\(country.shortcode.lowercased())/shop/buy-iphone/"
        let final = genericBase + cleanSlug
        if let url = URL(string: final) { return url }
        return nil
    }
}

enum JSONCatalogiPhone {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct CountryMap: Codable { let shop_paths: [String: String]?; let localization: AWLocalization? }
    struct PhoneRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: CountryMap]? }

    @MainActor private static func iphoneModelJSONFiles() -> [URL] {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let filtered = candidates.filter { url in
            let name = url.deletingPathExtension().lastPathComponent
            let lc = name.lowercased()
            let isLegacy = lc.hasPrefix("iphonemodels") && lc.hasSuffix("-intl")
            let isPerModel = lc.hasPrefix("iphone-") && lc.hasSuffix("-intl")
            return isLegacy || isPerModel
        }
        return filtered
    }

    @MainActor static func pdpBaseURL(for country: Country, sourcePage token: String) -> URL? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                if let byCountry = root.discovered_models?[lc] ?? root.discovered_models?[uc],
                   let node = byCountry[token], let nodeURL = node.url, let u = URL(string: nodeURL) {
                    return u
                }
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
                if let paths = root.country_mappings?[lc]?.shop_paths ?? root.country_mappings?[uc]?.shop_paths {
                    for key in paths.keys { if key.lowercased().hasPrefix("iphone-") { tokens.insert(key) } }
                }
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

    @MainActor static func tokenDisplayName(for country: Country, sourcePage: String) -> String? {
        let lc = country.shortcode.lowercased()
        let uc = country.shortcode.uppercased()
        for url in iphoneModelJSONFiles() {
            guard let data = try? Data(contentsOf: url) else { continue }
            if let root = try? JSONDecoder().decode(PhoneRootLite.self, from: data) {
                if let raw = root.country_mappings?[lc]?.localization?.token_display?[sourcePage] ?? root.country_mappings?[uc]?.localization?.token_display?[sourcePage] {
                    let bad = raw.lowercased()
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