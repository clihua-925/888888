"""v30 iy_web 解析器回归：宽松节点定位 + 关系卡片解析 + 节点渗透链。"""
import os, sys, time, sqlite3, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_PATH'] = DBPATH
os.environ['EXPERT_MODE'] = 'false'; os.environ['MISSION_DIRECTOR_ENABLED'] = 'false'
os.environ['WEBAI_ENABLED'] = 'false'; os.environ['IY_WEB_ENABLED'] = 'false'
os.environ['IMPORTYETI_ENABLED'] = 'false'; os.environ['HS_FINDER_ENABLED'] = 'false'
os.environ['IMPORTKEY_ENABLED'] = 'false'; os.environ['GATE_MIN_QUALIFIED'] = '1'
os.environ['SCHEDULER_ENABLED'] = 'false'

from core.config import settings
settings.DATABASE_PATH = DBPATH
for k in ('EXPERT_MODE','MISSION_DIRECTOR_ENABLED','WEBAI_ENABLED','IY_WEB_ENABLED',
          'IMPORTYETI_ENABLED','HS_FINDER_ENABLED','IMPORTKEY_ENABLED','SCHEDULER_ENABLED'):
    setattr(settings, k, False)
settings.HARVEST_ENABLED = True
settings.GATE_MIN_QUALIFIED = 1

from core.memory.db import DB
DB()


def test_search_card_parsers():
    from core.tools.iy_web import parse_search_card, _shipments_from
    # 老结构
    c = parse_search_card('Acme Candle LLC\ncompany\nBellevue, WA\nTotal Shipments\n1,234\nMost recent shipment\n2026-08-01')
    assert c['kind'] == 'company' and c['shipments'] == 1234 and c['last_seen'] == '2026-08-01'
    # 新写法：数字在 Shipments 前
    assert _shipments_from('Total Shipments: 56') == 56
    assert _shipments_from('2,341 Shipments') == 2341
    # 缺字段不丢节点（宽松）
    c2 = parse_search_card('Some Buyer Inc\ncompany')
    assert c2['kind'] == 'company' and c2['shipments'] == 0
    print('SEARCH_CARD_OK')


def test_rel_card_parser():
    from core.tools.iy_web import parse_rel_card
    c = parse_rel_card('Shenzhen Wax Factory\nGuangdong, CN\n412\nCandles, wax products\nHS Codes: (3406, 9503)\nSee all bills of lading with this supplier')
    assert c['shipments'] == 412, c
    assert '3406' in c['hs'], c
    c2 = parse_rel_card('Ningbo Light Co\n88 Shipments\ncandle jars')
    assert c2['shipments'] == 88, c2
    c3 = parse_rel_card('No shipment info here')
    assert c3['shipments'] == 0
    print('REL_CARD_OK')


def test_penetration_chain():
    """节点渗透：搜索落池的 supplier 节点必须进入反查链并挖出客户，收割后状态持久。"""
    now = time.time()
    with sqlite3.connect(DBPATH) as c:
        rows = [
            ('1','BOL1',now,'Buyer A','buyera','Pool Supplier X','','3406','candles',1,1,0,'CN','NGB','LAX','t'),
            ('2','BOL2',now-10,'Buyer B','buyerb','Pool Supplier X','','3406','candles',1,1,0,'CN','NGB','LAX','t'),
        ]
        c.executemany('INSERT INTO customs_raw(id,bol,ts,importer,importer_norm,shipper,notify,hs,descr,qty,weight,teu,origin,port_load,port_discharge,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
    from core.tools import suppliers as sup
    # 模拟第一搜索把 supplier 卡片落池（iy_web 搜索页行为）
    sup.upsert_pool([{'norm': sup.norm('Pool Supplier X'), 'name': 'Pool Supplier X',
                      'slug': 'pool-supplier-x', 'shipments': 30, 'last_seen': now}])
    state = {'task_id': 'pen-test', 'market': 'USA', 'industry': 'candle', 'quantity': 3,
             'companies': [{'name': 'Buyer A', 'type': 'importer', 'source': 'importyeti_web',
                            'evidence': {'shipments': 2, 'customs': True}}],
             'seed_buyers': [{'name': 'Buyer A', 'type': 'importer', 'evidence': {'shipments': 2}}],
             'node_reports': {}}
    from core.runtime import nodes as N
    out = N.n_supplier_mining(dict(state))
    names = {x['name'] for x in out.get('suppliers') or []}
    assert 'Pool Supplier X' in names, names          # 池里的节点进入了反查链
    assert out.get('supplier_new'), 'supplier_new 不能为空（未收割节点必须进入渗透）'
    st = dict(state); st.update(out)
    out2 = N.n_reverse_harvest(st)
    new_names = {c['name'] for c in out2.get('companies') or []}
    assert 'Buyer B' in new_names, new_names          # 通过该节点把客户挖出来了
    # 收割状态持久：再次挖供应商时该节点已被标记，不再重复反查
    out3 = N.n_supplier_mining(dict(state))
    still_new = {x['name'] for x in out3.get('supplier_new') or []}
    assert 'Pool Supplier X' not in still_new, still_new
    print('PENETRATION_OK', sorted(names), '-> buyers:', sorted(new_names))


def test_importyeti_first_order():
    """v30.2 恢复 v10 原始源序：hs_finder(HS榜单) → 本地海关库 → importyeti_web → importyeti API → customs_web；
    变体循环在外、源循环在内，且通用搜索引擎不属于第一采集链。"""
    import inspect
    from core.tools.data_sources.manager import DataSourceManager
    src = inspect.getsource(DataSourceManager.search)
    i_pipe = src.find('pipeline=[')
    assert i_pipe > 0, 'v10 pipeline loop missing'
    pipe = src[i_pipe:i_pipe+400]
    order = [pipe.find(x) for x in ("'hs_finder'", "'customs_local'", "'importyeti_web'", "'importyeti'", "'customs_web'")]
    assert all(x > 0 for x in order) and order == sorted(order), order
    assert 'breaker' in src and '>=2' in src, 'per-source circuit breaker missing'
    assert 'for qv in variants' in src and src.find('for qv in variants') < src.find('for name,fn'), 'variants-outer loop missing'
    assert 'bing' not in src and 'duckduckgo' not in src.lower(), 'search engine leaked into first chain'
    print('ORDER_OK v10 source order: hs_finder -> customs_local -> importyeti_web -> importyeti -> customs_web')


if __name__ == '__main__':
    test_search_card_parsers()
    test_rel_card_parser()
    test_penetration_chain()
    test_importyeti_first_order()
    print('V30_IY_PARSERS_ALL_OK')
