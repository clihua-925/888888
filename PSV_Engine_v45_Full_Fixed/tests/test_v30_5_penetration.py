# -*- coding: utf-8 -*-
"""v30.5 节点渗透测试：锁定用户两次强调的第一链设计 ——
关键词在 ImportYeti 锁定节点 → 递归渗透（节点的供应商 → 供应商的客户 → …）→
残片全保留（不按 quantity 截断）→ 每一环都在 IY 页面上完成（IY=验证标准）→ 交叉成网。

覆盖：BFS 深度展开 / 环防护 / 页访预算熔断 / 节点注册表去重 / 全链不按数量截断。
"""
import os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
                  IY_WEB_ENABLED='true', IMPORTYETI_ENABLED='false', HS_FINDER_ENABLED='false')
from core.config import settings
settings.DATABASE_PATH = DBPATH
settings.IY_WEB_ENABLED = True
settings.IY_PENETRATION_DEPTH = 2
settings.IY_PAGE_BUDGET = 25
settings.COLLECT_MAX_NODES = 300

from core.memory.db import DB
DB()

from core.trade_graph import iy_penetration, iy_network as iyn


class FakeWeb:
    """模拟 ImportYeti 站点结构：
    ACME(company) --Suppliers--> S1, S2
    S1(supplier)  --Customers--> B1, B2, ACME(环回)
    S2(supplier)  --Customers--> B1(重复), B3
    B*(company)   --Suppliers--> S1(环回)
    """
    PAGES = {
        'https://www.importyeti.com/company/acme-imports': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/supplier-one',
             'shipments': 30, 'products': 'candles', 'hs': ['3406']},
            {'name': 'Supplier Two', 'url': 'https://www.importyeti.com/supplier/supplier-two',
             'shipments': 10, 'products': 'wax', 'hs': ['3406']}]),
        'https://www.importyeti.com/supplier/supplier-one': ('Customers', [
            {'name': 'Buyer One', 'url': 'https://www.importyeti.com/company/buyer-one', 'shipments': 12},
            {'name': 'Buyer Two', 'url': 'https://www.importyeti.com/company/buyer-two', 'shipments': 8},
            {'name': 'Acme Imports', 'url': 'https://www.importyeti.com/company/acme-imports', 'shipments': 50}]),
        'https://www.importyeti.com/supplier/supplier-two': ('Customers', [
            {'name': 'Buyer One', 'url': 'https://www.importyeti.com/company/buyer-one', 'shipments': 3},
            {'name': 'Buyer Three', 'url': 'https://www.importyeti.com/company/buyer-three', 'shipments': 5}]),
        'https://www.importyeti.com/company/buyer-one': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/supplier-one', 'shipments': 30}]),
        'https://www.importyeti.com/company/buyer-two': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/supplier-one', 'shipments': 30}]),
        'https://www.importyeti.com/company/buyer-three': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/supplier-one', 'shipments': 30}]),
    }

    def __init__(self):
        self.last_total = 0
        self.last_error = ''
        self.calls = []  # (url, section) 真实页访记录

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def search(self, q, limit=10):
        return [{'name': 'Acme Imports', 'url': 'https://www.importyeti.com/company/acme-imports',
                 'kind': 'company', 'shipments': 50}]

    def relationships(self, url, section):
        self.calls.append((url, section))
        entry = self.PAGES.get(url)
        if not entry:
            return []
        want, rows = entry
        assert section == want, f'板块方向错误: {url} 应取 {want} 实取 {section}'
        self.last_total = len(rows)
        return rows

    def company_page_for(self, name): return ''
    def supplier_page_for(self, name): return ''


LOCKED = [{'name': 'Acme Imports', 'url': 'https://www.importyeti.com/company/acme-imports',
           'kind': 'company', 'shipments': 50}]


def _clear_registry():
    import sqlite3
    with sqlite3.connect(DBPATH) as c:
        c.execute('DELETE FROM iy_nodes')


def test_bfs_depth_and_cycle():
    """图谱必须展开到深度2：ACME(0) → S1/S2(1) → B1/B2/B3(2)；环回节点绝不重复打开。"""
    _clear_registry()
    w = FakeWeb()
    out = iy_penetration.penetrate(LOCKED, w, task_id='t1')
    by_name = {n['name']: n for n in out['nodes']}
    assert by_name['Acme Imports']['evidence']['depth'] == 0
    assert by_name['Supplier One']['evidence']['depth'] == 1
    assert by_name['Supplier Two']['evidence']['depth'] == 1
    for b in ('Buyer One', 'Buyer Two', 'Buyer Three'):
        assert b in by_name, f'深度2残片丢失: {b}'
        assert by_name[b]['evidence']['depth'] == 2
        assert by_name[b]['evidence']['iy_verified'] is True  # 每一环都在 IY 页面上 = IY 验证
        assert by_name[b]['evidence']['customer_relation']  # 残片带关系来源
    # 环防护：同一 URL 的页访最多一次（ACME/B1 都被多个上游指回）
    urls = [u for u, _s in w.calls]
    assert len(urls) == len(set(urls)), f'出现重复页访: {urls}'
    assert len(urls) == 6  # ACME + S1 + S2 + B1 + B2 + B3
    # 两种方向的关系都在
    kinds = {r['relation'] for r in out['relations']}
    assert kinds == {'buyer_to_supplier', 'supplier_to_customer'}
    # 交叉边：B1 同时挂在 S1 和 S2 下 → 信息网交叉
    b1_from = {r['from_name'] for r in out['relations'] if r['to_name'] == 'Buyer One'}
    assert b1_from == {'Supplier One', 'Supplier Two'}
    assert out['stats']['stopped_by'] == 'frontier_drained'
    assert out['stats']['pages'] == 6
    print('PASS bfs_depth_and_cycle nodes=%d relations=%d' % (len(out['nodes']), len(out['relations'])))


def test_page_budget_stop():
    """页访预算耗尽即停，已挖的关系全部保留（不丢碎片）。"""
    _clear_registry()
    w = FakeWeb()
    budget = iyn.PageBudget(2)
    out = iy_penetration.penetrate(LOCKED, w, budget=budget, task_id='t2')
    assert out['stats']['stopped_by'] == 'page_budget'
    assert out['stats']['pages'] <= 2
    assert len(w.calls) <= 2
    assert len(out['relations']) >= 2  # 第一页拉出的供应商关系已保留
    print('PASS page_budget_stop pages=%d relations=%d' % (out['stats']['pages'], len(out['relations'])))


def test_registry_dedup_across_runs():
    """节点注册表：21天内访问过的节点跨任务不再打开（防枯竭）。"""
    _clear_registry()
    w1 = FakeWeb()
    iy_penetration.penetrate(LOCKED, w1, task_id='t3a')
    w2 = FakeWeb()
    out2 = iy_penetration.penetrate(LOCKED, w2, task_id='t3b')
    assert out2['stats']['skipped_fresh'] >= 1
    assert len(w2.calls) == 0, f'注册表未生效，重复页访: {w2.calls}'
    # 但节点残片仍然作为候选返回（图谱不丢信息）
    assert any(n['name'] == 'Acme Imports' for n in out2['nodes'])
    print('PASS registry_dedup skipped=%d' % out2['stats']['skipped_fresh'])


def test_collect_chain_no_quantity_truncation(monkeypatch=None):
    """全链：渗透残片不按 quantity 截断；渗透边进入图谱；stats 带 penetration。"""
    import core.tools.iy_web as iyw
    import core.tools.data_sources.manager as mgr_mod
    from core.trade_graph import customs_node_pipeline as cnp

    iyw.IYWeb = FakeWeb
    iyw.available = lambda: True

    class FakeMgr:
        last_evolution = {}

        def search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
            return ([{'name': 'Buyer One', 'country': market, 'type': 'importer', 'source': 'customs_raw',
                      'strength': 5, 'evidence': {'shipments': 4, 'customs': True, 'trade_evidence': True}}],
                    ['customs_raw'], [], {'ok': True, 'raw': 1, 'new_candidates': 1, 'existing_enriched': 0})

    orig = mgr_mod.DataSourceManager
    mgr_mod.DataSourceManager = FakeMgr
    try:
        # 清理注册表，保证本次渗透真实发生
        _clear_registry()
        pipe = cnp.CustomsNodePipeline()
        companies, used, errors, gate, graph, stats = pipe.run(
            'USA', 'candles', 3, queries=['candle importer'], task_id='t4')
        names = {c['name'] for c in companies}
        # quantity=3 但图谱节点必须完整展开（6个节点 + 碎片合并）
        assert len(companies) > 3, f'残片被 quantity 截断: {len(companies)}'
        assert {'Acme Imports', 'Supplier One', 'Supplier Two', 'Buyer One', 'Buyer Two', 'Buyer Three'} <= names
        # Buyer One 被渗透 + customs_raw 双源命中 → 来源合并、iy_verified 保留
        b1 = next(c for c in companies if c['name'] == 'Buyer One')
        assert 'customs_raw' in b1['source'] and 'importyeti_penetration' in b1['source']
        assert b1['evidence']['iy_verified'] is True
        assert b1['evidence']['shipments'] >= 12  # 取渗透层更大的票数
        # 渗透统计与边
        assert stats['penetration']['nodes'] >= 6
        assert stats['penetration']['relations'] >= 7
        assert 'importyeti_penetration' in used
        edges = graph.to_dict().get('edges') or []
        assert edges, '渗透关系边未入图'
        assert any(e.get('relation') == 'supplier_to_customer' for e in edges)
        print('PASS collect_chain companies=%d edges=%d pen=%s' % (len(companies), len(edges), stats['penetration']))
    finally:
        mgr_mod.DataSourceManager = orig


if __name__ == '__main__':
    test_bfs_depth_and_cycle()
    test_page_budget_stop()
    test_registry_dedup_across_runs()
    test_collect_chain_no_quantity_truncation()
    print('ALL v30.5 penetration tests PASS')
