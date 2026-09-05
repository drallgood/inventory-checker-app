//
//  ModelLoader.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

actor SKUDataLoader {
    var defaultsManager = DefaultsVendor()
    
    var skuDataForPreferredProduct: SKUData {
        get async throws {
            _ = defaultsManager.preferredProductFamily
            return SKUData(orderedSKUs: [], lookup: [:])
        }
    }

    @MainActor func watchSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            return sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
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
            let baseName = baseDisplay
            var parts: [String] = [baseName]
            if let size = dm?.caseSize, !size.isEmpty { parts.append(size) }
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

    @MainActor func phoneSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogiPhone.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
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

    @MainActor func macSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogMac.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }

        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
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
    
    nonisolated private func buildLocalizedProductName(from metadata: ProductMetadata) -> String {
        let localizedColor = metadata.colorDisplay
        
        if metadata.name.isEmpty == false {
            return metadata.name
        }
        
        if let deviceMetadata = metadata.metadata {
            let caseSize = deviceMetadata.caseSize ?? ""
            let caseMaterial = deviceMetadata.caseMaterial ?? metadata.colorDisplay
            let connectivity = deviceMetadata.connectivity ?? ""
            
            if metadata.family.contains("apple_watch") {
                let baseName: String = metadata.familyName ?? "Apple Watch"
                
                var colorName = ""
                if let color = deviceMetadata.color, !color.isEmpty {
                    colorName = color.capitalized
                } else if !metadata.colorDisplay.isEmpty && metadata.colorDisplay != caseMaterial.capitalized {
                    colorName = metadata.colorDisplay
                }
                
                if !colorName.isEmpty {
                    return "\(baseName) \(caseSize) \(colorName) \(caseMaterial.capitalized) \(connectivity)"
                } else {
                    return "\(baseName) \(caseSize) \(caseMaterial.capitalized) \(connectivity)"
                }
            }
        }
        
        let familyName = metadata.familyName ?? metadata.name.components(separatedBy: " ").first ?? "Unknown"
        let capacity = metadata.capacity.uppercased()
        
        return "\(familyName) \(capacity) \(localizedColor)"
    }
    
    @MainActor private func appleWatchModels(for country: Country, category: String) throws -> SKUData {
        guard let categoryData = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: category) else {
            return SKUData(orderedSKUs: [], lookup: [:])
        }
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

    @MainActor func ipadSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogiPad.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
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

    @MainActor func ipadCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogiPad.pdpBaseURL(for: country, sourcePage: sourcePage)
    }

    @MainActor func airpodsSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogAirPods.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
            if sku.range(of: "^[A-Z0-9]{3,6}$", options: .regularExpression) != nil { return true }
            return false
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            result[tuple.0] = buildLocalizedProductName(from: tuple.1)
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    @MainActor func homepodSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogHomePod.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
            if sku.range(of: "^[A-Z0-9]{3,6}$", options: .regularExpression) != nil { return true }
            return false
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            result[tuple.0] = buildLocalizedProductName(from: tuple.1)
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    @MainActor func avpSKUData(forToken token: String, country: Country) -> SKUData? {
        guard let dict = JSONCatalogAVP.categoryData(for: country, sourcePage: token) else { return nil }
        let normalized: [(String, ProductMetadata)] = dict.map { (key, meta) in
            let sku = meta.partNumber ?? key
            return (sku, meta)
        }
        let valid = normalized.filter { (sku, meta) in
            if let isReal = meta.metadata?.isRealPartNumber { return isReal }
            if sku.range(of: "^[A-Z0-9]{4,8}[A-Z]{1,3}/[A-Z]$", options: .regularExpression) != nil { return true }
            if sku.range(of: "^[A-Z0-9]{3,6}$", options: .regularExpression) != nil { return true }
            return false
        }
        let orderedSKUs = valid.map { $0.0 }.sorted()
        let skuLookup = valid.reduce(into: [String: String]()) { result, tuple in
            result[tuple.0] = buildLocalizedProductName(from: tuple.1)
        }
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }

    @MainActor func airpodsCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogAirPods.pdpBaseURL(for: country, sourcePage: sourcePage)
    }

    @MainActor func homepodCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogHomePod.pdpBaseURL(for: country, sourcePage: sourcePage)
    }

    @MainActor func avpCategoryURL(for country: Country, sourcePage: String) -> URL? {
        return JSONCatalogAVP.pdpBaseURL(for: country, sourcePage: sourcePage)
    }
}