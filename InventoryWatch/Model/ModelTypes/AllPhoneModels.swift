//
//  AllPhoneModels.swift
//  InventoryWatch
//
//  Created by Worth Baker on 7/27/22.
//

import Foundation

struct AllPhoneModels {
    struct PhoneModel {
        let sku: String
        let productName: String
    }
    
    var proMax17: [PhoneModel]
    var pro17: [PhoneModel]
    var regular17: [PhoneModel]
    var air: [PhoneModel]
    var iphone16e: [PhoneModel]
    
    func toSkuData(_ keypath: KeyPath<AllPhoneModels, [AllPhoneModels.PhoneModel]>) -> SKUData {
        let models = self[keyPath: keypath]
        
        let lookup: [String: String] = models.reduce(into: [:]) { acc, next in
            acc[next.sku] = next.productName
        }
        
        return SKUData(orderedSKUs: models.map { $0.sku }, lookup: lookup)
    }
}
