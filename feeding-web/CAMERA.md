# iPhone 摄像头播放入口

页面 `/camera`，首页“看看宝宝”进入。用户点击才建立连接，默认静音；检测到实际视频帧才显示“实时画面”，停止、切后台或离开页面会退频道。iPhone Safari 18及以上具备相应H.265支持基础，但真实设备/编码兼容性仍需用户真机测试；不得把模拟测试或成功获取会话等同于实际播放成功。若浏览器要求安全上下文，需要部署可信HTTPS。

部署新增 camera.py、static/camera.html、camera.js、camera.css，并同步 server.py 和首页。将合法取得的 Agora Web SDK 4.24.1 放在运行主机 static/agora-sdk.js；本仓库不分发此第三方SDK。桥接 service.py 需已登录绑定并支持本机18874端口的 /preview/session 接口。

网页 POST /api/camera/session，复用现有JSON与Origin校验，后端只请求固定本机地址并筛选必要媒体字段；响应禁止缓存。会话令牌和媒体密钥只用于当前播放，不写入仓库、页面URL、数据库或日志。浏览器禁用SDK日志及日志上报。视频由浏览器直接接收与解码，盒子无需持续转码。

本次验证：实机视频会话及页面路由可用；合成数据测试覆盖点击才连接、H.265选择、加密配置、帧检测、静音/行内播放、停止清理与失败重试。iPhone实际出图尚待用户验证。

测试：python3 tests/test_camera.py；tests/ 目录 npm test（合成SDK，不连接真实摄像头）。
