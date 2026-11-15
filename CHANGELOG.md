# Changelog

## 3.0.0-RC.4

### Added

- Sparkle update dialogs show release notes from the changelog. Release packaging embeds the matching version's notes, or the Unreleased section for a new version.
- GitHub releases include the same changelog section ahead of automatically generated notes.

### Changed

- Scraper run to add new products and update availability: PROLED MacBook Pro

## 3.0.0-RC.3

### Added

- Added 2, 10, and 15 minute update intervals.
- In-app credits and project pages acknowledge the original author and contributors.

### Changed

- Custom SKU, preferred models, nearby-store inclusion, and the preferred-only display and notification options are now per search. Existing searches inherit the previous global values on first load.
- Settings now has a **General Settings** page (update interval and larger text) separate from per-search options.
- Searches sharing a country, store, and nearby-store setting are combined into one pickup request. Results and notification filtering respect each search's preferences.

## 3.0.0-RC.2

### Added

- Multiple saved product searches across all supported Apple product families, each with its own country and Apple Store.
- A master-detail Settings layout with a search sidebar, **New Search**, deletion controls, and immediate saving of edits to the selected search.
- Separate inventory result sections for each search, with country-specific product links and availability.
- Human-readable store labels, such as **Near Apple Memorial City — Houston, TX**, or **At Apple Memorial City — Houston, TX** when nearby stores are disabled.
- Sparkle app updates with daily checks, **Check for Updates…**, and persistent **Stable** and **Beta** channel selection. The updater requires a configured HTTPS feed and valid EdDSA public key.
- A GitHub Pages appcast template and release tooling for universal Apple Silicon/Intel archives, Developer ID signing, notarization, stapling, signature verification, ZIP checksums, and signed stable/beta appcast items.
- Regression tests for search persistence and migration, pickup request construction and response handling, cooldown behavior, and store-location labels.

### Changed

- Existing single-search preferences and earlier family/model-only saved searches migrate to independently identified searches using the previous country and store settings.
- Searches sharing a country and store are combined into one pickup request. Different locations are queried separately, and results are scoped to the corresponding search.
- Preferred-model selections are retained when switching products. Favorites from unrelated searches are excluded from pickup queries, and an empty preferred-only selection does not trigger an invalid request.
- Country changes validate the available model catalog before saving. Unsupported changes restore the previous search, and stale asynchronous editor loads cannot overwrite a newer selection.
- Notifications use the configured searches rather than the global product picker. Overlapping searches do not count the same country/store/part availability twice.
- Inventory refreshes reuse an ephemeral URLSession and coalesce overlapping triggers rather than cancelling in-flight requests. Changed configurations are refreshed after the current request completes.
- Apple bot blocks pause pickup checks for one minute instead of immediately retrying. Rate-limit responses honor supported `Retry-After` values, and the UI reports when checks can resume. This cooldown applies across searches for the current app session; it does not guarantee access to Apple's endpoint.
- Sparkle replaces GitHub-tag version polling and the old update-download indicator.

### Fixed

- Search headings and sidebar labels no longer repeat the product family when it is already part of the model name.
- Pickup warnings are collected across location groups, and the configured store is prioritized within its search's results.
- Refresh errors retain existing results, which may be stale, rather than replacing them with a successful-looking empty result.
- The SKU-name regression test now uses the existing SKU lookup API, allowing the test target to compile instead of leaving an incomplete unsigned test bundle after a failed build.
