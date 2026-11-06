# Codex implementation plan

**Target:** BOLOLO P50 Pro ↔ Home Assistant (Home Assistant runs on OpenWrt). **Default branch:** `main`; **no PR**.

## Facts
- Device owner can remotely control P50 Pro with official BOLOLO App over cellular while Wi-Fi/Bluetooth are disabled on phone.
- This is compatible with cloud relay, but no cloud API, local protocol, or protocol provider is confirmed.
- No sanitized packet captures, API schema, APK analysis, or device credentials have been supplied.

## M0 — Prepare reproducible, safe diagnostics (Codex can do this now)
- [ ] Inspect repo and related open-source integrations, documenting *evidence-backed* applicability to P50 Pro.
- [ ] Provide a compact OpenWrt diagnostics script, configurable by device IP, that inventories interfaces/routes and collects metadata and **bounded** filtered captures only after explicit invocation.
- [ ] Make script refuse absent or invalid IP, check `tcpdump`, avoid capturing unrelated hosts, ensure cleanup/CTRL-C behavior, and never print secrets.
- [ ] Provide a local offline analyzer for the capture's **metadata** (endpoints, ports, timestamps, DNS if observable, transport statistics). Prefer available tools; don't pretend to decrypt TLS.
- [ ] Add clear runbook for safely exporting an evidence summary (redacted endpoints, timestamps and domains as needed; no unredacted pcaps in Git).
- [ ] Document optional, user-supplied Android APK static analysis as a *separate* step; never assume an APK exists.
- [ ] Add unit tests with explicitly synthetic traffic metadata; include sample commands and expected output.
- [ ] Update research matrix in `docs/PROTOCOL_RESEARCH.md` with evidence, confidence, and unanswered questions.
- [ ] Keep all changes on `main`.

**M0 acceptance:** owner can run documented commands on their gateway/AP and obtain a sanitized research report; offline tests pass; nothing secret is committed.

## M1 — Protocol proof of concept (blocked on user-provided evidence)
- [ ] Verify actual topology and device IP, repeatable status-read traffic, and server(s) involved.
- [ ] Establish whether there is a usable local interface, officially authorized cloud API, or authorized session-based communication.
- [ ] Determine request/response or publish/subscribe semantics from **actual evidence**, not port guesses.
- [ ] Define a small `ProtocolClient` interface only after transport is verified; implement a read-only `get_status` PoC.
- [ ] Test using device-owner-approved credentials/configuration; never commit them.
- [ ] Record device model, firmware (if available), experimental steps, errors, and confidence in `docs/protocol-findings.md`.

**M1 acceptance:** repeatable non-invasive device status read on owner device, with documented reliability and no secret leakage.

## M2 — Home Assistant MVP (blocked on M1)
- [ ] Choose **either** a minimal MQTT Discovery bridge or a native HA custom integration. Prefer fewer moving parts given OpenWrt resource constraints.
- [ ] Expose only verified entities (temperature, status, heating, etc.); stable unique IDs, units and availability semantics.
- [ ] State handling for disconnected device, expired authentication, reconnect/retry with bounded backoff.
- [ ] Provide installation instructions for OpenWrt + HA and integration tests with synthetic/mocked data.
- [ ] Target-temperature writes only after validated range/step/acknowledgment semantics and user sign-off.
- [ ] Do not implement remote dispensing, ignore/unlock interlocks, or default to potentially unsafe actions.

**M2 acceptance:** Home Assistant accurately displays **verified** properties, robustly handles lost connectivity, and reports unknown rather than fabricating stale measurements.

## Implementation constraints
- Minimal Python, explicit configuration and tests.
- No assumption about MQTT, Tuya, Alibaba IoT, HTTP(S), WebSocket or BLE until proven.
- Distinguish a real-device pass from an offline mock pass.
- No over-engineered frameworks or speculative code.
- Update README / AGENTS / checklist as actual evidence develops.

## Next information required from owner
1. OpenWrt interface and the P50 Pro private IP/address path (share redacted).
2. Time-aligned filtered packet-capture metadata while app refreshes state / adjusts *target temperature only*.
3. If warranted, Android app APK from owner's lawful source and a sanitized analysis.
4. Permission for a later non-dangerous read-only live test.

Stop at evidence boundary; do not infer API schema from documentation templates.
