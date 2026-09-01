# -*- coding: utf-8 -*-
"""v30.6 贸易网交接测试：锁定用户反馈的两个生产 bug 与交叉去重规则——

bug1: 网络扩张挖到的新客户经 upsert_leads 入库不带 zone → 全部掉进“未分区”，
      开发池看不到（“开发了29个客户但开发池没有数据”）。
bug2: commit_discovery_lead 硬编码 kind='importer' → 供应商节点被误判成客户，
      供应商数据“没有转移过去”。

规则: 客户二次开发 → 供应商自动去重进库；供应商二次开发 → 客户自动去重进库；
      DISCOVERY_COMMIT 回读自证；network_analysis 基于关系事实表产出分析。
"""
import os, sys, tempfile, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
                  IY_WEB_ENABLED='true')
from core.config import settings
settings.DATABASE_PATH = DBPATH
from core.memory.db import DB
db = DB()


def test_commit_kind_aware():
    """供应商节点必须 kind='supplier' 入库，客户必须 kind='customer'。"""
    r1 = db.commit_discovery_lead({'name': 'Acme Buyer LLC', 'type': 'importer',
                                   'evidence': {'shipments': 9, 'customs': True}}, zone='dev')
    r2 = db.commit_discovery_lead({'name': 'Shenzhen Wax Factory', 'type': 'supplier',
                                   'evidence': {'shipments': 30, 'customs': True}}, zone='dev')
    assert r1['created'] and r2['created']
    l1, l2 = db.get_lead(r1['norm']), db.get_lead(r2['norm'])
    assert l1['kind'] == 'customer' and l1['zone'] == 'dev'
    assert l2['kind'] == 'supplier' and l2['zone'] == 'dev', l2['kind']
    print('PASS commit_kind_aware')


def test_commit_network_entity_dedup():
    """交叉入库原语：新实体进开发池；已存在只合并证据，绝不重置区域。"""
    r1 = db.commit_network_entity('Global Candle Supplier', 'supplier',
                                  evidence={'shipments': 12, 'iy_verified': True}, source='network_expand:d1')
    assert r1['created'] and r1['zone'] == 'dev'
    # 手动转维护池后再次看到：区域绝不被重置
    db.move_lead(r1['norm'], 'maint')
    r2 = db.commit_network_entity('Global Candle Supplier', 'supplier',
                                  evidence={'shipments': 20, 'iy_verified': True}, source='network_expand:d2')
    assert not r2['created']
    l = db.get_lead(r1['norm'])
    assert l['zone'] == 'maint', f"区域被重置: {l['zone']}"
    assert int(l['shipments']) == 20  # 证据合并（票数取大）
    # 同名大小写/空格变化去重
    r3 = db.commit_network_entity('GLOBAL  Candle   Supplier', 'supplier',
                                  evidence={'shipments': 3}, source='x')
    assert not r3['created'] and r3['norm'] == r1['norm']
    print('PASS commit_network_entity_dedup')


def test_expansion_cross_commit():
    """客户二次开发：供应商自动去重进库 + buyer→supplier 边 + 供应商客户 zone=dev。"""
    import core.tools.iy_web as iyw
    from core.tools import expand

    class FakeWeb:
        def __init__(self): self.last_total = 0; self.last_error = ''
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def company_page_for(self, name): return 'https://www.importyeti.com/company/acme-buyer-llc'
        def supplier_page_for(self, name): return ''
        def relationships(self, url, section):
            if url.endswith('/acme-buyer-llc') and section == 'Suppliers':
                return [{'name': 'Ningbo Light Co', 'url': 'https://www.importyeti.com/supplier/ningbo-light-co',
                         'shipments': 15, 'products': 'led candles'}]
            if url.endswith('/ningbo-light-co') and section == 'Customers':
                return [{'name': 'Fresh Buyer Inc', 'url': 'https://www.importyeti.com/company/fresh-buyer-inc',
                         'shipments': 6, 'products': 'led candles'},
                        {'name': 'Acme Buyer LLC', 'url': 'https://www.importyeti.com/company/acme-buyer-llc',
                         'shipments': 9}]
            return []

    iyw.IYWeb = FakeWeb
    iyw.available = lambda: True
    seed = db.get_lead(db._norm('Acme Buyer LLC'))
    stats = expand.run_network(task_id='exp6', seed_norms=[seed['norm']], depth=1, max_new=40)
    assert not stats.get('error'), stats
    # 供应商自动去重进客户数据库（kind=supplier, zone=dev）
    sup_lead = db.get_lead(db._norm('Ningbo Light Co'))
    assert sup_lead and sup_lead['kind'] == 'supplier' and sup_lead['zone'] == 'dev', sup_lead
    # 供应商挖到的新客户直接进开发池（旧 bug：zone 缺失掉进未分区）
    fresh = db.get_lead(db._norm('Fresh Buyer Inc'))
    assert fresh and fresh['zone'] == 'dev', fresh and fresh['zone']
    assert stats['new_leads'] == 1 and stats['new_suppliers'] == 1
    # 两类关系边都在：buyer→supplier 与 supplier→customer
    rels = db.list_relationships(task_id='exp6')
    kinds = {(r['from_name'], r['relation']) for r in rels}
    assert ('Acme Buyer LLC', 'buyer_to_supplier') in kinds
    assert ('Ningbo Light Co', 'supplier_to_customer') in kinds
    # 再次扩张：Fresh Buyer 已在库 → 不重复计数、不重置区域
    db.move_lead(fresh['norm'], 'maint')
    stats2 = expand.run_network(task_id='exp6b', seed_norms=[seed['norm']], depth=1, max_new=40)
    assert stats2['new_leads'] == 0 and stats2['new_suppliers'] == 0
    assert db.get_lead(fresh['norm'])['zone'] == 'maint'
    print('PASS expansion_cross_commit')


def test_supplier_seed_development():
    """供应商的二次开发：供应商种子直接收割其客户，客户去重进开发池。"""
    import core.tools.iy_web as iyw
    from core.tools import expand

    class FakeWeb2:
        def __init__(self): self.last_total = 0; self.last_error = ''
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def company_page_for(self, name): return ''
        def supplier_page_for(self, name):
            return 'https://www.importyeti.com/supplier/ningbo-light-co' if 'ningbo' in name.lower() else ''
        def relationships(self, url, section):
            assert section == 'Customers'
            return [{'name': 'Another Buyer LLC', 'url': '', 'shipments': 4}]

    iyw.IYWeb = FakeWeb2
    iyw.available = lambda: True
    sup_lead = db.get_lead(db._norm('Ningbo Light Co'))
    # 清注册表使该供应商可被重新收割（生产上 21 天内会跳过，这里验证逻辑路径）
    import sqlite3
    with sqlite3.connect(DBPATH) as c:
        c.execute("DELETE FROM iy_nodes WHERE kind='supplier'")
    stats = expand.run_network(task_id='exp6c', seed_norms=[sup_lead['norm']], depth=1, max_new=40)
    assert not stats.get('error'), stats
    another = db.get_lead(db._norm('Another Buyer LLC'))
    assert another and another['kind'] == 'customer' and another['zone'] == 'dev', another
    assert stats['new_leads'] == 1
    print('PASS supplier_seed_development')


def test_network_analysis():
    """贸易网分析：核心供应商/活跃客户/交叉供应商从关系事实表算出。"""
    a = db.network_analysis()
    assert a['relations_total'] > 0
    names = {s['name'] for s in a['top_suppliers']}
    assert 'Ningbo Light Co' in names
    assert any(s['name'] == 'Ningbo Light Co' and s['shared_customers'] >= 2 for s in a['shared_suppliers'])
    assert a['lead_kinds'].get('supplier', 0) >= 2
    print('PASS network_analysis', {k: a[k] for k in ('relations_total', 'lead_kinds')})


def test_commit_readback_verify():
    """DATABASE_COMMIT 回读自证：提交后同库必须读到客户/供应商计数。"""
    from core.runtime import nodes as N
    state = {'task_id': 'commit6', 'classified_entities': [
        {'name': 'Verify Buyer Co', 'type': 'importer', 'source': 'importyeti_penetration',
         'lifecycle': 'CUSTOMER_CONFIRMED', 'product_domain': 'CANDLE',
         'evidence': {'shipments': 5, 'customs': True, 'trade_evidence': True}},
        {'name': 'Verify Supplier Co', 'type': 'supplier', 'source': 'importyeti_penetration',
         'lifecycle': 'SUPPLIER_CONFIRMED', 'product_domain': 'CANDLE',
         'evidence': {'shipments': 8, 'customs': True, 'trade_evidence': True}}]}
    out = N.n_database_commit(state)
    dc = out['database_commit']
    assert dc['dev'] == 1 and dc['dev_suppliers'] == 1, dc
    v = out['commit_verify']
    assert v['probe_ok'] is True
    assert v['dev_customers'] >= 1 and v['dev_suppliers'] >= 1
    assert '客户' in out['_note'] and '供应商' in out['_note']
    print('PASS commit_readback_verify', v)


if __name__ == '__main__':
    test_commit_kind_aware()
    test_commit_network_entity_dedup()
    test_expansion_cross_commit()
    test_supplier_seed_development()
    test_network_analysis()
    test_commit_readback_verify()
    print('ALL v30.6 network handoff tests PASS')
