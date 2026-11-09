# BOLOLO P50 Pro 家庭喂养日记

这个仓库维护家庭局域网喂养网页、BOLOLO P50 Pro 只读客户端与 MQTT 上报解析，以及独立原生 iOS App 源码。

## iOS App（开发中）

[SwiftUI 源码、构建方式和限制](ios/README.md)。iPhone 可通过 BOLOLO 云端 HTTPS 登录、查询设备状态和读取已验证的备奶历史接口；本地记录使用 SwiftData。GitHub Actions 用 macOS 构建无签名模拟器版本。实机签名与纯 HTTP 称重仍需验证。

## 局域网喂养网页

需要 Python 3.8 或以上版本。

```sh
python feeding-web/server.py
```

打开 `http://127.0.0.1:8765/`。局域网运行、OpenWrt 配置、自动记奶和更新流程见[部署说明](feeding-web/README.md)。

## 目录

- [原生 iOS 客户端](ios/)
- [网页和 SQLite 服务](feeding-web/)
- [只读状态与会话客户端](bololo_read_status.py)
- [协议实测与研究手册](docs/PROTOCOL_RESEARCH.md)
- [维护计划](docs/CODEX_TASKS.md)

GitHub 的 `main` 维护源码和文档。每户的数据库、设备标识和会话由部署主机或 iPhone 自行保存。原有局域网网页不依赖 iOS 项目，原生 Home Assistant 集成仍是后续工作。
