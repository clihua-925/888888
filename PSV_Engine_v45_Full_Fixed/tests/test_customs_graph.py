import os,sys,tempfile,sqlite3,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))

def setup_db():
    p=tempfile.mktemp(suffix='.db')
    os.environ['DATABASE_PATH']=p
    from core.config import settings
    settings.DATABASE_PATH=p
    from core.memory.db import DB
    DB()
    with sqlite3.connect(p) as c:
        now=time.time()
        rows=[
          ('1','BOL1',now,'Buyer A','buyera','Supplier X','','3406','birthday candles',1,1,0,'','', '', 'test'),
          ('2','BOL2',now-10,'Buyer A','buyera','Supplier X','','3406','number candles',1,1,0,'','', '', 'test'),
          ('3','BOL3',now-20,'Buyer B','buyerb','Supplier X','','3406','spiral candles',1,1,0,'','', '', 'test'),
        ]
        c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
    return p

def test_customs_bidirectional_graph():
    setup_db()
    from core.tools.customs_graph import buyer_to_suppliers,supplier_to_buyers
    sups,rels=buyer_to_suppliers([{'name':'Buyer A'}],3)
    assert any(x['name']=='Supplier X' for x in sups)
    assert rels and rels[0]['source']=='customs_raw'
    buyers,rels2=supplier_to_buyers([{'name':'Supplier X'}],10)
    assert {x['name'] for x in buyers}=={'Buyer A','Buyer B'}
    assert all(x['source']=='customs_raw' for x in rels2)

def test_identity_only_customs_seed_is_kept():
    from core.tools.data_sources.manager import identity_valid
    assert identity_valid({'name':'Buyer Only','type':'importer','evidence':{'customs':True}})
