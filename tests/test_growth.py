import sys,tempfile,json,threading,urllib.request,urllib.error,uuid
from pathlib import Path
from functools import partial
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'feeding-web'))
import server,growth
assert growth.month_age(__import__('datetime').date(2024,1,31),__import__('datetime').date(2024,2,29))==1
assert growth.month_age(__import__('datetime').date(2024,2,29),__import__('datetime').date(2025,2,28))==12
with tempfile.TemporaryDirectory() as t:
 db=Path(t)/'test.sqlite';server.initialize(db);growth.initialize(db);growth.initialize(db)
 (Path(t)/'growth-profile.json').write_text(json.dumps({'sex':'female','birth_date':'2020-01-02','gestation_weeks':40}))
 h=server.ThreadingHTTPServer(('127.0.0.1',0),partial(server.Handler,database=db,bololo=None));threading.Thread(target=h.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(h.server_port)
 def call(path='/api/growth',method='GET',body=None):
  req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body else None,method=method,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 assert call()[1]['records']==[]
 body={'id':str(uuid.uuid4()),'measured_on':'2020-01-02','weight_kg':3.2,'length_cm':None,'note':'synthetic fixture'}
 assert call(method='POST',body=body)[0]==200
 assert call(method='POST',body=body)[0]==200
 assert len(call()[1]['records'])==1
 path='/api/growth/'+body['id'];body['version']=1;body['weight_kg']=3.4
 assert call(path,'PUT',body)[1]['version']==2
 assert call(path,'PUT',body)[0]==409
 assert call(path,'DELETE',{'version':2})[0]==200
 assert call()[1]['records']==[]
 assert call(path+'/restore','POST',{'version':3})[0]==200
 for value in [None,True,-1,float('nan')]:
  bad={**body,'id':str(uuid.uuid4()),'weight_kg':value};assert call(method='POST',body=bad)[0]==400
 assert call(method='POST',body={**body,'id':str(uuid.uuid4()),'measured_on':'2020-01-01'})[0]==400
 import sqlite3
 with sqlite3.connect(db) as c:assert c.execute('select count(*) from feeds').fetchone()[0]==0
 for identifier in ['ffffffff-ffff-4fff-8fff-ffffffffffff','11111111-1111-4111-8111-111111111111']:
  assert call(method='POST',body={**body,'id':identifier,'measured_on':'2020-01-03'})[0]==200
 rows=call()[1]['records'];assert rows[-1]['id']=='11111111-1111-4111-8111-111111111111'
 assert rows[-1]['age_days']==1
 h.shutdown()
ref=json.loads((Path(__file__).resolve().parents[1]/'feeding-web/static/growth-reference.json').read_text());assert len(ref['weight_kg'])==25 and len(ref['length_cm'])==24
for key in ['weight_kg','length_cm']:
 for row in ref[key]: assert len(row)==7 and row==sorted(row)
assert ref['weight_kg'][0][3]==3.3 and ref['length_cm'][12][3]==75.2
print('PASS: calendar age, schema migration, CRUD, retry idempotency, conflict, undo, validation, feeding isolation, reference structure')
