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
    
    private static let GermanyAltCode = "FD"
    private static let CanadaAltCode = "VC"
    private static let FranceAltCode = "NF"
    private static let ItalyAltCode = "TY"
    private static let AustriaAltCode = "FD"
    private static let NetherlandsAltCodeStudio = "FN"
    private static let NetherlandsAltCodeiPad = "NF"
}

let USData = Country(
    name: "United States",
    shortcode: "US",
    locale: "en_US",
    skuCode: "LL"
)

let AllCountries = [
    USData,
    Country(name: "Austria", shortcode: "AT", locale: "de_AT", skuCode: "ZD"),
    Country(name: "Australia", shortcode: "AU", locale: "en_AU", skuCode: "X"),
    Country(name: "Canada", shortcode: "CA", locale: "en_CA", skuCode: "LL"),
    Country(name: "Germany", shortcode: "DE", locale: "de_DE", skuCode: "ZD"),
    Country(name: "United Kingdom", shortcode: "UK", locale: "en_GB", skuCode: "QN"),
    Country(name: "France", shortcode: "FR", locale: "fr_FR", skuCode: "FN"),
    Country(name: "Italy", shortcode: "IT", locale: "it_IT", skuCode: "T"),
    Country(name: "Spain", shortcode: "ES", locale: "es_ES", skuCode: "Y"),
    Country(name: "Netherlands", shortcode: "NL", locale: "nl_NL", skuCode: "ZD"),
    Country(name: "Belgium", shortcode: "BE", locale: "nl_BE", skuCode: "ZD"),
    Country(name: "Belgium (Dutch)", shortcode: "BE-NL", locale: "nl_BE", skuCode: "ZD"),
    Country(name: "Belgium (French)", shortcode: "BE-FR", locale: "fr_BE", skuCode: "ZD"),
    Country(name: "Switzerland", shortcode: "CH", locale: "de_CH", skuCode: "ZD"),
    Country(name: "Switzerland (German)", shortcode: "CH-DE", locale: "de_CH", skuCode: "ZD"),
    Country(name: "Switzerland (French)", shortcode: "CH-FR", locale: "fr_CH", skuCode: "ZD"),
    Country(name: "Sweden", shortcode: "SE", locale: "sv_SE", skuCode: "KS"),
    Country(name: "Denmark", shortcode: "DK", locale: "da_DK", skuCode: "KN"),
    Country(name: "Norway", shortcode: "NO", locale: "nb_NO", skuCode: "KN"),
    Country(name: "Finland", shortcode: "FI", locale: "fi_FI", skuCode: "KS"),
    Country(name: "Japan", shortcode: "JP", locale: "ja_JP", skuCode: "J"),
    Country(name: "South Korea", shortcode: "KR", locale: "ko_KR", skuCode: "KH"),
    Country(name: "Hong Kong", shortcode: "HK", locale: "en_HK", skuCode: "ZP"),
    Country(name: "Singapore", shortcode: "SG", locale: "en_SG", skuCode: "ZP"),
    Country(name: "Taiwan", shortcode: "TW", locale: "zh_TW", skuCode: "TA"),
    Country(name: "Thailand", shortcode: "TH", locale: "th_TH", skuCode: "TH"),
    Country(name: "Malaysia", shortcode: "MY", locale: "en_MY", skuCode: "MY"),
    Country(name: "India", shortcode: "IN", locale: "en_IN", skuCode: "HN"),
    Country(name: "UAE", shortcode: "AE", locale: "en_AE", skuCode: "AB"),
    Country(name: "Saudi Arabia", shortcode: "SA", locale: "ar_SA", skuCode: "AB"),
    Country(name: "Turkey", shortcode: "TR", locale: "tr_TR", skuCode: "TU"),
    Country(name: "South Africa", shortcode: "ZA", locale: "en_ZA", skuCode: "ZA"),
    Country(name: "Brazil", shortcode: "BR", locale: "pt_BR", skuCode: "BZ"),
    Country(name: "Mexico", shortcode: "MX", locale: "es_MX", skuCode: "LA"),
    Country(name: "China", shortcode: "CN", locale: "zh_CN", skuCode: "CH"),
]
let Countries: [CountryCode: Country] = Dictionary(uniqueKeysWithValues: AllCountries.map { ($0.shortcode, $0) })
let OrderedCountries: [CountryCode] = AllCountries.map { $0.shortcode }
