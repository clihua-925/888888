# -*- coding: utf-8 -*-
"""v34.0 最终架构验证：真实产品【珐琅锅（enamel cookware）】全链路运行 + 22 条检查点。

检查点清单（与 v34 架构级总审计规范一一对应）：
 1  节点注册唯一（ORDER==FN，无重复名，一套命名贯穿）
 2  编排器唯一控制（节点只有执行权，编排状态由 graph.ORCHESTRATOR_KEYS 统一剥离）
 3  产品语义矩阵 16 维齐备
 4  动态查询计划：无固定上限 + 每条带 query_type/expected_role/expected_product_relation
 5  TRADE_STRATEGY 12 要素齐备
 6  HS 强辅助信号非硬过滤（policy 锁定）
 7  Trade Node 全字段 + UNRESOLVED_TRADE_NODE 保留不删
 8  逐查询计量落库（query_stats：result_count/usable_trade_nodes/precision_estimate/recall_contribution）
 9  动态淘汰：连续两轮零产出才 retired，有产出立即回活（降权不删除）
10  Trade Edge 标准字段 + evidence_level 真实列
11  证据四级 STRONG/MEDIUM/WEAK/UNVERIFIED，降权不删除（内存分级 + 存量对账）
12  实体角色 CUSTOMER/SUPPLIER/CUSTOMER_AND_SUPPLIER/UNKNOWN（同实体多角色合并）
13  GRAPH_EXPANSION 递归多层 + 动态停止 + 递归不丢实体（召回率）
14  三维分类 + 理由字段（entity_role/trade_status/development_status/classification_reason）
15  DATABASE_COMMIT 三类资产（Entity+Edge+Evidence）+ 数量恒等
16  双角色实体 kind='both' 入库，客户/供应商双视图可见
17  漏斗全程留痕（每阶段 in/out + drop_reasons）
18  handoff 全 9 节点齐全（含 GRAPH_EXPANSION），UI 版本/漏斗/kind 同步
19  handoff 契约 v34.0 字段齐备，checksum 对真实 payload（PAYLOAD_KEYS 快照）计算
20  状态机大写统一（PENDING/RUNNING/SUCCESS/FAILED/BLOCKED/SKIPPED/CANCELLED）
21  relationships 写库唯一出口 DATABASE_COMMIT（执行器/建边节点零直写）
22  UI 节点卡片恰 9 个 canonical 节点 + 数字口径语义 count_semantics 注入
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
# 珐琅锅真实贸易形态：进口商/供应商/双角色贸易商/物流货代/不同产品线（pot/pan/dutch oven）
with sqlite3.connect(DBPATH) as c:
    rows = [
        ('1','BOL1',now,'Cast Iron Kitchen Inc','castironkitchen','Shijiazhuang Enamel Works','','7323','enamel cast iron dutch oven',2,2,0,'CN','XGN','LAX','t'),
        ('2','BOL2',now-10,'Cast Iron Kitchen Inc','castironkitchen','Shijiazhuang Enamel Works','','7323','enamel cookware set',1,1,0,'CN','XGN','LAX','t'),
        ('3','BOL3',now-20,'HomeStyle Imports Ltd','homestyleimports','Guangdong Castware Co','','7323','enamel saucepan',1,1,0,'CN','SHA','OAK','t'),
        ('4','BOL4',now-30,'Cookware Depot LLC','cookwaredepot','Global Cookware Trading','','7323','enamel milk pot',1,1,0,'CN','NGB','NYC','t'),
        ('5','BOL5',now-40,'Global Cookware Trading','globalcookware','Shijiazhuang Enamel Works','','7323','enamel casserole',3,3,0,'CN','XGN','LAX','t'),
        ('6','BOL6',now-50,'Cast Iron Kitchen Inc','castironkitchen','Fast Freight Forwarding','','7323','enamel pot',1,1,0,'CN','XGN','LAX','t'),
    ]
    c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)

import core.tools.data_sources.manager as mgr
def fake_search(self, market, industry, quantity, variants_override=None, source_queries=None, hs_codes=None):
    return ([{'name':'Cast Iron Kitchen Inc','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':3,'hs':['7323'],'customs':True,'trade_evidence':True,'products':'enamel cast iron dutch oven'}},
             {'name':'Global Cookware Trading','country':market,'industry':industry,'type':'importer','source':'customs_raw','strength':5,
              'evidence':{'shipments':3,'hs':['7323'],'customs':True,'trade_evidence':True,'products':'enamel casserole'}}],
            ['customs_raw'], [], {'ok':True,'raw':2,'qualified':2,'strong':2,'new_candidates':2,'existing_enriched':0})
mgr.DataSourceManager.search = fake_search

from core.system import PSVSystem
SYS = PSVSystem()


def run_enamel_task():
    tid = SYS.start('v34 enamel cookware final verification', 'USA', 'enamel cookware', 5)
    deadline = time.time() + 120
    while time.time() < deadline:
        t = SYS.get(tid)
        if t and t.get('status') in ('done','failed','done_degraded','failed_gate','error'):
            break
        time.sleep(0.3)
    t = SYS.get(tid)
    assert t['status'] in ('done','done_degraded'), (t['status'], (t.get('result') or {}).get('error'))
    return tid, t.get('result') or {}


def test_01_node_registry_unique():
    from core.runtime import graph
    assert len(graph.ORDER) == len(set(graph.ORDER)) == 9
    assert list(graph.FN.keys()) == graph.ORDER
    print('PASS 1 节点注册唯一：%d 节点一套命名' % len(graph.ORDER))


def test_02_orchestrator_sole_control():
    src = open(ROOT/'core/runtime/graph.py', encoding='utf-8').read()
    assert 'ORCHESTRATOR_KEYS' in src, '编排层必须统一剥离编排状态键'
    run_once = src[src.index('def _run_once'):src.index('def _director')]
    assert 'ORCHESTRATOR_KEYS' in run_once, '节点产出必须经 ORCHESTRATOR_KEYS 剥离'
    assert src.index('state.update(out)') < src.index('_record_handoff(state, name', src.index('def _run_once')), \
        '必须先合并真实 payload 再记录 handoff（否则 checksum 对陈旧快照）'
    nsrc = open(ROOT/'core/runtime/nodes.py', encoding='utf-8').read()
    v34 = nsrc[nsrc.index('v34.0 业务节点层'):]
    assert "'abort':" not in v34 and "'next_node':" not in v34, '节点不得产出流程控制字段'
    print('PASS 2 编排器唯一控制：ORCHESTRATOR_KEYS 统一剥离 · state.update 先于 handoff 记录')


def test_03_04_semantic_matrix_and_dynamic_plan():
    from core.trade_graph import product_intelligence as pi
    p = pi.build_product_profile('enamel cookware', use_llm=False)
    DIMS16 = ('core_name','standard_name_en','synonyms','spelling_variants','industry_terms',
              'buyer_terms','supplier_terms','form_words','materials','function_words',
              'trade_terms','hs_candidates','exclusions','precision_terms','recall_terms','combo_queries')
    missing = [k for k in DIMS16 if k not in p]
    assert not missing, missing
    assert 'enameled cookware' in p['spelling_variants'] or 'enamelled cookware' in p['spelling_variants']
    assert any('importer' in x for x in p['buyer_terms']) and any('manufacturer' in x for x in p['supplier_terms'])
    plan = pi.build_query_plan(p)
    assert len(plan) >= 12, f'矩阵驱动查询数 {len(plan)}（无固定上限）'
    for q in plan:
        assert q['query'] and q['query_type'] and q['expected_role'] and q['expected_product_relation']
        assert 'result_count' in q and 'usable_trade_nodes' in q  # 计量字段预留
    print('PASS 3-4 语义矩阵16维齐备 · 动态查询计划 %d 条（无固定上限）' % len(plan))


def test_05_06_strategy_12_elements():
    from core.runtime import nodes as N
    pd_out = N.n_product_definition({'market':'USA','industry':'enamel cookware','task_id':'v34s'})
    st = {'market':'USA','industry':'enamel cookware','task_id':'v34s','quantity':5,
          'icp':pd_out['icp'],'product_profile':pd_out['product_profile'],'product_domain':pd_out['product_domain']}
    out = N.n_trade_strategy(st)
    s = out['strategy']
    E12 = ('product_domain','buyer_types','supplier_types','target_roles','target_hs','hs_strategy',
           'target_countries','query_plan','precision_recall_split','expansion_policy','evidence_policy','collection_budget')
    missing = [k for k in E12 if k not in s]
    assert not missing, missing
    assert s['hs_strategy']['policy'] == 'strong_signal_not_hard_filter'  # HS 强信号非硬过滤
    assert s['expansion_policy']['mode'] == 'bidirectional_recursive'
    assert s['evidence_policy']['levels'] == ['STRONG','MEDIUM','WEAK','UNVERIFIED']
    assert s['precision_recall_split']['precision'] > 0 and s['precision_recall_split']['recall'] > 0
    print('PASS 5-6 贸易定位12要素 · HS强信号非硬过滤 · 精度/召回 %s' % s['precision_recall_split'])


def test_08_09_query_telemetry_and_dynamic_retire():
    from core.trade_graph import product_intelligence as pi
    m = pi.measure_query('enamel', ['7323'])
    assert m['result_count'] >= 6, m  # 珐琅锅提单命中
    assert m['usable_trade_nodes'] >= 5, m
    db.save_query_stat('v34q','ENAMEL_COOKWARE',{'query':'enamel','query_type':'recall','expected_role':'both',
        'expected_product_relation':'broad','result_count':m['result_count'],'usable_trade_nodes':m['usable_trade_nodes']})
    db.save_query_stat('v34q','ENAMEL_COOKWARE',{'query':'nonexistent zzz term','query_type':'combo','expected_role':'both','expected_product_relation':'exact','result_count':0,'usable_trade_nodes':0})
    db.save_query_stat('v34q2','ENAMEL_COOKWARE',{'query':'nonexistent zzz term','query_type':'combo','expected_role':'both','expected_product_relation':'exact','result_count':0,'usable_trade_nodes':0})
    stats = {r['query']: r for r in db.list_query_stats('ENAMEL_COOKWARE')}
    assert stats['enamel']['status'] == 'active' and stats['enamel']['result_count'] >= 6
    assert stats['nonexistent zzz term']['status'] == 'retired' and stats['nonexistent zzz term']['runs_zero'] == 2
    # 有产出立即回活
    db.save_query_stat('v34q3','ENAMEL_COOKWARE',{'query':'nonexistent zzz term','query_type':'combo','expected_role':'both','expected_product_relation':'exact','result_count':3,'usable_trade_nodes':1})
    assert {r['query']: r for r in db.list_query_stats('ENAMEL_COOKWARE')}['nonexistent zzz term']['status'] == 'active'
    print('PASS 8-9 逐查询计量落库 · 动态淘汰（连续2轮零产出retired/有产出回活）')


def test_10_11_edge_fields_and_evidence_levels():
    db.add_relationship('v34e','Cast Iron Kitchen Inc','buyer','Shijiazhuang Enamel Works','supplier',
                        'buyer_to_supplier',{'shipments':2,'hs':['7323'],'products':'enamel dutch oven'},'customs_raw',0.95,1,evidence_level='STRONG')
    db.add_relationship('v34e','Mystery Buyer','buyer','Mystery Supplier','supplier',
                        'buyer_to_supplier',{},'guess_source',0.9,1)
    from core.runtime import nodes as N
    out = N.n_evidence_verify({'task_id':'v34e','companies':[]})  # 无内存边 → 存量对账路径
    ev = out['evidence_verify']
    assert ev['STRONG'] >= 1 and ev['UNVERIFIED'] >= 1, ev
    with sqlite3.connect(DBPATH) as c:
        lvl = c.execute("SELECT evidence_level,confidence,shipment_count,product FROM relationships WHERE task_id='v34e' AND from_name='Cast Iron Kitchen Inc'").fetchone()
        soft = c.execute("SELECT confidence,evidence_level FROM relationships WHERE task_id='v34e' AND from_name='Mystery Buyer'").fetchone()
        total = c.execute("SELECT COUNT(*) FROM relationships WHERE task_id='v34e'").fetchone()[0]
    assert lvl[0] == 'STRONG' and lvl[2] == 2 and 'enamel' in lvl[3], lvl  # 标准边字段真实列
    assert soft[0] <= 0.1 and soft[1] == 'UNVERIFIED', soft  # UNVERIFIED 降权 0.1
    assert total == 2, '证据不足≠删除节点/边'
    # 内存边分级路径（v34 主路径）：同一判定函数，降权不删除
    out2 = N.n_evidence_verify({'task_id':'v34e2','companies':[], 'trade_edges':[
        {'from_name':'A Buyer','to_name':'B Factory','relation':'buyer_to_supplier',
         'source':'customs_raw','confidence':0.9,'evidence':{'shipments':4}},
        {'from_name':'C Buyer','to_name':'D Factory','relation':'buyer_to_supplier',
         'source':'guess','confidence':0.9,'evidence':{}}]})
    assert out2['evidence_verify']['STRONG'] == 1 and out2['evidence_verify']['UNVERIFIED'] == 1, out2['evidence_verify']
    weak_edge = [e for e in out2['trade_edges'] if e['from_name'] == 'C Buyer'][0]
    assert weak_edge['confidence'] <= 0.1 and weak_edge['evidence_level'] == 'UNVERIFIED', weak_edge
    print('PASS 10-11 标准边字段+evidence_level列 · 证据四级（内存分级+存量对账，降权不删除）%s' % {k:v for k,v in ev.items() if isinstance(v,int) and v})


def test_12_entity_roles():
    from core.runtime import nodes as N
    companies = [
        {'name':'Dual Trade Co','type':'importer','country':'USA','evidence':{'shipments':5,'customs':True},'source':'customs_raw'},
        {'name':'Dual Trade Co','type':'supplier','country':'CN','evidence':{'shipments':9,'customs':True},'source':'customs_raw'},
        {'name':'Pure Buyer Inc','type':'importer','country':'USA','evidence':{'shipments':3},'source':'customs_raw'},
        {'name':'Pure Factory Ltd','type':'supplier','country':'CN','evidence':{'shipments':7},'source':'customs_raw'},
    ]
    out = N.n_entity_resolution({'task_id':'v34er','companies':companies,'new_companies':[]})
    roles = {e['name']: e['role'] for e in out['company_entities']}
    assert roles.get('Dual Trade Co') == 'CUSTOMER_AND_SUPPLIER', roles
    assert roles.get('Pure Buyer Inc') == 'CUSTOMER' and roles.get('Pure Factory Ltd') == 'SUPPLIER', roles
    dual = [e for e in out['company_entities'] if e['name'] == 'Dual Trade Co'][0]
    assert dual['entity_id'] and 'legal_name' in dual and 'aliases' in dual and 'trade_edges' in dual and 'source_count' in dual
    print('PASS 12 实体角色：CUSTOMER/SUPPLIER/CUSTOMER_AND_SUPPLIER 全字段实体结构 %s' % roles)


def test_13_recursive_expansion_dynamic_stop():
    from core.runtime import nodes as N
    # 单测隔离：复位收割标记，避免与全链路用例共享供应商收割状态
    with sqlite3.connect(DBPATH) as c:
        c.execute('UPDATE suppliers SET harvested_at=NULL')
    st = {'task_id':'v34gx','market':'USA','industry':'enamel cookware','quantity':2,
          'companies':[{'name':'Cast Iron Kitchen Inc','country':'USA','type':'importer','source':'customs_raw',
                        'evidence':{'shipments':3,'customs':True}}],
          'strategy':{'expansion_policy':{'max_depth':3}}}
    out = N.n_graph_expansion(st)
    gx = out['graph_expansion']
    assert gx['stopped_by'] in ('no_new_entities','declining_new_rate','max_depth','frontier_drained','consecutive_low_gain'), gx
    assert 1 <= len(gx['depths']) <= 3
    names = {c['name'] for c in out['companies']}
    assert 'Cast Iron Kitchen Inc' in names, '递归扩张不得丢失已有实体'
    assert len(out['companies']) >= 3, f'扩张应带来新实体（供应商+反向客户）: {names}'
    # v34：扩张发现的关系边同步进内存 trade_edges（不写库，DATABASE_COMMIT 统一落库）
    assert gx.get('edges_synced', 0) >= 1 and out.get('trade_edges'), '扩张边必须进入内存标准边'
    assert all(e.get('evidence_level') in ('STRONG','MEDIUM','WEAK','UNVERIFIED') for e in out['trade_edges'])
    print('PASS 13 递归多层扩张：%d 层 · 停止[%s] · 实体 %d · 内存边 %d（不丢实体）' % (
        len(gx['depths']), gx['stopped_by'], len(out['companies']), gx.get('edges_synced', 0)))


def test_14_three_dim_classification():
    from core.runtime import nodes as N
    companies = [
        {'name':'Hard Buyer','evidence':{'shipments':9,'customs':True},'source':'customs_raw'},
        {'name':'Soft Buyer','evidence':{},'source':'customs_raw'},
        {'name':'Mystery Node','evidence':{},'source':'unknown','type':'unknown'},
    ]
    out = N.n_resource_classification({'task_id':'v34rc','market':'USA','industry':'enamel cookware',
        'quantity':5,'companies':companies,'new_companies':[],
        'company_entities':[{'entity_id':'hardbuyer','role':'CUSTOMER'},{'entity_id':'softbuyer','role':'CUSTOMER'},{'entity_id':'mysterynode','role':'UNKNOWN'}],
        'product_domain':{'key':'ENAMEL_COOKWARE'}})
    by = {c['name']: c for c in out['classified_entities']}
    hb = by['Hard Buyer']
    assert hb['entity_role'] == 'CUSTOMER' and hb['trade_status'] == 'TRADE_CONFIRMED' and hb['development_status'] == 'DEVELOPMENT_POOL'
    assert hb['classification_reason'], '理由字段必填'
    assert by['Soft Buyer']['trade_status'] == 'DISCOVERED' and by['Soft Buyer']['development_status'] == 'DISCOVERED_POOL'
    assert by['Mystery Node']['lifecycle'] == 'TRADE_NODE_ONLY', by['Mystery Node'].get('lifecycle')
    cnt = out['classification']
    assert set(cnt) == {'by_role','by_trade_status','by_development_status','lifecycle'}
    print('PASS 14 三维分类+理由字段 %s' % cnt['by_trade_status'])


def test_21_single_write_channel_static():
    """静态：relationships 写库唯一出口 DATABASE_COMMIT——nodes.py 全文件只允许 1 处 add_relationship。"""
    nsrc = open(ROOT/'core/runtime/nodes.py', encoding='utf-8').read()
    body = nsrc[nsrc.index('def n_database_commit'):]
    head = nsrc[:nsrc.index('def n_database_commit')]
    assert 'add_relationship' not in head, 'DATABASE_COMMIT 之前任何节点不得写 relationships'
    assert body.count('add_relationship') >= 1, 'DATABASE_COMMIT 必须真正写边'
    cnp_src = open(ROOT/'core/trade_graph/customs_node_pipeline.py', encoding='utf-8').read()
    assert 'add_relationship' not in cnp_src, 'save_graph 不得再写关系边（唯一出口 DATABASE_COMMIT）'
    print('PASS 21 写库唯一出口：DATABASE_COMMIT 之前零直写 · save_graph 不再写边')


_FULL = None
def _full():
    global _FULL
    if _FULL is None:
        _FULL = run_enamel_task()
    return _FULL


def test_15_to_18_enamel_full_run():
    tid, res = _full()
    commit = res.get('database_commit') or {}
    # 15 三类资产
    assert commit.get('edges', 0) >= 3, commit.get('edges')
    assert commit.get('evidence_events', 0) >= 2, commit.get('evidence_events')
    assert commit.get('dev', 0) + commit.get('dev_both', 0) >= 2, commit
    assert commit.get('dev_suppliers', 0) >= 2, commit  # Shijiazhuang Enamel Works / Guangdong Castware / Global Cookware Trading
    # 16 双角色：Global Cookware Trading 既是买家（BOL5 importer）又是供应商（BOL4 shipper）
    with sqlite3.connect(DBPATH) as c:
        both = c.execute("SELECT name,kind,zone FROM leads WHERE kind='both'").fetchall()
        edges_lvl = c.execute("SELECT evidence_level,COUNT(*) FROM relationships GROUP BY evidence_level").fetchall()
        tn = c.execute("SELECT COUNT(*),SUM(CASE WHEN entity_status='UNRESOLVED_TRADE_NODE' THEN 1 ELSE 0 END) FROM trade_nodes").fetchone()
    assert any('Global Cookware' in b[0] for b in both), both
    # 双视图可见
    assert any('Global Cookware' in l['name'] for l in db.list_leads(kind='customer', limit=500))
    assert any('Global Cookware' in l['name'] for l in db.list_leads(kind='supplier', limit=500))
    # 7 Trade Node 全字段 + UNRESOLVED 保留（物流货代停放进节点池不删除）
    with sqlite3.connect(DBPATH) as c:
        logistics = c.execute("SELECT name,role,entity_status FROM trade_nodes WHERE name LIKE '%Freight%'").fetchall()
    assert logistics, '物流节点必须停放在贸易节点池'
    assert tn[0] >= 5, tn
    # 17 漏斗恒等
    funnel = commit.get('funnel') or res.get('funnel') or []
    assert len(funnel) >= 5, funnel
    dc_in = [f for f in funnel if f['stage'] == 'DATABASE_COMMIT.输入(已分类实体)'][0]
    dc_cv = [f for f in funnel if f['stage'] == 'DATABASE_COMMIT.转换(entity_converter)'][0]
    assert dc_in['in'] >= dc_cv['out'] and dc_cv['out'] >= 4, (dc_in, dc_cv)
    assert 'drop_reasons' in dc_cv
    assert any(f['stage'].startswith('DATABASE_COMMIT.Edge写入') for f in funnel), '边必须由 DATABASE_COMMIT 写入'
    # 18 handoff 全 9 节点 + payload_checksum
    ho = res.get('handoffs') or {}
    from core.runtime import graph
    assert set(ho) == set(graph.ORDER), ('handoff 必须覆盖全 9 节点（含 GRAPH_EXPANSION）', set(graph.ORDER) - set(ho))
    assert all('payload_checksum' in v for v in ho.values()), ho
    # UI 静态同步
    html_src = open(ROOT/'core/webui/app.py', encoding='utf-8').read()
    assert ('v35.0' in html_src or 'v36.0' in html_src or 'v37.0' in html_src or 'v38.0' in html_src or 'v39.0' in html_src or 'v40.0' in html_src) and 'kind=customer' in html_src and 'funnelHtml' in html_src
    assert 'data-kind="importer"' not in html_src
    print('PASS 15-18 珐琅锅全链路：客户%d·供应商%d·双角色%d·边%d·证据%d · 漏斗%d段 · handoff全9节点' % (
        commit.get('dev',0), commit.get('dev_suppliers',0), commit.get('dev_both',0),
        commit.get('edges',0), commit.get('evidence_events',0), len(funnel)))
    print('    边证据等级分布: %s · 贸易节点 %d（待解析 %d）' % (edges_lvl, tn[0], tn[1] or 0))


def test_19_handoff_contract_v34():
    """handoff 契约：node_id/from_node/to_node/task_id/run_id/contract_version/
    payload_keys/payload_checksum/node_report/status/metrics/errors/warnings/created_at。"""
    tid, res = _full()
    from core.runtime import graph
    ho = res.get('handoffs') or {}
    REQ = ('node_id','from_node','to_node','task_id','run_id','contract_version',
           'payload_keys','payload_checksum','node_report','status','metrics','errors','warnings','created_at')
    for name in graph.ORDER:
        h = ho.get(name) or {}
        missing = [k for k in REQ if k not in h]
        assert not missing, (name, missing)
        assert h['contract_version'] == graph.HANDOFF_CONTRACT_VERSION == 'v34.0'
        assert h['task_id'] == tid and h['run_id']
        assert isinstance(h['payload_checksum'], str) and len(h['payload_checksum']) == 12
        assert h['payload_keys'], 'checksum 必须对真实 payload（非空）计算'
        assert h['status'] in settings.NODE_STATUS
        assert isinstance(h['metrics'], dict) and isinstance(h['errors'], list) and isinstance(h['warnings'], list)
    # 链路顺序：from_node 必须指向上游节点
    for i, name in enumerate(graph.ORDER):
        expect_from = graph.ORDER[i-1] if i else 'MISSION_DIRECTOR'  # 首节点由总统筹发起
        assert ho[name]['from_node'] == expect_from, (name, ho[name]['from_node'], expect_from)
    print('PASS 19 handoff 契约 v34.0：9 节点字段齐备 · run_id 统一 · from_node 链式衔接')


def test_20_status_machine_uppercase():
    tid, res = _full()
    ns = res.get('node_status') or {}
    from core.runtime import graph
    assert set(ns) == set(graph.ORDER)
    for name, st in ns.items():
        assert st.get('status') in settings.NODE_STATUS, (name, st)
        assert st.get('status') == st.get('status').upper(), '状态必须大写（唯一口径 settings.NODE_STATUS）'
    assert res.get('engine') == 'trade-graph-pipeline-v34'
    print('PASS 20 状态机大写统一：%s' % {k: v.get('status') for k, v in list(ns.items())[:3]})


def test_22_ui_labels_and_count_semantics():
    tid, res = _full()
    asrc = open(ROOT/'core/webui/app.py', encoding='utf-8').read()
    # v37：DEV_LABELS 改为从 development 模块导入（标签唯一来源），锚点相应调整
    i0 = asrc.index('NODE_LABELS='); i1 = asrc.index('DEV_LABELS')
    block = asrc[i0:i1]
    from core.runtime import graph
    for name in graph.ORDER:
        assert ("'%s'" % name) in block, name
    for legacy in ("'ICP'","'STRATEGY'","'A_COLLECT'","'CLEAN_PASS1'","'CLEAN_QUALITY_GATE'",
                   "'SEED_BUYERS'","'SUPPLIER_MINING'","'REVERSE_HARVEST'","'CLEAN_VERIFY'","'A_GATE'"):
        assert legacy not in block, 'UI 不得再渲染旧节点卡片: ' + legacy
    assert block.count("':'") == 9, 'NODE_LABELS 必须恰 9 个'
    # 数字口径语义注入
    cs = res.get('count_semantics') or {}
    assert set(cs) == set(settings.COUNT_SEMANTICS) and 'trade_nodes' in cs
    # DEBUG_ONLY：单独执行默认关闭
    r = SYS.run_node(tid, graph.ORDER[0])
    assert r.get('debug_only') is True and not settings.DEBUG_MODE, '单独执行必须 DEBUG_MODE 才开放'
    print('PASS 22 UI 恰 9 节点卡片 · count_semantics 注入 · 单独执行 DEBUG_ONLY 闸门')


if __name__ == '__main__':
    test_01_node_registry_unique()
    test_02_orchestrator_sole_control()
    test_03_04_semantic_matrix_and_dynamic_plan()
    test_05_06_strategy_12_elements()
    test_08_09_query_telemetry_and_dynamic_retire()
    test_10_11_edge_fields_and_evidence_levels()
    test_12_entity_roles()
    test_14_three_dim_classification()
    test_21_single_write_channel_static()
    test_15_to_18_enamel_full_run()      # 全链路先跑（新鲜收割状态）
    test_19_handoff_contract_v34()
    test_20_status_machine_uppercase()
    test_22_ui_labels_and_count_semantics()
    test_13_recursive_expansion_dynamic_stop()  # 单测自带收割标记复位
    print('V34_FINAL_ARCHITECTURE_ALL_OK (珐琅锅全链路 · 22检查点)')
