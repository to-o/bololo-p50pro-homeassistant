# BOLOLO 云端认证与验证码流程（供客户端和 AI 代理参考）

更新时间：2026-11-09。本文仅记录本仓库代码、设备实测和用户提供的官方 App 行为中能确认的协议。它不是 BOLOLO 官方 API 文档；云端接口可能变更。没有实证的图形验证码接口会明确标为未知，不能根据机智云通用 API 猜测。

## 1. 适用范围与证据

- App 云端：`https://app.bololoapp3.com/`
- 认证接口使用本仓库 `BololoAPI.appID`（与 `bololo_read_status.py` 中的 `APP_ID` 相同）。设备 API 使用源码中的产品 key。它们是应用/产品标识，不是用户登录凭据。
- Python 客户端 `bololo_read_status.py` 与 iOS 客户端 `ios/BOLOLO/BololoAPI.swift` 实现了短信挑战、发送短信、手机号登录和 refresh token。
- 实测包裹格式是 HTTP JSON：`{"code":"200","data":...}` 表示业务成功。HTTP 200 本身不保证业务成功；必须检查 JSON 的 `code`。
- 用户账号、手机号、短信码、挑战 token、Authorization、refresh token、设备 MAC、SNO 均属于实例数据。示例一律用占位符；不要提交实际值、HAR 原文或完整响应到 GitHub、提示词或日志。

## 2. 通用 HTTP 约定

请求主机为 `app.bololoapp3.com`，使用 HTTPS。代码使用以下头部：

```http
X-Gizwits-Application-Id: <APP_ID>
Version: 1.0
Content-Type: application/json
Authorization: <access-token>   # 仅需要登录态的请求
```

除另有说明外，POST JSON 外包一层：

```json
{
  "appKey": "<APP_ID>",
  "data": { "...": "endpoint-specific fields" },
  "version": "1.0"
}
```

GET 请求不带 JSON 请求体。成功时读响应的 `data`；失败时同时保留 HTTP 状态和厂商业务 `code`，不要记录敏感请求头或请求体。

## 3. 已确认的短信登录流程

### 步骤 A：取得短信挑战 token

```http
GET /app/user/codeToken
```

预期成功响应形状：

```json
{"code":"200","data":"<challenge-token>"}
```

这里的 `data` 是后续发送短信请求使用的短期挑战 token。它不是短信验证码，也不是登录 access token。

### 步骤 B：请求发送短信

```http
POST /app/user/v2/mobileCode
Content-Type: application/json
```

通用包裹中的 `data`：

```json
{
  "mobile": "<手机号，仅数字，不带国家码>",
  "lang": "zh",
  "token": "<步骤 A 返回的 challenge-token>"
}
```

国家码不放在该请求中。当前客户端默认只在用户主动触发时请求短信；避免自动重试或连续请求，以免触发账号风控。

### 步骤 C：图形验证码（当前协议缺口）

**已观察到的行为：**官方 iOS App 在请求短信前会显示字符型图片验证码。独立 iOS 客户端调用步骤 B 曾收到业务码 `610`，错误说明要求先启用/完成图形验证码。应把 `610` 当作需要完成验证码流程的明确失败，不要把它当成短信已发送，也不要循环重试。

**尚未确认的内容：**两份用户提供的 Stream HAR 对 `app.bololoapp3.com` 只保留了 `CONNECT` 隧道记录，没有暴露 HTTPS 内层请求。因此目前没有经过验证的图片获取、刷新、校验 API 路径、参数、响应图片格式、captcha ID/临时令牌、有效期或把答案提交到短信接口的方式。

在获得一份能看到 HTTPS 内层请求的、由账号所有者授权的官方 App 抓包，或从合法取得的官方 App 客户端实现中确认完整协议以前：
- 不要杜撰诸如 `/app/verify/codes` 的端点；机智云公共 API 的同名路径不证明 BOLOLO 服务支持它。
- 不要尝试绕过验证码、风控或频率限制。
- UI 收到 `610` 时提示需要先完成官方验证码流程，并停止本次发送。不要把验证码答案、图片、手机号或 token 写入日志。

### 步骤 D：用短信码登录

短信由服务端发送后，调用：

```http
POST /app/user/loginByMobile
```

通用包裹中的 `data`：

```json
{
  "mobile": "<手机号，仅数字，不带国家码>",
  "code": "<用户收到的短信验证码>",
  "lang": "zh",
  "mobileCountryCode": "+86",
  "homeName": "我的家"
}
```

非中国号码必须传对应的 `mobileCountryCode`。短信码仅供当前登录使用，不能预填、复用或写入文档。

### 步骤 E：解析并保存会话

成功响应的 `data` 中，代码兼容以下 access token 位置：
- 首选 `jwtAuthenticationDto.token`
- 兼容顶层 `token`

refresh token 兼容 `refresh_token` 与 `refreshToken`。生命周期字段兼容 `created_at` / `createdAt` 和 `expired_at` / `expiredAt`；实测和代码均需兼容秒、毫秒 Unix 时间戳。

规范化后的会话字段：

```json
{
  "token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "created_at": 0,
  "expired_at": 0
}
```

数字 0 只是结构示例，不是实际会话值。iOS 客户端把会话写入 Keychain。OpenWrt 客户端把文件保存在 `/etc/bololo/session.json`，并以受限权限创建目录/锁文件；部署时仅允许服务账户读取。不要把会话文件加入版本控制或备份到公开位置。

### 步骤 F：刷新会话

```http
POST /app/user/refresh_token
Authorization: <旧 access-token>
```

通用包裹中的 `data`：

```json
{
  "clientId": "<APP_ID>",
  "refresh": true,
  "refresh_token": "<当前 refresh token>"
}
```

对响应使用与步骤 E 相同的解析逻辑，并原子替换旧会话。源码按 access token 生命周期中点刷新；设备请求返回已观察到的业务码 `505` 或 `526` 时，刷新一次并重试原请求一次。不要无限重试。OpenWrt 使用文件锁，避免并发请求同时轮换同一个 refresh token。

## 4. 登录后设备读取流程

所有以下请求都使用当前 access token：

1. 查询自有设备：`GET /app/smartHome/v2/users/devices`
2. 查询共享设备：`GET /app/smartHome/homes/shareDeviceListV2`
3. 从匹配条目读取 `sno` 和 MAC。匹配时使用本地用户选择/配置的设备，不要把 MAC 或 SNO 当作账号凭证。
4. 读取设备状态：`POST /bololo/app/device/status/{PRODUCT_KEY}/{MAC}`，通用包裹中的 `data` 为 `{}`。
5. 如需查云端备奶历史，见 [协议研究手册 §6.3](PROTOCOL_RESEARCH.md#63-读取-app-云端备奶历史)。

设备在自有列表中缺失不一定表示登录失败：目标设备可能尚未分享给该账号。已验证的设备分享接受流程另见协议研究手册；仅使用账号所有者生成的邀请。

## 5. 客户端实现和错误处理清单

- 认证顺序固定为：取得 `codeToken` → 发送短信 → 用户输入短信码 → `loginByMobile` → 安全保存会话 → 查询自有/共享设备。
- 每次请求验证 HTTPS 主机、HTTP 状态、JSON 结构和业务 `code`。不能仅因 HTTP 200 判成功。
- 对 `610` 停止并显示“需要完成厂商图形验证码”，不要把短信输入页面伪装成已发送成功。
- 登录成功但设备列表为空时，单独提示设备绑定/分享检查，不要重复索取验证码。
- 过期或 refresh 失败时清除无效会话并让用户重新登录；不能在后台偷偷发短信。
- 不打印完整 URL 查询参数、Authorization、手机号、验证码、验证码图像、challenge token、access/refresh token、完整响应对象。
- iOS 使用 Keychain；OpenWrt 文件和进程权限最小化。源码仓库只存端点、脱敏结构和可复现的合成 fixture。

## 6. 代码入口

- Python/OpenWrt：[`bololo_read_status.py`](../bololo_read_status.py) 的 `call`、`login_by_sms`、`normalize_session`、`refresh_session`、`query_saved`。
- 原生 iOS：[`BololoAPI.swift`](../ios/BOLOLO/BololoAPI.swift) 的 `request`、`sendSMS`、`login`、`parseSession`、`refresh`、`authorized`、`devices`。
- 当前图形验证码阻塞和验收计划：[iOS README](../ios/README.md#图形验证码阻塞2026-11-09)。
- 设备协议与实测边界：[协议研究手册](PROTOCOL_RESEARCH.md)。
