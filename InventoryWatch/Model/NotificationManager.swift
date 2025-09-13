//
//  NotificationManager.swift
//  InventoryWatch
//
//  Created by Worth Baker on 11/8/21.
//

import Foundation
import UserNotifications

@MainActor
final class NotificationManager: NSObject, @unchecked Sendable {
    
    static let shared = NotificationManager()
    
    func requestNotificationPermissions() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        
        center.requestAuthorization(options: [.alert, .badge, .sound]) { (granted, error) in
            if granted {
                print("Notifications are enabled.")
            } else {
                print("Notifications are disabled.")
            }
        }
    }
    
    func sendNotification(title: String, body: String) {
        // Prevent notification spam - track notifications per item with longer cooldown
        let notificationKey = "\(title):\(body)"
        let notificationHistoryKey = "notificationHistory"
        
        // Get existing notification history
        var notificationHistory = UserDefaults.standard.dictionary(forKey: notificationHistoryKey) as? [String: Date] ?? [:]
        
        // Check if this notification was sent recently (within 24 hours)
        if let lastTime = notificationHistory[notificationKey],
           Date().timeIntervalSince(lastTime) < 86400 { // 24 hours
            print("Skipping duplicate notification within 24 hours: \(title)")
            return
        }
        
        // Clean up old entries (older than 7 days)
        let weekAgo = Date().addingTimeInterval(-604800)
        notificationHistory = notificationHistory.filter { $0.value > weekAgo }
        
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = UNNotificationSound.default
        content.categoryIdentifier = "INVENTORY_ALERT"
        content.threadIdentifier = "inventory-updates"
        
        // Add action buttons
        let viewAction = UNNotificationAction(
            identifier: "VIEW_INVENTORY",
            title: "View Details",
            options: [.foreground]
        )
        
        let openStoreAction = UNNotificationAction(
            identifier: "OPEN_APPLE_STORE",
            title: "Open Apple Store",
            options: [.foreground]
        )
        
        let category = UNNotificationCategory(
            identifier: "INVENTORY_ALERT",
            actions: [viewAction, openStoreAction],
            intentIdentifiers: [],
            options: []
        )
        
        UNUserNotificationCenter.current().setNotificationCategories([category])
        
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        let uuidString = UUID().uuidString
        let request = UNNotificationRequest(identifier: uuidString, content: content, trigger: trigger)
        
        // Schedule the request with the system
        let notificationCenter = UNUserNotificationCenter.current()
        notificationCenter.add(request) { (error) in
            if let error = error {
                print("Notification error: \(error)")
            } else {
                // Store this notification in history to prevent duplicates
                notificationHistory[notificationKey] = Date()
                UserDefaults.standard.set(notificationHistory, forKey: notificationHistoryKey)
                print("Notification sent: \(title)")
            }
        }
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    nonisolated public func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Swift.Void) {
        completionHandler( [.banner, .badge, .sound])
    }
}
