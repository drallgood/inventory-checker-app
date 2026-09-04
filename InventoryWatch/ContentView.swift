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
    @AppStorage("preferrediPadToken") private var preferrediPadToken: String = ""
    @AppStorage("useLargeText") private var useLargeText: Bool = false
    @AppStorage("shouldIncludeNearbyStores") private var shouldIncludeNearbyStores: Bool = true
    
    private var onlyShowingPreferredResults: Bool {
        return UserDefaults.standard.bool(forKey: "showResultsOnlyForPreferredModels")
    }

@MainActor
private func displayNameForPhoneToken(token: String, country: Country) -> String? {
    if let explicit = JSONCatalogiPhone.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
        return explicit
    }
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

@MainActor
private func displayNameForMacToken(token: String, country: Country) -> String? {
    if let explicit = JSONCatalogMac.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
        return explicit
    }
    return token.replacingOccurrences(of: "-", with: " ").capitalized
}

@MainActor
private func displayNameForiPadToken(token: String, country: Country) -> String? {
    if let explicit = JSONCatalogiPad.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
        return explicit
    }
    return token.replacingOccurrences(of: "-", with: " ").capitalized
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
                    } else if let fam = family, fam.isMac, !preferredMacToken.isEmpty,
                              let tokenName = displayNameForMacToken(token: preferredMacToken, country: country) {
                        Text("Available \(Text(tokenName).font(font).fontWeight(.heavy)) Models")
                            .font(font)
                            .fontWeight(.semibold)
                    } else if let fam = family, fam.isIPad, !preferrediPadToken.isEmpty,
                              let tokenName = displayNameForiPadToken(token: preferrediPadToken, country: country) {
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

                    let country = model.defaultsVendor.preferredCountry
                    let preferred = model.defaultsVendor.preferredProductFamily

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

                    if preferred.isWatch {
                        ProductAvailabilityList(
                            country: country,
                            token: preferredWatchToken,
                            emptyTokenMessage: "Select a Watch Model in Settings.",
                            skuData: SKUDataLoader().watchSKUData(forToken: preferredWatchToken, country: country),
                            availableSkus: availableSkus,
                            pickupInfo: pickupInfo,
                            preferredSKUs: preferredSkus,
                            productURL: { SKUDataLoader().watchProductURL(for: $0, country: country) },
                            categoryURL: { SKUDataLoader().watchCategoryURL(for: country, sourcePage: preferredWatchToken) },
                            showPDPPreview: true
                        )
                    } else if preferred.isIPhone {
                        ProductAvailabilityList(
                            country: country,
                            token: preferredPhoneToken,
                            emptyTokenMessage: "Select a Phone Model in Settings.",
                            skuData: SKUDataLoader().phoneSKUData(forToken: preferredPhoneToken, country: country),
                            availableSkus: availableSkus,
                            pickupInfo: pickupInfo,
                            preferredSKUs: preferredSkus,
                            productURL: { SKUDataLoader().phoneProductURL(for: $0, country: country) },
                            categoryURL: { SKUDataLoader().phonePDPBaseURL(for: country, sourcePage: preferredPhoneToken) },
                            showPDPPreview: true
                        )
                    } else if preferred.isMac {
                        ProductAvailabilityList(
                            country: country,
                            token: preferredMacToken,
                            emptyTokenMessage: "Select a Mac Model in Settings.",
                            skuData: SKUDataLoader().macSKUData(forToken: preferredMacToken, country: country),
                            availableSkus: availableSkus,
                            pickupInfo: pickupInfo,
                            preferredSKUs: preferredSkus,
                            productURL: { _ in nil },
                            categoryURL: { JSONCatalogMac.pdpBaseURL(for: country, sourcePage: preferredMacToken) },
                            showPDPPreview: false
                        )
                    } else if preferred.isIPad {
                        ProductAvailabilityList(
                            country: country,
                            token: preferrediPadToken,
                            emptyTokenMessage: "Select an iPad Model in Settings.",
                            skuData: SKUDataLoader().ipadSKUData(forToken: preferrediPadToken, country: country),
                            availableSkus: availableSkus,
                            pickupInfo: pickupInfo,
                            preferredSKUs: preferredSkus,
                            productURL: { _ in nil },
                            categoryURL: { JSONCatalogiPad.pdpBaseURL(for: country, sourcePage: preferrediPadToken) },
                            showPDPPreview: false
                        )
                    } else {
                        if model.availableParts.isEmpty && model.isLoading == false {
                            Text("No models available in-store.")
                                .foregroundColor(.secondary)
                        }
                    }
                }
                
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
    return token.replacingOccurrences(of: "-", with: " ").capitalized
}