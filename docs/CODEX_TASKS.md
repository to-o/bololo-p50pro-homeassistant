# 维护计划

`main` 是喂养网页、P50 Pro 接入和 iOS SwiftUI 客户端的源码来源。部署配置与家庭数据应留在用户设备中。

## 已有能力

- 独立局域网喂养网页，提供记录、修改、撤销、按天历史和 7 天／14 天统计。
- BOLOLO P50 Pro 云端状态查询与已保存会话续期。
- MQTT 上报解码与自动记奶，现有 OpenWrt 部署可以持续监听。
- 实机验证了官方 App 云端备奶历史接口 `bololo/appdataSata/foam/detail/{sno}/3`，可读取记录时间、出水量、奶瓶标识；详见 `docs/PROTOCOL_RESEARCH.md` 第 6.3 节。
- `ios/` 已建立原生 SwiftUI 客户端源码及 GitHub Actions 无签名模拟器构建工作流；**能否编译及真机使用以 CI/实测结果为准**。

## 后续验证

- iOS 的短信登录、获取设备 `sno`、云端历史分页与恢复同步必须在用户自己的设备上验证。
- 历史 `total/pages` 可能失真；分页需要以返回条数和记录 ID 去重，增加重试及漏记提示。
- HTTP-only 称重仍为实验性；不得将 MQTT 已验证结果等同于 iOS HTTP 轮询已验证。
- 云端历史的时间时区、留存期限、授权分享及多设备/多账号隔离需继续核实。
- iOS 后台不保证定时刷新；只能在 App 打开时补齐云端仍可查询的历史。
- 真机分发需要用户自己的签名/证书；不要将密钥、Token 或家庭数据提交到仓库。
- Home Assistant 接入可后续按需加入，不作为 iOS 客户端依赖。

详见 `ios/README.md`、`feeding-web/README.md` 和 `docs/PROTOCOL_RESEARCH.md`。

- [阻塞] BOLOLO 短信登录业务码 `610`：官方要求字符型图形验证码，但目前厂商专用的图片与校验接口未验证。须先提取合法 App 的脱敏接口证据，再实现 SwiftUI 人工验证码弹窗；不能以仅通过模拟器测试视为登录可用。
