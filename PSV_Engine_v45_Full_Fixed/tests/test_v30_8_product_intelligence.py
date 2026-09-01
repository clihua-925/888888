# -*- coding: utf-8 -*-
"""v30.8 Trade Knowledge Graph 第一入口测试：
1. Product Intelligence：珐琅锅不能只搜 enamel pot——档案必须含同义词/商业名/排除词；
   LLM 离线时确定性兜底完整可用；
2. 排除词净化：enamel paint / dental enamel 被删，enamel cookware importer 保留；
3. HS 策略：候选集→历史贸易验证只标注不过滤（宽覆盖）；
4. Trade Edge 真实列：shipment_count/hs/product/first_seen/last_seen 落列且可累加；
5. 统一 Evidence 层：非 IY 来源碎片也进 trade_nodes 池；图谱口径指标齐全。
"""
import os, sys, tempfile, sqlite3, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
                  IY_WEB_ENABLED='false', WEBAI_ENABLED='false', LLM_BASE_URL='http://127.0.0.1:1')
from core.config import settings
settings.DATABASE_PATH = DBPATH
from core.memory.db import DB
db = DB()

from core.config.industry import save_industry
save_industry({'key': 'enamel_pot', 'name': '珐琅锅', 'name_en': 'Enamel Pot',
               'search_terms': 'enamel pot,enamel cookware,enameled cookware,enamel casserole,camp cookware,kitchenware',
               'hs_codes': '7323,6911', 'keywords': 'enamel cookware,cast iron cookware',
               'exclusions': 'enamel paint,dental enamel,nail enamel',
               'materials': 'cast iron', 'applications': 'camping,kitchen'})


def test_product_profile_wide_and_deterministic():
    """LLM 离线（base 指向死端口）时档案仍完整：同义词+商业名+材料+应用+排除词。"""
    from core.trade_graph import product_intelligence as pi
    p = pi.build_product_profile('enamel_pot')  # LLM 必失败 → 确定性兜底
    assert p['llm_enriched'] is False  # 明确标注未增强
    for w in ('enamel cookware', 'enameled cookware', 'enamel casserole', 'camp cookware', 'kitchenware'):
        assert w in [s.lower() for s in p['synonyms']], w
    # 内置规则生成商业采购名
    assert any('wholesale' in c or 'bulk' in c or 'oem' in c.lower() for c in p['commercial_names'])
    assert set(p['exclusions']) == {'enamel paint', 'dental enamel', 'nail enamel'}
    assert set(p['hs_candidates']) == {'7323', '6911'}
    qs = pi.expand_queries(p)
    assert len(qs) >= 8  # 宽覆盖不缩量
    assert qs[0] == 'enamel pot'
    print('PASS product_profile_wide_and_deterministic variants=%d' % len(qs))


def test_exclusion_purify():
    from core.tools import trade_filter
    cands = [
        {'name': 'Enamel Cookware Imports LLC', 'type': 'importer', 'evidence': {'shipments': 5}},
        {'name': 'Enamel Paint Depot', 'type': 'importer', 'evidence': {'shipments': 3, 'products': 'enamel paint supplies'}},
        {'name': 'Dental Enamel Research Institute', 'evidence': {'products': 'dental enamel study'}},
    ]
    kept, dropped = trade_filter.purify(cands, exclusions=['enamel paint', 'dental enamel'])
    assert [c['name'] for c in kept] == ['Enamel Cookware Imports LLC']
    reasons = [r for _c, r in dropped]
    assert any('排除词命中:enamel paint' in r for r in reasons)
    assert any('排除词命中:dental enamel' in r for r in reasons)
    # 不带排除词时行为不变（向后兼容）
    kept2, _ = trade_filter.purify(cands)
    assert len(kept2) >= 1
    print('PASS exclusion_purify')


def test_hs_validation_annotation_only():
    """历史验证只标注：无记录的 HS 保留为未验证候选，不被过滤。"""
    from core.trade_graph import product_intelligence as pi
    now = time.time()
    with sqlite3.connect(DBPATH) as c:
        c.execute("INSERT INTO customs_raw(bol,ts,importer,hs,descr,created_at) VALUES('B1',?,'X','7323.93','enamel cookware',?)", (now, now))
    v = pi.validate_hs(['7323', '6911'])
    assert v['7323']['validated'] is True and v['7323']['rows'] >= 1
    assert v['6911']['validated'] is False and v['6911']['rows'] == 0
    assert set(v.keys()) == {'7323', '6911'}  # 未验证也保留在集合里
    print('PASS hs_validation_annotation_only', v)


def test_trade_edge_columns():
    """边的 shipment_count/hs/product/first_seen/last_seen 提升为真实列，重复边累加证据。"""
    db.add_relationship('e1', 'Buyer A', 'buyer', 'Supplier X', 'supplier', 'buyer_to_supplier',
                        {'shipments': 10, 'hs': ['7323'], 'products': 'enamel cookware', 'iy_verified': True},
                        'importyeti_penetration', .95, 1)
    db.add_relationship('e1', 'Buyer A', 'buyer', 'Supplier X', 'supplier', 'buyer_to_supplier',
                        {'shipments': 22, 'products': 'enamel casserole'},
                        'importyeti_penetration', .9, 1)
    with sqlite3.connect(DBPATH) as c:
        c.row_factory = sqlite3.Row
        r = dict(c.execute("SELECT * FROM relationships WHERE from_name='Buyer A'").fetchone())
    assert r['shipment_count'] == 22  # 票数取大（累加而非忽略）
    assert r['hs'] == '7323' and r['product'] == 'enamel cookware'  # 只补空不覆盖
    assert r['first_seen'] and r['last_seen'] >= r['first_seen']
    assert r['confidence'] == .95
    print('PASS trade_edge_columns')


def test_unified_evidence_layer_and_metrics():
    """Customs Layer 统一入池：非 IY 来源碎片也进 trade_nodes；图谱口径指标齐全。"""
    import core.tools.data_sources.manager as mgr_mod
    from core.trade_graph import customs_node_pipeline as cnp

    class FakeMgr:
        last_evolution = {}
        def search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
            return ([{'name': 'Local Bol Buyer', 'type': 'importer', 'source': 'customs_raw',
                      'evidence': {'shipments': 7, 'hs': ['7323'], 'customs': True, 'trade_evidence': True}},
                     {'name': 'Csv Supplier Co', 'type': 'supplier', 'source': 'csv_import', 'country': 'CN',
                      'evidence': {'shipments': 3, 'products': 'enamel pot'}}],
                    ['customs_raw'], [], {'ok': True, 'raw': 2, 'new_candidates': 2, 'existing_enriched': 0})

    orig = mgr_mod.DataSourceManager
    mgr_mod.DataSourceManager = FakeMgr
    try:
        pipe = cnp.CustomsNodePipeline()
        companies, used, errors, gate, graph, stats = pipe.run('USA', 'enamel_pot', 10,
                                                               queries=['enamel cookware'], task_id='u1')
        pool = {t['name']: t for t in db.list_trade_nodes(limit=100)}
        assert 'Local Bol Buyer' in pool and 'Csv Supplier Co' in pool  # 非IY来源统一入池
        assert pool['Csv Supplier Co']['role'] == 'supplier' and pool['Csv Supplier Co']['country'] == 'CN'
        assert stats['buyers'] == 1 and stats['suppliers'] == 1
        assert 'network_depth' in stats
        print('PASS unified_evidence_layer buyers=%d suppliers=%d' % (stats['buyers'], stats['suppliers']))
    finally:
        mgr_mod.DataSourceManager = orig


if __name__ == '__main__':
    try:
        test_product_profile_wide_and_deterministic()
        test_exclusion_purify()
        test_hs_validation_annotation_only()
        test_trade_edge_columns()
        test_unified_evidence_layer_and_metrics()
        print('ALL v30.8 product intelligence tests PASS')
    finally:
        # 清理测试写入的行业配置，不污染项目目录
        cfg = ROOT / 'data' / 'industry_configs' / 'enamel_pot.json'
        if cfg.exists(): cfg.unlink()
