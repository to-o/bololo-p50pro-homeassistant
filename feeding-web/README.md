# 家庭喂养日记

一个手机优先的家庭瓶喂记录页。家人共用同一个地址和时间线，无需账号。首页显示最近一顿、今天的汇总和最近三顿，以及可点开的 7 天或 14 天奶量趋势。补记、修改和撤销删除都直接在页面操作。

默认奶量跟随奶机的水量设定，也可在「P50 设置」改为自定。奶机水量暂不可用时沿用最近同步值，首次未同步时用 60 mL 或已保存的自定值。默认值全家共用，只用于新记录。

## 本机预览

在工作区根目录运行。需要 Python 3.8 或以上版本及标准库的 SQLite 模块。

```sh
python feeding-web/server.py
```

用浏览器打开 `http://127.0.0.1:8765/`。默认数据库为 `feeding-web/data/feeding.sqlite3`。可用 `--db` 指定持久化位置，使用 `--site-title` 配置部署标题。备份时先停止服务，再复制数据库文件。

可在运行主机上加 `--birth-date YYYY-MM-DD`，在标题下显示出生第几天。按上海时间计算，出生当天算第 1 天。

## 家庭使用

在家里常开的主机上运行服务。把 `--bind` 设置为该主机的家庭局域网地址，家人访问该地址的 8765 端口即可共用记录。浏览器按上海时间显示和归档，打开页面或切回前台会刷新记录，前台也会定时同步。

## P50 Pro 只读接入

OpenWrt 可复用已有 BOLOLO 会话。仓库根目录的 `bololo_read_status.py` 是配套只读客户端。首次使用可在 OpenWrt 上运行以下命令，通过交互输入账户信息保存会话。

```sh
python3 bololo_read_status.py --mac DEVICE_MAC --enroll
```

从仓库根目录启动页面，使用实际的局域网地址、标题和设备 MAC。

```sh
python3 feeding-web/server.py \
  --bind LAN_IP \
  --site-title '家庭喂养日记' \
  --db /etc/feeding-web/feeding.sqlite3 \
  --bololo-mac DEVICE_MAC \
  --bololo-client ./bololo_read_status.py \
  --bololo-session /etc/bololo/session.json
```

卡片显示设备的最近一次出水量、瓶号和读取时间。带入表单时，原始出水量作为参考，奶量按家庭默认值预填，可在保存前或之后修改。读取时间是查询时间。P50 数据暂时不可用时，手动记录仍可正常保存。

已有实测 MQTT 地址和设备 ID 时，可以加上 `--bololo-mqtt-host BROKER` 和 `--bololo-device-id DEVICE_ID` 启用自动记录。服务看到出水开始，以及带实测水量的结束上报后，按当时的默认奶量保存。保留机器上报的出水量和观察到的开始时间。连接中断或漏掉开始时，留待手动补记。

## 更新部署

GitHub 的 `main` 分支是源码来源。更新时从同一个提交取 `feeding-web/server.py`、`feeding-web/bololo_events.py` 和 `feeding-web/static/`，再重启现有 OpenWrt 服务。使用该提交的 `bololo_read_status.py` 更新配套只读客户端。部署标题、局域网绑定、设备配置、会话与 SQLite 数据库保存在运行主机。

更新后打开首页，核对 `/api/feeds` 和 `/api/trend?days=7`。启用自动记奶的部署可在 `/api/p50` 查看 `auto_state`，成功订阅后显示 `listening`。
