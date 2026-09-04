import Testing
import Foundation
@testable import InventoryWatch

struct SKUResolutionTests {

    @Test func watchSKUDataReturnsNonNilForValidTokenAndUS() async throws {
        let loader = SKUDataLoader()
        let us = Country(name: "United States", shortcode: "US", locale: "en_US", skuCode: "LL")
        let result = await loader.watchSKUData(forToken: "apple-watch", country: us)
        #expect(result != nil, "watchSKUData should return non-nil for valid token plus US combo")
    }

    @Test func watchSKUDataReturnsNilForInvalidToken() async throws {
        let loader = SKUDataLoader()
        let us = Country(name: "United States", shortcode: "US", locale: "en_US", skuCode: "LL")
        let result = await loader.watchSKUData(forToken: "nonexistent-token-xyz", country: us)
        #expect(result == nil, "watchSKUData should return nil for invalid token")
    }

    @Test func buildLocalizedProductNameProducesNonEmptyForKnownSKUs() async throws {
        let loader = SKUDataLoader()
        let us = Country(name: "United States", shortcode: "US", locale: "en_US", skuCode: "LL")
        guard let data = await loader.watchSKUData(forToken: "apple-watch", country: us),
              let firstSKU = data.orderedSKUs.first else {
            return
        }
        let name = SKUDataLoader.buildLocalizedProductName(for: firstSKU, country: us, in: data)
        #expect(name.isEmpty == false, "buildLocalizedProductName should produce non-empty string")
    }
}