# -*- coding: utf-8 -*-
"""v31.0.1 全流程审查测试：逐环节验证"采集 → 入库 → API → UI 数据源"——

用户问题：开发的客户是否正常迁移到数据库，还是 UI 没更新？
本测试用真实队列 + 真实 HTTP API 逐段回答：
1. 发现任务走完九节点，客户与供应商都必须进 leads（kind 分开）。
2. /api/leads 按 zone/kind/domain 过滤都能取到数据（UI 数据源验证）。
3. 客户详情 API：关系/证据/生命周期齐全。
4. /api/trade-network 与 /api/network-analysis 有真实节点边。
5. 二次开发：客户扩张→供应商去重入库；供应商扩张→客户去重入库。
6. UI 静态审查：前端变量声明、新节点中文名、产品域过滤行存在。
"""
import os, sys, json, time, sqlite3, tempfile, threading, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
    WEBAI_ENABLED='false', IY_WEB_ENABLED='false', IMPORTYETI_ENABLED='false',
    HS_FINDER_ENABLED='false', IMPORTKEY_ENABLED='false', HARVEST_ENABLED='true',
    SCHEDULER_ENABLED='false', GATE_MIN_QUALIFIED='1', OUTREACH_ENABLED='false')
from core.config import settings
settings.DATABASE_PATH = DBPATH
for k in ('EXPERT_MODE','MISSION_DIRECTOR_ENABLED','WEBAI_ENABLED','IY_WEB_ENABLED',
          'IMPORTYETI_ENABLED','HS_FINDER_ENABLED','IMPORTKEY_ENABLED','SCHEDULER_ENABLED','OUTREACH_ENABLED'):
    setattr(settings, k, False)
settings.HARVEST_ENABLED = True; settings.GATE_MIN_QUALIFIED = 1

from core.memory.db import DB
DB()
now = time.time()
with sqlite3.connect(DBPATH) as c:
    rows = [('1','BOL1',now,'Buyer A','buyera','Supplier X','','3406','birthday candles',1,1,0,'CN','NGB','LAX','t'),
            ('2','BOL2',now-10,'Buyer A','buyera','Supplier X','','3406','number candles',1,1,0,'CN','NGB','LAX','t'),
            ('3','BOL3',now-20,'Buyer B','buyerb','Supplier X','','3406','spiral candles',1,1,0,'CN','NGB','LAX','t'),
            ('4','BOL4',now-30,'Buyer C','buyerc','Supplier Y','','3406','jar candles',1,1,0,'CN','SHA','OAK','t')]
    c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)

import core.tools.data_sources.manager as mgr
def fake_search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
    return ([{'name':'Buyer A','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':2,'hs':['3406'],'customs':True,'trade_evidence':True}}],
            ['customs_raw'], [], {'ok':True,'raw':1,'qualified':1,'strong':1,'new_candidates':1,'existing_enriched':0})
mgr.DataSourceManager.search = fake_search

from core.system import PSVSystem
SYS = PSVSystem()
from core.webui import app as webui
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 0), webui.H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def http(path, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', data=data, method=method,
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def test_1_discovery_commits_customers_and_suppliers():
    tid = SYS.start('full flow audit', 'USA', 'candle', 3)
    deadline = time.time() + 90
    while time.time() < deadline:
        t = SYS.get(tid)
        if t and t.get('status') in ('done','failed','done_degraded','failed_gate','error'):
            break
        time.sleep(0.3)
    t = SYS.get(tid)
    assert t['status'] in ('done','done_degraded'), (t['status'], (t.get('result') or {}).get('error'))
    res = t.get('result') or {}
    commit = res.get('database_commit') or {}
    assert commit.get('dev', 0) >= 2, commit          # 客户：Buyer A + 收割的 B/C
    assert commit.get('dev_suppliers', 0) >= 2, commit  # 供应商：Supplier X/Y 必须进库（v31.0.1 补齐）
    v = commit.get('verify') or {}
    assert v.get('probe_ok'), v
    # 回执承诺的数 = 数据库真实的数（回读自证之外再独立验证一次）
    with sqlite3.connect(DBPATH) as c:
        dc = c.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND COALESCE(kind,'')!='supplier'").fetchone()[0]
        ds = c.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND kind='supplier'").fetchone()[0]
    assert dc == v['dev_customers'] and ds == v['dev_suppliers'], (dc, ds, v)
    assert ds >= 2, f'供应商未迁移进库: {ds}'
    print('PASS 1 database_commit 客户%d 供应商%d（回执与库一致）' % (dc, ds))


def test_2_leads_api_views():
    all_dev = http('/api/leads?zone=dev')['leads']
    cust = http('/api/leads?zone=dev&kind=customer')['leads']
    sups = http('/api/leads?zone=dev&kind=supplier')['leads']
    assert len(all_dev) == len(cust) + len(sups), (len(all_dev), len(cust), len(sups))
    names = [l['name'] for l in cust]
    assert 'Buyer A' in names and 'Buyer B' in names, names
    snames = [l['name'] for l in sups]
    assert 'Supplier X' in snames and 'Supplier Y' in snames, snames
    # 产品域过滤
    dom = http('/api/leads?zone=dev&domain=BIRTHDAY_CANDLES')['leads']
    assert any(l['name'] == 'Buyer A' for l in dom), '产品域过滤无数据'
    assert not http('/api/leads?zone=dev&domain=FELT')['leads']
    # 生命周期已随实体落库
    a = [l for l in all_dev if l['name'] == 'Buyer A'][0]
    assert a.get('lifecycle') and a.get('product_domain'), a
    print('PASS 2 leads_api 客户%d 供应商%d 域过滤OK 生命周期=%s' % (len(cust), len(sups), a['lifecycle']))


def test_3_lead_detail_api():
    cust = http('/api/leads?zone=dev&kind=customer')['leads']
    norm_a = [l['norm'] for l in cust if l['name'] == 'Buyer A'][0]
    d = http('/api/leads/' + norm_a)
    assert d['lead']['name'] == 'Buyer A'
    assert d['relationships'], '客户关系未接通'
    assert d['evidence_strength'] == 'strong'
    # 详情页双面板数据源：供应商网络必须能筛出 Supplier X
    rel = d['relationships']
    sup_net = [r for r in rel if (r['relation'] == 'buyer_to_supplier' and r['from_name'] == 'Buyer A')
               or (r['relation'] == 'supplier_to_customer' and r['to_name'] == 'Buyer A')]
    assert any(r['to_name'] == 'Supplier X' or r['from_name'] == 'Supplier X' for r in sup_net), sup_net
    print('PASS 3 lead_detail 关系%d条 供应商网络%d条' % (len(rel), len(sup_net)))


def test_4_network_apis():
    tn = http('/api/trade-network')
    assert len(tn['nodes']) >= 5 and len(tn['edges']) >= 3, tn
    na = http('/api/network-analysis')
    assert na.get('relations_total', 0) >= 3, na
    st = http('/api/stats')
    assert st['dev_suppliers'] >= 2 and st['dev_customers'] >= 2, st
    assert 'BIRTHDAY_CANDLES' in (st.get('product_domains') or []), st.get('product_domains')
    assert st['version'].startswith(('v35','v36','v37','v38','v39','v40')), st['version']
    print('PASS 4 network_apis 节点%d 边%d 域=%s' % (len(tn['nodes']), len(tn['edges']), st['product_domains']))


def test_5_expansion_both_directions():
    """二次开发：客户→供应商去重入库；供应商→客户去重入库。"""
    import core.tools.expand as ex
    import core.tools.iy_web as iyw
    class FakeW:
        def __init__(self): self.last_error = ''
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def company_page_for(self, name): return 'https://www.importyeti.com/company/x-' + name.lower().replace(' ', '-')
        def supplier_page_for(self, name): return 'https://www.importyeti.com/supplier/x-' + name.lower().replace(' ', '-')
        def relationships(self, url, section):
            if '/company/' in url:
                return [{'name': 'Audit Supplier Z', 'shipments': 4, 'url': url + '/s', 'products': 'candles'}]
            return [{'name': 'Audit Buyer D', 'shipments': 2, 'products': 'candles', 'url': url + '/b'}]
    iyw.IYWeb = FakeW; iyw.available = lambda: True
    db = DB()
    # 客户二次开发 → 供应商进库
    buyer = db.get_lead(db._norm('Buyer A'))
    out = ex.run_network(task_id='aud_e1', seed_norms=[buyer['norm']], depth=1, max_new=5)
    assert not out.get('error'), out
    sup_z = db.get_lead(db._norm('Audit Supplier Z'))
    assert sup_z and sup_z['kind'] == 'supplier', '客户扩张的供应商未入库'
    # 供应商二次开发 → 客户进库
    out2 = ex.run_network(task_id='aud_e2', seed_norms=[sup_z['norm']], depth=1, max_new=5)
    assert not out2.get('error'), out2
    buyer_d = db.get_lead(db._norm('Audit Buyer D'))
    assert buyer_d and buyer_d.get('kind') != 'supplier', '供应商扩张的客户未入库'
    # 去重：重复扩张同一客户不产生重复行
    before = len(db.list_leads(limit=1000))
    ex.run_network(task_id='aud_e3', seed_norms=[buyer['norm']], depth=1, max_new=5)
    after = len(db.list_leads(limit=1000))
    assert after <= before + 1, (before, after)
    print('PASS 5 expansion 双向去重入库 供应商Z+客户D')


def test_6_ui_static():
    html = webui.HTML
    # 前端变量声明（selectedLeadNorm 未声明曾导致整个客户列表渲染崩溃）
    assert 'selectedLeadNorm=null' in html
    assert 'currentDomain' in html and 'domain_tabs' in html
    # 新节点中文名
    for label in ('产品定义','贸易定位策略','海关节点采集','贸易关系建立','证据验证',
                  '企业实体解析','贸易网络扩张','资源分类','贸易资产入库'):
        assert label in html, label
    # 贸易网络视图与双网络面板
    assert 'dash_net_graph' in html and '供应商网络' in html and '客户网络' in html
    # JS 语法校验（node 可用时）
    import re, shutil, subprocess
    m = re.search(r'<script>(.*)</script>', html, re.S)
    assert m
    if shutil.which('node'):
        p = '/tmp/_v31_ui_check.js'
        open(p, 'w', encoding='utf-8').write(m.group(1))
        r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[:500]
        print('PASS 6 ui_static 变量声明+节点名+双面板+JS语法(node --check)')
    else:
        print('PASS 6 ui_static 变量声明+节点名+双面板（无 node，跳过语法校验）')


if __name__ == '__main__':
    try:
        test_1_discovery_commits_customers_and_suppliers()
        test_2_leads_api_views()
        test_3_lead_detail_api()
        test_4_network_apis()
        test_5_expansion_both_directions()
        test_6_ui_static()
        print('V31_FULL_FLOW_AUDIT_ALL_OK')
    finally:
        srv.shutdown()
