//
//  SKUData.swift
//  InventoryWatch
//
//  Created by Worth Baker on 11/8/21.
//

import Foundation

struct SKUData {
    private let skuLookup: [String: String]
    let orderedSKUs: [String]
    
    init(orderedSKUs: [String], lookup: [String: String]) {
        self.orderedSKUs = orderedSKUs
        self.skuLookup = lookup
    }
    
    func productName(forSKU sku: String) -> String? {
        return skuLookup[sku]
    }
}


