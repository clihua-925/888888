# -*- coding: utf-8 -*-
"""v30.4 单点彻底性 + 架构边界回归。

1. 供应商画像：产品 mix/档次推断/供应能力/客户覆盖全部来自真实提单，推断如实标注；
   无价格数据时明确不编造质价比。
2. 图谱待展开节点可度量（pending_graph_nodes）。
3. 架构边界：graph.FN 只允许 ORDER 内的执行节点（REFLECT 等“小编排器”不得注册）。
4. IY 关系区上限可调（IY_REL_MAX_ROWS），lyWeb 暴露 last_total。
"""
import os, sys, time, sqlite3, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
    WEBAI_ENABLED='false', IY_WEB_ENABLED='false', SCHEDULER_ENABLED='false')
from core.config import settings
settings.DATABASE_PATH = DBPATH
from core.memory.db import DB
DB()

now = time.time()
with sqlite3.connect(DBPATH) as c:
    rows = []
    for i in range(10):
        rows.append((100 + i, f'BOL{i}', now - i * 86400 * 20, f'Buyer {i%4}', f'buyer{i%4}',
                     'Shenzhen Bright Wax Co', '', '3406', 'LED flameless rechargeable candle gift set', 500, 1200, 1, 'CN', 'NGB', 'LAX', 't'))
    rows.append((200, 'BOLX', now, 'Buyer 0', 'buyer0', 'Shenzhen Bright Wax Co', '', '3406', 'scented soy wax jar candle', 300, 800, 1, 'CN', 'NGB', 'LAX', 't'))
    c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)


def test_supplier_profile():
    from core.trade_graph import supplier_profile as sprof
    p = sprof.profile_supplier('Shenzhen Bright Wax Co', page_total=8, customers_found=4, run_id='t1')
    assert p is not None
    # 产品结构来自真实提单
    assert p['product_mix'] and p['product_mix'][0]['hs'] == '3406', p['product_mix']
    assert p['product_mix'][0]['shipments'] == 11
    # 档次推断：LED/rechargeable/gift set/soy wax → premium，且必须标注为推断
    assert p['tier'] == 'premium', p['tier']
    assert p['tier_signals'], '推断必须给出命中信号'
    assert 'inference' in p['tier_basis'] and '价格' in p['tier_basis']
    # 供应能力
    cap = p['capacity']
    assert cap['shipments'] >= 11 and cap['bol_records_local'] == 11
    assert cap['shipments_per_month'] and cap['avg_weight_kg_per_bol']
    # 客户覆盖：found 4 / total 8 = 50%，明确不是全部
    assert p['customers']['coverage'] == 0.5, p['customers']
    assert p['customers']['complete'] == 'partial'
    # 无总数时覆盖度如实为未知，而不是假装 100%
    p2 = sprof.profile_supplier('Shenzhen Bright Wax Co', page_total=0, customers_found=4, run_id='t2')
    assert p2['customers']['coverage'] is None and p2['customers']['complete'] == 'unknown'
    # 落表可读
    got = sprof.get_profile(p['norm'])
    assert got and got['supplier'] == 'Shenzhen Bright Wax Co'
    print('SUPPLIER_PROFILE_OK tier=%s coverage=%s' % (p['tier'], p['customers']['coverage']))


def test_pending_graph_nodes():
    from core.trade_graph import supplier_profile as sprof
    from core.tools import suppliers as sup
    sup.upsert_pool([{'norm': sup.norm('Shenzhen Bright Wax Co'), 'name': 'Shenzhen Bright Wax Co',
                      'slug': 'shenzhen-bright-wax', 'shipments': 11, 'last_seen': now}])
    from core.trade_graph import iy_network as iyn
    iyn.mark_node('buyer0', 'company', url='https://www.importyeti.com/company/buyer-0')
    p = sprof.pending_graph_nodes()
    assert p['unharvested_suppliers'] >= 1 and p['iy_nodes'] >= 1, p
    print('PENDING_GRAPH_OK', p)


def test_architecture_boundary():
    """编排器拥有控制权，节点只有执行权：FN 不得注册 ORDER 之外的节点。"""
    from core.runtime import graph
    assert set(graph.FN.keys()) == set(graph.ORDER), (set(graph.FN) ^ set(graph.ORDER))
    assert 'REFLECT' not in graph.FN, 'REFLECT 是小编排器残留，不得注册'
    # 节点函数不得返回流程控制字段（abort/next_node）——静态检查执行层纯度
    import inspect
    from core.runtime import nodes as N
    for name in graph.ORDER:
        src = inspect.getsource(graph.FN[name])
        assert "'abort'" not in src and '"abort"' not in src, f'{name} 试图控制流程走向'
        assert 'next_node' not in src, f'{name} 试图决定下一节点'
    print('ARCHITECTURE_BOUNDARY_OK FN==ORDER, nodes pure executors')


def test_iy_rel_limits():
    assert int(getattr(settings, 'IY_REL_MAX_ROWS', 0)) >= 50, '单点关系抓取上限必须足够大'
    import inspect
    from core.tools import iy_web
    assert 'last_total' in inspect.getsource(iy_web.IYWeb.__init__), 'IYWeb 必须暴露关系区总数 last_total'
    assert 'last_total' in inspect.getsource(iy_web.IYWeb._rel_once), '关系解析必须回写 last_total'
    print('IY_REL_LIMITS_OK max_rows=%s' % settings.IY_REL_MAX_ROWS)


if __name__ == '__main__':
    test_supplier_profile()
    test_pending_graph_nodes()
    test_architecture_boundary()
    test_iy_rel_limits()
    print('V30_4_ALL_OK')
