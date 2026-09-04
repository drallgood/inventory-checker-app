//
//  DefaultsVendor.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation
import Combine

// Minimal product family selector for token-driven UI
enum ProductFamily: String, Codable, CaseIterable, Identifiable {
    case watch = "watch"
    case iphone = "iphone"
    case mac = "mac"
    case ipad = "ipad"
    var id: Self { self }
    var isWatch: Bool { self == .watch }
    var isIPhone: Bool { self == .iphone }
    var isMac: Bool { self == .mac }
    var isIPad: Bool { self == .ipad }
    var displayName: String {
        switch self {
        case .watch: return "Apple Watch"
        case .iphone: return "iPhone"
        case .mac: return "Mac"
        case .ipad: return "iPad"
        }
    }
}

extension UserDefaults {
    
    @objc dynamic var preferredStoreNumber: String {
        get { string(forKey: "preferredStoreNumber") ?? "" }
        set { setValue(newValue, forKey: "preferredStoreNumber") }
    }
    
    @objc dynamic var lastUpdateDate: String? {
        get { string(forKey: "lastUpdateDate") }
        set { setValue(newValue, forKey: "lastUpdateDate") }
    }
    
    @objc dynamic var preferredUpdateInterval: Int {
        get {
            if let currentValue = object(forKey: "preferredUpdateInterval") as? Int {
                return currentValue
            } else {
                // WB 10/28/22: Changing default update interval from 1min to 5min
                let presetValue = 5
                set(presetValue, forKey: "preferredUpdateInterval")
                
                return presetValue
            }
        }
        set { setValue(newValue, forKey: "preferredUpdateInterval") }
    }
}

struct DefaultsVendor {
    
    var preferredCountry: Country {
        let value = UserDefaults.standard.string(forKey: "preferredCountry") ?? "US"
        
        return Countries[value] ?? USData
    }
    
    var preferredProductFamily: ProductFamily {
        // Reuse same storage key for backward compatibility; map any unknowns to iphone
        let value = UserDefaults.standard.string(forKey: "preferredProductType") ?? ProductFamily.iphone.rawValue
        return ProductFamily(rawValue: value) ?? .iphone
    }
    
    var countryPathElement: String {
        let country = preferredCountry
        if country.shortcode == "US" {
            return ""
        } else {
            return country.shortcode.lowercased() + "/"
        }
    }
    
    var preferredStoreNumber: String {
        get { return UserDefaults.standard.preferredStoreNumber }
        set { UserDefaults.standard.preferredStoreNumber = newValue }
    }
    
    var lastUpdateDate: String? {
        get { return UserDefaults.standard.lastUpdateDate }
        set { UserDefaults.standard.lastUpdateDate = newValue }
    }
    
    // unused - keeping this around as an example implementation
    private var preferredStoreNumberStream: AnyPublisher<String, Never> {
        return UserDefaults.standard
            .publisher(for: \.preferredStoreNumber)
            .eraseToAnyPublisher()
    }
    
    var preferredUpdateInterval: Int {
        return UserDefaults.standard.preferredUpdateInterval
    }
    
    var shouldIncludeNearbyStores: Bool {
        let value = UserDefaults.standard.object(forKey: "shouldIncludeNearbyStores") as? Bool
        
        return value ?? true
    }
    
    var preferredSKUs: Set<String> {
        guard let defaults = UserDefaults.standard.string(forKey: "preferredSKUs") else {
            return []
        }
        
        return defaults.components(separatedBy: ",").reduce(into: Set<String>()) { partialResult, next in
            partialResult.insert(next)
        }
    }
    
    var customSkuData: (sku: String, nickname: String)? {
        guard
            let sku = UserDefaults.standard.string(forKey: "customSku"),
            let name = UserDefaults.standard.string(forKey: "customSkuNickname")
        else {
            return nil
        }
        
        return (sku, name)
    }
    
    var showResultsOnlyForPreferredModels: Bool {
        UserDefaults.standard.bool(forKey: "showResultsOnlyForPreferredModels")
    }
    
    var notifyOnlyForPreferredModels: Bool {
        UserDefaults.standard.bool(forKey: "notifyOnlyForPreferredModels")
    }

    var notificationCooldownHours: Int {
        let val = UserDefaults.standard.integer(forKey: "notificationCooldownHours")
        return val > 0 ? val : 24
    }

    // Token-driven Apple Watch selection
    var preferredWatchToken: String {
        UserDefaults.standard.string(forKey: "preferredWatchToken") ?? ""
    }

    // Token-driven iPhone selection
    var preferredPhoneToken: String {
        UserDefaults.standard.string(forKey: "preferredPhoneToken") ?? ""
    }

    // Token-driven Mac selection
    var preferredMacToken: String {
        UserDefaults.standard.string(forKey: "preferredMacToken") ?? ""
    }

    var preferrediPadToken: String {
        UserDefaults.standard.string(forKey: "preferrediPadToken") ?? ""
    }
}
