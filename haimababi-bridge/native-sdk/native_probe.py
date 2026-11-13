"""Verify the Agora camera stream using the Linux Server Gateway SDK."""

import argparse
import base64
from collections import Counter
import json
import sys
from threading import Event, Lock
import time

from agora.rtc.agora_base import (
    AgoraServiceConfig,
    AudioPublishType,
    AudioScenarioType,
    EncryptionConfig,
    RTCConnConfig,
    RtcConnectionPublishConfig,
    VideoSubscriptionOptions,
)
from agora.rtc.agora_service import AgoraService
from agora.rtc.rtc_connection_observer import IRTCConnectionObserver
from agora.rtc.video_encoded_frame_observer import IVideoEncodedFrameObserver
from agora.rtc.video_frame_observer import IVideoFrameObserver


class ConnectionObserver(IRTCConnectionObserver):
    def __init__(self, camera_uid):
        self.camera_uid = str(camera_uid)
        self.connected = Event()
        self.camera_joined = Event()

    def on_connected(self, connection, info, reason):
        self.connected.set()

    def on_user_joined(self, connection, uid):
        if str(uid) == self.camera_uid:
            self.camera_joined.set()


class VideoObserver(IVideoEncodedFrameObserver, IVideoFrameObserver):
    def __init__(self, camera_uid):
        self.camera_uid = str(camera_uid)
        self.frames = Counter()
        self.lock = Lock()

    def on_encoded_video_frame(self, uid, buffer, length, info):
        if str(uid) == self.camera_uid:
            with self.lock:
                self.frames[(info.codec_type, info.width, info.height)] += 1

    def on_frame(self, channel_id, uid, frame):
        if str(uid) == self.camera_uid:
            with self.lock:
                self.frames[("decoded", frame.width, frame.height)] += 1

    def summary(self):
        with self.lock:
            return [
                {"codec": codec, "width": width, "height": height, "frames": count}
                for (codec, width, height), count in self.frames.items()
            ]


def require_ok(operation, code):
    if code != 0:
        raise RuntimeError(f"{operation} failed ({code})")


def probe(session, seconds, decode):
    camera_uid = session["deviceRtcUid"]
    observer = ConnectionObserver(camera_uid)
    video = VideoObserver(camera_uid)
    service = AgoraService()
    connection = None
    try:
        require_ok("Initialize Agora", service.initialize(AgoraServiceConfig(
            appid=session["appId"], enable_video=1, enable_audio_processor=0, log_path="/dev/null",
        )))
        connection = service.create_rtc_connection(
            RTCConnConfig(),
            RtcConnectionPublishConfig(
                is_publish_audio=False, audio_publish_type=AudioPublishType.AUDIO_PUBLISH_TYPE_NONE,
                audio_scenario=AudioScenarioType.AUDIO_SCENARIO_DEFAULT,
            ),
        )
        require_ok("Register connection observer", connection.register_observer(observer))
        if decode:
            require_ok("Register decoded observer", connection.register_video_frame_observer(video))
        else:
            require_ok("Register encoded observer", connection.register_video_encoded_frame_observer(video))
        if session.get("mediaKey") and session.get("mediaSalt"):
            require_ok("Enable encryption", connection.enable_encryption(1, EncryptionConfig(
                encryption_mode=7,
                encryption_key=session["mediaKey"],
                encryption_kdf_salt=bytearray(base64.b64decode(session["mediaSalt"], validate=True)),
            )))
        require_ok("Connect", connection.connect(
            session["rtcToken"], session["channelName"], str(session["userRtcUid"]),
        ))
        if not observer.connected.wait(12):
            raise TimeoutError("Agora channel did not connect")
        if not observer.camera_joined.wait(10):
            raise TimeoutError("Camera did not join the channel")
        require_ok("Subscribe", connection.get_local_user().subscribe_video(
            str(camera_uid), VideoSubscriptionOptions(encodedFrameOnly=not decode),
        ))
        time.sleep(seconds)
        return video.summary()
    finally:
        if connection:
            connection.disconnect()
            connection.release()
        service.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, choices=range(1, 31), default=10)
    parser.add_argument("--decode", action="store_true")
    args = parser.parse_args()
    result = probe(json.load(sys.stdin), args.seconds, args.decode)
    print(json.dumps({"video": result}), flush=True)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
