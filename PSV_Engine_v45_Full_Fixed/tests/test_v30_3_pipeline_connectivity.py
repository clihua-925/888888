# -*- coding: utf-8 -*-
"""v30.3 全链路接通测试：发现 → 入池 → 客户数据库(真实HTTP) → 开发信序列 → 网络扩张 → 节点注册表。

复现并锁定用户反馈的问题：任务显示"新开发池29"而客户数据库为空。
本测试走真实路径：PSVSystem 队列 worker → Orchestrator → DATABASE_COMMIT →
webui HTTP API(/api/leads?zone=dev /api/stats) → 开发信序列(假模型) → expand 网络扩张(模拟IY)。
"""
import os, sys, json, time, sqlite3, tempfile, threading, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
    WEBAI_ENABLED='false', IY_WEB_ENABLED='false', IMPORTYETI_ENABLED='false',
    HS_FINDER_ENABLED='false', IMPORTKEY_ENABLED='false', HARVEST_ENABLED='true',
    SCHEDULER_ENABLED='false', GATE_MIN_QUALIFIED='1', OUTREACH_ENABLED='false',
    WEB_PORT='0')
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


def http(port, path, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data, method=method,
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def test_full_connectivity():
    from core.system import PSVSystem
    sys_ = PSVSystem()
    # 1) 真实队列路径：POST /api/task 等效入口
    tid = sys_.start('connectivity test', 'USA', 'candle', 3)
    deadline = time.time() + 60
    while time.time() < deadline:
        t = sys_.get(tid)
        if t and t.get('status') in ('done','failed','done_degraded','failed_gate','error'):
            break
        time.sleep(0.3)
    t = sys_.get(tid)
    assert t['status'] in ('done','done_degraded'), (t['status'], (t.get('result') or {}).get('error'))
    commit = (t.get('result') or {}).get('database_commit') or {}
    assert commit.get('dev', 0) >= 1, commit

    # 2) 真实 HTTP API 路径：客户数据库页面看到的就是这个接口
    from core.webui import app as webui
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(('127.0.0.1', 0), webui.H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        stats = http(port, '/api/stats')
        assert stats['leads_total'] >= 3 and stats['dev_total'] >= 1, stats
        assert stats.get('db_path') == DBPATH, stats  # 界面必须能暴露当前数据库身份
        leads = http(port, '/api/leads?zone=dev')
        names = [l['name'] for l in leads['leads']]
        assert 'Buyer A' in names and 'Buyer B' in names, names
        # 详情接口（客户详情页）：关系与证据事件已接通
        norm_a = [l['norm'] for l in leads['leads'] if l['name'] == 'Buyer A'][0]
        detail = http(port, '/api/leads/' + norm_a)
        assert detail['lead']['name'] == 'Buyer A'
        assert detail['relationships'], '客户↔供应商关系未接通'
        assert detail['evidence_strength'] == 'strong'

        # 3) 开发信序列（第二流程）：假模型走完整 DEV 链
        import core.runtime.development as dev
        dev.auditor.audit_and_update = lambda lead, db=None, use_ai=True, webai=None: (dict(lead, shipments=3), {'verdict':'pass'})
        # v37：ENRICH/CONTACT 节点会走真实网络（bing/官网抓取）——连通性测试屏蔽外部IO，保持自持与确定性
        import core.intelligence.waterfall as wf
        wf._fetch = lambda url, timeout=15: ''
        import core.tools.contact_finder as cf
        cf.ContactFinder._search_website_by_company = lambda self, name, country='USA': None
        class FakeModel:
            def chat(self, *a, **k):
                return 'Subject: Sample idea for your candle line\n\nHi team, we are a candle factory in Ningjin offering free samples, fast quotation, flexible capacity and factory direct pricing for importers. Reply for our catalog and a free sample pack today.'
        import core.model.client as mc
        mc.ModelClient = FakeModel
        res = http(port, '/api/development', 'POST', {'lead_norm': norm_a})
        dev_tid = res['task_id']
        assert dev_tid.startswith('dev-'), res
        deadline = time.time() + 60
        while time.time() < deadline:
            dt_ = sys_.get(dev_tid)
            if dt_ and dt_.get('status') in ('done','failed'):
                break
            time.sleep(0.3)
        dt_ = sys_.get(dev_tid)
        assert dt_['status'] == 'done', (dt_['status'], (dt_.get('result') or {}).get('error'))
        msgs = DB().list_messages(norm_a)
        assert any(m['draft'] == 1 for m in msgs), '开发信草稿未生成'
        lead2 = DB().get_lead(norm_a)
        assert lead2.get('opportunity_score') is not None, '需求机会评分未写回客户'
    finally:
        srv.shutdown()
    print('CONNECTIVITY_OK discovery->leads->api->development')


def test_iy_network_registry_and_expand():
    from core.trade_graph import iy_network as iyn
    iyn.mark_node('buyera', 'company', slug='buyer-a', url='https://www.importyeti.com/company/buyer-a', shipments=5, run_id='t')
    assert iyn.node_fresh('buyera', 'company') is True
    assert iyn.node_fresh('nobody', 'company') is False
    assert iyn.node_url('buyera', 'company').endswith('/company/buyer-a')
    b = iyn.PageBudget(2)
    assert b.take('a') and b.take('b') and not b.take('c') and b.exhausted

    # 交叉验证标记：IY 命中→iy_verified；IY+其他源→cross_validated；非IY候选保留不动
    tagged = iyn.tag_verification([
        {'name':'X','source':'importyeti_web','evidence':{}},
        {'name':'Y','source':'customs_raw | importyeti_web','evidence':{}},
        {'name':'Z','source':'customs_raw','evidence':{}}])
    assert tagged[0]['evidence'].get('iy_verified') and not tagged[0]['evidence'].get('cross_validated')
    assert tagged[1]['evidence'].get('cross_validated')
    assert not tagged[2]['evidence'].get('iy_verified')

    # 网络扩张走 company_page_for / supplier_page_for，不猜 slug；注册表去重生效
    calls = []
    class FakeW:
        def __init__(self): self.last_error = ''
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def company_page_for(self, name): calls.append(('company_page_for', name)); return 'https://www.importyeti.com/company/' + name.lower().replace(' ', '-')
        def supplier_page_for(self, name): calls.append(('supplier_page_for', name)); return 'https://www.importyeti.com/supplier/' + name.lower().replace(' ', '-')
        def relationships(self, url, section):
            calls.append(('rel', url, section))
            if section == 'Suppliers':
                return [{'name':'New Supplier Q','shipments':7,'url':'https://www.importyeti.com/supplier/new-supplier-q','products':'candles'}]
            return [{'name':'Brand New Buyer LLC','shipments':3,'products':'candles','url':'https://www.importyeti.com/company/brand-new-buyer-llc'}]
    import core.tools.expand as ex
    import core.tools.iy_web as iyw
    iyw.IYWeb = FakeW; iyw.available = lambda: True
    db = DB()
    lead = db.get_lead(db._norm('Buyer C'))
    out = ex.run_network(task_id='exp1', seed_norms=[lead['norm']], depth=1, max_new=5)
    assert not out.get('error'), out
    assert out['new_leads'] >= 1, out
    assert db.get_lead(db._norm('Brand New Buyer LLC')), '扩张新客户未入库'
    # 第二次跑同一节点：注册表命中，不再访问任何页面（防资源枯竭）
    calls.clear()
    out2 = ex.run_network(task_id='exp2', seed_norms=[lead['norm']], depth=1, max_new=5)
    assert not any(c[0] == 'rel' for c in calls), calls
    print('IY_NETWORK_OK registry+budget+verification+expand')


if __name__ == '__main__':
    test_full_connectivity()
    test_iy_network_registry_and_expand()
    print('V30_3_CONNECTIVITY_ALL_OK')
