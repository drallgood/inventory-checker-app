//
//  Store.swift
//  InventoryWatch
//
//  Created by Worth Baker on 7/27/22.
//

import Foundation

struct FulfillmentStore: Equatable {
    let store: RetailStore
    let partsAvailability: [PartAvailability]

    var storeName: String { store.name }
    var storeNumber: String { store.storeNumber }
    var city: String { store.address.city }
    var state: String? { store.address.stateName }
    var locationDescription: String { store.address.cityStateDisplay }
}