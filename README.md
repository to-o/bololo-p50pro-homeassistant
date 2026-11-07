# BOLOLO P50 Pro 家庭喂养日记

这个仓库维护家庭局域网喂养网页，以及 BOLOLO P50 Pro 的只读客户端和 MQTT 上报解析。网页支持共享瓶喂记录、补记与修正、7 天和 14 天对比。通过已验证的 P50 出水上报，也可以在手机 App 关闭时自动记一笔。

## 快速运行

需要 Python 3.8 或以上版本。

```sh
python feeding-web/server.py
```

打开 `http://127.0.0.1:8765/`。局域网运行、OpenWrt 配置、自动记奶和更新流程见[部署说明](feeding-web/README.md)。

## 目录

- [网页和 SQLite 服务](feeding-web/)
- [只读状态与会话客户端](bololo_read_status.py)
- [协议实测与研究手册](docs/PROTOCOL_RESEARCH.md)
- [维护计划](docs/CODEX_TASKS.md)

GitHub 的 `main` 维护源码和文档。每户的站点标题、数据库、设备标识和会话由部署主机保存。当前上线的是独立喂养网页，原生 Home Assistant 集成仍是后续工作。
