//
//  FulfillmentModel.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation


actor FulfillmentModel {
    
    let defaultsVendor = DefaultsVendor()
    let skuDataLoader = SKUDataLoader()
    
    private var lastPickupRequestTime: Date = .distantPast
    private var lastStoreListRequestTime: Date = .distantPast
    private let minimumRequestInterval: TimeInterval = 3.0
    private let maxRetries = 3
    private let baseRetryDelay: TimeInterval = 5.0
    
    var skuDataForPreferredProduct: SKUData {
        get async throws {
            return try await skuDataLoader.skuDataForPreferredProduct
        }
    }
    
    private var cachedStoreData: [String: StoreCountry] = [:]
    private let decoder = JSONDecoder()
    // Latest pickup API error keys (e.g., ["invalidLocalModelStore"]) captured from Apple JSON
    private(set) var lastPickupErrorKeys: [String] = []
    
    var session: URLSession {
        let c = URLSessionConfiguration.ephemeral
        c.httpAdditionalHeaders = [:]
        c.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        c.httpCookieAcceptPolicy = .never
        c.httpShouldSetCookies = false
        c.httpCookieStorage = nil
        c.urlCredentialStorage = nil
        return URLSession(configuration: c)
    }
    
    private func applyBrowserHeaders(to request: inout URLRequest) {
        request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", forHTTPHeaderField: "User-Agent")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30
    }
    
    private var modelParsingFilter: Set<String>? {
        let filterForPreferredModels = defaultsVendor.showResultsOnlyForPreferredModels
        var filterModels = filterForPreferredModels ? defaultsVendor.preferredSKUs : nil
        if let customSku = defaultsVendor.customSkuData?.sku {
            filterModels?.insert(customSku)
        }
        
        return filterModels
    }
    
    func loadStoresByCountry() async throws -> [String: StoreCountry] {
        if cachedStoreData.isEmpty == false {
            return cachedStoreData
        }

        do {
            // Try loading remote stores first
            let url = URL(string: "https://www.apple.com/rsp-web/store-list?locale=\(defaultsVendor.preferredCountry.locale)")!
            var request = URLRequest(url: url)
            applyBrowserHeaders(to: &request)
            
            let timeSinceLastStoreRequest = Date().timeIntervalSince(lastStoreListRequestTime)
            if timeSinceLastStoreRequest < minimumRequestInterval {
                let delay = minimumRequestInterval - timeSinceLastStoreRequest
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            }
            lastStoreListRequestTime = Date()
            
            let (data, _) = try await session.data(for: request, delegate: nil)
            
            // Check if we received HTML instead of JSON
            if let responseString = String(data: data, encoding: .utf8) {
                if responseString.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("<") {
                    print("❌ Store list API returned HTML instead of JSON. Falling back to local data.")
                    throw AppError.invalidStoreResponse
                }
            }
            
            let jsonStores = try decoder.decode(StoreBootstrap.self, from: data)
            cachedStoreData = jsonStores.countryData
            return jsonStores.countryData
        } catch {
            print("Store list API error: \(error)")
        }
        
        // If remote stores failed to load, fallback to comprehensive global store data first
        let fileType = "json"
        
        // Try the comprehensive global store data first
        if let path = Bundle.main.path(forResource: "Stores_GlobalBootstrap", ofType: fileType) {
            do {
                let data = try Data(contentsOf: URL(fileURLWithPath: path))
                let jsonStores = try decoder.decode(StoreBootstrap.self, from: data)
                print("✅ Using comprehensive global store data (536 stores across 26 countries)")
                return jsonStores.countryData
            } catch {
                print("⚠️ Failed to load global store data, trying local fallback: \(error)")
            }
        }
        
        // Fallback to original local bootstrap if global data fails
        if let path = Bundle.main.path(forResource: "Stores_LocalBootstrap", ofType: fileType) {
            do {
                let data = try Data(contentsOf: URL(fileURLWithPath: path))
                let jsonStores = try decoder.decode(StoreBootstrap.self, from: data)
                print("✅ Using local store bootstrap data")
                return jsonStores.countryData
            } catch {
                print("❌ Failed to load local store data: \(error)")
                throw error
            }
        } else {
            throw AppError.invalidProjectState
        }
    }
    
    func fetchInventory() async throws -> [(FulfillmentStore, [PartAvailability])] {
        let countryPath = defaultsVendor.countryPathElement.lowercased()
        let urlRoot = "https://www.apple.com/\(countryPath)shop/retail/pickup-message?"
        let query = try await generateQueryString(includeStore: true, location: nil)
        
        guard let apiURL = URL(string: urlRoot + query) else {
            throw AppError.couldNotGenerateURL
        }
        
        print("🌐 Pickup URL: \(apiURL.absoluteString)")
        
        for attempt in 0..<maxRetries {
            if attempt > 0 {
                let delay = baseRetryDelay * pow(2.0, Double(attempt - 1))
                let jitter = Double.random(in: 0..<delay * 0.3)
                let totalDelay = delay + jitter
                print("⏳ Retry \(attempt)/\(maxRetries) after \(Int(totalDelay))s (backoff + jitter)")
                try await Task.sleep(nanoseconds: UInt64(totalDelay * 1_000_000_000))
            }
            
            let timeSinceLastPickup = Date().timeIntervalSince(lastPickupRequestTime)
            if timeSinceLastPickup < minimumRequestInterval {
                let waitTime = minimumRequestInterval - timeSinceLastPickup
                try await Task.sleep(nanoseconds: UInt64(waitTime * 1_000_000_000))
            }
            lastPickupRequestTime = Date()

            var request = URLRequest(url: apiURL)
            applyBrowserHeaders(to: &request)
            request.httpShouldHandleCookies = false

            let s = session
            let (data, response) = try await s.data(for: request, delegate: nil)
            let httpResponse = response as? HTTPURLResponse
            let status = httpResponse?.statusCode ?? 0
            print("📥 Pickup response: status=\(status), bytes=\(data.count)")
            
            if status == 541 {
                print("⚠️ Got 541 (bot detected), will retry")
                continue
            }

            let parsed = try await parseStoreResponse(data, response: httpResponse, filterForModels: modelParsingFilter)
            return parsed
        }
        
        throw AppError.botDetected
    }
    
    func getDefaultStoreForCurrentCountry() async throws -> RetailStore? {
        let storesByCountry = try await loadStoresByCountry()
        guard let stores = storesByCountry[defaultsVendor.preferredCountry.locale]?.stores else {
            throw AppError.invalidProjectState
        }
        
        return stores.first
    }
    
    private func generateQueryString(includeStore: Bool = true, location: String?) async throws -> String {
        // Build SKU list using token-driven path respecting active product family
        let country = defaultsVendor.preferredCountry
        let family = defaultsVendor.preferredProductFamily
        let watchToken = defaultsVendor.preferredWatchToken
        let iPhoneToken = defaultsVendor.preferredPhoneToken
        let macToken = defaultsVendor.preferredMacToken
        let iPadToken = defaultsVendor.preferrediPadToken
        let airpodsToken = defaultsVendor.preferredAirPodsToken
        let homepodToken = defaultsVendor.preferredHomePodToken
        let avpToken = defaultsVendor.preferredAVPToken

        func resolveFamilySKU(token: String, familyCheck: Bool, loader: () async -> SKUData?) async throws -> [String]? {
            guard familyCheck, token.isEmpty == false else { return nil }
            guard let data = await loader() else {
                throw AppError.productNotAvailableInRegion
            }
            return data.orderedSKUs
        }

        var resolvedSKUs: [String] = []
        if let skus = try await resolveFamilySKU(token: watchToken, familyCheck: family.isWatch, loader: { await SKUDataLoader().watchSKUData(forToken: watchToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: iPhoneToken, familyCheck: family.isIPhone, loader: { await SKUDataLoader().phoneSKUData(forToken: iPhoneToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: macToken, familyCheck: family.isMac, loader: { await SKUDataLoader().macSKUData(forToken: macToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: iPadToken, familyCheck: family.isIPad, loader: { await SKUDataLoader().ipadSKUData(forToken: iPadToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: airpodsToken, familyCheck: family.isAirPods, loader: { await SKUDataLoader().airpodsSKUData(forToken: airpodsToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: homepodToken, familyCheck: family.isHomePod, loader: { await SKUDataLoader().homepodSKUData(forToken: homepodToken, country: country) }) {
            resolvedSKUs = skus
        } else if let skus = try await resolveFamilySKU(token: avpToken, familyCheck: family.isAVP, loader: { await SKUDataLoader().avpSKUData(forToken: avpToken, country: country) }) {
            resolvedSKUs = skus
        } else {
            // Fallback: try whichever token is set, else empty
            if watchToken.isEmpty == false, let data = await SKUDataLoader().watchSKUData(forToken: watchToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if iPhoneToken.isEmpty == false, let data = await SKUDataLoader().phoneSKUData(forToken: iPhoneToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if macToken.isEmpty == false, let data = await SKUDataLoader().macSKUData(forToken: macToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if iPadToken.isEmpty == false, let data = await SKUDataLoader().ipadSKUData(forToken: iPadToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if airpodsToken.isEmpty == false, let data = await SKUDataLoader().airpodsSKUData(forToken: airpodsToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if homepodToken.isEmpty == false, let data = await SKUDataLoader().homepodSKUData(forToken: homepodToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else if avpToken.isEmpty == false, let data = await SKUDataLoader().avpSKUData(forToken: avpToken, country: country) {
                resolvedSKUs = data.orderedSKUs
            } else {
                let data = try await skuDataLoader.skuDataForPreferredProduct
                resolvedSKUs = data.orderedSKUs
            }
        }

        // Build final SKU order depending on user preference
        // When "Only show results for preferred models" is enabled, restrict to preferred SKUs (plus custom)
        let preferred = defaultsVendor.preferredSKUs
        let showOnlyPreferred = defaultsVendor.showResultsOnlyForPreferredModels
        var allSkus: [String] = []
        if showOnlyPreferred {
            // Preserve deterministic order based on the user's stored CSV order
            let preferredCsv = UserDefaults.standard.string(forKey: "preferredSKUs") ?? ""
            let preferredList = preferredCsv.split(separator: ",").map { String($0) }.filter { !$0.isEmpty }
            allSkus.append(contentsOf: preferredList)
        } else {
            // 1) All preferred SKUs exactly as the user selected (order preserved as stored, best-effort)
            // 2) Remaining resolved SKUs (from token/product) not already included
            if preferred.isEmpty == false {
                let preferredCsv = UserDefaults.standard.string(forKey: "preferredSKUs") ?? ""
                let preferredList = preferredCsv.split(separator: ",").map { String($0) }.filter { !$0.isEmpty }
                allSkus.append(contentsOf: preferredList)
                let remainder = resolvedSKUs.filter { sku in preferred.contains(sku) == false }
                allSkus.append(contentsOf: remainder)
            } else {
                allSkus = resolvedSKUs
            }
        }
        // Always append custom SKU if present
        if let customSku = defaultsVendor.customSkuData?.sku, customSku.isEmpty == false {
            allSkus.append(customSku)
        }
        // Deduplicate while preserving order
        var seen = Set<String>()
        allSkus = allSkus.filter { sku in
            if seen.contains(sku) { return false }
            seen.insert(sku)
            return true
        }

        // Mac-specific: pickup-message requires full Apple part numbers (contain a '/').
        // Many Mac catalogs encode only base codes (e.g., MW2X3) which produce empty results.
        if family.isMac {
            let full = allSkus.filter { $0.contains("/") }
            if full.isEmpty {
                print("⚠️ Mac catalog SKUs are missing full part numbers. First few SKUs: \(allSkus.prefix(5).joined(separator: ", "))")
                throw AppError.invalidCatalogData
            }
            allSkus = full
        }

        guard allSkus.isEmpty == false else {
            throw AppError.productNotAvailableInRegion
        }

        var queryItems: [String] = ["fae=true"]

        if includeStore && !defaultsVendor.preferredStoreNumber.isEmpty {
            queryItems.append("store=\(defaultsVendor.preferredStoreNumber)")
        }

        queryItems.append("little=false")

        queryItems.append(contentsOf: allSkus
            .enumerated()
            .compactMap { next in
                guard next.element.isEmpty == false else {
                    return nil
                }
                
                let count = next.offset
                let sku = next.element
                return "parts.\(count)=\(sku)"
            })

        queryItems.append("mts.0=regular")
        queryItems.append("mts.1=sticky")
        queryItems.append("fts=true")
        
        return queryItems.joined(separator: "&")
    }
    
    private func parseStoreResponse(_ responseData: Data?, response: HTTPURLResponse?, filterForModels: Set<String>?) async throws -> [(FulfillmentStore, [PartAvailability])] {
        guard let responseData = responseData else {
            throw errorForStatusCode(response?.statusCode) ?? AppError.invalidStoreResponse
        }
        
        // Check if we received HTML instead of JSON
        if let responseString = String(data: responseData, encoding: .utf8) {
            if responseString.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("<") {
                print("❌ Received HTML instead of JSON. Response length: \(responseData.count) bytes")
                print("First 200 characters: \(String(responseString.prefix(200)))")
                
                // Check for common error patterns
                if responseString.contains("accessDenied") || responseString.contains("Access Denied") {
                    throw AppError.botDetected
                } else if responseString.contains("403") || responseString.contains("Forbidden") {
                    throw AppError.accessDenied
                } else if responseString.contains("404") || responseString.contains("Not Found") {
                    throw AppError.resourceNotFound
                } else if responseString.contains("rate limit") || responseString.contains("too many requests") {
                    throw AppError.rateLimited
                } else {
                    throw AppError.invalidStoreResponse
                }
            }
        }
        
        guard let json = try? JSONSerialization.jsonObject(with: responseData, options: []) as? [String : Any] else {
            print("❌ Failed to parse JSON. Response status: \(response?.statusCode ?? -1)")
            if let responseString = String(data: responseData, encoding: .utf8) {
                print("Response preview: \(String(responseString.prefix(200)))")
            }
            throw errorForStatusCode(response?.statusCode) ?? AppError.invalidStoreResponse
        }
        
        guard let body = json["body"] as? [String: Any] else {
            throw AppError.unexpectedJSONStructure
        }

        let storeList: [[String: Any]]
        if let stores = body["stores"] as? [[String: Any]] {
            storeList = stores
        } else if let content = body["content"] as? [String: Any],
                  let pickupMessage = content["pickupMessage"] as? [String: Any] {
            if let errors = pickupMessage["errorMessageKeys"] as? [String], errors.isEmpty == false {
                lastPickupErrorKeys = errors
                print("Apple pickup API errors (non-fatal): \(errors.joined(separator: ", "))")
            } else {
                lastPickupErrorKeys = []
            }
            storeList = pickupMessage["stores"] as? [[String: Any]] ?? []
        } else {
            throw AppError.unexpectedJSONStructure
        }
        
        let skuData = try await skuDataForPreferredProduct
        let collectedStores: [FulfillmentStore] = storeList.compactMap { storeJSON -> FulfillmentStore? in
            guard let name = storeJSON["storeName"] as? String else { return nil }
            guard let number = storeJSON["storeNumber"] as? String else { return nil }
            guard let city = storeJSON["city"] as? String else { return nil }
            let state = storeJSON["state"] as? String
            
            guard let partsAvailability = storeJSON["partsAvailability"] as? [String: [String: Any]] else { return nil }
            let parsedParts: [PartAvailability] = partsAvailability.values.compactMap { part in
                guard
                    let availabilityString = part["pickupDisplay"] as? String,
                    let availability = PartAvailability.PickupAvailability(rawValue: availabilityString),
                    let messageTypes = part["messageTypes"] as? [String: Any],
                    let regular = messageTypes["regular"] as? [String: Any],
                    let availabilityStorePickupQuote = regular["storePickupQuote"] as? String
                else {
                    return nil
                }
                guard let partNumber = part["partNumber"] as? String else {
                    return nil
                }
                // get name from SKU data, or custom SKU if available
                let productName: String
                if let name = skuData.productName(forSKU: partNumber) {
                    productName = name
                } else if let customSku = defaultsVendor.customSkuData, partNumber == customSku.sku {
                    productName = customSku.nickname
                } else {
                    productName = partNumber
                }
                
                return PartAvailability(partNumber: partNumber, partName: productName, availability: availability, availabilityStorePickupQuote: availabilityStorePickupQuote)
            }
            
            
            
            let storeAddress = StoreAddress(city: city, address1: nil, address2: nil, stateName: state, stateCode: nil, postalCode: nil)
            let retailStore = RetailStore(id: number, name: name, telephone: "", slug: "", address: storeAddress)
            return FulfillmentStore(store: retailStore, partsAvailability: parsedParts)
        }
        
        return self.parseAvailableModels(from: collectedStores, filterForModels: filterForModels)
    }
    
    private func parseAvailableModels(from stores: [FulfillmentStore], filterForModels: Set<String>?) -> [(FulfillmentStore, [PartAvailability])] {
        let allAvailableModels: [(FulfillmentStore, [PartAvailability])] = stores
            .sorted(by: { first, _ in
                // always put preferred store first
                return first.storeNumber == defaultsVendor.preferredStoreNumber
            })
            .compactMap { store in
                let rv: [PartAvailability] = store.partsAvailability.filter { part in
                    switch part.availability {
                    case .available:
                        if let filter = filterForModels, filter.contains(part.partNumber) == false {
                            return false
                        }
                        
                        return true
                    case .unavailable, .ineligible:
                        return false
                    }
                }
                
                if rv.isEmpty {
                    return nil
                } else {
                    return (store, rv)
                }
            }
        
        return allAvailableModels
    }
    
    private func errorForStatusCode(_ statusCode: Int?) -> AppError? {
        guard let statusCode else {
            return nil
        }
        
        switch statusCode {
        case 541:
            return .botDetected
        case 500...599:
            return .storeUnavailable
        default:
            return nil
        }
    }
    
}