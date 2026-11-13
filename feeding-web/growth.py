"""Household growth records; female full-term references, WS/T 423-2022 A.2/A.4."""
import calendar
import json
import math
import re
import sqlite3
from datetime import date
from pathlib import Path

SOURCE = 'https://www.nhc.gov.cn/fzs/c100048/202211/5001d7cf57774770a1d49c1df46a291f/files/1733125082501_81468.pdf'

def month_age(born, day):
    months = (day.year-born.year)*12+day.month-born.month
    def anniversary(n):
        y,m=divmod(born.year*12+born.month-1+n,12)
        return date(y,m+1,min(born.day,calendar.monthrange(y,m+1)[1]))
    if day < anniversary(months): months-=1
    a,b=anniversary(months),anniversary(months+1)
    return months+(day-a).days/(b-a).days

def initialize(database):
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS growth_records (id TEXT PRIMARY KEY, measured_on TEXT NOT NULL, weight_kg REAL, length_cm REAL, note TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0)')

def handle(h, method, path):
    if not (path == '/api/growth' or path.startswith('/api/growth/')): return False
    if not re.fullmatch(r'/api/growth(?:/[a-f0-9-]+(?:/restore)?)?', path):
        h.send_json({'error':'没有找到这个接口'},404); return True
    from contextlib import closing
    import sys
    server = sys.modules[h.__class__.__module__]
    Problem, checked_uuid, now = server.Problem, server.checked_uuid, server.now
    with closing(sqlite3.connect(h.database)) as db:
        db.row_factory=sqlite3.Row
        profile_path=Path(h.database).parent/'growth-profile.json'
        if not profile_path.exists(): raise Problem(503,'请先配置宝宝成长档案')
        profile=json.loads(profile_path.read_text())
        born=date.fromisoformat(profile['birth_date'])
        if profile.get('sex')!='female' or profile.get('gestation_weeks',0)<37:
            raise Problem(409,'本版参考曲线适用于足月女童')
        if method=='GET' and path=='/api/growth':
            rows=[dict(r) for r in db.execute('SELECT * FROM growth_records WHERE deleted=0 ORDER BY measured_on,id')]
            for row in rows: row['age_months']=month_age(born,date.fromisoformat(row['measured_on']))
            h.send_json({'profile':profile,'records':rows,'today':now().date().isoformat()});return True
        body=h.read_json()
        identifier=checked_uuid(body.get('id')) if path=='/api/growth' else checked_uuid(path.split('/')[3])
        if method in ('POST','PUT') and not path.endswith('/restore'):
            try:
                day=date.fromisoformat(body.get('measured_on',''))
                if not born<=day<=now().date(): raise ValueError()
                values=[]
                for key,lo,hi in [('weight_kg',0.1,50),('length_cm',20,150)]:
                    v=body.get(key)
                    if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi):raise ValueError()
                    values.append(v)
                note=body.get('note','')
                if all(v is None for v in values) or not isinstance(note,str) or len(note)>200:raise ValueError()
                if month_age(born,day)>=24: raise Problem(400,'本版记录适用于未满2岁，身长请使用卧位测量')
            except (ValueError,TypeError):raise Problem(400,'请核对测量日期、体重和身长，至少填写一项')
        with db:
            if method=='POST' and path=='/api/growth':
                old=db.execute('SELECT * FROM growth_records WHERE id=?',(identifier,)).fetchone()
                if old:
                    if old['deleted'] or tuple(old[k] for k in ['measured_on','weight_kg','length_cm','note'])!=(day.isoformat(),*values,note):raise Problem(409,'记录已变化，请刷新后重试')
                else: db.execute('INSERT INTO growth_records(id,measured_on,weight_kg,length_cm,note) VALUES(?,?,?,?,?)',(identifier,day.isoformat(),*values,note))
            elif method in ('PUT','DELETE') or (method=='POST' and path.endswith('/restore')):
                version=body.get('version')
                if type(version)!=int or version<1: raise Problem(400,'记录版本无效')
                if method=='PUT':
                    sql='UPDATE growth_records SET measured_on=?,weight_kg=?,length_cm=?,note=?,version=version+1 WHERE id=? AND version=? AND deleted=0'
                    args=(day.isoformat(),*values,note,identifier,version)
                else:
                    restore=method=='POST'
                    sql='UPDATE growth_records SET deleted=?,version=version+1 WHERE id=? AND version=? AND deleted=?'
                    args=(0 if restore else 1,identifier,version,1 if restore else 0)
                if db.execute(sql,args).rowcount!=1:raise Problem(409,'家人已修改这条记录，请刷新后重试')
            else:raise Problem(404,'没有找到这个接口')
        h.send_json(dict(db.execute('SELECT * FROM growth_records WHERE id=?',(identifier,)).fetchone()))
    return True
