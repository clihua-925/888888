# -*- coding: utf-8 -*-
"""v30.7 贸易节点数据池 + 漏斗透明测试：
1. 渗透发现的每个节点（含残片）都登记 trade_nodes，原始关系行存档 raw_sources；
2. 物流/货代不再丢弃——停放节点池 role='logistics'，既是图谱证据也是收割路径；
3. 清洗验证漏斗透明：输入=输出+同名合并+物流入池+明确非企业，减少原因可解释；
4. 前端 selectedLeadNorm 已声明（v30.6 客户列表渲染崩溃的回归锁）。
"""
import os, sys, tempfile, sqlite3
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

from core.trade_graph import iy_penetration


class FakeWeb:
    PAGES = {
        'https://www.importyeti.com/company/acme': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/s1', 'shipments': 30, 'products': 'candles', 'hs': ['3406']},
            {'name': 'Fast Freight Logistics', 'url': 'https://www.importyeti.com/supplier/s2', 'shipments': 5}]),
        'https://www.importyeti.com/supplier/s1': ('Customers', [
            {'name': 'Buyer One', 'url': 'https://www.importyeti.com/company/b1', 'shipments': 9}]),
        'https://www.importyeti.com/supplier/s2': ('Customers', []),
        'https://www.importyeti.com/company/b1': ('Suppliers', [
            {'name': 'Supplier One', 'url': 'https://www.importyeti.com/supplier/s1', 'shipments': 30}]),
    }
    def __init__(self): self.last_total = 0; self.last_error = ''
    def search(self, q, limit=10): return []
    def relationships(self, url, section):
        e = self.PAGES.get(url)
        return e[1] if e else []
    def company_page_for(self, n): return ''
    def supplier_page_for(self, n): return ''


def test_penetration_writes_pool_and_raw():
    out = iy_penetration.penetrate(
        [{'name': 'Acme Imports', 'url': 'https://www.importyeti.com/company/acme', 'kind': 'company', 'shipments': 50}],
        FakeWeb(), task_id='pool1')
    assert out['nodes']
    pool = {t['name']: t for t in db.list_trade_nodes(limit=100)}
    for nm in ('Acme Imports', 'Supplier One', 'Buyer One'):
        assert nm in pool, f'节点未入池: {nm}'
    assert pool['Supplier One']['role'] == 'supplier'
    assert pool['Supplier One']['shipments'] == 30
    assert pool['Buyer One']['via'] == 'Supplier One'  # 关系路径可追溯
    # 原始页面关系行已存档（验证/证明/复核的一手证据）
    with sqlite3.connect(DBPATH) as c:
        raw_n = c.execute("SELECT COUNT(*) FROM raw_sources WHERE source='importyeti_penetration'").fetchone()[0]
    assert raw_n >= 3, raw_n
    print('PASS penetration_writes_pool_and_raw nodes=%d raw=%d' % (len(pool), raw_n))


def test_logistics_parked_not_dropped():
    from core.runtime import nodes as N
    state = {'task_id': 'funnel1', 'companies': [
        {'name': 'Real Buyer Co', 'type': 'importer', 'evidence': {'shipments': 5, 'customs': True}},
        {'name': 'Harbor Cargo Services', 'type': 'supplier', 'evidence': {'shipments': 5, 'customs': True, 'url': 'u2'}},
        {'name': 'Real Buyer Co', 'type': 'importer', 'evidence': {'shipments': 3}},  # 同名重复
        {'name': 'Candle Wiki Encyclopedia', 'type': 'importer', 'evidence': {}},      # 明确非企业
    ]}
    out = N.n_clean_verify(state)
    names = [c['name'] for c in out['companies']]
    assert names == ['Real Buyer Co']  # 客户侧只剩真实买家
    # 物流公司没有消失——在节点池里，role=logistics
    lg = db.list_trade_nodes(role='logistics')
    assert any(t['name'] == 'Harbor Cargo Services' for t in lg), lg
    # 漏斗透明：数字可解释
    f = [x for x in out['funnel'] if x['stage'] == 'ENTITY_RESOLUTION'][0]  # v34 节点名 canonical
    assert f['in'] == 4 and f['out'] == 1
    assert f['logistics_parked'] == 1 and f['duplicates_merged'] == 1 and f['dropped'] == 1
    assert f['out'] + f['logistics_parked'] + f['duplicates_merged'] + f['dropped'] == f['in']
    assert '物流入池 1' in out['_note'] and '同名合并 1' in out['_note']
    print('PASS logistics_parked_not_dropped', f)


def test_pool_upsert_accumulates():
    """重复出现只累加证据：票数取大、角色/URL 只补空、runs_seen 累加。"""
    n1 = db.upsert_trade_node('Accum Trader LLC', role='importer', shipments=5, via='t1')
    n2 = db.upsert_trade_node('Accum Trader LLC', role='', shipments=12, url='http://u', via='t2')
    assert n1 == n2
    t = [x for x in db.list_trade_nodes() if x['norm'] == n1][0]
    assert t['shipments'] == 12 and t['role'] == 'importer' and t['url'] == 'http://u'
    assert t['runs_seen'] == 2
    print('PASS pool_upsert_accumulates')


def test_frontend_var_declared():
    src = open(ROOT / 'core/webui/app.py', encoding='utf-8').read()
    assert 'selectedLeadNorm=null' in src, 'selectedLeadNorm 未声明，客户列表会再次渲染崩溃'
    assert 'data-kind' in src and 'currentKind' in src
    print('PASS frontend_var_declared')


if __name__ == '__main__':
    test_penetration_writes_pool_and_raw()
    test_logistics_parked_not_dropped()
    test_pool_upsert_accumulates()
    test_frontend_var_declared()
    print('ALL v30.7 trade pool tests PASS')
