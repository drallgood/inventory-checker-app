//
//  NotificationSender.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/27/22.
//

import Foundation

struct NotificationSender {
    
    private let defaultsVendor = DefaultsVendor()
    
    func sendNotificationIfNeeded(availableParts: [(FulfillmentStore, [PartAvailability])], skuData: SKUData) async {
        var hasPreferredModel = false
        let preferredModels = defaultsVendor.preferredSKUs
        for model in availableParts {
            for submodel in model.1 {
                if hasPreferredModel == false && preferredModels.contains(submodel.partNumber) {
                    hasPreferredModel = true
                    break
                }
                
                if hasPreferredModel == false, let customSku = defaultsVendor.customSkuData?.sku, submodel.partNumber == customSku {
                    hasPreferredModel = true
                    break
                }
            }
        }
        
        if defaultsVendor.notifyOnlyForPreferredModels && !hasPreferredModel {
            return
        }
        
        let message = self.generateNotificationText(from: availableParts, skuData: skuData, preferredModels: preferredModels)
        let title = generateNotificationTitle(hasPreferredModel: hasPreferredModel, availableParts: availableParts)
        await NotificationManager.shared.sendNotification(title: title, body: message)
    }
    
    private func generateNotificationText(from data: [(FulfillmentStore, [PartAvailability])], skuData: SKUData, preferredModels: Set<String>) -> String {
        guard data.isEmpty == false else {
            return "No inventory currently available at nearby stores"
        }
        
        let customSkuData = defaultsVendor.customSkuData
        let filterForPreferredModels = defaultsVendor.notifyOnlyForPreferredModels
        
        var collector: [PartAvailability: Int] = [:]
        var storeNames: Set<String> = []
        
        for (store, parts) in data {
            storeNames.insert(store.storeName)
            for part in parts {
                let shouldInclude = part.partNumber == customSkuData?.sku || 
                                 (filterForPreferredModels && preferredModels.contains(part.partNumber)) ||
                                 !filterForPreferredModels
                
                if shouldInclude {
                    collector[part, default: 0] += 1
                }
            }
        }
        
        let sortedModels = collector.sorted { $0.value > $1.value }
        let modelCount = sortedModels.count
        let storeCount = storeNames.count
        
        if modelCount == 0 {
            return "No preferred models available at this time"
        }
        
        let topModels = sortedModels.prefix(3).map { (part, count) in
            let shortName = part.partName
                .replacingOccurrences(of: "iPhone ", with: "")
                .replacingOccurrences(of: " Pro Max", with: " Pro Max")
            return "\(shortName) (×\(count))"
        }
        
        let storeText = storeCount == 1 ? "1 store" : "\(storeCount) stores"
        let modelText = modelCount > 3 ? "& \(modelCount - 3) more" : ""
        
        let message = "\(topModels.joined(separator: ", ")) \(modelText) • Available at \(storeText)"
        return message.trimmingCharacters(in: .whitespaces)
    }
    
    private func generateNotificationTitle(hasPreferredModel: Bool, availableParts: [(FulfillmentStore, [PartAvailability])]) -> String {
        let totalModels = availableParts.reduce(0) { total, storeParts in
            total + storeParts.1.count
        }
        
        if hasPreferredModel {
            let emojis = ["🎉", "✨", "🔥", "⚡️", "🚀"]
            let randomEmoji = emojis.randomElement() ?? "🎉"
            return "\(randomEmoji) Your iPhone is Available!"
        } else if totalModels > 10 {
            return "📱 Lots of iPhone Models Available"
        } else if totalModels > 0 {
            return "📱 iPhone Inventory Update"
        } else {
            return "📱 Inventory Check Complete"
        }
    }
    
}
