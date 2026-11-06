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

## 6. Evidence matrix (update after tests)

| Claim | Status | Evidence | Next test |
|---|---|---|---|
| BOLOLO App controls P50 Pro over cellular-only phone connection | Owner-reported verified | Phone Wi-Fi + Bluetooth off, control still works | Repeat and timestamp |
| Device uses specific cloud service | Unknown | None | Correlate device IP flows with actions |
| Device supports local IP commands | Unknown | None | Passive observation / documented endpoint discovery |
| MQTT is used | Unknown | None | Confirm handshake/protocol, not port alone |
| Current temperature field exists | Unknown | None | Establish actual schema |
| Target temperature write available to HA | Unknown | None | Confirm protocol and safety bounds |

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
