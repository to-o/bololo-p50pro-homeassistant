"""Serve a shared feeding log with an optional read-only BOLOLO adapter."""

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from functools import partial
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from bololo_events import reports


ROOT = Path(__file__).resolve().parent
SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_AMOUNT_ML = 60
DEFAULT_SITE_TITLE = "家庭喂养日记"
ASSETS = {
    "/": ("index.html", "text/html"),
    "/style.css": ("style.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


class Problem(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def now():
    return datetime.now(SHANGHAI)


def connect(path):
    db = sqlite3.connect(str(path), timeout=5)
    db.row_factory = sqlite3.Row
    return db


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db, db:
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS feeds (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('bottle', 'breast')),
                amount_ml INTEGER,
                duration_min INTEGER,
                side TEXT,
                bottle_number INTEGER,
                water_ml INTEGER,
                note TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS feeds_by_time ON feeds(deleted, started_at)")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(feeds)")}
        if "device_started_at" not in columns:
            db.execute("ALTER TABLE feeds ADD COLUMN device_started_at TEXT")
        if "time_estimated" not in columns:
            db.execute("ALTER TABLE feeds ADD COLUMN time_estimated INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE feeds SET time_estimated=1 WHERE note LIKE '%时间估算%'")
        if "amount_source" not in columns:
            db.execute("ALTER TABLE feeds ADD COLUMN amount_source TEXT")
            db.execute("UPDATE feeds SET amount_source='default' "
                       "WHERE device_started_at IS NOT NULL AND amount_ml IS NOT NULL AND version=1")
        db.execute("""
            CREATE TABLE IF NOT EXISTS feeding_settings (
                id INTEGER PRIMARY KEY CHECK(id=1),
                default_amount_ml INTEGER NOT NULL CHECK(default_amount_ml BETWEEN 1 AND 1000)
            )
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(feeding_settings)")}
        if "default_mode" not in columns:
            db.execute("ALTER TABLE feeding_settings ADD COLUMN default_mode TEXT NOT NULL DEFAULT 'device'")
            db.execute("UPDATE feeding_settings SET default_mode='custom' WHERE default_amount_ml!=?", (DEFAULT_AMOUNT_ML,))
        if "device_amount_ml" not in columns:
            db.execute("ALTER TABLE feeding_settings ADD COLUMN device_amount_ml INTEGER")
        db.execute("INSERT OR IGNORE INTO feeding_settings (id, default_amount_ml) VALUES (1, ?)",
                   (DEFAULT_AMOUNT_ML,))


def checked_uuid(value):
    try:
        parsed = UUID(value)
        if str(parsed) == value:
            return value
    except (ValueError, AttributeError, TypeError):
        pass
    raise Problem(400, "记录编号无效")


def integer(value, lower, upper, label, optional=True):
    if optional and value is None:
        return None
    if type(value) is not int or not lower <= value <= upper:
        raise Problem(400, f"{label}应在 {lower} 至 {upper} 之间")
    return value


def checked_feed(body):
    if body.get("kind") != "bottle":
        raise Problem(400, "当前只支持奶瓶记录")
    timestamp = body.get("started_at")
    if not isinstance(timestamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", timestamp):
        raise Problem(400, "请选择喂奶时间")
    try:
        start = datetime.fromisoformat(timestamp).replace(tzinfo=SHANGHAI)
    except ValueError:
        raise Problem(400, "喂奶时间无效") from None
    if start > now() + timedelta(minutes=2):
        raise Problem(400, "喂奶时间不能晚于当前时间")
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 200:
        raise Problem(400, "备注最多 200 字")
    amount = integer(body.get("amount_ml"), 0, 1000, "奶量")
    number = integer(body.get("bottle_number"), 1, 253, "奶瓶编号")
    water = integer(body.get("water_ml"), 1, 5000, "参考出水量")
    return timestamp, "bottle", amount, None, None, number, water, note.strip()


FEED_FIELDS = "started_at, kind, amount_ml, duration_min, side, bottle_number, water_ml, note"
FIELD_NAMES = FEED_FIELDS.split(", ")
SELECT_FEED = f"SELECT id, {FEED_FIELDS}, version, device_started_at, time_estimated, amount_source FROM feeds"
EFFECTIVE_AMOUNT = "CASE WHEN default_mode='device' THEN COALESCE(device_amount_ml, default_amount_ml) ELSE default_amount_ml END"


def read_settings(db):
    return dict(db.execute(
        f"SELECT {EFFECTIVE_AMOUNT} AS default_amount_ml, default_amount_ml AS custom_amount_ml, "
        "default_mode, device_amount_ml FROM feeding_settings WHERE id=1"
    ).fetchone())


def save_device_feed(database, started, water, bottle):
    with closing(connect(database)) as db, db:
        db.execute(f"""
            INSERT INTO feeds (id, started_at, kind, amount_ml, bottle_number, water_ml, note, device_started_at, amount_source)
            SELECT ?, ?, 'bottle', {EFFECTIVE_AMOUNT}, ?, ?, '', ?, 'default'
            FROM feeding_settings WHERE id=1
        """, (str(uuid4()), started.isoformat(timespec="minutes")[:16], bottle, water,
              started.isoformat(timespec="seconds")))


class Bololo:
    def __init__(self, client_file, mac, session, *, database=None, mqtt_host=None, device_id=None):
        self.mac = mac
        self.session = session
        self.database = database
        self.amount_lock = threading.Lock()
        self.amount_revision = 0
        self.result = {"state": "loading" if mac else "disabled"}
        self.auto_state = "connecting" if mqtt_host else "disabled"
        if mac:
            spec = importlib.util.spec_from_file_location("feeding_bololo_client", client_file)
            self.client = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.client)
            threading.Thread(target=self.poll, daemon=True).start()
            if mqtt_host:
                threading.Thread(target=self.listen, args=(database, mqtt_host, device_id), daemon=True).start()

    def poll(self):
        while True:
            try:
                amount_revision = self.amount_revision
                data = self.client.query_saved(self.mac, self.session)
                self.update_device_amount(data.get("wateryield"), amount_revision)
                amount = data.get("record")
                number = data.get("bottle_record")
                self.result = {
                    "state": "available",
                    "water_ml": amount if type(amount) is int and 0 < amount <= 5000 else None,
                    "bottle_number": number if type(number) is int and 0 < number < 254 else None,
                    "checked_at": now().isoformat(timespec="seconds"),
                }
            except (self.client.ApiError, OSError, ValueError, AttributeError, sqlite3.Error):
                self.result = {**self.result, "state": "unavailable"}
            time.sleep(45)

    def update_device_amount(self, amount, expected_revision=None):
        if self.database is None or type(amount) is not int or not 30 <= amount <= 500:
            return
        with self.amount_lock:
            if expected_revision is None:
                self.amount_revision += 1
            elif expected_revision != self.amount_revision:
                return
            with closing(connect(self.database)) as db, db:
                db.execute("UPDATE feeding_settings SET device_amount_ml=? "
                           "WHERE id=1 AND device_amount_ml IS NOT ?", (amount, amount))

    def listen(self, database, mqtt_host, device_id):
        while True:
            try:
                status = self.client.query_saved(self.mac, self.session)
                modes = {name: status.get(name) for name in ("self_cleaning", "quantitative_fit", "function_status")}
                if any(value is None for value in modes.values()):
                    raise ValueError("Incomplete BOLOLO state")
                token = self.client.load_session(self.session)["token"]
                homes = self.client.call("app/smartHome/v2/homes", None, token)
                uid = homes[0]["userId"]
                started = None
                waiting_for_end = bool(status.get("detect_status"))
                for report in reports(mqtt_host, device_id, self.client.APP_ID, uid, token):
                    if report is None:
                        self.auto_state = "listening"
                        continue
                    if "wateryield" in report:
                        self.update_device_amount(report["wateryield"])
                    for name in modes:
                        if name in report:
                            modes[name] = report[name]
                    detected = report.get("detect_status")
                    if waiting_for_end:
                        if detected == 0:
                            waiting_for_end = False
                        continue
                    if any(value not in (0, "0", False) for value in modes.values()):
                        started = None
                        continue
                    if detected == 1 and started is None:
                        started = now()
                    if detected == 0 and started is not None:
                        water = report.get("record", 0)
                        elapsed = (now() - started).total_seconds()
                        if 0 < water <= 5000 and 0 <= elapsed <= 120:
                            bottle = report.get("bottle_record", 0)
                            save_device_feed(database, started, water, bottle if 0 < bottle < 254 else None)
                        started = None
            except (self.client.ApiError, OSError, EOFError, ValueError, AttributeError, IndexError,
                    KeyError, TypeError, sqlite3.Error) as exc:
                self.auto_state = "reconnecting"
                print(f"P50 event listener retrying ({type(exc).__name__})", flush=True)
                time.sleep(12)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, database, bololo, site_title=DEFAULT_SITE_TITLE, birth_date=None, **kwargs):
        self.database = database
        self.bololo = bololo
        self.site_title = site_title
        self.birth_date = birth_date
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PUT(self):
        self.handle_request("PUT")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def reply(self, status, content, media):
        self.send_response(status)
        self.send_header("Content-Type", f"{media}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data, status=200):
        self.reply(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")

    def handle_request(self, method):
        target = urlsplit(self.path)
        try:
            if method == "GET" and target.path in ASSETS:
                file, media = ASSETS[target.path]
                asset = ROOT / "static" / file
                if target.path == "/" and self.site_title != DEFAULT_SITE_TITLE:
                    content = asset.read_text(encoding="utf-8").replace(DEFAULT_SITE_TITLE, escape(self.site_title))
                    return self.reply(200, content.encode("utf-8"), media)
                return self.reply(200, asset.read_bytes(), media)
            if method == "GET" and target.path == "/api/p50":
                return self.send_json({**self.bololo.result, "auto_state": self.bololo.auto_state})
            if method == "GET" and target.path == "/api/trend":
                return self.show_trend(parse_qs(target.query))
            if method == "PUT" and target.path == "/api/settings":
                return self.change_settings(self.read_json())
            if target.path == "/api/feeds":
                if method == "GET":
                    return self.list_feeds(parse_qs(target.query))
                if method == "POST":
                    return self.create_feed(self.read_json())
            match = re.fullmatch(r"/api/feeds/([a-f0-9-]+)(/restore)?", target.path)
            if match:
                identifier = checked_uuid(match[1])
                if (method == "POST" and match[2]) or (method in ("PUT", "DELETE") and not match[2]):
                    return self.change_feed(identifier, method, self.read_json())
            raise Problem(404, "没有找到这个页面或记录")
        except Problem as exc:
            self.send_json({"error": exc.message}, exc.status)
        except sqlite3.Error:
            self.send_json({"error": "记录暂时无法读取或保存，请稍后重试"}, 503)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def read_json(self):
        origin = self.headers.get("Origin")
        if origin and (urlsplit(origin).scheme not in ("http", "https") or
                       urlsplit(origin).netloc != self.headers.get("Host")):
            raise Problem(403, "请在当前页面提交记录")
        if self.headers.get_content_type() != "application/json":
            raise Problem(415, "请求必须为 JSON")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError()
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            raise Problem(400, "请求内容无效") from None
        if not isinstance(body, dict):
            raise Problem(400, "请求内容无效")
        return body

    def list_feeds(self, query):
        current = now()
        birth_day = (current.date() - self.birth_date).days + 1 if self.birth_date else None
        raw = query.get("day", [current.date().isoformat()])[0]
        try:
            selected = date.fromisoformat(raw)
            if raw != selected.isoformat():
                raise ValueError()
            end = (selected + timedelta(days=1)).isoformat()
        except (ValueError, OverflowError):
            raise Problem(400, "日期无效") from None
        with closing(connect(self.database)) as db:
            items = db.execute(
                SELECT_FEED + " WHERE deleted=0 AND kind='bottle' AND started_at>=? AND started_at<? "
                "ORDER BY started_at DESC, rowid DESC", (raw, end),
            ).fetchall()
            latest = db.execute(
                SELECT_FEED + " WHERE deleted=0 AND kind='bottle' AND time_estimated=0 "
                "ORDER BY started_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            settings = read_settings(db)
        return self.send_json({
            "day": raw, "today": current.date().isoformat(),
            "birth_day": birth_day if birth_day and birth_day > 0 else None,
            "now": current.isoformat(timespec="seconds"),
            **settings,
            "feeds": [dict(row) for row in items], "latest": dict(latest) if latest else None,
        })

    def show_trend(self, query):
        length = query.get("days", ["7"])[0]
        if length not in ("7", "14"):
            raise Problem(400, "请选择 7 天或 14 天")
        current = now().date()
        first = current - timedelta(days=int(length) - 1)
        average_first = current - timedelta(days=7)
        with closing(connect(self.database)) as db:
            rows = db.execute("""
                SELECT substr(started_at,1,10) AS day, COUNT(*) AS count,
                       SUM(amount_ml) AS total_ml, COUNT(*)-COUNT(amount_ml) AS missing
                FROM feeds
                WHERE deleted=0 AND kind='bottle' AND started_at>=? AND started_at<?
                GROUP BY substr(started_at,1,10)
            """, (min(first, average_first).isoformat(), (current + timedelta(days=1)).isoformat())).fetchall()
        totals = {row["day"]: dict(row) for row in rows}
        days = [(first + timedelta(days=i)).isoformat() for i in range(int(length))]
        complete = [row["total_ml"] for row in totals.values()
                    if average_first.isoformat() <= row["day"] < current.isoformat()
                    and row["total_ml"] is not None and row["missing"] == 0]
        return self.send_json({
            "today": current.isoformat(),
            "days": [totals.get(day, {"day": day, "count": 0, "total_ml": None, "missing": 0}) for day in days],
            "average_ml": round(sum(complete) / len(complete)) if complete else None,
            "average_days": len(complete),
        })

    def change_settings(self, body):
        mode = body.get("default_mode", "custom")
        if mode not in ("device", "custom"):
            raise Problem(400, "请选择默认奶量来源")
        amount = integer(body.get("default_amount_ml"), 1, 1000, "默认奶量", optional=mode == "device")
        with closing(connect(self.database)) as db, db:
            db.execute("UPDATE feeding_settings SET default_mode=?, default_amount_ml=COALESCE(?, default_amount_ml) "
                       "WHERE id=1", (mode, amount))
            settings = read_settings(db)
        return self.send_json(settings)

    def create_feed(self, body):
        identifier = checked_uuid(body.get("id"))
        values = checked_feed(body)
        with closing(connect(self.database)) as db, db:
            added = db.execute(
                f"INSERT INTO feeds (id, {FEED_FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING", (identifier, *values),
            ).rowcount
            row = db.execute(
                f"SELECT id, {FEED_FIELDS}, version, deleted FROM feeds WHERE id=?", (identifier,),
            ).fetchone()
            if row["deleted"] or tuple(row[key] for key in FIELD_NAMES) != values:
                raise Problem(409, "记录已改变，请刷新后再试")
            result = dict(row)
            result.pop("deleted")
        return self.send_json(result, 201 if added else 200)

    def change_feed(self, identifier, method, body):
        version = integer(body.get("version"), 1, 2**31 - 1, "记录版本", optional=False)
        if method == "PUT":
            updates = ", ".join(f"{key}=?" for key in FIELD_NAMES)
            values = checked_feed(body)
            updates += ", amount_source=CASE WHEN device_started_at IS NOT NULL AND amount_ml IS NOT ? " \
                       "THEN CASE WHEN ? IS NULL THEN NULL ELSE 'corrected' END ELSE amount_source END"
            values += (body.get("amount_ml"), body.get("amount_ml"))
        else:
            updates = "deleted=?"
            values = (int(method == "DELETE"),)
        with closing(connect(self.database)) as db, db:
            changed = db.execute(
                f"UPDATE feeds SET {updates}, version=version+1 WHERE id=? AND version=? AND deleted=?",
                (*values, identifier, version, int(method == "POST")),
            ).rowcount
            if not changed:
                raise Problem(409, "这条记录已被修改，请刷新后再试")
            result = dict(db.execute(SELECT_FEED + " WHERE id=?", (identifier,)).fetchone())
        return self.send_json(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "feeding.sqlite3")
    parser.add_argument("--site-title", default=DEFAULT_SITE_TITLE)
    parser.add_argument("--birth-date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--bololo-mac")
    parser.add_argument("--bololo-client", type=Path, default=Path("/etc/bololo/read_status.py"))
    parser.add_argument("--bololo-session", type=Path, default=Path("/etc/bololo/session.json"))
    parser.add_argument("--bololo-mqtt-host")
    parser.add_argument("--bololo-device-id")
    args = parser.parse_args()
    if not 1 <= len(args.site_title.strip()) <= 40:
        parser.error("--site-title must contain 1 to 40 characters")
    mac = re.sub(r"[:-]", "", args.bololo_mac).upper() if args.bololo_mac else None
    if mac and (not re.fullmatch(r"[0-9A-F]{12}", mac) or not args.bololo_client.is_file()):
        parser.error("provide a valid BOLOLO MAC and existing client script")
    if args.bololo_mqtt_host or args.bololo_device_id:
        if not mac or not args.bololo_mqtt_host or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.bololo_device_id or ""):
            parser.error("automatic logging requires a BOLOLO MAC, broker host, and valid device ID")
    initialize(args.db)
    bololo = Bololo(args.bololo_client, mac, args.bololo_session, database=args.db,
                    mqtt_host=args.bololo_mqtt_host, device_id=args.bololo_device_id)
    handler = partial(Handler, database=args.db, bololo=bololo, site_title=args.site_title.strip(),
                      birth_date=args.birth_date)
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Local: http://{args.bind}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
