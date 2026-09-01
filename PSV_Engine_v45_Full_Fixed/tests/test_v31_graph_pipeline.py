# -*- coding: utf-8 -*-
"""v31.0 Trade Graph Pipeline 测试：锁定九节点重构的核心语义——

1. 编排器：ORDER 为九节点新流程，FN==ORDER，严格证据节点集合正确。
2. 产品定义先行：产出产品域矩阵/HS候选/排除词，domain key 稳定。
3. 贸易关系建立：trade_graph.edges 落库为真实边列（shipment_count/hs/product）。
4. 证据验证只门控边：无证据边降权不删除，节点数不变。
5. 实体解析保守合并：'X Co., Ltd.' 与 'X LLC' 同键合并、证据取大、别名记录。
6. 资源分类新旧判定以数据库为准（回归锁：扩张新增实体不得被误判为"已有画像"）。
"""
import os, sys, tempfile, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
                  WEBAI_ENABLED='false')
from core.config import settings
settings.DATABASE_PATH = DBPATH
from core.memory.db import DB
db = DB()


def test_order_and_fn():
    from core.runtime import graph
    assert graph.ORDER == ['PRODUCT_DEFINITION', 'TRADE_STRATEGY', 'CUSTOMS_NODE_COLLECTION',
                           'TRADE_EDGE_BUILD', 'EVIDENCE_VERIFY', 'ENTITY_RESOLUTION',
                           'GRAPH_EXPANSION', 'RESOURCE_CLASSIFICATION', 'DATABASE_COMMIT']
    assert list(graph.FN.keys()) == graph.ORDER
    assert graph.STRICT_EVIDENCE == {'EVIDENCE_VERIFY', 'RESOURCE_CLASSIFICATION', 'DATABASE_COMMIT'}
    # 流程控制权铁律：编排器剥离节点返回的控制字段
    import inspect
    src = inspect.getsource(graph._run_once)
    assert 'ORCHESTRATOR_KEYS' in src, '编排器必须经 ORCHESTRATOR_KEYS 统一剥离节点返回的控制字段'
    print('PASS order_fn_strict')


def test_product_definition():
    from core.runtime import nodes as N
    out = N.n_product_definition({'task_id': 'v31pd', 'market': 'USA', 'industry': 'candle', 'quantity': 5})
    pd = out['product_domain']
    assert pd['key'] and pd['matrix'] and pd['hs_candidates'], pd
    assert 'exclusions' in pd and 'hs_validation' in pd
    assert out['icp'], '产品定义节点必须同时产出 ICP 契约'
    print('PASS product_definition domain=%s matrix=%d' % (pd['key'], len(pd['matrix'])))


def test_trade_edge_build_persists_columns():
    """v34 边生命周期：TRADE_EDGE_BUILD 只建内存标准边（不写库）→ DATABASE_COMMIT 唯一写库。"""
    from core.runtime import nodes as N
    state = {'task_id': 'v31edge', 'trade_graph': {'edges': [
        {'from_name': 'Edge Buyer A', 'from_type': 'buyer', 'to_name': 'Edge Supplier X',
         'to_type': 'supplier', 'relation': 'buyer_to_supplier', 'source': 'customs_raw',
         'confidence': 0.9, 'depth': 1,
         'evidence': {'shipments': 12, 'hs': ['3406'], 'products': 'pillar candles'}}]}}
    out = N.n_trade_edge_build(state)
    assert out['edges_built'] == 1
    e = out['trade_edges'][0]
    assert e['shipment_count'] == 12 and '3406' in str(e['hs_code']) and 'candle' in e['product_text'], e
    assert e['evidence_level'] == 'STRONG' and e['buyer_entity_id'] and e['supplier_entity_id']
    import sqlite3
    with sqlite3.connect(DBPATH) as c:
        r = c.execute("SELECT COUNT(*) FROM relationships WHERE from_name='Edge Buyer A'").fetchone()[0]
    assert r == 0, '建边节点不得写库（唯一出口 DATABASE_COMMIT）'
    # 重复建边：内存幂等去重，不产生重复边
    out2 = N.n_trade_edge_build(state)
    assert len(out2['trade_edges']) == 1, out2['trade_edges']
    # DATABASE_COMMIT 写库：标准字段真实列
    N.n_database_commit({'task_id': 'v31edge', 'trade_edges': out2['trade_edges'],
                         'classified_entities': [], 'funnel': []})
    with sqlite3.connect(DBPATH) as c:
        r = c.execute("SELECT shipment_count, hs, product FROM relationships WHERE from_name='Edge Buyer A'").fetchone()
        n = c.execute("SELECT COUNT(*) FROM relationships WHERE from_name='Edge Buyer A'").fetchone()[0]
    assert r and r[0] == 12 and '3406' in (r[1] or '') and 'candle' in (r[2] or ''), r
    assert n == 1, n
    print('PASS trade_edge_build 内存标准边 + DATABASE_COMMIT 唯一写库幂等')


def test_evidence_verify_gates_edges_not_nodes():
    from core.runtime import nodes as N
    db.add_relationship('v31ev', 'EV Buyer Hard', 'buyer', 'EV Supplier Hard', 'supplier',
                        'buyer_to_supplier', {'shipments': 5, 'customs': True}, 'customs_raw', 0.9, 1)
    db.add_relationship('v31ev', 'EV Buyer Soft', 'buyer', 'EV Supplier Soft', 'supplier',
                        'buyer_to_supplier', {}, 'guess_source', 0.9, 1)
    companies = [{'name': 'EV Buyer Hard', 'evidence': {'shipments': 5}},
                 {'name': 'EV Buyer Soft', 'evidence': {}}]
    out = N.n_evidence_verify({'task_id': 'v31ev', 'companies': companies})
    ev = out['evidence_verify']
    assert ev['strong'] >= 1 and (ev['weak'] + ev['unverified']) >= 1, ev
    # 无证据边降权但保留；节点一个不少
    import sqlite3
    with sqlite3.connect(DBPATH) as c:
        soft = c.execute("SELECT confidence FROM relationships WHERE from_name='EV Buyer Soft'").fetchone()
        total = c.execute("SELECT COUNT(*) FROM relationships WHERE task_id='v31ev'").fetchone()[0]
    assert soft[0] <= 0.3, soft
    assert total == 2, '无证据边必须保留（降权隔离），不得删除'
    assert len(out['companies']) == 2, '证据验证不得删节点'
    print('PASS evidence_verify edges_only demote=%s (强/中/弱分级)' % soft[0])


def test_entity_clean_conservative_merge():
    from core.runtime import nodes as N
    companies = [
        {'name': 'Ningbo Bright Plastic Co., Ltd.', 'evidence': {'shipments': 8}, 'source': 'customs_raw'},
        {'name': 'Ningbo Bright Plastic LLC', 'evidence': {'shipments': 20}, 'source': 'importyeti'},
        {'name': 'Totally Different Entity', 'evidence': {'shipments': 1}, 'source': 'customs_raw'},
    ]
    # 只测合并段：直接调用内部归一键，避免 n_clean_verify 依赖完整 state
    k1 = N.entity_key(companies[0]['name']); k2 = N.entity_key(companies[1]['name'])
    k3 = N.entity_key(companies[2]['name'])
    assert k1 == k2, (k1, k2)
    assert k3 != k1
    out = N.n_entity_resolution({'task_id': 'v31ec', 'companies': companies, 'new_companies': []})
    names = [c['name'] for c in out['new_companies']]
    # 后缀变体合并为 1 条（票数高者为主），不同实体绝不错并
    bright = [c for c in out['new_companies'] if 'Bright' in c['name']]
    assert len(bright) == 1 and bright[0]['name'] == 'Ningbo Bright Plastic LLC', names
    assert bright[0]['evidence'].get('same_as_merged'), '合并必须留 SAME_AS 痕迹'
    assert 'Ningbo Bright Plastic Co., Ltd.' in (bright[0]['evidence'].get('aliases') or [])
    assert any('Different' in n for n in names)
    print('PASS entity_clean merge -> %s' % names)


def test_resource_classification_vocabulary():
    """v32 分类词表：禁止只用 QUALIFIED；全部合格实体都进提交清单（新旧由入库层幂等判定）。"""
    from core.runtime import nodes as N
    db.commit_discovery_lead({'name': 'RC Existing Buyer', 'type': 'importer',
                              'evidence': {'shipments': 3, 'customs': True}}, zone='dev')
    companies = [
        {'name': 'RC Existing Buyer', 'evidence': {'shipments': 3, 'customs': True}, 'source': 'customs_raw'},
        {'name': 'RC Fresh Harvest Buyer', 'evidence': {'shipments': 6, 'customs': True}, 'source': 'customs_raw'},
        {'name': 'RC Soft Buyer', 'evidence': {}, 'source': 'customs_raw'},
    ]
    out = N.n_resource_classification({'task_id': 'v31rc', 'market': 'USA', 'industry': 'candle',
                                       'quantity': 5, 'companies': companies, 'new_companies': [],
                                       'product_domain': {'key': 'CANDLE'}})
    names = [c['name'] for c in out['classified_entities']]
    # 全部已分类实体都提交（含库里已有的——入库层会报"更新"而非"新增"，不再是提交0）
    assert 'RC Fresh Harvest Buyer' in names and 'RC Existing Buyer' in names, names
    by = {c['name']: c for c in out['classified_entities']}
    assert by['RC Fresh Harvest Buyer']['lifecycle'] == 'CUSTOMER_CONFIRMED', by['RC Fresh Harvest Buyer']
    assert by['RC Soft Buyer']['lifecycle'] == 'CUSTOMER_DEVELOPMENT'
    assert all(c.get('product_domain') == 'CANDLE' for c in out['classified_entities'])
    print('PASS resource_classification vocabulary %s' % {k: v for k, v in out['classification'].items() if v})


def test_lifecycle_domain_persisted():
    """生命周期与产品域随实体落库；已有实体只补空不覆盖。"""
    r = db.commit_discovery_lead({'name': 'LC Buyer One', 'type': 'importer',
                                  'evidence': {'shipments': 4, 'customs': True},
                                  'lifecycle': 'CUSTOMER_CONFIRMED', 'product_domain': 'CANDLE'}, zone='dev')
    lead = db.get_lead(r['norm'])
    assert lead['lifecycle'] == 'CUSTOMER_CONFIRMED' and lead['product_domain'] == 'CANDLE', lead
    r2 = db.commit_discovery_lead({'name': 'LC Buyer One', 'type': 'importer',
                                   'evidence': {'shipments': 9, 'customs': True},
                                   'lifecycle': 'CUSTOMER_DEVELOPMENT', 'product_domain': 'FELT'}, zone='dev')
    lead2 = db.get_lead(r['norm'])
    assert lead2['lifecycle'] == 'CUSTOMER_CONFIRMED' and lead2['product_domain'] == 'CANDLE', '已有分类不得被覆盖'
    leads = db.list_leads(zone='dev', domain='CANDLE')
    assert any(l['name'] == 'LC Buyer One' for l in leads), '产品域过滤未生效'
    assert not db.list_leads(zone='dev', domain='ENAMEL_COOKWARE')
    print('PASS lifecycle_domain_persisted')


if __name__ == '__main__':
    test_order_and_fn()
    test_product_definition()
    test_trade_edge_build_persists_columns()
    test_evidence_verify_gates_edges_not_nodes()
    test_entity_clean_conservative_merge()
    test_resource_classification_vocabulary()
    test_lifecycle_domain_persisted()
    print('V31_GRAPH_PIPELINE_ALL_OK')
