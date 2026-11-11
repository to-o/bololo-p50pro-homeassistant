"""Read sleep reports and camera events from the local Haima bridge."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
import json
from threading import Lock
from time import monotonic
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:18874"
EVENT_KINDS = {"BabyCrying": "cry", "MouthNoseBlock": "mouth_block", "HeadFaceBlock": "face_block"}
SLEEP_EVENTS = {"LightSleep", "DeepSleep", "BabyAwaken"}


def read_json(path):
    try:
        with urlopen(BASE_URL + path, timeout=4) as response:
            data = json.load(response)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def read_segments(day):
    data = read_json(f"/sleep/daily?date={day}")
    report = data.get("report") if data else None
    records = report.get("sleepInfos") if isinstance(report, dict) else None
    if not isinstance(records, list):
        return [], False

    segments = []
    for row in records:
        try:
            start = datetime.fromisoformat(row["asleepSleepTime"])
            end = datetime.fromisoformat(row["wakeSleepTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.tzinfo is None and end.tzinfo is None and end > start:
            segments.append((start, end))
    return segments, True


def read_events(day):
    events = set()
    deadline = monotonic() + 12
    for page in range(1, 1001):
        data = read_json(f"/events?date={day}&page={page}")
        if not data or not isinstance(data.get("events"), list):
            return events, False
        for row in data["events"]:
            try:
                timestamp = datetime.fromisoformat(row["eventTime"])
                kind = row["eventType"]
            except (KeyError, TypeError, ValueError):
                continue
            if (timestamp.tzinfo is None and timestamp.date() == day and
                    isinstance(kind, str) and (kind in EVENT_KINDS or kind in SLEEP_EVENTS)):
                events.add((timestamp, kind))
        total = data.get("total")
        if not data["events"] or (type(total) is int and page * 10 >= total):
            return events, True
        if monotonic() >= deadline:
            break
    return events, False


def build_snapshot(day, reports, event_result):
    midnight = datetime.combine(day, time.min)
    next_midnight = midnight + timedelta(days=1)
    segments = sorted({segment for records, _ in reports for segment in records})
    events, events_complete = event_result
    timeline = [(at, EVENT_KINDS[kind], None) for at, kind in events if kind in EVENT_KINDS]
    sleep_seconds = 0
    covered_until = midnight
    for start, end in segments:
        if midnight <= start < next_midnight:
            timeline.append((start, "sleep_start", None))
        if midnight <= end < next_midnight:
            timeline.append((end, "sleep_end", int((end - start).total_seconds())))
        first = max(start, covered_until)
        last = min(end, next_midnight)
        if last > first:
            sleep_seconds += int((last - first).total_seconds())
            covered_until = last

    latest = max(segments, key=lambda segment: segment[1], default=None)
    recent = max(((at, kind) for at, kind in events if kind in SLEEP_EVENTS), default=None)
    if recent and (recent[1] == "BabyAwaken" or (latest and recent[0] <= latest[1])):
        recent = None
    return {
        "enabled": True,
        "day": day.isoformat(),
        "reports_complete": all(ok for _, ok in reports),
        "events_complete": events_complete,
        "sleep_seconds": sleep_seconds,
        "latest": ({"wake_at": latest[1].isoformat(),
                    "seconds": int((latest[1] - latest[0]).total_seconds())} if latest else None),
        "recent_sleep_event": ({"at": recent[0].isoformat(), "type": recent[1]} if recent else None),
        "timeline": [{"at": at.isoformat(), "kind": kind, "seconds": seconds}
                     for at, kind, seconds in sorted(set(timeline), key=lambda item: item[:2], reverse=True)],
    }


class SleepBridge:
    def __init__(self):
        self.lock = Lock()
        self.cached = None
        self.expires_at = 0

    def snapshot(self, day):
        with self.lock:
            if self.cached and self.cached["day"] == day.isoformat() and monotonic() < self.expires_at:
                return self.cached
            with ThreadPoolExecutor(max_workers=3) as pool:
                reports = [pool.submit(read_segments, day - timedelta(days=1)), pool.submit(read_segments, day)]
                events = pool.submit(read_events, day)
                self.cached = build_snapshot(day, [report.result() for report in reports], events.result())
            self.expires_at = monotonic() + 60
            return self.cached
