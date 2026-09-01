# -*- coding: utf-8 -*-
"""v35 统一整改验收：契约注册表 + 伪实体拦截 + 统一生命周期 + 单一数据源
+ BIRTHDAY_CANDLES 全链路真实验收 + 五者一致性（任务结果=节点结果=数据库=API=UI 数据）。

检查点：
 1  Node Contract Registry：9 节点注册齐备，八要素完整
 2  契约硬校验：空字段不得冒充成功（缺 output ⇒ fail）
 3  伪实体拦截：国家/城市/港口/占位文本不得成为公司实体
 4  统一生命周期：迁移白名单 + won 证据门槛 + 审计日志
 5  单一数据源：DATABASE_PATH 绝对化 + data_root_info 事实
 6  BIRTHDAY_CANDLES 全链验收：9 节点 SUCCESS + 三类资产 + 无伪实体入库
 7  五者一致性：任务回执数量 == 数据库实际数量 == API 读模型数量
"""
import os, sys, json, time, sqlite3, tempfile
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
db = DB()
now = time.time()
# BIRTHDAY_CANDLES 真实贸易形态（含一行 notify/港口伪实体诱饵）
with sqlite3.connect(DBPATH) as c:
    rows = [
        ('1','B1',now,'Party City Imports','partycityimports','Shantou Candle Works','','3406','birthday candles spiral',3,3,0,'CN','SWA','LAX','t'),
        ('2','B2',now-10,'Party City Imports','partycityimports','Shantou Candle Works','','3406','birthday number candles',2,2,0,'CN','SWA','LAX','t'),
        ('3','B3',now-20,'Celebration Depot LLC','celebrationdepot','Wax Bright Manufacturing','','3406','birthday cake candles',1,1,0,'CN','NGB','OAK','t'),
        ('4','B4',now-30,'Cake Decor Trading','cakedecortrading','Shantou Candle Works','','3406','birthday candles set',2,2,0,'CN','SWA','NYC','t'),
        ('5','B5',now-40,'Cake Decor Trading','cakedecortrading','Tacoma','','3406','birthday candles',1,1,0,'CN','XGN','LAX','t'),  # 伪实体诱饵：港口被写进 shipper
        ('6','B6',now-50,'United States of America','usa','Wax Bright Manufacturing','','3406','birthday candles',1,1,0,'CN','NGB','LAX','t'),  # 伪实体诱饵：国家被写进 importer
    ]
    c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)

import core.tools.data_sources.manager as mgr
def fake_search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
    return ([{'name':'Party City Imports','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':5,'hs':['3406'],'customs':True,'trade_evidence':True,'products':'birthday candles spiral'}},
             {'name':'Cake Decor Trading','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':3,'hs':['3406'],'customs':True,'trade_evidence':True,'products':'birthday candles set'}}],
            ['customs_raw'], [], {'ok':True,'raw':2,'qualified':2,'strong':2,'new_candidates':2,'existing_enriched':0})
mgr.DataSourceManager.search = fake_search

from core.system import PSVSystem
SYS = PSVSystem()


def test_1_contract_registry():
    from core.runtime import contracts, graph
    assert set(contracts.CONTRACTS) == set(graph.ORDER), '每个正式节点必须有注册契约'
    for n, c in contracts.CONTRACTS.items():
        for k in ('input','responsibility','output','success','failure','blocking','side_effects','db_write'):
            assert c.get(k) is not None, (n, k)
    snap = contracts.registry_snapshot()
    assert len(snap) == 9 and snap['DATABASE_COMMIT']['db_write'].startswith('SOLE-WRITER')
    print('PASS 1 Node Contract Registry：9 节点八要素齐备')


def test_2_contract_hard_validation():
    from core.runtime import contracts
    # 空字段冒充成功 ⇒ 必须失败
    ok, issues, _ = contracts.validate('CUSTOMS_NODE_COLLECTION', {'companies': [], 'trade_nodes': []}, {})
    assert not ok and any('companies' in i for i in issues), issues
    ok, issues, _ = contracts.validate('DATABASE_COMMIT', {'database_commit': {}, 'commit_verify': {}}, {})
    assert not ok, issues
    # 真实产物 ⇒ 通过
    ok, issues, warns = contracts.validate('PRODUCT_DEFINITION',
        {'icp': {'x': 1}, 'product_profile': {'x': 1}, 'product_domain': {'key': 'BIRTHDAY_CANDLES'}}, {})
    assert ok and any('input' in w for w in warns), (issues, warns)  # 输入缺失仅警告（软校验）
    print('PASS 2 契约硬校验：空产物拒绝成功 · 输入缺失只警告')


def test_3_geo_noncompany_block():
    from core.trade_graph.trade_node import is_non_company_name
    for bad in ('United States of America', 'Tacoma', 'Asheboro', 'To Order', 'Houston TX', 'China'):
        assert is_non_company_name(bad), bad
    for good in ('El Dorado Furniture', 'Shantou Candle Works', 'Party City Imports'):
        assert not is_non_company_name(good), good
    # 实体解析兜底：伪实体不进入公司实体
    from core.runtime import nodes as N
    out = N.n_entity_resolution({'task_id': 'v35er', 'companies': [
        {'name': 'United States of America', 'type': 'importer', 'evidence': {'shipments': 1}},
        {'name': 'Real Buyer Co', 'type': 'importer', 'evidence': {'shipments': 2}}], 'new_companies': []})
    names = {e['name'] for e in out['company_entities']}
    assert 'United States of America' not in names and 'Real Buyer Co' in names, names
    assert out['entity_resolution']['non_entity_filtered'] == 1
    print('PASS 3 伪实体拦截：地理/占位名精确拦截，真实公司零误伤')


def test_4_unified_lifecycle():
    from core.domain import lifecycle
    db.upsert_leads([{'name': 'Lifecycle Probe Co', 'kind': 'customer', 'source': 'customs_raw'}])
    n = db._norm('Lifecycle Probe Co')
    # 非法迁移拒绝（pool→won 跳过开发/维护）
    r = db.move_lead(n, 'won')
    assert not r['ok'] and 'illegal transition' in r['error'], r
    # 合法迁移 + 审计日志
    assert db.move_lead(n, 'pending')['ok']
    assert db.move_lead(n, 'dev')['ok']
    assert db.move_lead(n, 'won')['ok']  # dev→won 合法
    ev = db.list_lead_events(n)
    assert [e['to_zone'] for e in reversed(ev)] == ['pending', 'dev', 'won'], ev
    assert all(e['actor'] == 'ui' for e in ev)
    # won→maint 合法；discard→pending 恢复通道
    assert db.move_lead(n, 'maint')['ok'] and db.move_lead(n, 'discard')['ok'] and db.move_lead(n, 'pending')['ok']
    print('PASS 4 统一生命周期：白名单迁移 + won 门槛 + 审计日志 %d 条' % len(db.list_lead_events(n)))


def test_5_single_data_root():
    assert os.path.isabs(settings.DATABASE_PATH), 'DATABASE_PATH 必须绝对化（杜绝 cwd 漂移出第二个库）'
    info = settings.data_root_info()
    assert info['database'] == settings.DATABASE_PATH and info['data_root'] == os.path.dirname(settings.DATABASE_PATH)
    # 全代码库 sqlite 连接点必须只认 settings.DATABASE_PATH
    import subprocess
    hits = subprocess.run(['grep', '-rln', 'sqlite3.connect', str(ROOT/'core')], capture_output=True, text=True).stdout.split()
    for f in hits:
        src = open(f).read()
        assert 'DATABASE_PATH' in src or 'self.path' in src or 'self.db' in src, f
    print('PASS 5 单一数据源：绝对路径 + %d 个连接点全部指向 settings.DATABASE_PATH' % len(hits))


_FULL = None
def _full():
    global _FULL
    if _FULL is None:
        tid = SYS.start('v35 birthday candles acceptance', 'USA', 'birthday candles', 5)
        deadline = time.time() + 120
        while time.time() < deadline:
            t = SYS.get(tid)
            if t and t.get('status') in ('done', 'failed', 'done_degraded', 'failed_gate', 'error'):
                break
            time.sleep(0.3)
        t = SYS.get(tid)
        assert t['status'] in ('done', 'done_degraded'), (t['status'], (t.get('result') or {}).get('error'))
        _FULL = (tid, t.get('result') or {})
    return _FULL


def test_6_birthday_candles_acceptance():
    tid, res = _full()
    from core.runtime import graph
    ns = res.get('node_status') or {}
    assert set(ns) == set(graph.ORDER)
    assert all(v.get('status') == 'SUCCESS' for v in ns.values()), ns  # 每节点契约校验通过
    ho = res.get('handoffs') or {}
    assert set(ho) == set(graph.ORDER)
    assert all(h.get('contract_version') == 'v34.0' and h.get('payload_checksum') for h in ho.values())
    commit = res.get('database_commit') or {}
    assert commit.get('dev', 0) + commit.get('dev_both', 0) >= 2, commit
    assert commit.get('dev_suppliers', 0) >= 2, commit
    assert commit.get('edges', 0) >= 3, commit.get('edges')
    # 伪实体绝不入库：leads / relationships / trade_nodes 都不含地理名
    with sqlite3.connect(DBPATH) as c:
        bad_leads = c.execute("SELECT name FROM leads WHERE name IN ('Tacoma','United States of America')").fetchall()
        bad_edges = c.execute("SELECT from_name,to_name FROM relationships WHERE from_name IN ('Tacoma','United States of America') OR to_name IN ('Tacoma','United States of America')").fetchall()
        bad_nodes = c.execute("SELECT name FROM trade_nodes WHERE name IN ('Tacoma','United States of America')").fetchall()
        n_events = c.execute('SELECT COUNT(*) FROM lead_events').fetchone()[0]
    assert not bad_leads and not bad_edges and not bad_nodes, (bad_leads, bad_edges, bad_nodes)
    assert n_events >= 1, 'DATABASE_COMMIT 首次入库分区必须写审计日志'
    print('PASS 6 BIRTHDAY_CANDLES 全链：9 节点 SUCCESS · 客户/供应商/边/证据齐备 · 伪实体零入库 · 审计日志 %d 条' % n_events)


def test_7_five_way_consistency():
    tid, res = _full()
    commit = res.get('database_commit') or {}
    # 任务结果 == 数据库
    with sqlite3.connect(DBPATH) as c:
        db_edges = c.execute('SELECT COUNT(*) FROM relationships WHERE task_id=?', (tid,)).fetchone()[0]
    assert db_edges == commit.get('edges'), (db_edges, commit.get('edges'))
    # 数据库 == API 读模型
    from core.webui.app import _stats
    st = _stats()
    assert st['db_path'] == settings.DATABASE_PATH
    with sqlite3.connect(DBPATH) as c:
        real_dev_c = c.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND kind IN ('customer','both')").fetchone()[0]
        real_dev_s = c.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND kind IN ('supplier','both')").fetchone()[0]
    assert st['dev_customers'] == real_dev_c and st['dev_suppliers'] == real_dev_s, (st['dev_customers'], real_dev_c)
    assert st['graph_relationships'] >= db_edges
    # UI 数据源唯一：HTML 渲染标签与契约注册表一致
    html_src = open(ROOT/'core/webui/app.py', encoding='utf-8').read()
    from core.runtime import contracts
    for n in contracts.CONTRACTS:
        assert ("'%s'" % n) in html_src, n
    print('PASS 7 五者一致：回执边 %d == 库边 %d · API 开发池 %d/%d == 库 %d/%d · UI 标签==契约注册表' % (
        commit.get('edges'), db_edges, st['dev_customers'], st['dev_suppliers'], real_dev_c, real_dev_s))


if __name__ == '__main__':
    test_1_contract_registry()
    test_2_contract_hard_validation()
    test_3_geo_noncompany_block()
    test_4_unified_lifecycle()
    test_5_single_data_root()
    test_6_birthday_candles_acceptance()
    test_7_five_way_consistency()
    print('V35_UNIFICATION_ALL_OK (BIRTHDAY_CANDLES 全链路验收 · 7 检查点)')
