"use strict";

const $ = id => document.getElementById(id);
const editor = $("editor");
const form = $("entry-form");
const inputs = form.elements;
const decreaseButtons = [...$("quick-amount").querySelectorAll("button")];
const settings = $("settings");
const settingsForm = $("settings-form");
const shanghai = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short",
});
const localTime = () => shanghai.format(new Date()).replace(" ", "T");
const today = () => localTime().slice(0, 10);
const numberText = value => new Intl.NumberFormat("zh-CN").format(value);

let tab = "today";
let day = today();
let latest = null;
let p50 = null;
let p50Sequence = 0;
let manualWeighBusy = false;
let draft = null;
let deleted = null;
let loadSequence = 0;
let busy = false;
let noticeTimer = null;
let defaultAmount = null;
let defaultMode = "device";
let customAmount = null;
let deviceAmount = null;
let trendDays = 7;
let trendDay = null;
let trendSequence = 0;
let trendDaySequence = 0;
let trendSnapshot = "";
let activeFeeds = [];
let activeDay = null;
let sleepSnapshot = null;
let sleepLoading = false;
let showAllToday = false;
const recentLimit = 3;

async function api(path, method = "GET", body) {
    const response = await fetch(path, {
        method,
        headers: body ? {"Content-Type": "application/json"} : undefined,
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "操作失败，请重试");
    return data;
}

function errorAt(id, message = "") {
    const element = $(id);
    element.textContent = message;
    element.hidden = !message;
}

function minuteDistance(first, second) {
    return Math.max(0, Math.floor((new Date(second + "+08:00") - new Date(first + "+08:00")) / 60000));
}

function durationLabel(minutes) {
    if (minutes < 1) return "刚刚";
    if (minutes < 60) return minutes + " 分钟";
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return hours + " 小时" + (rest ? " " + rest + " 分钟" : "");
}

function feedDetail(feed) {
    if (feed.amount_ml === null) return "奶量未记";
    const prefix = feed.amount_source === "weighed" ? "约 " : "";
    return prefix + numberText(feed.amount_ml) + " mL";
}

function weighedAmount(feed) {
    if (!Number.isInteger(feed.before_weight_dg) || !Number.isInteger(feed.after_weight_dg)) return "";
    const grams = ((feed.before_weight_dg - feed.after_weight_dg) / 10).toFixed(1);
    const estimate = Number.isInteger(feed.estimated_amount_ml) && feed.amount_source !== "weighed"
        ? "称重约 " + numberText(feed.estimated_amount_ml) + " mL · " : "";
    return estimate + "重量差 " + grams + " 克";
}

function feedSource(feed) {
    if (feed.device_started_at) return "P50 自动记录";
    if (feed.time_estimated || feed.note.startsWith("美柚截图导入")) return "截图导入";
    return "手动补记";
}

function refreshHero() {
    const preparedOnly = latest?.device_started_at && !Number.isInteger(latest.estimated_amount_ml);
    $("last-title").textContent = preparedOnly ? "上次备奶" : "上次喂奶";
    $("edit-latest").hidden = !latest;
    $("add-first").hidden = Boolean(latest);
    $("last-amount").textContent = latest ? feedDetail(latest) : "";
    if (!latest) {
        $("last-time").textContent = "—";
        $("last-detail").textContent = "暂无时间明确的喂奶记录";
        return;
    }
    const feedDay = latest.started_at.slice(0, 10);
    const distance = durationLabel(minuteDistance(latest.started_at, localTime()));
    const when = (feedDay === today() ? "" : feedDay.slice(5).replace("-", "/") + " ") + latest.started_at.slice(11);
    $("last-time").textContent = when;
    $("last-detail").textContent = distance === "刚刚" ? distance : distance + "前";
}

function textElement(tag, className, value) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = value;
    return element;
}

function renderLog(feeds) {
    activeFeeds = feeds;
    const measured = feeds.filter(feed => feed.amount_ml !== null);
    const missing = feeds.length - measured.length;
    $("count").textContent = numberText(feeds.length);
    const approximation = measured.some(feed => feed.amount_source === "weighed") ? "约 " : "";
    $("total").textContent = measured.length
        ? approximation + numberText(measured.reduce((total, feed) => total + feed.amount_ml, 0)) + " mL"
        : "—";
    $("missing").hidden = missing === 0;
    $("missing").textContent = missing ? missing + " 顿瓶喂未填写奶量" : "";
    renderTimeline();
}

function renderTimeline() {
    const isToday = tab === "today";
    const cameraEvents = isToday && activeDay === sleepSnapshot?.day ? sleepSnapshot.timeline : [];
    const hasCry = cameraEvents.some(event => event.kind === "cry");
    const hasAlerts = cameraEvents.some(event => event.kind === "mouth_block" || event.kind === "face_block");
    $("camera-filter").hidden = !hasCry && !hasAlerts;
    const visibleEvents = cameraEvents.filter(event =>
        (event.kind !== "cry" || $("show-camera-cry").checked) &&
        ((event.kind !== "mouth_block" && event.kind !== "face_block") || $("show-camera-alerts").checked));
    const entries = activeFeeds.map((feed, index) => ({at: feed.started_at, feed, previous: activeFeeds[index + 1]}))
        .concat(timelineSleepEntries(visibleEvents), visibleEvents.filter(event => event.kind !== "sleep_start" && event.kind !== "sleep_end"))
        .sort((left, right) => right.at.localeCompare(left.at));
    const limit = visibleEvents.length ? 6 : recentLimit;
    const canExpand = isToday && entries.length > limit;
    const toggle = $("show-all");
    toggle.hidden = !canExpand;
    toggle.textContent = showAllToday ? "收起" : "查看全部 " + entries.length + (visibleEvents.length ? " 条" : " 顿");
    toggle.setAttribute("aria-expanded", String(canExpand && showAllToday));
    const displayed = canExpand && !showAllToday ? entries.slice(0, limit) : entries;
    $("timeline").replaceChildren(...displayed.map(entry => entry.feed
        ? feedRow(entry.feed, entry.previous, false, isToday) : cameraRow(entry)));
    $("empty").hidden = entries.length > 0;
    $("empty").textContent = isToday && sleepSnapshot?.enabled ? "今天还没有记录" : "这一天还没有喂奶记录";
    renderLogActions();
}

function timelineSleepEntries(events) {
    const starts = events.filter(event => event.kind === "sleep_start");
    const ends = events.filter(event => event.kind === "sleep_end");
    const usedStarts = new Set();
    const entries = ends.map(event => {
        const endMs = Date.parse(event.at + "Z");
        const startMs = endMs - event.seconds * 1000;
        const startAt = new Date(startMs).toISOString().slice(0, 19);
        const match = starts.find(start => !usedStarts.has(start) && start.at === startAt);
        if (match) usedStarts.add(match);
        return {...event, kind: "sleep_interval", at: startAt, wakeAt: event.at};
    });
    return entries.concat(starts.filter(event => !usedStarts.has(event)).map(event => ({...event, kind: "sleep_open"})));
}

function sleepDuration(seconds) {
    if (seconds === 0) return "0 分钟";
    if (seconds < 60) return seconds + " 秒";
    return durationLabel(Math.floor(seconds / 60)) + (seconds % 60 ? " " + seconds % 60 + " 秒" : "");
}

function cameraRow(event) {
    const li = document.createElement("li");
    const row = textElement("div", "timeline-row", "");
    const title = {
        sleep_interval: "睡眠时段", sleep_open: "入睡", cry: "哭声",
        mouth_block: "口鼻遮挡", face_block: "头脸遮挡",
    }[event.kind];
    const startDay = event.at.slice(0, 10);
    const startLabel = startDay !== activeDay
        ? (startDay === new Date(Date.parse(activeDay + "T00:00:00Z") - 86400000).toISOString().slice(0, 10) ? "昨晚 " : startDay.slice(5) + " ") + event.at.slice(11, 16)
        : event.at.slice(11, 16);
    const info = textElement("strong", "entry-info", "");
    info.append(textElement("span", "", title));
    if (event.kind === "sleep_interval") info.append(textElement("span", "small muted", "醒来 " + event.wakeAt.slice(11, 16)));
    row.append(textElement("time", "entry-time", startLabel), info,
        textElement("span", "entry-amount", event.seconds === null ? "" : sleepDuration(event.seconds)));
    li.append(row);
    return li;
}

async function loadSleep() {
    if (sleepLoading || tab !== "today") return;
    sleepLoading = true;
    try {
        const data = await api("/api/sleep");
        sleepSnapshot = data.enabled && data.day === today() ? data : null;
        $("sleep-card").hidden = !sleepSnapshot;
        if (sleepSnapshot) {
            const latest = data.latest;
            $("sleep-latest").textContent = latest ? sleepDuration(latest.seconds) : "—";
            $("sleep-wake").textContent = latest ? "最近醒来 " +
                (latest.wake_at.slice(0, 10) === data.day ? "" : latest.wake_at.slice(5, 10) + " ") +
                latest.wake_at.slice(11, 16) : "最近一觉";
            $("sleep-total").textContent = data.reports_complete || data.sleep_seconds > 0
                ? sleepDuration(data.sleep_seconds) : "—";
            $("sleep-status").textContent = !data.reports_complete ? "睡眠日报暂未取全"
                : !data.events_complete ? "摄像头事件暂未取全" : "";
            const recent = data.recent_sleep_event;
            $("sleep-recent").hidden = !recent;
            $("sleep-recent").textContent = recent ? "最近检测到" +
                (recent.type === "DeepSleep" ? "深睡" : "浅睡") + " · " + recent.at.slice(11, 16) : "";
        }
        if (tab === "today") renderTimeline();
    } catch {
        if (sleepSnapshot) $("sleep-status").textContent = "睡眠数据暂时无法刷新";
    } finally {
        sleepLoading = false;
    }
}

function renderLogActions() {
    const warning = {
        reconnecting: "自动记奶暂不可用，正在重连",
        connecting: "正在连接自动记奶",
        disabled: "自动记奶尚未启用",
        unknown: "暂时无法确认自动记奶状态",
    }[p50?.auto_state];
    const isToday = tab === "today";
    const notice = $("auto-warning");
    const noticeText = $("auto-warning-text");
    notice.hidden = !isToday || !warning;
    if (noticeText.textContent !== (warning || "")) noticeText.textContent = warning || "";
    $("add-bottle").hidden = !latest || Boolean(warning);
    $("today-actions").hidden = !isToday || ($("add-bottle").hidden && $("show-all").hidden);
}

function renderRows(list, feeds) {
    list.replaceChildren(...feeds.map((feed, index) => feedRow(feed, feeds[index + 1], list.id === "trend-day-entries")));
}

function feedRow(feed, previous, fromTrend, compact = false) {
    const li = document.createElement("li");
    const row = textElement("button", "timeline-row", "");
    row.type = "button";
    const info = textElement("span", "entry-info", "");
    const interval = previous && !previous.time_estimated && !feed.time_estimated
        ? minuteDistance(previous.started_at, feed.started_at) : null;
    const source = feedSource(feed);
    const amountSource = {default: "默认奶量", corrected: "已修正", weighed: "称重估算"}[feed.amount_source];
    const note = feed.note.startsWith("美柚截图导入")
        ? feed.note.replace(/^美柚截图导入(?: · 时间估算)?/, "").trim() : feed.note;
    const sub = [source, feed.time_estimated && "时间估算", amountSource,
        feed.bottle_number && feed.bottle_number + " 号瓶", weighedAmount(feed), note,
        interval ? "间隔 " + durationLabel(interval) : ""].filter(Boolean).join(" · ");
    info.append(textElement("strong", "", "瓶喂"));
    if (sub && !compact) info.append(textElement("span", "muted small entry-note", sub));
    row.append(textElement("time", "entry-time", feed.started_at.slice(11)), info,
        textElement("span", "entry-amount", feedDetail(feed)));
    row.addEventListener("click", () => openEditor(feed, null, fromTrend));
    li.append(row);
    return li;
}

function chartDate(day) {
    return Number(day.slice(5, 7)) + "/" + Number(day.slice(8, 10));
}

function selectTrendDay(selected) {
    trendDay = selected;
    for (const button of $("trend-chart").querySelectorAll("button")) {
        button.setAttribute("aria-pressed", String(button.dataset.day === selected));
    }
    $("trend-detail").hidden = !selected;
    if (selected) {
        $("trend-day-title").textContent = chartDate(selected) + " 明细";
        $("trend-day-status").textContent = "读取中";
        $("trend-day-entries").replaceChildren();
        loadTrendDay();
    }
}

async function loadTrendDay() {
    if (!trendDay || tab !== "today") return;
    const request = ++trendDaySequence;
    const selected = trendDay;
    try {
        const data = await api("/api/feeds?day=" + encodeURIComponent(selected));
        if (request !== trendDaySequence || trendDay !== selected) return;
        const missing = data.feeds.filter(feed => feed.amount_ml === null).length;
        $("trend-day-status").textContent = data.feeds.length
            ? data.feeds.length + " 次" + (missing ? " · " + missing + " 顿未填奶量" : "")
            : "这天没有记录";
        renderRows($("trend-day-entries"), data.feeds);
    } catch {
        if (request === trendDaySequence && trendDay === selected) {
            $("trend-day-status").textContent = "暂时无法读取明细";
        }
    }
}

function renderTrend(data) {
    const chart = $("trend-chart");
    const focusDay = chart.contains(document.activeElement) ? document.activeElement.dataset.day : null;
    const max = Math.max(1, ...data.days.map(item => item.total_ml || 0));
    const weeks = [];
    for (let offset = 0; offset < data.days.length; offset += 7) {
        const row = textElement("div", "trend-week", "");
        for (const item of data.days.slice(offset, offset + 7)) {
            const label = chartDate(item.day);
            const isToday = item.day === data.today;
            const total = item.total_ml === null ? "—" : numberText(item.total_ml);
            const button = textElement("button", "trend-day", "");
            button.type = "button";
            button.dataset.day = item.day;
            button.classList.toggle("trend-today", isToday);
            button.setAttribute("aria-pressed", String(trendDay === item.day));
            const description = item.count === 0 ? "无记录"
                : (item.total_ml === null ? "奶量未填" : total + " 毫升") + "，" + item.count + " 次"
                    + (item.missing ? "，" + item.missing + " 顿未填奶量" : "");
            button.setAttribute("aria-label", label + (isToday ? "，今天进行中，" : "，") + description);
            const slot = textElement("span", "trend-bar-slot", "");
            if (item.total_ml > 0) {
                const bar = textElement("span", "trend-bar", "");
                bar.style.height = 100 * item.total_ml / max + "%";
                slot.append(bar);
            }
            button.append(textElement("span", "trend-total", total), slot,
                textElement("span", "trend-date", isToday ? "今天" : label),
                textElement("span", "trend-count", item.count ? item.count + "次" : "无"));
            button.addEventListener("click", () => selectTrendDay(item.day));
            row.append(button);
        }
        weeks.push(row);
    }
    chart.replaceChildren(...weeks);
    if (focusDay) chart.querySelector('button[data-day="' + focusDay + '"]')?.focus();
    $("trend-average").textContent = data.average_ml === null
        ? "过去 7 天暂无可用于日均的完整记录"
        : "过去 7 天日均 " + numberText(data.average_ml) + " mL · " + data.average_days + " 个完整记录日";
}

async function loadTrend() {
    if (tab !== "today") return;
    const request = ++trendSequence;
    try {
        const data = await api("/api/trend?days=" + trendDays);
        if (request !== trendSequence || tab !== "today") return;
        if (trendDay && !data.days.some(item => item.day === trendDay)) selectTrendDay(null);
        const snapshot = JSON.stringify(data);
        if (snapshot !== trendSnapshot) {
            renderTrend(data);
            trendSnapshot = snapshot;
        }
        errorAt("trend-error");
    } catch {
        if (request === trendSequence && tab === "today") errorAt("trend-error", "暂时无法刷新奶量对比");
    }
}

function refreshTrend() {
    loadTrend();
    loadTrendDay();
}

async function loadFeeds() {
    const sequence = ++loadSequence;
    const selected = tab === "today" ? today() : day;
    try {
        const data = await api("/api/feeds?day=" + encodeURIComponent(selected));
        if (sequence !== loadSequence) return;
        latest = data.latest;
        const birthDay = $("birth-day");
        birthDay.hidden = !Number.isInteger(data.birth_day);
        birthDay.textContent = birthDay.hidden ? "" : "出生第 " + data.birth_day + " 天";
        setDefaultAmount(data);
        $("day-label").textContent = data.day.slice(5).replace("-", " 月 ") + " 日";
        $("selected-day").value = data.day;
        $("selected-day").max = data.today;
        $("next-day").disabled = data.day >= data.today;
        activeDay = data.day;
        renderLog(data.feeds);
        refreshHero();
        errorAt("load-error");
    } catch {
        if (sequence === loadSequence) errorAt("load-error", "暂时无法刷新记录，请检查连接");
    }
}

function setView(next) {
    tab = next;
    const isToday = tab === "today";
    $("today-view").hidden = !isToday;
    $("device").hidden = !isToday;
    $("day-picker").hidden = isToday;
    $("trend").hidden = !isToday;
    renderLogActions();
    $("log-title").textContent = isToday ? "今日记录" : "历史记录";
    $("today-tab").toggleAttribute("aria-current", isToday);
    $("history-tab").toggleAttribute("aria-current", !isToday);
    if (isToday) $("today-tab").setAttribute("aria-current", "page");
    else $("history-tab").setAttribute("aria-current", "page");
    loadFeeds();
    if (isToday) {
        refreshTrend();
        loadSleep();
    }
}

function changeDay(step) {
    const value = new Date(day + "T00:00:00Z");
    value.setUTCDate(value.getUTCDate() + step);
    const next = value.toISOString().slice(0, 10);
    if (next > today()) return;
    day = next;
    loadFeeds();
}

function makeId() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}

function syncDecreaseButtons() {
    const amount = inputs.amount_ml.valueAsNumber;
    for (const button of decreaseButtons) {
        button.disabled = busy || !inputs.amount_ml.validity.valid || !(amount > 0);
    }
}

function openEditor(entry, reference, fromTrend = false) {
    if (editor.open) return;
    form.reset();
    const editing = Boolean(entry);
    draft = {
        id: editing ? entry.id : makeId(), kind: "bottle", version: editing ? entry.version : null, fromTrend,
        bottle_number: entry?.bottle_number ?? reference?.bottle_number ?? null,
        water_ml: entry?.water_ml ?? reference?.water_ml ?? null,
    };
    const time = localTime();
    inputs.started_at.value = entry?.started_at || (tab === "history" && day < today() ? day + time.slice(10) : time);
    inputs.amount_ml.value = (editing ? entry.amount_ml : defaultAmount) ?? "";
    $("quick-amount").hidden = !editing;
    $("quick-amount-status").textContent = "";
    syncDecreaseButtons();
    inputs.note.value = entry?.note || "";
    $("delete-feed").hidden = !editing;
    $("editor-title").textContent = editing ? "修改喂奶记录" : "记一顿";
    const water = draft.water_ml
        ? "P50 出水 " + draft.water_ml + " mL"
            + (entry?.device_started_at ? " · 开始 " + entry.device_started_at.slice(11, 19) : "")
            + (draft.bottle_number ? " · " + draft.bottle_number + " 号瓶" : "")
        : "";
    const weigh = entry ? weighedAmount(entry) : "";
    const source = entry ? feedSource(entry) : "";
    $("water-reference").textContent = [source, water, weigh].filter(Boolean).join(" · ");
    $("water-reference").hidden = !source && !water && !weigh;
    errorAt("form-error");
    editor.showModal();
    if (editing) {
        (decreaseButtons.find(button => !button.disabled) || $("save-feed")).focus();
    } else {
        inputs.amount_ml.focus();
    }
}

function showNotice(message, undoEntry = null) {
    clearTimeout(noticeTimer);
    deleted = undoEntry;
    $("notice-text").textContent = message;
    $("undo").hidden = !deleted;
    $("notice").hidden = false;
    noticeTimer = setTimeout(() => {
        $("notice").hidden = true;
        deleted = null;
    }, undoEntry ? 12000 : 3000);
}

function setBusy(value) {
    busy = value;
    for (const id of ["save-feed", "delete-feed", "close-editor"]) $(id).disabled = value;
    syncDecreaseButtons();
}

inputs.amount_ml.addEventListener("input", syncDecreaseButtons);
for (const button of decreaseButtons) {
    button.addEventListener("click", () => {
        const amount = Math.max(0, inputs.amount_ml.valueAsNumber - Number(button.dataset.decrease));
        inputs.amount_ml.value = amount;
        $("quick-amount-status").textContent = "本次奶量 " + amount + " 毫升";
        syncDecreaseButtons();
        if (amount === 0) $("save-feed").focus();
    });
}

form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    const readNumber = field => inputs[field].value === "" ? null : Number(inputs[field].value);
    const {fromTrend, ...fields} = draft;
    const body = {
        ...fields, started_at: inputs.started_at.value, amount_ml: readNumber("amount_ml"),
        note: inputs.note.value,
    };
    setBusy(true);
    errorAt("form-error");
    try {
        await api(draft.version ? "/api/feeds/" + draft.id : "/api/feeds", draft.version ? "PUT" : "POST", body);
        editor.close();
        showNotice("已保存记录");
        if (!fromTrend && body.started_at.slice(0, 10) !== (tab === "today" ? today() : day)) {
            day = body.started_at.slice(0, 10);
            setView(day === today() ? "today" : "history");
        } else {
            loadFeeds();
            refreshTrend();
        }
    } catch (error) {
        errorAt("form-error", error.message || "保存失败，请重试");
    } finally {
        setBusy(false);
    }
});

$("delete-feed").addEventListener("click", async () => {
    if (busy || !draft?.version || !window.confirm("删除这条喂奶记录？")) return;
    setBusy(true);
    try {
        const removed = await api("/api/feeds/" + draft.id, "DELETE", {version: draft.version});
        editor.close();
        showNotice("已删除记录", removed);
        loadFeeds();
        refreshTrend();
    } catch (error) {
        errorAt("form-error", error.message);
    } finally {
        setBusy(false);
    }
});

$("undo").addEventListener("click", async () => {
    if (!deleted || $("undo").disabled) return;
    const entry = deleted;
    $("undo").disabled = true;
    try {
        await api("/api/feeds/" + entry.id + "/restore", "POST", {version: entry.version});
        showNotice("已恢复记录");
        loadFeeds();
        refreshTrend();
    } catch (error) {
        showNotice(error.message, entry);
    } finally {
        $("undo").disabled = false;
    }
});

function canUseWaterReference(status) {
    return status.state === "available" && status.water_ml !== null && status.auto_state !== "listening";
}

function renderWeighing() {
    const info = $("p50-weigh");
    const button = $("calibrate-p50");
    const target = p50.weigh_target;
    const recent = p50.recent_feed;
    info.hidden = !p50.weigh_enabled;
    button.hidden = !target || p50.auto_state !== "listening";
    if (info.hidden) return;
    button.textContent = target?.calibrating ? "取消校准" : target?.reference_dg ? "重新校准喂前基准" : "校准喂前基准";
    const result = p50.weigh_result;
    const flow = "空托盘时按一次夜灯键，等约 2 秒放稳奶瓶。去皮后约 4 秒自动取重，放稳后也可再按一下提前取重。";
    const progress = {
        tare: "正在去皮，请保持托盘空着。",
        place: "已去皮。放稳奶瓶后可再按一下夜灯键，立即取重。",
        measure: "正在取重。",
        failed: "这次未保存。请拿下奶瓶，再按夜灯键重新称。",
    }[result?.id === target?.id ? result?.state : ""];
    if (progress) {
        info.textContent = progress;
    } else if (!target && recent?.water_ml && !recent.bottle_number && recent.after_weight_dg == null) {
        info.textContent = "最近一次 P50 备奶记录缺少瓶号，无法用夜灯键关联称重。可用「单独称重」查看克数。";
    } else if (!target) {
        info.textContent = result?.state === "saved"
            ? "最近一次喂后称重已保存。" : "有新的 P50 备奶记录后可称重。";
    } else if (target.calibrating) {
        info.textContent = "校准 " + target.bottle_number + " 号瓶 · 出水 " + target.water_ml
            + " mL。请使用冲好、还没喂的整瓶奶。" + flow;
    } else if (target.reference_dg) {
        info.textContent = target.bottle_number + " 号瓶 · 出水 " + target.water_ml
            + " mL · 喂前基准 " + (target.reference_dg / 10).toFixed(1) + " 克。" + flow;
    } else {
        info.textContent = target.bottle_number + " 号瓶 · 出水 " + target.water_ml
            + " mL。首次使用请校准冲好后、喂之前的整瓶重量。";
    }
}

function manualWeighActive() {
    return ["tare", "place", "measure"].includes(p50?.manual_weight?.state);
}

function renderManualWeighing() {
    const status = $("manual-weight-status");
    const button = $("manual-weigh");
    const cancel = $("cancel-weigh");
    const result = p50.manual_weight;
    const active = manualWeighActive();
    const online = p50.auto_state === "listening";
    status.hidden = $("manual-weight-actions").hidden = !p50.weigh_enabled;
    cancel.hidden = !active;
    button.disabled = manualWeighBusy || !online || (active && result.state !== "place");
    cancel.disabled = manualWeighBusy || !online;
    button.textContent = result?.state === "place" ? "已放稳，取重" : result?.state === "result" ? "再称一次" : "单独称重";
    if (result?.state === "result") {
        status.textContent = "本次实测 " + (result.weight_dg / 10).toFixed(1) + " 克。拿下物品后可以再称。";
        return;
    }
    status.textContent = (online && {
        tare: "正在去皮，请保持托盘空着。",
        place: "去皮完成。请把物品放稳，再点「已放稳，取重」。",
        measure: "正在取重，请保持物品不动。",
        cancelled: "称重已取消。",
        failed: "这次没有取得有效重量。请清空托盘，再试一次。",
    }[result?.state]) || (online ? "清空托盘后，可以单独测一次克重。" : "P50 称重暂不可用。");
}

async function loadP50() {
    const request = ++p50Sequence;
    let status;
    try {
        status = await api("/api/p50");
    } catch {
        status = {state: "unavailable", auto_state: "unknown"};
    }
    if (request !== p50Sequence) return;
    const previous = p50?.weigh_result;
    const result = status.weigh_result;
    p50 = status;
    if (result?.state === "saved" && (previous?.id !== result.id || previous?.state !== "saved")) {
        loadFeeds();
        refreshTrend();
    }
    renderLogActions();
    renderWeighing();
    renderManualWeighing();
    const usable = p50.state === "available" && p50.water_ml !== null;
    const action = $("use-p50");
    action.textContent = p50.recent_feed ? "改最近自动记录" : "带入最近出水";
    action.hidden = !p50.recent_feed && !canUseWaterReference(p50);
    if (usable) {
        const parts = ["最近出水 " + p50.water_ml + " mL"];
        if (p50.bottle_number) parts.push(p50.bottle_number + " 号瓶");
        if (p50.checked_at) parts.push("读取于 " + p50.checked_at.slice(11, 16));
        $("p50-summary").textContent = parts.join(" · ");
    } else {
        $("p50-summary").textContent = {
            disabled: "未接入出水数据",
            unavailable: "暂时无法读取出水数据",
            loading: "正在读取出水数据",
            available: "暂无可用出水记录",
        }[p50.state];
    }
}

async function manualWeigh(action) {
    if (manualWeighBusy || !p50?.weigh_enabled) return;
    const current = p50.manual_weight;
    manualWeighBusy = true;
    renderManualWeighing();
    try {
        const result = await api("/api/p50/weigh", "POST", {action, id: current?.id});
        p50 = {...p50, manual_weight: result};
        await loadP50();
    } catch (error) {
        showNotice(error.message || "暂时无法称重");
    } finally {
        manualWeighBusy = false;
        renderManualWeighing();
    }
}

$("manual-weigh").addEventListener("click", () => {
    manualWeigh(p50?.manual_weight?.state === "place" ? "measure" : "start");
});
$("cancel-weigh").addEventListener("click", () => manualWeigh("cancel"));

$("calibrate-p50").addEventListener("click", async event => {
    const button = event.currentTarget;
    const target = p50?.weigh_target;
    if (!target) return;
    button.disabled = true;
    try {
        await api("/api/p50/weight-reference", "POST", {id: target.id, enabled: !target.calibrating});
        await loadP50();
    } catch (error) {
        showNotice(error.message || "暂时无法更新称重基准");
    } finally {
        button.disabled = false;
    }
});

function syncTheme() {
    const root = document.documentElement;
    $("theme").setAttribute("aria-pressed", String(root.dataset.theme === "dark"));
    const paper = getComputedStyle(root).getPropertyValue("--paper").trim();
    if (paper) document.querySelector('meta[name="theme-color"]').content = paper;
}

const darkPreference = matchMedia("(prefers-color-scheme: dark)");
let chosenTheme;
try { chosenTheme = localStorage.getItem("feeding-theme"); } catch {}
document.documentElement.dataset.theme = chosenTheme || (darkPreference.matches ? "dark" : "light");
syncTheme();
$("theme").addEventListener("click", () => {
    chosenTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = chosenTheme;
    try { localStorage.setItem("feeding-theme", chosenTheme); } catch {}
    syncTheme();
});

$("today-tab").addEventListener("click", () => setView("today"));
$("history-tab").addEventListener("click", () => { day = today(); setView("history"); });
$("previous-day").addEventListener("click", () => changeDay(-1));
$("next-day").addEventListener("click", () => changeDay(1));
$("selected-day").addEventListener("change", event => {
    if (!event.target.value || event.target.value > today()) return;
    day = event.target.value;
    loadFeeds();
});
$("add-bottle").addEventListener("click", () => openEditor());
$("add-first").addEventListener("click", () => openEditor());
$("add-offline").addEventListener("click", () => openEditor());
$("show-all").addEventListener("click", () => {
    showAllToday = !showAllToday;
    renderTimeline();
});
$("edit-latest").addEventListener("click", () => { if (latest) openEditor(latest); });
$("close-trend-day").addEventListener("click", () => {
    const selected = trendDay;
    selectTrendDay(null);
    if (selected) $("trend-chart").querySelector('button[data-day="' + selected + '"]')?.focus();
});
$("trend-toggle").addEventListener("click", () => {
    trendDays = trendDays === 7 ? 14 : 7;
    $("trend-title").textContent = "最近 " + trendDays + " 天";
    $("trend-toggle").textContent = trendDays === 14 ? "回到 7 天" : "看 14 天";
    $("trend-toggle").setAttribute("aria-pressed", String(trendDays === 14));
    loadTrend();
});
$("use-p50").addEventListener("click", async event => {
    const action = event.currentTarget;
    const editing = Boolean(p50?.recent_feed);
    action.disabled = true;
    try {
        const fresh = await api("/api/p50");
        if (editing && fresh.recent_feed) {
            openEditor(fresh.recent_feed);
        } else if (!editing && !fresh.recent_feed && canUseWaterReference(fresh)) {
            openEditor(null, fresh);
        } else {
            loadP50();
            showNotice("P50 状态已更新，请再试");
        }
    } catch (error) {
        showNotice(error.message || "暂时无法读取 P50");
    } finally {
        action.disabled = false;
    }
});
$("close-editor").addEventListener("click", () => editor.close());
editor.addEventListener("cancel", event => { if (busy) event.preventDefault(); });

function setDefaultAmount(data) {
    const amount = data.default_amount_ml;
    if (!Number.isInteger(amount)) return;
    defaultAmount = amount;
    defaultMode = data.default_mode;
    customAmount = data.custom_amount_ml;
    deviceAmount = data.device_amount_ml;
    $("change-default").textContent = "默认 " + amount + " mL";
}

function showAmountSource() {
    const isCustom = settingsForm.elements.default_mode.value === "custom";
    $("custom-amount").hidden = !isCustom;
    settingsForm.elements.default_amount_ml.disabled = !isCustom;
    $("device-amount-reference").textContent = deviceAmount === null
        ? "奶机水量暂未读到。"
        : "奶机最近同步的水量设定为 " + deviceAmount + " mL。";
}

$("change-default").addEventListener("click", () => {
    settingsForm.elements.default_mode.value = defaultMode;
    settingsForm.elements.default_amount_ml.value = customAmount ?? "";
    showAmountSource();
    errorAt("settings-error");
    settings.showModal();
});
settingsForm.elements.default_mode.addEventListener("change", showAmountSource);
$("close-settings").addEventListener("click", () => settings.close());
settings.addEventListener("cancel", event => {
    if ($("save-settings").disabled) event.preventDefault();
});
settingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    const save = $("save-settings");
    const close = $("close-settings");
    if (save.disabled) return;
    save.disabled = close.disabled = true;
    errorAt("settings-error");
    try {
        const mode = settingsForm.elements.default_mode.value;
        const data = await api("/api/settings", "PUT", {
            default_mode: mode,
            default_amount_ml: mode === "custom" ? Number(settingsForm.elements.default_amount_ml.value) : null,
        });
        loadSequence += 1;
        setDefaultAmount(data);
        settings.close();
        showNotice("已更新全家默认奶量");
        loadFeeds();
    } catch (error) {
        errorAt("settings-error", error.message);
    } finally {
        save.disabled = close.disabled = false;
    }
});
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        loadFeeds();
        loadSleep();
        loadP50();
        refreshTrend();
    }
});
setInterval(() => { if (!document.hidden) loadFeeds(); }, 8000);
$("device").addEventListener("toggle", () => { if ($("device").open) loadP50(); });
setInterval(() => { if (!document.hidden && $("device").open) loadP50(); }, 1500);
setInterval(() => { if (!document.hidden && !$("device").open) loadP50(); }, 30000);
setInterval(() => { if (!document.hidden) refreshTrend(); }, 20000);
$("show-camera-alerts").addEventListener("change", renderTimeline);
$("show-camera-cry").addEventListener("change", renderTimeline);
setInterval(() => { if (!document.hidden) loadSleep(); }, 60000);
loadFeeds();
loadSleep();
loadP50();
loadTrend();
