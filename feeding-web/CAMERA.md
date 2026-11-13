# iPhone 摄像头播放入口

页面 `/camera`，首页“看看宝宝”进入。用户点击才建立连接，默认静音；检测到实际视频帧才显示“实时画面”，停止、切后台或离开页面会退频道。iPhone Safari 18及以上具备相应H.265支持基础，但真实设备/编码兼容性仍需用户真机测试；不得把模拟测试或成功获取会话等同于实际播放成功。若浏览器要求安全上下文，需要部署可信HTTPS。

部署新增 camera.py、static/camera.html、camera.js、camera.css，并同步 server.py 和首页。将合法取得的 Agora Web SDK 4.24.1 放在运行主机 static/agora-sdk.js；本仓库不分发此第三方SDK。桥接 service.py 需已登录绑定并支持本机18874端口的 /preview/session 接口。

网页 POST /api/camera/session，复用现有JSON与Origin校验，后端只请求固定本机地址并筛选必要媒体字段；响应禁止缓存。会话令牌和媒体密钥只用于当前播放，不写入仓库、页面URL、数据库或日志。浏览器禁用SDK日志及日志上报。视频由浏览器直接接收与解码，盒子无需持续转码。

本次验证：实机视频会话及页面路由可用；合成数据测试覆盖点击才连接、H.265选择、加密配置、帧检测、静音/行内播放、停止清理与失败重试。iPhone实际出图尚待用户验证。

测试：python3 tests/test_camera.py；tests/ 目录 npm test（合成SDK，不连接真实摄像头）。

## 局域网 HTTPS

Agora Web SDK 要求 HTTPS 或 localhost，普通局域网 HTTP 不适合直接播放。服务在配置 --tls-dir（默认服务目录下 data/tls）中的 server.crt、server.key 后，同时启动8766端口的HTTPS监听，与原HTTP监听共用同一个设备监听器，不重复连接MQTT。默认安装目录为 /etc/feeding-web/data/tls。原HTTP入口保留，可从 /camera-ca.cer 下载仅包含公开根证书的DER文件；该目录中的私钥永不通过HTTP路由提供。

iPhone 先安装公开根证书，然后在 设置→通用→关于本机→证书信任设置 中开启完全信任，再通过https://本机局域网地址:8766/camera播放。证书名称为 Family Feeding LAN。仅点击浏览器的忽略证书警告不能代替完整信任设置。私钥留在盒子，配置目录设为700、密钥600；证书和密钥均属于运行配置，不提交源码仓库。

服务证书应有对应IP的SAN、serverAuth用途、SHA256签名及不超过365天的有效期。根证书和服务器证书需由部署者自行安全生成；不要共用示例私钥。页面在非安全上下文会显示安装步骤并阻止无效播放；错误提示保留不含令牌的错误码供定位。

已验证：CA校验、IP匹配、HTTPS静态路由和媒体会话。iPhone安装信任后的实际画面仍需用户确认。
