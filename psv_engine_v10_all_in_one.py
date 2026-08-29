################################################################################
# PSV Engine v10.5.1 - All-in-One Source Archive
# Total files: 40\n################################################################################

\n================================================================================\n# FILE [1/40]: backfill_messages.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""补登记历史发送记录到 messages 表，使通信时间线可见。"""
import sqlite3
import time

DB_PATH = 'data/psv.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 查询所有已发送的序列记录（stage > 0 且不是 failed）
    rows = conn.execute("""
        SELECT es.norm, es.stage, es.last_sent_at, l.name, l.emails
        FROM email_sequence es
        LEFT JOIN leads l ON es.norm = l.norm
        WHERE es.stage > 0 AND es.status != 'failed'
    """).fetchall()

    print(f"找到 {len(rows)} 条已发送记录，开始补登记...")
    count = 0
    for r in rows:
        norm = r['norm']
        stage = r['stage']
        name = r['name'] or norm
        emails = r['emails'] or ''
        to = emails.split(',')[0].strip() if emails else '(无邮箱)'
        subject = f'Candle supply partnership - {name}'

        # 检查是否已经补过记录，避免重复
        existing = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE lead_norm=? AND content LIKE ?",
            (norm, f'[第{stage}封已发送]%')
        ).fetchone()[0]

        if existing > 0:
            continue

        content = f'[第{stage}封已发送] 收件人: {to} | 主题: {subject}\n\n(历史发送，正文未保存)'
        ts = r['last_sent_at'] if r['last_sent_at'] else time.time()

        conn.execute(
            "INSERT INTO messages(lead_norm, direction, channel, content, draft, ts) VALUES(?,?,?,?,?,?)",
            (norm, 'out', 'email', content, 0, ts)
        )
        count += 1

    conn.commit()
    print(f"补登记完成，新增 {count} 条通信记录。")
    conn.close()

if __name__ == "__main__":
    main()\n\n================================================================================\n# FILE [2/40]: core/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [3/40]: core/config/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [4/40]: core/config/settings.py\n================================================================================\n\n# -*- coding: utf-8 -*-
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
def _env():
    p=PROJECT_ROOT/'.env'
    if p.exists():
        raw=p.read_bytes()
        text=''
        for enc in ('utf-8-sig','utf-16'):
            try: text=raw.decode(enc); break
            except Exception: continue
        if not text: text=raw.decode('utf-8','ignore')
        for line in text.replace('\x00','').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k.strip(), v.strip())
_env()
VERSION='v18.3.0'
LLM_BASE_URL=os.getenv('LLM_BASE_URL','http://192.168.1.26:8081/v1')
LLM_MODEL=os.getenv('LLM_MODEL','deepseek-r1-distill-llama-70b')
LLM_API_KEY=os.getenv('LLM_API_KEY','not-needed')
LLM_TIMEOUT=int(os.getenv('LLM_TIMEOUT','480'))
LLM_MAX_TOKENS=int(os.getenv('LLM_MAX_TOKENS','4096'))
DATABASE_PATH=os.getenv('DATABASE_PATH', str(PROJECT_ROOT/'data'/'psv.db'))
IMPORT_DIR=str(PROJECT_ROOT/'data'/'imports')
CUSTOMS_DIR=str(PROJECT_ROOT/'data'/'customs')
WEB_HOST=os.getenv('WEB_HOST','0.0.0.0'); WEB_PORT=int(os.getenv('WEB_PORT','8090'))
SOURCE_PER_LIMIT=int(os.getenv('SOURCE_PER_LIMIT','30'))
AGGREGATE_MIN_RESULTS=int(os.getenv('AGGREGATE_MIN_RESULTS','25'))
PROFILE_TOP_N=int(os.getenv('PROFILE_TOP_N','10')); ANALYSIS_TOP_N=int(os.getenv('ANALYSIS_TOP_N','10')); LETTER_TOP_N=int(os.getenv('LETTER_TOP_N','5'))
IMPORTYETI_ENABLED=os.getenv('IMPORTYETI_ENABLED','false').lower()=='true'
IMPORTYETI_SEARCH_URL=os.getenv('IMPORTYETI_SEARCH_URL','https://www.importyeti.com/api/search')
IMPORTYETI_DAILY_QUOTA=int(os.getenv('IMPORTYETI_DAILY_QUOTA','25'))
IMPORTYETI_QUOTA_RESERVE=int(os.getenv('IMPORTYETI_QUOTA_RESERVE','5'))
IMPORTYETI_MAX_PAGES=int(os.getenv('IMPORTYETI_MAX_PAGES','1'))
BING_CN_ENABLED=os.getenv('BING_CN_ENABLED','false').lower()=='true'
HS_FINDER_ENABLED=os.getenv('HS_FINDER_ENABLED','true').lower()=='true'
HS_CODES=os.getenv('HS_CODES','3406')
CONTACT_ENABLED=os.getenv('CONTACT_ENABLED','true').lower()=='true'
CONTACT_TOP_N=int(os.getenv('CONTACT_TOP_N','10'))
CONTACT_HARD_STD=os.getenv('CONTACT_HARD_STD','true').lower()=='true'
CONTACT_MODE=os.getenv('CONTACT_MODE','webai_first')
# ---- v18.3.0 资料审核 ----
AUDIT_ENABLED=os.getenv('AUDIT_ENABLED','true').lower()=='true'
AUDIT_AI_MODE=os.getenv('AUDIT_AI_MODE','always')
AUDIT_AI_PER_RUN=int(os.getenv('AUDIT_AI_PER_RUN','30'))
# ---- v18.0 邮件发送 ----
MAIL_PROVIDER=os.getenv('MAIL_PROVIDER','outlook')
SMTP_HOST=os.getenv('SMTP_HOST','smtp-mail.outlook.com')
SMTP_PORT=int(os.getenv('SMTP_PORT','587'))
SMTP_USER=os.getenv('SMTP_USER','changlihua925@outlook.com')
SMTP_PASS=os.getenv('SMTP_PASS','')
SMTP_FROM=os.getenv('SMTP_FROM','')
# ---- v16.5 网页AI ----
WEBAI_ENABLED=os.getenv('WEBAI_ENABLED','true').lower()=='true'
WEBAI_ENGINE=os.getenv('WEBAI_ENGINE','chatgpt')   # 主引擎 GPT，备用 DeepSeek
WEBAI_DAILY_MAX=int(os.getenv('WEBAI_DAILY_MAX','200'))
WEBAI_MIN_INTERVAL=int(os.getenv('WEBAI_MIN_INTERVAL','15'))
WEBAI_TIMEOUT=int(os.getenv('WEBAI_TIMEOUT','150'))
WEBAI_PER_RUN=int(os.getenv('WEBAI_PER_RUN','50'))
# ---- v17 署名与工厂档案 ----
SENDER_NAME=os.getenv('SENDER_NAME','常立华')
SENDER_NAME_EN=os.getenv('SENDER_NAME_EN','Lihua Chang')
SENDER_PHONE=os.getenv('SENDER_PHONE','+86 17303304256')
SENDER_EMAIL=os.getenv('SENDER_EMAIL','changlihua925@outlook.com')
SENDER_COMPANY=os.getenv('SENDER_COMPANY','Ningjin Birthday Candle Factory')
# ---- v17 网络扩张预算 ----
EXPAND_BUYERS=int(os.getenv('EXPAND_BUYERS','5'))
EXPAND_CUSTOMERS=int(os.getenv('EXPAND_CUSTOMERS','15'))
EXPAND_MAX_NEW=int(os.getenv('EXPAND_MAX_NEW','40'))
DDG_ENABLED=os.getenv('DDG_ENABLED','false').lower()=='true'
DATA_SOURCE_TIMEOUT=int(os.getenv('DATA_SOURCE_TIMEOUT','12'))
SCRAPE_PROXY_URL=os.getenv('SCRAPE_PROXY_URL','')
EVOLUTION_TRIGGER_RUNS=int(os.getenv('EVOLUTION_TRIGGER_RUNS','3'))
EVOLUTION_MAX_QUERY_VARIANTS=int(os.getenv('EVOLUTION_MAX_QUERY_VARIANTS','2'))
GATE_MIN_QUALIFIED=int(os.getenv('GATE_MIN_QUALIFIED','3'))
GATE_MIN_STRONG=int(os.getenv('GATE_MIN_STRONG','1'))
# ---- v14 反向收割 ----
APIFY_TOKEN=os.getenv('APIFY_TOKEN','')
APIFY_ACTOR=os.getenv('APIFY_ACTOR','logiover~importyeti-scraper')
APIFY_RUN_TIMEOUT=int(os.getenv('APIFY_RUN_TIMEOUT','420'))
APIFY_MAX_SUPPLIERS_PER_RUN=int(os.getenv('APIFY_MAX_SUPPLIERS_PER_RUN','3'))
APIFY_COMPANY_INPUT=os.getenv('APIFY_COMPANY_INPUT','{"mode":"companySearch","companySlug":"{slug}","maxResults":50}')
HARVEST_ENABLED=os.getenv('HARVEST_ENABLED','true').lower()=='true'
HARVEST_MIN_SHIPMENTS=int(os.getenv('HARVEST_MIN_SHIPMENTS','1'))
# ---- v14.1 ImportYeti 网页收割 ----
IY_WEB_ENABLED=os.getenv('IY_WEB_ENABLED','true').lower()=='true'
IY_WEB_HEADLESS=os.getenv('IY_WEB_HEADLESS','true').lower()=='true'
IY_WEB_AUTO_HEADED=os.getenv('IY_WEB_AUTO_HEADED','true').lower()=='true'
IY_WEB_CHALLENGE_WAIT=float(os.getenv('IY_WEB_CHALLENGE_WAIT','30'))
IY_WEB_CDP_ENABLED=os.getenv('IY_WEB_CDP_ENABLED','true').lower()=='true'
IY_WEB_CDP_URL=os.getenv('IY_WEB_CDP_URL','http://127.0.0.1:9222')
IY_WEB_DELAY_MIN=float(os.getenv('IY_WEB_DELAY_MIN','4'))
IY_WEB_DELAY_MAX=float(os.getenv('IY_WEB_DELAY_MAX','8'))
IY_WEB_SEARCH_LIMIT=int(os.getenv('IY_WEB_SEARCH_LIMIT','25'))
IY_WEB_TOP_BUYERS=int(os.getenv('IY_WEB_TOP_BUYERS','5'))
IY_WEB_MAX_SUPPLIERS=int(os.getenv('IY_WEB_MAX_SUPPLIERS','3'))
IY_WEB_MAX_CUSTOMERS=int(os.getenv('IY_WEB_MAX_CUSTOMERS','25'))
# ---- v15 ExpertGraph ----
EXPERT_MODE=os.getenv('EXPERT_MODE','true').lower()=='true'
REFLECT_MAX_ROUNDS=int(os.getenv('REFLECT_MAX_ROUNDS','3'))
LLM_REVIEW_MAX_TOKENS=int(os.getenv('LLM_REVIEW_MAX_TOKENS','900'))
LLM_REVIEW_TIMEOUT=int(os.getenv('LLM_REVIEW_TIMEOUT','240'))
# ---- v14 USITC ----
USITC_TOKEN=os.getenv('USITC_TOKEN','')
USITC_API_URL=os.getenv('USITC_API_URL','https://datawebws.usitc.gov/dataweb/api/v2/report2/runReport')
USITC_HS_CODE=os.getenv('USITC_HS_CODE','3406')
USITC_NOTES_FILE=os.getenv('USITC_NOTES_FILE', str(PROJECT_ROOT/'data'/'usitc_notes.txt'))
for p in (Path(DATABASE_PATH).parent, Path(IMPORT_DIR), Path(CUSTOMS_DIR)): p.mkdir(parents=True, exist_ok=True)
\n\n================================================================================\n# FILE [5/40]: core/memory/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [6/40]: core/memory/db.py\n================================================================================\n\nimport re,sqlite3,time,json
from core.config import settings

LEAD_COLS=[('website','TEXT'),('emails','TEXT'),('phones','TEXT'),('address','TEXT'),('linkedin','TEXT'),('contact_person','TEXT'),('score','REAL'),('grade','TEXT'),('profile','TEXT'),('zone','TEXT'),('touch_status','TEXT'),('last_touch','REAL'),('audit','TEXT')]
MSG_SQL="""CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,lead_norm TEXT,direction TEXT,channel TEXT,content TEXT,draft INT,ts REAL);"""

class DB:
    def __init__(self,path=None): self.path=path or settings.DATABASE_PATH; self.init()
    def c(self): return sqlite3.connect(self.path,timeout=10)
    def init(self):
        with self.c() as x:
            x.executescript('''
            CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,request TEXT,status TEXT,result TEXT,created_at REAL,updated_at REAL);
            CREATE TABLE IF NOT EXISTS icp_cards(id INTEGER PRIMARY KEY AUTOINCREMENT,market TEXT,industry TEXT,card TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS companies(norm TEXT PRIMARY KEY,name TEXT,country TEXT,industry TEXT,type TEXT,website TEXT,source TEXT,strength INT,freshness REAL,updated_at REAL);
            CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY AUTOINCREMENT,norm TEXT,kind TEXT,content TEXT,source TEXT,ts REAL);
            CREATE TABLE IF NOT EXISTS raw_sources(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT,query TEXT,payload TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS search_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,project_key TEXT,market TEXT,industry TEXT,limit_n INT,result_count INT,used_sources TEXT,source_errors TEXT,gate TEXT,evolved INT,created_at REAL);
            CREATE TABLE IF NOT EXISTS project_evolution(project_key TEXT PRIMARY KEY,run_count INT,evolved INT,updated_at REAL);
            CREATE TABLE IF NOT EXISTS source_quota(source TEXT,day TEXT,count INT,UNIQUE(source,day));
            CREATE TABLE IF NOT EXISTS customs_raw(id INTEGER PRIMARY KEY AUTOINCREMENT,row_hash TEXT UNIQUE,bol TEXT,ts REAL,importer TEXT,importer_norm TEXT,shipper TEXT,notify TEXT,hs TEXT,descr TEXT,qty REAL,weight REAL,teu REAL,origin TEXT,port_load TEXT,port_discharge TEXT,source_file TEXT,direct_importer INT,created_at REAL);
            CREATE TABLE IF NOT EXISTS buyers_90d(importer_norm TEXT PRIMARY KEY,importer TEXT,first_seen REAL,last_seen REAL,shipments INT,total_weight REAL,total_qty REAL,total_teu REAL,supplier_count INT,origins TEXT,ports TEXT,sample_desc TEXT,score REAL,reasons TEXT,updated_at REAL);
            CREATE TABLE IF NOT EXISTS suppliers(supplier_norm TEXT PRIMARY KEY,name TEXT,slug TEXT,shipments INT,first_seen REAL,last_seen REAL,harvested_at REAL,bol_fetched INT,updated_at REAL);
            CREATE TABLE IF NOT EXISTS company_state(norm TEXT PRIMARY KEY,name TEXT,first_seen REAL,last_seen REAL,runs_seen INT,profiled INT,source TEXT);
            CREATE TABLE IF NOT EXISTS harvest_log(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,slug TEXT,supplier TEXT,mode TEXT,status TEXT,items INT,note TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS usitc_cache(id INTEGER PRIMARY KEY AUTOINCREMENT,hs TEXT,kind TEXT,payload TEXT,created_at REAL);
            CREATE TABLE IF NOT EXISTS leads(norm TEXT PRIMARY KEY,name TEXT,country TEXT,kind TEXT,hs_code TEXT,shipments INT,last_shipment TEXT,tags TEXT,segment TEXT,desc_sample TEXT,source TEXT,first_seen REAL,last_seen REAL,status TEXT);
            '''+MSG_SQL+'''
            ''')
            have={r[1] for r in x.execute('PRAGMA table_info(leads)')}
            for col,typ in LEAD_COLS:
                if col not in have: x.execute('ALTER TABLE leads ADD COLUMN '+col+' '+typ)
            x.execute("UPDATE leads SET zone='pool' WHERE zone IS NULL OR zone=''")
    def save_task(self,tid,req,status,result):
        now=time.time()
        with self.c() as x: x.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET status=excluded.status,result=excluded.result,updated_at=excluded.updated_at',(tid,req,status,json.dumps(result,ensure_ascii=False),now,now))
    @staticmethod
    def _norm(n): return re.sub(r'[^a-z0-9]+','',str(n or '').lower())
    def upsert_leads(self,items):
        now=time.time()
        with self.c() as x:
            for c in items or []:
                nm=(c.get('name') or '').strip()
                if len(nm)<3: continue
                norm=self._norm(nm)
                old=x.execute('SELECT tags,shipments,segment,source,first_seen FROM leads WHERE norm=?',(norm,)).fetchone()
                tags=c.get('tags') or []
                if isinstance(tags,list): tags=','.join(tags)
                if old:
                    ot=set(t for t in (old[0] or '').split(',') if t); nt=set(t for t in tags.split(',') if t)
                    tags=','.join(sorted(ot|nt))
                    ship=max(old[1] or 0,int(c.get('shipments') or 0))
                    seg=c.get('segment') or old[2] or ''
                    src=old[3] if c.get('source') in (old[3] or '') else (old[3]+'+'+c.get('source','')).strip('+')
                    x.execute('UPDATE leads SET name=?,country=?,kind=?,hs_code=?,shipments=?,last_shipment=?,tags=?,segment=?,desc_sample=?,source=?,last_seen=?,status=? WHERE norm=?',
                        (nm,c.get('country',''),c.get('kind',''),c.get('hs_code',''),ship,c.get('last_shipment',''),tags,seg,c.get('desc_sample','')[:300],src,now,c.get('status') or 'new',norm))
                else:
                    x.execute('INSERT INTO leads(norm,name,country,kind,hs_code,shipments,last_shipment,tags,segment,desc_sample,source,first_seen,last_seen,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (norm,nm,c.get('country',''),c.get('kind',''),c.get('hs_code',''),int(c.get('shipments') or 0),c.get('last_shipment',''),tags,c.get('segment',''),c.get('desc_sample','')[:300],c.get('source',''),now,now,c.get('status') or 'new'))
    def list_leads(self,kind=None,segment=None,q=None,zone=None,limit=500):
        sql='SELECT * FROM leads WHERE 1=1'; args=[]
        if kind: sql+=' AND kind=?'; args.append(kind)
        if segment: sql+=' AND segment=?'; args.append(segment)
        if zone: sql+=' AND zone=?'; args.append(zone)
        if q: sql+=' AND name LIKE ?'; args.append('%'+q+'%')
        sql+=' ORDER BY COALESCE(score,0) DESC,shipments DESC,last_seen DESC LIMIT ?'; args.append(int(limit))
        with self.c() as x:
            x.row_factory=sqlite3.Row
            return [dict(r) for r in x.execute(sql,args).fetchall()]
    def get_lead(self,norm):
        with self.c() as x:
            x.row_factory=sqlite3.Row
            r=x.execute('SELECT * FROM leads WHERE norm=?',(norm,)).fetchone()
            return dict(r) if r else None
    def lead_update(self,norm,**kw):
        if not kw: return
        sql='UPDATE leads SET '+','.join(k+'=?' for k in kw)+' WHERE norm=?'
        with self.c() as x: x.execute(sql,tuple(kw.values())+(norm,))
    def set_zone(self,norm,zone,touch_status=None):
        kw={'zone':zone}
        if touch_status is not None: kw['touch_status']=touch_status; kw['last_touch']=time.time()
        self.lead_update(norm,**kw)
    def add_message(self,norm,direction,channel,content,draft=0):
        with self.c() as x: x.execute('INSERT INTO messages(lead_norm,direction,channel,content,draft,ts) VALUES(?,?,?,?,?,?)',(norm,direction,channel,content,int(draft),time.time()))
        self.lead_update(norm,last_touch=time.time())
    def get_message(self,mid):
        with self.c() as x:
            x.row_factory=sqlite3.Row
            r=x.execute('SELECT * FROM messages WHERE id=?',(int(mid),)).fetchone()
            return dict(r) if r else None
    def delete_message(self,mid):
        with self.c() as x: x.execute('DELETE FROM messages WHERE id=?',(int(mid),))
    def update_message(self,mid,content):
        with self.c() as x: x.execute('UPDATE messages SET content=? WHERE id=?',(str(content),int(mid)))
    def list_messages(self,norm,limit=100):
        with self.c() as x:
            x.row_factory=sqlite3.Row
            return [dict(r) for r in x.execute('SELECT * FROM messages WHERE lead_norm=? ORDER BY ts ASC LIMIT ?',(norm,int(limit))).fetchall()]
    def get_task(self,tid):
        with self.c() as x: r=x.execute('SELECT request,status,result FROM tasks WHERE task_id=?',(tid,)).fetchone()
        return None if not r else {'request':r[0],'status':r[1],'result':json.loads(r[2] or '{}')}
\n\n================================================================================\n# FILE [7/40]: core/memory/experience.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""经验库模块"""
import sqlite3, time, json
from core.config import settings

SQL_EXPERIENCE = '''CREATE TABLE IF NOT EXISTS experience(
id INTEGER PRIMARY KEY AUTOINCREMENT,
type TEXT NOT NULL,
key TEXT,
value TEXT,
score REAL DEFAULT 0,
count INTEGER DEFAULT 0,
updated_at REAL
)'''

SQL_RULES = '''CREATE TABLE IF NOT EXISTS runtime_rules(
id INTEGER PRIMARY KEY AUTOINCREMENT,
rule_type TEXT,
rule_key TEXT,
rule_value TEXT,
enabled INTEGER DEFAULT 1,
updated_at REAL
)'''

class Experience:
    def __init__(self, db_path=None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._conn() as c:
            c.execute(SQL_EXPERIENCE)
            c.execute(SQL_RULES)

    def record(self, exp_type, key, value, score=0.0):
        now = time.time()
        with self._conn() as c:
            row = c.execute('SELECT id, score, count FROM experience WHERE type=? AND key=?', (exp_type, key)).fetchone()
            if row:
                new_count = row[2] + 1
                new_score = (row[1] * (new_count - 1) + score) / new_count
                c.execute('UPDATE experience SET value=?, score=?, count=?, updated_at=? WHERE id=?',
                          (json.dumps(value, ensure_ascii=False), new_score, new_count, now, row[0]))
            else:
                c.execute('INSERT INTO experience(type, key, value, score, count, updated_at) VALUES(?,?,?,?,?,?)',
                          (exp_type, key, json.dumps(value, ensure_ascii=False), score, 1, now))

    def get(self, exp_type, key):
        with self._conn() as c:
            row = c.execute('SELECT value, score, count FROM experience WHERE type=? AND key=?', (exp_type, key)).fetchone()
        if row:
            return {'value': json.loads(row[0]), 'score': row[1], 'count': row[2]}
        return None

    def best(self, exp_type, limit=5):
        with self._conn() as c:
            rows = c.execute('SELECT key, value, score, count FROM experience WHERE type=? ORDER BY score DESC LIMIT ?',
                             (exp_type, limit)).fetchall()
        return [{'key': r[0], 'value': json.loads(r[1]), 'score': r[2], 'count': r[3]} for r in rows]

    def all(self, exp_type=None):
        with self._conn() as c:
            if exp_type:
                rows = c.execute('SELECT type, key, value, score, count FROM experience WHERE type=?', (exp_type,)).fetchall()
            else:
                rows = c.execute('SELECT type, key, value, score, count FROM experience').fetchall()
        return [
            {'type': r[0], 'key': r[1], 'value': json.loads(r[2]), 'score': r[3], 'count': r[4]}
            for r in rows
        ]

    def add_rule(self, rule_type, rule_key, rule_value):
        now = time.time()
        with self._conn() as c:
            c.execute('INSERT OR REPLACE INTO runtime_rules(rule_type, rule_key, rule_value, enabled, updated_at) VALUES(?,?,?,?,?)',
                      (rule_type, rule_key, rule_value, 1, now))

    def get_rules(self, rule_type=None):
        with self._conn() as c:
            if rule_type:
                rows = c.execute('SELECT rule_type, rule_key, rule_value FROM runtime_rules WHERE rule_type=? AND enabled=1', (rule_type,)).fetchall()
            else:
                rows = c.execute('SELECT rule_type, rule_key, rule_value FROM runtime_rules WHERE enabled=1').fetchall()
        return [{'rule_type': r[0], 'rule_key': r[1], 'rule_value': r[2]} for r in rows]\n\n================================================================================\n# FILE [8/40]: core/model/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [9/40]: core/model/client.py\n================================================================================\n\nimport json,time,urllib.request
from core.config import settings
class ModelClient:
    _h={}
    def __init__(self): self.base=settings.LLM_BASE_URL.rstrip('/'); self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def health(self):
        now=time.time(); c=self._h.get(self.base)
        if c and c[0] and now-c[1]<10: return True
        ok=False
        try:
            req=urllib.request.Request(self.base+'/models',headers={'Authorization':'Bearer '+settings.LLM_API_KEY})
            with self.opener.open(req,timeout=5) as r: ok=r.status==200
        except Exception: ok=False
        self._h[self.base]=(ok,now); return ok
    def chat(self,prompt,system=None,temperature=0.3,max_tokens=None,timeout=None):
        body={'model':settings.LLM_MODEL,'messages':([] if not system else [{'role':'system','content':system}])+[{'role':'user','content':prompt}],'temperature':temperature,'max_tokens':int(max_tokens or settings.LLM_MAX_TOKENS),'stream':False}
        req=urllib.request.Request(self.base+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+settings.LLM_API_KEY})
        try:
            with self.opener.open(req,timeout=int(timeout or settings.LLM_TIMEOUT)) as r: return json.loads(r.read().decode())['choices'][0]['message']['content']
        except Exception:
            self._h.pop(self.base,None); return None
\n\n================================================================================\n# FILE [10/40]: core/model/reasoning.py\n================================================================================\n\nfrom core.model.client import ModelClient
from core.utils.jsonutil import j,jl
from core.config import settings
class ReasoningEngine:
    def __init__(self,model=None): self.model=model or ModelClient()
    @property
    def available(self): return self.model.health()
    def json(self,prompt,system=None,as_list=False,temperature=0.3):
        if not self.model.health(): return [] if as_list else None
        t=self.model.chat(prompt,system=system,temperature=temperature)
        if not t: return [] if as_list else None
        return jl(t) if as_list else j(t)
    def text(self,prompt,system=None,temperature=0.3,max_tokens=None):
        """自由文本调用（专家推理/诊断用）"""
        if not self.model.health(): return ''
        return self.model.chat(prompt,system=system,temperature=temperature,
                               max_tokens=max_tokens or settings.LLM_REVIEW_MAX_TOKENS,
                               timeout=settings.LLM_REVIEW_TIMEOUT) or ''
    def review(self,prompt,system=None):
        """专家复核调用：小 tokens、低温度、强制 JSON 结论"""
        if not self.model.health(): return None
        t=self.model.chat(prompt,system=system,temperature=0.2,
                          max_tokens=settings.LLM_REVIEW_MAX_TOKENS,
                          timeout=settings.LLM_REVIEW_TIMEOUT)
        return j(t) if t else None
\n\n================================================================================\n# FILE [11/40]: core/runtime/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [12/40]: core/runtime/experts.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v15 ExpertGraph 专家层：每个节点一位有验收标准的专家。
三段式：执行(确定性代码) → 专家复核(LLM 人设+验收清单) → 判定(pass/fail/degraded)。
复核结论写入 state['node_reports'] 共享认知通道：下游节点可读上游判断，UI 可展开验收明细。
LLM 离线时自动降级为规则验收（verdict=degraded），流程不中断。"""
import time
from core.config import settings
from core.model.reasoning import ReasoningEngine
# ---------- 专家注册表：人设 + 使命 + 验收标准说明 ----------
EXPERTS={
 'ICP':{'role':'资深外贸客户画像师','mission':'把行业输入转化为可执行的客户画像契约：必收信号、拒收信号、关键词、HS 编码。契约是后续所有节点的判定基准。',
        'accept':['契约含明确的必收信号','契约含明确的拒收信号','关键词/HS 编码与行业强相关']},
 'STRATEGY':{'role':'搜索策略师','mission':'基于 ICP 契约、进化变体与复盘建议，制定本轮搜索查询词组合，覆盖买家直搜与供应商反查两条线。',
        'accept':['至少1个查询词','查询词与 ICP 关键词一致','有复盘建议时必须回应建议']},
 'A_COLLECT':{'role':'采集质检员','mission':'检验采集到的候选公司：是否真实存在、是否 ICP 相关、是否垃圾名片（词典/电商/货代）、覆盖度是否足够。',
        'accept':['候选数≥1','无明显的词典/翻译/电商垃圾','至少部分候选带出货量等硬证据']},
 'SUPPLIER_MINING':{'role':'供应链分析师','mission':'评估同行工厂池质量：供应商是否真实蜡烛/家居香氛工厂、出货量是否值得收割、slug 是否可用于反查。',
        'accept':['池内供应商与行业相关','至少1家未收割供应商（或均已收割属正常终态）']},
 'REVERSE_HARVEST':{'role':'收割评估员','mission':'评估反向收割产出：透视出的新同行、收割到的新买家数量与质量、失败原因归类（风控/结构变化/无数据）。',
        'accept':['透视或收割至少产生新线索','失败原因已正确归类']},
 'CLEAN_VERIFY':{'role':'数据管家','mission':'核对清洗分流结果：跨轮去重是否正确、新增/已知/剔除三类计数是否自洽。',
        'accept':['计数自洽（新增+已知+剔除=输入）','已知公司只做记录不进下游']},
 'A_GATE':{'role':'资格审判官','mission':'逐家审判新增候选： accept/reject 并给出理由。只放行有真实进口证据或强相关的美国公司，宁缺毋滥。',
        'accept':['逐家给出 accept/reject 理由','放行标准与 ICP 契约一致','合格数达到闸门阈值才放行']},
 'USITC':{'role':'宏观情报员','mission':'把 USITC 数据/手工情报浓缩成开发信可用的一句话弹药（趋势、数字、来源）。无数据时明确跳过。',
        'accept':['有数据→产出可引用的一句弹药','无数据→明确标记跳过不编造']},
 'RANK':{'role':'采购优先级顾问','mission':'按证据强度与采购潜力排序，给每家公司一句排序理由，硬证据优先。',
        'accept':['排序覆盖全部合格公司','每家有一句排序理由']},
 'CONTACT':{'role':'联系方式提取员','mission':'为合格进口商补全官网/邮箱/电话/地址，并把评分与等级落库。提取失败不阻断流程，如实记录。',
        'accept':['评分与等级已写入客户库','有联系方式缺口时尝试补全并记录结果']},
 'AUDIT':{'role':'资料审核员','mission':'对补全后的联系方式进行多重校验，包括格式、黑名单、交叉一致、活性和GPT复核，确保资料真实可用。',
        'accept':['所有字段通过或达到重试上限','审核结论已写入共享状态']},
 'CORRECT':{'role':'资料修正员','mission':'根据审核反馈修正联系方式，优先使用AI建议，无建议则清空失败字段等待重新补全或人工处理。',
        'accept':['修正后进入重新审核','修正次数不超过最大重试上限']},
 'B_PROFILE':{'role':'客户画像专家','mission':'为 TopN 公司生成采购画像（产品线、规模、渠道、切入点）。',
        'accept':['画像份数=预期 TopN','每份画像含切入点建议']},
 'C_ANALYSIS':{'role':'采购机会分析师','mission':'评估每家公司的采购机会与优先级，优先分析有提单硬证据的公司。',
        'accept':['分析份数=预期 TopN','结论有证据支撑不空泛']},
 'D_OUTREACH':{'role':'开发信撰稿人','mission':'为 TopN 公司写简短英文开发信，自然引用品类相关性/宏观数据，不编造数字。',
        'accept':['信件份数=预期 TopN','英文、简短、无编造数据']},
 'REFLECT':{'role':'复盘诊断师','mission':'诊断上游失败根因（查询词太窄/垃圾结果/风控/闸门过严），开出可执行的纠正处方：新查询词+调整建议。',
        'accept':['诊断指到具体根因','给出新的查询词或明确放弃理由']},
}
_SYS='你是{role}。{mission}\n以专家标准复核给你的工作结果，只输出JSON：{{"verdict":"pass或fail","thinking":"推理过程,150字内","criteria":[{{"name":"验收项","ok":true或false,"detail":"一句依据"}}],"notes":"给下游节点的一句话交接建议"}}'
def _engine():
    global _ENG
    try: return _ENG
    except NameError:
        _ENG=ReasoningEngine(); return _ENG
def review(node,subject,rule_checks=None,critical=None):
    """专家复核主入口。
    node: 节点名；subject: 给专家看的工作结果摘要；
    rule_checks: [(name,ok,detail)] 确定性规则验收；critical: 其中一票否决的项名集合。
    返回 report: {role,verdict,criteria,thinking,notes,offline,ts}"""
    rule_checks=rule_checks or []; critical=critical or set()
    exp=EXPERTS.get(node,{'role':'专家','mission':'复核工作结果','accept':[]})
    report={'role':exp['role'],'mission':exp['mission'],'verdict':'pass',
            'criteria':[{'name':n,'ok':bool(ok),'detail':d,'by':'rule'} for n,ok,d in rule_checks],
            'thinking':'','notes':'','offline':False,'ts':time.time()}
    rule_fail=[c for c in report['criteria'] if not c['ok'] and c['name'] in critical]
    if not settings.EXPERT_MODE:
        report['thinking']='EXPERT_MODE 关闭，仅规则验收'
        report['verdict']='fail' if rule_fail else 'pass'
        return report
    eng=_engine()
    if not eng.available:
        report['offline']=True
        report['thinking']='LLM 离线，降级为规则验收'
        report['verdict']='fail' if rule_fail else 'degraded'
        return report
    accept_txt='\n'.join('- '+a for a in exp['accept']) or '- 结果合理可用'
    prompt=('验收标准：\n'+accept_txt+'\n\n规则预检结果（可参考，可推翻非关键项）：\n'
            +('\n'.join('- %s: %s %s'%(c['name'],'OK' if c['ok'] else 'FAIL',c['detail']) for c in report['criteria']) or '（无）')
            +'\n\n待验收的工作结果：\n'+str(subject)[:3500])
    r=eng.review(prompt,system=_SYS.format(**exp))
    if not r:
        report['offline']=True
        report['thinking']='LLM 复核未返回有效JSON，降级为规则验收'
        report['verdict']='fail' if rule_fail else 'degraded'
        return report
    # LLM 结论并入（规则关键项失败不可被推翻——硬底线）
    report['thinking']=str(r.get('thinking') or '')[:600]
    report['notes']=str(r.get('notes') or '')[:300]
    for c in (r.get('criteria') or [])[:8]:
        report['criteria'].append({'name':str(c.get('name') or '?')[:60],'ok':bool(c.get('ok')),
                                   'detail':str(c.get('detail') or '')[:160],'by':'llm'})
    llm_verdict=str(r.get('verdict') or '').lower()
    if rule_fail: report['verdict']='fail'
    elif llm_verdict=='fail': report['verdict']='fail'
    else: report['verdict']='pass'
    return report
def diagnose(fail_node,fail_report,context):
    """REFLECT 节点的诊断调用 → {diagnosis,advice,new_queries[]}；LLM 离线给规则处方"""
    exp=EXPERTS['REFLECT']
    eng=_engine()
    if eng.available:
        prompt=(f'失败节点：{fail_node}\n失败验收报告：\n{fail_report}\n\n任务上下文：\n{context}'
                '\n\n只输出JSON：{"diagnosis":"根因,120字内","advice":"纠正处方,120字内","new_queries":["改写后的英文搜索词,最多4个"]}')
        r=eng.review(prompt,system='你是'+exp['role']+'。'+exp['mission'])
        if r:
            qs=[str(x).strip() for x in (r.get('new_queries') or []) if str(x).strip()][:4]
            return {'diagnosis':str(r.get('diagnosis') or '')[:300],'advice':str(r.get('advice') or '')[:300],
                    'new_queries':qs,'by':'llm'}
    # 规则处方：换一批未用过的进化变体
    return {'diagnosis':'LLM 离线，按规则处方：换用更宽/更窄的查询词组合重试',
            'advice':'试试加 importer/buyer/wholesale 后缀，或换成 HS 3406 相关词',
            'new_queries':[],'by':'rule'}\n\n================================================================================\n# FILE [13/40]: core/runtime/graph.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v15 ExpertGraph 编排层：LangGraph 状态图（SqliteSaver 检查点 + 反思循环边）。
图拓扑：ICP→STRATEGY→A_COLLECT⇢(验收失败→REFLECT→A_COLLECT)→MINING→HARVEST→CLEAN→A_GATE⇢(→REFLECT)→USITC→RANK→CONTACT→AUDIT⇢(审核不过→CORRECT→AUDIT)→PROFILE→ANALYSIS→OUTREACH
A_COLLECT / A_GATE 验收不过时走条件边到 REFLECT，诊断开方后回到 A_COLLECT 重跑，≤REFLECT_MAX_ROUNDS 轮。
CONTACT 后新增 AUDIT 节点，审核不通过时进入 CORRECT 修正节点，修正后重新审核，直到通过或达到最大重试次数。
langgraph 缺失时自动降级为等价的手写循环执行器，共享同一套节点函数与逐节点落盘快照。"""
import time,sqlite3,traceback
from pathlib import Path
from typing import TypedDict
from core.config import settings
from core.runtime import nodes as N
class S(TypedDict,total=False):
    task_id:str; request:str; market:str; industry:str; quantity:int
    icp:dict; strategy:dict; query_override:list
    companies:list; new_companies:list; suppliers:list; supplier_new:list
    harvest:dict; usitc:dict; gate:dict; collect_gate:dict; evolution:dict
    profiles:list; analyses:list; letters:list; nodes:list
    node_reports:dict; reflection:dict
    source:str; source_errors:list; known_count:int; dropped_count:int
    abort:str; skip_llm:bool; error:str; warning:str; success:bool; duration_sec:float
    engine:str; traceback:str
    _reflect:str  # 反思触发标记：A_COLLECT/A_GATE 验收失败时置位，路由到 REFLECT
    # v2 新增：联系方式审核与修正
    contact_leads:list          # 补全后的 lead 列表
    audit_results:dict          # {norm: audit_report}
    corrections:dict            # {norm: suggest_dict}
    audit_retry_count:int       # 当前修正循环次数
    audit_max_retries:int       # 最大修正次数，默认 3
    audit_pass:bool             # 本轮审核是否通过
ORDER=['ICP','STRATEGY','A_COLLECT','SUPPLIER_MINING','REVERSE_HARVEST','CLEAN_VERIFY',
       'A_GATE','USITC','RANK','CONTACT','B_PROFILE','C_ANALYSIS','D_OUTREACH','LEARN']
FN={'ICP':N.n_icp,'STRATEGY':N.n_strategy,'A_COLLECT':N.n_collect,'SUPPLIER_MINING':N.n_supplier_mining,
    'REVERSE_HARVEST':N.n_reverse_harvest,'CLEAN_VERIFY':N.n_clean_verify,'A_GATE':N.n_gate,
    'REFLECT':N.n_reflect,'USITC':N.n_usitc,'RANK':N.n_rank,'CONTACT':N.n_contact,
    'AUDIT':N.n_audit,'CORRECT':N.n_correct,
    'B_PROFILE':N.n_profile,'C_ANALYSIS':N.n_analysis,'D_OUTREACH':N.n_outreach,'LEARN':N.n_learn}
REFLECT_AFTER={'A_COLLECT','A_GATE'}  # 这两个节点验收失败可触发反思回路
CONTRACTS={'STRATEGY':('icp',),'A_COLLECT':('market','industry','quantity'),'REVERSE_HARVEST':('task_id',),
           'CLEAN_VERIFY':('companies',),'A_GATE':('new_companies',),'RANK':('new_companies',),
           'B_PROFILE':('new_companies','icp'),'C_ANALYSIS':('new_companies',),'D_OUTREACH':('new_companies',),
           'REFLECT':('_reflect',)}
SKIP_ON_KNOWN={'A_GATE','USITC','RANK','CONTACT','B_PROFILE','C_ANALYSIS','D_OUTREACH'}  # 全部已知公司时跳过
def _entry(name,ok,note='',dur=0.0,skipped=False):
    e={'node':name,'success':ok}
    if skipped: e['skipped']=True
    if note: e['note']=note
    if dur: e['duration']=round(dur,2)
    return e
def _exec(state,name,fn,persist):
    """节点包装器：abort 短路 → 已知跳段 → 契约校验 → 执行 → 快照落盘。任何异常不外溢。"""
    if state.get('abort'):
        state['nodes']=state.get('nodes',[])+[_entry(name,True,'已中止，跳过',skipped=True)]; return state
    if state.get('skip_llm') and name in SKIP_ON_KNOWN:
        state['nodes']=state.get('nodes',[])+[_entry(name,True,'候选均已入库，跳过',skipped=True)]
        persist(state); return state
    missing=[k for k in CONTRACTS.get(name,()) if state.get(k) is None]
    if missing:
        state['nodes']=state.get('nodes',[])+[_entry(name,False,'契约校验失败: 缺输入 '+','.join(missing))]
        state['abort']='error'; state['error']=f'{name} 契约校验失败：缺输入 {missing}（上游节点未产出）'
        persist(state); return state
    t0=time.time()
    try:
        up=fn(state) or {}
        state.update(up)
        ok=up.get('_success',True); note=up.get('_note','')
        state.pop('_success',None); state.pop('_note',None)
        state['nodes']=state.get('nodes',[])+[_entry(name,ok,note,time.time()-t0)]
    except Exception as e:
        state['nodes']=state.get('nodes',[])+[_entry(name,False,str(e)[:120],time.time()-t0)]
        state['abort']='error'; state['error']=f'{name} 节点异常: {str(e)[:300]}'
        state['traceback']=traceback.format_exc()[-800:]
    persist(state); return state
# ---------- LangGraph 路径（带反思循环边）----------
def _lg_available():
    try:
        import langgraph.graph  # noqa
        return True
    except Exception:
        return False
def _checkpointer():
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        fp=str(Path(settings.DATABASE_PATH).parent/'lg_checkpoints.db')
        conn=sqlite3.connect(fp,check_same_thread=False)
        saver=SqliteSaver(conn)
        try: saver.setup()
        except Exception: pass
        return saver
    except Exception:
        return None
def _route_after(st,nxt):
    """条件路由：abort→收尾；_reflect 置位→REFLECT；否则顺序向下"""
    if st.get('abort'): return 'END'
    if st.get('_reflect'): return 'REFLECT'
    return nxt
def _route_after_audit(st):
    """审核后路由：abort→收尾；审核通过或达到最大重试→B_PROFILE；否则→CORRECT"""
    if st.get('abort'): return 'END'
    if st.get('audit_pass') or st.get('audit_retry_count',0) >= st.get('audit_max_retries',3):
        return 'B_PROFILE'
    return 'CORRECT'
def run_graph(state,persist):
    """优先 LangGraph；任何环节装不上/编译失败都回退手写循环，功能等价。"""
    if _lg_available():
        try:
            from langgraph.graph import StateGraph,END
            g=StateGraph(S)
            channels=set(S.__annotations__)
            for name in ORDER+['REFLECT','AUDIT','CORRECT']:
                def make(nm):
                    def call(st):
                        out=_exec(dict(st),nm,FN[nm],persist)
                        return {k:v for k,v in out.items() if k in channels}  # 只回传声明过的通道
                    return call
                g.add_node(name,make(name))
            g.set_entry_point('ICP')
            g.add_edge('ICP','STRATEGY'); g.add_edge('STRATEGY','A_COLLECT')
            g.add_conditional_edges('A_COLLECT',lambda st:_route_after(st,'SUPPLIER_MINING'),
                {'SUPPLIER_MINING':'SUPPLIER_MINING','REFLECT':'REFLECT','END':END})
            g.add_edge('SUPPLIER_MINING','REVERSE_HARVEST'); g.add_edge('REVERSE_HARVEST','CLEAN_VERIFY')
            g.add_edge('CLEAN_VERIFY','A_GATE')
            g.add_conditional_edges('A_GATE',lambda st:_route_after(st,'USITC'),
                {'USITC':'USITC','REFLECT':'REFLECT','END':END})
            g.add_edge('REFLECT','A_COLLECT')  # 反思回路：带着处方重跑采集
            g.add_edge('USITC','RANK'); g.add_edge('RANK','CONTACT')
            # 新增审核与修正闭环
            g.add_edge('CONTACT','AUDIT')
            g.add_conditional_edges('AUDIT',_route_after_audit,
                {'B_PROFILE':'B_PROFILE','CORRECT':'CORRECT','END':END})
            g.add_edge('CORRECT','AUDIT')  # 修正后重新审核
            g.add_edge('B_PROFILE','C_ANALYSIS'); g.add_edge('C_ANALYSIS','D_OUTREACH')
            g.add_edge('D_OUTREACH','LEARN')
            g.add_edge('LEARN','AGGREGATOR')
            saver=_checkpointer()
            app=g.compile(checkpointer=saver)
            cfg={'configurable':{'thread_id':state['task_id']},'recursion_limit':150}
            out=app.invoke(state,cfg)
            state.update(out or {}); state['engine']='langgraph'
            return state
        except Exception as e:
            state['nodes']=state.get('nodes',[])+[_entry('ENGINE',False,'LangGraph失败，回退循环执行器: '+str(e)[:120])]
            persist(state)
    # ---- 手写循环执行器（与状态图等价，支持反思回路）----
    done={e.get('node') for e in state.get('nodes',[]) if e.get('success')}
    reflected=False; i=0
    while i<len(ORDER):
        name=ORDER[i]
        if not reflected and name in done: i+=1; continue  # 崩溃恢复：已成功的节点不重跑
        state=_exec(state,name,FN[name],persist)
        if name in REFLECT_AFTER and state.get('_reflect') and not state.get('abort'):
            state=_exec(state,'REFLECT',FN['REFLECT'],persist); reflected=True
            i=ORDER.index('A_COLLECT'); continue  # 带着处方回到采集重跑
        # 手写循环特殊处理 CONTACT 后的审核与修正
        if name=='CONTACT' and not state.get('abort'):
            # 执行审核
            state=_exec(state,'AUDIT',FN['AUDIT'],persist)
            # 若不通过且未达重试上限，执行修正并重新审核
            while not state.get('audit_pass') and state.get('audit_retry_count',0) < state.get('audit_max_retries',3) and not state.get('abort'):
                state=_exec(state,'CORRECT',FN['CORRECT'],persist)
                state=_exec(state,'AUDIT',FN['AUDIT'],persist)
        i+=1
    state.setdefault('engine','sequential')
    return state\n\n================================================================================\n# FILE [14/40]: core/runtime/nodes.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v15 ExpertGraph 节点：执行(确定性) → 专家复核(LLM+验收清单) → 判定。
验收结论写入 node_reports 共享通道；A_COLLECT/A_GATE 验收失败置 _reflect，
由编排层路由到 REFLECT 诊断节点，带着处方回到 A_COLLECT 重跑（≤REFLECT_MAX_ROUNDS 轮）。
CONTACT 后新增 AUDIT 审核节点和 CORRECT 修正节点，形成补全→审核→修正→重新审核闭环。
自动修正：CORRECT 节点优先应用 AI 建议，无建议则重新补全，并用本地模型机器审核验证。
达到最大重试仍不通过的客户，从下游工作集剔除，不阻断整体流程。
新增 LEARN 节点：任务后自主进化，分析经验、咨询 GPT、更新动态规则。"""
import json, re, sqlite3, time
from pathlib import Path
from core.config import settings
from core.model.reasoning import ReasoningEngine
from core.runtime import experts
from core.tools.data_sources.manager import DataSourceManager, Evolution, gate_check, norm, noise
from core.tools import suppliers as sup
from core.tools import apify_client as apify
from core.tools import usitc as usitc_mod

BAD = re.compile(r'on behalf of|freight|forwarder|logistics|express|cargo|翻译|词典', re.I)
_engine = None

def _eng():
    global _engine
    if _engine is None:
        _engine = ReasoningEngine()
    return _engine

def _report(state, node, rep):
    nr = dict(state.get('node_reports') or {})
    nr[node] = rep
    return nr

def _ev(c):
    e = c.get('evidence') or {}
    bits = []
    if e.get('shipments'):
        bits.append(f"shipments={e['shipments']}")
    if e.get('score'):
        bits.append(f"score={e['score']}")
    if e.get('last_seen'):
        bits.append(f"last_seen={e['last_seen']}")
    return (' [' + ', '.join(str(b) for b in bits) + ']') if bits else ''

def _brief(cs, n=12):
    return '\n'.join('- ' + c.get('name','') + ' | ' + str(c.get('country','')) + ' | ' + str(c.get('source','')) + _ev(c) for c in (cs or [])[:n])

# ---------- 1. ICP 客户画像师 ----------
def n_icp(state):
    ind = state['industry']
    icp = None
    if settings.EXPERT_MODE and _eng().available:
        icp = _eng().review(
            f'市场:{state["market"]} 行业:{ind}\n生成客户画像契约JSON：'
            '{"must":["必收信号3-5条"],"reject":["拒收信号3-5条"],"keywords":["英文关键词5-8个"],"hs":["相关HS编码"]}',
            system='你是资深外贸客户画像师，只输出JSON')
    if not icp or not icp.get('must'):
        icp = {'must': ['USA company','candle/home fragrance import or trade evidence'],
               'reject': ['dictionary','marketplace retail page','freight forwarder','packaging only'],
               'keywords': ['candle','birthday candles','wax','fragrance','3406'], 'hs': ['3406']}
    rep = experts.review('ICP', '契约：\n' + json.dumps(icp, ensure_ascii=False),
                         [('含必收信号', bool(icp.get('must')), 'must 非空' if icp.get('must') else 'must 缺失'),
                          ('含拒收信号', bool(icp.get('reject')), 'reject 非空' if icp.get('reject') else 'reject 缺失'),
                          ('关键词与行业相关', bool(icp.get('keywords')), ','.join((icp.get('keywords') or [])[:5]))],
                         critical={'含必收信号','含拒收信号'})
    return {'icp': icp, 'node_reports': _report(state, 'ICP', rep), '_note': '客户画像契约已锁定'}

# ---------- 2. STRATEGY 搜索策略师 ----------
def n_strategy(state):
    plan = Evolution().plan(state['market'], state['industry'])
    base = [v for v in (state.get('query_override') or plan['variants']) if v][:4] or [state['industry']]
    rationale = '进化变体' if not state.get('query_override') else '复盘处方改写'
    ref = (state.get('reflection') or {}).get('history') or []
    advice = ref[-1].get('advice') if ref else ''
    queries = base
    if settings.EXPERT_MODE and _eng().available:
        r = _eng().review('ICP 关键词：' + json.dumps((state.get('icp') or {}).get('keywords') or [], ensure_ascii=False)
                          + f'\n候选查询词：{json.dumps(base, ensure_ascii=False)}\n复盘建议：{advice or "无"}'
                          '\n确定最终搜索查询词（覆盖买家直搜与供应商反查），只输出JSON：{"queries":["最多4个英文查询词"],"rationale":"一句话策略说明"}',
                          system='你是搜索策略师，只输出JSON')
        if r and r.get('queries'):
            queries = [str(x).strip() for x in r['queries'] if str(x).strip()][:4] or base
            rationale = str(r.get('rationale') or rationale)[:200]
    strategy = {'queries': queries, 'rationale': rationale, 'evolution': plan}
    rep = experts.review('STRATEGY', '查询词：' + json.dumps(queries, ensure_ascii=False) + '\n策略：' + rationale,
                         [('至少1个查询词', bool(queries), '%d个' % len(queries)),
                          ('回应复盘建议', bool(not advice or state.get('query_override') or queries != base), advice[:60] if advice else '无建议')],
                         critical={'至少1个查询词'})
    return {'strategy': strategy, 'node_reports': _report(state, 'STRATEGY', rep), '_note': f"查询词{len(queries)}个"}

# ---------- 3. A_COLLECT 采集质检员 ----------
def n_collect(state):
    mgr = DataSourceManager()
    qs = (state.get('strategy') or {}).get('queries')
    companies, used, errors, gate = mgr.search(state['market'], state['industry'], state['quantity'], variants_override=qs)
    junk = [c for c in companies if noise(c.get('name')) or BAD.search(c.get('name') or '')]
    rep = experts.review('A_COLLECT',
                         f'采集{len(companies)}家，来源{used}：\n' + _brief(companies),
                         [('候选数≥1', bool(companies), f'{len(companies)}家'),
                          ('垃圾占比低', len(junk) <= max(1, len(companies)//3), f'垃圾{len(junk)}家'),
                          ('含硬证据候选', any((c.get('evidence') or {}).get('shipments') for c in companies),
                           '有出货量证据' if any((c.get('evidence') or {}).get('shipments') for c in companies) else '无出货量证据')],
                         critical={'候选数≥1'})
    up = {'companies': companies, 'source': '+'.join(used) if used else 'none', 'source_errors': errors,
          'collect_gate': gate, 'evolution': mgr.last_evolution, 'node_reports': _report(state, 'A_COLLECT', rep),
          '_success': bool(companies), '_note': f"采集{len(companies)}家"}
    if not companies or rep['verdict'] == 'fail':
        up['_reflect'] = 'A_COLLECT'
        if not companies:
            up['error'] = '未采集到真实候选公司：' + '；'.join(errors or ['无可用数据源'])
    return up

# ---------- 4. SUPPLIER_MINING 供应链分析师 ----------
def n_supplier_mining(state):
    p = sup.pool(days=90, min_shipments=settings.HARVEST_MIN_SHIPMENTS)
    if p:
        sup.upsert_pool(p)
    new = [s for s in p if not s['harvested']]
    rep = experts.review('SUPPLIER_MINING',
                         '工厂池（前10）：\n' + '\n'.join('- %s | 提单%s | %s' % (s['name'], s['shipments'], s.get('via','')) for s in p[:10])
                         + f'\n未收割{len(new)}家',
                         [('池非空或已达终态', bool(p) or True, f'池{len(p)}家·未收割{len(new)}家')])
    return {'suppliers': p[:20], 'supplier_new': new[:10], 'node_reports': _report(state, 'SUPPLIER_MINING', rep),
            '_success': True, '_note': f"同行工厂池{len(p)}家·未收割{len(new)}家"}

# ---------- 5. REVERSE_HARVEST 收割评估员 ----------
def _write_plan(new_suppliers):
    fp = Path(settings.DATABASE_PATH).parent / f'harvest_plan_{time.strftime("%Y%m%d")}.txt'
    lines = ['# 反向收割计划（Apify 控制台手工执行）','# Actor: logiover/importyeti-scraper 模式 companySearch','']
    for s in new_suppliers:
        lines.append(f"slug: {s['slug']}   # {s['name']} 提单{s['shipments']}条")
    lines += ['','# 步骤：Apify → Actor 页 → Input 填 {"mode":"companySearch","companySlug":"<上面的slug>","maxResults":50}',
              '# 导出 CSV → 丢进 data\\customs\\ → 运行 customs_clean.py 清洗','# 0 结果不收费；slug 猜错无成本']
    fp.write_text('\n'.join(lines), encoding='utf-8')
    return fp.name

def _harvested_norms():
    try:
        conn = sqlite3.connect(settings.DATABASE_PATH)
        r = {x[0] for x in conn.execute('SELECT supplier_norm FROM suppliers WHERE harvested_at IS NOT NULL')}
        conn.close()
        return r
    except Exception:
        return set()

def _harvest_playwright(state, res):
    from core.tools import iy_web
    buyers = [c for c in (state.get('companies') or []) if (c.get('evidence') or {}).get('url')][:settings.IY_WEB_TOP_BUYERS]
    done = _harvested_norms()
    pool = {}
    for s in (state.get('supplier_new') or []):
        if s['norm'] not in done:
            pool[s['norm']] = {'name': s['name'], 'shipments': s.get('shipments') or 0,
                               'via': s.get('via') or 'customs', 'slug': s.get('slug') or ''}
    merged = list(state.get('companies') or [])
    with iy_web.IYWeb() as w:
        if not w.ok:
            res['errors'].append('Playwright/Chromium 未就绪：pip install playwright && playwright install chromium')
            return None
        fails = 0
        for b in buyers:
            if fails >= 2:
                res['errors'].append('连续失败已熔断，本轮停止透视')
                break
            try:
                rows = w.relationships(b['evidence']['url'], 'Suppliers')
                fails = 0
                for r in rows:
                    n = norm(r['name'])
                    if n and n not in done and n not in pool:
                        pool[n] = {'name': r['name'], 'shipments': r.get('shipments') or 0, 'via': b.get('name'),
                                   'products': r.get('products') or '', 'slug': ''}
            except Exception as e:
                fails += 1
                res['errors'].append(f"透视 {b.get('name')}: {str(e)[:80]}")
        res['suppliers_found'] = len(pool)
        have = {norm(c.get('name')) for c in merged}
        for n, s in sorted(pool.items(), key=lambda kv: -kv[1]['shipments'])[:max(1, settings.IY_WEB_MAX_SUPPLIERS)]:
            if fails >= 2:
                res['errors'].append('连续失败已熔断，本轮停止收割')
                break
            try:
                url = 'https://www.importyeti.com/supplier/' + s['slug'] if (s.get('slug') and s.get('via') == 'web') else w.supplier_page_for(s['name'])
                if not url:
                    res['errors'].append(f"{s['name']}: 未找到供应商主页")
                    continue
                rows = w.relationships(url, 'Customers')[:settings.IY_WEB_MAX_CUSTOMERS]
                fails = 0
                slug = url.rstrip('/').split('/')[-1]
                added = 0
                for r in rows:
                    rn = norm(r['name'])
                    if not rn or rn in have:
                        continue
                    have.add(rn)
                    added += 1
                    merged.append({'name': r['name'], 'country': 'USA', 'industry': state['industry'], 'type': 'importer',
                                   'website': '', 'source': 'importyeti_web', 'strength': 4,
                                   'evidence': {'shipments': r.get('shipments'), 'products': r.get('products') or '',
                                                'hs': ','.join(r.get('hs') or []), 'via_supplier': s['name'], 'url': url}})
                sup.upsert_pool([{'norm': n, 'name': s['name'], 'slug': slug, 'shipments': s['shipments'], 'last_seen': time.time()}])
                sup.mark_harvested(n, len(rows))
                sup.log_harvest(state['task_id'], slug, s['name'], 'playwright', 'ok', len(rows), f'新增客户{added}')
                res['results'].append({'slug': slug, 'name': s['name'], 'items': len(rows), 'file': f'新增客户{added}'})
            except Exception as e:
                fails += 1
                res['errors'].append(f"收割 {s['name']}: {str(e)[:80]}")
                sup.log_harvest(state['task_id'], '', s['name'], 'playwright', 'fail', 0, str(e)[:90])
        res['merged_after_harvest'] = len(merged) - len(state.get('companies') or [])
    return merged

def n_reverse_harvest(state):
    if not settings.HARVEST_ENABLED:
        return {'harvest': {'mode':'disabled','results':[],'errors':[]}, '_note': '收割已禁用'}
    new = state.get('supplier_new') or []
    plan_file = _write_plan(new) if new else ''
    res = {'mode':'plan','plan_file':plan_file,'results':[],'errors':[]}
    if settings.APIFY_TOKEN and new:
        res['mode'] = 'apify_api'; fails = 0
        for s in new[:max(1, settings.APIFY_MAX_SUPPLIERS_PER_RUN)]:
            try:
                n, fn = apify.harvest_company(s['slug'])
                sup.mark_harvested(s['norm'], n); fails = 0
                sup.log_harvest(state['task_id'], s['slug'], s['name'], 'apify_api', 'ok', n, fn)
                res['results'].append({'slug': s['slug'], 'name': s['name'], 'items': n, 'file': fn})
            except Exception as e:
                fails += 1; msg = str(e)[:90]
                sup.log_harvest(state['task_id'], s['slug'], s['name'], 'apify_api', 'fail', 0, msg)
                res['errors'].append(f"{s['slug']}: {msg}")
                if fails >= 2:
                    res['errors'].append('连续失败已熔断，本轮停止收割')
                    break
        if res['results']:
            try:
                import customs_clean
                customs_clean.ingest(settings.CUSTOMS_DIR, settings.DATABASE_PATH, 90)
                conn = sqlite3.connect(settings.DATABASE_PATH); conn.row_factory = sqlite3.Row
                rows = conn.execute('SELECT * FROM buyers_90d ORDER BY score DESC LIMIT 50').fetchall(); conn.close()
                have = {norm(c.get('name')) for c in state.get('companies') or []}
                merged = list(state.get('companies') or [])
                for r in rows:
                    if r['importer_norm'] in have: continue
                    have.add(r['importer_norm'])
                    merged.append({'name': r['importer'], 'country': 'USA', 'industry': state['industry'], 'type': 'importer',
                                   'website': '', 'source': 'customs_bulk', 'strength': 5,
                                   'evidence': {'shipments': r['shipments'], 'score': r['score'], 'last_seen': r['last_seen'], 'reasons': r['reasons']}})
                res['merged_after_harvest'] = len(merged) - len(state.get('companies') or [])
                rep = experts.review('REVERSE_HARVEST', json.dumps(res['results'], ensure_ascii=False))
                return {'harvest': res, 'companies': merged, 'node_reports': _report(state, 'REVERSE_HARVEST', rep), '_success': True,
                        '_note': f"API收割{len(res['results'])}家同行·新增买家{res['merged_after_harvest']}家"}
            except Exception as e:
                res['errors'].append('收割后清洗失败: ' + str(e)[:90])
        rep = experts.review('REVERSE_HARVEST', f"API收割{len(res['results'])}家·失败{len(res['errors'])}家")
        return {'harvest': res, 'node_reports': _report(state, 'REVERSE_HARVEST', rep),
                '_success': bool(res['results']) or not res['errors'],
                '_note': f"API收割{len(res['results'])}家·失败{len(res['errors'])}家"}
    if settings.IY_WEB_ENABLED:
        from core.tools import iy_web
        if iy_web.available():
            res['mode'] = 'playwright'
            merged = _harvest_playwright(state, res)
            if merged is None:
                rep = experts.review('REVERSE_HARVEST', 'Playwright 未就绪')
                return {'harvest': res, 'node_reports': _report(state, 'REVERSE_HARVEST', rep), '_success': False, '_note': 'Playwright 未就绪，已降级'}
            rep = experts.review('REVERSE_HARVEST',
                                 f"透视出{res.get('suppliers_found',0)}家同行·收割{len(res['results'])}家·新增买家{res.get('merged_after_harvest',0)}家\n"
                                 + ('\n'.join('- %s: 客户%d家 %s' % (r['name'], r['items'], r['file']) for r in res['results']))
                                 + ('\n失败：' + '; '.join(res['errors'][:4]) if res['errors'] else ''))
            up = {'harvest': res, 'node_reports': _report(state, 'REVERSE_HARVEST', rep),
                  '_success': bool(res['results']) or not res['errors'],
                  '_note': f"网页收割：透视出{res.get('suppliers_found',0)}家同行·收割{len(res['results'])}家·新增买家{res.get('merged_after_harvest',0)}家"}
            if merged is not state.get('companies'):
                up['companies'] = merged
            return up
    if not new:
        res['mode'] = 'idle'
        rep = experts.review('REVERSE_HARVEST', '同行工厂均已收割过（正常终态）')
        return {'harvest': res, 'node_reports': _report(state, 'REVERSE_HARVEST', rep), '_success': True, '_note': '同行工厂均已收割过'}
    rep = experts.review('REVERSE_HARVEST', f'已生成收割计划 {len(new)} 家')
    return {'harvest': res, 'node_reports': _report(state, 'REVERSE_HARVEST', rep), '_success': True, '_note': f"未配APIFY_TOKEN且Playwright不可用→已生成收割计划（{len(new)}家同行）"}

# ---------- 6. CLEAN_VERIFY 数据管家 ----------
def n_clean_verify(state):
    companies = state.get('companies') or []
    new_companies = []; known = 0; dropped = 0; now = time.time()
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        seen = {r[0] for r in c.execute('SELECT norm FROM company_state')}
        for x in companies:
            nm = (x.get('name') or '').strip()
            if noise(nm) or BAD.search(nm):
                dropped += 1; continue
            n = norm(nm)
            if not n:
                dropped += 1; continue
            if n in seen:
                known += 1
                c.execute('UPDATE company_state SET last_seen=?, runs_seen=runs_seen+1 WHERE norm=?', (now, n))
            else:
                c.execute('INSERT INTO company_state(norm,name,first_seen,last_seen,runs_seen,profiled,source) VALUES(?,?,?,?,1,0,?)', (n, nm, now, now, x.get('source') or ''))
                seen.add(n)
                new_companies.append(x)
            c.execute('INSERT INTO companies(norm,name,country,industry,type,website,source,strength,freshness,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(norm) DO UPDATE SET source=excluded.source,strength=excluded.strength,freshness=excluded.freshness,updated_at=excluded.updated_at',
                      (n, nm, x.get('country'), x.get('industry'), x.get('type'), x.get('website'), x.get('source'), x.get('strength'), now, now))
    try:
        from core.memory.db import DB
        DB().upsert_leads([{'name': x.get('name'), 'country': x.get('country') or '', 'kind': 'importer',
                            'shipments': (x.get('evidence') or {}).get('shipments') or 0,
                            'last_shipment': (x.get('evidence') or {}).get('last_shipment',''),
                            'hs_code': (x.get('evidence') or {}).get('hs',''),
                            'segment': x.get('segment',''), 'desc_sample': (x.get('evidence') or {}).get('products',''),
                            'tags': x.get('tags') or [], 'source': x.get('source') or ''} for x in companies])
    except Exception as e:
        print('[leads] upsert failed:', str(e)[:80])
    total_ok = (len(new_companies) + known + dropped) == len(companies)
    rep = experts.review('CLEAN_VERIFY', f'输入{len(companies)}·新增{len(new_companies)}·已知{known}·剔除{dropped}',
                         [('计数自洽', total_ok, f'{len(new_companies)}+{known}+{dropped} vs {len(companies)}')], critical={'计数自洽'})
    up = {'new_companies': new_companies, 'known_count': known, 'dropped_count': dropped,
          'node_reports': _report(state, 'CLEAN_VERIFY', rep), '_success': True,
          '_note': f"新增{len(new_companies)}·已知{known}·清洗剔除{dropped}"}
    if not new_companies:
        if not (state.get('reflection') or {}).get('count'):
            up['skip_llm'] = True
            up['warning'] = '本轮候选全部为已入库公司，仅做记录，跳过闸门与模型调用（不消耗LLM配额）'
        else:
            up['warning'] = '反思回路中：本轮候选均已有记录，仍放行闸门重审（寻找达标组合）'
    return up

# ---------- 7. A_GATE 资格审判官 ----------
def n_gate(state):
    reflect_on = bool((state.get('reflection') or {}).get('count'))
    cs = (state.get('companies') or []) if reflect_on else (state.get('new_companies') or [])
    g = gate_check(cs)
    judgments = []
    if settings.EXPERT_MODE and _eng().available and cs:
        arr = _eng().json('逐家审判以下候选公司是否为真实的美国相关进口买家（accept/reject+理由）：\n'
                          + _brief(cs, 25) + '\nICP契约：' + json.dumps(state.get('icp') or {}, ensure_ascii=False),
                          system='你是资格审判官，宁缺毋滥，只输出JSON数组：[{"name":"公司名","verdict":"accept或reject","reason":"一句理由"}]', as_list=True) or []
        acc = {str(x.get('name') or '').strip().lower(): x for x in arr if isinstance(x, dict)}
        if acc:
            final = []; rejects = list(g.get('rejects') or [])
            for c in cs:
                jd = acc.get((c.get('name') or '').strip().lower())
                if jd is None:
                    final.append(c); continue
                judgments.append({'name': c.get('name'), 'verdict': jd.get('verdict'), 'reason': str(jd.get('reason') or '')[:120]})
                if str(jd.get('verdict')).lower() == 'accept':
                    final.append(c)
                else:
                    rejects.append({'name': c.get('name'), 'reason': 'llm: ' + str(jd.get('reason') or '')[:80]})
            strong = {'customs_bulk','csv_import','importyeti','importyeti_web'}
            g = {'ok': False, 'raw': g['raw'], 'qualified': len(final), 'strong': sum(1 for c in final if c.get('source') in strong),
                 'rejects': rejects[:20], 'judgments': judgments[:25], 'qualified_companies': final}
            g['ok'] = g['qualified'] >= settings.GATE_MIN_QUALIFIED and (g['strong'] >= settings.GATE_MIN_STRONG or g['qualified'] >= 8)
    g.setdefault('qualified_companies', [c for c in cs if not any(r.get('name') == c.get('name') for r in (g.get('rejects') or []))])
    rep = experts.review('A_GATE',
                         f"原始{g['raw']}·合格{g['qualified']}·强证据{g['strong']}\n" + '\n'.join(
                             '- %s: %s %s' % (x['name'], x.get('verdict','?'), x.get('reason','')) for x in (g.get('judgments') or [])[:12]),
                         [('达到闸门阈值', g['ok'], f"合格{g['qualified']}/{settings.GATE_MIN_QUALIFIED}·强{g['strong']}/{settings.GATE_MIN_STRONG}")])
    up = {'gate': g, 'node_reports': _report(state, 'A_GATE', rep), '_success': g['ok']}
    if g['ok']:
        if reflect_on and not (state.get('new_companies')):
            up['new_companies'] = g.get('qualified_companies') or []
            up['skip_llm'] = False
    else:
        up['_reflect'] = 'A_GATE'
        up['error'] = 'A节点资格闸门未通过'
    return up

# ---------- REFLECT 复盘诊断师 ----------
def n_reflect(state):
    fail_node = state.get('_reflect') or 'A_GATE'
    ref = dict(state.get('reflection') or {}); hist = list(ref.get('history') or []); count = int(ref.get('count') or 0)
    last = (state.get('node_reports') or {}).get(fail_node) or {}
    ctx = json.dumps({'industry': state.get('industry'), 'market': state.get('market'),
                      'queries': (state.get('strategy') or {}).get('queries'),
                      'gate': {k:v for k,v in (state.get('gate') or {}).items() if k in ('raw','qualified','strong')},
                      'companies': len(state.get('companies') or []), 'errors': (state.get('source_errors') or [])[:3]}, ensure_ascii=False)
    d = experts.diagnose(fail_node, json.dumps(last, ensure_ascii=False)[:1500], ctx)
    if count >= 1 and settings.WEBAI_ENABLED:
        try:
            from core.tools import web_ai
            ans = web_ai.solve(
                '你是外贸客户采集系统的诊断专家。管线在 %s 节点连续验收失败，本地AI已反思%d轮未解。'
                '请给出：1) 最可能的根因一句话；2) 可执行的纠正建议一句话；3) 3个新的英文搜索查询词。'
                '只输出JSON：{"diagnosis":"","advice":"","new_queries":[]}' % (fail_node, count),
                context='节点报告:\n' + json.dumps(last, ensure_ascii=False)[:1200] + '\n全局:\n' + ctx, timeout=180)
            if ans:
                from core.utils import jsonutil
                j = jsonutil.j(ans)
                if j and j.get('diagnosis'):
                    d = {'diagnosis': '[网页AI] ' + str(j['diagnosis'])[:150],
                         'advice': str(j.get('advice') or d.get('advice') or '')[:200],
                         'new_queries': [str(x)[:80] for x in (j.get('new_queries') or [])][:4] or d.get('new_queries'),
                         'by': 'webai'}
        except Exception as e:
            print('[reflect] webai failed:', str(e)[:60])
    rep = experts.review('REFLECT', f"诊断：{d['diagnosis']}\n处方：{d['advice']}\n新查询词：{d['new_queries']}",
                         [('诊断非空', bool(d.get('diagnosis')), d.get('by',''))])
    hist.append({'round': count+1, 'at_node': fail_node, 'diagnosis': d['diagnosis'], 'advice': d['advice'],
                 'new_queries': d['new_queries'], 'by': d.get('by'), 'ts': time.time()})
    ref = {'count': count+1, 'history': hist}
    up = {'reflection': ref, 'node_reports': _report(state, 'REFLECT', rep),
          '_note': f"第{count+1}轮复盘：{d['diagnosis'][:60]}"}
    if count+1 >= settings.REFLECT_MAX_ROUNDS:
        up['abort'] = 'failed' if fail_node == 'A_COLLECT' else 'failed_gate'
        up['error'] = (state.get('error') or '验收未通过') + f"（已反思{count+1}轮仍不达标，终止。最后诊断：{d['diagnosis']}）"
        up['_reflect'] = None
    else:
        up['_reflect'] = None
        if d['new_queries']:
            up['query_override'] = d['new_queries']
        else:
            up['query_override'] = None
        up.pop('error', None)
    return up

# ---------- 8. USITC 宏观情报员 ----------
def n_usitc(state):
    info = usitc_mod.intel()
    note = {'file':'手工情报已加载','api':'DataWeb API 已加载','none':'未配置，跳过（把DataWeb查到的数据粘进 data/usitc_notes.txt 即可启用）'}[info['source']]
    if info.get('ok') and settings.EXPERT_MODE and _eng().available:
        ammo = _eng().text('把以下美国市场数据浓缩成开发信可自然引用的一句英文弹药（含数字与来源，不编造）：\n' + info['text'][:1200],
                           system='你是宏观情报员，只输出一句英文')
        if ammo:
            info['ammo'] = ammo.strip()[:400]
    rep = experts.review('USITC', info.get('ammo') or info.get('text','')[:400] or '无数据',
                         [('有数据或明确跳过', True, info['source'])])
    return {'usitc': info, 'node_reports': _report(state, 'USITC', rep), '_success': True, '_note': note}

# ---------- 9. RANK 采购优先级顾问 ----------
def n_rank(state):
    cs = sorted(state.get('new_companies') or [], key=lambda c: (c.get('strength') or 0), reverse=True)
    rep = experts.review('RANK', '排序结果：\n' + _brief(cs),
                         [('覆盖全部合格公司', True, f'{len(cs)}家')])
    return {'new_companies': cs, 'node_reports': _report(state, 'RANK', rep), '_success': True, '_note': '已按证据强度排序，硬证据优先进入模型'}

def _pair_profiles(state, profiles):
    cs = state.get('new_companies') or []
    out = []
    used = set()
    for pf in profiles or []:
        nm = ''
        if isinstance(pf, dict):
            nm = str(pf.get('name') or pf.get('company') or '')
        idx = None
        if nm:
            for i, c in enumerate(cs):
                if i in used: continue
                if norm(c.get('name')) == norm(nm):
                    idx = i; break
        if idx is None:
            for i in range(len(cs)):
                if i not in used:
                    idx = i; break
        if idx is None: continue
        used.add(idx)
        out.append((cs[idx].get('name'), pf))
    return out

def _lines(state):
    return '\n'.join('- ' + c.get('name','') + ' ' + str(c.get('country','')) + ' ' + str(c.get('source','')) + _ev(c)
                     for c in (state.get('new_companies') or [])[:settings.PROFILE_TOP_N])

def _mark_profiled(state):
    now = time.time()
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        for x in (state.get('new_companies') or [])[:settings.PROFILE_TOP_N]:
            c.execute('UPDATE company_state SET profiled=1,last_seen=? WHERE norm=?', (now, norm(x.get('name'))))

def _upstream_notes(state, node):
    nr = state.get('node_reports') or {}
    bits = []
    for k in ('ICP','A_COLLECT','A_GATE','RANK'):
        n = (nr.get(k) or {}).get('notes')
        if n:
            bits.append(f'[{k}] {n}')
    return '\n上游专家交接：\n' + '\n'.join(bits) if bits else ''

# ---------- 9.5 CONTACT 联系方式提取员 ----------
def n_contact(state):
    if not settings.CONTACT_ENABLED:
        return {'_success': True, '_note': '联系方式提取已禁用', 'node_reports': _report(state, 'CONTACT', experts.review('CONTACT', '已禁用'))}
    from core.memory.db import DB
    from core.tools import contact_finder, scoring
    db = DB()
    cs = (state.get('new_companies') or [])[:settings.CONTACT_TOP_N]
    leads = []
    for c in cs:
        l = db.get_lead(norm(c.get('name')))
        if l and l.get('kind') == 'importer':
            leads.append(l)
    todo = [l for l in leads if not (l.get('website') or l.get('emails'))]
    ok = 0
    errs = []
    if todo:
        f = contact_finder.ContactFinder()
        try:
            f._launch()
            for l in todo:
                try:
                    r = f.enrich(l, do_audit=False)
                    if r.get('ok'):
                        ok += 1
                except Exception as e:
                    errs.append(str(e)[:60])
                time.sleep(1)
        except Exception as e:
            errs.append('浏览器未就绪: ' + str(e)[:80])
        finally:
            f.close()
    graded = []
    for l in leads:
        l = db.get_lead(l['norm']) or l
        sc, gr, why = scoring.score_lead(l)
        db.lead_update(l['norm'], score=sc, grade=gr)
        graded.append('- %s | %s级 %.1f | 邮箱%s | %s' % (l['name'], gr, sc, '有' if l.get('emails') else '无', why[:60]))
    rep = experts.review('CONTACT',
                         '目标%d家·待补%d家·补全%d家\n评分落库：\n%s' % (len(leads), len(todo), ok, '\n'.join(graded[:12])) +
                         ('\n失败：' + '; '.join(errs[:3]) if errs else ''),
                         [('评分已落库', bool(graded), '%d家' % len(graded)),
                          ('有可用联系方式', ok > 0 or not todo, '补全%d家' % ok if todo else '均已有联系方式')])
    contact_leads = []
    for l in leads:
        fresh = db.get_lead(l['norm'])
        contact_leads.append(fresh if fresh else l)
    return {'node_reports': _report(state, 'CONTACT', rep), '_success': True,
            '_note': f'联系方式补全{ok}/{len(todo)}家·评分{len(graded)}家落库',
            'contact_leads': contact_leads,
            'audit_retry_count': 0,
            'audit_max_retries': 3}

# ---------- 9.6 AUDIT 资料审核员 ----------
def n_audit(state):
    """GPT 验证并自动更新客户资料。"""
    from core.tools import auditor
    from core.memory.db import DB
    db = DB()
    leads = state.get('contact_leads') or []
    if not leads:
        return {'_success': True, '_note': '无待审核客户', 'audit_pass': True,
                'audit_results': {}, 'corrections': {}, 'audit_retry_count': 0}
    audit_results = {}
    all_pass = True
    suggestions = {}
    updated_leads = []
    for lead in leads:
        updated, rep = auditor.audit_and_update(lead, db=db, use_ai=True, webai=state.get('_webai_instance'))
        updated_leads.append(updated)
        audit_results[updated['norm']] = rep
        if rep['verdict'] != 'pass':
            all_pass = False
        if rep.get('ai', {}).get('suggest'):
            suggestions[updated['norm']] = rep['ai']['suggest']
    fail_count = sum(1 for r in audit_results.values() if r['verdict'] != 'pass')
    return {'contact_leads': updated_leads,
            'audit_results': audit_results,
            'corrections': suggestions,
            'audit_pass': all_pass,
            'audit_retry_count': state.get('audit_retry_count', 0),
            '_success': True,
            '_note': '审核通过' if all_pass else f'审核不通过 {fail_count}家'}

# ---------- 9.7 CORRECT 资料修正员 ----------
def n_correct(state):
    """审核未通过时，再次调用 GPT 验证并更新。达到最大重试则剔除失败客户。"""
    from core.memory.db import DB
    from core.tools import auditor
    db = DB()
    leads = state.get('contact_leads') or []
    audit_results = state.get('audit_results') or {}
    retry = state.get('audit_retry_count', 0) + 1

    updated_leads = []
    for lead in leads:
        updated, rep = auditor.audit_and_update(lead, db=db, use_ai=True, webai=state.get('_webai_instance'))
        updated_leads.append(updated)
        audit_results[updated['norm']] = rep

    passed = [l for l in updated_leads if audit_results.get(l['norm'], {}).get('verdict') == 'pass']
    failed = [l for l in updated_leads if audit_results.get(l['norm'], {}).get('verdict') != 'pass']

    if retry >= state.get('audit_max_retries', 3):
        return {
            'contact_leads': passed,
            'audit_results': audit_results,
            'audit_retry_count': retry,
            'audit_pass': True,
            'new_companies': [c for c in state.get('new_companies') or [] if norm(c.get('name')) in [l['norm'] for l in passed]],
            '_success': True,
            '_note': f'第{retry}次修正完成，通过{len(passed)}家，剔除{len(failed)}家'
        }

    all_pass = len(failed) == 0
    return {
        'contact_leads': passed,
        'audit_results': audit_results,
        'audit_retry_count': retry,
        'audit_pass': all_pass,
        'new_companies': state.get('new_companies') if all_pass else [c for c in state.get('new_companies') if norm(c.get('name')) in [l['norm'] for l in passed]],
        '_success': True,
        '_note': f'第{retry}次修正完成，通过{len(passed)}家' + ('' if all_pass else f'，剩余{len(failed)}家')
    }

# ---------- 10/11/12. LLM 画像/分析/开发信（带验收）----------
def n_profile(state):
    if not _eng().available:
        return {'_success': False, 'abort': 'done_degraded', 'warning': 'LLM离线：仅完成真实采集/收割/去重', '_note': 'offline'}
    want = min(settings.PROFILE_TOP_N, len(state.get('new_companies') or []))
    p = _eng().json('基于ICP为以下外贸客户生成画像JSON数组（输入含来源与证据强度，请在画像中体现）：\n' + json.dumps(state['icp'], ensure_ascii=False) + '\n' + _lines(state) + _upstream_notes(state, 'B_PROFILE'),
                    system='只输出JSON数组', as_list=True) or []
    _mark_profiled(state)
    try:
        from core.memory.db import DB
        db = DB()
        for c, (name, pf) in zip(state.get('new_companies') or [], _pair_profiles(state, p)):
            db.lead_update(norm(name), profile=str(pf)[:800])
    except Exception as e:
        print('[leads] profile writeback failed:', str(e)[:60])
    rep = experts.review('B_PROFILE', f'画像{len(p)}份/预期{want}份',
                         [('份数达标', len(p) >= want or not p, f'{len(p)}/{want}')])
    return {'profiles': p, 'node_reports': _report(state, 'B_PROFILE', rep), '_success': bool(p), '_note': f'{len(p)}份'}

def n_analysis(state):
    want = min(settings.ANALYSIS_TOP_N, len(state.get('new_companies') or []))
    a = _eng().json('评估以下公司的采购机会JSON数组（优先分析有提单/海关硬证据的公司）：\n' + _lines(state) + _upstream_notes(state, 'C_ANALYSIS'),
                    system='只输出JSON数组', as_list=True) or []
    rep = experts.review('C_ANALYSIS', f'分析{len(a)}份/预期{want}份',
                         [('份数达标', len(a) >= want or not a, f'{len(a)}/{want}')])
    return {'analyses': a, 'node_reports': _report(state, 'C_ANALYSIS', rep), '_success': bool(a), '_note': f'{len(a)}份'}

def n_outreach(state):
    u = state.get('usitc') or {}
    ammo = ''
    if u.get('ok'):
        ammo = '\n可参考的美国市场宏观数据（USITC来源，可自然引用一句以体现专业度，不要编造数字）：\n' + (u.get('ammo') or u['text'][:800])
    want = min(settings.LETTER_TOP_N, len(state.get('new_companies') or []))
    from core.tools import pitch
    from core.memory.db import DB as _DB
    _db = _DB()
    letters_prompts = []
    for c in (state.get('new_companies') or [])[:want]:
        ld = _db.get_lead(norm(c.get('name'))) or {'name': c.get('name'), 'country': c.get('country'),
                                                   'segment': c.get('segment',''), 'shipments': (c.get('evidence') or {}).get('shipments') or 0,
                                                   'tags': ','.join(c.get('tags') or []), 'desc_sample': (c.get('evidence') or {}).get('products','')}
        letters_prompts.append(pitch.letter_prompt(ld, ammo))
    l = []
    for pr in letters_prompts:
        t = _eng().text(pr, system='你是资深外贸业务员，只输出英文邮件成稿', temperature=0.6)
        if t:
            l.append({'letter': t.strip()[:2000]})
    rep = experts.review('D_OUTREACH', f'开发信{len(l)}封/预期{want}封',
                         [('份数达标', len(l) >= want or not l, f'{len(l)}/{want}')])
    return {'letters': l, 'node_reports': _report(state, 'D_OUTREACH', rep), '_success': bool(l), '_note': f'{len(l)}封'}

# ---------- 10.5 LEARN 学习与进化节点 ----------
def n_learn(state):
    """自主进化节点：分析经验库，咨询GPT，更新动态规则。"""
    import json as _json
    from collections import Counter
    from core.memory.experience import Experience
    from core.tools import web_ai

    exp = Experience()

    queries = (state.get('strategy') or {}).get('queries') or []
    companies = state.get('companies') or []
    new_companies = state.get('new_companies') or []
    gate = state.get('gate') or {}
    audit_results = state.get('audit_results') or {}
    letters = state.get('letters') or []

    if queries:
        for q in queries:
            score = min(len(companies) / 20.0, 1.0)
            exp.record('search_query', q, {'result_count': len(companies)}, score=score)

    if audit_results:
        pass_count = sum(1 for r in audit_results.values() if r.get('verdict') == 'pass')
        pass_rate = pass_count / max(1, len(audit_results))
        exp.record('audit_stats', 'pass_rate', {'rate': pass_rate}, score=pass_rate)

    if letters:
        exp.record('letter_stats', 'generated', {'count': len(letters)}, score=0.5)

        # 开发信内容自评：不依赖客户反馈，直接分析内容质量
        try:
            sample = letters[:3]
            letter_texts = []
            for idx, letter_item in enumerate(sample, 1):
                if isinstance(letter_item, dict):
                    text = letter_item.get('letter') or letter_item.get('content') or ''
                else:
                    text = str(letter_item)
                letter_texts.append(f"第{idx}封：\n{text[:800]}")

            if letter_texts:
                prompt_letter_review = (
                    '你是外贸开发信内容评审专家。以下是最近系统生成的开发信：\n\n'
                    + '\n\n'.join(letter_texts) +
                    '\n\n请分析这些开发信的内容质量，指出可能存在的问题，例如：\n'
                    '- 产品线不匹配\n'
                    '- 缺乏个性化钩子\n'
                    '- 营销词过多，可能触发垃圾邮件过滤\n'
                    '- 没有明确的低门槛动作\n'
                    '- 篇幅过长或过短\n'
                    '请按以下格式输出每条建议一行：\n'
                    'LETTER_ADVICE: 具体建议内容\n'
                    '如果无需改进，请回答 NO_ACTION。'
                )

                web2 = web_ai.WebAI()
                try:
                    web2._launch()
                    letter_advice = web2.ask(prompt_letter_review)
                    if letter_advice and letter_advice.strip() != 'NO_ACTION':
                        for line in letter_advice.strip().splitlines():
                            line = line.strip()
                            if line.startswith('LETTER_ADVICE:'):
                                desc = line.replace('LETTER_ADVICE:', '').strip()
                                if desc:
                                    exp.record('letter_content_advice', f"task_{state.get('task_id')}", desc, score=0.5)
                except Exception as e:
                    print('[learn] 开发信评审失败:', str(e)[:80])
                finally:
                    try:
                        web2.close()
                    except Exception:
                        pass
        except Exception as e:
            print('[learn] 开发信自评异常:', str(e)[:80])

    all_exp = exp.all()
    if len(all_exp) < 5:
        return {'_success': True, '_note': '经验不足，暂不进化', 'learn_summary': {'total_experience': len(all_exp)}}

    query_scores = {}
    for e in all_exp:
        if e['type'] == 'search_query':
            key = e['key']
            query_scores.setdefault(key, []).append(e['score'])

    low_queries = []
    for key, scores in query_scores.items():
        avg = sum(scores) / len(scores)
        if avg < 0.4 and len(scores) >= 3:
            low_queries.append({'query': key, 'avg_score': avg, 'count': len(scores)})

    email_fail_counter = Counter()
    for e in all_exp:
        if e['type'] == 'audit_fail_email' and isinstance(e.get('value'), dict):
            email = e['value'].get('email', '')
            if email:
                prefix = email.split('@')[0].lower()
                domain = email.split('@')[-1].lower()
                email_fail_counter[prefix] += 1
                email_fail_counter[domain] += 1

    failed_patterns = [p for p, c in email_fail_counter.items() if c >= 3]

    audit_stats = [e for e in all_exp if e['type'] == 'audit_stats']
    latest_audit = None
    if audit_stats:
        latest = sorted(audit_stats, key=lambda x: x.get('updated_at', 0))[-1]
        if isinstance(latest.get('value'), dict):
            latest_audit = latest['value'].get('rate')

    summary = {
        'total_experience': len(all_exp),
        'low_queries': low_queries,
        'failed_email_patterns': failed_patterns,
        'audit_pass_rate': latest_audit,
        'total_letters': sum(e.get('value', {}).get('count', 0) for e in all_exp if e['type'] == 'letter_stats' and isinstance(e.get('value'), dict))
    }

    web = web_ai.WebAI()
    try:
        web._launch()
        prompt = (
            '你是外贸客户采集系统的自主进化顾问。以下是最近积累的经验统计和问题摘要：\n'
            f'{_json.dumps(summary, ensure_ascii=False, indent=2)}\n\n'
            '请分析这些数据，提出具体的优化方案。你可以建议：\n'
            '1. 新增邮箱黑名单模式（例如 privacy@, customercare@）\n'
            '2. 减少或替换低效查询词\n'
            '3. 调整审核规则\n'
            '4. 改进开发信模板\n\n'
            '请按以下格式输出，每条建议一行：\n'
            'ADD_BAD_EMAIL: privacy@\n'
            'ADD_BAD_EMAIL: customercare@\n'
            'REDUCE_QUERY: 某个查询词\n'
            'RULE_CHANGE: 具体规则调整描述\n'
            'CODE_SUGGESTION: 需要修改代码的建议\n'
            '如果不需要修改，请回答 NO_ACTION。'
        )
        answer = web.ask(prompt)
    except Exception as e:
        print('[learn] GPT咨询失败:', str(e)[:80])
        answer = None
    finally:
        try:
            web.close()
        except Exception:
            pass

    applied_rules = []
    code_suggestions = []
    if answer and answer.strip() != 'NO_ACTION':
        for line in answer.strip().splitlines():
            line = line.strip()
            if line.startswith('ADD_BAD_EMAIL:'):
                pattern = line.replace('ADD_BAD_EMAIL:', '').strip().lower()
                if pattern:
                    exp.add_rule('bad_email_pattern', pattern, _json.dumps({'source': 'auto_evolution'}))
                    applied_rules.append(('bad_email_pattern', pattern))
            elif line.startswith('REDUCE_QUERY:'):
                query = line.replace('REDUCE_QUERY:', '').strip()
                if query:
                    exp.add_rule('low_priority_query', query, _json.dumps({'weight': 0.1}))
                    applied_rules.append(('low_priority_query', query))
            elif line.startswith('RULE_CHANGE:'):
                desc = line.replace('RULE_CHANGE:', '').strip()
                if desc:
                    code_suggestions.append(desc)
            elif line.startswith('CODE_SUGGESTION:'):
                desc = line.replace('CODE_SUGGESTION:', '').strip()
                if desc:
                    code_suggestions.append(desc)

    if code_suggestions:
        import datetime
        suggest_path = Path(settings.DATABASE_PATH).parent / 'evolution_code_suggestions.txt'
        suggest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(suggest_path, 'a', encoding='utf-8') as f:
            f.write(f"\n===== {datetime.datetime.now()} =====\n")
            for s in code_suggestions:
                f.write(f"- {s}\n")

    exp.record('evolution_action', f"task_{state.get('task_id')}", {
        'applied_rules': applied_rules,
        'code_suggestions': code_suggestions,
        'gpt_answer': (answer or '')[:1000]
    }, score=0.5)

    note = '学习完成'
    if applied_rules:
        note += f"，应用规则 {len(applied_rules)} 条"
    if code_suggestions:
        note += f"，生成代码建议 {len(code_suggestions)} 条"
    if not applied_rules and not code_suggestions:
        note += '，无新规则'

    return {
        '_success': True,
        '_note': note,
        'learn_summary': summary
    }\n\n================================================================================\n# FILE [15/40]: core/runtime/orchestrator.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v14 编排入口：组装初始状态 → 跑状态图 → 每节点快照 → 终态落库。结果结构与 v13 兼容，前端无需大改。"""
import time,uuid
from core.memory.db import DB
from core.runtime import graph
class Orchestrator:
    def __init__(self): self.db=DB()
    def run(self,request,market='USA',industry='birthday candles',quantity=20,task_id=None):
        tid=task_id or uuid.uuid4().hex[:8]; t0=time.time()
        state={'task_id':tid,'request':request,'market':market,'industry':industry,
               'quantity':int(quantity or 20),'nodes':[],'companies':[],'profiles':[],
               'analyses':[],'letters':[],'success':False,
               'node_reports':{},'reflection':{'count':0,'history':[]},'strategy':{},'query_override':None}
        def persist(st):
            res={k:v for k,v in st.items() if k!='traceback'}
            self.db.save_task(tid,request,'running',res)
        persist(state)
        state=graph.run_graph(state,persist)
        abort=state.get('abort')
        status={'failed':'failed','failed_gate':'failed_gate','done_degraded':'done_degraded','error':'error'}.get(abort,'done')
        state['success']=status in ('done','done_degraded')
        state['duration_sec']=round(time.time()-t0,2)
        res={k:v for k,v in state.items() if k!='traceback'}
        self.db.save_task(tid,request,status,res)
        return res
\n\n================================================================================\n# FILE [16/40]: core/system.py\n================================================================================\n\nimport json,threading,time,uuid,queue
from core.runtime.orchestrator import Orchestrator
from core.memory.db import DB

class PSVSystem:
    """单 worker 串行队列：同一时刻只跑一个任务。
    采集共享同一个桌面浏览器/CDP 会话和同一个 SQLite，并发跑会互相打架。
    v15.1.1: 任务ID全程统一（队列与编排同一个 tid，侧边栏一行一任务）；
    启动时收割上一进程留下的僵尸任务：running 标记中断，带参数的 queued 自动续跑。"""

    def __init__(self):
        self.orch=Orchestrator(); self.db=DB(); self.q=queue.Queue()
        self._reap()
        threading.Thread(target=self._worker,daemon=True).start()

    def _reap(self):
        """worker 只活在内存里：进程重启后库里的 running/queued 必然是僵尸。"""
        now=time.time(); resumed=0
        with self.db.c() as x:
            running=x.execute("SELECT task_id,result FROM tasks WHERE status='running'").fetchall()
            for tid,res in running:
                try: r=json.loads(res or '{}')
                except Exception: r={}
                r['error']='服务重启：任务被中断（可重新 RUN）'
                x.execute('UPDATE tasks SET status=?,result=?,updated_at=? WHERE task_id=?',
                          ('failed',json.dumps(r,ensure_ascii=False),now,tid))
                print('[queue] reaped interrupted task',tid)
            queued=x.execute("SELECT task_id,request,result FROM tasks WHERE status='queued' ORDER BY created_at").fetchall()
        for tid,req,res in queued:
            try: p=json.loads(res or '{}').get('params') or {}
            except Exception: p={}
            if p.get('industry'):
                self.q.put((tid,req,p.get('market') or 'USA',p['industry'],p.get('quantity') or 20)); resumed+=1
                print('[queue] resumed queued task',tid)
            else:
                with self.db.c() as x:
                    x.execute("UPDATE tasks SET status='failed',result=?,updated_at=? WHERE task_id=?",
                              (json.dumps({'error':'服务重启：排队任务已清理（请重新 RUN）'},ensure_ascii=False),now,tid))
                print('[queue] dropped legacy queued task',tid)
        if resumed: print('[queue]',resumed,'queued task(s) will run now')

    def _worker(self):
        while True:
            tid,request,market,industry,quantity=self.q.get()
            try:
                self.orch.run(request,market,industry,int(quantity or 20),task_id=tid)
            except Exception as e:
                self.db.save_task(tid,request,'error',{'error':str(e)[:300]})

    def start(self,request,market,industry,quantity):
        tid=uuid.uuid4().hex[:8]
        self.db.save_task(tid,request,'queued',{'params':{'market':market,'industry':industry,'quantity':int(quantity or 20)}})
        self.q.put((tid,request,market,industry,quantity)); return tid

    def get(self,tid): return self.db.get_task(tid)
\n\n================================================================================\n# FILE [17/40]: core/tools/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [18/40]: core/tools/apify_client.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""Apify 官方 REST 客户端：异步跑 actor → 轮询 → 拉数据集 → 扁平化为 CSV 落进 data/customs。
按结果付费，0 结果 = $0。只走 Apify 云端，零直接抓取。"""
import csv,json,time,urllib.request,urllib.parse
from pathlib import Path
from core.config import settings
BASE='https://api.apify.com/v2'
def _opener():
    px=settings.SCRAPE_PROXY_URL or ''
    return urllib.request.build_opener(urllib.request.ProxyHandler({'http':px,'https':px} if px else {}))
def _req(method,url,payload=None,timeout=60):
    data=json.dumps(payload).encode() if payload is not None else None
    r=urllib.request.Request(url,data=data,method=method,headers={'Content-Type':'application/json'})
    with _opener().open(r,timeout=timeout) as resp:
        body=resp.read().decode('utf-8','ignore')
        return json.loads(body) if body.strip() else {}
def _tok(url): return url+('&' if '?' in url else '?')+'token='+urllib.parse.quote(settings.APIFY_TOKEN)
def start_run(actor,input_json):
    d=_req('POST',_tok(f'{BASE}/acts/{actor}/runs'),payload=input_json,timeout=60)
    info=d.get('data') or {}
    if not info.get('id'): raise RuntimeError('Apify 启动失败: '+json.dumps(d,ensure_ascii=False)[:160])
    return info
def wait_run(run_id):
    t0=time.time()
    while time.time()-t0<settings.APIFY_RUN_TIMEOUT:
        d=_req('GET',_tok(f'{BASE}/actor-runs/{run_id}'),timeout=30)
        st=(d.get('data') or {}).get('status')
        if st=='SUCCEEDED': return d.get('data') or {}
        if st in ('FAILED','ABORTED','TIMED-OUT'): raise RuntimeError(f'Apify 运行{st}')
        time.sleep(8)
    raise RuntimeError('Apify 运行超时')
def dataset_items(dataset_id,limit=1000):
    d=_req('GET',_tok(f'{BASE}/datasets/{dataset_id}/items')+f'&limit={limit}&clean=true',timeout=120)
    return d if isinstance(d,list) else []
def flatten(obj,prefix=''):
    """嵌套 JSON → Apify CSV 导出同款斜杠路径（hs_codes/0/hs_code），与 customs_clean.MAP 对齐"""
    out={}
    if isinstance(obj,dict):
        for k,v in obj.items(): out.update(flatten(v,f'{prefix}/{k}' if prefix else str(k)))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): out.update(flatten(v,f'{prefix}/{i}'))
    else:
        out[prefix]=obj
    return out
def save_csv(items,fp):
    rows=[flatten(x) for x in items]
    keys=[]
    for r in rows:
        for k in r:
            if k not in keys: keys.append(k)
    with open(fp,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
        for r in rows: w.writerow(r)
def company_input(slug):
    tpl=settings.APIFY_COMPANY_INPUT
    try:
        return json.loads(tpl.replace('{slug}',slug))
    except Exception:
        return {'mode':'companySearch','companySlug':slug,'maxResults':50}
def harvest_company(slug):
    """对一个公司 slug 跑 companySearch，CSV 落盘 data/customs。返回 (条数, CSV文件名)"""
    if not settings.APIFY_TOKEN: raise RuntimeError('未配置 APIFY_TOKEN')
    info=start_run(settings.APIFY_ACTOR,company_input(slug))
    fin=wait_run(info['id'])
    ds=fin.get('defaultDatasetId') or info.get('defaultDatasetId')
    if not ds: raise RuntimeError('Apify 未返回数据集ID')
    items=dataset_items(ds)
    fp=Path(settings.CUSTOMS_DIR)/f'apify_company_{slug}_{int(time.time())}.csv'
    if items: save_csv(items,fp)
    return len(items),fp.name if items else ''
\n\n================================================================================\n# FILE [19/40]: core/tools/auditor.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""资料审核节点：GPT 验证并自动更新客户资料。
采用开放式提问，让 GPT 自由提供详细信息，系统自动提取关键字段并更新数据库。
"""
import re, time, json
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '../..')))
from core.config import settings

PROGRESS = None

def _prog(msg):
    try:
        if PROGRESS: PROGRESS(msg)
    except Exception: pass

VERDICT_CN = {'pass': '审核通过', 'suspect': '有疑点', 'fail': '未通过'}

def reset_run():
    pass

def _extract_from_text(txt):
    """从 GPT 自然语言回复中提取官网、邮箱、电话、地址。"""
    if not txt:
        return {}
    emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', txt)
    websites = re.findall(r'https?://[A-Za-z0-9./_-]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}', txt)
    phones = re.findall(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}', txt)
    addresses = re.findall(r'\d{1,6}\s+[A-Za-z0-9][\w .#-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy)[\w .,#-]*', txt)
    out = {}
    if websites:
        out['website'] = websites[0].strip('.,;')
    if emails:
        out['emails'] = list(dict.fromkeys(emails[:5]))
    if phones:
        out['phones'] = list(dict.fromkeys(phones[:2]))
    if addresses:
        out['address'] = addresses[0].strip()
    return out

def _call_gpt(lead, webai=None):
    """开放式询问 GPT，返回自然语言回复。"""
    from core.tools import web_ai
    own = False
    w = webai
    if w is None:
        w = web_ai.WebAI(); w._launch(); own = True
    try:
        name = lead.get('name') or ''
        prompt = (
            f'请提供 "{name}" 这家公司的详细公开联系信息。\n'
            '最好包括官网、邮箱（尤其是采购或供应商相关邮箱）、电话、地址。\n'
            '如果你知道其他有用的联系渠道，也请一并说明。\n'
            '请用自然语言回答，不需要固定格式。'
        )
        txt = w.ask(prompt)
        if not txt:
            alt = 'chatgpt' if settings.WEBAI_ENGINE == 'deepseek' else 'deepseek'
            txt = w.ask(prompt, engine=alt)
        return txt
    finally:
        if own:
            try: w.close()
            except Exception: pass

def audit_and_update(lead, db=None, use_ai=True, webai=None):
    """审核并自动更新客户资料。返回 (更新后的 lead, 审核报告)。"""
    from core.memory.db import DB
    if db is None:
        db = DB()

    rep = {'ts': time.time(), 'day': time.strftime('%Y-%m-%d %H:%M'), 'verdict': 'pass',
           'fields': {}, 'ai': {'ran': False, 'suggest': None}}

    name = lead.get('name') or ''
    _prog(f'GPT验证并更新：{name}')

    if use_ai and settings.WEBAI_ENABLED:
        txt = _call_gpt(lead, webai=webai)
        if txt:
            info = _extract_from_text(txt)
            if info:
                kw = {}
                if info.get('website'):
                    kw['website'] = info['website']
                if info.get('emails'):
                    kw['emails'] = ','.join(info['emails'])
                if info.get('phones'):
                    kw['phones'] = ','.join(info['phones'])
                if info.get('address'):
                    kw['address'] = info['address']
                if kw:
                    db.lead_update(lead['norm'], **kw)
                    lead = db.get_lead(lead['norm']) or lead
                    rep['ai']['ran'] = True
                    rep['ai']['suggest'] = kw
                    rep['ai']['notes'] = 'GPT已提供更新'
                    _prog(f'{name} 已应用GPT更新')
                else:
                    rep['ai']['notes'] = 'GPT未提取到更新'
            else:
                rep['ai']['notes'] = 'GPT回复无法解析'
        else:
            rep['ai']['notes'] = 'GPT未回复'

    # 简单机器兜底审核：缺少核心字段则标记为 suspect
    if not lead.get('website'):
        rep['fields']['website'] = {'st': 'missing', 'why': ['缺官网']}
    else:
        rep['fields']['website'] = {'st': 'ok', 'why': []}
    if not lead.get('emails'):
        rep['fields']['emails'] = {'st': 'missing', 'why': ['缺邮箱']}
    else:
        rep['fields']['emails'] = {'st': 'ok', 'why': []}
    if not lead.get('phones'):
        rep['fields']['phones'] = {'st': 'missing', 'why': ['缺电话']}
    else:
        rep['fields']['phones'] = {'st': 'ok', 'why': []}

    if not lead.get('website') or not lead.get('emails'):
        rep['verdict'] = 'suspect'
    else:
        rep['verdict'] = 'pass'

    db.lead_update(lead['norm'], audit=json.dumps(rep, ensure_ascii=False))
    return lead, rep

def audit_lead(lead, use_ai=True, webai=None):
    """兼容旧接口，内部调用 audit_and_update。"""
    from core.memory.db import DB
    db = DB()
    updated, rep = audit_and_update(lead, db=db, use_ai=use_ai, webai=webai)
    return rep\n\n================================================================================\n# FILE [20/40]: core/tools/contact_finder.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v16.2: 联系方式提取器 v2 —— GPT式多源综合。
思路升级（对照 GPT 的做法）：
  1) 三路证据：搜索引擎结果摘要(不用开网页就有大量联系信息) + 官网联系页 + 目录站(BBB/商会/企业库)；
  2) 多个搜索引擎兜底：DuckDuckGo html → DDG lite → Bing（CDP 桌面浏览器直连，可过风控）；
  3) 正则先粗提（邮箱/电话/美式地址），本地 70B 再综合全部证据出最终 JSON；
  4) 写回 leads 表（website/emails/phones/address/contact_person/linkedin）。"""
import re,time,urllib.parse
import os as _os,sys as _sys
_sys.path.insert(0,_os.path.abspath(_os.path.join(_os.path.dirname(__file__),'../..')))
from core.config import settings

# 找官网阶段要跳过的站（非官网）
SKIP_DOM=re.compile(r'duckduckgo|google|bing|yahoo|linkedin\.com|facebook|instagram|twitter|x\.com|youtube|pinterest|'
    r'importyeti|importgenius|panjiva|alibaba|made-in-china|globalsources|zoominfo|rocketreach|'
    r'yelp|wikipedia|amazon\.|walmart\.com|target\.com|indeed|glassdoor|bbb\.org|chamberofcommerce|'
    r'trademo|volza|tradeatlas|importinfo|exportgenius|seair|zauba|importkey|descartes|datamyne|panjiva|tradeintell|'
    r'buzzfile|corporationwiki|dnb\.com|manta\.com|mapquest|yellowpages|opencorporates',re.I)
# 提取阶段允许抓取的目录站（联系方式金矿）
DIR_OK=re.compile(r'bbb\.org|chamberofcommerce|buzzfile|corporationwiki|manta\.com|dnb\.com|yellowpages|mapquest',re.I)
EMAIL_RE=re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
BAD_EMAIL=re.compile(r'example\.|sentry|wixpress|@2x\.|\.png$|\.jpg$|\.gif$|godaddy|w3\.org|schema|u003|@sentry|@duckduckgo',re.I)
PHONE_RE=re.compile(r'(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}')
ADDR_RE=re.compile(r'\d{1,6}\s+[A-Z0-9][\w .#-]{2,60}?(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Way|Ct|Court|Hwy|Highway|Pkwy|Parkway|Pl|Place|Cir|Circle|Terrace)\b(?:[ \w.#,-]{0,50}?)[A-Z]{2}\s+\d{5}(?:-\d{4})?',re.I)
CONTACT_PATHS=['/contact','/contact-us','/contactus','/pages/contact','/about','/about-us','/pages/about-us','/wholesale',
'/terms','/terms-of-service','/terms-and-conditions','/policies/terms-of-service','/privacy','/privacy-policy','/policies/privacy-policy']

def _clean_text(html):
    t=re.sub(r'(?is)<(script|style|noscript).*?</\1>',' ',str(html or ''))
    t=re.sub(r'<[^>]+>',' ',t)
    t=t.replace('&amp;','&').replace('&#x27;',"'").replace('&quot;','"')
    return re.sub(r'\s+',' ',t).strip()

def _unwrap_ddg(href):
    u=urllib.parse.urlparse(href)
    if 'duckduckgo.com' in u.netloc:
        qs=urllib.parse.parse_qs(u.query)
        href=(qs.get('uddg') or [href])[0]
    return href

def _mine(text,emails,phones,addrs):
    """从任意文本粗提联系方式。"""
    for e in EMAIL_RE.findall(text or ''):
        e=e.strip('.,;:').lower()
        if not BAD_EMAIL.search(e) and len(e)<60: emails.add(e)
    for p in PHONE_RE.findall(text or ''):
        p=re.sub(r'\s+',' ',p).strip()
        if len(re.sub(r'\D','',p))>=10 and _phone_real(p): phones.add(p)
    for a in ADDR_RE.findall(text or ''):
        a=re.sub(r'\s+',' ',a).strip()
        if len(a)<140: addrs.add(a)

def _name_tokens(name):
    return [t for t in re.sub(r'[^a-z0-9 ]',' ',str(name or '').lower()).split() if len(t)>=4 and t not in ('candle','candles','home','inc','llc','ltd','corp','company','intl','international')]
def _site_match(name,dom):
    """域名与公司名相关性：长令牌出现 / 短令牌开头 / 首字母串开头(如 sbofusa=Signature Brands Of USA)。"""
    d=dom.lower().replace('www.','').split('.')[0].replace('-','').replace('_','')
    if not d or len(d)<4: return False
    words=[t for t in re.sub(r'[^a-z0-9 ]',' ',str(name or '').lower()).split() if t not in ('inc','llc','ltd','corp','company','the')]
    toks=[t for t in words if len(t)>=4 and t not in ('candle','candles','home','intl','international')]
    if any(t in d for t in toks): return True
    if any(len(t) in (2,3) and d.startswith(t) for t in words): return True
    init=''.join(t[0] for t in words)
    return len(init)>=2 and d.startswith(init)
BAD_PHONE=re.compile(r'(?:\+?1[\s.\-]?)?\(?555\)?[\s.\-]\d{3}[\s.\-]\d{4}|\(?\d{3}\)?[\s.\-]555[\s.\-]?01\d\d')
def _phone_real(p):
    """拒收好莱坞假号段：555区号(不存在) 和 555-01xx(虚构专用局号)。"""
    return not BAD_PHONE.search(str(p or ''))

FORBID_CC=re.compile(r'^\+(44|33|49|39|34|31|32|41|43|45|46|47|48|351|61|81|82|86|91|92|7|52|55|65|27)')
def _cc_ok(phone,country):
    """电话国家码与线索国家一致性：美加客户不该留欧/亚号段电话（张冠李戴的典型信号）。
    无+号的美式格式(如 800-90-1112)视为国内号放行。"""
    c=(country or '').upper()
    if c not in ('US','USA','CA','CAN','UNITED STATES'): return True
    p=re.sub(r'[\s()\-.]','',str(phone or ''))
    if p.startswith('+') and not p.startswith('+1'): return False
    return True

BAD_EDOM=re.compile(r'importinfo|importyeti|trademo|volza|panjiva|importgenius|exportgenius|importkey|'
    r'zoominfo|rocketreach|contactout|buzzfile|corporationwiki|dnb\.|manta\.|yellowpages|bbb\.org|'
    r'chamberofcommerce|opencorporates|datamyne|descartes|seair|zauba|tradeatlas',re.I)

def _email_ok(email,name,site):
    """邮箱归属校验: 数据网站/目录站域名一律拒收; 域名与官网一致或与公司名相关才留。"""
    dom=email.split('@')[-1].lower()
    if BAD_EDOM.search(dom): return False
    if site:
        sd=urllib.parse.urlparse(site).netloc.lower().replace('www.','')
        if dom==sd or sd.endswith('.'+dom) or dom.endswith('.'+sd): return True
        if dom.split('.')[0] in sd: return True
    return _site_match(name,dom)

UA={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Accept-Language':'en-US,en;q=0.9'}
def _http_get(url,timeout=14):
    """搜索页直连抓取：优先走 SCRAPE_PROXY_URL 代理（DDG/国际Bing 在国内需代理），无代理则直连。"""
    import urllib.request
    px=settings.SCRAPE_PROXY_URL
    op=urllib.request.build_opener(urllib.request.ProxyHandler({'http':px,'https':px}) if px else urllib.request.ProxyHandler({}))
    req=urllib.request.Request(url,headers=UA)
    with op.open(req,timeout=timeout) as r:
        return r.read().decode('utf-8','ignore')

def parse_ddg(html,limit=8):
    out=[]
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)class="result__snippet"[^>]*>(.*?)</a>',html,re.S):
        out.append({'title':_clean_text(m.group(2)),'url':_unwrap_ddg(m.group(1)),'snippet':_clean_text(m.group(4))})
    if not out:
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',html,re.S):
            out.append({'title':_clean_text(m.group(2)),'url':_unwrap_ddg(m.group(1)),'snippet':''})
    return out[:limit]
def parse_bing(html,limit=8):
    out=[]
    for blk in re.findall(r'<li class="b_algo[^"]*"[^>]*>(.*?)</li>',html,re.S):
        m=re.search(r'<h2[^>]*>.*?<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>',blk,re.S)
        if not m: continue
        sn=re.search(r'<p[^>]*>(.*?)</p>',blk,re.S)
        out.append({'title':_clean_text(m.group(2)),'url':m.group(1),'snippet':_clean_text(sn.group(1)) if sn else ''})
    return out[:limit]

CJK_RE=re.compile(r'[\u4e00-\u9fff]')
def _drop_cjk(rows):
    """搜美国公司时中文结果必是本地化垃圾（百度百科/词典/翻译），直接丢弃。"""
    return [r for r in rows if not CJK_RE.search((r.get('title') or '')+(r.get('snippet') or ''))]

def http_search(q,limit=8):
    """不依赖浏览器的搜索：DDG html -> 国际Bing。返回 (results, engine)。"""
    qe=urllib.parse.quote(q)
    try:
        r=_drop_cjk(parse_ddg(_http_get('https://html.duckduckgo.com/html/?q='+qe),limit))
        if r: return r,'ddg_http'
    except Exception as e: print('[contact] ddg_http failed:',str(e)[:60])
    try:
        r=_drop_cjk(parse_bing(_http_get('https://www.bing.com/search?q='+qe+'&mkt=en-US&setlang=en'),limit))
        if r: return r,'bing_http'
    except Exception as e: print('[contact] bing_http failed:',str(e)[:60])
    return [],''

PROGRESS=None  # UI进度回调 fn(str)，由 webui 注入；为 None 时静默
LAST={'webai_ready':None,'webai_tried':0,'webai_ok':0,'webai_note':''}  # 最近一次补全的网页AI统计（UI总结用）
def _prog(msg):
    try:
        if PROGRESS: PROGRESS(msg)
    except Exception: pass

def is_complete(lead):
    """开发区客户硬标准：官网 + 电话 + 邮箱 三件套齐全。"""
    return bool((lead.get('website') or '') and (lead.get('emails') or '') and (lead.get('phones') or ''))

def _email_candidates(site):
    """有官网没邮箱时，按常见模式生成候选（供网页AI验证/参考，不直接落库）。"""
    dom=urllib.parse.urlparse(site or '').netloc.lower().replace('www.','')
    if not dom: return []
    return [p+dom for p in ('info@','sales@','contact@','hello@')]

def _cdp_alive(url):
    import urllib.request
    try:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url+'/json/version',timeout=4) as r: return r.status==200
    except Exception: return False

class ContactFinder:
    def __init__(self):
        self._pw=None; self._br=None; self._pg=None; self._via_cdp=False
        self._webai=None; self._webai_used=0
    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw=sync_playwright().start()
        cdp=settings.IY_WEB_CDP_URL
        if settings.IY_WEB_CDP_ENABLED and _cdp_alive(cdp):
            self._br=self._pw.chromium.connect_over_cdp(cdp); self._via_cdp=True
            ctx=self._br.contexts[0]
            self._pg=ctx.pages[0] if ctx.pages else ctx.new_page()
            _prog('浏览器通道：已接管桌面Chrome(9222)')
            return
        _prog('警告：9222无响应，本次用内置无头浏览器跑，网页AI追问不可用！（先关掉所有Chrome窗口，再双击start_chrome_debug.bat）')
        try: self._br=self._pw.chromium.launch(channel='chrome',headless=True)
        except Exception: self._br=self._pw.chromium.launch(headless=True)
        self._pg=self._br.new_context().new_page()
    def close(self):
        try:
            if self._webai: self._webai.close()
            if self._br and not self._via_cdp: self._br.close()
            if self._pw: self._pw.stop()
        except Exception: pass
    def _goto(self,url,wait=2500):
        self._pg.goto(url,timeout=45000,wait_until='domcontentloaded')
        self._pg.wait_for_timeout(wait)
        try: return self._pg.content()
        except Exception:
            self._pg.wait_for_timeout(2500)
            return self._pg.content()
    # ---- 多引擎搜索：返回 [{title,url,snippet}]；HTTP(代理)优先，浏览器兜底 ----
    def search(self,q,limit=8):
        r,eng=http_search(q,limit)
        if r:
            self.last_engine=eng
            return r
        qe=urllib.parse.quote(q)
        # 1) DDG html
        try:
            html=self._goto('https://html.duckduckgo.com/html/?q='+qe,2000)
            out=[]
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)class="result__snippet"[^>]*>(.*?)</a>',html,re.S):
                out.append({'title':_clean_text(m.group(2)),'url':_unwrap_ddg(m.group(1)),'snippet':_clean_text(m.group(4))})
            if out: return _drop_cjk(out)[:limit]
            # 无snippet的结构
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',html,re.S):
                out.append({'title':_clean_text(m.group(2)),'url':_unwrap_ddg(m.group(1)),'snippet':''})
            if out: return _drop_cjk(out)[:limit]
        except Exception as e: print('[contact] ddg_html failed:',str(e)[:60])
        # 2) DDG lite
        try:
            html=self._goto('https://lite.duckduckgo.com/lite/?q='+qe,2000)
            out=[]
            for m in re.finditer(r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',html,re.S):
                out.append({'title':_clean_text(m.group(2)),'url':_unwrap_ddg(m.group(1)),'snippet':''})
            if out: return _drop_cjk(out)[:limit]
        except Exception as e: print('[contact] ddg_lite failed:',str(e)[:60])
        # 3) Bing
        try:
            html=self._goto('https://www.bing.com/search?q='+qe+'&mkt=en-US&setlang=en',2500)
            out=_drop_cjk(parse_bing(html,limit))
            if out: return out
        except Exception as e: print('[contact] bing failed:',str(e)[:60])
        return []
    # ---- 找官网（域名相关性校验 + 多查询变体） ----
    def find_site(self,name,country=''):
        for q in ('"%s" %s candles'%(name,country or 'USA'),'"%s" candle brand'%name,'%s candles USA official'%name):
            for r in self.search(q):
                dom=urllib.parse.urlparse(r['url']).netloc.lower()
                if not dom or SKIP_DOM.search(dom): continue
                if not _site_match(name,dom): continue
                return 'https://'+dom
        return None
    # ---- 抓官网联系页 ----
    def fetch_site_pages(self,site,emails,phones,addrs):
        texts=[]
        for path in ['']+CONTACT_PATHS:
            try: html=self._goto(site+path,1800)
            except Exception: continue
            body=_clean_text(html)
            if len(body)>200: texts.append(body[:4000])
            _mine(html+' '+body,emails,phones,addrs)
            if emails and addrs: break
        return texts
    # ---- 单个客户 enrich（多源综合） ----
    def enrich(self, lead, do_audit=True):
        from core.memory.db import DB
        db=DB(); norm=lead['norm']; name=lead['name']
        site=lead.get('website') or ''
        emails=set(e for e in (lead.get('emails') or '').split(',') if e)
        phones=set(p for p in (lead.get('phones') or '').split(',') if p)
        # v18.2.1 历史污染清洗：已存官网是数据网站域名 / 邮箱是数据网站域名 -> 先清空再补
        if site and SKIP_DOM.search(urllib.parse.urlparse(site).netloc.lower()):
            print('[contact] %s 已存官网是数据网站(%s)，清空重补'%(name,site)); site=''; db.lead_update(norm,website='')
        bad=[e for e in emails if not _email_ok(e,name,site)]
        if bad:
            print('[contact] %s 剔除污染邮箱: %s'%(name,','.join(sorted(bad))))
            emails-=set(bad); db.lead_update(norm,emails=','.join(sorted(emails)))
        addrs=set(); evidence=[]
        # ---- v18.0 AI直连优先：开发/维护客户先问DeepSeek/GPT，本地只验证+补漏 ----
        ai_first=(getattr(settings,'CONTACT_MODE','webai_first')=='webai_first'
                  and settings.WEBAI_ENABLED and (lead.get('zone') or 'pool') in ('dev','maint'))
        if ai_first:
            _prog('AI直连查询：%s（DeepSeek/GPT）'%name)
            wa0=self._webai_fallback(name,site,emails,phones,addrs,focus='force',country=lead.get('country') or '')
            if wa0.get('website') and not site: site=wa0['website']
            if wa0.get('address'): addrs.add(wa0['address'])
            _prog('%s AI答：%s'%(name,'官网%s 邮箱%d 电话%d'%('有' if site else '无',len(emails),len(phones)) if (site or emails or phones) else '未给出有效资料'))
        # 证据1：搜索摘要（AI直连已拿全三项时跳过搜索，省时省额度）
        res=[]
        if not ai_first or not (site and emails and phones):
            qmain='"%s" email phone address contact'%name
            try:
                res=self.search(qmain,limit=8)
                if len(res)<4:  # 结果太少时换个角度再搜一次并合并
                    more=self.search('"%s" LLC headquarters phone'%name,limit=6)
                    seen={r.get('url') for r in res}
                    res+=[r for r in more if r.get('url') not in seen]
                for r in res:
                    blob=(r.get('title','')+' '+r.get('snippet','')).strip()
                    if blob: evidence.append(blob[:400]); _mine(blob,emails,phones,addrs)
            except Exception as e: print('[contact] %s search failed: %s'%(name,str(e)[:60])); res=[]
        # 证据2：官网
        if not site:
            try: site=self.find_site(name,lead.get('country') or '')
            except Exception: pass
        if site:
            try: evidence+=self.fetch_site_pages(site,emails,phones,addrs)
            except Exception as e: print('[contact] %s site fetch failed: %s'%(name,str(e)[:60]))
        # 证据3：目录站页面（只提地址，不采邮箱电话——页脚全是目录站自己的联系方式，会污染）
        dirs=0
        for r in res:
            if dirs>=2: break
            dom=urllib.parse.urlparse(r.get('url','')).netloc.lower()
            if not DIR_OK.search(dom): continue
            try:
                body=_clean_text(self._goto(r['url'],1800))
                if len(body)>300:
                    evidence.append(body[:4000])
                    for a in ADDR_RE.findall(body):
                        a=re.sub(r'\s+',' ',a).strip()
                        if len(a)<140: addrs.add(a)
                    dirs+=1
            except Exception: continue
        # 邮箱归属过滤：只留与官网/公司名相关的（目录页摘要里的邮箱常是目录站自己的）
        emails={e for e in emails if _email_ok(e,name,site)}
        # 70B 综合：从全部证据中产出最终结构化结果（GPT式合成，本地免费）
        ext=self.llm_extract(name,evidence) if evidence else {}
        for e in ext.get('emails') or []:
            e=str(e).strip().lower()
            if EMAIL_RE.fullmatch(e) and not BAD_EMAIL.search(e) and _email_ok(e,name,site): emails.add(e)
        for p in ext.get('phones') or []:
            p=re.sub(r'\s+',' ',str(p)).strip()
            if len(re.sub(r'\D','',p))>=10: phones.add(p)
        if not site and ext.get('website'):
            w=str(ext['website']).strip()
            if w.startswith('http') and not SKIP_DOM.search(urllib.parse.urlparse(w).netloc): site=w
        # 网页AI兜底：仍无邮箱时最后问一次（AI直连模式已问过，跳过）
        wa={} if ai_first else self._webai_fallback(name,site,emails,phones,addrs,country=lead.get('country') or '')
        if wa.get('website') and not site: site=wa['website']
        if wa.get('address') and not addrs: addrs.add(wa['address'])
        # ---- v17.1 硬性标准二轮攻坚：开发/维护客户必须 官网+电话+邮箱 三件齐 ----
        if getattr(settings,'CONTACT_HARD_STD',True) and (lead.get('zone') or 'pool') in ('dev','maint'):
            missing=[x for x,ok in (('官网',bool(site)),('邮箱',bool(emails)),('电话',bool(phones))) if not ok]
            if missing:
                print('[contact] %s 二轮攻坚：缺%s'%(name,'/'.join(missing)))
                if not site:  # 换角度再搜官网
                    for q2 in ('"%s" contact information'%name,'"%s" company headquarters'%name):
                        try:
                            site=self.find_site(q2,lead.get('country') or '')
                        except Exception: site=''
                        if site: break
                if site and not emails:  # 官网有了但没邮箱：再抓一遍官网联系页
                    try: self.fetch_site_pages(site,emails,phones,addrs)
                    except Exception: pass
                if not ai_first and ((not emails) or (not phones)):  # 双引擎网页AI再问，问题直指缺口
                    wa2=self._webai_fallback(name,site,emails,phones,addrs,focus='full',country=lead.get('country') or '')
                    if wa2.get('website') and not site: site=wa2['website']
                    if wa2.get('address') and not addrs: addrs.add(wa2['address'])
        phones={p for p in phones if _cc_ok(p,lead.get('country')) and _phone_real(p)}  # v18.2.2 国家码 + v18.2.7 假号段

        # ---- v18.3.1 强制 GPT 补充缺失的关键字段 ----
        if getattr(settings,'WEBAI_ENABLED',True) and (not site or not emails):
            try:
                wa_force = self._webai_fallback(name, site, emails, phones, addrs, focus='force', country=lead.get('country') or '')
                if wa_force.get('website') and not site:
                    site = wa_force['website']
                if wa_force.get('address'):
                    if not addrs:
                        addrs.add(wa_force['address'])
                # 注意 _webai_fallback 内部会将 emails/phones 添加到对应的集合
                print('[contact] %s GPT强制补充: 官网%s 邮箱%d 电话%d' % (name, '有' if site else '无', len(emails), len(phones)))
            except Exception as e:
                print('[contact] %s GPT强制补充失败: %s' % (name, str(e)[:80]))

        kw={}
        if site: kw['website']=site
        if emails: kw['emails']=','.join(sorted(emails)[:5])
        if phones: kw['phones']=','.join(sorted(phones)[:3])
        addr=str(ext.get('address') or '').strip() or (sorted(addrs)[0] if addrs else '')
        if addr: kw['address']=addr[:200]
        if ext.get('contact_person'): kw['contact_person']=str(ext['contact_person'])[:120]
        if ext.get('linkedin'): kw['linkedin']=str(ext['linkedin'])[:200]
        # v18.3.0 假数据被滤光时同步清空库里的旧值，避免脏数据残留
        if not emails and (lead.get('emails') or ''): kw['emails']=''
        if not phones and (lead.get('phones') or ''): kw['phones']=''
        if kw: db.lead_update(norm,**kw)
        print('[contact] %s -> site:%s 邮箱%d 电话%d 地址:%s'%(name,'有' if site else '无',
              len(emails),len(phones),(kw.get('address') or '无')[:50]))
        miss=[x for x,ok in (('官网',bool(site)),('邮箱',bool(emails)),('电话',bool(phones))) if not ok]
        # ---- v18.3.0 资料审核闸口（可选择跳过，自动修正时由节点控制）----
        if do_audit and getattr(settings,'AUDIT_ENABLED',True):
            try:
                from core.tools import auditor
                auditor.PROGRESS=PROGRESS
                merged=dict(lead); merged.update(kw)
                merged['website']=site
                merged['emails']=','.join(sorted(emails)[:5])
                merged['phones']=','.join(sorted(phones)[:3])
                rep=auditor.audit_lead(merged,webai=self._webai)
                import json as _json
                db.lead_update(norm,audit=_json.dumps(rep,ensure_ascii=False))
                _prog('%s 资料审核：%s'%(name,auditor.VERDICT_CN.get(rep['verdict'],rep['verdict'])))
            except Exception as e:
                print('[audit] %s 审核失败: %s'%(name,str(e)[:80]))
        return {'norm':norm,'ok':bool(site),'emails':len(emails),'phones':len(phones),
                'complete':not miss,'missing':'/'.join(miss)}
    # ---- 网页AI兜底：本地多源仍缺邮箱时，问 DeepSeek/GPT（少量疑难用） ----
    def _ensure_webai(self):
        """网页AI就绪：挂已登录的CDP浏览器。连不上就抛错，原因给UI显示。"""
        if self._webai: return self._webai
        from core.tools import web_ai
        w=web_ai.WebAI(); w._launch()
        self._webai=w; return w

    def _webai_fallback(self,name,site,emails,phones,addrs,focus=None,country=''):
        if not settings.WEBAI_ENABLED: return {}
        if focus is None and emails: return {}
        if focus=='email' and emails: return {}
        if focus=='phone' and phones: return {}
        if focus=='full' and site and emails and phones: return {}
        # focus=='force'：无条件全项提问（v18.0 AI直连模式）
        if self._webai_used>=int(settings.WEBAI_PER_RUN):
            if not LAST.get('quota_told'):
                LAST['quota_told']=True
                _prog('网页AI本次额度(%d家)已用完，剩余客户本轮不再追问'%settings.WEBAI_PER_RUN)
            print('[webai] 本次兜底额度(%d)已用完'%settings.WEBAI_PER_RUN); return {}
        from core.utils import jsonutil
        try: self._ensure_webai()
        except Exception as e:
            if LAST.get('webai_ready') is not False:
                LAST['webai_ready']=False; LAST['webai_note']=str(e)[:80]
                _prog('网页AI未就绪：%s —— 缺资料将无法追问DeepSeek/GPT'%LAST['webai_note'])
            print('[webai] 未就绪: %s'%str(e)[:80]); return {}
        LAST['webai_ready']=True
        if focus=='force':
            need=['官网','公开联系邮箱','电话','总部地址']
        else:
            need=[]
            if not site: need.append('官网')
            if not emails: need.append('公开联系邮箱')
            if not phones: need.append('电话')
            need.append('总部地址')
        hint=''
        if site and not emails:
            cands=', '.join(_email_candidates(site)[:3])
            hint=('已知官网可能是 %s，请确认其公开邮箱（类似 %s 这类官网域名邮箱，必须是真实公开出现的，不要编造）。'%(site,cands))
        q=('公司 "%s"（美国蜡烛/家居香氛进口商）。请查它的：%s。%s'
           '只输出JSON：{"website":"","emails":[],"phones":[],"address":""}，查不到就给空值，不要编造。')%(name,'、'.join(need),hint)
        needtxt='全套资料' if focus=='force' else ('/'.join(need[:-1]) if len(need)>1 else '联系方式')
        _prog('网页AI追问：%s（缺%s，主引擎%s）'%(name,needtxt,settings.WEBAI_ENGINE))
        txt=self._webai.ask(q)
        self._webai_used+=1; LAST['webai_tried']=LAST.get('webai_tried',0)+1
        if not txt:
            # 主引擎没答 → 换备用引擎问同一题
            alt='chatgpt' if settings.WEBAI_ENGINE=='deepseek' else 'deepseek'
            _prog('%s 主引擎未回复，换 %s 再问'%(name,alt))
            txt=self._webai.ask(q,engine=alt)
            self._webai_used+=1; LAST['webai_tried']=LAST.get('webai_tried',0)+1
        if not txt:
            LAST['webai_note']='AI未回复（未登录或页面改版）'
            _prog('%s 两个引擎都没回复（检查AI浏览器登录态）'%name)
            return {}
        LAST['webai_ok']=LAST.get('webai_ok',0)+1
        j=jsonutil.j(txt)
        if not j:
            # 退一步：直接从回答文本里挖
            _mine(txt,emails,phones,addrs); return {}
        out={}
        w=str(j.get('website') or '').strip()
        if w.startswith('http'):
            dom=urllib.parse.urlparse(w).netloc.lower()
            if not SKIP_DOM.search(dom) and _site_match(name,dom): out['website']=w
        for e in j.get('emails') or []:
            e=str(e).strip().lower()
            if EMAIL_RE.fullmatch(e) and not BAD_EMAIL.search(e) and _email_ok(e,name,site or out.get('website')): emails.add(e)
        for p in j.get('phones') or []:
            p=re.sub(r'\s+',' ',str(p)).strip()
            if len(re.sub(r'\D','',p))>=10 and _cc_ok(p,country) and _phone_real(p): phones.add(p)
        if j.get('address'): out['address']=str(j['address'])[:200]
        return out

    # ---- 70B 综合提取 ----
    def llm_extract(self,name,evidence):
        from core.model.client import ModelClient
        from core.utils import jsonutil
        blob='\n---\n'.join(str(t)[:1200] for t in evidence[:10])[:7000]
        prompt=('你是信息提取员。下面是关于公司 "%s" 的多条网页证据（搜索摘要/官网/企业目录页）。\n'
                '综合所有证据，只输出 JSON：\n'
                '{"website":"官网URL(证据中出现的公司官网,不要目录站/社媒,没有则空字符串)",'
                '"emails":["邮箱,去掉明显假邮箱"],'
                '"phones":["电话,含国家码或区号格式"],'
                '"address":"总部街道地址(含城市/州/邮编,没有则空字符串)",'
                '"contact_person":"采购/批发相关负责人姓名+头衔(没有则空字符串)",'
                '"linkedin":"公司linkedin主页URL(没有则空字符串)"}\n'
                '证据：\n%s'%(name,blob))
        try:
            r=ModelClient().chat(prompt,temperature=0.1,max_tokens=700,timeout=int(settings.LLM_REVIEW_TIMEOUT))
            return jsonutil.j(r) or {}
        except Exception: return {}

def enrich_one(norm):
    """单个客户后台补全（移入开发区时自动触发）。"""
    from core.memory.db import DB
    l=DB().get_lead(norm)
    if not l: return None
    try:
        from core.tools import auditor; auditor.reset_run()
    except Exception: pass
    f=ContactFinder()
    try:
        f._launch()
        _prog('正在自动补全: '+l['name'])
        r=f.enrich(l)
        if r: _prog('%s：%s'%(l['name'],'三件套齐全 ✓' if r.get('complete') else '缺'+(r.get('missing') or '官网')))
    finally: f.close()
    from core.tools import scoring
    s,g,_=scoring.score_lead(DB().get_lead(norm) or l)
    DB().lead_update(norm,score=s,grade=g)
    return r

def run(limit=10,only_kind='importer',force=False,zones=('dev','maint')):
    """批量：只补开发区/维护区里缺联系方式的客户（线索池不确认开发，不浪费配额）。
    force=True 时重查所有（含已有部分信息的）。zones=None 表示不限分区（旧行为）。"""
    from core.memory.db import DB
    db=DB()
    leads=db.list_leads(kind=only_kind,limit=1000)
    if zones: leads=[l for l in leads if (l.get('zone') or 'pool') in zones]
    if not force:  # 跳过条件升级：三件套齐全才算"已补全"，缺任何一件都继续补
        leads=[l for l in leads if not is_complete(l)]
    leads=leads[:int(limit)]
    print('[contact] 待提取: %d 家'%len(leads))
    if not leads: return []
    LAST.update({'webai_ready':None,'webai_tried':0,'webai_ok':0,'webai_note':'','quota_told':False})
    try:
        from core.tools import auditor; auditor.reset_run()
    except Exception: pass
    f=ContactFinder(); out=[]
    try:
        f._launch()
        if settings.WEBAI_ENABLED:  # 预检：开跑前先把"AI能不能用"亮出来
            try:
                f._ensure_webai(); LAST['webai_ready']=True
                _prog('网页AI兜底已就绪（主引擎 %s），开始补全'%settings.WEBAI_ENGINE)
            except Exception as e:
                LAST['webai_ready']=False; LAST['webai_note']=str(e)[:80]
                _prog('注意：网页AI未就绪（%s）→ 缺资料不会追问DeepSeek/GPT！请先双击 start_chrome_debug.bat 并确认已登录，再重新点补全'%LAST['webai_note'])
                time.sleep(3)  # 让用户来得及看到这条
        for i,l in enumerate(leads):
            _prog('正在补全 %d/%d: %s ...'%(i+1,len(leads),l['name']))
            try:
                r=f.enrich(l); out.append(r)
                _prog('%s：%s'%(l['name'],'三件套齐全 ✓' if r.get('complete') else '缺'+(r.get('missing') or '官网')))
            except Exception as e:
                print('[contact] %s error: %s'%(l['name'],str(e)[:80]))
                _prog('%s：补全出错（详见控制台）'%l['name'])
            time.sleep(1)
    finally: f.close()
    ok=sum(1 for o in out if o.get('ok'))
    print('[contact] done: %d/%d 有官网'%(ok,len(out)))
    return out

if __name__=='__main__':
    import sys
    if len(sys.argv)>2 and sys.argv[1]=='diag':
        name=sys.argv[2]
        print('== 诊断:',name,'==')
        print('SCRAPE_PROXY_URL:',settings.SCRAPE_PROXY_URL or '(未配置)')
        r,eng=http_search('"%s" email phone address contact'%name)
        print('HTTP搜索[%s]: %d 条'%(eng or '全部失败',len(r)))
        for x in r[:4]: print('  -',x['title'][:60],'|',x['url'][:70],'|',x['snippet'][:80])
        f=ContactFinder(); f._launch()
        r2=f.search('"%s" email phone address contact'%name)
        print('浏览器兜底: %d 条'%len(r2))
        f.close()
    else:
        run(limit=3)\n\n================================================================================\n# FILE [21/40]: core/tools/data_sources/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [22/40]: core/tools/data_sources/base.py\n================================================================================\n\nimport urllib.parse,urllib.request,json,sqlite3,time,socket
from core.config import settings
def q(s): return urllib.parse.quote_plus(str(s or ''))
def key(market,industry): return str(market or '').lower()+'|'+str(industry or '').lower()
_PX={}
def proxy_alive():
    """代理健康检查：SCRAPE_PROXY_URL 配了但端口没人听（Clash没开）时回退直连，5分钟缓存。"""
    px=getattr(settings,'SCRAPE_PROXY_URL','') or ''
    if not px: return False
    hit=_PX.get(px)
    if hit and time.time()-hit[1]<300: return hit[0]
    ok=False
    try:
        u=urllib.parse.urlparse(px)
        s=socket.create_connection((u.hostname,u.port or 80),timeout=2); s.close(); ok=True
    except Exception: ok=False
    _PX[px]=(ok,time.time())
    if not ok: print(f'[proxy] {px} 不可达，本次回退直连（Clash 未启动？）')
    return ok
class Quota:
    def __init__(self,db=None): self.db=db or settings.DATABASE_PATH
    def _c(self): return sqlite3.connect(self.db,timeout=10)
    def hit(self,source,n=1):
        day=time.strftime('%Y-%m-%d')
        with self._c() as c: c.execute('INSERT INTO source_quota VALUES(?,?,?) ON CONFLICT(source,day) DO UPDATE SET count=count+?',(source,day,n,n))
    def used(self,source):
        day=time.strftime('%Y-%m-%d')
        with self._c() as c: r=c.execute('SELECT count FROM source_quota WHERE source=? AND day=?',(source,day)).fetchone()
        return r[0] if r else 0
    def remaining(self,source,quota): return max(0,quota-self.used(source))
class Source:
    name='base'; label='源'; strength=1; config_hint=''
    def available(self): return True
    def search(self,market,industry,limit): raise NotImplementedError
    def _opener(self):
        px=(getattr(settings,'SCRAPE_PROXY_URL','') or '') if proxy_alive() else ''
        return urllib.request.build_opener(urllib.request.ProxyHandler({'http':px,'https':px} if px else {}))
    def _text(self,url):
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 PSV/12'})
        with self._opener().open(req,timeout=settings.DATA_SOURCE_TIMEOUT) as r: return r.read().decode(errors='ignore')
    def _json(self,url):
        with self._opener().open(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 PSV/12'}),timeout=settings.DATA_SOURCE_TIMEOUT) as r: return json.loads(r.read().decode())
\n\n================================================================================\n# FILE [23/40]: core/tools/data_sources/manager.py\n================================================================================\n\nimport re,sqlite3,time,json
from core.config import settings
from core.tools.data_sources.base import key
from core.tools.data_sources.sources import BulkCustomsSource,CsvSource,ImportYetiSource,BingCnSource,ImportYetiWebSource,HsFinderSource
SUF=re.compile(r'\b(inc|llc|ltd|co|corp|corporation|company|imports|import|trading|trade)\b\.?',re.I)
BAD=re.compile(r'翻译|词典|百科|英语单词|是什么意思|amazon|ikea|walmart|alibaba|made-in-china|globalsource|on behalf of|freight|forwarder|logistics|packaging|\.com|_|\||…|&amp;',re.I)
def norm(n): return re.sub(r'[^a-z0-9一-鿿]+','',SUF.sub('',str(n or '').lower()))
def noise(n):
    n=str(n or '').strip(); return len(n)<3 or BAD.search(n) or not re.search(r'[a-zA-Z一-鿿]',n)
class Evolution:
    SYN={'birthday':['party candles','celebration candles'],
         'candle':['candle importer','candle wholesale'],
         'candles':['scented candles importer','wax candles']}
    def __init__(self): self.db=settings.DATABASE_PATH
    def count(self,market,industry):
        with sqlite3.connect(self.db) as c: r=c.execute('SELECT run_count FROM project_evolution WHERE project_key=?',(key(market,industry),)).fetchone()
        return r[0] if r else 0
    def _variants(self,base):
        b=str(base or '').lower().strip(); out=[]
        for k,vv in self.SYN.items():
            if k in b: out+=vv
        out+=['3406 candle',(str(base).strip()+' importer').strip(),(str(base).strip()+' distributor').strip()]
        seen=set(); res=[]
        for v in out:
            lv=v.lower().strip()
            if lv and lv!=b and lv not in seen: seen.add(lv); res.append(v)
        return res
    def plan(self,market,industry):
        c=self.count(market,industry)
        if c<settings.EVOLUTION_TRIGGER_RUNS: return {'evolved':False,'run_count':c,'variants':[industry],'note':f'普通搜索 第{c+1}次'}
        base=str(industry or '').strip(); vs=[base]+self._variants(base)
        vs=vs[:max(1,settings.EVOLUTION_MAX_QUERY_VARIANTS)]
        return {'evolved':True,'run_count':c,'variants':vs,'note':f'进化搜索 已采样{c}次 变体{len(vs)-1}个'}
    def record(self,market,industry,limit,result_count,used,errors,gate,evolved):
        now=time.time(); k=key(market,industry)
        with sqlite3.connect(self.db) as c:
            c.execute('INSERT INTO search_runs(project_key,market,industry,limit_n,result_count,used_sources,source_errors,gate,evolved,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(k,market,industry,limit,result_count,json.dumps(used,ensure_ascii=False),json.dumps(errors,ensure_ascii=False),json.dumps(gate,ensure_ascii=False),1 if evolved else 0,now))
            c.execute('INSERT INTO project_evolution VALUES(?,?,?,?) ON CONFLICT(project_key) DO UPDATE SET run_count=run_count+1,evolved=CASE WHEN run_count+1>=? THEN 1 ELSE evolved END,updated_at=?',(k,1,1 if evolved else 0,now,settings.EVOLUTION_TRIGGER_RUNS,now))
class DataSourceManager:
    def __init__(self): self.sources=[HsFinderSource(),BulkCustomsSource(),ImportYetiWebSource(),CsvSource(),ImportYetiSource(),BingCnSource()]; self.evo=Evolution(); self.last_evolution=None
    def search(self,market,industry,limit,variants_override=None):
        limit=int(limit or 20); target=max(limit,settings.AGGREGATE_MIN_RESULTS); per=max(limit,settings.SOURCE_PER_LIMIT)
        plan=self.evo.plan(market,industry); self.last_evolution=plan
        # v15：STRATEGY 节点/REFLECT 处方可覆盖查询词；否则用进化变体
        variants=[v for v in (variants_override or plan['variants']) if v][:4] or [industry]
        merged=[]; seen=set(); used=[]; errors=[]; breaker={}
        for variant in variants:
            for s in self.sources:
                if breaker.get(s.name,0)>=2: continue
                if s.name=='bing_cn' and merged: continue  # 必应只做空仓兜底：前面有货就不问它（网页标题垃圾多）
                if not s.available(): continue
                try:
                    found=s.search(market,variant,per) or []; breaker[s.name]=0
                except Exception as e:
                    breaker[s.name]=breaker.get(s.name,0)+1
                    tip='；连续失败已熔断，本轮跳过后续变体' if breaker[s.name]>=2 else ''
                    errors.append(f'{s.label}[{variant}]: {str(e)[:90]}{tip}'); continue
                if found and s.name not in used: used.append(s.name)
                for c in found:
                    n=(c.get('name') or '').strip()
                    if noise(n): continue
                    k=norm(n)
                    if k and k not in seen: seen.add(k); merged.append(c)
                if len(merged)>=target: break
            if len(merged)>=target: break
        merged.sort(key=lambda c:(c.get('strength') or 0),reverse=True)
        gate=gate_check(merged)
        self.evo.record(market,industry,limit,len(merged),used,errors,gate,plan['evolved'])
        return merged[:limit],used,errors,gate
def gate_check(companies):
    strong={'customs_bulk','csv_import','importyeti','importyeti_web'}
    qualified=[]; rejects=[]
    for c in companies or []:
        name=(c.get('name') or '').strip(); src=c.get('source') or ''
        if noise(name): rejects.append({'name':name,'reason':'noise'}); continue
        ev=c.get('evidence') or {}
        ev_txt=str(ev.get('products') or '')+' '+str(ev.get('hs') or '')+' '+str(ev.get('reasons') or '')
        ev_icp=bool(re.search(r'candle|3406|wax|fragrance',ev_txt,re.I))
        if src in strong or ev_icp or re.search(r'candle|importer|import|distributor|wholesale|trading|inc|llc|ltd',name,re.I): qualified.append(c)
        else: rejects.append({'name':name,'reason':'not_icp_like'})
    strong_count=sum(1 for c in qualified if c.get('source') in strong)
    ok=len(qualified)>=settings.GATE_MIN_QUALIFIED and (strong_count>=settings.GATE_MIN_STRONG or len(qualified)>=8)
    return {'ok':ok,'raw':len(companies or []),'qualified':len(qualified),'strong':strong_count,'rejects':rejects[:20]}
\n\n================================================================================\n# FILE [24/40]: core/tools/data_sources/sources.py\n================================================================================\n\nimport csv,re,sqlite3,time,json
from pathlib import Path
from core.config import settings
from core.tools.data_sources.base import Source,Quota,q
try:
    from curl_cffi import requests as creq
except Exception: creq=None
def card(name,country,industry,typ,source,strength,website='',evidence=None):
    return {'name':str(name or '').strip(),'country':country or '','industry':industry or '','type':typ or 'lead','website':website or '','source':source,'strength':strength,'evidence':evidence or {}}
class BulkCustomsSource(Source):
    name='customs_bulk'; label='90天提单库'; strength=5; config_hint='用 customs_clean.py 导入CSV后自动启用'
    def available(self):
        try:
            conn=sqlite3.connect(settings.DATABASE_PATH); n=conn.execute('SELECT COUNT(*) FROM buyers_90d').fetchone()[0]; conn.close(); return n>0
        except Exception: return False
    def search(self,market,industry,limit):
        conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
        rows=conn.execute('SELECT * FROM buyers_90d ORDER BY score DESC LIMIT ?',(max(limit,settings.SOURCE_PER_LIMIT),)).fetchall(); conn.close()
        return [card(r['importer'],'USA',industry,'importer',self.name,self.strength,'',{'shipments':r['shipments'],'score':r['score'],'last_seen':r['last_seen'],'reasons':r['reasons']}) for r in rows]
class CsvSource(Source):
    name='csv_import'; label='CSV手工导入'; strength=4; config_hint='放CSV到 data/imports'
    def available(self): return any(Path(settings.IMPORT_DIR).glob('*.csv'))
    def search(self,market,industry,limit):
        out=[]
        for fp in Path(settings.IMPORT_DIR).glob('*.csv'):
            with fp.open(encoding='utf-8-sig',errors='ignore') as f:
                for row in csv.DictReader(f):
                    name=(row.get('name') or row.get('company') or '').strip()
                    if name: out.append(card(name,row.get('country') or market,row.get('industry') or industry,row.get('type') or 'lead',self.name,self.strength,row.get('website') or '',{'email':row.get('email') or ''}))
                    if len(out)>=limit: return out
        return out
class ImportYetiSource(Source):
    name='importyeti'; label='ImportYeti海关摘要'; strength=4; config_hint='公开摘要，配额保护'
    def __init__(self): self.quota=Quota()
    def available(self): return settings.IMPORTYETI_ENABLED
    def _get(self,url):
        if creq:
            kw={'impersonate':'chrome','timeout':settings.DATA_SOURCE_TIMEOUT}
            if settings.SCRAPE_PROXY_URL: kw['proxies']={'http':settings.SCRAPE_PROXY_URL,'https':settings.SCRAPE_PROXY_URL}
            r=creq.get(url,**kw)
            if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code}')
            self.quota.hit(self.name); return r.json()
        data=self._json(url); self.quota.hit(self.name); return data
    def search(self,market,industry,limit):
        if str(market).lower() not in ('usa','us','united states','美国','america',''): return []
        if self.quota.remaining(self.name,settings.IMPORTYETI_DAILY_QUOTA)<=settings.IMPORTYETI_QUOTA_RESERVE: raise RuntimeError('ImportYeti配额触及保留线')
        items=[]
        for page in range(1,max(1,settings.IMPORTYETI_MAX_PAGES)+1):
            data=self._get(f"{settings.IMPORTYETI_SEARCH_URL}?q={q(industry)}&page={page}")
            rows=data.get('searchResults') or data.get('results') or data.get('data') or []
            if not rows: break
            items.extend(rows)
            if len(items)>=max(limit,settings.SOURCE_PER_LIMIT): break
        return [card(r.get('title') or r.get('name') or r.get('companyName'),'USA',industry,'importer',self.name,self.strength,r.get('website') or '',{'shipments':r.get('totalShipments'),'address':r.get('address') or ''}) for r in items if (r.get('title') or r.get('name') or r.get('companyName'))][:limit]
class ImportYetiWebSource(Source):
    name='importyeti_web'; label='ImportYeti网页'; strength=4; config_hint='Playwright真人节奏，直连'
    def available(self):
        if not getattr(settings,'IY_WEB_ENABLED',False): return False
        from core.tools import iy_web
        return iy_web.available()
    def search(self,market,industry,limit):
        if str(market).lower() not in ('usa','us','united states','美国','america',''): return []
        from core.tools import iy_web
        with iy_web.IYWeb() as w:
            if not w.ok: raise RuntimeError('Playwright/Chromium 未就绪（pip install playwright && playwright install chromium）')
            rows=w.search(industry,max(1,min(int(limit or 10),settings.IY_WEB_SEARCH_LIMIT)))
            err=w.last_error
        if not rows and err=='cloudflare':
            raise RuntimeError('被人机验证(Cloudflare)拦截：headless与可视窗口均未通过。请手工打开 importyeti.com 过一次验证再跑；快照见 data/iy_debug_*.html')
        if not rows and err=='parse_empty':
            raise RuntimeError('页面0条解析结果（结构可能变化），调试快照已存 data/iy_debug_*.html')
        # 同行工厂种子：搜索结果里的 supplier 卡片直接入池（slug 精确，收割时免二次搜索）
        try:
            from core.tools import suppliers as _sup
            seeds=[]
            for r in rows:
                if r.get('kind')!='supplier': continue
                n=_sup.norm(r['name'])
                if not n: continue
                seeds.append({'norm':n,'name':r['name'],'slug':r['url'].rstrip('/').split('/')[-1],
                              'shipments':r.get('shipments') or 0,'last_seen':time.time()})
            if seeds:
                _sup.upsert_pool(seeds)
                print('[importyeti_web] %d supplier seeds -> pool'%len(seeds))
        except Exception as e:
            print('[importyeti_web] seed pool skipped:',str(e)[:80])
        out=[]
        for r in rows:
            if r.get('kind')!='company': continue
            slug=r['url'].rstrip('/').split('/')[-1]
            out.append(card(r['name'],'USA',industry,'importer',self.name,self.strength,'',
                {'shipments':r.get('shipments'),'last_seen':r.get('last_seen'),
                 'address':r.get('address') or '','slug':slug,'url':r['url']}))
        return out
class BingCnSource(Source):
    name='bing_cn'; label='必应中国补充'; strength=1; config_hint='弱来源，只做补充'
    def available(self): return settings.BING_CN_ENABLED
    def search(self,market,industry,limit):
        bad=re.compile(r'翻译|词典|百科|英语单词|是什么意思|amazon|ikea|walmart|alibaba|made-in-china|globalsource|buy .*candle|scented candles|packaging|\.com|_|\||…|&amp;',re.I)
        html=self._text('https://cn.bing.com/search?q='+q(str(industry)+' USA importer company -amazon -ikea -翻译 -词典'))
        out=[]
        for m in re.finditer(r'<h2.*?>(.*?)</h2>',html,re.S|re.I):
            t=re.sub(r'<.*?>','',m.group(1)).strip(); t=re.sub(r'\s+',' ',t)
            if bad.search(t): continue
            if not re.search(r'candle|importer|import|distributor|wholesale|trading|inc|llc|ltd',t,re.I): continue
            if 3<=len(t)<=90: out.append(card(t,market,industry,'lead',self.name,self.strength))
            if len(out)>=limit: break
        return out

class HsFinderSource(Source):
    """v16 阶段1主路：HS Product Finder 榜单（证据化种子），每次 search 只跑首轮变体。"""
    name='hs_finder'; label='HS编码榜'; strength=5; config_hint='Product Finder by HS Code，提单硬证据'
    def __init__(self): self._done=False
    def available(self): return settings.HS_FINDER_ENABLED and not self._done
    def search(self,market,industry,limit):
        self._done=True
        from core.tools import hs_finder
        companies,sups=hs_finder.run()
        out=[]
        for c in companies:
            cd=card(c['name'],market,industry,'buyer',self.name,self.strength)
            cd['country']=c.get('country') or ''
            cd['evidence']={'shipments':c.get('shipments'),'last_shipment':c.get('last_shipment',''),
                            'hs':c.get('hs_code',''),'products':c.get('desc_sample',''),
                            'reasons':'HS%s榜[%s]'%(c.get('hs_code',''),'/'.join(c.get('tags') or []))}
            out.append(cd)
        return out
\n\n================================================================================\n# FILE [25/40]: core/tools/email_sequence.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""开发信自动序列模块：后台队列 + 进度持久化 + 失败自动保存草稿 + 通信记录。"""
import time
import sqlite3
import random
from core.config import settings
from core.memory.db import DB
from core.tools import contact_finder, auditor, mailer, pitch
from core.model.client import ModelClient

INTERVALS = [4 * 86400, 10 * 86400]  # 第一封后4天，第二封后10天

SEND_BUTTON_SELECTORS = [
    'button[aria-label="发送"]',
    'div[aria-label="发送"]',
    'button[title="发送"]',
    'div[role="button"]:has-text("发送")',
]

def init_table():
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS email_sequence(
                norm TEXT PRIMARY KEY,
                stage INTEGER DEFAULT 0,
                last_sent_at REAL,
                status TEXT DEFAULT 'pending'
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS email_drafts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                norm TEXT NOT NULL,
                stage INTEGER,
                subject TEXT,
                body TEXT,
                created_at REAL
            )
        ''')

def save_draft(norm, stage, subject, body):
    """保存邮件到本地草稿箱"""
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('''
            INSERT INTO email_drafts(norm, stage, subject, body, created_at)
            VALUES(?,?,?,?,?)
        ''', (norm, stage, subject, body, time.time()))

def get_customers(zone):
    db = DB()
    return [l for l in db.list_leads(kind='importer', zone=zone, limit=1000)
            if l.get('touch_status') not in ('replied', 'sample', 'deal')]

def get_sequence(norm):
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        row = c.execute('SELECT stage, last_sent_at, status FROM email_sequence WHERE norm=?', (norm,)).fetchone()
    if row:
        return {'stage': row[0], 'last_sent_at': row[1], 'status': row[2]}
    return {'stage': 0, 'last_sent_at': None, 'status': 'pending'}

def update_sequence(norm, stage=None, last_sent_at=None, status=None):
    current = get_sequence(norm)
    new_stage = current['stage'] if stage is None else stage
    new_last = current['last_sent_at'] if last_sent_at is None else last_sent_at
    new_status = current['status'] if status is None else status
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('''
            INSERT INTO email_sequence(norm, stage, last_sent_at, status) VALUES(?,?,?,?)
            ON CONFLICT(norm) DO UPDATE SET stage=excluded.stage, last_sent_at=excluded.last_sent_at, status=excluded.status
        ''', (norm, new_stage, new_last, new_status))

def should_send_now(seq):
    if seq['status'] == 'paused':
        return False, 'paused'
    if seq['stage'] == 0:
        return True, 'first'
    if seq['stage'] == 1 and seq['last_sent_at'] and (time.time() - seq['last_sent_at']) >= INTERVALS[0]:
        return True, 'second'
    if seq['stage'] == 2 and seq['last_sent_at'] and (time.time() - seq['last_sent_at']) >= INTERVALS[1]:
        return True, 'third'
    return False, 'waiting'

def ensure_contact(lead):
    """补全并审核客户资料。"""
    db = DB()
    fresh = db.get_lead(lead['norm']) or lead
    if not fresh.get('website') or not fresh.get('emails'):
        f = contact_finder.ContactFinder()
        try:
            f._launch()
            f.enrich(fresh, do_audit=False)
        finally:
            f.close()
        fresh = db.get_lead(fresh['norm']) or fresh
    updated, rep = auditor.audit_and_update(fresh, db=db, use_ai=True)
    return updated, rep

def generate_letter(lead, stage):
    if stage == 0:
        strategy = '这是第一封破冰开发信，介绍公司与产品，突出宁晋集群、免费寄样、常规无起订量，给一个低门槛动作。'
    elif stage == 1:
        strategy = '这是第二封跟进信，提供额外价值，如产品目录、针对客户采购记录的具体产品建议，再次强调免费寄样。语气轻松提醒。'
    else:
        strategy = '这是第三封尝试信，换一个角度，提及市场趋势或定制方案，语气简短尊重，表示如果暂时不需要可忽略。'

    client = ModelClient()
    prompt = ('你是资深外贸业务员，为以下客户写一封简短的英文开发信。\n' + strategy + '\n' + pitch.letter_prompt(lead))
    text = client.chat(prompt, system='你是资深外贸业务员，只输出英文邮件成稿', temperature=0.6, max_tokens=800, timeout=300)
    if not text:
        try:
            from core.tools import web_ai
            w = web_ai.WebAI(); w._launch()
            text = w.ask(prompt)
            w.close()
        except Exception:
            pass
    return text

def click_send_button(page, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in SEND_BUTTON_SELECTORS:
            try:
                els = page.query_selector_all(sel)
                for el in els:
                    if el.is_visible():
                        el.click()
                        return True
            except Exception:
                continue
        page.wait_for_timeout(2000)
    return False

def _get_browser_page():
    from core.tools.contact_finder import _cdp_alive
    if not _cdp_alive(settings.IY_WEB_CDP_URL):
        raise RuntimeError('Chrome 调试浏览器未启动（9222）')
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    br = pw.chromium.connect_over_cdp(settings.IY_WEB_CDP_URL)
    page = br.contexts[0].new_page()
    return pw, br, page

def open_compose_and_send(page, to, subject, body):
    page.goto(mailer.compose_url(to, subject, body, provider='outlook'), timeout=60000, wait_until='domcontentloaded')
    page.wait_for_timeout(6000)
    if not click_send_button(page):
        raise RuntimeError('自动点击发送失败')

def process_customer(lead, stage_name):
    """生成邮件内容，返回 (updated, subject, to, body) 或 (False, 错误信息)。"""
    updated, rep = ensure_contact(lead)
    if not updated.get('emails'):
        return False, '没有可用邮箱'

    stage_index = {'first':0, 'second':1, 'third':2}[stage_name]
    letter = generate_letter(updated, stage_index)
    if not letter or len(letter.strip()) < 50:
        return False, '开发信生成失败或过短'

    subject = f'Candle supply partnership - {updated["name"]}'
    to = updated['emails'].split(',')[0].strip()
    return updated, subject, to, letter

def run_sequence(zone='dev', max_customers=20, progress_cb=None):
    init_table()
    customers = get_customers(zone)
    if not customers:
        if progress_cb:
            progress_cb('没有可处理客户')
        return

    def log(msg):
        if progress_cb:
            progress_cb(msg)
        print(msg)

    log(f'开始开发信序列：{zone} 区域，候选 {len(customers)} 个，本次最多处理 {max_customers} 个')

    processed = 0
    for lead in customers:
        if processed >= max_customers:
            break

        seq = get_sequence(lead['norm'])
        should, stage_name = should_send_now(seq)
        if not should:
            continue

        update_sequence(lead['norm'], status='processing')
        log(f'[{processed+1}/{max_customers}] {lead["name"]} [{stage_name}]')

        try:
            result = process_customer(lead, stage_name)
            if result:
                updated, subject, to, body = result
                pw, br, page = _get_browser_page()
                try:
                    open_compose_and_send(page, to, subject, body)
                finally:
                    page.close()
                    br.close()
                    pw.stop()

                next_stage = {'first':1, 'second':2, 'third':3}[stage_name]
                if next_stage >= 3:
                    update_sequence(updated['norm'], stage=3, last_sent_at=time.time(), status='paused')
                else:
                    update_sequence(updated['norm'], stage=next_stage, last_sent_at=time.time(), status='active')

                # 写入通信记录
                db = DB()
                db.add_message(
                    updated['norm'],
                    'out',
                    'email',
                    f'[第{next_stage}封已发送] 收件人: {to} | 主题: {subject}\n\n{body[:500]}',
                    draft=0
                )
                db.lead_update(updated['norm'], touch_status='contacted', last_touch=time.time())
                processed += 1
                log(f'  已发送，记录阶段 {next_stage}，通信记录已更新')
            else:
                _, err = result
                update_sequence(lead['norm'], status='failed')
                log(f'  跳过：{err}')
        except Exception as e:
            # 发送失败，保存草稿
            try:
                if 'result' in locals() and isinstance(result, tuple) and len(result) == 4:
                    updated, subject, to, body = result
                    save_draft(updated['norm'], {'first':0,'second':1,'third':2}[stage_name], subject, body)
                    update_sequence(updated['norm'], status='draft_pending')
                    log(f'  发送失败，已保存草稿: {lead["name"]}')
                else:
                    update_sequence(lead['norm'], status='failed')
                    log(f'  处理失败且无内容保存: {str(e)[:120]}')
            except Exception:
                pass

        delay = random.uniform(8, 20)
        log(f'  等待 {delay:.1f} 秒...')
        time.sleep(delay)

    log(f'开发信序列完成：本次成功处理 {processed} 个客户，草稿保存在 email_drafts 表')\n\n================================================================================\n# FILE [26/40]: core/tools/expand.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v17: 关系网络循环扩张。
原理：每个买家有它的供应商，每个供应商有它的客户——沿着 ImportYeti 关系图逐层外扩：
  客户库 TopN 进口商 → 公司主页 Suppliers 区 → 新同行工厂入池
                     → 每家工厂 Customers 区 → 新买家进客户库（带来源链 via=expand:买家名）
去重闸门：leads 表 norm 去重 + suppliers.harvested_at 收割标记，跑多少次都不会重复劳动。
预算控制：EXPAND_BUYERS（每轮最多透视几家买家）、EXPAND_CUSTOMERS（每家工厂最多翻几个客户）、
EXPAND_MAX_NEW（每轮最多新增多少条线索，到量即停）。"""
import re,time
from core.config import settings

def _slug(name):
    return re.sub(r'-+','-',re.sub(r'[^a-z0-9]+','-',str(name or '').lower())).strip('-')

def run(limit_buyers=None,customers_per=None,max_new=None):
    from core.memory.db import DB
    from core.tools import suppliers as sup
    from core.tools import iy_web
    db=DB()
    limit_buyers=int(limit_buyers or settings.EXPAND_BUYERS)
    customers_per=int(customers_per or settings.EXPAND_CUSTOMERS)
    max_new=int(max_new or settings.EXPAND_MAX_NEW)
    # 按评分选种子买家：开发区优先，然后线索池高分
    seeds=[l for l in db.list_leads(kind='importer',limit=200) if l.get('kind')=='importer']
    seeds.sort(key=lambda l:((l.get('zone')=='dev')*2+(l.get('zone')=='maint'),l.get('score') or 0),reverse=True)
    seeds=seeds[:limit_buyers]
    print('[expand] 种子买家 %d 家: %s'%(len(seeds),'、'.join(l['name'] for l in seeds)))
    if not seeds: return {'buyers':0,'new_leads':0}
    stats={'buyers':0,'suppliers':0,'new_leads':0,'errors':[]}
    have={l['norm'] for l in db.list_leads(limit=10000)}
    done_sups={r[0] for r in __import__('sqlite3').connect(settings.DATABASE_PATH)
               .execute('SELECT supplier_norm FROM suppliers WHERE harvested_at IS NOT NULL')} if True else set()
    with iy_web.IYWeb() as w:
        if not w.ok:
            print('[expand] 浏览器未就绪'); return stats
        for lead in seeds:
            if stats['new_leads']>=max_new: break
            url='https://www.importyeti.com/company/'+_slug(lead['name'])
            try:
                rows=w.relationships(url,'Suppliers')
            except Exception as e:
                stats['errors'].append('%s: %s'%(lead['name'],str(e)[:60])); continue
            if not rows:
                print('[expand] %s 透视不到供应商（slug猜错或无数据）'%lead['name']); continue
            stats['buyers']+=1
            newsups=[r for r in rows if DB._norm(r['name']) not in done_sups]
            print('[expand] %s -> %d 供应商（%d 新）'%(lead['name'],len(rows),len(newsups)))
            sup.upsert_pool([{'norm':DB._norm(r['name']),'name':r['name'],'slug':_slug(r['name']),
                              'shipments':r.get('shipments') or 0,'last_seen':time.time(),'via':'expand:'+lead['name']} for r in rows])
            for r in sorted(newsups,key=lambda x:-(x.get('shipments') or 0))[:3]:  # 每家买家最多深挖3家新工厂
                if stats['new_leads']>=max_new: break
                sn=DB._norm(r['name'])
                surl='https://www.importyeti.com/supplier/'+_slug(r['name'])
                try:
                    custs=w.relationships(surl,'Customers')[:customers_per]
                except Exception as e:
                    stats['errors'].append('%s: %s'%(r['name'],str(e)[:60])); continue
                added=[]
                for c in custs:
                    cn=DB._norm(c['name'])
                    if not cn or cn in have: continue
                    have.add(cn)
                    added.append({'name':c['name'],'country':'US','kind':'importer','shipments':c.get('shipments') or 0,
                                  'segment':'candle' if re.search(r'candle|wax',c.get('products') or '',re.I) else '',
                                  'desc_sample':(c.get('products') or '')[:300],'source':'expand:'+lead['name']})
                if added: db.upsert_leads(added)
                stats['suppliers']+=1; stats['new_leads']+=len(added)
                sup.upsert_pool([{'norm':sn,'name':r['name'],'slug':_slug(r['name']),
                                  'shipments':r.get('shipments') or 0,'last_seen':time.time()}])
                sup.mark_harvested(sn,len(custs))
                sup.log_harvest('expand',_slug(r['name']),r['name'],'expand','ok',len(custs),'新增买家%d'%len(added))
                print('[expand]   工厂 %s -> 客户 %d（新增 %d）'%(r['name'],len(custs),len(added)))
    print('[expand] done: 透视%d买家·挖%d工厂·新增线索%d'%(stats['buyers'],stats['suppliers'],stats['new_leads']))
    return stats

if __name__=='__main__':
    run()
\n\n================================================================================\n# FILE [27/40]: core/tools/hs_finder.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v16: ImportYeti Product Finder by HS Code 采集器。
/hs-codes/{code} 页面按 Top / New / Fast Growing 三个切片抓取进口商榜（每片约7家），
并解析页底的近期提单表得到带证据的供应商种子（slug/日期/重量/品类描述）。
全部产出写入标准化 leads 表；供应商种子同时进 suppliers 池（via=hs_bol）。"""
import re,time,json,urllib.parse
from pathlib import Path
from core.config import settings

HS_SLUG={3406:'3406-candles-tapers-and-the-like'}
CHIPS=['Top','New','Fast Growing']
BIRTHDAY=re.compile(r'birthday|spiral|number candle|party candle',re.I)
CANDLE=re.compile(r'candle|wax|tealight|taper',re.I)
FORWARDER=re.compile(r'logistics|freight|forwarder|shipping|transatlantic|worldwide\s|express|cargo|supply chain',re.I)

def segment_of(text):
    t=str(text or '')
    if BIRTHDAY.search(t): return 'birthday'
    if CANDLE.search(t): return 'candle'
    return ''

def _clean(s): return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',str(s or ''))).strip()

def parse_companies(html,chip):
    """公司榜表格：name/country/tags/shipments/desc。返回标准化 lead dict 列表。"""
    out=[]
    for rw in re.findall(r'<tr class="[^"]*">(.*?)</tr>',html,re.S):
        m=re.search(r'href="/company/([^"]+)"[^>]*>([^<]+)',rw)
        if not m: continue
        slug,name=m.group(1),m.group(2).strip()
        flag=re.search(r'fflag-([A-Z]{2})',rw)
        tds=re.findall(r'<td[^>]*>(.*?)</td>',rw,re.S)
        txt=[_clean(t) for t in tds]
        ship=0;desc=''
        for t in txt:
            mm=re.match(r'^([\d,]+)\s',t)
            if mm and not ship: ship=int(mm.group(1).replace(',',''))
            if 'bills of lading' in t: desc=re.sub(r'\s*See all bills of lading.*$','',t).strip()
        tags=[chip] if chip else []
        for extra in ('Top','Fast Growing','New'):
            if extra!=chip and re.search(r'\b'+re.escape(extra)+r'\b',rw) and extra not in tags: tags.append(extra)
        out.append({'name':name,'slug':slug,'country':flag.group(1) if flag else '',
                    'kind':'importer','shipments':ship,'tags':tags,
                    'segment':segment_of(desc),'desc_sample':desc[:300],'source':'hs_finder'})
    return out

def parse_bol_suppliers(html,hs_code):
    """页底近期提单表：date/BOL/supplier+slug/weight/desc → 供应商种子。"""
    out=[]
    for rw in re.findall(r'<tr class="[^"]*">(.*?)</tr>',html,re.S):
        m=re.search(r'href="/supplier/([^"]+)"[^>]*>([^<]+)',rw)
        if not m: continue
        slug,name=m.group(1),m.group(2).strip()
        tds=[_clean(t) for t in re.findall(r'<td[^>]*>(.*?)</td>',rw,re.S)]
        date=tds[0] if tds and re.match(r'\d{2}/\d{2}/\d{4}',tds[0]) else ''
        weight='';desc=''
        for t in tds:
            if re.search(r'kg$',t): weight=t
            if t in ('Candles','Candle') or CANDLE.search(t) and len(t)<60 and 'kg' not in t: desc=t
        if FORWARDER.search(name): continue  # 货代/物流不是同行工厂
        flag=re.search(r'fflag-([A-Z]{2})',rw)
        out.append({'name':name,'slug':slug,'country':flag.group(1) if flag else '',
                    'kind':'supplier','hs_code':str(hs_code),'last_shipment':date,
                    'weight':weight,'segment':segment_of(desc or 'candle'),'desc_sample':desc,
                    'source':'hs_finder'})
    return out

# ---------- 浏览器层（与 iy_web 同一套 CDP 思路） ----------
def _cdp_alive(url):
    import urllib.request
    try:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url+'/json/version',timeout=4) as r: return r.status==200
    except Exception: return False

class HsFinder:
    def __init__(self):
        self._pw=None; self._br=None; self._pg=None; self._via_cdp=False
    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw=sync_playwright().start()
        cdp=settings.IY_WEB_CDP_URL
        if settings.IY_WEB_CDP_ENABLED and _cdp_alive(cdp):
            self._br=self._pw.chromium.connect_over_cdp(cdp); self._via_cdp=True
            ctx=self._br.contexts[0]
            self._pg=ctx.pages[0] if ctx.pages else ctx.new_page(); return
        try: self._br=self._pw.chromium.launch(channel='chrome',headless=True)
        except Exception: self._br=self._pw.chromium.launch(headless=True)
        self._pg=self._br.new_context().new_page()
    def close(self):
        try:
            if self._br and not self._via_cdp: self._br.close()
            if self._pw: self._pw.stop()
        except Exception: pass
    def _page(self,url,wait=4500):
        self._pg.goto(url,timeout=60000,wait_until='domcontentloaded')
        self._pg.wait_for_timeout(wait)
        return self._pg.content()
    def fetch(self,hs_code=3406,chips=None):
        """返回 (companies_leads, supplier_seeds)。切片点击失败时降级为当前页。"""
        if not self._pg: self._launch()
        slug=HS_SLUG.get(int(hs_code),str(hs_code))
        url='https://www.importyeti.com/hs-codes/'+slug
        chips=chips if chips is not None else CHIPS
        companies=[];seen=set();suppliers=[]
        first=True
        for chip in chips:
            try:
                if first:
                    html=self._page(url); first=False
                else:
                    self._pg.click('text='+chip,timeout=8000)
                    self._pg.wait_for_timeout(3500)
                    html=self._pg.content()
            except Exception as e:
                print('[hs_finder] chip %s failed: %s'%(chip,str(e)[:80])); continue
            if not suppliers: suppliers=parse_bol_suppliers(html,hs_code)
            for c in parse_companies(html,chip):
                c['hs_code']=str(hs_code)
                k=c['slug'] or c['name'].lower()
                if k in seen: continue
                seen.add(k); companies.append(c)
        for c in companies: print('[hs_finder] importer: %s | %s | %s提单 | %s'%(c['name'],c['country'],c['shipments'],'/'.join(c['tags'])))
        print('[hs_finder] hs%s: %d importers, %d bol suppliers'%(hs_code,len(companies),len(suppliers)))
        return companies,suppliers

def run(hs_codes=None):
    """入口：按配置的 HS 编码列表采集，写 leads 表 + suppliers 池。"""
    from core.memory.db import DB
    from core.tools import suppliers as sup
    codes=hs_codes or [c.strip() for c in str(settings.HS_CODES).split(',') if c.strip()]
    f=HsFinder(); allc=[]; alls=[]
    try:
        for code in codes:
            try:
                c,s=f.fetch(code); allc+=c; alls+=s
            except Exception as e:
                print('[hs_finder] hs%s failed: %s'%(code,str(e)[:120]))
    finally: f.close()
    db=DB()
    if allc: db.upsert_leads(allc)
    if alls:
        db.upsert_leads(alls)
        sup.upsert_pool([{'norm':DB._norm(s['name']),'name':s['name'],'slug':s['slug'],'shipments':0,
                          'last_seen':time.time(),'via':'hs_bol'} for s in alls if s.get('slug')])
    return allc,alls

if __name__=='__main__':
    c,s=run()
    print('SELF-TEST: %d importers, %d suppliers'%(len(c),len(s)))
\n\n================================================================================\n# FILE [28/40]: core/tools/iy_web.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""ImportYeti 网页收割器（Playwright 真人节奏模拟）。
数据源是手工验证过的免费网页：/search → /company/{slug} → /supplier/{slug}。
v14.2 强化：
- Cloudflare 挑战轮询等待（默认最长30秒，IY_WEB_CHALLENGE_WAIT 可调）
- headless 被拦截时自动切换【可视窗口】重试一次（IY_WEB_AUTO_HEADED=true）
- 全程 last_error 诊断：cloudflare / parse_empty / no_playwright / launch:*
- 命令行自检：python -m core.tools.iy_web "birthday candles"
- 解析失败自动把页面 HTML 存到 data/iy_debug_*.html 供迭代选择器"""
import json,random,re,time
from pathlib import Path
from core.config import settings
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
CHALLENGE=re.compile(r'just a moment|attention required|cf-chl|challenge-platform|verify you are human|cf-turnstile|performing security verification',re.I)
# ---------- 文本解析（基于真实页面结构，纯函数可单测）----------
def _num(s):
    m=re.match(r'^([\d,]+)$',s.strip()); return int(m.group(1).replace(',','')) if m else None
def parse_search_card(text):
    """搜索结果卡片文本 → {kind,address,shipments,last_seen}"""
    lines=[l.strip() for l in (text or '').splitlines() if l.strip()]
    kind=''; address=''; shipments=0; last_seen=''
    for i,l in enumerate(lines):
        if l in ('company','supplier') and not kind: kind=l
        if l=='Total Shipments' and i+1<len(lines):
            shipments=_num(lines[i+1]) or 0
            if i>0: address=lines[i-1]
        if l=='Most recent shipment' and i+1<len(lines): last_seen=lines[i+1]
    return {'kind':kind,'address':address,'shipments':shipments,'last_seen':last_seen}
def parse_rel_text(text,section):
    """公司/供应商主页的关系区文本（Suppliers|Customers）→ [{name,location,shipments,products,hs}]"""
    m=re.search(r"'s\s*"+section,text or '')
    if not m: return []
    lines=[l.strip() for l in text[m.start():].splitlines() if l.strip()]
    try: start=lines.index('Product Descriptions')+1
    except ValueError: start=0
    rows=[]; i=start
    STOP=re.compile(r'^(Cost Structure|Top 10|Recent Sea Shipments|Addresses and Contact|Imports Per Country)')
    while i<len(lines) and len(rows)<25:
        l=lines[i]
        if STOP.search(l): break
        if l in ('CSV','See all bills of lading with this supplier','See all bills of lading with this company') or l.startswith('HS Codes'):
            i+=1; continue
        # 一行关系记录：名称开头 → 地点行 → 纯数字(出货量) → 产品/HS → 直到 "See all bills..."
        name=l; j=i+1; loc=[]; shipments=0; products=[]; hs=[]
        while j<len(lines):
            s=lines[j]
            if s in (',',): j+=1; continue
            n=_num(s)
            if n is not None and not shipments: shipments=n; j+=1; break
            if s.startswith('HS Codes') or STOP.search(s): break
            loc.append(s); j+=1
        while j<len(lines):
            s=lines[j]
            if s.startswith('See all bills of lading'): j+=1; break
            if STOP.search(s): break
            if s=='(': j+=1; continue
            products.append(s); j+=1
        # 提取 HS 编码
        prod_txt=' '.join(products)
        hm=re.search(r'HS Codes?:\s*\(?\s*([\d.,\s)]+)',prod_txt)
        if hm: hs=[x for x in re.split(r'[,\s]+',hm.group(1).strip(' )')) if re.match(r'^\d',x)]
        if name and shipments:
            rows.append({'name':name,'location':' '.join(loc),'shipments':shipments,
                         'products':re.sub(r'HS Codes?:.*','',prod_txt).strip(' (')[:200],'hs':hs[:6]})
        i=max(j,i+1)
    return rows
# ---------- 浏览器层 ----------
_PW=None
def _pw():
    global _PW
    if _PW is None:
        try:
            from playwright.sync_api import sync_playwright
            _PW=sync_playwright
        except Exception:
            _PW=False
    return _PW
def _cdp_alive(url):
    """桌面浏览器调试端口是否已开（start_chrome_debug.bat 启动的 Chrome/Edge）"""
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip('/')+'/json/version',timeout=2) as r:
            return r.status==200
    except Exception: return False
class IYWeb:
    """一个实例 = 一个浏览器会话。用法：with IYWeb() as w: w.search(...) / w.relationships(...)
    优先级：CDP 接管桌面浏览器（真实profile，Cloudflare视为真人）→ 自启动 headless/可视窗口"""
    def __init__(self,headless=None):
        self.headless=settings.IY_WEB_HEADLESS if headless is None else bool(headless)
        self.ok=False; self.last_error=''; self.escalated=False; self._via_cdp=False
        self._p=None; self._b=None; self._pg=None
        if not _pw(): self.last_error='no_playwright'; return
        self._launch(self.headless)
    def _launch(self,headless):
        self._close_browser()
        try:
            if self._p is None: self._p=_pw()().start()
            # 1) 优先接管桌面浏览器（CDP）：真实 Chrome/Edge + 持久 profile，验证一次后长期免验证
            cdp_url=getattr(settings,'IY_WEB_CDP_URL','http://127.0.0.1:9222')
            if getattr(settings,'IY_WEB_CDP_ENABLED',True) and _cdp_alive(cdp_url):
                self._b=self._p.chromium.connect_over_cdp(cdp_url)
                ctx=self._b.contexts[0] if self._b.contexts else self._b.new_context()
                self._pg=ctx.pages[0] if ctx.pages else ctx.new_page()
                self.ok=True; self._via_cdp=True
                print('[iy_web] attached to DESKTOP browser via CDP (%s)'%cdp_url)
                return
            # 2) 自启动浏览器（优先系统 Chrome，其次内置 Chromium）
            args=['--disable-blink-features=AutomationControlled','--no-first-run']
            try:
                self._b=self._p.chromium.launch(headless=headless,channel='chrome',args=args)
            except Exception:
                self._b=self._p.chromium.launch(headless=headless,args=args)
            ctx=self._b.new_context(user_agent=UA,viewport={'width':1366,'height':900},locale='en-US',timezone_id='America/New_York')
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            self._pg=ctx.new_page(); self.ok=True
            print('[iy_web] browser ready (%s; tip: run start_chrome_debug.bat to use your desktop browser)'%('headless' if headless else 'VISIBLE window'))
        except Exception as e:
            self.last_error='launch:'+str(e)[:120]; self.ok=False
    def _close_browser(self):
        try:
            if self._b: self._b.close()  # CDP 模式下只是断开连接，不会关掉用户的桌面浏览器
        except Exception: pass
        self._b=None; self._pg=None
    def close(self):
        self._close_browser()
        try:
            if self._p: self._p.stop()
        except Exception: pass
        self._p=None; self.ok=False
    def __enter__(self): return self
    def __exit__(self,*a): self.close()
    def _pace(self):
        time.sleep(random.uniform(settings.IY_WEB_DELAY_MIN,settings.IY_WEB_DELAY_MAX))
    def _is_challenge(self):
        try:
            if CHALLENGE.search(self._pg.title() or ''): return True
            return bool(CHALLENGE.search((self._pg.content() or '')[:6000]))
        except Exception: return False
    def _goto(self,url):
        self._pace()
        self._pg.goto(url,timeout=45000,wait_until='domcontentloaded')
        self._pg.wait_for_timeout(2500)
        if self._is_challenge():
            wait_s=float(getattr(settings,'IY_WEB_CHALLENGE_WAIT','30'))
            print('[iy_web] Cloudflare challenge, waiting up to %.0fs ...'%wait_s)
            if self._via_cdp: print('[iy_web] >> click the checkbox in your desktop browser window, the script is waiting <<')
            t0=time.time()
            while time.time()-t0<wait_s:
                self._pg.wait_for_timeout(2000)
                if not self._is_challenge(): break
        return self._pg
    def _run(self,tag,fn):
        """执行一次采集；headless 被 Cloudflare 拦住时自动升级可视窗口重试一次（CDP 模式已是真实桌面浏览器，无需升级）"""
        rows=fn()
        if not rows and self.last_error=='cloudflare' and not self._via_cdp and self.headless and getattr(settings,'IY_WEB_AUTO_HEADED',True):
            print('[iy_web] headless blocked by Cloudflare; retrying with a VISIBLE browser window')
            print('[iy_web] (if a checkbox/captcha appears, just click it - the script waits)')
            self._launch(False); self.escalated=True
            if self.ok: rows=fn()
        if not rows: self._debug_dump(tag)
        return rows
    def _debug_dump(self,tag):
        try:
            fp=Path(settings.DATABASE_PATH).parent/f'iy_debug_{tag}_{int(time.time())}.html'
            fp.write_text(self._pg.content(),encoding='utf-8')
            print('[iy_web] debug snapshot saved:',fp.name)
            return fp.name
        except Exception: return ''
    def _search_once(self,query,limit):
        self.last_error=''
        import urllib.parse
        print('[iy_web] search:',query)
        pg=self._goto('https://www.importyeti.com/search?q='+urllib.parse.quote_plus(query))
        if self._is_challenge(): self.last_error='cloudflare'; return []
        cards=pg.eval_on_selector_all('a[href*="/company/"],a[href*="/supplier/"]',"""els=>els.map(a=>{
            let box=a,txt='';
            for(let i=0;i<6&&box;i++){box=box.parentElement;if(box&&/Total Shipments/.test(box.innerText||'')){txt=box.innerText;break;}}
            return {name:(a.innerText||'').trim(),href:a.href,text:txt};
        }).filter(x=>x.name&&x.text)""")
        out=[]
        for c in cards[:limit]:
            info=parse_search_card(c['text'])
            if not info.get('kind'):  # 卡片文本里没有 company/supplier 行时，从 URL 补判
                info['kind']='company' if '/company/' in c['href'] else ('supplier' if '/supplier/' in c['href'] else '')
            out.append({'name':c['name'],'url':c['href'],**info})
        if not out: self.last_error='parse_empty'
        else: print('[iy_web] %d cards parsed'%len(out))
        return out
    def search(self,query,limit=10):
        """搜索页 → [{name,url,kind,address,shipments,last_seen}]（公司/供应商卡片）"""
        return self._run('search',lambda:self._search_once(query,limit))
    def _rel_once(self,url,section):
        self.last_error=''
        pg=self._goto(url)
        if self._is_challenge(): self.last_error='cloudflare'; return []
        txt=pg.eval_on_selector('body','e=>e.innerText')
        rows=parse_rel_text(txt,section)
        if not rows: self.last_error='parse_empty'
        else: print('[iy_web] %s: %d rows'%(section,len(rows)))
        return rows
    def relationships(self,url,section):
        """公司/供应商主页 → 关系区（'Suppliers'|'Customers'）行列表"""
        return self._run('rel_'+section.lower(),lambda:self._rel_once(url,section))
    def supplier_page_for(self,name):
        """按供应商名搜索，取第一个 supplier 卡片的主页 URL"""
        for c in self.search(name,limit=5):
            if c.get('kind')=='supplier' or '/supplier/' in c.get('url',''):
                return c['url']
        return None
def available():
    return bool(_pw())
def main():
    """命令行自检：python -m core.tools.iy_web "birthday candles" """
    import sys
    query=' '.join(sys.argv[1:]).strip() or 'birthday candles'
    with IYWeb() as w:
        if not w.ok:
            print('FAIL: browser not ready:',w.last_error); return 2
        rows=w.search(query,10)
        mode='desktop_cdp' if w._via_cdp else ('headless' if w.headless else 'visible')
        print(json.dumps({'query':query,'mode':mode,'count':len(rows),'last_error':w.last_error,
                          'escalated_to_visible':w.escalated,'sample':rows[:3]},ensure_ascii=False,indent=2))
        if rows:
            print('SELF-TEST OK: importyeti_web usable'); return 0
        print('SELF-TEST EMPTY: check data/iy_debug_*.html (send it back for selector fix)')
        return 1
if __name__=='__main__': raise SystemExit(main())
\n\n================================================================================\n# FILE [29/40]: core/tools/mailer.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v18.0 邮件发送双通道：compose 半自动 + smtp 直发。
支持抄送多个邮箱。"""
import urllib.parse
from core.config import settings

COMPOSE={
 'gmail':'https://mail.google.com/mail/?view=cm&fs=1&to={to}&su={su}&body={body}&cc={cc}',
 'outlook':'https://outlook.live.com/mail/0/deeplink/compose?to={to}&subject={su}&body={body}&cc={cc}',
}

def compose_url(to,subject,body,cc_list=None,provider=None):
    tpl=COMPOSE.get(str(provider or getattr(settings,'MAIL_PROVIDER','outlook') or 'outlook').lower(),COMPOSE['outlook'])
    q=lambda s: urllib.parse.quote(str(s or ''),safe='')
    cc=','.join(cc_list) if cc_list else ''
    return tpl.format(to=q(to),su=q(subject),body=q(body),cc=q(cc))

def open_compose(to,subject,body,cc_list=None,provider=None):
    """在AI控制浏览器里新开一页，打开预填好的写信页。"""
    from core.tools.contact_finder import _cdp_alive
    if not _cdp_alive(settings.IY_WEB_CDP_URL):
        raise RuntimeError('AI浏览器(9222)未启动——先双击 start_chrome_debug.bat')
    from playwright.sync_api import sync_playwright
    pw=sync_playwright().start()
    try:
        br=pw.chromium.connect_over_cdp(settings.IY_WEB_CDP_URL)
        ctx=br.contexts[0]
        pg=ctx.new_page()
        pg.goto(compose_url(to,subject,body,cc_list,provider),timeout=60000,wait_until='domcontentloaded')
    finally:
        try: pw.stop()
        except Exception: pass

def smtp_configured():
    return bool(getattr(settings,'SMTP_HOST','') and getattr(settings,'SMTP_USER','') and getattr(settings,'SMTP_PASS',''))

def smtp_send(to,subject,body,cc_list=None):
    """SMTP直发，支持抄送。"""
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    if not smtp_configured():
        raise RuntimeError('未配置SMTP：.env 里加 SMTP_HOST / SMTP_USER / SMTP_PASS(授权码)')
    msg=MIMEText(str(body),'plain','utf-8')
    msg['Subject']=Header(str(subject),'utf-8')
    msg['From']=getattr(settings,'SMTP_FROM','') or settings.SMTP_USER
    msg['To']=to
    if cc_list:
        msg['Cc']=','.join(cc_list)
    port=int(getattr(settings,'SMTP_PORT',587))
    last_err=None
    try:
        if port==465:
            s=smtplib.SMTP_SSL(settings.SMTP_HOST,port,timeout=25)
        else:
            s=smtplib.SMTP(settings.SMTP_HOST,port,timeout=25)
            s.starttls()
        s.login(settings.SMTP_USER,settings.SMTP_PASS)
        s.sendmail(msg['From'],[to]+(cc_list or []),msg.as_string())
        s.quit()
        return
    except Exception as e:
        last_err=e
        print('[mailer] SMTP失败:',str(e)[:100])
    raise RuntimeError('SMTP发送失败：%s'%str(last_err)[:120])
\n\n================================================================================\n# FILE [30/40]: core/tools/pitch.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v17: 开发信话术内核——宁晋集群叙事 + 真实署名 + 按客户画像定制钩子。
D_OUTREACH 节点和通信模块共用这一套，保证口径一致。
所有"事实"只允许来自这里登记的素材，禁止大模型编造数字。"""
from core.config import settings

# 宁晋生日蜡烛产业集群（老板亲述素材，可直接引用的事实）
CLUSTER_FACTS=[
 'Our factory is based in Ningjin, Hebei — the hometown of birthday candles, a cluster that supplies roughly 60% of the world\'s birthday candles.',
 'The cluster works like one giant production line: hundreds of specialized workshops each master a single step or category, and full-chain manufacturers handle R&D to finished product — so capacity is flexible, sampling is fast, and pricing stays very competitive.',
]


# 新增业务事实：免费打样/寄样、常规产品无起订量、定制产品详谈
EXTRA_FACTS = [
    'We offer free samples for candle products — free sampling and free shipping for evaluation.',
    'For our regular market products, there is no minimum order quantity (MOQ).',
    'For customized products, we can discuss details based on your specific requirements.',
]

def signature():
    """真实署名块：姓名+邮箱+WhatsApp 三渠道，客户任选都能找回我们（settings/.env 可改）。"""
    lines=['Best regards,',
           '%s (%s)'%(settings.SENDER_NAME_EN,settings.SENDER_NAME),
           'Birthday Candle Manufacturer, Ningjin, Hebei, China']
    em=(getattr(settings,'SENDER_EMAIL','') or '').strip()
    if em: lines.append('Email: %s'%em)
    lines.append('WhatsApp / Mobile: %s'%settings.SENDER_PHONE)
    return '\n'.join(lines)

def hooks_for(lead):
    """按客户画像选钩子（最多2个，宁缺毋滥）。返回英文要点列表。"""
    hooks=[]
    seg=lead.get('segment') or ''
    tags=str(lead.get('tags') or '')
    ship=int(lead.get('shipments') or 0)
    score=float(lead.get('score') or 0)
    if seg=='birthday':
        hooks.append('Lead with the Ningjin birthday-candle cluster story; mention spiral candles, number candles and party candles specifically (their product line matches).')
    elif seg=='candle':
        hooks.append('Position us as candle specialists (scented/pillar/decorative), with the birthday-candle cluster as proof of category depth.')
    else:
        hooks.append('Open with the candle-manufacturing capability and OEM/ODM service; mention the Ningjin cluster briefly as credibility.')
    if score>=75 or ship>=500:
        hooks.append('They buy at scale — emphasize stable capacity, consistent quality control, and competitive cluster pricing for large volumes.')
    if 'New' in tags:
        hooks.append('They recently started importing candles — emphasize low MOQ trial orders and fast free samples to lower their entry risk.')
    if 'Fast Growing' in tags:
        hooks.append('They are growing fast — emphasize flexible capacity that scales with their orders and short lead times.')
    return hooks[:2]

def letter_prompt(lead,ammo=''):
    """生成给 LLM 的完整写信指令。"""
    who='; '.join([x for x in [lead.get('name'),lead.get('country'),
        '生日蜡烛品类买家' if lead.get('segment')=='birthday' else ('蜡烛品类买家' if lead.get('segment') else ''),
        ('年提单约%d条'%lead['shipments']) if lead.get('shipments') else '',
        (lead.get('desc_sample') or '')[:120]] if x])
    hooks='\n'.join('- '+h for h in hooks_for(lead))
    return ('你是资深外贸业务员，为以下客户写一封简短的英文开发信（正文120词以内）。\n'
            '【可引用的事实素材，只允许用这些，禁止编造其他数字】\n'+'\n'.join('- '+f for f in CLUSTER_FACTS+EXTRA_FACTS)+'\n'
            +(('【市场情报】'+ammo[:300]+'\n') if ammo else '')
            +'【客户】'+who+'\n'
            '【针对此客户的钩子，选1-2个自然融入，不要全堆】\n'+hooks+'\n'
            '【我方身份】公司名固定写作 '+getattr(settings,'SENDER_COMPANY','Ningjin Birthday Candle Factory')+'，是宁晋的生日蜡烛制造工厂（不是贸易/物流/包装公司）；\n'
            '【要求】第一行写 Subject: ...；称呼用采购团队即可（Hi team 或 Hello）；'
            '正文简短、具体、无空话；结尾给一个低门槛动作（回复要目录/报价单/免费样品）；\n'
            '严禁出现 [Your Company Name] 之类的占位符，自我介绍直接写公司名；\n'
            '署名必须原样使用以下内容：\n'+signature()+'\n'
            '只输出成稿本身，不要解释。')
\n\n================================================================================\n# FILE [31/40]: core/tools/scoring.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v16.1: 客户评分（确定性公式，LLM 离线也可算）。
评分维度：提单量(40) + 品类信号(20) + 榜单标签(15) + 联系方式完整度(15) + 美国本土(5) + 最近活跃度(5)。
等级：>=75 A（优先开发），>=55 B，其余 C。写回 leads.score / leads.grade。"""
import math,time

def score_lead(lead):
    s=0.0; why=[]
    ship=int(lead.get('shipments') or 0)
    if ship>0:
        pts=min(40.0, math.log10(ship+1)/math.log10(2000)*40)  # 2000提单≈满分40
        s+=pts; why.append('提单%d(+%.0f)'%(ship,pts))
    seg=lead.get('segment') or ''
    if seg=='birthday': s+=20; why.append('生日蜡烛信号(+20)')
    elif seg=='candle': s+=10; why.append('蜡烛品类(+10)')
    tags=str(lead.get('tags') or '')
    tp=0
    if 'Top' in tags: tp+=10
    if 'New' in tags: tp+=5
    if 'Fast Growing' in tags or 'FG' in tags: tp+=5
    tp=min(15,tp)
    if tp: s+=tp; why.append('榜单标签(+%d)'%tp)
    if lead.get('emails'): s+=10; why.append('有邮箱(+10)')
    if lead.get('website'): s+=5; why.append('有官网(+5)')
    if (lead.get('country') or '').upper()=='US': s+=5; why.append('美国(+5)')
    ls=lead.get('last_shipment') or ''
    if ls:
        try:
            y=int(str(ls)[-4:])
            if y>=time.localtime().tm_year-1: s+=5; why.append('近期活跃(+5)')
        except Exception: pass
    s=round(min(100.0,s),1)
    grade='A' if s>=75 else ('B' if s>=55 else 'C')
    return s,grade,'; '.join(why)

def rescore_all():
    """全库重算评分（联系方式补全后调用）。"""
    from core.memory.db import DB
    db=DB(); n=0
    for l in db.list_leads(limit=5000):
        s,g,_=score_lead(l)
        db.lead_update(l['norm'],score=s,grade=g); n+=1
    return n

if __name__=='__main__':
    print(rescore_all(),'leads rescored')
\n\n================================================================================\n# FILE [32/40]: core/tools/suppliers.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""供应商池：从海关提单的 shipper 字段透视"同行工厂"，生成 ImportYeti slug 供反向收割。"""
import re,sqlite3,time
from core.config import settings
SUF=re.compile(r'\b(inc|llc|ltd|co|corp|corporation|company|import|imports|export|exports|trading|trade|group|factory|industrial|industry|international|intl)\b\.?',re.I)
BAD=re.compile(r'on behalf of|freight|forwarder|logistics|express|cargo|customs broker|shipping',re.I)
def norm(s): return re.sub(r'[^a-z0-9一-鿿]+','',SUF.sub('',str(s or '').lower()))
def slugify(name):
    """公司名 → ImportYeti 风格 slug：Shenzhen Aroma Bay Trading Co., Ltd → shenzhen-aroma-bay"""
    s=SUF.sub(' ',str(name or '').lower())
    s=re.sub(r'[^a-z0-9一-鿿]+','-',s)
    s=re.sub(r'-{2,}','-',s).strip('-')
    return s
def pool(days=90,min_shipments=1):
    """近 N 天提单里的活跃供应商，附收割状态。返回 [{name,norm,slug,shipments,last_seen,harvested}]"""
    cutoff=time.time()-days*86400
    conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
    rows=conn.execute('SELECT shipper,COUNT(*) sh,MAX(ts) ls FROM customs_raw WHERE ts>=? AND shipper!="" GROUP BY shipper HAVING sh>=? ORDER BY sh DESC',(cutoff,min_shipments)).fetchall()
    done={r['supplier_norm']:r for r in conn.execute('SELECT * FROM suppliers')}
    conn.close()
    out=[]; seen=set()
    for r in rows:
        nm=r['shipper']
        if not nm or BAD.search(nm): continue
        n=norm(nm)
        if not n: continue
        d=done.get(n)
        seen.add(n)
        out.append({'name':nm,'norm':n,'slug':(d['slug'] if d and d['slug'] else slugify(nm)),
                    'shipments':r['sh'],'last_seen':r['ls'],'harvested':bool(d and d['harvested_at']),
                    'bol_fetched':(d['bol_fetched'] if d else 0),'via':'customs'})
    # 网页种子：ImportYeti 搜索卡片直接入池的同行工厂（slug 精确，未收割过的才放行）
    for n,d in done.items():
        if n in seen or d['harvested_at']: continue
        out.append({'name':d['name'],'norm':n,'slug':d['slug'],'shipments':d['shipments'] or 0,
                    'last_seen':d['last_seen'],'harvested':False,'bol_fetched':d['bol_fetched'] or 0,'via':'web'})
    out.sort(key=lambda x:-(x['shipments'] or 0))
    return out
def upsert_pool(entries):
    now=time.time()
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        for e in entries:
            c.execute('INSERT INTO suppliers(supplier_norm,name,slug,shipments,first_seen,last_seen,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(supplier_norm) DO UPDATE SET name=excluded.name,slug=excluded.slug,shipments=excluded.shipments,last_seen=excluded.last_seen,updated_at=excluded.updated_at',
                      (e['norm'],e['name'],e['slug'],e['shipments'],now,e['last_seen'],now))
def mark_harvested(supplier_norm,bol_count):
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('UPDATE suppliers SET harvested_at=?,bol_fetched=bol_fetched+?,updated_at=? WHERE supplier_norm=?',(time.time(),bol_count,time.time(),supplier_norm))
def log_harvest(task_id,slug,supplier,mode,status,items,note):
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('INSERT INTO harvest_log(task_id,slug,supplier,mode,status,items,note,created_at) VALUES(?,?,?,?,?,?,?,?)',(task_id,slug,supplier,mode,status,items,str(note or '')[:200],time.time()))
\n\n================================================================================\n# FILE [33/40]: core/tools/usitc.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""USITC 宏观情报节点：给开发信提供权威市场弹药。
三级降级：① data/usitc_notes.txt 手工情报（永远生效，推荐）② USITC_TOKEN API 尝试（实验性）③ 跳过不阻塞。"""
import json,sqlite3,time,urllib.request
from pathlib import Path
from core.config import settings
def _from_file():
    p=Path(settings.USITC_NOTES_FILE)
    if p.exists():
        try:
            raw=p.read_bytes()
            for enc in ('utf-8-sig','gb18030','utf-16'):
                try: t=raw.decode(enc); break
                except Exception: continue
            else: t=raw.decode('utf-8','ignore')
            t=t.replace('\x00','').strip()
            if t: return t
        except Exception: pass
    return ''
def _cached():
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH)
        r=conn.execute('SELECT payload,created_at FROM usitc_cache WHERE hs=? ORDER BY id DESC LIMIT 1',(settings.USITC_HS_CODE,)).fetchone()
        conn.close()
        if r and time.time()-r[1]<7*86400: return r[0]
    except Exception: pass
    return ''
def _from_api():
    """实验性：USITC DataWeb API（需在 dataweb.usitc.gov 免费注册拿 token）。任何异常都降级。"""
    if not settings.USITC_TOKEN: return ''
    cached=_cached()
    if cached: return cached
    payload={'dataType':'IMPORTS','dataSource':'GEN','timePeriod':'ANNUAL','years':['2024','2025'],
             'htsCodes':[settings.USITC_HS_CODE],'countries':['World','China'],'tradeDirection':'IMPORTS'}
    req=urllib.request.Request(settings.USITC_API_URL,data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+settings.USITC_TOKEN})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=30) as r:
        d=json.loads(r.read().decode('utf-8','ignore'))
    txt=json.dumps(d,ensure_ascii=False)
    if len(txt)>20:
        with sqlite3.connect(settings.DATABASE_PATH) as c:
            c.execute('INSERT INTO usitc_cache(hs,kind,payload,created_at) VALUES(?,?,?,?)',(settings.USITC_HS_CODE,'api',txt,time.time()))
        return txt
    return ''
def intel():
    """返回 {'ok':bool,'source':'file|api|none','text':str}。永不抛异常。"""
    try:
        t=_from_api()
        if t: return {'ok':True,'source':'api','text':t[:2000]}
    except Exception: pass
    t=_from_file()
    if t: return {'ok':True,'source':'file','text':t[:2000]}
    return {'ok':False,'source':'none','text':''}
\n\n================================================================================\n# FILE [34/40]: core/tools/web_ai.py\n================================================================================\n\n# -*- coding: utf-8 -*-
"""v16.5: 网页AI兜底通道（DeepSeek/ChatGPT 网页版，走用户已登录的 CDP 浏览器会话）。
定位：疑难问题的少量对话式兜底，不是批量工具。
安全闸：每日上限 WEBAI_DAILY_MAX + 调用间隔 WEBAI_MIN_INTERVAL 秒 + 仅开发/维护区客户触发。
用法：
  from core.tools import web_ai
  txt=web_ai.ask('把 Signature Brands 的官网/邮箱/电话/地址给我，输出JSON')
  python -m core.tools.web_ai diag deepseek "hello"   # 诊断"""
import re,time,json,sqlite3,random
import os as _os,sys as _sys
_sys.path.insert(0,_os.path.abspath(_os.path.join(_os.path.dirname(__file__),'../..')))
from core.config import settings

ENGINES={
 'deepseek':{'url':'https://chat.deepseek.com/',
             'inputs':['textarea#chat-input','textarea[placeholder]','textarea'],
             'answers':['.ds-markdown','.markdown','.message','[class*=markdown]']},
 'chatgpt':{'url':'https://chatgpt.com/',
            'inputs':['#prompt-textarea','div[contenteditable="true"]','textarea'],
            'answers':['[data-message-author-role="assistant"]','.markdown','[class*=markdown]']},
}
_last_call=[0.0]

def _quota_ok(engine):
    day=time.strftime('%Y-%m-%d')
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH)
        conn.execute('CREATE TABLE IF NOT EXISTS source_quota(source TEXT,day TEXT,count INT,UNIQUE(source,day))')
        r=conn.execute('SELECT count FROM source_quota WHERE source=? AND day=?',('webai_'+engine,day)).fetchone()
        used=r[0] if r else 0
        ok=used<int(settings.WEBAI_DAILY_MAX)
        conn.close(); return ok,used
    except Exception: return True,0

def _quota_inc(engine):
    day=time.strftime('%Y-%m-%d')
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH)
        conn.execute('INSERT INTO source_quota(source,day,count) VALUES(?,?,1) ON CONFLICT(source,day) DO UPDATE SET count=count+1',('webai_'+engine,day))
        conn.commit(); conn.close()
    except Exception: pass

def _cdp_alive(url):
    import urllib.request
    try:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url+'/json/version',timeout=4) as r: return r.status==200
    except Exception: return False

class WebAI:
    """挂 CDP 桌面浏览器（用户已登录 DeepSeek/GPT 的那个 Chrome）。"""
    def __init__(self):
        self._pw=None; self._br=None; self._pg=None
    def _launch(self):
        from playwright.sync_api import sync_playwright
        if not (settings.IY_WEB_CDP_ENABLED and _cdp_alive(settings.IY_WEB_CDP_URL)):
            raise RuntimeError('CDP 浏览器未就绪（先跑 start_chrome_debug.bat 并登录 AI 网站）')
        self._pw=sync_playwright().start()
        self._br=self._pw.chromium.connect_over_cdp(settings.IY_WEB_CDP_URL)
        ctx=self._br.contexts[0]
        self._pg=ctx.new_page()
    def close(self):
        try:
            if self._pg: self._pg.close()
            if self._pw: self._pw.stop()
        except Exception: pass
    def _first_visible(self,selectors):
        for sel in selectors:
            try:
                els=self._pg.query_selector_all(sel)
                for el in els:
                    if el.is_visible(): return el
            except Exception: continue
        return None
    def ask(self,question,engine=None,timeout=None):
        """开新会话问一个问题，等流式输出稳定后取回最后一条回答。失败返回 None。"""
        engine=engine or settings.WEBAI_ENGINE
        cfg=ENGINES.get(engine)
        if not cfg: print('[webai] 未知引擎:',engine); return None
        ok,used=_quota_ok(engine)
        if not ok:
            print('[webai] %s 已达今日上限(%d轮)，跳过'%(engine,settings.WEBAI_DAILY_MAX)); return None
        # 拟人节奏: 随机间隔
        import random as _rnd
        need=float(settings.WEBAI_MIN_INTERVAL)*_rnd.uniform(1.0,2.5)
        gap=time.time()-_last_call[0]
        if gap<need: time.sleep(need-gap)
        if not self._pg: self._launch()
        try:
            self._pg.goto(cfg['url'],timeout=60000,wait_until='domcontentloaded')
            self._pg.wait_for_timeout(5000)
            box=self._first_visible(cfg['inputs'])
            if not box:
                print('[webai] %s 未找到输入框（未登录或页面改版）'%engine); return None
            # 点击输入框并清空可能存在的旧内容
            box.click()
            self._pg.wait_for_timeout(500)
            try:
                box.fill('')
            except Exception:
                pass
            self._pg.wait_for_timeout(300)
            # 使用 insert_text 一次性输入完整问题，速度更快且不易中断
            # 限制 4000 字符，基本覆盖审核 prompt 长度
            text = question[:4000]
            self._pg.keyboard.insert_text(text)
            self._pg.wait_for_timeout(1200)  # 确保文本完全写入
            self._pg.keyboard.press('Enter')
            _last_call[0]=time.time()
            # 等回答出现并稳定（流式结束=连续2轮文本不变）
            deadline=time.time()+int(timeout or settings.WEBAI_TIMEOUT)
            last=''; stable=0; seen=False
            while time.time()<deadline:
                self._pg.wait_for_timeout(3000)
                el=self._first_visible(cfg['answers'])
                txt=''
                if el:
                    try:
                        els=self._pg.query_selector_all(cfg['answers'][0])
                        els=[e for e in els if e.is_visible()]
                        if els: txt=els[-1].inner_text().strip()
                    except Exception: pass
                if txt:
                    seen=True
                    if txt==last: stable+=1
                    else: stable=0
                    last=txt
                    if stable>=2 and len(txt)>10: break
            if not seen:
                print('[webai] %s 无回答（可能触发验证或限流）'%engine); return None
            _quota_inc(engine)
            print('[webai] %s 回答 %d 字（今日第%d/%d轮）'%(engine,len(last),used+1,settings.WEBAI_DAILY_MAX))
            return last
        except Exception as e:
            print('[webai] %s 异常: %s'%(engine,str(e)[:100]))
            return None

def solve(problem,context='',engines=None,timeout=None):
    """难题终结者：本地解决不了的核心问题，按引擎链逐个问，拿到第一个有效回答。"""
    engines=engines or [settings.WEBAI_ENGINE]+[e for e in ('deepseek','chatgpt') if e!=settings.WEBAI_ENGINE]
    prompt=(problem+'\n\n背景上下文：\n'+str(context)[:3000]) if context else problem
    w=WebAI()
    try:
        w._launch()
        for eng in engines:
            r=w.ask(prompt,engine=eng,timeout=timeout)
            if r and len(r.strip())>10:
                print('[webai] 难题已由 %s 解决(%d字)'%(eng,len(r)))
                return r
            print('[webai] %s 无有效回答, 换下一引擎'%eng)
        return None
    except Exception as e:
        print('[webai] solve failed:',str(e)[:100]); return None
    finally: w.close()

def ask(question,engine=None,timeout=None):
    """一次性入口：自动开/关浏览器页。"""
    w=WebAI()
    try:
        w._launch()
        return w.ask(question,engine=engine,timeout=timeout)
    except Exception as e:
        print('[webai] failed:',str(e)[:100]); return None
    finally: w.close()

if __name__=='__main__':
    import sys
    if len(sys.argv)>2 and sys.argv[1]=='diag':
        eng=sys.argv[2]
        q=sys.argv[3] if len(sys.argv)>3 else '请只回答两个字：收到'
        print('== 网页AI诊断:',eng,'==')
        print('引擎URL:',ENGINES.get(eng,{}).get('url'))
        print('每日上限:',settings.WEBAI_DAILY_MAX,'| 间隔:',settings.WEBAI_MIN_INTERVAL,'s')
        r=ask(q,engine=eng,timeout=90)
        print('回答:',(r or '(无)')[:200])
    else:
        print('用法: python -m core.tools.web_ai diag deepseek "问题"')
\n\n================================================================================\n# FILE [35/40]: core/utils/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [36/40]: core/utils/jsonutil.py\n================================================================================\n\nimport json,re
def j(text):
    if not text: return None
    m=re.search(r'\{.*\}',str(text),re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None
def jl(text):
    if not text: return []
    m=re.search(r'\[.*\]',str(text),re.S)
    if not m: return []
    try:
        x=json.loads(m.group(0)); return x if isinstance(x,list) else []
    except Exception: return []
\n\n================================================================================\n# FILE [37/40]: core/webui/__init__.py\n================================================================================\n\n\n\n================================================================================\n# FILE [38/40]: core/webui/app.py\n================================================================================\n\nimport json,re,sqlite3,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from core.config import settings
from core.system import PSVSystem
SYS=PSVSystem()

def _w(wf,b):
    try: wf.write(b)
    except (BrokenPipeError,ConnectionResetError): pass  # 浏览器先断开，静默忽略

HTML='''<!doctype html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>PSV __VER__ ExpertGraph</title>
<style>
:root{--bg:#0a0c10;--bg2:#0d1117;--bd:#21262d;--fg:#c9d1d9;--mut:#8b949e;--grn:#3fb950;--amb:#d29922;--red:#f85149;--blu:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.6 "Cascadia Mono",Consolas,"Courier New",monospace;background-image:linear-gradient(var(--bd) 1px,transparent 1px),linear-gradient(90deg,var(--bd) 1px,transparent 1px);background-size:26px 26px}
header{display:flex;gap:14px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--bd);background:var(--bg2);flex-wrap:wrap}
.logo{font-size:15px;letter-spacing:2px}.logo b{color:var(--grn)}
.logo span{color:var(--mut);font-size:11px;letter-spacing:1px}
input,button{background:var(--bg);color:var(--fg);border:1px solid var(--bd);padding:6px 10px;font:inherit}
input:focus{border-color:var(--blu);outline:none}
button{cursor:pointer;border-color:var(--grn);color:var(--grn)}
button:hover{background:var(--grn);color:#000}
.tab{cursor:pointer;color:var(--mut);padding:4px 12px;border:1px solid var(--bd)}
.tab.on{color:var(--grn);border-color:var(--grn)}
#hint{color:var(--mut);font-size:11px}
.wrap{display:grid;grid-template-columns:300px 1fr;gap:12px;padding:12px 16px;align-items:start}
aside,.pane{border:1px solid var(--bd);background:var(--bg2);padding:10px}
.pt{color:var(--mut);letter-spacing:2px;font-size:11px;border-bottom:1px solid var(--bd);padding-bottom:6px;margin-bottom:8px}
.pt b{color:var(--amb);font-weight:400;float:right;letter-spacing:1px}
.ti{padding:6px 8px;border-bottom:1px solid var(--bd);cursor:pointer;word-break:break-all}
.ti:hover{background:var(--bg)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--mut)}
.dot.done{background:var(--grn)}.dot.failed,.dot.failed_gate,.dot.error{background:var(--red)}
.dot.running{background:var(--amb);animation:blink 1s infinite}
.dot.queued{background:var(--blu)}
@keyframes blink{50%{opacity:.25}}
.mut{color:var(--mut)}.err{color:var(--red)}.warn{color:var(--amb)}
.badge{padding:2px 10px;border:1px solid var(--bd);letter-spacing:1px}
.b-done{color:var(--grn);border-color:var(--grn)}.b-running{color:var(--amb);border-color:var(--amb)}
.b-failed,.b-failed_gate,.b-error{color:var(--red);border-color:var(--red)}.b-queued{color:var(--blu);border-color:var(--blu)}
.meta{color:var(--mut);font-size:11px;margin:4px 0 8px}
.sec{color:var(--amb);letter-spacing:2px;margin:20px 0 10px;border-bottom:1px dashed var(--bd);padding-bottom:5px}
.sec .exbtn{float:right;letter-spacing:0}
.exbtn{display:inline-block;border:1px solid var(--grn);color:var(--grn);padding:2px 12px;text-decoration:none;margin-left:8px}
.exbtn:hover{background:var(--grn);color:#000}
.stg{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}
.snode{border:1px solid var(--bd);border-left:3px solid var(--mut);padding:6px 8px;cursor:pointer;background:var(--bg);min-height:58px}
.snode:hover{border-color:var(--blu)}
.snode .sn{font-weight:700;font-size:12px}
.snode .st{position:absolute;margin:-4px 0 0 0;color:var(--mut);font-size:10px}
.snode .sc{color:var(--mut);font-size:11px}
.snode .sd{color:var(--blu);font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.snode.ok{border-left-color:var(--grn)}
.snode.no{border-left-color:var(--red)}
.snode.run{border-left-color:var(--amb);animation:blink 1.2s infinite}
.snode.skip{opacity:.45;border-left-style:dashed}
.snode.refl{border-left-color:var(--amb);border-top-style:dashed;border-right-style:dashed;border-bottom-style:dashed}
.snode.sel{outline:1px solid var(--blu)}
.flowleg{color:var(--mut);font-size:11px;margin-top:6px}
.reflstrip{margin-top:8px}
.rs{border-left:2px dashed var(--amb);padding:4px 10px;margin:4px 0;color:var(--amb);font-size:12px}
.rs span{color:var(--mut)}
.xdetail{border:1px solid var(--blu);background:var(--bg);padding:10px;margin-top:10px}
.xrole{color:var(--mut);margin-left:10px}
.xv{float:right;padding:0 8px;border:1px solid}
.xv.pass{color:var(--grn)}.xv.fail{color:var(--red)}.xv.degraded{color:var(--amb)}
.crit{margin:3px 0}
.ck.y{color:var(--grn);margin-right:6px}.ck.n{color:var(--red);margin-right:6px}
.cby{color:var(--mut);font-size:10px;border:1px solid var(--bd);padding:0 4px;margin-left:6px}
.think{border-left:2px solid var(--grn);padding:4px 10px;margin:8px 0;color:var(--fg);background:var(--bg2)}
.xnotes{color:var(--blu);margin:4px 0}
.card{border:1px solid var(--bd);background:var(--bg);padding:8px 10px;margin:8px 0}
.card.err{border-color:var(--red)}
.reflcard{border-left:3px solid var(--amb)}
table{border-collapse:collapse;width:100%;margin-top:6px}
th,td{border:1px solid var(--bd);padding:3px 8px;text-align:left;font-weight:400;font-size:12px}
th{color:var(--mut)}
.s5{color:var(--grn)}.s4{color:var(--blu)}.s1{color:var(--mut)}
.y{color:var(--grn)}.n{color:var(--red)}
pre{white-space:pre-wrap;word-break:break-all;background:var(--bg2);padding:8px;border:1px solid var(--bd);font-size:11px}
details{margin:8px 0}summary{cursor:pointer;color:var(--amb);letter-spacing:1px}
.lcard{border:1px solid var(--bd);border-left:3px solid var(--grn);background:var(--bg);padding:10px 12px;margin:10px 0}
.lco{font-weight:700;color:var(--grn)}
.lsub{color:var(--blu);margin:4px 0}
.lbody{white-space:pre-wrap;color:var(--fg);border-top:1px dashed var(--bd);padding-top:6px;margin-top:4px}
.cp{float:right;font-size:11px;padding:1px 10px}
.pcard{border:1px solid var(--bd);background:var(--bg);padding:8px 12px;margin:8px 0}
.kv{margin:2px 0}.kv b{color:var(--blu);font-weight:400;margin-right:8px}
.chip{cursor:pointer;border:1px solid var(--bd);color:var(--mut);padding:1px 10px;margin-right:4px;font-size:11px}
.chip.on{color:var(--grn);border-color:var(--grn)}
.gd{display:inline-block;padding:0 6px;font-size:11px;border:1px solid;font-weight:700}
.gdA{color:var(--grn);border-color:var(--grn)}.gdB{color:var(--amb);border-color:var(--amb)}.gdC{color:var(--mut);border-color:var(--bd)}
.aub{display:inline-block;padding:0 6px;font-size:11px;border:1px solid;font-weight:700}
.aup{color:var(--grn);border-color:var(--grn)}.aus{color:var(--amb);border-color:var(--amb)}.auf{color:var(--red);border-color:var(--red)}.au0{color:var(--mut);border-color:var(--bd)}
.zmv{font-size:10px;padding:0 6px;margin-left:4px;border-color:var(--blu);color:var(--blu)}
.zmv:hover{background:var(--blu);color:#000}
.zl{display:inline-block;padding:0 6px;font-size:10px;border:1px solid var(--bd);color:var(--mut)}
.zl.dev{color:var(--amb);border-color:var(--amb)}.zl.maint{color:var(--grn);border-color:var(--grn)}
.commwrap{display:grid;grid-template-columns:290px 1fr;gap:10px}
.commleft{border:1px solid var(--bd);background:var(--bg);padding:8px;max-height:70vh;overflow:auto}
.commright{border:1px solid var(--bd);background:var(--bg);padding:10px;min-height:300px}
.cli{padding:6px 8px;border-bottom:1px solid var(--bd);cursor:pointer}
.cli:hover{background:var(--bg2)}
.cli.sel{background:var(--bg2);border-left:3px solid var(--grn)}
.ccard{border:1px solid var(--bd);background:var(--bg2);padding:8px 12px;margin-bottom:10px}
.msg{border:1px solid var(--bd);padding:6px 10px;margin:6px 0;white-space:pre-wrap}
.msg.in{border-left:3px solid var(--blu)}
.msg.out{border-left:3px solid var(--grn)}
.msg.draft{border-left:3px solid var(--amb);border-top-style:dashed;border-right-style:dashed;border-bottom-style:dashed}
.mh{font-size:10px;color:var(--mut);margin-bottom:3px}
textarea{background:var(--bg);color:var(--fg);border:1px solid var(--bd);padding:6px 10px;font:inherit;width:100%;min-height:64px}
select{background:var(--bg);color:var(--fg);border:1px solid var(--bd);padding:4px 8px;font:inherit}
.cbtn{padding:4px 12px;margin-right:6px;margin-top:6px}
.mailc{color:var(--grn)}
.ok3{color:var(--grn);font-weight:700;cursor:help}
.tag{display:inline-block;border:1px solid var(--bd);padding:0 5px;margin-right:3px;font-size:10px}
.tag.Top{color:var(--grn);border-color:var(--grn)}.tag.New{color:var(--blu);border-color:var(--blu)}.tag.FG{color:var(--amb);border-color:var(--amb)}
.kd{display:inline-block;padding:0 6px;font-size:10px;border:1px solid}
.kd.importer{color:var(--grn)}.kd.supplier{color:var(--blu)}
.sg.birthday{color:var(--grn)}.sg.candle{color:var(--blu)}.sg.none{color:var(--mut)}
.stat4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.stat{border:1px solid var(--bd);background:var(--bg);padding:12px}
.stat b{font-size:26px;color:var(--grn);display:block}
.bars div{margin:3px 0}
.bar{height:10px;background:var(--grn);display:inline-block}
.bar.no{background:var(--red)}
</style>
<body>
<header>
<div class=logo>PSV <b>__VER__</b> EXPERTGRAPH <span>EXPERT REVIEW / REFLECT LOOP / WEB HARVEST</span></div>
<form id=f style="display:flex;gap:8px;flex-wrap:wrap">
<input id=req size=22 value="找美国生日蜡烛进口商">
<input id=ind size=16 value="birthday candles">
<input id=n size=3 value=20>
<button id=go>RUN</button>
<span id=hint></span>
</form>
<div><span class="tab on" id=tab1>[ 专家工作台 ]</span> <span class=tab id=tab3>[ 客户库 ]</span> <span class=tab id=tab4>[ 通信 ]</span> <span class=tab id=tab2>[ 数据仪表盘 ]</span></div>
</header>
<div class=wrap>
<aside><div class=pt>最近任务 <b>TASKS</b></div><div id=tasks></div></aside>
<main>
<div id=page1 class=page><div class=pane><div class=pt>任务终端 <b>TERMINAL</b></div><div id=out><span class=mut>选择左侧任务查看，或点击 RUN 开始新任务</span></div></div></div>
<div id=page3 class=page style="display:none"><div class=pane><div class=pt>客户库 <b>LEADS</b><span id=leadstats class=mut style="float:right"></span></div>
<div style="margin-bottom:8px">
<span class="chip on" data-k="kind" data-v="">全部</span>
<span class=chip data-k="kind" data-v="importer">进口商</span>
<span class=chip data-k="kind" data-v="supplier">供应商</span>
<span class=chip style="margin-left:14px" data-k="segment" data-v="">全部品类</span>
<span class=chip data-k="segment" data-v="birthday">生日蜡烛</span>
<span class=chip data-k="segment" data-v="candle">蜡烛</span>
<span class=chip style="margin-left:14px" data-k="zone" data-v="">全部分区</span>
<span class=chip data-k="zone" data-v="pool">线索池</span>
<span class=chip data-k="zone" data-v="dev">开发区</span>
<span class=chip data-k="zone" data-v="maint">维护区</span>
<input id=leadq size=14 placeholder=搜公司名 style="margin-left:14px">
<a class=exbtn id=leadcsv href="/api/leads.csv" target=_blank>[ 导出 CSV ]</a>
<button id=seqbtn style="padding:2px 12px;margin-left:8px;border-color:var(--amb);color:var(--amb)">[ 启动开发信序列 ]</button><span id=seqst class=mut style="font-size:11px;margin-left:6px"></span>
<button id=enrichbtn style="padding:2px 12px;margin-left:8px">[ 补全开发/维护区 ]</button><button id=wadiagbtn title="检查AI浏览器/登录态，不发问题不耗额度" style="padding:2px 12px;margin-left:4px;border-color:var(--amb);color:var(--amb)">[ 诊断网页AI ]</button><button id=expandbtn style="padding:2px 12px;margin-left:8px;border-color:var(--amb);color:var(--amb)">[ 网络扩张 ]</button><span id=enrichst class=mut style="font-size:11px;margin-left:6px"></span>
</div>
<div id=leads></div></div></div>

<div id=page4 class=page style="display:none"><div class=pane><div class=pt>通信 <b>COMM · 大模型待机</b><span id=commhint class=mut style="float:right"></span></div>
<div class=commwrap>
<div class=commleft>
<div style="margin-bottom:6px"><span class="chip zchip on" data-z="dev">开发区</span><span class="chip zchip" data-z="maint">维护区</span></div>
<div id=commlist><span class=mut>loading...</span></div>
</div>
<div class=commright id=commright><span class=mut>从左侧选择客户。<br>把客户回复粘贴进输入框，大模型结合该客户画像与往来记录即时起草回信（邮件 / WhatsApp）。</span></div>
</div></div></div>
<div id=page2 class=page style="display:none"><div class=pane><div class=pt>数据仪表盘 <b>DASHBOARD</b></div><div id=dash><span class=mut>loading...</span></div></div></div>
</main>
</div>
<script>
let tid=null,timer=null,selNode=null,LAST=null;
const out=document.getElementById("out"),tasks=document.getElementById("tasks"),dash=document.getElementById("dash"),
req=document.getElementById("req"),ind=document.getElementById("ind"),n=document.getElementById("n"),
go=document.getElementById("go"),hint=document.getElementById("hint");
const CANON=["ICP","STRATEGY","A_COLLECT","SUPPLIER_MINING","REVERSE_HARVEST","CLEAN_VERIFY","A_GATE","USITC","RANK","CONTACT","B_PROFILE","C_ANALYSIS","D_OUTREACH"];
const CN={ICP:"画像契约：定验收标准",STRATEGY:"搜索策略：生成查询词",A_COLLECT:"采集：搜候选公司",SUPPLIER_MINING:"挖厂：沉淀同行工厂池",REVERSE_HARVEST:"收割：翻工厂提单找买家",CLEAN_VERIFY:"清洗：去重剔垃圾",A_GATE:"闸门：硬证据审判",USITC:"情报：宏观数据(可选)",RANK:"排序：证据强度优先",CONTACT:"联系方式：官网/邮箱/评分",B_PROFILE:"画像：逐家建档",C_ANALYSIS:"分析：采购机会",D_OUTREACH:"开发信：英文触达",REFLECT:"复盘：诊断+新处方"};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function showTab(k){
  for(let i of [1,2,3,4]){document.getElementById("page"+i).style.display=(i===k?"block":"none");document.getElementById("tab"+i).className="tab"+(i===k?" on":"")}
  if(k===2)loadDash();
  if(k===3)loadLeads();
  if(k===4)loadComm();
}
document.getElementById("tab1").onclick=function(){showTab(1)};
document.getElementById("tab2").onclick=function(){showTab(2)};
document.getElementById("tab3").onclick=function(){showTab(3)};
document.getElementById("tab4").onclick=function(){showTab(4)};
let LFILT={kind:"",segment:"",zone:""};
function leadQS(){
  let p=[];if(LFILT.kind)p.push("kind="+LFILT.kind);if(LFILT.segment)p.push("segment="+LFILT.segment);if(LFILT.zone)p.push("zone="+LFILT.zone);
  let q=document.getElementById("leadq").value.trim();if(q)p.push("q="+encodeURIComponent(q));
  return p.length?"?"+p.join("&"):"";
}
async function loadLeads(){
  let qs=leadQS();
  document.getElementById("leadcsv").href="/api/leads.csv"+qs;
  let d=await (await fetch("/api/leads"+qs)).json();
  let st=d.stats||{};
  document.getElementById("leadstats").textContent="共 "+(st.total||0)+" · 进口商 "+(st.importers||0)+" · 供应商 "+(st.suppliers||0)+" · 生日蜡烛信号 "+(st.birthday||0);
  let rows=d.leads||[];
  let h="<table><tr><th>#</th><th>公司</th><th>国家</th><th>类型</th><th>品类</th><th>提单</th><th>评分</th><th>联系方式</th><th>标签</th><th>分区</th><th>来源</th></tr>";
  rows.forEach((r,i)=>{
    let tags=String(r.tags||"").split(",").filter(t=>t).map(t=>"<span class='tag "+(t==="Fast Growing"?"FG":t)+"'>"+(t==="Fast Growing"?"成长":esc(t))+"</span>").join("");
    let seg=r.segment==="birthday"?"<span class='sg birthday'>生日蜡烛</span>":(r.segment==="candle"?"<span class='sg candle'>蜡烛</span>":"<span class='sg none'>-</span>");
    let kd=r.kind==="importer"?"<span class='kd importer'>进口商</span>":(r.kind==="supplier"?"<span class='kd supplier'>供应商</span>":esc(r.kind||""));
    let gd=r.grade?"<span class='gd gd"+r.grade+"'>"+r.grade+"</span> <span class=mut>"+(r.score==null?"":r.score)+"</span>":"<span class=mut>-</span>";
    let ct="";
    if(r.emails)ct+="<span class=mailc title='"+esc(r.emails)+"'>邮</span> ";
    if(r.phones)ct+="<span class=mailc title='"+esc(r.phones)+"'>话</span> ";
    if(r.website)ct+="<a href='"+esc(r.website)+"' target=_blank style='color:var(--blu)'>网</a>";
    if(r.emails&&r.phones&&r.website)ct+=" <span class=ok3 title='官网/邮箱/电话三件套齐全'>✓</span>";
    if(!ct)ct="<span class=mut>-</span>";
    let zn=r.zone||"pool";
    let zl=zn==="dev"?"<span class='zl dev'>开发</span>":(zn==="maint"?"<span class='zl maint'>维护</span>":"<span class=zl>线索池</span>");
    let mv="";
    if(zn==="pool"&&r.kind==="importer")mv="<button class=zmv data-n='"+esc(r.norm)+"' data-z='dev'>→开发</button>";
    if(zn==="dev")mv="<button class=zmv data-n='"+esc(r.norm)+"' data-z='maint'>→维护</button><button class=zmv data-n='"+esc(r.norm)+"' data-z='pool'>→池</button>";
    if(zn==="maint")mv="<button class=zmv data-n='"+esc(r.norm)+"' data-z='dev'>→开发</button>";
    h+="<tr><td>"+(i+1)+"</td><td>"+esc(r.name)+"</td><td>"+esc(r.country)+"</td><td>"+kd+"</td><td>"+seg+"</td><td>"+esc(r.shipments||"")+"</td><td>"+gd+"</td><td>"+ct+"</td><td>"+tags+"</td><td>"+zl+mv+"</td><td class=mut>"+esc(r.source)+"</td></tr>";
  });
  h+="</table>";
  if(!rows.length)h="<span class=mut>客户库为空——跑一轮任务后这里会累积标准化档案</span>";
  document.getElementById("leads").innerHTML=h;
  document.querySelectorAll(".zmv").forEach(el=>el.onclick=async function(){
    await fetch("/api/lead/zone",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:el.dataset.n,zone:el.dataset.z})});
    loadLeads();
  });
}
document.querySelectorAll(".chip").forEach(el=>el.onclick=function(){
  let k=el.dataset.k,v=el.dataset.v;
  if(k==="zone"&&el.classList.contains("zchip")){
    COMMZ=v;
    document.querySelectorAll(".zchip").forEach(c2=>{c2.className="chip zchip"+(c2.dataset.z===COMMZ?" on":"")});
    loadComm(); return;
  }
  if(k&&LFILT[k]!==undefined){LFILT[k]=(LFILT[k]===v?"":v)}
  ["kind","segment","zone"].forEach(kk=>{
    document.querySelectorAll(".chip").forEach(c2=>{
      if(c2.dataset.k===kk&&!c2.classList.contains("zchip"))c2.className="chip"+(((c2.dataset.v===""&&!LFILT[kk])||(c2.dataset.v===LFILT[kk]&&LFILT[kk]!==""))?" on":"");
    });
  });
  loadLeads();
});
document.getElementById("leadq").oninput=function(){loadLeads()};

let COMMZ="dev",CUR=null;
const ZN={pool:"线索池",dev:"开发区",maint:"维护区"};
const TS={new:"新线索",contacted:"已触达",replied:"已回复",sample:"寄样",deal:"成交",paused:"搁置"};
function gdBadge(r){return r.grade?"<span class='gd gd"+r.grade+"'>"+r.grade+"</span>":""}
async function loadComm(){
  let d=await (await fetch("/api/leads?zone="+COMMZ+"&kind=importer")).json();
  let rows=(d.leads||[]).sort((a,b)=>((b.score||0)-(a.score||0)));
  let h="";
  rows.forEach(r=>{
    h+="<div class='cli"+(CUR===r.norm?" sel":"")+"' data-n='"+esc(r.norm)+"'>"+gdBadge(r)+" <b>"+esc(r.name)+"</b> <span class=mut>"+(r.score==null?"":r.score)+"</span><br><span class=mut>"+esc(TS[r.touch_status]||"新线索")+" · "+esc(r.country||"")+"</span></div>";
  });
  if(!rows.length)h="<span class=mut>"+ZN[COMMZ]+"为空——到客户库把进口商移进来</span>";
  document.getElementById("commlist").innerHTML=h;
  document.querySelectorAll(".cli").forEach(el=>el.onclick=function(){pickComm(el.dataset.n)});
}
async function pickComm(norm){
  CUR=norm;
  document.querySelectorAll(".cli").forEach(el=>{el.className="cli"+(el.dataset.n===norm?" sel":"")});
  let d=await (await fetch("/api/lead/"+norm)).json();
  renderWs(d);
}
let LASTLEAD=null;
function auParse(r){try{return JSON.parse(r.audit||"null")}catch(e){return null}}
function auBadge(r){
  let a=auParse(r);
  if(!a||!a.verdict)return "<span class='aub au0'>未审核</span>";
  if(a.verdict==="pass")return "<span class='aub aup'>审核通过</span>";
  if(a.verdict==="suspect")return "<span class='aub aus'>有疑点</span>";
  return "<span class='aub auf'>未通过</span>";
}
function auDetail(r){
  let a=auParse(r);
  if(!a)return "<span class=mut>还没有审核记录——点[审核资料]跑一次（机器校验+GPT复核）</span>";
  let F={website:"官网",emails:"邮箱",phones:"电话",address:"地址"};
  let ST={ok:"✓ 通过",suspect:"! 疑点",fail:"✗ 未通过",missing:"- 缺失"};
  let h="";
  ["website","emails","phones","address"].forEach(function(k){
    let f=(a.fields||{})[k]; if(!f)return;
    h+="<div>"+F[k]+"："+(ST[f.st]||f.st)+((f.why||[]).length?" <span class=mut>— "+esc(f.why.join("；"))+"</span>":"")+"</div>";
  });
  if(a.ai&&a.ai.ran){
    h+="<div>GPT复核：已执行"+(a.ai.notes?" <span class=mut>— "+esc(a.ai.notes)+"</span>":"")+"</div>";
    if(a.ai.suggest)h+="<div class=warn>GPT建议修正（不会自动写入，确认后用[改资料]改）："+esc(JSON.stringify(a.ai.suggest))+"</div>";
  }else h+="<div class=mut>GPT复核：未执行（额度/通道/配置原因），以上为机器校验结果</div>";
  h+="<div class=mut>"+esc(a.day||"")+"</div>";
  return h;
}
function auditWarn(r){
  let a=auParse(r);
  if(!a)return "";
  let rs=((a.machine_reasons||[]).slice(0,3)).join("；");
  if(a.verdict==="fail")return "该客户资料审核未通过："+rs+"。确定仍要操作吗？（建议先[改资料]或[重补资料]）";
  if(a.verdict==="suspect")return "该客户资料有疑点："+rs+"。确定继续吗？";
  return "";
}
function renderWs(d){
  let r=d.lead||{},msgs=d.messages||[];
  LASTLEAD=r;
  let digits=String(r.phones||"").split("").filter(c=>"0123456789".indexOf(c)>=0).join("");
  let firstMail=String(r.emails||"").split(",")[0]||"";
  let h="<div class=ccard>";
  h+="<div>"+gdBadge(r)+" "+auBadge(r)+" <b style='font-size:14px'>"+esc(r.name)+"</b> <span class=mut>"+esc(r.country||"")+" · "+esc(ZN[r.zone]||"线索池")+" · "+esc(TS[r.touch_status]||"新线索")+"</span></div>";
  h+="<div class=meta>提单 "+esc(r.shipments||"-")+" · 品类 "+(r.segment==="birthday"?"生日蜡烛":(r.segment==="candle"?"蜡烛":"-"))+" · 最近出货 "+esc(r.last_shipment||"-")+"</div>";
  h+="<div class=kv><b>官网</b>"+(r.website?"<a href='"+esc(r.website)+"' target=_blank style='color:var(--blu)'>"+esc(r.website)+"</a>":"<span class=mut>-</span>")+"</div>";
  h+="<div class=kv><b>邮箱</b><span>"+(r.emails?esc(r.emails):"<span class=mut>-</span>")+"</span></div>";
  h+="<div class=kv><b>电话</b><span>"+(r.phones?esc(r.phones):"<span class=mut>-</span>")+"</span></div>";
  h+="<div class=kv><b>地址</b><span>"+(r.address?esc(r.address):"<span class=mut>-</span>")+"</span></div>";
  h+="<div class=kv><b>审核</b><span>"+auBadge(r)+" <a id=autog style='color:var(--blu);font-size:11px;cursor:pointer'>[详情]</a></span></div>";
  h+="<div id=aurep style='display:none;padding:2px 0 6px 14px;font-size:12px;line-height:1.7'>"+auDetail(r)+"</div>";
  if(r.contact_person)h+="<div class=kv><b>联系人</b><span>"+esc(r.contact_person)+"</span></div>";
  if(r.profile)h+="<div class=kv><b>画像</b><span class=mut>"+esc(r.profile)+"</span></div>";
  h+="<div style='margin-top:6px'>";
  if(firstMail)h+="<a class=exbtn href='mailto:"+esc(firstMail)+"?subject="+encodeURIComponent("Candle supply - factory direct")+"' >[ 邮件客户端 ]</a> ";
  if(digits)h+="<a class=exbtn href='https://wa.me/"+digits+"' target=_blank>[ WhatsApp ]</a> ";
  h+="<select id=touchst>"+["new","contacted","replied","sample","deal","paused"].map(k=>"<option value='"+k+"'"+((r.touch_status||"new")===k?" selected":"")+">"+TS[k]+"</option>").join("")+"</select>";
  h+=" <button class=cbtn id=reenrich title='强制重新补全该客户的官网/邮箱/电话（AI直连DeepSeek/GPT）'>[ 重补资料 ]</button>";
  h+=" <button class=cbtn id=auditbtn title='机器多重校验+GPT对话复核官网/邮箱/电话/地址'>[ 审核资料 ]</button>";
  h+="</div></div>";
  h+="<div class=pt>往来时间线 <b>TIMELINE</b></div><div id=commtl>";
  msgs.forEach(m=>{
    let cls=m.draft?"draft":(m.direction==="in"?"in":"out");
    let who=m.draft?"AI草稿·"+(m.channel==="whatsapp"?"WhatsApp":"邮件"):(m.direction==="in"?"客户·":"我方·")+esc(m.channel||"");
    let sentb=(m.content&&m.content.indexOf("[待发送]")===0)?" <button class='msent cbtn' data-mid='"+m.id+"' style='float:none;margin:0 0 0 8px;padding:0 8px;border-color:var(--amb);color:var(--amb)'>确认已发</button>":"";
    h+="<div class='msg "+cls+"'><div class=mh>"+who+" · "+esc(m.day||"")+(m.draft?" <button class='cp cbtn' data-mid='"+m.id+"' style='float:none;margin:0 0 0 8px;padding:0 8px'>复制</button> <button class='mdel cbtn' data-mid='"+m.id+"' style='float:none;margin:0;padding:0 8px;border-color:var(--red);color:var(--red)'>删</button>":"")+sentb+"</div><div class=mbody>"+esc(m.content)+"</div></div>";
  });
  if(!msgs.length)h+="<span class=mut>还没有往来记录</span>";
  h+="</div>";
  h+="<div class=pt style='margin-top:10px'>起草 / 记录 <b>AI</b></div>";
  h+="<textarea id=commin placeholder='粘贴客户的回复，或写你的意图（如：他问了MOQ和价格，帮我回一封报价跟进信）'></textarea>";
  h+="<div><button class=cbtn id=draftmail>[ 生成邮件 ]</button><button class=cbtn id=draftwa>[ 生成WhatsApp ]</button><button class=cbtn id=sendmail title='在AI浏览器打开Gmail/Outlook写信页，收件人/标题/正文已预填，检查后手动发送' >[ 邮箱发送 ]</button><button class=cbtn id=smtpsend title='需.env配置SMTP授权码；新邮箱每天不超过20封' style='border-color:var(--amb);color:var(--amb)'>[ SMTP直发 ]</button><button class=cbtn id=loginb>[ 记为客户回复 ]</button><button class=cbtn id=logoutb>[ 记为我方已发 ]</button><span id=commst class=mut style='font-size:11px'></span></div>";
  document.getElementById("commright").innerHTML=h;
  document.getElementById("reenrich").onclick=async function(){
    let st=document.getElementById("commst");
    st.textContent="重补资料中（AI直连，约1-2分钟）...";
    await fetch("/api/lead/reenrich",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR})});
    let t=setInterval(async function(){
      let d=await (await fetch("/api/enrich_status")).json();
      if(d.log)st.textContent=d.log;
      if(!d.running){clearInterval(t);pickComm(CUR)}
    },6000);
  };
  document.getElementById("autog").onclick=function(){
    let p=document.getElementById("aurep");
    p.style.display=p.style.display==="none"?"block":"none";
  };
  document.getElementById("auditbtn").onclick=async function(){
    let st=document.getElementById("commst");
    st.textContent="资料审核中（机器校验→GPT复核，约1-2分钟）...";
    await fetch("/api/lead/audit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR})});
    let t=setInterval(async function(){
      let d=await (await fetch("/api/enrich_status")).json();
      if(d.log)st.textContent=d.log;
      if(!d.running){clearInterval(t);pickComm(CUR)}
    },6000);
  };
  document.getElementById("touchst").onchange=async function(){
    await fetch("/api/lead/status",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR,touch_status:this.value})});
    loadComm();
  };
  document.getElementById("loginb").onclick=function(){commLog("in")};
  document.getElementById("logoutb").onclick=function(){commLog("out")};
  document.getElementById("draftmail").onclick=function(){commDraft("email")};
  document.getElementById("sendmail").onclick=function(){commSend("compose")};
  document.getElementById("smtpsend").onclick=function(){commSend("smtp")};
  document.getElementById("draftwa").onclick=function(){commDraft("whatsapp")};
  document.querySelectorAll(".mdel").forEach(el=>el.onclick=async function(){
    if(!confirm("删除这条草稿？"))return;
    await fetch("/api/comm/delmsg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mid:el.getAttribute("data-mid")})});
    pickComm(CUR);
  });
  document.querySelectorAll(".msent").forEach(el=>el.onclick=async function(){
    await fetch("/api/comm/marksent",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mid:el.getAttribute("data-mid")})});
    pickComm(CUR);
  });
  document.querySelectorAll(".cp").forEach(el=>el.onclick=function(){
    let b=el.parentElement.parentElement.querySelector(".mbody");
    if(b&&navigator.clipboard)navigator.clipboard.writeText(b.textContent);
    el.textContent="已复制";
  });
}
async function commLog(dir){
  let t=document.getElementById("commin").value.trim();
  if(!t){document.getElementById("commst").textContent="先输入内容";return}
  await fetch("/api/comm/log",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR,direction:dir,channel:dir==="in"?"email":"manual",content:t})});
  document.getElementById("commin").value="";
  pickComm(CUR);loadComm();
}
async function commSend(via){
  let w=auditWarn(LASTLEAD||{});
  if(w&&!confirm(w))return;
  document.getElementById("commst").textContent=via==="smtp"?"SMTP发送中...":"正在打开你的邮箱写信页...";
  let d=await (await fetch("/api/comm/sendmail",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR,via:via})})).json();
  if(d.error){document.getElementById("commst").textContent="发送失败："+d.error;alert(d.error);return}
  document.getElementById("commst").textContent=d.note||"";
  pickComm(CUR);
}
async function commDraft(mode){
  let w=auditWarn(LASTLEAD||{});
  if(w&&!confirm(w))return;
  let hint=document.getElementById("commin").value.trim();
  document.getElementById("commst").textContent="大模型起草中（本地70B，约1-3分钟）...";
  let d=await (await fetch("/api/comm/draft",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({norm:CUR,mode:mode,hint:hint})})).json();
  document.getElementById("commst").textContent=d.text?"起草完成":"起草失败："+(d.error||"LLM离线");
  document.getElementById("commin").value="";
  pickComm(CUR);
}
document.getElementById("seqbtn").onclick=async function(){
  document.getElementById("seqst").textContent="开发信序列运行中...";
  await fetch("/api/email_sequence/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({zone:"dev",max:20})});
  pollSeq();
};
async function pollSeq(){
  let d=await (await fetch("/api/email_sequence/status")).json();
  document.getElementById("seqst").textContent=d.log||"";
  if(d.running)setTimeout(pollSeq,5000);
}
document.getElementById("enrichbtn").onclick=async function(){
  document.getElementById("enrichst").textContent="后台补全中（每家约20秒）...";
  await fetch("/api/leads/enrich",{method:"POST"});
  pollEnrich();
};
document.getElementById("wadiagbtn").onclick=async function(){
  let st=document.getElementById("enrichst");
  st.textContent="诊断网页AI通道中（约20秒）...";
  try{
    let d=await (await fetch("/api/webai_diag")).json();
    let lines=(d.steps||[]).map(function(s){return (s[1].indexOf("未")===0||s[1].indexOf("失败")===0?"[X] ":"[OK] ")+s[0]+"："+s[1]});
    st.textContent=d.ok?"网页AI通道正常":"网页AI通道有问题，见弹窗";
    let NL=String.fromCharCode(10);
    alert("网页AI通道诊断"+NL+NL+lines.join(NL)+NL+NL+(d.ok?"通道正常，缺资料时会自动追问DeepSeek/GPT":"按提示修复后再点[补全开发/维护区]"));
  }catch(e){st.textContent="诊断失败";alert("诊断请求失败："+e)}
};
document.getElementById("expandbtn").onclick=async function(){
  document.getElementById("enrichst").textContent="网络扩张中：透视买家供应商->翻工厂客户（几分钟）...";
  await fetch("/api/leads/expand",{method:"POST"});
  pollEnrich();
};
async function pollEnrich(){
  let d=await (await fetch("/api/enrich_status")).json();
  document.getElementById("enrichst").textContent=d.log||"";
  if(d.running)setTimeout(pollEnrich,5000);
  else loadLeads();
}
function strengthBadge(s){let cls=s>=5?"s5":(s>=4?"s4":"s1");return "<span class="+cls+">"+esc(s)+"</span>"}
function statusBadge(st){return "<span class='badge b-"+esc(st)+"'>● "+esc(st)+"</span>"}
function verdictBadge(v){return "<span class='xv "+esc(v||"pass")+"'>"+esc({pass:"PASS",fail:"FAIL",degraded:"DEGRADED"}[v]||v||"PASS")+"</span>"}
function pickNode(name){selNode=(selNode===name?null:name);redraw()}
function redraw(){if(LAST)render(LAST)}
function xdetail(name,rep){
  if(!rep)return "<div class=mut style='margin-top:8px'>该节点无专家报告（未执行或被跳过）</div>";
  let h="<div class=xdetail>";
  h+="<span style='font-weight:700'>"+esc(name)+"</span><span class=xrole>"+esc(rep.role||"")+"</span>"+verdictBadge(rep.verdict);
  if(rep.mission)h+="<div class=mut style='margin-top:4px'>使命："+esc(rep.mission)+"</div>";
  let cs=rep.criteria||[];
  if(cs.length){h+="<div style='margin-top:8px'>";
    for(let c of cs)h+="<div class=crit><span class='ck "+(c.ok?"y'>[✓]":"n'>[✗]")+"</span>"+esc(c.name)+(c.detail?" — "+esc(c.detail):"")+"<span class=cby>"+esc(c.by==="llm"?"LLM":"RULE")+"</span></div>";
    h+="</div>"}
  if(rep.thinking)h+="<div class=think>"+esc(rep.thinking)+"</div>";
  if(rep.notes)h+="<div class=xnotes>> 交接建议："+esc(rep.notes)+"</div>";
  if(rep.offline)h+="<div class=mut>（本次复核 LLM 离线，为规则判定）</div>";
  h+="</div>";
  return h;
}
function fieldOf(o,names){
  let keys=Object.keys(o);
  for(let w of names)for(let k of keys){if(String(k).toLowerCase().indexOf(w)>=0)return o[k]}
  return "";
}
function kvDump(o){
  let h="";
  for(let k of Object.keys(o)){
    let v=o[k];if(v&&typeof v==="object")v=JSON.stringify(v);
    h+="<div class=kv><b>"+esc(k)+"</b><span>"+esc(v)+"</span></div>";
  }
  return h;
}
function render(x){
  LAST=x;
  let r=x.result||{},h="";
  h+="<div>"+statusBadge(x.status)+" <span class=mut>"+esc(x.request||"")+"</span></div>";
  let meta=[];
  if(r.duration_sec)meta.push("elapsed "+r.duration_sec+"s");
  if(r.engine)meta.push("engine "+r.engine);
  let rf=r.reflection||{};
  if(rf.count)meta.push("reflect x"+rf.count);
  if(r.task_id)meta.push("task "+r.task_id);
  if(meta.length)h+="<div class=meta>"+esc(meta.join(" | "))+"</div>";
  if(r.error)h+="<p class=err>[!] "+esc(r.error)+"</p>";
  if(r.warning)h+="<p class=warn>[!] "+esc(r.warning)+"</p>";
  let nodes=r.nodes||[],nr=r.node_reports||{};
  let lastRec={};
  for(let nd of nodes)lastRec[nd.node]=nd;
  let cur=null;
  if(x.status==="running"&&nodes.length){
    let last=nodes[nodes.length-1].node;
    if(last==="REFLECT")cur="A_COLLECT";
    else{let i=CANON.indexOf(last);if(i>=0&&i<CANON.length-1)cur=CANON[i+1]}
  }
  h+="<div class=sec>▶ 流水线总览（①-⑫ 顺序执行，REFLECT 为失败回路）</div><div class=stg>";
  CANON.forEach((name,i)=>{
    let rec=lastRec[name],cls="snode";
    if(rec)cls+=(rec.skipped?" skip":(rec.success!==false?" ok":" no"));
    else if(x.status==="running")cls+=(name===cur?" run":"");
    else cls+=" skip";
    if(selNode===name)cls+=" sel";
    let d="";
    if(rec){let t=[];if(rec.note)t.push(rec.note);if(rec.duration!=null)t.push(rec.duration+"s");d=t.join(" | ")}
    else if(x.status!=="running")d="未执行";
    else if(name===cur)d="执行中...";
    h+="<div class='"+cls+"' data-n='"+esc(name)+"'><div class=sn>"+(i+1)+" "+esc(name)+"</div><div class=sc>"+esc(CN[name])+"</div><div class=sd>"+esc(d)+"</div></div>";
  });
  let rc=rf.count||0,rcls="snode refl"+(rc?" ok":"")+(selNode==="REFLECT"?" sel":"");
  h+="<div class='"+rcls+"' data-n='REFLECT'><div class=sn>↺ REFLECT</div><div class=sc>"+esc(CN.REFLECT)+"</div><div class=sd>"+(rc?("x"+rc+" 轮"):"未触发")+"</div></div>";
  h+="</div>";
  h+="<div class=flowleg>绿=通过 红=验收失败 琥珀闪=执行中 灰虚=跳过 · 点击节点查看专家验收明细</div>";
  if(rf.history&&rf.history.length){
    h+="<div class=reflstrip>";
    for(let q of rf.history)h+="<div class=rs>#"+esc(q.round)+" @"+esc(q.at_node)+" "+esc(q.diagnosis)+"<br><span>处方："+esc(q.advice||"")+((q.new_queries||[]).length?" → "+esc(q.new_queries.join(" / ")):"")+"</span></div>";
    h+="</div>";
  }
  if(selNode)h+=xdetail(selNode,nr[selNode]);
  let cs=r.new_companies&&r.new_companies.length?r.new_companies:(r.companies||[]);
  let prof=r.profiles||[],ana=r.analyses||[],let2=r.letters||[];
  if(cs.length||prof.length||ana.length||let2.length){
    h+="<div class=sec>▣ 执行成果<a class=exbtn href='/api/export/"+esc(r.task_id||tid)+"' target=_blank>[ 导出 MD ]</a></div>";
    if(cs.length){
      h+="<div class=card>[新客户] "+cs.length+"<table><tr><th>#</th><th>公司</th><th>国家</th><th>来源</th><th>强度</th></tr>"+cs.map((c,i)=>"<tr><td>"+(i+1)+"</td><td>"+esc(c.name)+"</td><td>"+esc(c.country)+"</td><td>"+esc(c.source)+"</td><td>"+strengthBadge(c.strength)+"</td></tr>").join("")+"</table></div>";
    }
    if(let2.length){
      h+="<div class=card>[开发信] "+let2.length+" 封";
      for(let o of let2){
        if(o&&typeof o==="object"){
          let co=fieldOf(o,["company","公司","to","name"]),sub=fieldOf(o,["subject","主题","title"]),body=fieldOf(o,["body","正文","content","email","letter","message"]);
          h+="<div class=lcard><button class=cp>复制</button><div class=lco>"+esc(co||"（未命名）")+"</div>";
          if(sub)h+="<div class=lsub>"+esc(sub)+"</div>";
          h+="<div class=lbody>"+esc(body||"")+"</div>";
          if(!body)h+=kvDump(o);
          h+="</div>";
        }else h+="<div class=lcard><div class=lbody>"+esc(o)+"</div></div>";
      }
      h+="</div>";
    }
    if(prof.length){h+="<div class=card>[客户画像] "+prof.length+" 份";for(let o of prof)h+="<div class=pcard>"+(o&&typeof o==="object"?kvDump(o):esc(o))+"</div>";h+="</div>"}
    if(ana.length){h+="<div class=card>[采购分析] "+ana.length+" 份";for(let o of ana)h+="<div class=pcard>"+(o&&typeof o==="object"?kvDump(o):esc(o))+"</div>";h+="</div>"}
  }
  h+="<details class=proc><summary>▤ 过程明细（策略 / 进化 / 收割 / 工厂池 / 闸门 / 清洗 / 情报）</summary>";
  if(r.strategy&&(r.strategy.queries||[]).length){let s=r.strategy;h+="<div class=card>[STRATEGY] "+esc((s.queries||[]).join(" / "))+"<div class=mut>"+esc(s.rationale||"")+"</div></div>"}
  if(r.evolution){let e=r.evolution;h+="<div class=card>[EVOLVE] <b>"+(e.evolved?"ON":"OFF")+"</b> · "+esc(e.note||"")+" · "+esc((e.variants||[]).join(" / "))+"</div>"}
  if(r.harvest){let v=r.harvest;let rows=(v.results||[]).map(t=>"<tr><td>"+esc(t.name)+"</td><td>"+esc(t.slug)+"</td><td>"+esc(t.items)+"</td><td>"+esc(t.file||"")+"</td></tr>").join("");
    h+="<div class=card>[HARVEST] <b>"+esc(v.mode||"")+"</b>"+(v.plan_file?" · plan "+esc(v.plan_file):"")+(v.merged_after_harvest!=null?" · new buyers "+v.merged_after_harvest:"");
    if(rows)h+="<table><tr><th>同行工厂</th><th>slug</th><th>提单</th><th>结果</th></tr>"+rows+"</table>";
    if(v.errors&&v.errors.length)h+="<div class=err>"+v.errors.map(esc).join("<br>")+"</div>";
    h+="</div>"}
  if(r.suppliers&&r.suppliers.length){h+="<div class=card>[FACTORY POOL] "+r.suppliers.length+"<table><tr><th>供应商</th><th>slug</th><th>提单</th><th>已收割</th></tr>"+r.suppliers.map(s=>"<tr><td>"+esc(s.name)+"</td><td>"+esc(s.slug)+"</td><td>"+esc(s.shipments)+"</td><td>"+(s.harvested?"<span class=y>Y</span>":"<span class=n>N</span>")+"</td></tr>").join("")+"</table></div>"}
  if(r.gate){let g=r.gate;h+="<div class=card>[GATE] "+(g.ok?"<span class=y>PASS</span>":"<span class=n>BLOCKED</span>")+" · raw "+g.raw+" · qualified "+g.qualified+" · strong "+g.strong;
    if(g.judgments&&g.judgments.length)h+="<table><tr><th>公司</th><th>审判</th><th>理由</th></tr>"+g.judgments.map(j2=>"<tr><td>"+esc(j2.name)+"</td><td>"+(String(j2.verdict).toLowerCase()==="accept"?"<span class=y>ACCEPT</span>":"<span class=n>REJECT</span>")+"</td><td>"+esc(j2.reason||"")+"</td></tr>").join("")+"</table>";
    h+="</div>"}
  if(r.known_count!=null||r.dropped_count!=null)h+="<div class=card>[CLEAN] <span class=y>new "+((r.new_companies||[]).length)+"</span> · known "+(r.known_count||0)+" · dropped "+(r.dropped_count||0)+"</div>";
  if(r.usitc){let u=r.usitc;h+="<div class=card>[USITC] "+(u.ok?"<span class=y>LOADED ("+esc(u.source)+")</span>":"<span class=mut>OFF</span>")+(u.ammo?"<div class=xnotes>> "+esc(u.ammo)+"</div>":"")+(u.ok&&u.text?"<pre>"+esc(u.text.slice(0,600))+"</pre>":"")+"</div>"}
  if(r.source_errors&&r.source_errors.length)h+="<div class='card err'>[SRC ERR]<br>"+r.source_errors.map(esc).join("<br>")+"</div>";
  h+="</details>";
  h+="<details><summary>[RAW JSON]</summary><pre>"+esc(JSON.stringify(x,null,2))+"</pre></details>";
  out.innerHTML=h;
  out.querySelectorAll(".snode").forEach(el=>el.onclick=function(){pickNode(el.dataset.n)});
  out.querySelectorAll(".cp").forEach(el=>el.onclick=function(){
    let b=el.parentElement.querySelector(".lbody");
    if(b&&navigator.clipboard)navigator.clipboard.writeText(b.textContent);
    el.textContent="已复制";
  });
}
async function poll(){
  let x=await (await fetch("/api/task/"+tid)).json(); render(x);
  if(x.status==="running"||x.status==="queued")timer=setTimeout(poll,2000);
  else{hint.textContent="";loadTasks()}
}
async function run(e){
  e.preventDefault(); go.disabled=true; hint.textContent="expert mode: each node reviewed by local 70B, ~15-30min per round...";
  out.innerHTML="<span class=mut>queued...</span>";selNode=null;LAST=null;
  let r=await fetch("/api/task",{method:"POST",body:JSON.stringify({request:req.value,market:"USA",industry:ind.value,quantity:+n.value})});
  let d=await r.json(); tid=d.task_id; go.disabled=false; poll();
}
document.getElementById("f").onsubmit=run;
async function loadTasks(){
  let d=await (await fetch("/api/tasks")).json();
  tasks.innerHTML=(d.tasks||[]).map(t=>"<div class=ti data-tid='"+esc(t.task_id)+"'><span class='dot "+esc(t.status)+"'></span>"+esc((t.request||"").slice(0,16))+"<br><span class=mut>"+esc(t.task_id)+" · "+esc(t.status)+"</span></div>").join("")||"<span class=mut style='padding:10px;display:block'>暂无</span>";
  tasks.querySelectorAll(".ti").forEach(el=>el.onclick=function(){tid=el.dataset.tid;selNode=null;showTab(1);poll()});
  if(!tid&&(d.tasks||[]).length){
    let act=null;
    for(let t of d.tasks){if(t.status==="running"){act=t;break}}
    if(!act)act=d.tasks[0];
    tid=act.task_id;poll();
  }
}
async function loadDash(){
  let d=await (await fetch("/api/stats")).json(); let h="";
  h+="<div class=stat4>";
  for(let s of [[d.companies_total,"已建档公司"],[d.suppliers_total+" / "+d.suppliers_unharvested,"同行池 / 未收割"],[d.harvest_items,"收割提单累计"],[d.runs_total,"累计采集轮次"]])
    h+="<div class=stat><b>"+esc(s[0]==null?0:s[0])+"</b><span class=mut>"+esc(s[1])+"</span></div>";
  h+="</div>";
  if(d.runs&&d.runs.length){
    h+="<div class=card>[采集轮次·近12] 绿=闸门通过<div class=bars>"+d.runs.map(r2=>"<div><span class='bar"+(r2.gate_ok?"":" no")+"' style='width:"+Math.max(4,(r2.result_count||0)*8)+"px'></span> <span class=mut>"+esc(r2.day||"")+" · "+esc(r2.result_count||0)+"家</span></div>").join("")+"</div></div>";
  }
  if(d.harvest_log&&d.harvest_log.length){
    h+="<div class=card>[收割日志·近10]<table><tr><th>供应商</th><th>方式</th><th>状态</th><th>条数</th><th>备注</th></tr>"+d.harvest_log.map(v=>"<tr><td>"+esc(v.supplier)+"</td><td>"+esc(v.mode)+"</td><td>"+esc(v.status)+"</td><td>"+esc(v.items)+"</td><td>"+esc(v.note||"")+"</td></tr>").join("")+"</table></div>";
  }
  if(d.top_suppliers&&d.top_suppliers.length){
    h+="<div class=card>[同行池 TOP]<table><tr><th>供应商</th><th>提单</th><th>已收割</th></tr>"+d.top_suppliers.map(s=>"<tr><td>"+esc(s.name)+"</td><td>"+esc(s.shipments)+"</td><td>"+(s.harvested?"<span class=y>Y</span>":"<span class=n>N</span>")+"</td></tr>").join("")+"</table></div>";
  }
  if(!d.runs_total)h+="<div class=card mut>还没有历史数据，先去工作台跑一轮任务。</div>";
  dash.innerHTML=h;
}
loadTasks();setInterval(loadTasks,15000);
</script>'''

HTML=HTML.replace('__VER__',settings.VERSION)

def _day(ts):
    try: return time.strftime('%m-%d %H:%M',time.localtime(float(ts)))
    except Exception: return ''

def _stats():
    out={'companies_total':0,'suppliers_total':0,'suppliers_unharvested':0,'harvest_items':0,
         'runs_total':0,'runs':[],'harvest_log':[],'top_suppliers':[]}
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
        out['companies_total']=conn.execute('SELECT COUNT(*) c FROM company_state').fetchone()['c']
        r=conn.execute('SELECT COUNT(*) t,SUM(CASE WHEN harvested_at IS NULL THEN 1 ELSE 0 END) u FROM suppliers').fetchone()
        out['suppliers_total']=r['t'] or 0; out['suppliers_unharvested']=r['u'] or 0
        out['harvest_items']=conn.execute("SELECT COALESCE(SUM(items),0) s FROM harvest_log WHERE status='ok'").fetchone()['s'] or 0
        out['runs_total']=conn.execute('SELECT COUNT(*) c FROM search_runs').fetchone()['c']
        for r in conn.execute('SELECT result_count,gate,created_at FROM search_runs ORDER BY id DESC LIMIT 12'):
            g={}
            try: g=json.loads(r['gate'] or '{}')
            except Exception: pass
            out['runs'].append({'result_count':r['result_count'],'gate_ok':bool(g.get('ok')),'day':_day(r['created_at'])})
        out['runs'].reverse()
        for r in conn.execute('SELECT supplier,mode,status,items,note,created_at FROM harvest_log ORDER BY id DESC LIMIT 10'):
            out['harvest_log'].append({'supplier':r['supplier'],'mode':r['mode'],'status':r['status'],
                                       'items':r['items'],'note':r['note'],'day':_day(r['created_at'])})
        for r in conn.execute('SELECT name,shipments,harvested_at FROM suppliers ORDER BY shipments DESC LIMIT 8'):
            out['top_suppliers'].append({'name':r['name'],'shipments':r['shipments'] or 0,'harvested':bool(r['harvested_at'])})
        conn.close()
    except Exception: pass
    return out


def _export_md(tid):
    x=SYS.get(tid)
    if not x: return None
    r=x.get('result') or {}
    L=['# PSV 成果导出','','任务: %s | 请求: %s | 状态: %s'%(tid,x.get('request'),x.get('status'))]
    cs=r.get('new_companies') or r.get('companies') or []
    if cs:
        L+=['','## 新客户清单','']
        for c in cs: L.append('- %s | %s | 强度%s | %s'%(c.get('name'),c.get('country'),c.get('strength'),c.get('source')))
    for key,title in [('profiles','客户画像'),('analyses','采购分析'),('letters','开发信')]:
        arr=r.get(key) or []
        if not arr: continue
        L+=['','## '+title,'']
        for it in arr:
            if isinstance(it,dict):
                for k,v in it.items(): L.append('**%s**: %s'%(k,v))
                L+=['','---','']
            else: L+=[str(it),'']
    return '\n'.join(L)

ENRICH={'running':False,'log':''}
SEQ={'running':False,'log':''}
EXPAND={'running':False,'log':''}
def _expand_bg():
    EXPAND['running']=True; ENRICH['running']=True
    try:
        ENRICH['log']='网络扩张中：透视买家->工厂->客户...'
        from core.tools import expand,scoring
        st=expand.run()
        n=scoring.rescore_all()
        ENRICH['log']='扩张完成：透视%d买家·挖%d工厂·新增线索%d条（%d条评分已刷新）'%(st.get('buyers',0),st.get('suppliers',0),st.get('new_leads',0),n)
        if st.get('errors'): ENRICH['log']+=' · 失败%d家'%len(st['errors'])
    except Exception as e:
        ENRICH['log']='扩张失败: '+str(e)[:120]
    EXPAND['running']=False; ENRICH['running']=False
def _webai_diag():
    """一键诊断网页AI通道：浏览器->接管->登录态，不发问题不耗额度。"""
    from core.tools import contact_finder
    steps=[]
    ok=contact_finder._cdp_alive(settings.IY_WEB_CDP_URL)
    steps.append(['AI浏览器(9222端口)','已启动' if ok else '未启动 —— 关掉所有Chrome窗口后双击 start_chrome_debug.bat'])
    if not ok: return {'ok':False,'steps':steps}
    try:
        from core.tools import web_ai
        w=web_ai.WebAI(); w._launch()
        steps.append(['接管浏览器','成功'])
    except Exception as e:
        steps.append(['接管浏览器','失败: '+str(e)[:80]])
        return {'ok':False,'steps':steps}
    for eng in ('deepseek','chatgpt'):
        cfg=web_ai.ENGINES[eng]
        try:
            w._pg.goto(cfg['url'],timeout=30000,wait_until='domcontentloaded')
            w._pg.wait_for_timeout(4000)
            box=w._first_visible(cfg['inputs'])
            steps.append([eng,'已登录，随时可以对话' if box else '未找到输入框 —— 请在该浏览器里登录'])
        except Exception as e:
            steps.append([eng,'打开失败: '+str(e)[:60]])
    try: w.close()
    except Exception: pass
    allok=steps[1][1]=='成功' and any('已登录' in v for _,v in steps[2:])
    return {'ok':allok,'steps':steps}

def _enrich_one_bg(norm):
    """移入开发区：自动给该客户补联系方式+刷新评分（与批量补全互斥，避免抢浏览器）。"""
    if ENRICH.get('running'): return
    ENRICH['running']=True
    try:
        from core.memory.db import DB
        nm=(DB().get_lead(norm) or {}).get('name','?')
        ENRICH['log']='正在自动补全: '+nm
        from core.tools import contact_finder
        contact_finder.PROGRESS=lambda m: ENRICH.__setitem__('log',m)
        r=contact_finder.enrich_one(norm)
        if r and r.get('complete'): msg='三件套齐全 ✓'
        elif r: msg='缺'+(r.get('missing') or '官网')
        else: msg='未找到官网'
        ENRICH['log']='自动补全完成: %s（%s）'%(nm,msg)
    except Exception as e:
        ENRICH['log']='自动补全失败: '+str(e)[:100]
    try: contact_finder.PROGRESS=None
    except Exception: pass
    ENRICH['running']=False
def _audit_one_bg(norm):
    """单个客户资料审核：GPT 验证并自动更新。"""
    if ENRICH.get('running'): return
    ENRICH['running']=True
    try:
        from core.memory.db import DB
        from core.tools import auditor
        db=DB(); lead=db.get_lead(norm)
        if not lead:
            ENRICH['log']='审核失败：客户不存在'
        else:
            ENRICH['log']='GPT验证并更新: '+lead['name']+'...'
            auditor.PROGRESS=lambda m: ENRICH.__setitem__('log',m)
            updated, rep = auditor.audit_and_update(lead, db=db, use_ai=True)
            ENRICH['log']='审核完成: %s → %s'%(updated.get('name', lead['name']), auditor.VERDICT_CN.get(rep['verdict'], rep['verdict']))
    except Exception as e:
        ENRICH['log']='审核失败: '+str(e)[:120]
    finally:
        try: auditor.PROGRESS=None
        except Exception: pass
        ENRICH['running']=False
def _seq_bg(zone='dev', max_customers=20):
    SEQ['running']=True
    try:
        from core.tools import email_sequence
        email_sequence.run_sequence(zone=zone, max_customers=max_customers, progress_cb=lambda m: SEQ.__setitem__('log',m))
    except Exception as e:
        SEQ['log']='开发信序列失败: '+str(e)[:150]
    SEQ['running']=False

def _enrich_bg():
    ENRICH['running']=True
    try:
        from core.tools import contact_finder,scoring
        contact_finder.PROGRESS=lambda m: ENRICH.__setitem__('log',m)
        out=contact_finder.run(limit=15)
        ok=sum(1 for o in out if o.get('ok'))
        full=sum(1 for o in out if o.get('complete'))
        n=scoring.rescore_all()
        wa=contact_finder.LAST
        if wa.get('webai_ready') is False:
            watip=' · 网页AI未就绪(%s)'%(wa.get('webai_note') or 'AI浏览器未启动')
        elif wa.get('webai_tried'):
            watip=' · 网页AI成功%d/尝试%d'%(wa.get('webai_ok',0),wa['webai_tried'])
        else:
            watip=' · 网页AI未触发'
        ENRICH['log']='补全完成：%d/%d 找到官网 · %d 家三件套齐全 · %d 条评分已刷新'%(ok,len(out),full,n)+watip
    except Exception as e:
        ENRICH['log']='补全失败: '+str(e)[:120]
    try: contact_finder.PROGRESS=None
    except Exception: pass
    ENRICH['running']=False

def _draft_reply(lead,msgs,mode,hint):
    """通信模块的大模型待机核心：结合画像+分区策略+往来记录起草回信。"""
    from core.model.client import ModelClient
    zone=lead.get('zone') or 'pool'
    strat={'pool':'这是尚未开发的新线索，写第一封破冰内容。',
           'dev':'这是开发中的客户：目标是破冰/跟进/推进到报价或寄样。简短有钩子，结尾给一个低门槛动作（回邮件/要目录/15分钟电话）。',
           'maint':'这是已合作客户：目标是维护关系/促复购/推新品，语气熟络，可适当提及上次合作。'}.get(zone,'')
    hist='\n'.join(('我方' if m['direction']=='out' else '客户')+'['+str(m.get('channel') or '')+']: '+str(m['content'])[:300] for m in (msgs or [])[-8:])
    who='; '.join([x for x in [lead.get('name'),lead.get('country'),
        '生日蜡烛品类' if lead.get('segment')=='birthday' else ('蜡烛/家居香氛品类' if lead.get('segment') else ''),
        ('年提单约%d条'%lead['shipments']) if lead.get('shipments') else '',
        (lead.get('desc_sample') or '')[:120]] if x])
    prof=(lead.get('profile') or '')[:500]
    ident=('我方身份（必须严格使用，禁止占位符如 [Your Company Name]）：中国河北宁晋的生日蜡烛工厂'
           '（宁晋是全球生日蜡烛之都，约占全球产量60%，产业集群内有上百家专业作坊和全链条厂家）。'
           '产品：spiral/number/party birthday candles 及香薰/装饰蜡烛，支持OEM/ODM、低起订量试单、快速免费寄样。'
           '业务是制造蜡烛，不是包装、不是物流、不是贸易公司。'
           '署名固定：'+settings.SENDER_NAME_EN+' ('+settings.SENDER_NAME+') / WhatsApp '+settings.SENDER_PHONE+
           ((' / Email '+settings.SENDER_EMAIL) if getattr(settings,'SENDER_EMAIL','') else '')+'。')
    if mode=='whatsapp':
        fmt=('写一条 WhatsApp 短消息：2-4句英文，口语化自然，不用邮件格式，不要主题行。'
             '第一句话说清我们是谁（Ningjin birthday candle factory），给一个和对方产品线相关的钩子，结尾给一个低门槛动作。')
        prompt=(strat+'\n'+ident+'\n'+fmt+'\n客户档案：'+who+'\n客户画像：'+prof+
                '\n最近往来：\n'+(hist or '（无，这是首次联系）')+
                ('\n本次意图：'+str(hint)[:300] if hint else '')+
                '\n只输出成稿本身，不要解释，不要编造数据，不要用任何占位符。')
    else:
        from core.tools import pitch
        prompt=strat+'\n'+pitch.letter_prompt(lead)+(
            '\n最近往来：\n'+(hist or '（无，这是首次联系）') if hist else '')+(
            '\n本次意图：'+str(hint)[:300] if hint else '')
    txt=ModelClient().chat(prompt,temperature=0.5,max_tokens=900,timeout=300)
    if not txt and settings.WEBAI_ENABLED:
        from core.tools import web_ai
        txt=web_ai.solve('你是资深外贸业务员。'+ident+'\n'+prompt[:800],context='客户档案：'+who+'\n画像：'+prof+
            '\n最近往来：\n'+(hist or '（无）')+('\n本次意图：'+str(hint)[:300] if hint else '')+
            '\n只输出成稿本身，不要解释，不要用任何占位符。',timeout=180)
    if txt:  # v18.2.3 兜底：占位符一律替换为 configured 公司名
        comp=getattr(settings,'SENDER_COMPANY','Ningjin Birthday Candle Factory')
        for ph in ('[Your Company Name]','[Company Name]','[Insert Company Name]','[Your Company]','[公司名]'):
            txt=txt.replace(ph,comp)
    return txt

class H(BaseHTTPRequestHandler):
    def _s(self,o,code=200,html=False):
        b=o.encode() if html else json.dumps(o,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(b)))
        self.end_headers()
        _w(self.wfile,b)
    def do_GET(self):
        qs={}
        if '?' in self.path:
            from urllib.parse import parse_qs
            qs={k:v[0] for k,v in parse_qs(self.path.split('?',1)[1]).items()}
        self.path=self.path.split('?')[0] or '/'
        if self.path=='/': return self._s(HTML,html=True)
        if self.path=='/api/stats': return self._s(_stats())
        if self.path=='/api/leads':
            from core.memory.db import DB
            db=DB(); rows=db.list_leads(kind=qs.get('kind') or None,segment=qs.get('segment') or None,q=qs.get('q') or None,zone=qs.get('zone') or None)
            allr=db.list_leads(limit=10000)
            st={'total':len(allr),'importers':sum(1 for r in allr if r.get('kind')=='importer'),
                'suppliers':sum(1 for r in allr if r.get('kind')=='supplier'),
                'birthday':sum(1 for r in allr if r.get('segment')=='birthday')}
            return self._s({'leads':rows,'stats':st})
        if self.path=='/api/leads.csv':
            from core.memory.db import DB
            rows=DB().list_leads(kind=qs.get('kind') or None,segment=qs.get('segment') or None,q=qs.get('q') or None,limit=10000)
            import io,csv
            buf=io.StringIO(); w=csv.writer(buf)
            w.writerow(['公司','国家','类型','HS编码','品类信号','提单数','最近出货','评分','等级','官网','邮箱','电话','地址','联系人','标签','分区','触达状态','来源','首次发现','最近发现'])
            ZN={'pool':'线索池','dev':'开发区','maint':'维护区'}
            TS={'new':'新线索','contacted':'已触达','replied':'已回复','sample':'寄样','deal':'成交','paused':'搁置'}
            for r in rows:
                w.writerow([r.get('name'),r.get('country'),r.get('kind'),r.get('hs_code'),r.get('segment'),
                            r.get('shipments'),r.get('last_shipment'),r.get('score'),r.get('grade'),
                            r.get('website'),r.get('emails'),r.get('phones'),r.get('address'),r.get('contact_person'),
                            r.get('tags'),ZN.get(r.get('zone') or 'pool','线索池'),TS.get(r.get('touch_status') or 'new','新线索'),r.get('source'),
                            time.strftime('%Y-%m-%d',time.localtime(r.get('first_seen') or 0)),
                            time.strftime('%Y-%m-%d',time.localtime(r.get('last_seen') or 0))])
            b=('\ufeff'+buf.getvalue()).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','text/csv; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="psv_leads.csv"')
            self.send_header('Content-Length',str(len(b)))
            self.end_headers(); _w(self.wfile,b); return
        m=re.match(r'/api/lead/(\w+)',self.path)
        if m:
            from core.memory.db import DB
            db=DB(); lead=db.get_lead(m.group(1))
            if not lead: return self._s({'error':'not found'},404)
            msgs=db.list_messages(m.group(1))
            for mm in msgs: mm['day']=_day(mm.get('ts'))
            return self._s({'lead':lead,'messages':msgs})
        if self.path=='/api/enrich_status': return self._s({'running':bool(ENRICH.get('running') or EXPAND.get('running')),'log':ENRICH.get('log','')})

        if self.path=='/api/email_sequence/status':
            return self._s({'running':SEQ.get('running',False),'log':SEQ.get('log','')})
        if self.path=='/api/webai_diag': return self._s(_webai_diag())
        if self.path=='/api/tasks':
            try:
                conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
                rows=[dict(r) for r in conn.execute('SELECT task_id,request,status,created_at,updated_at FROM tasks ORDER BY updated_at DESC LIMIT 20')]
                conn.close()
            except Exception: rows=[]
            return self._s({'tasks':rows})
        m=re.match(r'/api/task/(\w+)',self.path)
        if m:
            x=SYS.get(m.group(1)); return self._s(x or {'error':'not found'},200 if x else 404)
        m=re.match(r'/api/export/(\w+)',self.path)
        if m:
            md=_export_md(m.group(1))
            if md is None: return self._s({'error':'not found'},404)
            b=md.encode()
            self.send_response(200)
            self.send_header('Content-Type','text/markdown; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="leads_%s.md"'%m.group(1))
            self.send_header('Content-Length',str(len(b)))
            self.end_headers(); _w(self.wfile,b); return
        return self._s({'error':'not found'},404)
    def do_POST(self):
        self.path=self.path.split('?')[0]
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))).decode() or '{}')
        if self.path=='/api/task':
            return self._s({'task_id':SYS.start(body.get('request',''),body.get('market','USA'),body.get('industry','birthday candles'),int(body.get('quantity') or 20))})
        if self.path=='/api/lead/update':
            return self._s({'ok':False,'error':'手动修改已禁用，请使用自动修正流程'},403)
        if self.path=='/api/lead/audit':
            if ENRICH.get('running'): return self._s({'ok':True,'already':True})
            import threading
            threading.Thread(target=_audit_one_bg,args=(body.get('norm',''),),daemon=True).start()
            return self._s({'ok':True})
        if self.path=='/api/lead/zone':
            from core.memory.db import DB
            DB().set_zone(body.get('norm',''),body.get('zone','pool'))
            if body.get('zone')=='dev':
                import threading
                threading.Thread(target=_enrich_one_bg,args=(body.get('norm',''),),daemon=True).start()
            return self._s({'ok':True})
        if self.path=='/api/lead/status':
            from core.memory.db import DB
            DB().lead_update(body.get('norm',''),touch_status=body.get('touch_status','new'),last_touch=time.time())
            return self._s({'ok':True})
        if self.path=='/api/comm/delmsg':
            from core.memory.db import DB
            DB().delete_message(body.get('mid'))
            return self._s({'ok':True})
        if self.path=='/api/comm/marksent':
            from core.memory.db import DB
            db=DB(); m=db.get_message(body.get('mid'))
            if not m: return self._s({'error':'not found'},404)
            db.update_message(m['id'],str(m['content']).replace('[待发送]','[邮件已发送]',1))
            db.lead_update(m['lead_norm'],touch_status='contacted',last_touch=time.time())
            return self._s({'ok':True})
        if self.path=='/api/comm/sendmail':
            from core.memory.db import DB
            from core.tools import mailer
            db=DB(); lead=db.get_lead(body.get('norm',''))
            if not lead: return self._s({'error':'not found'},404)
            emails=[e.strip() for e in (lead.get('emails') or '').split(',') if e.strip()]
            if not emails: return self._s({'error':'该客户还没有邮箱——先补全联系方式'},400)
            to=emails[0]
            cc=emails[1:4]  # 最多抄送3个邮箱
            drafts=[m for m in db.list_messages(lead['norm']) if m.get('direction')=='out' and m.get('channel')=='email' and m.get('draft')]
            if not drafts: return self._s({'error':'还没有邮件草稿——先点[生成邮件]'},400)
            letter=drafts[-1]['content']
            subject='Birthday candles for %s - Ningjin factory direct'%(lead.get('name') or '')
            try:
                if body.get('via')=='smtp':
                    mailer.smtp_send(to,subject,letter,cc_list=cc)
                    db.add_message(lead['norm'],'out','email','[SMTP已发送] 收件:%s 抄送:%s | 标题:%s'%(to,','.join(cc),subject))
                    db.lead_update(lead['norm'],touch_status='contacted',last_touch=time.time())
                    return self._s({'ok':True,'note':'已通过SMTP发送到 '+to})
                mailer.open_compose(to,subject,letter,cc_list=cc)
                db.add_message(lead['norm'],'out','email','[待发送] 邮箱写信页已打开 | 收件:%s 抄送:%s | 标题:%s'%(to,','.join(cc),subject))
                return self._s({'ok':True,'note':'写信页已打开（收件人 '+to+'）。在邮箱里点发送后，回时间线点[确认已发]'})
            except Exception as e:
                return self._s({'error':str(e)[:150]},502)
        if self.path=='/api/comm/log':
            from core.memory.db import DB
            DB().add_message(body.get('norm',''),body.get('direction','out'),body.get('channel','manual'),body.get('content',''))
            return self._s({'ok':True})
        if self.path=='/api/comm/draft':
            from core.memory.db import DB
            db=DB(); lead=db.get_lead(body.get('norm',''))
            if not lead: return self._s({'error':'not found'},404)
            txt=_draft_reply(lead,db.list_messages(lead['norm']),body.get('mode','email'),body.get('hint',''))
            if not txt: return self._s({'error':'LLM无响应（检查本地模型是否在线）'},502)
            db.add_message(lead['norm'],'out',body.get('mode','email'),txt,draft=1)
            return self._s({'text':txt})
        if self.path=='/api/email_sequence/start':
            if SEQ.get('running'): return self._s({'ok':True,'already':True})
            import threading
            threading.Thread(target=_seq_bg,args=(body.get('zone','dev'),int(body.get('max',20))),daemon=True).start()
            return self._s({'ok':True})

        if self.path=='/api/leads/enrich':
            if ENRICH.get('running'): return self._s({'ok':True,'already':True})
            import threading
            threading.Thread(target=_enrich_bg,daemon=True).start()
            return self._s({'ok':True})
        if self.path=='/api/leads/expand':
            if ENRICH.get('running') or EXPAND.get('running'): return self._s({'ok':True,'already':True})
            import threading
            threading.Thread(target=_expand_bg,daemon=True).start()
            return self._s({'ok':True})
        return self._s({'error':'not found'},404)
    def log_message(self,*a): pass
class _Srv(ThreadingHTTPServer):
    allow_reuse_address=False
    daemon_threads=True

def run():
    try: srv=_Srv((settings.WEB_HOST,settings.WEB_PORT),H)
    except OSError:
        print('[webui] port %s already in use - another console instance is running.'%settings.WEB_PORT)
        print('[webui] open http://localhost:%s (this window can be closed)'%settings.WEB_PORT)
        return
    print('[webui] console: http://localhost:%s'%settings.WEB_PORT)
    srv.serve_forever()
\n\n================================================================================\n# FILE [39/40]: customs_clean.py\n================================================================================\n\n#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PSV v13 海关提单清洗器
用法：
  python customs_clean.py --input data/customs --db data/psv.db [--days 90] [--top 10]
支持 .csv 与 .xlsx（xlsx 需环境里有 pandas）。兼容 Apify importyeti-scraper 导出列名。
"""
import argparse,csv,hashlib,re,sqlite3,time
from pathlib import Path
HS=re.compile(r'^\s*3406(\.0{1,4})?\b',re.I); OK=re.compile(r'\b(candle|candles|scented candle|birthday candle|taper|home fragrance|wax candle)\b',re.I); BAD=re.compile(r'on behalf of|freight|forwarder|amazon|ikea|walmart|翻译|词典',re.I)
SUF=re.compile(r'\b(inc|llc|ltd|co|corp|corporation|company|import|imports|trading)\b\.?',re.I)
MAP={'bol':['bol','bol_number','bol #','bol#','bill_of_lading','bl','shipment_id','house_bol','master_bol'],
     'date':['date','arrival_date','import_date','shipment_date','arrival'],
     'importer':['importer','company_name','consignee','consignee_name','buyer','importer_name'],
     'shipper':['shipper','supplier_name','shipper_name','exporter','supplier','seller'],
     'notify':['notify','notify_party'],
     'hs':['hs','hs_code','hscode','commodity_code','hs_codes/0/hs_code'],
     'desc':['desc','description','product_description','commodity','goods','hs_codes/0/description'],
     'qty':['qty','quantity','units','packages','pcs'],
     'weight':['weight','weight_kg','gross_weight','kg'],
     'teu':['teu','containers','containers_count'],
     'origin':['origin','country_of_origin','shipper_country','supplier_country'],
     'port_discharge':['port_discharge','port_of_unlading','us_port','arrival_port']}
def norm(s): return re.sub(r'[^a-z0-9]+','',SUF.sub('',str(s or '').lower()))
def pick(row,keys):
    low={str(k).lower().strip():v for k,v in row.items()}
    for k in keys:
        for c in low:
            if c==k or c.replace(' ','_')==k or k in c:
                v=str(low[c] or '').strip()
                if v and v.lower()!='nan': return v
    return ''
def num(x):
    m=re.findall(r'-?\d+(?:\.\d+)?',str(x or '').replace(',','')); return float(m[0]) if m else 0.0
def dt(x):
    x=str(x or '').strip()[:10]
    for f in ('%Y-%m-%d','%Y/%m/%d','%m/%d/%Y','%Y%m%d'):
        try: return time.mktime(time.strptime(x,f))
        except Exception: pass
    return 0.0
def init(db):
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE IF NOT EXISTS customs_raw(id INTEGER PRIMARY KEY AUTOINCREMENT,row_hash TEXT UNIQUE,bol TEXT,ts REAL,importer TEXT,importer_norm TEXT,shipper TEXT,notify TEXT,hs TEXT,descr TEXT,qty REAL,weight REAL,teu REAL,origin TEXT,port_discharge TEXT,source_file TEXT,direct_importer INT,created_at REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS buyers_90d(importer_norm TEXT PRIMARY KEY,importer TEXT,first_seen REAL,last_seen REAL,shipments INT,total_weight REAL,total_qty REAL,total_teu REAL,supplier_count INT,origins TEXT,ports TEXT,sample_desc TEXT,score REAL,reasons TEXT,updated_at REAL)')
def rows_of(fp):
    """统一产出 dict 行；csv 多编码兜底，xlsx 走 pandas"""
    if fp.suffix.lower() in ('.xlsx','.xls'):
        try:
            import pandas as pd
        except ImportError:
            print(f'[跳过] {fp.name}: xlsx 需要 pandas，请在 Apify 导出时改选 CSV，或 pip install pandas openpyxl')
            return
        for r in pd.read_excel(fp,dtype=str).to_dict('records'): yield r
        return
    for enc in ('utf-8-sig','gb18030','latin1'):
        try:
            f=fp.open(encoding=enc,errors='strict',newline=''); f.read(2048); f.seek(0); break
        except Exception: continue
    else: return
    with f:
        for row in csv.DictReader(f): yield row
def ingest(inp,db,days):
    init(db); cutoff=time.time()-days*86400; kept=0; reasons={'无进口商或货代':0,'非蜡烛品类':0,'超出时间窗':0,'重复提单':0}
    with sqlite3.connect(db) as c:
        for fp in sorted(Path(inp).rglob('*')):
            if fp.suffix.lower() not in ('.csv','.xlsx','.xls'): continue
            for row in rows_of(fp) or []:
                r={k:pick(row,v) for k,v in MAP.items()}
                if not r['importer'] or BAD.search(r['importer']): reasons['无进口商或货代']+=1; continue
                if not (HS.search(r['hs']) or (OK.search(r['desc']) and not BAD.search(r['desc']))): reasons['非蜡烛品类']+=1; continue
                ts=dt(r['date']) or cutoff
                if ts<cutoff: reasons['超出时间窗']+=1; continue
                direct=0 if (r['notify'] and norm(r['notify'])!=norm(r['importer'])) else 1
                h=hashlib.md5('|'.join([r['bol'],str(ts),r['importer'],r['shipper'],r['desc']]).encode()).hexdigest()
                try:
                    c.execute('INSERT INTO customs_raw(row_hash,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_discharge,source_file,direct_importer,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(h,r['bol'],ts,r['importer'],norm(r['importer']),r['shipper'],r['notify'],r['hs'],r['desc'],num(r['qty']),num(r['weight']),num(r['teu']),r['origin'],r['port_discharge'],fp.name,direct,time.time())); kept+=1
                except sqlite3.IntegrityError: reasons['重复提单']+=1
    print('kept',kept,'| skipped:',', '.join(f'{k}={v}' for k,v in reasons.items()))
    rebuild(db,days)
def rebuild(db,days):
    cutoff=time.time()-days*86400
    with sqlite3.connect(db) as c:
        rows=c.execute('SELECT importer_norm,MAX(importer),MIN(ts),MAX(ts),COUNT(*),SUM(weight),SUM(qty),SUM(teu),COUNT(DISTINCT shipper),GROUP_CONCAT(DISTINCT origin),GROUP_CONCAT(DISTINCT port_discharge),GROUP_CONCAT(DISTINCT substr(descr,1,60)),AVG(direct_importer) FROM customs_raw WHERE ts>=? GROUP BY importer_norm',(cutoff,)).fetchall()
        c.execute('DELETE FROM buyers_90d'); now=time.time()
        for n,imp,fs,ls,sh,tw,tq,tt,sc,orig,ports,desc,dr in rows:
            score=round(max(0,30-(now-(ls or cutoff))/86400/3)+min(35,sh*7)+min(20,(tw or 0)/1000+(tt or 0)*3)+min(10,(sc or 0)*2)+(5 if (dr or 0)>0.7 else 0),2)
            c.execute('INSERT INTO buyers_90d VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(n,imp,fs,ls,sh,tw or 0,tq or 0,tt or 0,sc or 0,orig or '',ports or '',desc or '',score,f'shipments={sh};suppliers={sc};direct={dr:.2f}',now))
        print('buyers_90d',c.execute('SELECT COUNT(*) FROM buyers_90d').fetchone()[0])
def top(db,limit):
    conn=sqlite3.connect(db); conn.row_factory=sqlite3.Row
    for r in conn.execute('SELECT importer,shipments,supplier_count,total_weight,score,reasons FROM buyers_90d ORDER BY score DESC LIMIT ?',(limit,)): print(dict(r))
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--db',default='data/psv.db'); ap.add_argument('--days',type=int,default=90); ap.add_argument('--top',type=int,default=0); a=ap.parse_args(); Path(a.db).parent.mkdir(parents=True,exist_ok=True); ingest(a.input,a.db,a.days); top(a.db,a.top) if a.top else None
\n\n================================================================================\n# FILE [40/40]: run_webui.py\n================================================================================\n\nfrom core.webui.app import run
if __name__=='__main__': run()
\n