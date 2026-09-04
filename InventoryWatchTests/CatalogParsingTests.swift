import Testing
import Foundation
@testable import InventoryWatch

struct CatalogParsingTests {

    @Test func allIntlJSONFilesParseSuccessfully() throws {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let intlFiles = candidates.filter { $0.lastPathComponent.lowercased().hasSuffix("-intl.json") }
        #expect(intlFiles.isEmpty == false, "No intl json files found in bundle")

        for url in intlFiles {
            let data = try Data(contentsOf: url)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            #expect(json != nil, "File \(url.lastPathComponent) is not a valid JSON dictionary")
        }
    }

    @Test func intlJSONFilesHaveDiscoveredModels() throws {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let intlFiles = candidates.filter { $0.lastPathComponent.lowercased().hasSuffix("-intl.json") }

        for url in intlFiles {
            let data = try Data(contentsOf: url)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            #expect(json?["discovered_models"] != nil, "File \(url.lastPathComponent) missing discovered_models key")
        }
    }

    @Test func intlJSONFilesHaveCountryEntriesWithSKUs() throws {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let intlFiles = candidates.filter { $0.lastPathComponent.lowercased().hasSuffix("-intl.json") }

        var foundCountryWithSKUs = false
        for url in intlFiles {
            let data = try Data(contentsOf: url)
            if let root = try? JSONDecoder().decode(CatalogRoot.self, from: data),
               let models = root.discovered_models {
                for (_, category) in models {
                    for (_, node) in category {
                        if let skus = node.skus, skus.isEmpty == false {
                            foundCountryWithSKUs = true
                            break
                        }
                    }
                    if foundCountryWithSKUs { break }
                }
            }
            if foundCountryWithSKUs { break }
        }
        #expect(foundCountryWithSKUs, "No country entries with SKUs found across intl files")
    }

    @Test func intlJSONSKUsHaveRequiredProductMetadataFields() throws {
        let candidates = Bundle.main.urls(forResourcesWithExtension: "json", subdirectory: nil) ?? []
        let intlFiles = candidates.filter { $0.lastPathComponent.lowercased().hasSuffix("-intl.json") }

        var checkedAtLeastOne = false
        for url in intlFiles {
            let data = try Data(contentsOf: url)
            guard let root = try? JSONDecoder().decode(CatalogRoot.self, from: data),
                  let models = root.discovered_models else { continue }

            for (_, category) in models {
                for (_, node) in category {
                    guard let skus = node.skus else { continue }
                    for (_, sku) in skus {
                        checkedAtLeastOne = true
                        #expect(sku.colorKey.isEmpty == false, "SKU missing colorKey in \(url.lastPathComponent)")
                        #expect(sku.colorDisplay.isEmpty == false, "SKU missing colorDisplay in \(url.lastPathComponent)")
                        #expect(sku.capacity.isEmpty == false, "SKU missing capacity in \(url.lastPathComponent)")
                        #expect(sku.family.isEmpty == false, "SKU missing family in \(url.lastPathComponent)")
                    }
                }
            }
            if checkedAtLeastOne { break }
        }
        #expect(checkedAtLeastOne, "No SKUs found to validate required fields")
    }
}