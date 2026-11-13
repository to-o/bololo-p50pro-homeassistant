# OpenWrt 启动示例

这些是脱敏模板，不覆盖运行主机已有配置。喂养服务部署到 `/etc/feeding-web`；复制本目录 `feeding-web.init` 为 `/etc/init.d/feeding-web`，设置755权限。将 `service.conf.example` 复制为 `/etc/feeding-web/service.conf`，填写实际配置并设为600权限；将根目录 `bololo_read_status.py` 部署为 `/etc/bololo/read_status.py`。数据库及成长档案的恢复见 `../../feeding-web/GROWTH.md`。

海马桥接模板的 `/mnt/storage/haimababi-bridge` 是占位安装目录，先修改为本机实际路径，再安装为 `/etc/init.d/haimababi-bridge`。需要自定义诊断目标时，在本机 `/etc/haimababi-bridge.conf` 设置 `HAIMA_CAMERA_IP`、`HAIMA_P2P_NAME`，不要提交实际文件。

确认两个服务配置与私有运行文件齐备后，可使用 OpenWrt 的 enable/start 命令启用。更新之前使用 SQLite backup API 备份数据库，并备份私有配置；运行中的 SQLite 不应只复制主库而遗漏 WAL。页面自定义宝宝图标保留在运行主机；仓库默认使用通用 favicon。
