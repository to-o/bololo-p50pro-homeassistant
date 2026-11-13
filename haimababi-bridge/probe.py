"""Test the paired camera over the Android XP2P SDK on OpenWrt."""

import json
import os
import select
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parent
SESSION_FILE = ROOT / ".session.json"
CAMERA_FILE = ROOT / ".camera.json"
CAMERA_IDENTITY_FILE = ROOT / ".camera-identity.json"
IMAGE = "docker.m.daocloud.io/redroid/redroid@sha256:41e5f0c1ff27a4a474c474e5595168cedf6c40fc5dd102c5617f48c80f511e9e"
CAMERA_IP = os.environ.get("HAIMA_CAMERA_IP", "")
STATUS_FIELDS = (
    "FIRMWARE", "TEMPERATURE", "HUMIDITY", "TEMPERATURE_UNIT", "WIFI_SIGNAL",
    "SD_STATE", "STATE", "SLEEP_TRACKING", "CurAIMode",
)


def save_session(client):
    if not client.user_id or not client.token:
        raise ValueError("Missing authenticated session")
    save_private_json(SESSION_FILE, {"user_id": client.user_id, "token": client.token})


def save_private_json(path, data):
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", dir=ROOT, prefix=f"{path.name}-", delete=False) as output:
            temporary_path = Path(output.name)
            json.dump(data, output)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def objects(value):
    for _ in range(3):
        if not isinstance(value, str) or not value.lstrip().startswith(("{", "[", '"')):
            break
        try:
            value = json.loads(value)
        except ValueError:
            return
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def connection_parameters(client, device):
    product_id = str(device["productId"])
    device_name = str(device["p2pDeviceName"])
    device_id = str(device["deviceId"])
    credentials, token = client.call(
        "aibind/agora/bind/getScP2pInfo",
        {"deviceName": device_name, "productId": product_id, "secret": client.user_id},
        request_type=2,
    )
    if credentials.get("is_success") == 500713:
        client.auth_expired = True
    if token and credentials.get("is_success") == 1:
        client.token = token
        save_session(client)
    xp2p_info = next(
        (
            item["_sys_xp2p_info"]["Value"]
            for item in objects(credentials.get("data"))
            if isinstance(item.get("_sys_xp2p_info"), dict)
            and item["_sys_xp2p_info"].get("Value")
        ),
        None,
    )
    return (device_id, product_id, device_name, xp2p_info), credentials.get("is_success")


@contextmanager
def worker(parameters):
    if any(not isinstance(value, str) or not value or "\n" in value or "\r" in value for value in parameters):
        raise ValueError("Invalid XP2P parameters")
    command = [
        "docker", "run", "--rm", "-i", "--network", "host", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--log-driver", "none",
        "--entrypoint", "/system/apex/com.android.runtime/bin/linker64",
        "-e", "LD_LIBRARY_PATH=/system/apex/com.android.runtime/lib64/bionic:/system/lib64",
        "-v", f"{ROOT / 'xp2p-worker'}:/bridge/xp2p-worker:ro",
        "-v", f"{ROOT / 'libiot_video_demo.so'}:/bridge/libiot_video_demo.so:ro",
        IMAGE, "/bridge/xp2p-worker",
    ]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0) as proc:
        try:
            proc.stdin.write(("\n".join(parameters) + "\n").encode())
            yield proc
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)


def worker_lines(proc, seconds):
    deadline = time.monotonic() + seconds
    buffer = b""
    while (remaining := deadline - time.monotonic()) > 0:
        if not select.select([proc.stdout], [], [], remaining)[0]:
            break
        data = os.read(proc.stdout.fileno(), 65536)
        if not data:
            break
        buffer += data
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")


def open_flv(proxy_url, device_id):
    url = urlsplit(proxy_url)
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "0.0.0.0") or not url.port:
        raise ValueError("The SDK did not return a local HTTP proxy")
    query = dict(parse_qsl(url.query))
    query.update({"action": "live", "channel": 0, "quality": "standard", "user_args": device_id})
    endpoint = f"http://127.0.0.1:{url.port}{url.path.rstrip('/')}/ipc.flv?{urlencode(query)}"
    return build_opener(ProxyHandler({})).open(endpoint, timeout=12)


def inspect_flv(proxy_url, device_id):
    with open_flv(proxy_url, device_id) as response:
        header = response.read(9)
        if len(header) != 9 or not header.startswith(b"FLV"):
            return False, False
        data_offset = int.from_bytes(header[5:9], "big")
        if not 9 <= data_offset <= 4096:
            return True, False
        response.read(data_offset - 9 + 4)
        for _ in range(80):
            tag = response.read(11)
            if len(tag) != 11:
                break
            length = int.from_bytes(tag[1:4], "big")
            if not 0 < length <= 2_000_000:
                break
            payload = response.read(length)
            response.read(4)
            if tag[0] == 9 and len(payload) == length and length > 8:
                is_frame = payload[0] & 0x0f in (1, 3) if payload[0] & 0x80 else payload[1] == 1
                if is_frame:
                    return True, True
        return True, False


def prepare_camera(client):
    result = {}
    if CAMERA_FILE.is_file():
        return json.loads(CAMERA_FILE.read_text()), result
    if not client.user_id or client.auth_expired:
        return None, {"stage": "authorization_required"}
    if CAMERA_IDENTITY_FILE.is_file():
        device = json.loads(CAMERA_IDENTITY_FILE.read_text())
        if device.get("accountId") == client.user_id and device.get("productId") and device.get("p2pDeviceName"):
            return cache_connection(client, device, result)
    devices = client.devices or {}
    items = [
        item for item in objects(devices.get("data"))
        if all(item.get(key) for key in ("productId", "p2pDeviceName", "deviceId"))
    ]
    result["tencent_devices"] = len(items)
    matching = [
        item for item in items
        if "SC-AI18" in str(item.get("model", "")).upper()
        or (os.environ.get("HAIMA_P2P_NAME") and os.environ["HAIMA_P2P_NAME"] == str(item["p2pDeviceName"]))
    ]
    candidates = matching or items
    if not candidates and devices.get("is_success") == 1:
        bound = [item for item in objects(devices.get("data")) if item.get("deviceId")]
        if len(bound) == 1:
            device = bound[0]
            save_private_json(CAMERA_IDENTITY_FILE, {
                "deviceId": str(device["deviceId"]), "deviceType": device.get("deviceType") or 338,
                "accountId": client.user_id,
            })
            if device.get("deviceType") in (336, 337, 338):
                return None, {"stage": "agora_live", "device_type": device["deviceType"]}
            detail, token = client.call(
                "aibind/agora/bind/getTencentDeviceByUserId",
                {"userId": client.user_id, "deviceId": str(device["deviceId"])},
                request_type=2,
            )
            if detail.get("is_success") == 500713:
                client.auth_expired = True
            if token and detail.get("is_success") == 1:
                client.token = token
                save_session(client)
            result["tencent_detail_code"] = detail.get("is_success")
            for item in objects(detail):
                p2p_name = item.get("p2pDeviceName") or item.get("deviceName")
                if item.get("productId") and p2p_name:
                    candidates = [{**device, "productId": item["productId"], "p2pDeviceName": p2p_name}]
                    break
            if not candidates:
                result["bound_device_type"] = device.get("deviceType")
                if isinstance(detail.get("data"), int):
                    result["tencent_detail_state"] = detail["data"]
                result["detail_schema"] = [
                    {key: type(value).__name__ for key, value in item.items()}
                    for item in objects(detail)
                ][:8]
    if len(candidates) == 1:
        device = candidates[0]
        result["cloud_status"] = {
            key: device[key] for key in ("deviceType", "babyState", "babyMode", "wifiStrength", "wifiQuality")
            if isinstance(device.get(key), (str, int, bool))
        }
        identity = {key: str(device[key]) for key in ("deviceId", "productId", "p2pDeviceName")}
        identity["accountId"] = client.user_id
        identity["deviceType"] = device.get("deviceType") or 338
        save_private_json(CAMERA_IDENTITY_FILE, identity)
        return cache_connection(client, identity, result)
    result["stage"] = "select_camera"
    return None, result


def cache_connection(client, identity, result):
    params, code = connection_parameters(client, identity)
    result["xp2p_info_code"] = code
    if params[3]:
        save_private_json(CAMERA_FILE, list(params))
        return params, result
    result["stage"] = "xp2p_info"
    return None, result


def wait_for_proxy(lines, result):
    result["stage"] = "sdk_proxy"
    for line in lines:
        if line.startswith("XP2P start returned "):
            result["sdk_start_code"] = int(line.rsplit(" ", 1)[-1])
        if line.startswith("XP2P_PROXY "):
            return line[len("XP2P_PROXY "):].strip()
    return None


def read_camera_status(proc, result, lines=None):
    proc.stdin.write(b"action=user_define&channel=0&cmd=CHECK_ONLINE,\n")
    for line in lines if lines is not None else worker_lines(proc, 8):
        if not line.startswith("XP2P_STATUS "):
            continue
        _, status, body = line.split(" ", 2)
        result["device_command_code"] = int(status)
        try:
            fields = json.loads(body)
        except ValueError:
            return
        result["device_status"] = {
            key: item[key] for item in objects(fields) for key in STATUS_FIELDS
            if isinstance(item.get(key), (str, int, float, bool))
        }
        return


def device_status(params):
    ping = subprocess.run(
        ["ping", "-c", "1", "-W", "1", CAMERA_IP],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
    ) if CAMERA_IP else None
    result = {"lan_ping_reply": ping.returncode == 0 if ping else None, "camera_binding_saved": bool(params)}
    if params:
        with worker(params) as proc:
            if wait_for_proxy(worker_lines(proc, 30), result):
                result["stage"] = "check_online"
                read_camera_status(proc, result)
    return result


@contextmanager
def live_stream(params):
    with worker(params) as proc:
        if not (proxy := wait_for_proxy(worker_lines(proc, 30), {})):
            raise OSError("XP2P proxy unavailable")
        with open_flv(proxy, params[0]) as response:
            header = response.read(9)
            if len(header) != 9 or not header.startswith(b"FLV"):
                raise ValueError("Invalid FLV header")
            yield header, response


def probe(client):
    with client.camera_setup_lock:
        params, result = prepare_camera(client)
    result.update({"session_saved": SESSION_FILE.is_file(), "flv": False})
    if not params:
        return result
    result["camera_binding_saved"] = True
    with worker(params) as proc:
        lines = worker_lines(proc, 30)
        proxy_url = wait_for_proxy(lines, result)
        if not proxy_url:
            return result
        result["stage"] = "stream"
        try:
            result["flv"], result["video_frame"] = inspect_flv(proxy_url, params[0])
        except HTTPError as error:
            result["stream_http"] = error.code
        except OSError:
            result["stream_timeout"] = True
        read_camera_status(proc, result)
    return result
