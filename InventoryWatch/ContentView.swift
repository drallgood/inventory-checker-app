//
//  ContentView.swift
//  InventoryWatch
//
//  Created by Worth Baker on 11/8/21.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: ViewModel
    
    @AppStorage("lastUpdateDate") private var lastUpdateDate: String = ""
    @AppStorage("preferredProductType") private var preferredProductType: String = ProductFamily.iphone.rawValue
    @AppStorage("preferredWatchToken") private var preferredWatchToken: String = ""
    @AppStorage("preferredPhoneToken") private var preferredPhoneToken: String = ""
    @AppStorage("preferredMacToken") private var preferredMacToken: String = ""
    @AppStorage("useLargeText") private var useLargeText: Bool = false
    @AppStorage("shouldIncludeNearbyStores") private var shouldIncludeNearbyStores: Bool = true

    
    private var onlyShowingPreferredResults: Bool {
        return UserDefaults.standard.bool(forKey: "showResultsOnlyForPreferredModels")
    }

@MainActor
private func displayNameForPhoneToken(token: String, country: Country) -> String? {
    // Prefer explicit JSON-provided token display if available
    if let explicit = JSONCatalogiPhone.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
        return explicit
    }
    // Derive name from JSON metadata; fall back to prettified token
    var baseName: String = "iPhone"
    if let dict = JSONCatalogiPhone.categoryData(for: country, sourcePage: token),
       let md = dict.values.first {
        if let famName = md.familyName, famName.isEmpty == false, famName.lowercased() != "unknown" {
            baseName = famName
        } else if md.family.isEmpty == false {
            baseName = md.family.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    if baseName.lowercased() == "iphone" { baseName = "iPhone" }
    var variant = ""
    if token.hasPrefix("iphone-") {
        let suffix = String(token.dropFirst("iphone-".count))
        if suffix.isEmpty == false {
            variant = suffix.replacingOccurrences(of: "-", with: " ").capitalized
        }
    }
    return variant.isEmpty ? baseName : "\(baseName) \(variant)"
}
    
    var body: some View {
        VStack {
            HStack {
                ZStack {
                    if model.hasLatestVersion == false {
                        Text("!")
                            .bold().foregroundColor(.blue)
                            .offset(x: 8, y: -8)
                    }
                    if #available(macOS 14, *) {
                    SettingsLink {
                        Image(systemName: "gearshape.fill")
                    }
                    .padding()
                    } else {
                        Button(
                            action: {
                                if #available(macOS 13, *) {
                                    NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
                                } else {
                                    NSApp.sendAction(Selector(("showPreferencesWindow:")), to: nil, from: nil)
                                }
                            },
                            label: { Image(systemName: "gearshape.fill") }
                        )
                        .buttonStyle(BorderlessButtonStyle())
                        .padding()
                    }
                }
                
                Spacer()
                
                VStack {
                    let font = useLargeText ? Font.largeTitle : Font.title2
                    let country = model.defaultsVendor.preferredCountry
                    let family = ProductFamily(rawValue: preferredProductType)
                    if let fam = family, fam.isWatch, !preferredWatchToken.isEmpty,
                       let tokenName = displayNameForWatchToken(token: preferredWatchToken, country: country) {
                        Text("Available \(Text(tokenName).font(font).fontWeight(.heavy)) Models")
                            .font(font)
                            .fontWeight(.semibold)
                    } else if let fam = family, fam.isIPhone, !preferredPhoneToken.isEmpty,
                              let tokenName = displayNameForPhoneToken(token: preferredPhoneToken, country: country) {
                        Text("Available \(Text(tokenName).font(font).fontWeight(.heavy)) Models")
                            .font(font)
                            .fontWeight(.semibold)
                    } else if family != nil {
                        Text("Available Models")
                            .font(font)
                            .fontWeight(.semibold)
                    } else {
                        Text("Available Models")
                            .font(font)
                            .fontWeight(.semibold)
                    }
                    
                    
                    if let preferredStoreName = model.preferredStoreName {
                        Text("\(shouldIncludeNearbyStores ? "near" : "at") \(preferredStoreName)")
                            .font(.title2)
                    }
                }
                
                Spacer()
                
                ProgressView()
                    .progressViewStyle(CircularProgressViewStyle())
                    .opacity(model.isLoading ? 1.0 : 0.0)
                    .scaleEffect(0.5, anchor: .center)
                    .padding(.top, 8)
                
            }
            
            ZStack(alignment:.center) {
                
                
                List {
                    if let error = model.errorState {
                        Text(error.errorMessage)
                            .font(.subheadline)
                            .italic()
                    }

                    let productFont = useLargeText ? Font.title.weight(.medium) : Font.body.weight(.medium)
                    let country = model.defaultsVendor.preferredCountry
                    let preferred = model.defaultsVendor.preferredProductFamily

                    // Render only the selected Apple Watch model token (Settings -> Watch Model)
                    if preferred.isWatch {
                        // Build availability set from current inventory (any store)
                        let availableSkus: Set<String> = Set(model.availableParts.flatMap { $0.1.map { $0.partNumber } })
                        // Build per-SKU pickup availability details (store count and a sample quote)
                        let pickupInfo: [String: (count: Int, quote: String?)] = model.availableParts.reduce(into: [:]) { (acc: inout [String: (count: Int, quote: String?)], entry) in
                            let parts = entry.1
                            parts.forEach { part in
                                guard part.availability == .available else { return }
                                let current = acc[part.partNumber] ?? (0, nil)
                                let newCount = current.count + 1
                                let quote = current.quote ?? part.availabilityStorePickupQuote
                                acc[part.partNumber] = (newCount, quote)
                            }
                        }
                        // Preferred SKUs from Settings
                        let preferredSkus = Set((UserDefaults.standard.string(forKey: "preferredSKUs") ?? "").split(separator: ",").map { String($0) }.filter { !$0.isEmpty })
                        // Token from Settings
                        let token = preferredWatchToken
                        if token.isEmpty {
                            Text("Select a Watch Model in Settings.")
                                .foregroundColor(.secondary)
                        } else if let data = SKUDataLoader().watchSKUData(forToken: token, country: country) {
                            // Filter SKUs: only those with availability AND (if preferred list set) present in preferred SKUs
                            let filtered = data.orderedSKUs.filter { sku in
                                let isAvailable = availableSkus.contains(sku)
                                if preferredSkus.isEmpty { return isAvailable }
                                return isAvailable && preferredSkus.contains(sku)
                            }
                            if filtered.isEmpty {
                                Text("No models available in-store.")
                                    .foregroundColor(.secondary)
                            } else {
                                ForEach(filtered, id: \.self) { partNumber in
                                    let name = data.productName(forSKU: partNumber) ?? partNumber
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(name)
                                                .font(productFont)
                                            Spacer()
                                        }
                                        // PDP URL preview (resolved from JSON)
                                        if let preview = SKUDataLoader().watchProductURL(for: partNumber, country: country)?.absoluteString {
                                            Text(preview)
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.secondary)
                                                .textSelection(.enabled)
                                        }
                                        // Pickup availability (aggregated across stores)
                                        if let info = pickupInfo[partNumber] {
                                            let countText = info.count == 1 ? "1 store" : "\(info.count) stores"
                                            let quoteText = info.quote ?? "Available for pickup"
                                            Text("Pickup: \(quoteText) • \(countText)")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.green)
                                        } else {
                                            Text("Pickup: Unavailable")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.secondary)
                                        }
                                        Button(action: {
                                            Task {
                                                if let url = SKUDataLoader().watchProductURL(for: partNumber, country: country) {
                                                    NSWorkspace.shared.open(url)
                                                    return
                                                }
                                                // Fallback: token/category-level buy page URL from our JSON catalogs
                                                // (e.g. /shop/buy-watch/apple-watch-ultra). Avoid hardcoded product URLs.
                                                if let url = SKUDataLoader().watchCategoryURL(for: country, sourcePage: token) {
                                                    NSWorkspace.shared.open(url)
                                                    return
                                                }

                                                print("⚠️ Could not resolve watch order URL for sku=\(partNumber), token=\(token)")
                                            }
                                        }) {
                                            Text("Order Online")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.blue)
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                    }
                                    .padding(.vertical, 2)
                                }
                            }
                        } else {
                            Text("No SKUs available")
                                .foregroundColor(.secondary)
                        }
                    } else if preferred.isIPhone {
                        // iPhone tokenized rendering
                        // Build availability set from current inventory (any store)
                        let availableSkus: Set<String> = Set(model.availableParts.flatMap { $0.1.map { $0.partNumber } })
                        // Build per-SKU pickup availability details (store count and a sample quote)
                        let pickupInfo: [String: (count: Int, quote: String?)] = model.availableParts.reduce(into: [:]) { (acc: inout [String: (count: Int, quote: String?)], entry) in
                            let parts = entry.1
                            parts.forEach { part in
                                guard part.availability == .available else { return }
                                let current = acc[part.partNumber] ?? (0, nil)
                                let newCount = current.count + 1
                                let quote = current.quote ?? part.availabilityStorePickupQuote
                                acc[part.partNumber] = (newCount, quote)
                            }
                        }
                        // Preferred SKUs from Settings
                        let preferredSkus = Set((UserDefaults.standard.string(forKey: "preferredSKUs") ?? "").split(separator: ",").map { String($0) }.filter { !$0.isEmpty })
                        // Token from Settings
                        let token = preferredPhoneToken
                        if token.isEmpty {
                            Text("Select a Phone Model in Settings.")
                                .foregroundColor(.secondary)
                        } else if let data = SKUDataLoader().phoneSKUData(forToken: token, country: country) {
                            let filtered = data.orderedSKUs.filter { sku in
                                let isAvailable = availableSkus.contains(sku)
                                if preferredSkus.isEmpty { return isAvailable }
                                return isAvailable && preferredSkus.contains(sku)
                            }
                            if filtered.isEmpty {
                                Text("No models available in-store.")
                                    .foregroundColor(.secondary)
                            } else {
                                ForEach(filtered, id: \.self) { partNumber in
                                    let name = data.productName(forSKU: partNumber) ?? partNumber
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(name)
                                                .font(productFont)
                                            Spacer()
                                        }
                                        // PDP URL preview (resolved from JSON)
                                        if let preview = SKUDataLoader().phoneProductURL(for: partNumber, country: country)?.absoluteString {
                                            Text(preview)
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.secondary)
                                                .textSelection(.enabled)
                                        }
                                        // Pickup availability (aggregated across stores)
                                        if let info = pickupInfo[partNumber] {
                                            let countText = info.count == 1 ? "1 store" : "\(info.count) stores"
                                            let quoteText = info.quote ?? "Available for pickup"
                                            Text("Pickup: \(quoteText) • \(countText)")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.green)
                                        } else {
                                            Text("Pickup: Unavailable")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.secondary)
                                        }
                                        Button(action: {
                                            // Prefer per-SKU PDP URL, fallback to token base derived from scraped JSON
                                            if let url = SKUDataLoader().phoneProductURL(for: partNumber, country: country) {
                                                NSWorkspace.shared.open(url)
                                            } else if let base = SKUDataLoader().phonePDPBaseURL(for: country, sourcePage: token) {
                                                NSWorkspace.shared.open(base)
                                            }
                                        }) {
                                            Text("Order Online")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.blue)
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                    }
                                    .padding(.vertical, 2)
                                }
                            }
                        } else {
                            Text("No SKUs available")
                                .foregroundColor(.secondary)
                        }
                    } else if preferred.isMac {
                        // Mac tokenized rendering
                        let availableSkus: Set<String> = Set(model.availableParts.flatMap { $0.1.map { $0.partNumber } })
                        let pickupInfo: [String: (count: Int, quote: String?)] = model.availableParts.reduce(into: [:]) { (acc: inout [String: (count: Int, quote: String?)], entry) in
                            let parts = entry.1
                            parts.forEach { part in
                                guard part.availability == .available else { return }
                                let current = acc[part.partNumber] ?? (0, nil)
                                let newCount = current.count + 1
                                let quote = current.quote ?? part.availabilityStorePickupQuote
                                acc[part.partNumber] = (newCount, quote)
                            }
                        }
                        let preferredSkus = Set((UserDefaults.standard.string(forKey: "preferredSKUs") ?? "").split(separator: ",").map { String($0) }.filter { !$0.isEmpty })
                        let token = preferredMacToken
                        if token.isEmpty {
                            Text("Select a Mac Model in Settings.")
                                .foregroundColor(.secondary)
                        } else if let data = SKUDataLoader().macSKUData(forToken: token, country: country) {
                            let filtered = data.orderedSKUs.filter { sku in
                                let isAvailable = availableSkus.contains(sku)
                                if preferredSkus.isEmpty { return isAvailable }
                                return isAvailable && preferredSkus.contains(sku)
                            }
                            if filtered.isEmpty {
                                Text("No models available in-store.")
                                    .foregroundColor(.secondary)
                            } else {
                                ForEach(filtered, id: \.self) { partNumber in
                                    let name = data.productName(forSKU: partNumber) ?? partNumber
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(name)
                                                .font(productFont)
                                            Spacer()
                                        }
                                        if let info = pickupInfo[partNumber] {
                                            let countText = info.count == 1 ? "1 store" : "\(info.count) stores"
                                            let quoteText = info.quote ?? "Available for pickup"
                                            Text("Pickup: \(quoteText) • \(countText)")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.green)
                                        } else {
                                            Text("Pickup: Unavailable")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.secondary)
                                        }
                                        Button(action: {
                                            // Mac catalogs currently provide token-level buy URLs.
                                            if let url = JSONCatalogMac.pdpBaseURL(for: country, sourcePage: token) {
                                                NSWorkspace.shared.open(url)
                                            }
                                        }) {
                                            Text("Order Online")
                                                .font(useLargeText ? .caption : .caption2)
                                                .foregroundColor(.blue)
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                    }
                                    .padding(.vertical, 2)
                                }
                            }
                        } else {
                            Text("No SKUs available")
                                .foregroundColor(.secondary)
                        }
                    } else {
                        // Non-tokenized categories
                        if model.availableParts.isEmpty && model.isLoading == false {
                            Text("No models available in-store.")
                                .foregroundColor(.secondary)
                        }
                    }
                }
                
                // Hide legacy inventory empty-state for Apple Watch JSON-driven UI
                let preferred = model.defaultsVendor.preferredProductFamily
                if preferred.isWatch == false {
                    if model.availableParts.isEmpty && model.isLoading == false {
                        Text("No models available in-store.")
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            HStack {
                let font = useLargeText ? Font.title3 : Font.caption
                
                if onlyShowingPreferredResults {
                    Text("Only showing results for preferred models.")
                        .font(font)
                        .padding(.leading, 8)
                }
                
                Spacer()
                
                if lastUpdateDate.isEmpty == false {
                    Text("Last update at \(lastUpdateDate)")
                        .font(font)
                } else {
                    Text("")
                        .font(font)
                }
                
                Button(
                    action: { Task { await model.fetchLatestInventory() } },
                    label: { Image(systemName: "arrow.clockwise") }
                )
                    .buttonStyle(BorderlessButtonStyle())
                    .keyboardShortcut("r", modifiers: .command)
                    .padding(.trailing, 8)
            }
            .padding(.bottom, 8)
            
        }
        .frame(
            minWidth: 500,
            maxWidth: .infinity,
            minHeight: 300,
            maxHeight: .infinity,
            alignment: .center
        )
        .onAppear {
            Task {
                await model.fetchLatestInventory()
                NotificationManager.shared.requestNotificationPermissions()
            }
        }
    }
}

@MainActor
private func displayNameForWatchToken(token: String, country: Country) -> String? {
    // Derive name purely from JSON metadata; avoid any hardcoded configuration
    if let dict = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: token),
       let md = dict.values.first {
        var baseName: String? = nil
        if let famName = md.familyName, famName.isEmpty == false {
            baseName = famName
        } else {
            let fam = md.family
            if fam == "apple_watch" { baseName = "Apple Watch" }
            else if fam.isEmpty == false { baseName = fam.replacingOccurrences(of: "_", with: " ").capitalized }
        }
        var variant: String? = nil
        if token.hasPrefix("apple-watch-") {
            let suffix = String(token.dropFirst("apple-watch-".count))
            if suffix.isEmpty == false {
                variant = (suffix.lowercased() == "se") ? "SE" : suffix.replacingOccurrences(of: "-", with: " ").capitalized
            }
        }
        if let base = baseName { return variant != nil ? "\(base) \(variant!)" : base }
    }
    // Last resort, prettify token
    return token.replacingOccurrences(of: "-", with: " ").capitalized
}

//struct ContentView_Previews: PreviewProvider {
//    static var previews: some View {
//        ContentView()
//            .environmentObject(Model.testData)
//    }
//}
