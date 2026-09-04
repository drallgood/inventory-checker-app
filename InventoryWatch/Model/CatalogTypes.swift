//
//  CatalogTypes.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

struct AWLocalization: Codable { let token_display: [String: String]? }

protocol CategoryResolver {
    @MainActor func productURL(for partNumber: String, country: Country) -> URL?
}

struct ProductMetadata: Codable {
    let name: String
    let colorKey: String
    let colorDisplay: String
    let capacity: String
    let family: String
    let familyName: String?
    let urlSlug: String?
    let price: Double?
    let partNumber: String?
    let metadata: DeviceMetadata?
}

struct DeviceMetadata: Codable {
    let caseSize: String?
    let caseMaterial: String?
    let connectivity: String?
    let color: String?
    let isRealPartNumber: Bool?
    let urlFormat: [String: String]?
    let sourcePage: String?
}