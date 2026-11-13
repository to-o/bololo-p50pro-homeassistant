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

## 成长记录与完整部署源码

- [成长记录与中国女童参考曲线](feeding-web/GROWTH.md)：体重以斤输入和显示，支持首月视图、编辑及撤销。
- [海马爸比桥接源码](haimababi-bridge/README.md)：摄像头事件、睡眠日报及独立取流诊断源码与依赖限制。
- [OpenWrt 启动模板](deploy/openwrt/README.md)：脱敏配置，真实凭据和家庭数据保留在运行主机。

验证：`python3 tests/test_growth.py`；前端合成数据交互测试在 `tests/` 下执行 `npm install` 后运行 `npm test`。测试不访问真实设备或写入家庭数据库。视频取流需要另行准备外部SDK，详见桥接说明。


- [iPhone 摄像头播放入口](feeding-web/CAMERA.md)：按需打开、浏览器直接解码；实际手机出图仍待真机验证。
