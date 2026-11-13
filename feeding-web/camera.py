"""Same-origin, read-only camera playback session bridge."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

FIELDS = ('appId','rtcToken','channelName','deviceRtcUid','userRtcUid','mediaKey','mediaSalt')

def handle(h, method, path):
    if path not in ('/api/camera/session','/camera-sdk.js'): return False
    Problem = sys.modules[h.__class__.__module__].Problem
    if path == '/camera-sdk.js':
        if method != 'GET': raise Problem(405,'请求方式不支持')
        sdk=Path(__file__).parent/'static/agora-sdk.js'
        if not sdk.is_file(): raise Problem(503,'播放器组件尚未准备好')
        h.reply(200,sdk.read_bytes(),'text/javascript');return True
    if method != 'POST': raise Problem(405,'请从播放页面连接摄像头')
    h.read_json()  # Existing JSON/origin validation applies to this endpoint too.
    request=Request('http://127.0.0.1:18874/preview/session',data=b'',method='POST')
    try:
        with build_opener(ProxyHandler({})).open(request,timeout=20) as response:
            session=json.load(response)
    except HTTPError as exc:
        if exc.code==503:raise Problem(503,'摄像头会话不可用，请检查桥接登录和设备绑定') from None
        raise Problem(502,'摄像头暂时无法连接，请稍后重试') from None
    except (URLError,OSError,ValueError):
        raise Problem(503,'摄像头桥接暂时无法连接，请稍后重试') from None
    if not isinstance(session,dict) or any(not session.get(k) for k in FIELDS[:5]):
        raise Problem(502,'摄像头返回的会话不完整')
    h.send_json({k:session[k] for k in FIELDS if k in session})
    return True
