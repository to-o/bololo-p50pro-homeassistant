"""Query one BOLOLO P50 Pro using the account owner's App session."""

import argparse
from contextlib import contextmanager
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASE_URL = "https://app.bololoapp3.com/"
APP_ID = "91732ca20dfd4517b164c38aac162c43"
PRODUCT = "k1mvpMY27jy000000000000000000000"
SESSION_FILE = Path("/etc/bololo/session.json")
FIELDS = {
    "temp_current", "temp_set", "work_state", "fault", "online", "isOnline",
    "record", "wateryield", "bottle_weight",
}


class ApiError(Exception):
    def __init__(self, message, *, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call(path, data=None, token=None):
    headers = {
        "X-Gizwits-Application-Id": APP_ID,
        "Version": "1.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = token
    payload = None
    if data is not None:
        payload = json.dumps({"appKey": APP_ID, "data": data, "version": "1.0"}).encode()
    req = Request(BASE_URL + path, data=payload, headers=headers)
    try:
        response = build_opener(NoRedirect()).open(req, timeout=15)
    except HTTPError as exc:
        response = exc
    with response:
        status = response.status
        try:
            result = json.loads(response.read(1024 * 1024))
        except (ValueError, UnicodeError):
            raise ApiError(f"{path.split('/')[0]}: HTTP {status}, no JSON response", status=status) from None
    code = str(result.get("code")) if isinstance(result, dict) else ""
    if status != 200 or code != "200":
        code = code if re.fullmatch(r"-?\d{1,10}", code) else "unknown"
        raise ApiError(f"{path.split('/')[0]}: HTTP {status}, BOLOLO code {code}", status=status, code=code)
    return result.get("data")


def timestamp(value):
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return value // 1000 if value > 100_000_000_000 else value


def normalize_session(data):
    if not isinstance(data, dict):
        raise ApiError("The server did not return a refreshable account session.")
    jwt = data.get("jwtAuthenticationDto")
    token = jwt.get("token") if isinstance(jwt, dict) else data.get("token")
    refresh_token = data.get("refresh_token") or data.get("refreshToken")
    if not all(isinstance(item, str) and item for item in (token, refresh_token)):
        raise ApiError("The server did not return a refreshable account session.")
    return {
        "token": token,
        "refresh_token": refresh_token,
        "created_at": timestamp(data.get("created_at") or data.get("createdAt")),
        "expired_at": timestamp(data.get("expired_at") or data.get("expiredAt")),
    }


@contextmanager
def session_lock(path):
    # OpenWrt uses flock to keep overlapping polling calls from rotating the same token.
    if os.name != "posix":
        raise ApiError("Run saved-session mode on OpenWrt.")
    import fcntl

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path.with_suffix(path.suffix + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load_session(path):
    try:
        with path.open(encoding="utf-8") as handle:
            return normalize_session(json.load(handle))
    except FileNotFoundError:
        raise ApiError("No saved session. Enroll once before polling.") from None
    except ValueError:
        raise ApiError("The saved session file is invalid.") from None


def save_session(path, session):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".session-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(session, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def refresh_session(session, path):
    result = call("app/user/refresh_token", {
        "clientId": APP_ID, "refresh": True, "refresh_token": session["refresh_token"],
    }, session["token"])
    updated = normalize_session(result)
    save_session(path, updated)
    return updated


def query_saved(mac, path, force_refresh=False, enroll=False, country_code="+86"):
    with session_lock(path):
        if enroll:
            session = login_by_sms(country_code)
            save_session(path, session)
        else:
            session = load_session(path)
        created = session["created_at"]
        expires = session["expired_at"]
        # The official App refreshes after half the access-token lifetime.
        due = 0 < created < expires and time.time() >= (created + expires) / 2
        refreshed = force_refresh or due
        if refreshed:
            session = refresh_session(session, path)
        route = f"bololo/app/device/status/{PRODUCT}/{mac}"
        try:
            return call(route, {}, session["token"])
        except ApiError as exc:
            if refreshed or (exc.status != 401 and exc.code not in {"505", "526"}):
                raise
        session = refresh_session(session, path)
        return call(route, {}, session["token"])


def login_by_sms(country_code):
    mobile = getpass.getpass("BOLOLO account mobile number (no country prefix): ").strip()
    if not re.fullmatch(r"\d{5,15}", mobile):
        raise ApiError("Mobile number must contain digits only.")
    challenge = call("app/user/codeToken")
    if not isinstance(challenge, str) or not challenge:
        raise ApiError("The server did not return an SMS challenge.")
    call("app/user/v2/mobileCode", {"mobile": mobile, "lang": "zh", "token": challenge})
    code = getpass.getpass("SMS verification code: ").strip()
    if not re.fullmatch(r"\d{4,8}", code):
        raise ApiError("Invalid verification code format.")
    data = call("app/user/loginByMobile", {
        "mobile": mobile, "code": code, "lang": "zh",
        "mobileCountryCode": country_code, "homeName": "我的家",
    })
    return normalize_session(data)


def select_readings(value, path="data"):
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from select_readings(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            # Intermediate object keys may contain device identifiers.
            child_path = f"{path}.{key}" if key in FIELDS else f"{path}.*"
            if key in FIELDS and type(item) in (bool, int, float):
                yield child_path, item
            elif key == "work_state" and isinstance(item, str) and item in {
                "Heating", "Keeping", "Cooling", "0", "1", "2",
            }:
                yield child_path, item
            elif isinstance(item, (dict, list)):
                yield from select_readings(item, child_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mac", required=True, help="Device MAC from the BOLOLO App")
    parser.add_argument("--country-code", default="+86")
    parser.add_argument("--session-file", type=Path, default=SESSION_FILE)
    parser.add_argument("--enroll", action="store_true", help="Log in once by SMS and save the new session")
    parser.add_argument("--refresh-now", action="store_true", help="Verify token refresh before querying")
    parser.add_argument("--existing-session", action="store_true", help="Prompt for an existing App session token")
    args = parser.parse_args()
    mac = re.sub(r"[:-]", "", args.mac)
    if not re.fullmatch(r"[0-9a-fA-F]{12}", mac):
        parser.error("--mac must be a 12-digit hexadecimal MAC address")
    try:
        if args.existing_session:
            token = getpass.getpass("BOLOLO App Authorization value: ").strip()
            if not token:
                raise ApiError("An account session is required.")
            data = call(f"bololo/app/device/status/{PRODUCT}/{mac}", {}, token)
        else:
            data = query_saved(mac, args.session_file, args.refresh_now, args.enroll, args.country_code)
        readings = dict(select_readings(data))
        if not readings:
            raise ApiError("The API returned success, but no recognized P50 Pro state fields were found.")
        print(json.dumps(readings, indent=2, ensure_ascii=False))
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, URLError, EOFError, KeyboardInterrupt):
        print("Request or interactive input interrupted.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
