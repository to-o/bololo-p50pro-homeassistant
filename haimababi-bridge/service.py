"""Local setup service for a paired SC-AI18 camera."""

import base64
import hashlib
import hmac
import html
import json
import secrets
import subprocess
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from runpy import run_path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


BASE_URL = "https://hmbaby.simshine.cn/"
PORT = 18874
CONFIG = Path(__file__).with_name("protocol.json")
SESSION = Path(__file__).with_name(".session.json")
CAPTCHA_SCRIPT = Path(__file__).with_name("ct4.js")
ASSETS = Path(__file__).parent
CAMERA_IDENTITY = ASSETS / ".camera-identity.json"
CAPTCHA_ID = "128cd93a6b8d582e3d066acbad4cf6e5"
NEW_DEVICE_VERIFICATION = 500616
STATUS_COMMANDS = ("CHECK_ONLINE", "GetAIMode", "GET_MP3_PLAYINFO")
COMMAND_SWAPS = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def status_queries(license_key, phone):
    if not isinstance(license_key, str) or len(license_key) < 20 or not license_key.isascii():
        return []
    queries = []
    for command in STATUS_COMMANDS:
        encoded = base64.b64encode(command.encode("ascii")).decode("ascii")
        permuted = [license_key[2]]
        for offset in range(0, len(encoded), 4):
            key = ord(license_key[(offset // 4) % len(license_key)])
            first, second = key % 6, (key // 10) % 6
            if first == second:
                first = (first + 1) % 6
            block = list(encoded[offset:offset + 4])
            for index in (first, second):
                left, right = COMMAND_SWAPS[index]
                block[left], block[right] = block[right], block[left]
            permuted.extend(block)
        queries.append({
            "mid": str(uuid4()),
            "cmd_type": "IPCAM_CMD",
            "data": {"cmd": "".join(permuted) + "," + phone},
        })
    return queries


class HaimaClient:
    def __init__(self, config):
        self.agora_aes_key = config.get("agora_aes_key")
        self.agora_command_account = config.get("agora_command_account") or {}
        self.key = config["aes_key"]
        self.iv = config["aes_iv"]
        self.sign_suffix = bytes.fromhex(config["sign_suffix"])
        self.device_id = config["device_id"]
        self.user_id = ""
        self.token = ""
        self.devices = None
        self.auth_expired = False
        self.camera_setup_lock = threading.Lock()

    def _envelope(self, parameters, request_type):
        body = f"{urlencode(parameters)}&reqType={request_type}&timestamp={int(time.time())}"
        signature = hashlib.md5(body.encode() + self.sign_suffix).hexdigest()
        ciphertext = subprocess.run(
            ["openssl", "enc", "-aes-128-cbc", "-K", self.key, "-iv", self.iv],
            input=f"{body}&sign={signature}".encode(),
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
        return base64.b64encode(base64.b64encode(ciphertext)).decode("ascii")

    def call(self, path, parameters, request_type):
        request = Request(
            BASE_URL + path,
            data=urlencode({"data": self._envelope(parameters, request_type)}).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "token": self.token,
                "secret": self.user_id,
                "lang": "cn",
                "appType": "1",
                "ua": "0",
                "version": "1.0.9(0930a)",
            },
        )
        with urlopen(request, timeout=12) as response:
            token = response.headers.get("token", "")
            result = json.loads(response.read(512_000))
        if not isinstance(result, dict):
            raise ValueError("Unexpected vendor response")
        return result, token

    def login(self, phone, password, code=""):
        parameters = {
            "phone": phone,
            "pwd": password,
            "phoneType": "0",
            "channel": "oss",
            "model": "Android",
            "uniqueDevice": self.device_id,
        }
        if code:
            parameters["code"] = code
        result, token = self.call(
            "user/api/auth/v1/v2/login",
            parameters,
            request_type=1,
        )
        data = result.get("data")
        if isinstance(data, str):
            data = json.loads(data)
        if result.get("is_success") == 1 and isinstance(data, dict) and data.get("userId"):
            self.user_id = str(data["userId"])
            self.token = token or str(data.get("token") or "")
            self.auth_expired = False
            return 1, "已登录海马爸比。"
        code = result.get("is_success", result.get("code", "?"))
        return code, f"{result.get('msg') or '登录失败'}（{code}）"

    def send_verification(self, phone, captcha):
        result, _ = self.call(
            "user/sms/sendVerify",
            {
                "phone": phone,
                "type": "5",
                "captchaId": CAPTCHA_ID,
                "lotNumber": captcha["lot_number"],
                "captchaOutput": captcha["captcha_output"],
                "passToken": captcha["pass_token"],
                "genTime": captcha["gen_time"],
            },
            request_type=1,
        )
        sent = result.get("is_success") == 1
        return sent, "请输入收到的短信验证码。" if sent else str(result.get("msg") or "短信发送失败。")

    def refresh_devices(self):
        try:
            result, token = self.call(
                "aibind/agora/bind/getDeviceByUserId",
                {"userId": self.user_id},
                request_type=2,
            )
        except (URLError, OSError, ValueError, subprocess.SubprocessError):
            return
        self.auth_expired = result.get("is_success") == 500713
        if token and not self.auth_expired:
            self.token = token
            self.save_session()
        self.devices = result
        if result.get("is_success") == 1:
            try:
                with self.camera_setup_lock:
                    run_path(str(Path(__file__).with_name("probe.py")))["prepare_camera"](self)
            except (URLError, OSError, ValueError, subprocess.SubprocessError):
                pass

    def save_session(self):
        if self.user_id and self.token:
            return run_path(str(Path(__file__).with_name("probe.py")))["save_session"](self)

    def restore_session(self):
        try:
            saved = json.loads(SESSION.read_text())
            self.user_id = str(saved["user_id"])
            self.token = str(saved["token"])
        except (OSError, ValueError, TypeError, KeyError):
            return False
        return bool(self.user_id and self.token)

    def probe(self):
        probe_script = Path(__file__).with_name("probe.py")
        return run_path(str(probe_script))["probe"](self)

    def recent_events(self, day, page):
        with self.camera_setup_lock:
            if self.auth_expired or not self.user_id:
                return {"error": "authorization_required"}, 503
            camera = run_path(str(Path(__file__).with_name("probe.py")))
            identity_file = camera["CAMERA_IDENTITY_FILE"]
            if not identity_file.is_file():
                return {"error": "camera_binding_required"}, 503
            identity = json.loads(identity_file.read_text())
            if identity.get("accountId") != self.user_id:
                return {"error": "camera_binding_required"}, 503
            result, token = self.call(
                "event/event/v2/getBabyEventsByDeviceId",
                {"deviceId": identity["deviceId"], "deviceType": str(identity["deviceType"]),
                 "findDate": day, "pageNum": str(page), "pageSize": "10"},
                request_type=2,
            )
            code = result.get("is_success")
            if code == 500713:
                self.auth_expired = True
                return {"error": "authorization_required", "vendor_code": code}, 503
            if code != 1:
                return {"error": "event_query_failed", "vendor_code": code}, 502
            if token:
                self.token = token
                self.save_session()
            data = result.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                return {"error": "invalid_event_response"}, 502
            fields = ("eventId", "eventType", "eventTime", "eventName")
            events = [{key: item[key] for key in fields if isinstance(item.get(key), (str, int))}
                      for item in data["data"] if isinstance(item, dict)]
            return {"date": day, "page": page, "total": data.get("total"), "events": events}, 200

    def sleep_report(self, day, weekly):
        if weekly:
            days = [day - timedelta(days=offset) for offset in range(6, -1, -1)]
            parameters = {"weekTimes": ",".join(item.isoformat() for item in days)}
            endpoint = "getWeekSleepInfo"
        else:
            parameters = {"begin": f"{day} 08:00:00", "end": f"{day + timedelta(days=1)} 08:00:00"}
            endpoint = "getBabyReport"

        with self.camera_setup_lock:
            if self.auth_expired or not self.user_id:
                return {"error": "authorization_required"}, 503
            if not CAMERA_IDENTITY.is_file():
                return {"error": "camera_binding_required"}, 503
            identity = json.loads(CAMERA_IDENTITY.read_text())
            if identity.get("accountId") != self.user_id:
                return {"error": "camera_binding_required"}, 503
            result, token = self.call(
                f"event/app/baby/20210331/{endpoint}",
                {"deviceId": identity["deviceId"], **parameters},
                request_type=2,
            )
            code = result.get("is_success")
            if code == 500713:
                self.auth_expired = True
                return {"error": "authorization_required", "vendor_code": code}, 503
            if code != 1:
                return {"error": "sleep_report_failed", "vendor_code": code}, 502
            if token:
                self.token = token
                self.save_session()

        data = result.get("data")
        if not isinstance(data, list if weekly else dict):
            return {"error": "invalid_sleep_report"}, 502
        return {"date": day.isoformat(), **parameters, "report": data}, 200

    def agora_session(self):
        with self.camera_setup_lock:
            if self.auth_expired or not self.user_id:
                return {"error": "authorization_required"}, 503
            identity_file = CAMERA_IDENTITY
            if not identity_file.is_file():
                return {"error": "camera_binding_required"}, 503
            identity = json.loads(identity_file.read_text())
            if identity.get("accountId") != self.user_id or identity.get("deviceType") not in (336, 337, 338):
                return {"error": "agora_camera_required"}, 503
            detail, token = self.call(
                "aibind/agora/bind/getAgroDeviceByUserId",
                {"userId": self.user_id, "deviceId": identity["deviceId"]},
                request_type=2,
            )
            if detail.get("is_success") == 500713:
                self.auth_expired = True
                return {"error": "authorization_required"}, 503
            app_id = detail.get("data", {}).get("appId") if isinstance(detail.get("data"), dict) else None
            if detail.get("is_success") != 1 or not app_id:
                return {"error": "agora_device_unavailable"}, 502
            if token:
                self.token = token
                self.save_session()
            response, token = self.call(
                "aibind/agora/bind/initAgora",
                {"userId": self.user_id, "deviceId": identity["deviceId"], "appId": app_id, "initType": "LIVE"},
                request_type=2,
            )
            code = response.get("is_success")
            if code == 500713:
                self.auth_expired = True
                return {"error": "authorization_required"}, 503
            data = response.get("data")
            fields = ("rtcToken", "channelName", "deviceRtcUid", "userRtcUid")
            if code != 1 or not isinstance(data, dict) or any(field not in data for field in fields):
                return {"error": "agora_init_failed", "vendor_code": code}, 502
            if token:
                self.token = token
                self.save_session()
            if not self.agora_aes_key:
                return {"error": "agora_key_missing"}, 503
            ciphertext = base64.b64decode(base64.b64decode(data["rtcToken"], validate=True), validate=True)
            rtc_token = subprocess.run(
                ["openssl", "enc", "-d", "-aes-128-cbc", "-K", self.agora_aes_key,
                 "-iv", b"16-Bytes--String".hex()],
                input=ciphertext, capture_output=True, timeout=5, check=True,
            ).stdout.decode("ascii")
            if not rtc_token.startswith(("006", "007")) or (
                rtc_token.startswith("006") and rtc_token[3:35] != app_id
            ):
                return {"error": "invalid_agora_token"}, 502
            session = {
                "appId": app_id,
                "rtcToken": rtc_token,
                "channelName": data["channelName"],
                "deviceRtcUid": data["deviceRtcUid"],
                "userRtcUid": data["userRtcUid"],
            }
            command_account = self.agora_command_account
            phone = command_account.get("phone")
            if command_account.get("user_id") == self.user_id and isinstance(phone, str) and phone.isascii() and phone.isdigit():
                session["statusQueries"] = status_queries(detail["data"].get("license"), phone)
            if data.get("t"):
                salt = base64.b64decode(data["t"], validate=True)
                if len(salt) < 32:
                    return {"error": "invalid_agora_media_salt"}, 502
                device_id = identity["deviceId"]
                session["mediaKey"] = hashlib.md5(device_id.encode()).hexdigest() + device_id
                session["mediaSalt"] = base64.b64encode(salt[:32]).decode("ascii")
            return session, 200


class SetupHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, *args):
        pass

    def send_body(self, body, content_type, status=200, captcha_nonce=None, preview=False):
        content = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        policy = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
        if captcha_nonce:
            policy = policy.replace("style-src 'unsafe-inline'", "style-src 'unsafe-inline' https://*.alicaptcha.com https://*.geetest.com")
            policy += (
                f"; script-src 'self' 'nonce-{captcha_nonce}' 'unsafe-eval' https://*.alicaptcha.com https://*.geetest.com"
                "; connect-src 'self' https://*.alicaptcha.com https://*.geetest.com"
                "; img-src data: blob: https://*.alicaptcha.com https://*.geetest.com"
                "; font-src data: https://*.alicaptcha.com https://*.geetest.com"
            )
        elif preview:
            policy += "; script-src 'self'; connect-src 'self' https: wss:; media-src 'self' blob:; worker-src 'self' blob:"
        self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        self.wfile.write(content)

    def page(self):
        message = html.escape(self.server.message)
        csrf = self.server.csrf
        nonce = None
        if self.server.client.auth_expired and not self.server.pending:
            message = "海马爸比后台已判定保存的会话过期。"
        if self.server.client.user_id and not self.server.client.auth_expired:
            form = ""
        elif self.server.pending:
            form = f"""
          <form action="/verify" method="post">
            <input type="hidden" name="csrf" value="{csrf}">
            <label>短信验证码<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{4,8}}" required></label>
            <button>验证并登录</button>
          </form>"""
            if not self.server.sms_sent:
                nonce = secrets.token_urlsafe(18)
                form = f"""
          <div id="captcha"></div><button id="send" disabled>验证并发送短信</button>
          <script src="/ct4.js"></script><script nonce="{nonce}">
          const send = document.querySelector("#send");
          const status = document.querySelector("[role=status]");
          initAlicom4({{captchaId: "{CAPTCHA_ID}", product: "bind", language: "zh", protocol: "https://"}}, (captcha) => {{
            captcha.appendTo("#captcha").onReady(() => {{
              send.disabled = false;
              send.onclick = () => (captcha.showCaptcha || captcha.showBox).call(captcha);
            }}).onSuccess(async () => {{
              const proof = captcha.getValidate();
              if (!proof) return;
              send.disabled = true;
              try {{
                await fetch("/captcha", {{method: "POST", body: new URLSearchParams({{...proof, csrf: "{csrf}"}})}});
                location.reload();
              }} catch {{
                status.textContent = "验证码提交失败，请刷新重试。";
                send.disabled = false;
              }}
            }}).onError(() => {{ status.textContent = "人机验证加载失败，请刷新页面。"; }});
          }});
          </script>""" + form
        else:
            form = f"""
          <form action="/login" method="post">
            <input type="hidden" name="csrf" value="{csrf}">
            <label>手机号<input name="phone" inputmode="tel" autocomplete="username" required></label>
            <label>海马爸比密码<input name="password" type="password" autocomplete="current-password" required></label>
            <button>登录并验证</button>
          </form>"""
        self.send_body(f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>海马爸比桥接</title><style>
body{{font:16px system-ui,sans-serif;background:#f3f6fa;color:#18314a;margin:0}}
main{{max-width:26rem;margin:12vh auto;padding:2rem;background:white;border:1px solid #d6e0ec;border-radius:1rem}}
h1{{margin:0 0 1rem;font-size:1.5rem}} label{{display:block;margin-top:1rem}}
input:not([type=hidden]),button{{box-sizing:border-box;width:100%;padding:.75rem;border-radius:.5rem;font:inherit}}
input{{border:1px solid #9bacbf;margin-top:.35rem}} button{{border:0;background:#205598;color:white;margin-top:1.25rem}}
</style><main><h1>海马爸比桥接</h1><p>SC-AI18 · 本机连接</p>
<p role="status">{message}</p>{form}</main></html>""", "text/html; charset=utf-8", captcha_nonce=nonce)

    def do_GET(self):
        if self.headers.get("Host") not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            self.send_error(400)
            return
        url = urlsplit(self.path)
        if url.path == "/events":
            self.serve_events(url.query)
        elif url.path in ("/sleep/daily", "/sleep/weekly"):
            self.serve_sleep_report(url.query, weekly=url.path == "/sleep/weekly")
        elif self.path == "/status":
            client = self.server.client
            devices = client.devices or {}
            data = devices.get("data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except ValueError:
                    data = None
            status = {
                "authenticated": bool(client.user_id) and not client.auth_expired,
                "has_token": bool(client.token),
                "session_saved": SESSION.is_file(),
                "camera_binding_saved": CAMERA_IDENTITY.is_file() or SESSION.with_name(".camera.json").is_file(),
                "verification_required": bool(self.server.pending),
                "sms_sent": self.server.sms_sent,
                "device_list_code": devices.get("is_success"),
                "device_count": len(data) if isinstance(data, list) else None,
            }
            self.send_body(json.dumps(status), "application/json")
        elif self.path == "/":
            self.page()
        elif self.path == "/ct4.js":
            self.send_body(CAPTCHA_SCRIPT.read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/preview":
            self.send_body((ASSETS / "preview.html").read_bytes(), "text/html; charset=utf-8", preview=True)
        elif self.path in ("/agora-sdk.js", "/preview.js"):
            self.send_body((ASSETS / self.path[1:]).read_bytes(), "text/javascript; charset=utf-8")
        elif self.path in ("/device/status", "/live.flv"):
            self.serve_camera()
        elif self.path == "/probe" and self.server.client.user_id:
            try:
                with self.server.probe_lock:
                    result = self.server.client.probe()
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                result = {"error": "取流探测未完成"}
            self.send_body(json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self.send_error(404)

    def send_json(self, data, status=200):
        self.send_body(json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8", status)

    def serve_events(self, query):
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_error(403)
            return
        args = parse_qs(query)
        try:
            day = date.fromisoformat(args.get("date", [""])[0]).isoformat()
            page = int(args.get("page", ["1"])[0])
            if not 1 <= page <= 1000:
                raise ValueError("page out of range")
        except ValueError:
            self.send_json({"error": "invalid_date_or_page"}, 400)
            return
        try:
            result, status = self.server.client.recent_events(day, page)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            result, status = {"error": "event_query_failed"}, 502
        self.send_json(result, status)

    def serve_sleep_report(self, query, weekly):
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_error(403)
            return
        try:
            day = date.fromisoformat(parse_qs(query).get("date", [""])[0])
        except ValueError:
            self.send_json({"error": "invalid_date"}, 400)
            return
        try:
            result, status = self.server.client.sleep_report(day, weekly)
        except OverflowError:
            result, status = {"error": "invalid_date"}, 400
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            result, status = {"error": "sleep_report_failed"}, 502
        self.send_json(result, status)

    def serve_camera(self):
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_error(403)
            return
        if not self.server.probe_lock.acquire(blocking=False):
            self.send_json({"error": "camera_busy"}, 409)
            return
        started = False
        try:
            camera = run_path(str(Path(__file__).with_name("probe.py")))
            binding = camera["CAMERA_FILE"]
            params = json.loads(binding.read_text()) if binding.is_file() else None
            if self.path == "/device/status":
                self.send_json(camera["device_status"](params))
            elif not params:
                self.send_json({"error": "camera_binding_required"}, 503)
            else:
                with camera["live_stream"](params) as (header, response):
                    self.send_response(200)
                    self.send_header("Content-Type", "video/x-flv")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    started = True
                    self.wfile.write(header)
                    while chunk := response.read1(65536):
                        self.wfile.write(chunk)
        except (OSError, ValueError, subprocess.SubprocessError):
            if not started:
                self.send_json({"error": "camera_unavailable"}, 502)
        finally:
            self.server.probe_lock.release()

    def do_POST(self):
        if self.headers.get("Host") not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            self.send_error(400)
            return
        if self.path == "/preview/session":
            origin = self.headers.get("Origin")
            if self.headers.get("Sec-Fetch-Site") == "cross-site" or (
                origin is not None and origin != f"http://{self.headers['Host']}"
            ):
                self.send_error(403)
                return
            try:
                result, status = self.server.client.agora_session()
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                result, status = {"error": "agora_init_failed"}, 502
            self.send_json(result, status)
            return
        if self.path not in ("/login", "/captcha", "/verify"):
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= 32768:
            self.send_error(400)
            return
        fields = parse_qs(self.rfile.read(size).decode("utf-8", errors="replace"))
        csrf = fields.get("csrf", [""])[0]
        if not csrf.isascii() or not hmac.compare_digest(csrf, self.server.csrf):
            self.send_error(403)
            return
        with self.server.login_lock:
            if not self.server.client.user_id or self.server.client.auth_expired:
                try:
                    self.process_login(fields)
                except HTTPError as error:
                    self.server.message = f"海马爸比服务器返回 HTTP {error.code}。"
                except (URLError, ValueError, KeyError, OSError, subprocess.SubprocessError):
                    self.server.message = "登录请求未完成，请重试。"
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def process_login(self, fields):
        client = self.server.client
        if self.path == "/login":
            if client.auth_expired:
                client.token = ""
                client.user_id = ""
            phone = fields.get("phone", [""])[0].strip()
            password = fields.get("password", [""])[0].strip()
            code, self.server.message = client.login(phone, password)
            if code == NEW_DEVICE_VERIFICATION:
                pending = (phone, password, secrets.token_urlsafe(12))
                self.server.pending = pending
                self.server.sms_sent = False
                timer = threading.Timer(600, expire_verification, (self.server, pending[2]))
                timer.daemon = True
                timer.start()
        elif self.server.pending:
            phone, password, _ = self.server.pending
            if self.path == "/captcha":
                proof = {name: fields[name][0] for name in ("lot_number", "captcha_output", "pass_token", "gen_time")}
                self.server.sms_sent, self.server.message = client.send_verification(phone, proof)
                return
            otp = fields.get("code", [""])[0]
            if not 4 <= len(otp) <= 8 or not otp.isascii() or not otp.isdecimal():
                self.server.message = "请输入有效的短信验证码。"
                return
            code, self.server.message = client.login(phone, password, otp)
        else:
            return
        if code == 1:
            self.server.pending = None
            self.server.sms_sent = False
            client.save_session()
            threading.Thread(target=client.refresh_devices, daemon=True).start()


def expire_verification(server, attempt_id):
    with server.login_lock:
        if server.pending and server.pending[2] == attempt_id:
            server.pending = None
            server.sms_sent = False
            server.message = "验证已超时，请重新登录。"


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), SetupHandler)
    server.csrf = secrets.token_urlsafe(24)
    server.login_lock = threading.Lock()
    server.probe_lock = threading.Lock()
    server.pending = None
    server.sms_sent = False
    server.message = "使用已绑定这台摄像头的账号登录。"
    server.client = HaimaClient(json.loads(CONFIG.read_text()))
    if server.client.restore_session():
        server.message = "已恢复海马爸比登录会话。"
        threading.Thread(target=server.client.refresh_devices, daemon=True).start()
    server.serve_forever()
