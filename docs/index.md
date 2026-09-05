# InventoryWatch

A macOS app to monitor Apple Store pickup availability for iPhone, Apple Watch, Mac, iPad, AirPods, HomePod, and Apple Vision Pro.

This is the open-source version of InventoryWatch. For the latest commercial release with web access, email/SMS notifications, and multi-search support, visit [InventoryWatch.app](https://inventorywatch.app).

## Features

- Real-time inventory checking across Apple Store locations in 35+ countries
- Support for all Apple product families: iPhone, iPad, Mac, Apple Watch, AirPods, HomePod, Apple Vision Pro
- Per-model and per-country token selection with persistent preferences
- Configurable update intervals with macOS notifications
- All product data scraped from Apple's official buy pages — no hardcoded SKUs

## Quick Start

```bash
# Clone and build
git clone https://github.com/worthbak/inventory-checker-app.git
cd inventory-checker-app
open InventoryWatch.xcodeproj  # Build (Cmd+B) then Run (Cmd+R)
```

Requires Xcode 15+ and macOS 14+.

### Regenerate Product Data

```bash
pip install requests
python3 scrape_models.py --family iphone --all-models
python3 scrape_apple_stores.py
```

See [README.md](../README.md) for full documentation, architecture, and scraper configuration reference.

## Project Status

Actively maintained as of 2025 with major refactoring completed:

- **Config-driven Python scraper**: `scrape_models.py` + `family_handlers.py` + `scraper_config.json` generates all catalog JSONs from Apple.com
- **Data-driven architecture**: All SKUs, countries, and stores externalized to JSON — no hardcoded product data in Swift
- **Full product family support**: iPhone (16, 17, 17e, 17 Pro, Air), iPad (Pro, Air, Mini, base), Mac (Air, Pro, Neo, iMac, Mini, Studio, Displays), Apple Watch (SE, Ultra, Hermes), AirPods (4, Max, Pro 2, Pro 3), HomePod, Apple Vision Pro
- **Multi-language stores**: Belgian (Dutch/French) and Swiss (German/French) dual-language store support
- **Anti-bot hardening**: Proper HTTP/1.1 handling and backoff for Apple's Akamai CDN

For a detailed changelog, see [REFACTORING_NOTES.md](../REFACTORING_NOTES.md).