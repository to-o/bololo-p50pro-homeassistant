# Protocol discovery runbook

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
| 原版历史回补 | 待验证 | 找到 App 的明细请求结构。现有会话没有返回该请求所需的设备绑定编号。 |
| HA 写入或控制 | 待验证 | 当前客户端只读取状态、续期和订阅。 |

详细配置和自动记录规则见[喂养网页部署说明](../feeding-web/README.md)。

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
