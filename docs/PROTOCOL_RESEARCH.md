# Protocol discovery runbook

Android 1271W APK 静态解析结论已整理在[Android APK 分析文档](ANDROID_APK_ANALYSIS.md)。短信认证流程见[认证文档](AUTHENTICATION.md)。

## Why capture first?
Cellular-only phone app control proves phone-side LAN/BLE is unnecessary for the tested operation. It **does not** prove the exact appliance connectivity, cloud vendor, device transport, or availability of public APIs.

## 1. Identify where packets traverse
Run on OpenWrt:

```sh
cat /tmp/dhcp.leases
ip neigh show
ip -br addr
ip route
```

Locate the P50 Pro by owner's known MAC/hostname, controlled reconnect observation, DHCP lease, or AP client listing. Confirm its traffic traverses OpenWrt; otherwise capture on the actual gateway or AP. Beware hardware/software offload and bridged Wi-Fi traffic that may evade `tcpdump -i any`.

## 2. Install tcpdump
Only on owner-controlled router, if needed:

```sh
if command -v apk >/dev/null; then
  apk update && apk add tcpdump
elif command -v opkg >/dev/null; then
  opkg update && opkg install tcpdump
else
  echo "Install tcpdump using the current firmware package manager"
fi
```

## 3. Capture *only* the selected device
Example private LAN IP; replace with the actual address:

```sh
DEVICE_IP=192.168.1.150
tcpdump -ni any "host ${DEVICE_IP} and (tcp or udp)"
# Bounded rotating pcap: up to ~2 × 5 MB on filesystem
tcpdump -ni any -s 0 -C 5 -W 2 -w /tmp/bololo.pcap "host ${DEVICE_IP} and (tcp or udp)"
```

Rotate cap safeguards disk space but not necessarily the observation duration. Manually stop with Ctrl-C. `/tmp` may be tmpfs and memory-limited. Choose an appropriate interface for bridge/offload topology.

At recorded timestamps, test:
1. App refresh / read device status.
2. 30–60 seconds of idle state.
3. Safely change an existing *target* temperature once and restore it.
4. Observe appliance/app acknowledgement and changes.

**Do not test dispensing.** Note whether the device can operate without broadband, and whether the app behaves differently off-LAN, but do not intentionally risk appliance safety.

## 4. Wireshark / tshark checks
Use Wireshark Conversations and endpoint statistics. Filters:

```text
dns
tls.handshake.extensions_server_name
tcp.port == 443
udp.port == 443
tcp.port == 8883
tcp.port == 1883
```

Optional summary (may include sensitive addresses; keep local and sanitize):

```sh
tshark -r bololo.pcap0 -q -z conv,tcp -z conv,udp
```

File names may be `bololo.pcap0`, `bololo.pcap1`, etc., depending on tcpdump platform. TLS is normally encrypted and SNI may not be visible. Port numbers do not prove protocols.

## 5. Optional APK research
Only use the owner's legitimately acquired Android APK and permission. Do not upload APK binaries or secrets into this repo:

```sh
jadx -d bololo-src base.apk
rg -ni 'mqtt|tuya|aliyun|iot|websocket|wss://' bololo-src
```

Class names or strings establish *hypotheses*, not deployment architecture. Focus on model/product selection, cloud endpoints, state schema, authorization flow and supported command set; avoid defeating protections or accessing accounts not owned by the user.

## 6. 实测状态

| 功能 | 状态 | 证据或边界 |
|---|---|---|
| App 云端状态查询 | 已验证 | OpenWrt 用已保存会话读取水温、目标温度、运行状态和出水设定，会话刷新已实测。 |
| 设备端连接 | 已验证 | 网关抓包识别出设备与阿里云 IoT 的 MQTT/TLS 流量。 |
| App 端 MQTT 推送 | 已验证 | 观察到官方 App 登录、订阅和设备上报，OpenWrt 也用同一用户的授权会话独立订阅成功。 |
| 自动记一顿 | 已部署 | 实机抓到出水开始、结束和水量上报。回放测试区分了两笔同量出水。只在收到配对的开始及带水量的结束上报时写入。 |
| 标记瓶重 | 已验证 | 登记瓶重可读，传输值除以 10 得到克重。 |
| 托盘实时克重 | 未证实 | 待机加载对照没有读到随重量变化的克重。 |
| 标准机智云局域网 | 未连通 | 在线设备对常用 UDP 发现端口返回不可达，TCP 会话端口也拒绝连接。 |
| App 云端备奶历史 | 已实机验证 | 已读取设备的备奶时间和出水量，详见 [6.3](#63-读取-app-云端备奶历史)。 |
| 标记模式远程取重 | 已实机验证 | 接受 App 设备分享后，可由 OpenWrt 去皮、取重，并通过 MQTT 读取新克重。喂养网页还未接入该流程。 |

详细配置和自动记录规则见[喂养网页部署说明](../feeding-web/README.md)。

### 6.1 1271W 称重字段边界

官方 Android App 2.1.86 内置的 1271W 产品配置列出 32 个协议数据点。设备云端状态和 App 面板可以对照出以下字段的用途。

| 字段 | 协议用途 |
|---|---|
| `bottle_tag`（21） | 标记奶瓶流程。0 进入标记程序，1 确认托盘去皮，2 确认放瓶。 |
| `new_bottles`（18） | 完成标记后，设备上报分配的奶瓶编号。 |
| `bottle_weight`（27） | 标记时取得的奶瓶重量，传输值除以 10 得到克重。 |
| `bottle_list`（30） | 机器的奶瓶标记列表。每页 17 字节，首字节为页号，其余为 8 个大端 16 位重量。 |
| `bottle_record`（22）和 `record`（25） | 本次出水的奶瓶编号和出水量。 |

App 在提交奶瓶名称之前就等候设备上报编号，随后才把名称和该重量写入云端。现有设备快照中，最近标记的重量已经出现在对应编号的硬件列表中。取消命名后是否会回收标记位尚未验证。已有普通放瓶和取瓶对照日志中，49 次状态读取的标记重量一致。

真机对照确认，使用原版 App 操作时，托盘去皮会推送 `bottle_tag=1`。放入喂后的奶瓶并点击下一步，MQTT 在提交名称前推送新的 `bottle_weight`，云端状态随后也返回相同的读数。本次试验中，`bottle_tag` 回到 0，`new_bottles` 和硬件标记列表均保持原值。不同重量或未登记的奶瓶是否会占用新槽位仍需验证。OpenWrt 会话可读取状态和订阅上报，但复现原版 App 的 HTTP 标记指令时被服务器拒绝（业务码 `2000062`），其绑定及共享设备列表均为空。

另外复测了 App 的主动状态查询（`issueFindStatus`）。当前会话用空对象及其 JSON 字符串发送请求，均收到业务码 `504`，观察窗口内没有新的重量推送，查询到的重量和状态时间保持原值。再次发送标记起始指令也仍收到 `2000062`。在设备待机时，OpenWrt 完成短时 BLE 扫描，未发现与已知设备地址或名称匹配的广播。

按官方 App 的 iOS 应用标识重新完成短信登录，返回的家庭用户 ID 与已有 OpenWrt 会话一致，设备、自有设备和共享设备列表仍为空。这排除了仅切换应用标识或重新签发同一手机号会话即可取得设备绑定的方案。该试验单独使用新会话，既有设备监听仍在线。

后续通过原版 App 生成的单设备分享邀请解决了控制权限。OpenWrt 使用原有会话按 App 的 `singleDeviceShareV2` 流程接受邀请后，目标设备出现在共享设备及用户设备列表。同一会话随后成功依次下发 `bottle_tag=0`（同时清零本次 `new_bottles`）、`bottle_tag=1`（空托盘去皮）、`bottle_tag=2`（放稳奶瓶后取重）。在 MQTT 收到去皮确认和新的 `bottle_weight`，云端状态也返回同一重量，状态回到 0。本次硬件奶瓶槽位未变。这验证了无需在手机 App 点按即可触发单次取重。不同负载的两次称量和可能新增的槽位仍需要对照验证。

两次不同负载对照中，每次均确认空托盘去皮后再放物，由 OpenWrt 触发取重。MQTT 和云端分别一致报出 147.6 g 和 62.5 g。第二次使用了另一件测试物，用户确认读数符合实际重量。这验证了可以读取不同负载的新重量，尚未验证同一奶瓶的喂前喂后差值。第二轮上报的 `new_bottles` 变成新候选编号，复查 `bottle_list` 时对应槽位仍为空。仅凭候选编号不能判断设备已新增永久标记。

这份产品配置没有独立的实时托盘克重或余奶字段。要验证将标记流程用作两次取重，需要同时观测瓶重、编号和硬件列表。只有两次重量都随负载变化且能验证标记位可恢复，才适合考虑进一步集成。定量适配的用途是固定量出水校准。

### 6.2 机身夜灯键作为触发信号

用户短按机身夜灯键后，OpenWrt 在 MQTT 收到 `night_mode`（数据点 28）的即时切换，两种状态 0 和 1 均有实测。设备状态接口随后也反映 `night_mode` 的变化，`night_light`（数据点 31）在本次试验中保持原值。连续切换产生多条上报，任何联动都应限制为一次称重流程，且只在存在待称的备奶记录时启用。

临时监听随后验证了完整流程：空托盘时短按夜灯键，OpenWrt 收到 `night_mode` 切换并发出去皮指令，P50 上报 `bottle_tag=1`。用户放稳奶瓶后，临时监听在去皮确认约 17 秒时自动发出取重指令。MQTT 和云端一致返回 147.9 g，标记状态回到 0，原有奶瓶槽位保持原值。此试验未接入常驻服务或喂养记录。

### 6.3 读取 App 云端备奶历史

在 P50 Pro（1271W）上已验证以下只读查询。它对应原版 App 的 `queryMilkBrewingMachineDetail`，历史类型为 `3`。

1. 使用能访问目标设备的 App 会话。OpenWrt 可复用 `bololo_read_status.py` 的 `APP_ID` 和 `load_session()` 读出的 `session["token"]`，部署默认会话路径为 `/etc/bololo/session.json`。
2. 请求 `GET https://app.bololoapp3.com/app/smartHome/v2/users/devices`，按设备 MAC 或设备 ID 匹配目标条目，取它的 `sno`。接受原版 App 的单设备分享后，同一会话也能在 `GET /app/smartHome/homes/shareDeviceListV2` 找到设备及 `sno`。
3. 请求 `POST https://app.bololoapp3.com/bololo/appdataSata/foam/detail/{sno}/3`。请求体直接发送 JSON，现有 `call()` 会加 `appKey`、`data`、`version` 外层，因此这个 POST 要单独构造。

将 `APP_ID`、`TOKEN` 和 `SNO` 设为上面取到的值。`START_MS`、`END_MS` 是查询起止时间的 Unix 毫秒时间戳。如果按自然日查询，先用当地时区确定日期边界再转为时间戳。

```sh
curl -sS --fail-with-body \
  -H "X-Gizwits-Application-Id: $APP_ID" \
  -H "Authorization: $TOKEN" \
  -H 'Version: 1.0' \
  -H 'Content-Type: application/json' \
  --data-binary "$(printf '{"current":1,"size":999,"query":{"startTime":%s,"endTime":%s}}' "$START_MS" "$END_MS")" \
  "https://app.bololoapp3.com/bololo/appdataSata/foam/detail/$SNO/3"
```

- 检查 HTTP 状态和响应中的业务 `code` 均为 `200`，再读取 `data.records`。`current` 从 `1` 开始，`size` 为每页条数。App 的按日查询会带 `query.babyId`，设备级实测可省略。
- 实测 `total` 和 `pages` 有时只反映当前页，即使 `pages=1` 也可以读到后续页。固定时间范围和 `size`，遇到满页就递增 `current`，读到不足一页或空页时结束。合并时按 `id` 去重。
- `date` 是记录时间，实测格式为 `YYYY-MM-DD HH:mm:ss.SSS`，没有时区后缀。`bottleId` 和 `bottleName` 用于标识奶瓶。把每条的 `data` 字符串解析为 JSON，`waterOutput` 是备奶出水量，单位为 mL。实喝量需另用喂前和喂后称重推算。

## 7. Report template
In `docs/protocol-findings.md`, add only sanitized findings:

```md
## Trial YYYY-MM-DD
- Appliance model / firmware: ...
- Router/AP topology (non-identifying): ...
- Phone network mode: cellular only / LAN
- Action + precise local timestamp: ...
- Observable connection endpoints (redacted as needed): ...
- Transport and protocol (verified vs hypothesis): ...
- Device response/acknowledgement: ...
- Confidence and contradictory observations: ...
- Next experiment: ...
```

**Before publishing anywhere:** remove credentials, cookies, token material, serial numbers, raw device identifiers, private IP/MAC if sensitive, account IDs, and raw capture payloads. Even private repositories should be treated as potentially distributable.
