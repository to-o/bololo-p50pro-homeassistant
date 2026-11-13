const start = document.querySelector("#start");
const stop = document.querySelector("#stop");
const readStatus = document.querySelector("#read-status");
const status = document.querySelector("#state");
const container = document.querySelector("#video");
const deviceState = document.querySelector("#device-state");
const telemetry = document.querySelector("#telemetry");
const deviceDetails = document.querySelector("#device-details");
const extendedTelemetry = document.querySelector("#extended-telemetry");
const labels = {
  CAMERA_MODEL: "设备型号", VER: "固件版本", Temp: "温度 (°C)", Humi: "湿度 (%)",
  WIFI_SIGNAL: "Wi-Fi 信号", SD_STATE: "SD 卡状态", CurAIMode: "AI 模式代码",
  LED: "指示灯状态", Volume: "音量", mp3_state: "安抚播放状态码",
  mp3_current_sec: "安抚播放进度 (秒)",
};
const additionalLabels = {
  "AI 检测设置": {
    SLEEP_TRACKING: "睡眠追踪", SLEEP_TRACK_SENSE: "睡眠追踪灵敏度", BE: "呼吸监测",
    BLOCK: "遮挡检测", BLOCK_SENSE: "遮挡检测灵敏度", BLOCK_TYPE: "遮挡检测类型代码",
    CRY_DETECT_SENSE: "哭声检测灵敏度", CRYDET_TIME: "哭声检测时段",
    FENCE: "虚拟围栏", FENCE_DISPLAY: "显示围栏", FENCEDET_SENSE: "围栏灵敏度",
    FENCEDET_TIME: "围栏检测时段", SPIT: "吐奶检测", SPIT_SENSE: "吐奶检测灵敏度",
    QUILT_COVER: "盖被检测", QUILT_COVER_SENSE: "盖被检测灵敏度",
    BODY_TEMP: "体温相关检测", BODY_TEMP_DISTANCE: "体温检测距离设置",
  },
  "通知设置": {
    SLEEP_NOTIFY: "睡眠通知", APPEASE_NOTIFY: "安抚通知", FENCE_NOTIFY: "围栏通知",
    BLOCK_NOTIFY: "遮挡通知", MOVING_NOTIFY: "移动通知", TEMP_NOTIFY: "温度通知",
    GROWTH_NOTIFY: "成长通知", SPIT_NOTIFY: "吐奶通知", QUILT_COVER_NOTIFY: "盖被通知",
    BODY_TEMP_NOTIFY: "体温相关通知", NOTIFY_TIME: "通知时段",
  },
  "画面与录像设置": {
    LUMI: "亮度", CONT: "对比度", SATU: "饱和度", FH: "水平翻转", FV: "垂直翻转",
    LOGO: "画面标识", RECORDTIME: "录像时长设置", MOS_ENABLE: "区域隐私遮挡",
    SNAPSHOT: "精彩时光设置代码", NIGHT_SNAP: "夜间抓拍设置",
  },
  "安抚设置与播放": {
    APPEASE: "安抚设置", MUSIC_APPEASING: "音乐安抚设置", CRY_APPEASE: "哭声安抚模式",
    MusicState: "音乐状态代码", mp3_full_sec: "曲目时长 (秒)",
  },
};
const statusFields = [...Object.keys(labels), ...Object.values(additionalLabels).flatMap(Object.keys)];
const cardStates = new Map([["0", "正常"], ["1", "未插卡"], ["2", "异常"]]);
let client;

function renderFields(fieldLabels, fields) {
  return Object.entries(fieldLabels).filter(([key]) => fields.has(key)).flatMap(([key, label]) => {
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = label;
    const raw = fields.get(key);
    value.textContent = key === "SD_STATE" ? (cardStates.get(String(raw)) ?? raw) : raw;
    return [term, value];
  });
}

function renderDeviceStatus(fields) {
  telemetry.replaceChildren(...renderFields(labels, fields));
  extendedTelemetry.replaceChildren(...Object.entries(additionalLabels).flatMap(([heading, fieldLabels]) => {
    const rows = renderFields(fieldLabels, fields);
    if (!rows.length) return [];
    const title = document.createElement("h2");
    const list = document.createElement("dl");
    title.textContent = heading;
    list.append(...rows);
    return [title, list];
  }));
  deviceDetails.hidden = !extendedTelemetry.childElementCount;
}

async function leave() {
  const current = client;
  client = undefined;
  if (current) await current.leave();
  container.replaceChildren();
  start.disabled = false;
  readStatus.disabled = false;
  stop.disabled = true;
}

function trackDeviceStatus(rtc, session) {
  const pending = new Map();
  const fields = new Map();
  const replies = new Set();
  let requested = false;

  rtc.on("stream-message", (uid, payload) => {
    if (client !== rtc || String(uid) !== String(session.deviceRtcUid)) return;
    try {
      let data = JSON.parse(new TextDecoder().decode(payload));
      if (typeof data?.m === "string" && typeof data.d === "string" &&
          Number.isInteger(data.n) && data.n > 0 && data.n <= 64 &&
          Number.isInteger(data.i) && data.i >= 0 && data.i < data.n) {
        if (!pending.has(data.m)) {
          if (pending.size >= 8) pending.delete(pending.keys().next().value);
          pending.set(data.m, new Map());
        }
        const parts = pending.get(data.m);
        parts.set(data.i, data.d.trim());
        if (parts.size !== data.n) return;
        const encoded = Array.from({ length: data.n }, (_, index) => parts.get(index)).join("");
        pending.delete(data.m);
        const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
        data = JSON.parse(new TextDecoder().decode(bytes));
      }
      if (!["CHECK_ONLINE", "GetAIMode", "GET_MP3_PLAYINFO"].includes(data?.REQUEST_CMD)) return;
      replies.add(data.REQUEST_CMD);
      for (const key of statusFields) {
        if (typeof data[key] === "string" || typeof data[key] === "number") fields.set(key, data[key]);
      }
      renderDeviceStatus(fields);
      deviceState.textContent = `设备已回复（${replies.size}/3）`;
    } catch {
      // Ignore messages that do not contain a complete status response.
    }
  });

  async function query() {
    if (requested || client !== rtc || !session.statusQueries?.length) return;
    requested = true;
    try {
      for (const query of session.statusQueries) {
        if (client !== rtc) return;
        await rtc.sendStreamMessage({ payload: JSON.stringify(query), syncWithAudio: false });
      }
    } catch {
      if (client === rtc && !replies.size) deviceState.textContent = "设备状态查询发送失败";
    }
  }

  function watchTimeout() {
    if (!session.statusQueries?.length) return;
    setTimeout(() => {
      if (client === rtc && !replies.size && deviceState.textContent === "等待设备状态") {
        deviceState.textContent = "设备状态查询超时";
      }
    }, 10000);
  }
  return { query, watchTimeout };
}

async function connect(watchVideo) {
  start.disabled = true;
  readStatus.disabled = true;
  status.textContent = "正在连接";
  deviceState.hidden = true;
  renderDeviceStatus(new Map());
  try {
    const response = await fetch("/preview/session", { method: "POST" });
    const session = await response.json();
    if (!response.ok) throw new Error(session.error);

    const supportsHevc = globalThis.RTCRtpReceiver?.getCapabilities?.("video")?.codecs.some(
      codec => codec.mimeType.toLowerCase() === "video/h265",
    );
    const waitingForVideo = supportsHevc
      ? "已订阅，等待摄像头画面"
      : "已订阅，当前浏览器未声明 H.265 支持";
    const rtc = AgoraRTC.createClient({ mode: "live", codec: supportsHevc ? "h265" : "h264" });
    client = rtc;
    const deviceStatus = trackDeviceStatus(rtc, session);
    deviceState.hidden = false;
    deviceState.textContent = session.statusQueries?.length ? "等待设备状态" : "当前账号未配置设备状态查询";
    if (session.mediaKey && session.mediaSalt) {
      const salt = Uint8Array.from(atob(session.mediaSalt), character => character.charCodeAt(0));
      rtc.setEncryptionConfig("aes-128-gcm2", session.mediaKey, salt);
    }
    rtc.on("crypt-error", () => {
      if (client === rtc) status.textContent = "媒体解密失败";
    });
    rtc.on("user-published", async (user, media) => {
      if (media !== "video" || String(user.uid) !== String(session.deviceRtcUid)) return;
      void deviceStatus.query();
      if (!watchVideo) return;
      try {
        await rtc.subscribe(user, media);
        if (client !== rtc) return;
        user.videoTrack.play(container);
        const video = container.querySelector("video");
        status.textContent = waitingForVideo;
        if (video) {
          const updateVideoStatus = () => {
            if (client !== rtc || !container.contains(video) || video.readyState < 2) return;
            const { videoWidth, videoHeight } = video;
            status.textContent = videoWidth > 2 && videoHeight > 2
              ? `直播中（${videoWidth} × ${videoHeight}）`
              : waitingForVideo;
          };
          video.addEventListener("playing", updateVideoStatus);
          video.addEventListener("resize", updateVideoStatus);
          updateVideoStatus();
        }
      } catch (error) {
        status.textContent = `订阅失败（${error.code || "Agora"}）`;
      }
    });
    rtc.on("user-unpublished", (user, media) => {
      if (watchVideo && media === "video" && String(user.uid) === String(session.deviceRtcUid)) {
        container.replaceChildren();
        status.textContent = "摄像头暂停视频";
      }
    });
    // Match the Android viewer role without publishing local media.
    await rtc.setClientRole("host");
    await rtc.join(session.appId, session.channelName, session.rtcToken, session.userRtcUid);
    deviceStatus.watchTimeout();
    if (rtc.remoteUsers.some(user => String(user.uid) === String(session.deviceRtcUid))) void deviceStatus.query();
    if (!watchVideo) status.textContent = "已连接设备频道";
    else if (!container.querySelector("video")) status.textContent = "已入频道，等待摄像头发布视频";
    stop.disabled = false;
  } catch (error) {
    status.textContent = `连接失败（${error.code || error.message}）`;
    await leave();
  }
}

start.onclick = () => connect(true);
readStatus.onclick = () => connect(false);

stop.onclick = async () => {
  await leave();
  status.textContent = "已停止";
};
