//
//  ModelError.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

enum AppError: Swift.Error, LocalizedError {
    case failedToParseGithubVersion
    case invalidLocalModelStore
    case invalidProjectState
    case invalidCatalogData
    case couldNotGenerateURL
    case noStoresFound
    case storeUnavailable
    case invalidStoreResponse
    case unexpectedJSONStructure
    case accessDenied
    case resourceNotFound
    case rateLimited
    case generic(Error?)
    
    var errorDescription: String? {
        switch self {
        case .generic(let error):
            return error?.localizedDescription ?? "unknown error"
        default:
            return "\(self)"
        }
    }
    
    var errorMessage: String {
        switch self {
        case .couldNotGenerateURL:
            return "InventoryWatch failed to construct a valid URL for your search."
        case .invalidCatalogData:
            return "The bundled model catalog JSON is missing required part numbers for this product. Please update the catalog files (they must include full Apple part numbers like MWUE3D/A, not only base codes like MWUE3D)."
        case .invalidStoreResponse, .unexpectedJSONStructure, .noStoresFound:
            return "Unexpected inventory data found. Please confirm that the selected store is valid for the selected country."
        case .storeUnavailable:
            return "Apple's fulfillment API returned an internal server error and is currently unavailable."
        case .accessDenied:
            return "Access denied by Apple's servers. This may be due to rate limiting or geographic restrictions."
        case .resourceNotFound:
            return "The requested inventory resource was not found. The product may not be available in your region."
        case .rateLimited:
            return "Too many requests sent to Apple's servers. Please wait a few minutes before trying again."
        case .invalidLocalModelStore, .invalidProjectState, .failedToParseGithubVersion:
            return "InventoryWatch has invalid or currupted local data. Please contact the developer (@worthbak)."
        case .generic(let optional):
            return "A network error occurred. Details: \(optional?.localizedDescription ?? "unknown")"
        }
    }
}
