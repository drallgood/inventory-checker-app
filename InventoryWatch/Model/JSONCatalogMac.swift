//
//  JSONCatalogMac.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

enum JSONCatalogMac {
    struct Node: Codable { let url: String?; let skus: [String: ProductMetadata]? }
    struct CountryMap: Codable { let shop_paths: [String: String]?; let localization: AWLocalization? }
    struct MacRootLite: Codable { let discovered_models: [String: [String: Node]]?; let country_mappings: [String: CountryMap]? }

    @MainActor private static func macModelJSONFiles() -> [URL] {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let filtered = candidates.filter { url in
            let name = url.deletingPathExtension().lastPathComponent
            let lc = name.lowercased()
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