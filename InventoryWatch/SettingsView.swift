//
//  SettingsView.swift
//  InventoryWatch
//
//  Created by Worth Baker on 11/9/21.
//

import SwiftUI

struct SettingsView: View {
    
    
    private struct ProductModel: Identifiable, Equatable {
        let sku: String
        var name: String
        var isFavorite: Bool
        
        var id: String { sku }
    }
    
    private struct StoreWithSelection: Identifiable, Equatable {
        var store: RetailStore
        var isSelected: Bool
        
        var id: String { storeNumber }
        var storeNumber: String { store.id }
        var storeName: String { store.name }
        var city: String { store.address.city }
        
        var stateName: String? { store.address.stateName }
        var stateCode: String? { store.address.stateCode }
    }
    
    @EnvironmentObject var model: ViewModel
    @Environment(\.openURL) var openURL
    
    @AppStorage("preferredCountry") private var preferredCountry = "US"
    @AppStorage("preferredStoreNumber") private var preferredStoreNumber = ""
    @AppStorage("preferredSKUs") private var preferredSKUs: String = ""
    @AppStorage("preferredUpdateInterval") private var preferredUpdateInterval: Int = 1
    @AppStorage("preferredProductType") private var preferredProductType: String = ProductFamily.iphone.rawValue
    @AppStorage("preferredWatchToken") private var preferredWatchToken: String = ""
    @AppStorage("preferredPhoneToken") private var preferredPhoneToken: String = ""
    @AppStorage("preferredMacToken") private var preferredMacToken: String = ""
    @AppStorage("notifyOnlyForPreferredModels") private var notifyOnlyForPreferredModels: Bool = false
    @AppStorage("showResultsOnlyForPreferredModels") private var showResultsOnlyForPreferredModels: Bool = false
    @AppStorage("customSku") private var customSku = ""
    @AppStorage("customSkuNickname") private var customSkuNickname = ""
    @AppStorage("useLargeText") private var useLargeText: Bool = false
    @AppStorage("shouldIncludeNearbyStores") private var shouldIncludeNearbyStores: Bool = true
    
    @State private var selectedCountryIndex = 0
    @State private var allModels: [ProductModel] = []
    @State private var allStores: [StoreWithSelection] = []
    @State private var storeSearchText: String = ""
    @State private var selectedStore: String = ""
    @State private var availableWatchTokens: [String] = []
    @State private var availablePhoneTokens: [String] = []
    @State private var availableMacTokens: [String] = []
    @State private var watchTokenNames: [String: String] = [:]
    @State private var phoneTokenNames: [String: String] = [:]
    @State private var macTokenNames: [String: String] = [:]
    
    var body: some View {
        VStack(alignment: .leading) {
            if model.pickupErrorKeys.isEmpty == false {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text("Apple pickup API warning: \(model.pickupErrorKeys.joined(separator: ", "))")
                }
                .foregroundColor(.orange)
                .padding(.bottom, 6)
            }
            topControls
            modelsAndStores
                .padding(.top, 8)
        }
        .padding()
        .frame(
            minWidth: 500,
            maxWidth: .infinity,
            minHeight: 600,
            maxHeight: .infinity,
            alignment: .center
        )
        .onAppear { onAppearSetup() }
        .onChange(of: selectedCountryIndex) { newValue in handleSelectedCountryIndexChange(newValue) }
        .onChange(of: allModels) { models in handleAllModelsChange(models) }
        .onChange(of: storeSearchText) { newText in handleStoreSearchTextChange(newText) }
        .onChange(of: allStores) { newStores in handleAllStoresChange(newStores) }
        .onChange(of: preferredProductType) { newType in handlePreferredProductTypeChange(newType) }
        .onChange(of: preferredStoreNumber) { _ in handlePreferredStoreNumberChange() }
        .onChange(of: preferredUpdateInterval) { _ in handlePreferredUpdateIntervalChange() }
        .onChange(of: preferredCountry) { _ in handlePreferredCountryChange() }
        .onChange(of: showResultsOnlyForPreferredModels) { _ in handleReloadInventory() }
        .onChange(of: shouldIncludeNearbyStores) { _ in handleReloadInventory() }
        .onChange(of: preferredWatchToken) { _ in handlePreferredWatchTokenChange() }
        .onChange(of: preferredPhoneToken) { _ in handlePreferredPhoneTokenChange() }
        .onChange(of: preferredMacToken) { _ in handlePreferredMacTokenChange() }
    }

    // Break complex views into smaller computed blocks to assist the type-checker
    @ViewBuilder private var topControls: some View {
        HStack(alignment: .top, spacing: 24) {
            leftControlsView
                .fixedSize()
                .padding(.leading, 8)
                .padding(.bottom, 8)
            rightControlsView
        }
    }

    @ViewBuilder private var modelsAndStores: some View {
        HStack {
            preferredModelsList
            preferredStoreList
        }
    }

    // MARK: - Extracted subviews
    @ViewBuilder private var leftControlsView: some View {
        VStack(alignment: .leading) {
            countryPickerView
            productOrWatchPickerView

            Picker("Update every", selection: $preferredUpdateInterval) {
                Text("Never").tag(0)
                Text("1 minute").tag(1)
                Text("5 minutes").tag(5)
                Text("30 minutes").tag(30)
                Text("60 minutes").tag(60)
            }
            
            Toggle(isOn: $notifyOnlyForPreferredModels) {
                Text("Notify only for preferred models")
                    .padding(.leading, 4)
            }
            Toggle(isOn: $showResultsOnlyForPreferredModels) {
                Text("Only show results for preferred models")
                    .padding(.leading, 4)
            }
        }
    }

    @ViewBuilder private var rightControlsView: some View {
        VStack(alignment: .leading) {
            HStack(alignment: .top) {
                Text("Custom SKU")
                VStack {
                    TextField("Enter a custom SKU", text: $customSku)
                    TextField("Custom SKU Nickname", text: $customSkuNickname)
                }
            }
            
            Toggle(isOn: $useLargeText) {
                Text("Use larger text sizes")
            }
            
            Toggle(isOn: $shouldIncludeNearbyStores) {
                Text("Include results from nearby stores")
            }
            
            if model.hasLatestVersion == false {
                Link(destination: URL(string: "https://worthbak.github.io/inventory-checker-app/")!) {
                    HStack(spacing: 4) {
                        Text("A new version of InventoryWatch is available - click here to download.")
                        Image(systemName: "arrow.forward.circle")
                    }
                    .font(.headline)
                }
                .padding(.top, 16)
            }
        }
    }

    @ViewBuilder private var preferredModelsList: some View {
        VStack(alignment: .leading) {
            Text("Preferred Model(s)")
                .font(.headline)
            
            Text("Only certain model configurations are stocked in-stores. If you believe a configuration is missing, [please open an issue](https://github.com/worthbak/inventory-checker-app/issues).")
                .font(.caption).italic()
            
            List {
                ForEach($allModels) { model in
                    Toggle(isOn: model.isFavorite) {
                        Text(model.name.wrappedValue)
                            .padding(.leading, 4)
                    }
                }
            }
        }
    }

    @ViewBuilder private var preferredStoreList: some View {
        VStack(alignment: .leading) {
            Text("Preferred Store")
                .font(.headline)
            
            TextField("Filter by store name, city, state, or province", text: $storeSearchText)
                .padding(.top, -5)
            
            List {
                ForEach($allStores) { store in
                    Toggle(isOn: store.isSelected) {
                        let wrapped = store.wrappedValue
                        Text("\(Text(wrapped.storeName).bold()) - \(wrapped.store.address.cityStateDisplay)")
                            .padding(.leading, 4)
                    }
                }
            }
        }
    }

    @ViewBuilder private var countryPickerView: some View {
        Picker("Country", selection: $selectedCountryIndex) {
            ForEach(0..<OrderedCountries.count, id: \.self) { index in
                let countryCode = OrderedCountries[index]
                let country = Countries[countryCode]
                Text(country?.name ?? countryCode)
            }
        }
    }

    @ViewBuilder private var productOrWatchPickerView: some View {
        let isWatch: Bool = {
            guard let fam = ProductFamily(rawValue: preferredProductType) else { return false }
            return fam.isWatch
        }()
        let isPhone: Bool = {
            guard let fam = ProductFamily(rawValue: preferredProductType) else { return false }
            return fam.isIPhone
        }()
        let isMac: Bool = {
            guard let fam = ProductFamily(rawValue: preferredProductType) else { return false }
            return fam.isMac
        }()
        // Dropdown to switch between product families
        Picker("Product Type", selection: $preferredProductType) {
            Text("Apple Watch").tag(ProductFamily.watch.rawValue)
            Text("iPhone").tag(ProductFamily.iphone.rawValue)
            Text("Mac").tag(ProductFamily.mac.rawValue)
        }
        .pickerStyle(.menu)
        .frame(minWidth: 260)
        
        if isWatch {
            Picker("Watch Model", selection: $preferredWatchToken) {
                ForEach(availableWatchTokens, id: \.self) { token in
                    Text(displayName(forToken: token)).tag(token)
                }
            }
        } else if isPhone {
            // Selected token display name beside the picker label
            let selectedDisplayName: String = {
                return phoneTokenNames[preferredPhoneToken] ?? preferredPhoneToken
            }()
            HStack {
                Text("Phone Model")
                Spacer()
                Text(selectedDisplayName).foregroundColor(.secondary)
            }
            // PDP base preview resolved from scraped JSON
            if let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()] {
                let pdpBase = SKUDataLoader().phonePDPBaseURL(for: country, sourcePage: preferredPhoneToken)
                HStack(spacing: 8) {
                    Text("PDP Base")
                    Spacer()
                    Text(pdpBase?.absoluteString ?? "—")
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Picker("", selection: $preferredPhoneToken) {
                ForEach(availablePhoneTokens, id: \.self) { token in
                    Text(phoneTokenNames[token] ?? token).tag(token)
                }
            }
            .id("phonepicker-\(preferredCountry)-\(preferredProductType)-\(availablePhoneTokens.joined(separator: ","))")
            .pickerStyle(.menu)
            .frame(minWidth: 260) // help AppKit menu measure and update reliably
        } else if isMac {
            let selectedMacDisplayName: String = {
                if let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()],
                   preferredMacToken.isEmpty == false,
                   let name = JSONCatalogMac.tokenDisplayName(for: country, sourcePage: preferredMacToken) {
                    return name
                }
                return macTokenNames[preferredMacToken] ?? preferredMacToken
            }()
            HStack {
                Text("Mac Model")
                Spacer()
                Text(selectedMacDisplayName).foregroundColor(.secondary)
            }
            if let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()] {
                let pdpBase = JSONCatalogMac.pdpBaseURL(for: country, sourcePage: preferredMacToken)
                HStack(spacing: 8) {
                    Text("PDP Base")
                    Spacer()
                    Text(pdpBase?.absoluteString ?? "—")
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Picker("", selection: $preferredMacToken) {
                ForEach(availableMacTokens, id: \.self) { token in
                    Text(macTokenNames[token] ?? token).tag(token)
                }
            }
            .id("macpicker-\(preferredCountry)-\(preferredProductType)-\(availableMacTokens.joined(separator: ","))")
            .pickerStyle(.menu)
            .frame(minWidth: 260)
        }
    }
    
    func loadCountries() {
        OrderedCountries.enumerated().forEach { index, value in
            if value == preferredCountry {
                selectedCountryIndex = index
            }
        }
    }
    
    func loadSkus() async {
        let favoriteSkus = Set<String>(preferredSKUs.components(separatedBy: ","))
        // Resolve the preferred product type
        let family = ProductFamily(rawValue: preferredProductType)
        // When Apple Watch is selected, use the JSON-driven, cached watch helper (synchronous)
        if family?.isWatch == true {
            if let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()],
               preferredWatchToken.isEmpty == false,
               let skuData = SKUDataLoader().watchSKUData(forToken: preferredWatchToken, country: country) {
                allModels = skuData.orderedSKUs.map { sku in
                    let name = skuData.productName(forSKU: sku) ?? sku
                    return ProductModel(sku: sku, name: name, isFavorite: favoriteSkus.contains(sku))
                }
                return
            }
        }
        // When iPhone is selected and a token is chosen, use phone token path
        if family?.isIPhone == true {
            if let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()],
               preferredPhoneToken.isEmpty == false,
               let skuData = SKUDataLoader().phoneSKUData(forToken: preferredPhoneToken, country: country) {
                allModels = skuData.orderedSKUs.map { sku in
                    let name = skuData.productName(forSKU: sku) ?? sku
                    return ProductModel(sku: sku, name: name, isFavorite: favoriteSkus.contains(sku))
                }
                return
            }
        }
        // Fallback for non-watch (existing async path)
        guard let skuData = try? await model.skuDataForPreferredProduct else { return }
        allModels = skuData.orderedSKUs.map { sku in
            let name = skuData.productName(forSKU: sku) ?? sku
            return ProductModel(sku: sku, name: name, isFavorite: favoriteSkus.contains(sku))
        }
    }

    @MainActor func loadWatchTokens() async {
        guard let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()] else { return }
        availableWatchTokens = JSONCatalogAppleWatch.categoriesSourcePages(for: country)
        // Build human-friendly names for tokens from JSON metadata
        var names: [String: String] = [:]
        for token in availableWatchTokens {
            // 1) Prefer explicit per-country token display from JSON if available
            if let explicit = JSONCatalogAppleWatch.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
                names[token] = explicit
                continue
            }
            // 2) Derive from metadata
            if let dict = JSONCatalogAppleWatch.categoryData(for: country, sourcePage: token),
               let md = dict.values.first {
                var baseName: String? = nil
                if let famName = md.familyName, famName.isEmpty == false, famName.lowercased() != "unknown" {
                    baseName = famName
                } else {
                    let fam = md.family
                    if fam == "apple_watch" {
                        baseName = "Apple Watch"
                    } else if fam.isEmpty == false {
                        baseName = fam.replacingOccurrences(of: "_", with: " ").capitalized
                    }
                }
                var variant: String? = nil
                if token.hasPrefix("apple-watch-") {
                    let suffix = String(token.dropFirst("apple-watch-".count))
                    if suffix.isEmpty == false {
                        variant = (suffix.lowercased() == "se") ? "SE" : suffix.replacingOccurrences(of: "-", with: " ").capitalized
                    }
                }
                if let base = baseName { names[token] = variant != nil ? "\(base) \(variant!)" : base }
            }
        }
        watchTokenNames = names
        // If current preferredWatchToken is not in the list, set a sensible default (first token or empty)
        if preferredWatchToken.isEmpty || availableWatchTokens.contains(preferredWatchToken) == false {
            preferredWatchToken = availableWatchTokens.first ?? ""
        }
    }

    @MainActor func loadPhoneTokens() async {
        guard let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()] else { return }
        availablePhoneTokens = JSONCatalogiPhone.categoriesSourcePages(for: country)
        var names: [String: String] = [:]
        for token in availablePhoneTokens {
            // 1) Prefer explicit per-country token display from JSON if available
            if let explicit = JSONCatalogiPhone.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
                names[token] = explicit
                continue
            }
            // 2) Derive base name from JSON (familyName or family)
            var baseName: String = "iPhone"
            if let dict = JSONCatalogiPhone.categoryData(for: country, sourcePage: token),
               let md = dict.values.first {
                if let famName = md.familyName, famName.isEmpty == false, famName.lowercased() != "unknown" {
                    baseName = famName
                } else {
                    let fam = md.family
                    if fam.isEmpty == false {
                        baseName = fam.replacingOccurrences(of: "_", with: " ").capitalized
                    }
                }
            }
            // Ensure proper casing for iPhone family
            if baseName.lowercased() == "iphone" { baseName = "iPhone" }
            // Derive variant from token suffix (e.g., "iphone-17-pro" -> "17 Pro")
            var variant: String = ""
            if token.hasPrefix("iphone-") {
                let suffix = String(token.dropFirst("iphone-".count))
                if suffix.isEmpty == false {
                    variant = suffix.replacingOccurrences(of: "-", with: " ").capitalized
                }
            }
            // Compose final name
            let finalName = variant.isEmpty ? baseName : "\(baseName) \(variant)"
            names[token] = finalName
        }
        phoneTokenNames = names
        // Load any previously-saved per-country token selection
        let perCountryKey = "preferredPhoneToken.\(preferredCountry.uppercased())"
        if let saved = UserDefaults.standard.string(forKey: perCountryKey), availablePhoneTokens.contains(saved) {
            preferredPhoneToken = saved
        } else if preferredPhoneToken.isEmpty || availablePhoneTokens.contains(preferredPhoneToken) == false {
            // Keep selection stable when possible; if current selection is missing, pick first available
            preferredPhoneToken = availablePhoneTokens.first ?? ""
        }
    }

    @MainActor func loadMacTokens() async {
        guard let country = Countries[preferredCountry] ?? Countries[preferredCountry.uppercased()] else { return }
        availableMacTokens = JSONCatalogMac.categoriesSourcePages(for: country)
        var names: [String: String] = [:]
        for token in availableMacTokens {
            // Prefer JSON-provided token display if available
            if let explicit = JSONCatalogMac.tokenDisplayName(for: country, sourcePage: token), explicit.isEmpty == false {
                names[token] = explicit
                continue
            }
            // Fallback: prettify token
            names[token] = token.replacingOccurrences(of: "-", with: " ").capitalized
        }
        macTokenNames = names
        // Per-country persisted selection
        let perCountryKey = "preferredMacToken.\(preferredCountry.uppercased())"
        if let saved = UserDefaults.standard.string(forKey: perCountryKey), availableMacTokens.contains(saved) {
            preferredMacToken = saved
        } else if preferredMacToken.isEmpty || availableMacTokens.contains(preferredMacToken) == false {
            preferredMacToken = availableMacTokens.first ?? ""
        }
    }

    private func displayName(forToken token: String) -> String {
        if let name = watchTokenNames[token], name.isEmpty == false { return name }
        // Fallback: prettify token string
        return token.replacingOccurrences(of: "-", with: " ").capitalized
    }
    
    func loadStores(filterText: String?) async {
        if selectedStore.isEmpty {
            selectedStore = preferredStoreNumber
        }
        
        let storesJson = await model.storesForCurrentCountry
        let stores: [StoreWithSelection] = storesJson.map { store in
            StoreWithSelection(
                store: store,
                isSelected: store.storeNumber == selectedStore
            )
        }
        if let filter = filterText?.lowercased(), filter.isEmpty == false {            
            allStores = stores.filter { store in
                if store.storeName.lowercased().contains(filter) {
                    return true
                }
                
                if store.city.lowercased().contains(filter) {
                    return true
                }
                
                if store.storeNumber.lowercased().contains(filter) {
                    return true
                }
                
                if (store.stateName?.lowercased() ?? "").contains(filter) {
                    return true
                }
                
                if (store.stateCode?.lowercased() ?? "").contains(filter) {
                    return true
                }
                
                return false
            }
        } else {
            allStores = stores
        }
    }
    
    func selectDefaultStoreForNewCountry() async {
        guard let defaultStore = await model.getDefaultStoreForCurrentCountry() else {
            return
        }
        
        preferredStoreNumber = defaultStore.storeNumber
        selectedStore = preferredStoreNumber
        
        for var store in allStores {
            store.isSelected = store.storeNumber == preferredStoreNumber
        }
    }

    // MARK: - Lifecycle helpers used in view modifiers
    private func onAppearSetup() {
        loadCountries()
        Task { await loadSkus() }
        Task { await loadStores(filterText: nil) }
        Task { await model.fetchLatestGithubRelease() }
        Task { await loadWatchTokens() }
        Task { await loadPhoneTokens() }
        Task { await loadMacTokens() }
    }

    private func handleSelectedCountryIndexChange(_ newValue: Int) {
        let newCountry = OrderedCountries[newValue]
        preferredCountry = newCountry
        Task { await loadWatchTokens() }
        Task { await loadPhoneTokens() }
        Task { await loadMacTokens() }
    }

    private func handleAllModelsChange(_ models: [ProductModel]) {
        let favoritedModels = models.filter { $0.isFavorite }
        preferredSKUs = favoritedModels.map { $0.sku }.joined(separator: ",")
    }

    private func handleStoreSearchTextChange(_ newText: String) {
        if newText.isEmpty {
            Task { await loadStores(filterText: nil) }
        } else {
            Task { await loadStores(filterText: newText) }
        }
    }

    private func handleAllStoresChange(_ newStores: [StoreWithSelection]) {
        let currentSelected = selectedStore
        for store in newStores where store.isSelected && store.storeNumber != currentSelected {
            selectedStore = store.storeNumber
        }
        if preferredStoreNumber != selectedStore { preferredStoreNumber = selectedStore }
        Task { await loadStores(filterText: storeSearchText) }
    }

    private func handlePreferredProductTypeChange(_ newType: String) {
        preferredSKUs = ""
        Task { await loadSkus() }
        model.clearCurrentAvailableParts()
        Task { await model.fetchLatestInventory() }
        Task { await loadWatchTokens() }
        Task { await loadPhoneTokens() }
        Task { await loadMacTokens() }
    }

    private func handlePreferredStoreNumberChange() {
        Task { await model.updateStoreName() }
        Task { await model.fetchLatestInventory() }
    }

    private func handlePreferredUpdateIntervalChange() {
        Task { await model.fetchLatestInventory() }
    }

    private func handlePreferredCountryChange() {
        storeSearchText = ""
        Task { await loadStores(filterText: storeSearchText) }
        Task { await loadSkus() }
        Task { await selectDefaultStoreForNewCountry() }
        Task { await loadWatchTokens() }
        Task { await loadPhoneTokens() }
        Task { await loadMacTokens() }
    }

    private func handleReloadInventory() {
        Task { await model.fetchLatestInventory() }
    }

    private func handlePreferredWatchTokenChange() {
        Task { await loadSkus() }
        model.clearCurrentAvailableParts()
        Task { await model.fetchLatestInventory() }
    }

    private func handlePreferredPhoneTokenChange() {
        // Persist per-country selection for iPhone token
        let perCountryKey = "preferredPhoneToken.\(preferredCountry.uppercased())"
        UserDefaults.standard.set(preferredPhoneToken, forKey: perCountryKey)
        Task { await loadSkus() }
        model.clearCurrentAvailableParts()
        Task { await model.fetchLatestInventory() }
    }

    private func handlePreferredMacTokenChange() {
        // Persist per-country selection for Mac token
        let perCountryKey = "preferredMacToken.\(preferredCountry.uppercased())"
        UserDefaults.standard.set(preferredMacToken, forKey: perCountryKey)
        Task { await loadSkus() }
        model.clearCurrentAvailableParts()
        Task { await model.fetchLatestInventory() }
    }
}

//struct SettingsView_Previews: PreviewProvider {
//    static var previews: some View {
//        SettingsView()
//            .environmentObject(Model.testData)
//    }
//}
