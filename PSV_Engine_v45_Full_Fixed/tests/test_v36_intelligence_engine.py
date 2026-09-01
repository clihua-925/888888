# -*- coding: utf-8 -*-
"""v36 贸易情报网络发现引擎验收：
 1  EVIDENCE_VERIFY 去质量闸门：全弱证据只分级不判存亡（节点成功、主链不阻断）
 2  GRAPH_EXPANSION 边际收益计量：每层含 new_entities/new_buyers/new_suppliers/new_edges/duplicate_rate/frontier_size/consecutive_zero_gain
 3  扩张可追溯性：relationships 落库 discovered_via/parent_node/expansion_path，可多跳回溯
 4  产品域严格隔离：relationships/trade_nodes 携带 product_domain
 5  产品情报反哺：真实海关描述 → product_intel_terms → learned_recall 查询进入下轮计划
 6  契约 data_semantics：9 节点齐备并出现在注册表快照
 7  max_depth 仅安全上限：策略层默认值放宽且 dynamic_stop 不含"深度=正常终止"
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
with sqlite3.connect(DBPATH) as c:
    rows = [
        ('1','E1',now,'Kitchen World Imports','kitchenworldimports','Linyi Enamel Works','','7323','enamel cast iron cookware set',3,3,0,'CN','QIN','LAX','t'),
        ('2','E2',now-10,'Kitchen World Imports','kitchenworldimports','Linyi Enamel Works','','7323','enameled cast iron dutch oven',2,2,0,'CN','QIN','LAX','t'),
        ('3','E3',now-20,'Home Hearth Trading','homehearthtrading','Hebei Casting Co','','7323','cast iron enamel pot',1,1,0,'CN','XGN','OAK','t'),
        ('4','E4',now-30,'Home Hearth Trading','homehearthtrading','Linyi Enamel Works','','7323','enamel coated cast iron casserole',2,2,0,'CN','QIN','NYC','t'),
    ]
    c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)

import core.tools.data_sources.manager as mgr
def fake_search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
    return ([{'name':'Kitchen World Imports','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':5,'hs':['7323'],'customs':True,'trade_evidence':True,'products':'enamel cast iron cookware set'}},
             {'name':'Home Hearth Trading','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':3,'hs':['7323'],'customs':True,'trade_evidence':True,'products':'enamel coated cast iron casserole'}}],
            ['customs_raw'], [], {'ok':True,'raw':2,'qualified':2,'strong':2,'new_candidates':2,'existing_enriched':0})
mgr.DataSourceManager.search = fake_search

from core.system import PSVSystem
SYS = PSVSystem()


def test_1_evidence_verify_grades_not_judges():
    from core.runtime import nodes as N, contracts
    # 全弱证据边：无票数、无海关硬证据 ⇒ 全部 WEAK/UNVERIFIED
    state = {'task_id': 'v36weak',
             'trade_edges': [
                 {'from_name': 'Alpha Buyer', 'from_type': 'buyer', 'to_name': 'Beta Supplier',
                  'to_type': 'supplier', 'relation': 'buyer_to_supplier', 'source': 'unknown_web',
                  'evidence': {}, 'confidence': 0.8},
                 {'from_name': 'Gamma Buyer', 'from_type': 'buyer', 'to_name': 'Delta Supplier',
                  'to_type': 'supplier', 'relation': 'buyer_to_supplier', 'source': 'unknown_web',
                  'evidence': {}, 'confidence': 0.8}],
             'companies': []}
    out = N.n_evidence_verify(state)
    ev = out['evidence_verify']
    assert out['_success'] is True, '全弱证据不得判节点失败（分级≠判存亡）'
    assert ev['STRONG'] + ev['MEDIUM'] == 0 and ev['UNVERIFIED'] + ev['WEAK'] >= 2, ev
    # 契约校验同样通过（产物齐备）
    ok, issues, _ = contracts.validate('EVIDENCE_VERIFY', out, state)
    assert ok, issues
    # 弱边降权保留，不删除
    assert len(out['trade_edges']) == 2
    assert all(e['confidence'] <= 0.3 for e in out['trade_edges'])
    print('PASS 1 EVIDENCE_VERIFY：全弱证据只分级不判存亡（UNVERIFIED %d · 降权保留 %d 条）' % (
        ev['UNVERIFIED'], len(out['trade_edges'])))


_FULL = None
def _full():
    global _FULL
    if _FULL is None:
        tid = SYS.start('v36 enamel acceptance', 'USA', 'enamel cookware', 5)
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


def test_2_marginal_yield_metrics():
    tid, res = _full()
    gx = res.get('graph_expansion') or {}
    assert gx.get('stopped_by') in ('no_new_entities', 'declining_new_rate', 'max_depth',
                                    'frontier_drained', 'consecutive_low_gain'), gx.get('stopped_by')
    assert gx.get('max_depth_role') == 'safety_cap_only'
    KEYS = ('new_entities', 'new_buyers', 'new_suppliers', 'new_edges', 'duplicate_rate',
            'frontier_size', 'consecutive_zero_gain', 'edges_total')
    for d in gx.get('depths') or []:
        for k in KEYS:
            assert k in d, (k, d)
    print('PASS 2 边际收益计量：%d 层 · 停止[%s] · 每层 8 项指标齐备（新增边/买家/供应商/重复率/frontier）' % (
        len(gx.get('depths') or []), gx.get('stopped_by')))


def test_3_expansion_path_traceable():
    tid, res = _full()
    with sqlite3.connect(DBPATH) as c:
        rows = c.execute("SELECT from_name,to_name,discovered_via,parent_node,expansion_path,product_domain FROM relationships WHERE task_id=?", (tid,)).fetchall()
    assert rows, '必须有正式边落库'
    missing = [r for r in rows if not (r[2] and r[3] and r[4])]
    assert not missing, '每条边必须携带 discovered_via/parent_node/expansion_path: %s' % (missing[:3],)
    # 多跳回溯：扩张发现的节点能答出"由谁发现"
    deep = [r for r in rows if '→' in (r[4] or '')]
    assert deep, 'expansion_path 必须包含 from→to 单跳路径'
    sample = deep[0]
    chain = db.expansion_path_for(db._norm(sample[1]))
    assert len(chain) >= 2 and chain[-1] == sample[1], (sample, chain)  # 链末端=目标，链长≥2跳
    # 多跳链：至少一个节点能回溯出 3 级（客户→供应商→客户）
    multi = [r for r in rows if len(db.expansion_path_for(db._norm(r[1]))) >= 3]
    assert multi, '必须存在可多跳回溯（≥3级）的节点'
    chain = db.expansion_path_for(db._norm(sample[1]))
    print('PASS 3 可追溯性：%d 条边全部携带 discovered_via/parent_node/expansion_path · 多跳回溯样例 %s' % (
        len(rows), '→'.join(chain)))


def test_4_product_domain_isolation():
    tid, res = _full()
    dom = (res.get('product_domain') or {}).get('key')
    assert dom, res.get('product_domain')
    with sqlite3.connect(DBPATH) as c:
        e_no_dom = c.execute("SELECT COUNT(*) FROM relationships WHERE task_id=? AND COALESCE(product_domain,'')=''", (tid,)).fetchone()[0]
        n_total = c.execute("SELECT COUNT(*) FROM trade_nodes WHERE product_domain=?", (dom,)).fetchone()[0]
    assert e_no_dom == 0, '本任务每条边必须带 product_domain'
    assert n_total >= 1, 'trade_nodes 必须带 product_domain'
    # 域过滤读路径生效
    assert db.list_relationships(task_id=tid, domain=dom) and not db.list_relationships(task_id=tid, domain='OTHER_DOMAIN')
    print('PASS 4 产品域隔离：边 0 条缺域 · 图谱节点 %d 个带域[%s] · 域过滤读路径生效' % (n_total, dom))


def test_5_product_intelligence_feedback():
    from core.trade_graph import product_intelligence as pi
    prof = {'core_name': 'enamel cookware', 'hs_candidates': ['7323'], 'exclusions': ['dental enamel'],
            'synonyms': ['enamelware'], 'precision_terms': [], 'recall_terms': [], 'combo_queries': []}
    r = pi.harvest_description_terms('ENAMEL_COOKWARE', prof, min_hits=1)
    assert r['learned'], '真实海关描述必须反哺出产品词: %s' % r
    # 真实商业叫法被学到（cast iron / dutch oven / casserole 类）
    blob = ' '.join(r['learned'])
    assert any(w in blob for w in ('cast iron', 'dutch oven', 'casserole', 'coated')), blob
    # 进入下轮查询计划
    qs = pi.learned_recall_queries('ENAMEL_COOKWARE', min_hits=1)
    assert qs and all(q['query_type'] == 'learned_recall' for q in qs)
    # 排除词不被学习
    assert not any('dental' in q['query'] for q in qs)
    # 幂等：再次收割命中数累加而非重复行
    r2 = pi.harvest_description_terms('ENAMEL_COOKWARE', prof, min_hits=1)
    with sqlite3.connect(DBPATH) as c:
        n = c.execute("SELECT COUNT(*) FROM product_intel_terms WHERE product_domain='ENAMEL_COOKWARE'").fetchone()[0]
    assert n == len(set(list(r['learned']) + list(r2['learned']))), n
    print('PASS 5 产品情报反哺：学到 %d 个真实描述词（%s…）· 下轮 learned_recall 查询 %d 条 · 幂等累加' % (
        len(r['learned']), list(r['learned'])[:3], len(qs)))


def test_6_contract_data_semantics():
    from core.runtime import contracts
    snap = contracts.registry_snapshot()
    assert len(snap) == 9
    for n, c in snap.items():
        assert c.get('data_semantics'), n
    print('PASS 6 契约九要素：9 节点 data_semantics 齐备（数字口径可解释）')


def test_7_max_depth_safety_cap_only():
    from core.runtime import nodes as N
    out = N.n_trade_strategy({'task_id': 'v36strat', 'industry': 'enamel cookware', 'market': 'USA',
                              'product_domain': {'key': 'ENAMEL_COOKWARE', 'query_plan': [], 'hs_candidates': ['7323']},
                              'icp': {}})
    ep = (out.get('strategy') or {}).get('expansion_policy') or {}
    assert int(ep.get('max_depth') or 0) >= 5, ep  # 放宽为安全上限，不作正常终止
    assert not any('深度' in str(x) and '安全' not in str(x) for x in ep.get('dynamic_stop') or []), ep
    print('PASS 7 max_depth=%s 仅安全上限 · 动态停止条件 %s' % (ep.get('max_depth'), ep.get('dynamic_stop')))


if __name__ == '__main__':
    test_1_evidence_verify_grades_not_judges()
    test_2_marginal_yield_metrics()
    test_3_expansion_path_traceable()
    test_4_product_domain_isolation()
    test_5_product_intelligence_feedback()
    test_6_contract_data_semantics()
    test_7_max_depth_safety_cap_only()
    print('V36_INTELLIGENCE_ENGINE_ALL_OK (珐琅锅全链路 · 7 检查点)')
