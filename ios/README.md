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

## 图形验证码阻塞（2026-11-09）

- 官方 BOLOLO iOS App 在请求短信时弹出**字符型图片验证码**（图片、刷新、手动输入、确认）。用户的独立 iOS App 在发送短信时收到业务码 **610**，服务端明确说明“需开启图形验证码验证”。
- 当前 `sendSMS` 为 `GET /app/user/codeToken` → `POST /app/user/v2/mobileCode`，没有获取图片验证码、验证码 ID/会话以及校验环节。因此短信登录尚不能宣称通过真机测试；不能只靠新增弹窗修复。
- 机智云公开 Open API 有 `GET /app/verify/codes`、`POST /app/verify/codes`，但目前没有证据证明 BOLOLO 自有云端遵循相同端点、App Token、App Secret 与数据结构；禁止凭推测接入或绕过风控。
- 接入前需要从**用户合法获得的官方 App APK**或用户授权的本人网络调试中确认：图片获取接口及返回值（图片 URL/Base64、captchaId、临时 token）、刷新接口、校验/发短信接口、是否与 `app/user/v2/mobileCode` 结合、过期时间和重试限制。记录脱敏的请求/响应结构，不提交验证码、手机号、Token 或密钥。
- 确认协议后提供 SwiftUI sheet：图片预览、刷新、字符输入、确认、过期重拉；成功后才启用短信验证码输入；添加可重复的脱敏协议 fixture 单元测试及用户实机验收。
