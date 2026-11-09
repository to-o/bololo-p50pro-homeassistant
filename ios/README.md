# BOLOLO iOS (independent, no OpenWrt)

A first native iOS 17+ SwiftUI client for the owner's BOLOLO P50 Pro, using the verified vendor HTTPS endpoints from `docs/PROTOCOL_RESEARCH.md`.

## Present scope

- Phone/SMS login, refreshable session stored in iOS Keychain.
- Discover owned or shared devices with a valid `sno` and MAC.
- Read device status over HTTPS (foreground refresh).
- Retrieve cloud *preparation* history from `foam/detail/{sno}/3`, page through records, and deduplicate on cloud record ID.
- Persist manual bottle-feeding notes and cloud preparation records using SwiftData. Prepared water volume is **not** consumed milk volume.
- Experimental, explicitly initiated HTTP-only weighing workflow (device must be idle and previously shared/authorized). This flow is NOT yet proven end to end on iOS.

## Start (macOS or GitHub Actions)

Install Xcode 15 or later, and [XcodeGen](https://github.com/yonaskolb/XcodeGen).

```sh
cd ios
xcodegen generate
xcodebuild -project BOLOLO.xcodeproj -scheme BOLOLO -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

GitHub Actions `.github/workflows/ios-build.yml` performs unsigned simulator compilation on a hosted Mac. **Unsigned simulator builds are not installable IPAs**. For device installation, configure your own Apple signing and TestFlight (paid developer membership); no certificates, tokens, or signing secrets belong in the repository.

## Limitations and security

- Only when the app is open can it refresh on demand. Apple's background scheduling does not guarantee always-on event collection. After reopening, the app re-queries vendor history; completeness is bounded by cloud retention and API behavior.
- The vendor API is reverse-engineered rather than a supported public contract. Pagination counters can be wrong; this implementation ignores `pages` as a stopping condition and deduplicates by `id`.
- Cloud dates are timezone-naive. This first version interprets them as Asia/Shanghai local time; verify the device's configured zone.
- All requests use the OS TLS trust store. Session tokens are stored in Keychain and must never be logged. No MQTT/1883 is used.
- Cloud user/device data is private and remains on this iPhone. SwiftData has no automatic family sync configured.
- Remote weighing is opt-in and conservative: do not dispense water, do not change temperature, and abort if the device is busy or any acknowledgement is ambiguous.
- The `ios` client is independent; existing `feeding-web` and OpenWrt services are left unchanged.
