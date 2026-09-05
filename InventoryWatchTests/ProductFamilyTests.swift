import Testing
import Foundation
@testable import InventoryWatch

struct ProductFamilyTests {

    @Test func allCasesContainsWatchPhoneMacIPad() {
        let cases = ProductFamily.allCases
        #expect(cases.contains(.watch), "allCases should contain watch")
        #expect(cases.contains(.iphone), "allCases should contain iphone")
        #expect(cases.contains(.mac), "allCases should contain mac")
        #expect(cases.contains(.ipad), "allCases should contain ipad")
        #expect(cases.contains(.airpods), "allCases should contain airpods")
        #expect(cases.contains(.homepod), "allCases should contain homepod")
        #expect(cases.contains(.avp), "allCases should contain avp")
    }

    @Test func displayNameReturnsExpectedValues() {
        #expect(ProductFamily.watch.displayName == "Apple Watch")
        #expect(ProductFamily.iphone.displayName == "iPhone")
        #expect(ProductFamily.mac.displayName == "Mac")
        #expect(ProductFamily.ipad.displayName == "iPad")
        #expect(ProductFamily.airpods.displayName == "AirPods")
        #expect(ProductFamily.homepod.displayName == "HomePod")
        #expect(ProductFamily.avp.displayName == "Apple Vision Pro")
    }

    @Test func isPropertiesAreMutuallyExclusive() {
        let all: [ProductFamily] = [.watch, .iphone, .mac, .ipad, .airpods, .homepod, .avp]
        for family in all {
            var count = 0
            if family.isWatch { count += 1 }
            if family.isIPhone { count += 1 }
            if family.isMac { count += 1 }
            if family.isIPad { count += 1 }
            if family.isAirPods { count += 1 }
            if family.isHomePod { count += 1 }
            if family.isAVP { count += 1 }
            #expect(count == 1, "\(family) should have exactly one isX property true")
        }
    }
}