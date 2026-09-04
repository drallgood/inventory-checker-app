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
        let title = await generateNotificationTitle(hasPreferredModel: hasPreferredModel, availableParts: availableParts, skuData: skuData)
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
        
        let family = DefaultsVendor().preferredProductFamily
        let topModels = sortedModels.prefix(3).map { (part, count) in
            var shortName = part.partName
            let prefix = "\(family.displayName) "
            if shortName.hasPrefix(prefix) {
                shortName = String(shortName.dropFirst(prefix.count))
            }
            return "\(shortName) (×\(count))"
        }
        
        let storeText = storeCount == 1 ? "1 store" : "\(storeCount) stores"
        let modelText = modelCount > 3 ? "& \(modelCount - 3) more" : ""
        
        let message = "\(topModels.joined(separator: ", ")) \(modelText) • Available at \(storeText)"
        return message.trimmingCharacters(in: .whitespaces)
    }
    
    private func generateNotificationTitle(hasPreferredModel: Bool, availableParts: [(FulfillmentStore, [PartAvailability])], skuData: SKUData) async -> String {
        let totalModels = availableParts.reduce(0) { total, storeParts in
            total + storeParts.1.count
        }
        
        // Determine product type from active family
        let productName = await getProductName(from: skuData)
        let productEmoji = getProductEmojiFromSKUData(skuData)
        
        if hasPreferredModel {
            let emojis = ["🎉", "✨", "🔥", "⚡️", "🚀"]
            let randomEmoji = emojis.randomElement() ?? "🎉"
            return "\(randomEmoji) Your \(productName) is Available!"
        } else if totalModels > 10 {
            return "\(productEmoji) Lots of \(productName) Models Available"
        } else if totalModels > 0 {
            return "\(productEmoji) \(productName) Inventory Update"
        } else {
            return "\(productEmoji) Inventory Check Complete"
        }
    }
    
    private func getProductName(from skuData: SKUData) async -> String {
        // Respect the active product family for notification labeling
        let defaults = DefaultsVendor()
        let family = defaults.preferredProductFamily
        if family.isWatch {
            // If a Watch token is selected, derive the base display name from JSON (family/familyName + token variant)
            let token = defaults.preferredWatchToken
            if token.isEmpty == false {
                let country = defaults.preferredCountry
                if let display = await displayNameForWatchToken(token: token, country: country) {
                    return display
                }
            }
            return "Apple Watch"
        }
        if family.isIPhone {
            return "iPhone"
        }
        if family.isMac {
            return "Mac"
        }
        if family.isIPad {
            // If an iPad token is selected, derive display name from JSON
            let token = defaults.preferrediPadToken
            if token.isEmpty == false {
                let country = defaults.preferredCountry
                if let display = await displayNameForiPadToken(token: token, country: country) {
                    return display
                }
            }
            return "iPad"
        }
        // Fallback: infer from SKU names (should not typically be reached)
        for sku in skuData.orderedSKUs {
            if let productName = skuData.productName(forSKU: sku) {
                let n = productName.lowercased()
                if n.contains("iphone") { return "iPhone" }
                if n.contains("apple watch") || n.contains("watch") { return "Apple Watch" }
            }
        }
        return "iPhone"
    }

    private func displayNameForWatchToken(token: String, country: Country) async -> String? {
        // MainActor for JSONCatalogAppleWatch access
        return await MainActor.run {
            guard let dict = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: token), let md = dict.values.first else { return nil }
            // Base name from familyName or family
            var baseName: String? = nil
            if let famName = md.familyName, famName.isEmpty == false {
                baseName = famName
            } else {
                let fam = md.family
                if fam == "apple_watch" {
                    baseName = "Apple Watch"
                } else if fam.isEmpty == false {
                    baseName = fam.replacingOccurrences(of: "_", with: " ").capitalized
                }
            }
            // Variant from token suffix
            var variant: String? = nil
            if token.hasPrefix("apple-watch-") {
                let suffix = String(token.dropFirst("apple-watch-".count))
                if suffix.isEmpty == false {
                    variant = (suffix.lowercased() == "se") ? "SE" : suffix.replacingOccurrences(of: "-", with: " ").capitalized
                }
            }
            if let base = baseName { return variant != nil ? "\(base) \(variant!)" : base }
            return nil
        }
    }

    private func displayNameForiPadToken(token: String, country: Country) async -> String? {
        return await MainActor.run {
            guard let dict = JSONCatalogiPad.categoryData(for: country, sourcePage: token), let md = dict.values.first else { return nil }
            if let famName = md.familyName, famName.isEmpty == false, famName.lowercased() != "unknown" {
                return famName
            }
            if md.family.isEmpty == false {
                return md.family.replacingOccurrences(of: "_", with: " ").capitalized
            }
            return token.replacingOccurrences(of: "-", with: " ").capitalized
        }
    }
    
    private func getProductEmojiFromSKUData(_ skuData: SKUData) -> String {
        // Emoji should reflect the active product family
        let family = DefaultsVendor().preferredProductFamily
        if family.isWatch { return "⌚️" }
        if family.isIPhone { return "📱" }
        if family.isMac { return "💻" }
        if family.isIPad { return "📱" }
        return "📱"
    }
    
}
