import Testing
import Foundation
@testable import InventoryWatch

private struct CountryEntry: Codable {
    let name: String
    let shortcode: String
    let locale: String
    let skuCode: String
}

private struct CountryList: Codable {
    let countries: [CountryEntry]
}

struct CountriesJSONTests {

    @Test func countriesJSONParsesCorrectly() throws {
        guard let url = Bundle.main.url(forResource: "countries", withExtension: "json") else {
            Issue.record("countries.json not found in bundle")
            return
        }
        let data = try Data(contentsOf: url)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(json != nil, "countries.json is not a valid JSON dictionary")
    }

    @Test func allCountryEntriesHaveRequiredFields() throws {
        guard let url = Bundle.main.url(forResource: "countries", withExtension: "json") else {
            Issue.record("countries.json not found in bundle")
            return
        }
        let data = try Data(contentsOf: url)
        let wrapper = try JSONDecoder().decode(CountryList.self, from: data)
        let countries = wrapper.countries
        #expect(countries.isEmpty == false, "Country list is empty")

        for country in countries {
            #expect(country.name.isEmpty == false, "Country missing name: \(country.shortcode)")
            #expect(country.shortcode.isEmpty == false, "Country missing shortcode: \(country.name)")
            #expect(country.locale.isEmpty == false, "Country missing locale: \(country.shortcode)")
            #expect(country.skuCode.isEmpty == false, "Country missing skuCode: \(country.shortcode)")
        }
    }

    @Test func usCountryIsPresent() throws {
        guard let url = Bundle.main.url(forResource: "countries", withExtension: "json") else {
            Issue.record("countries.json not found in bundle")
            return
        }
        let data = try Data(contentsOf: url)
        let wrapper = try JSONDecoder().decode(CountryList.self, from: data)
        let usCountries = wrapper.countries.filter { $0.shortcode == "US" }
        #expect(usCountries.isEmpty == false, "US country not found")
    }

    @Test func noDuplicateShortcodes() throws {
        guard let url = Bundle.main.url(forResource: "countries", withExtension: "json") else {
            Issue.record("countries.json not found in bundle")
            return
        }
        let data = try Data(contentsOf: url)
        let wrapper = try JSONDecoder().decode(CountryList.self, from: data)
        let shortcodes = wrapper.countries.map { $0.shortcode }
        let uniqueShortcodes = Set(shortcodes)
        #expect(uniqueShortcodes.count == shortcodes.count, "Duplicate shortcodes found in countries.json")
    }
}