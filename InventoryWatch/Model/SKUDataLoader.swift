//
//  ModelLoader.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

actor SKUDataLoader {
    
    private enum iPhoneModel: CaseIterable {
        case sixteen, seventeen, air
    }
    
    var defaultsManager = DefaultsVendor()
    
    private var cachediPhoneData: [Country: AllPhoneModels] = [:]
    private var cachedAppleWatchUltraData: [CountryCode: AppleWatchData] = [:]
    
    var skuDataForPreferredProduct: SKUData {
        get async throws {
            return try await skuData(for: defaultsManager.preferredProductType, and: defaultsManager.preferredCountry)
        }
    }
    
    func skuData(for productType: ProductType, and country: Country) async throws -> SKUData {
        switch productType {
        case .MacBookPro:
            return try loadMacModels(for: country, category: "macbook_pro_m1")
        case .M2MacBookPro13:
            return try loadMacModels(for: country, category: "macbook_pro_m2_13")
        case .M2MacBookAir:
            return try loadMacModels(for: country, category: "macbook_air_m2")
        case .MacStudio:
            return try loadMacModels(for: country, category: "mac_studio")
            
        case .StudioDisplay:
            return try loadAccessoryModels(for: country, category: "studio_display")
        case .AirPodsProGen3:
            return try loadAccessoryModels(for: country, category: "airpods_pro_gen3")
        case .ApplePencilUSBCAdapter:
            return try loadAccessoryModels(for: country, category: "apple_pencil_usbc_adapter")
            
        case .iPadMiniWifi:
            return try loadiPadModels(for: country, category: "ipad_mini_wifi")
        case .iPadMiniCellular:
            return try loadiPadModels(for: country, category: "ipad_mini_cellular")
        case .iPad10thGenWifi:
            return try loadiPadModels(for: country, category: "ipad_10th_gen_wifi")
        case .iPad10thGenCellular:
            return try loadiPadModels(for: country, category: "ipad_10th_gen_cellular")
        case .iPadProM2_11in_Wifi:
            return try loadiPadModels(for: country, category: "ipad_pro_m2_11in_wifi")
        case .iPadProM2_11in_Cellular:
            return try loadiPadModels(for: country, category: "ipad_pro_m2_11in_cellular")
        case .iPadProM2_13in_Wifi:
            return try loadiPadModels(for: country, category: "ipad_pro_m2_13in_wifi")
        case .iPadProM2_13in_Cellular:
            return try loadiPadModels(for: country, category: "ipad_pro_m2_13in_cellular")
            
        case .iPhone16e:
            return try phoneModels(for: country).toSkuData(\.iphone16e)
        case .iPhoneAir:
            return try phoneModels(for: country).toSkuData(\.air)
        case .iPhoneRegular17:
            return try phoneModels(for: country).toSkuData(\.regular17)
        case .iPhonePro17:
            return try phoneModels(for: country).toSkuData(\.pro17)
        case .iPhoneProMax17:
            return try phoneModels(for: country).toSkuData(\.proMax17)
            
        case .AppleWatchUltra:
            return try appleWatchUltraModels(for: country)
        }
    }
    
    private func generateiPhoneModelsByCountry() throws -> [Country: AllPhoneModels] {
        if cachediPhoneData.isEmpty == false {
            return cachediPhoneData
        }
        
        var rv = [Country: AllPhoneModels]()
        
        for phoneModel in iPhoneModel.allCases {
            let phoneModelsJson = try loadIPhoneModels(for: phoneModel)
            
            for (countryCode, phones) in phoneModelsJson {
                guard let country = Countries[countryCode.uppercased()] else {
                    throw AppError.invalidLocalModelStore
                }
                
                let unmappedModelsData: [(String, WritableKeyPath<AllPhoneModels, [AllPhoneModels.PhoneModel]>)]
                switch phoneModel {
                case .sixteen:
                    unmappedModelsData = [
                        ("iphone16e", \AllPhoneModels.iphone16e)
                    ]
                case .seventeen:
                    unmappedModelsData = [
                        ("regular17", \AllPhoneModels.regular17),
                        ("pro17", \AllPhoneModels.pro17),
                        ("proMax17", \AllPhoneModels.proMax17)
                    ]
                case .air:
                unmappedModelsData = [
                    ("air", \AllPhoneModels.air),
                ]
                }
                
                let modelsData = unmappedModelsData.map { first, second in
                    return (phones[first], second)
                }
                
                var phoneModels: AllPhoneModels
                if let existing = rv[country] {
                    phoneModels = existing
                } else {
                    phoneModels = AllPhoneModels(proMax17: [], pro17: [], regular17: [], air: [], iphone16e: [])
                }
                
                for (models, keyPath) in modelsData {
                    guard let models = models else {
                        continue
                    }
                    
                    let parsed: [AllPhoneModels.PhoneModel] = models.map { modelData in
                        return AllPhoneModels.PhoneModel(sku: modelData.key, productName: modelData.value)
                    }.sorted { $0.sku < $1.sku }
                    
                    phoneModels[keyPath: keyPath] = parsed
                }
                
                rv[country] = phoneModels
            }
        }
        
        cachediPhoneData = rv
        return rv
    }
    
    private func phoneModels(for country: Country) throws -> AllPhoneModels {
        let iPhoneModels = try generateiPhoneModelsByCountry()
        
        guard let models = iPhoneModels[country] else {
            throw AppError.invalidLocalModelStore
        }
        
        return models
    }
    
                                                                 // country: type:    model:   description
    private func loadIPhoneModels(for model: iPhoneModel) throws -> [String: [String: [String: String]]] {
        let location: String
        switch model {
        case .sixteen:
            location = "iPhoneModels16-intl"
        case .seventeen:
            location = "iPhoneModels17-intl"
        case .air:
            location = "iPhoneModelsAir-intl"
        }
        
        if let path = Bundle.main.path(forResource: location, ofType: "json") {
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            let decoder = JSONDecoder()
            
            let iphoneData = try decoder.decode([String: [String: [String: String]]].self, from: data)
            return iphoneData
        } else {
            throw AppError.invalidProjectState
        }
    }
    
    private func appleWatchUltraModels(for country: Country) throws -> SKUData {
        let rawData = try loadAppleWatchUltraModels()
        if rawData.isEmpty {
            fatalError()
        }
        
        var compiled: [Country: AppleWatchData] = [:]
        for (countryCode, models) in rawData {
            guard let foundCountry = Countries[countryCode.uppercased()] else {
                throw AppError.invalidLocalModelStore
            }
            
            compiled[foundCountry] = models
        }
        
        guard let countryData = compiled[country] else {
            throw AppError.invalidLocalModelStore
        }
        
        return countryData.toSkuData()
    }
    
    private func loadAppleWatchUltraModels() throws -> [CountryCode: AppleWatchData] {
        if cachedAppleWatchUltraData.isEmpty == false {
            return cachedAppleWatchUltraData
        }
        
        if let path = Bundle.main.path(forResource: "AppleWatchUltra-intl", ofType: "json") {
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            let decoder = JSONDecoder()
            
            if let appleWatchData = try? decoder.decode([String: [String: [String: String]]].self, from: data) {
                let mapped: [CountryCode: AppleWatchData] = appleWatchData.reduce(into: [:]) { partialResult, item in
                    let data = AppleWatchData(from: item.value)
                    partialResult[item.key] = data
                }
                
                cachedAppleWatchUltraData = mapped
                return mapped
            } else {
                throw AppError.invalidLocalModelStore
            }
        } else {
            throw AppError.invalidProjectState
        }
    }
    
    // MARK: - JSON Loading Methods
    
    private func loadMacModels(for country: Country, category: String) throws -> SKUData {
        return try loadModelsFromJSON(fileName: "MacModels-intl", country: country, category: category)
    }
    
    private func loadiPadModels(for country: Country, category: String) throws -> SKUData {
        return try loadModelsFromJSON(fileName: "iPadModels-intl", country: country, category: category)
    }
    
    private func loadAccessoryModels(for country: Country, category: String) throws -> SKUData {
        return try loadModelsFromJSON(fileName: "AccessoryModels-intl", country: country, category: category)
    }
    
    private func loadModelsFromJSON(fileName: String, country: Country, category: String) throws -> SKUData {
        guard let path = Bundle.main.path(forResource: fileName, ofType: "json") else {
            throw AppError.invalidProjectState
        }
        
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let decoder = JSONDecoder()
        
        let jsonData = try decoder.decode([String: [String: [String: String]]].self, from: data)
        
        let countryKey = country.shortcode.lowercased()
        guard let countryData = jsonData[countryKey],
              let categoryData = countryData[category] else {
            throw AppError.invalidLocalModelStore
        }
        
        let orderedSKUs = categoryData.keys.sorted()
        let skuLookup = categoryData
        
        return SKUData(orderedSKUs: orderedSKUs, lookup: skuLookup)
    }
}




