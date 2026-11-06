# BOLOLO P50 Pro × Home Assistant

Connect a BOLOLO (波咯咯) P50 Pro smart formula-water appliance to Home Assistant. **Research-stage project; device protocol and API have not yet been validated.**

## Confirmed by the device owner
- The appliance is a **BOLOLO P50 Pro**.
- The official BOLOLO phone app can control it.
- The app **still controls the appliance when the phone has Wi-Fi and Bluetooth turned off and uses cellular data only**.
- Home Assistant is already deployed in an **OpenWrt** environment.
- The GitHub repository is private; Codex may implement directly on `main`.

## What is *not* confirmed
- Whether the appliance has a local Wi-Fi or Bluetooth API.
- Whether it uses MQTT, HTTPS, WebSockets, a proprietary protocol, or a third-party cloud platform.
- Cloud endpoint addresses, authentication formats, device IDs, payload formats, supported attributes, temperature limits, and command semantics.
- Whether OpenWrt is the appliance's actual network gateway.
- Whether any ready-made Home Assistant integration works with this model.

**Cellular-only app control suggests remote/cloud-mediated control, but it is not proof of any particular protocol.**

## Goal
Deliver a small, reproducible Home Assistant integration that supports **verified** device functions. Prefer local control if demonstrably available; otherwise evaluate an authorized cloud interface.

Priority:
1. Discover device address, routing topology, endpoints, and protocol with reproducible evidence.
2. Read verified properties (water temperature, heating mode, online status) only if actually provided by device.
3. Set target temperature only after identifying and validating a safe, legitimate command.
4. Integrate with Home Assistant via the simplest sustainable design: MQTT Discovery bridge **or** native custom integration; don't build both prematurely.
5. Test reconnection, retries, cloud outages, stale values, and device unavailability.

Out of scope for the first milestone: automatic water dispensing, bypassing the appliance's remote-lock/safety mechanisms, and making up unverified entities or APIs.

## Codex entrypoint
Start with [AGENTS.md](AGENTS.md), then [docs/CODEX_TASKS.md](docs/CODEX_TASKS.md) and [docs/PROTOCOL_RESEARCH.md](docs/PROTOCOL_RESEARCH.md). Develop directly on `main` as requested.

**Important:** There are no device captures, APKs, tokens, or credentials in this repo yet. Do not claim device integration works without live-device evidence. Build offline-testable diagnostics and leave evidence-gated tasks clearly marked as blocked until the owner supplies redacted data.

## Minimal OpenWrt procedure
Run as the owner on the actual network gateway or access point (not on an unrelated router):

```sh
cat /tmp/dhcp.leases
ip neigh show
ip -br addr
```

Confirm the actual P50 Pro IP and route. Replace the example address below:

```sh
DEVICE_IP=192.168.1.150
tcpdump -ni any "host ${DEVICE_IP} and (tcp or udp)"
# Separate bounded collection; stop with Ctrl-C after app observations:
tcpdump -ni any -s 0 -C 5 -W 2 -w /tmp/bololo.pcap "host ${DEVICE_IP} and (tcp or udp)"
```

On the phone, record timestamps while refreshing status and **safely** changing/restoring the desired water temperature. Do **not** trigger dispensing. The `-C 5 -W 2` options limit rotated capture sizes; check device disk/RAM space first. Pcap files can include sensitive network metadata—do not commit raw captures.

## Security and safety
- Never commit passwords, tokens, proprietary firmware/APK dumps, unredacted capture files, user/device identifiers, or secrets.
- Keep authentication in environment variables or user-managed secrets; no embedded credentials.
- Respect the real appliance's safety interlocks and avoid unattended dispensing commands.
- Use mock/sanitized fixtures for CI, and document all real-device tests separately.
- Do not bypass account protection or inspect traffic/devices not owned or authorized by the user.

## Current milestone
**M0: Evidence-based protocol identification and an offline-testable scaffold.** See [Codex tasks](docs/CODEX_TASKS.md).
