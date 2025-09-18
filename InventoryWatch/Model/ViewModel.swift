//
//  ViewModel.swift
//  InventoryWatch
//
//  Created by Worth Baker on 10/25/22.
//

import Foundation

@MainActor
final class ViewModel: ObservableObject {
    
    private let fulfillmentModel = FulfillmentModel()
    private let githubModel = GithubModel()
    private let notificationSender = NotificationSender()
    public var defaultsVendor = DefaultsVendor()
    
    private var updateTimer: Timer?
    
    @Published var availableParts: [(FulfillmentStore, [PartAvailability])] = []
    @Published var isLoading = false
    @Published var hasLatestVersion = true
    @Published var errorState: AppError?
    @Published var preferredStoreName: String? = nil
    @Published var pickupErrorKeys: [String] = []
    
    var skuDataForPreferredProduct: SKUData {
        get async throws {
            return try await fulfillmentModel.skuDataForPreferredProduct
        }
    }
    
    var storesForCurrentCountry: [RetailStore] {
        get async {
            do {
                let storesByCountry = try await fulfillmentModel.loadStoresByCountry()
                guard let stores = storesByCountry[defaultsVendor.preferredCountry.locale]?.stores else {
                    throw AppError.invalidProjectState
                }
                
                return stores .sorted(by: { first, second in
                    if let firstState = first.address.stateName, let secondState = second.address.stateName {
                        return firstState < secondState
                    } else {
                        return first.name < second.name
                    }
                })
            } catch {
                updateErrorState(to: error)
                return []
            }
        }
    }
    
    private var selectedStore: RetailStore? {
        get async {
            let allStores = await storesForCurrentCountry
            let preferredStoreNumber = defaultsVendor.preferredStoreNumber
            
            return allStores.first(where: { $0.storeNumber == preferredStoreNumber })
        }
    }
    
    init() {
        Task { await updateStoreName() }
    }
    
    private var latestTask: Task<(), Never>? = nil
    
    func fetchLatestInventory() async {
        isLoading = true
        AnalyticsData.updateAnalyticsData()
        
        if let task = latestTask {
            print("cancelling prior task: \(task)")
            task.cancel()
        }
        
        latestTask = Task {
            
            do {
                hasLatestVersion = try await githubModel.hasLatestGithubRelease()
                updateErrorState(to: .none, deactivateLoadingState: false)
                
                availableParts = try await fulfillmentModel.fetchInventory()
                // Surface any Apple pickup API error keys (e.g., invalidLocalModelStore)
                pickupErrorKeys = await fulfillmentModel.lastPickupErrorKeys
                try Task.checkCancellation()
                updateErrorState(to: .none)
                
                refreshLastUpdateTime()
                
                if let skuData = try? await skuDataForPreferredProduct {
                    await notificationSender.sendNotificationIfNeeded(availableParts: availableParts, skuData: skuData)
                }
                
                print("successful update at \(defaultsVendor.lastUpdateDate ?? "unknown time")")
            } catch {
                if error is CancellationError {
                    print("task cancelled - suppressing thrown CancellationError and returning")
                    return
                } else {
                    updateErrorState(to: error)
                }
            }
            
            isLoading = false
            latestTask = nil
            resetTimer()
        }
    }
    
    func clearCurrentAvailableParts() {
        availableParts = []
    }
    
    func fetchLatestGithubRelease() async {
        if let latest = try? await githubModel.hasLatestGithubRelease() {
            hasLatestVersion = latest
        }
    }
    
    func updateErrorState(to error: Error?, deactivateLoadingState: Bool = true) {
        if deactivateLoadingState {
            self.isLoading = false
        }
        
        guard let error = error else {
            self.errorState = nil
            return
        }
        
        print(error.localizedDescription)
        if let modelError = error as? AppError {
            self.errorState = modelError
        } else {
            self.errorState = AppError.generic(error)
        }
    }
    
    func getDefaultStoreForCurrentCountry() async -> RetailStore? {
        do {
            guard let store = try await fulfillmentModel.getDefaultStoreForCurrentCountry() else {
                throw AppError.invalidProjectState
            }
            
            return store
        } catch {
            updateErrorState(to: error)
            return nil
        }
    }
    
    func updateStoreName() async {
        let storeNumber = defaultsVendor.preferredStoreNumber
        let store = await self.storesForCurrentCountry.first(where: { store in
            store.storeNumber == storeNumber
        })
        
        self.preferredStoreName = store?.name
    }
    
    private func refreshLastUpdateTime() {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, h:mm a"
        let dateString = formatter.string(from: Date())
        
        defaultsVendor.lastUpdateDate = dateString
    }
    
    private func resetTimer() {
        // if the timer settings have changed, kill the current timer
        if let existingTimer = updateTimer, existingTimer.timeInterval != Double(defaultsVendor.preferredUpdateInterval * 60) {
            existingTimer.invalidate()
            updateTimer = nil
        }
        
        // if no timer exists, and the user wants repeated updates, construct a repeating timer 
        if defaultsVendor.preferredUpdateInterval > 0, updateTimer == nil {
            let interval = Double(defaultsVendor.preferredUpdateInterval * 60)
            updateTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true, block: { _ in
                Task { [weak self] in await self?.fetchLatestInventory() }
            })
        }
    }
    
}
