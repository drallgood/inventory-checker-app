//
//  Countries.swift
//  InventoryWatch
//
//  Created by Worth Baker on 11/10/21.
//

import Foundation

struct Country: Hashable {
    let name: String
    let shortcode: String
    let locale: String
    let skuCode: String
}

let USData = Country(
    name: "United States",
    shortcode: "US",
    locale: "en_US",
    skuCode: "LL"
)

private struct CountryJSON: Codable {
    struct Entry: Codable {
        let name: String
        let shortcode: String
        let locale: String
        let skuCode: String
    }
    let countries: [Entry]
}

private let allCountriesFromJSON: [Country] = {
    guard let url = Bundle.main.url(forResource: "countries", withExtension: "json"),
          let data = try? Data(contentsOf: url),
          let decoded = try? JSONDecoder().decode(CountryJSON.self, from: data)
    else {
        return [USData]
    }
    return decoded.countries.map {
        Country(name: $0.name, shortcode: $0.shortcode, locale: $0.locale, skuCode: $0.skuCode)
    }
}()

let AllCountries: [Country] = allCountriesFromJSON
let Countries: [CountryCode: Country] = Dictionary(uniqueKeysWithValues: AllCountries.map { ($0.shortcode, $0) })
let OrderedCountries: [CountryCode] = AllCountries.map { $0.shortcode }