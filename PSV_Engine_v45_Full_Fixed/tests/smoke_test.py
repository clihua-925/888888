import os, tempfile, json, time, sqlite3, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import tempfile as _tf; os.environ['DATABASE_PATH']=_tf.mktemp(suffix='.db')  # v35: 测试库不进数据根
os.environ['OUTREACH_ENABLED']='false'
os.environ['WEBAI_ENABLED']='false'
os.environ['EXPERT_MODE']='false'
os.environ['MISSION_DIRECTOR_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
(root/'data').mkdir(exist_ok=True)

from core.memory.db import DB
import core.runtime.development as dev
dev.auditor.audit_and_update=lambda lead,db=None,use_ai=True,webai=None: (lead, {'verdict':'pass','criteria':[]})
dev.pitch.letter_prompt=lambda lead,ammo='',industry_key=None: 'Write a concise Subject line and a short email using only provided facts.'
from core.runtime.development import run_sequence

db=DB(); db.upsert_leads([{'name':'Acme Candle Imports LLC','country':'USA','kind':'importer','category':'birthday candles','shipments':8,'last_shipment':'2026-07-20','source':'smoke','status':'new'}])
lead=db.get_lead('acmecandleimportsllc'); assert lead
# seed trade history
with db.c() as c:
    c.execute("INSERT OR REPLACE INTO buyers_90d(importer_norm,importer,first_seen,last_seen,shipments,total_weight,total_qty,total_teu,supplier_count,origins,ports,sample_desc,score,reasons,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ('acmecandleimportsllc',lead['name'],'2026-01-01','2026-07-20',8,100,200,2,3,'CN','LAX','birthday candles',90,'smoke',time.time()))
# v37+ 合同：DEV_LETTER 必须把草稿真实落库（DEV_REVIEW 人工审核门只认库内草稿），stub 也需遵守
def _smoke_letter(state):
    txt='Subject: Sample idea for your candle line\n\nHi team, we are a candle factory in Ningjin offering free samples, fast quotation, flexible capacity and factory direct pricing for importers. Reply for our catalog and a free sample pack today.'
    db.add_message(state['lead_norm'],'out','email',txt,draft=1)
    m=db.latest_out_message(state['lead_norm'])
    if m: db.set_message_status(m['id'],'drafted')
    return {'letter':txt,'_success':True,'_note':'smoke letter'}
dev.FN['DEV_LETTER']=_smoke_letter
# 沙箱确定性：钉死网页抓取/网站搜索（冒烟测的是链路连通，不是外网）
from core.intelligence import waterfall as _wf
from core.tools import contact_finder as _cf
_wf._fetch=lambda url,timeout=15: ''
_cf.ContactFinder._search_website_by_company=lambda self,*a,**k: None
res=run_sequence(lead['norm'],task_id='dev-smoke')
assert res['ok'],res
assert res['opportunity']['window'] in {'NOW','SOON','WATCH','DORMANT','UNKNOWN'}
assert res['offer_strategy']['offers']
assert res['letter']
# schedule persistence / claim lock
DB().upsert_schedule('smoke','discovery','USA','candle',5,1,True,{})
s=DB().list_schedules()[0]; DB().mark_schedule_run(s['id'],'test'); assert DB().list_schedules()[0]['last_status']=='test'
print('SMOKE_OK')
print(json.dumps({'lead':lead['name'],'opportunity':res['opportunity'],'window':res['opportunity']['window']},ensure_ascii=False))
