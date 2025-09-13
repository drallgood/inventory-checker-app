//
//  PartAvailability.swift
//  InventoryWatch
//
//  Created by Worth Baker on 7/27/22.
//

import Foundation

struct PartAvailability: Equatable, Hashable {
    enum PickupAvailability: String {
        case available, unavailable, ineligible
    }
    
    let partNumber: String
    let partName: String
    let availability: PickupAvailability
    let availabilityStorePickupQuote: String
}

extension PartAvailability: Identifiable {
    var id: String {
        partNumber
    }
}
