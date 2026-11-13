import sys,json,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'feeding-web'))
import camera
class Problem(Exception):
 def __init__(self,status,message):self.status=status;self.message=message
class Handler:
 def __init__(self):self.read=False;self.result=None
 def read_json(self):self.read=True;return {}
 def send_json(self,value):self.result=value
class Opener:
 def open(self,*args,**kwargs):return io.BytesIO(json.dumps({'appId':'synthetic','rtcToken':'synthetic','channelName':'synthetic','deviceRtcUid':'2','userRtcUid':'3','extra_secret':'must_not_return'}).encode())
h=Handler()
with patch.object(camera,'build_opener',return_value=Opener()):assert camera.handle(h,'POST','/api/camera/session')
assert h.read and 'extra_secret' not in h.result
try:camera.handle(h,'GET','/api/camera/session');assert False
except Problem as e:assert e.status==405
assert camera.handle(h,'GET','/unrelated') is False
print('PASS: session proxy validates request, whitelists output, rejects GET, leaves other routes intact')
