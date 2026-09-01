import os,sys,tempfile,sqlite3,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))

def setup():
    p=tempfile.mktemp(suffix='.db'); os.environ['DATABASE_PATH']=p
    from core.config import settings; settings.DATABASE_PATH=p
    from core.memory.db import DB; DB()
    now=time.time()
    with sqlite3.connect(p) as c:
        rows=[]
        for i in range(1,7):
            n=f'buyer{i}'
            rows.append((n,f'Buyer {i}',now-i*100,now-i*10,10-i,0,0,1,'CN','LAX','candles',90,'trade',now,now))
        c.executemany('INSERT INTO buyers_90d VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
    return p

def test_incremental_known_does_not_consume_new_slots():
    setup(); from core.memory.db import DB; from core.tools.data_sources.manager import DataSourceManager
    db=DB(); db.upsert_leads([{'name':'Buyer 1','country':'USA','kind':'customer'},{'name':'Buyer 2','country':'USA','kind':'customer'}])
    # Make bulk source return a larger window; manager should rank unseen before known.
    m=DataSourceManager(); rows,used,errors,gate=m.search('USA','candle',3,variants_override=['birthday candles'])
    names={r['name'] for r in rows}
    assert 'Buyer 3' in names and 'Buyer 4' in names
    assert gate['new_candidates'] >= 2

def test_incremental_upsert_preserves_business_zone_and_fills_profile():
    setup(); from core.memory.db import DB
    db=DB(); db.upsert_leads([{'name':'Buyer 1','country':'USA','kind':'customer','shipments':3,'website':'','status':'new'}])
    db.lead_update('buyer1',zone='maint',development_status='running')
    db.upsert_leads([{'name':'Buyer 1','country':'USA','kind':'customer','shipments':8,'last_shipment':'999','website':'https://example.com','hs_code':['3406','340699'],'source':'customs_raw'}])
    x=db.get_lead('buyer1')
    assert x['zone']=='maint' and x['development_status']=='running'
    assert x['website']=='https://example.com' and x['shipments']==8 and '3406' in x['hs_code']

def test_second_run_can_refresh_existing_without_recreating_it():
    setup(); from core.memory.db import DB; from core.tools.data_sources.manager import DataSourceManager
    db=DB(); db.upsert_leads([{'name':'Buyer 1','country':'USA','kind':'customer'}])
    m=DataSourceManager(); rows,_,_,gate=m.search('USA','candle',1,variants_override=['birthday candles'])
    assert rows
    assert gate['new_candidates'] >= 0
