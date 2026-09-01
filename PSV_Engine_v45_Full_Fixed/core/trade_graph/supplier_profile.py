# -*- coding: utf-8 -*-
"""v30.4 供应商单点画像（纯执行工具，不是节点、不做流程决策）。

回答一个具体问题：“这个核心供应商，我们分析清楚了没有？”
- 产品结构：提单 HS 编码 + 品名分布（来自本地 customs_raw 真实提单）
- 产品档次：关键词分层推断（premium/standard/economy），明确标注为“推断”，可被行业配置覆盖
- 供应能力：总票数、活跃期、月均票数、均票规模（数量/重量）
- 客户覆盖：已收客户数 vs 页面声明总客户数（iy_nodes/harvest 记录），覆盖不全如实标注
- 质价比：没有价格数据就不编造——只给出“规模/频次”侧写，并注明价格数据缺失

数据只来自海关提单与 ImportYeti 节点记录；产物写入 supplier_profiles 表，跨任务复用。
"""
import json, re, sqlite3, time
from core.config import settings
from core.tools import suppliers as sup

# 默认档次关键词（行业配置 industry['product_tiers'] 可覆盖）。
# 这是推断规则，不是事实；结论必须带 tier_basis 说明。
DEFAULT_TIERS = {
    'premium': ['led', 'remote', 'rechargeable', 'flameless', 'smart', 'organic', 'handmade',
                'luxury', 'gift set', 'soy wax', 'beeswax', 'essential oil', 'aromatherapy', 'custom'],
    'economy': ['tealight', 'tea light', 'bulk', 'unscented', 'plain', 'promotional', 'cheap', 'disposable'],
}
# standard = 命中不到 premium/economy 的默认档。


def _conn():
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table():
    with _conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS supplier_profiles('
                  'supplier_norm TEXT PRIMARY KEY, name TEXT, profile TEXT, tier TEXT, '
                  'shipments INT, coverage REAL, updated_at REAL)')


def _tier_rules():
    try:
        from core.config.industry import load_industry
        cfg = load_industry(getattr(settings, 'INDUSTRY', '') or '') or {}
        t = cfg.get('product_tiers')
        if isinstance(t, dict) and any(t.values()):
            return {k: [str(x).lower() for x in (v or [])] for k, v in t.items()}
    except Exception:
        pass
    return DEFAULT_TIERS


def _infer_tier(descriptions, rules):
    text = ' '.join(str(d or '').lower() for d in descriptions)
    hits = {'premium': [], 'economy': []}
    for tier, kws in rules.items():
        if tier not in hits:
            continue
        for kw in kws:
            if kw in text:
                hits[tier].append(kw)
    if hits['premium'] and len(hits['premium']) >= max(1, len(hits['economy'])):
        return 'premium', hits['premium'][:5]
    if hits['economy']:
        return 'economy', hits['economy'][:5]
    if text.strip():
        return 'standard', []
    return 'unknown', []


def profile_supplier(name, page_total=0, customers_found=0, run_id=''):
    """生成/刷新单个供应商画像并落表。所有数字必须可溯源；推断必须标注。"""
    ensure_table()
    n = sup.norm(name)
    if not n:
        return None
    now = time.time()
    hs_mix = {}
    descs = []
    shippers_rows = []
    with _conn() as c:
        rows = c.execute(
            'SELECT ts,hs,descr,qty,weight,teu,importer FROM customs_raw WHERE shipper=? ORDER BY ts ASC LIMIT 5000',
            (name,)).fetchall()
        # 名称变体（norm 相同的提单发货人）也并入
        if not rows:
            like = c.execute('SELECT DISTINCT shipper FROM customs_raw WHERE shipper!=""').fetchall()
            for r in like:
                if sup.norm(r['shipper']) == n:
                    rows += c.execute(
                        'SELECT ts,hs,descr,qty,weight,teu,importer FROM customs_raw WHERE shipper=? ORDER BY ts ASC LIMIT 5000',
                        (r['shipper'],)).fetchall()
    importers = set()
    total_qty = total_w = total_teu = 0.0
    dates = []
    for r in rows:
        hs = str(r['hs'] or '').strip()
        if hs:
            d = hs_mix.setdefault(hs, {'hs': hs, 'shipments': 0, 'samples': []})
            d['shipments'] += 1
            if r['descr'] and len(d['samples']) < 3:
                d['samples'].append(str(r['descr'])[:80])
        if r['descr']:
            descs.append(str(r['descr']))
        if r['importer']:
            importers.add(str(r['importer']).strip())
        total_qty += float(r['qty'] or 0)
        total_w += float(r['weight'] or 0)
        total_teu += float(r['teu'] or 0)
        if r['ts']:
            dates.append(float(r['ts']))
    # 池与节点注册表的补充信息（IY 侧）
    pool_shipments = 0
    with _conn() as c:
        pr = c.execute('SELECT shipments FROM suppliers WHERE supplier_norm=?', (n,)).fetchone()
        if pr:
            pool_shipments = int(pr['shipments'] or 0)
        iy = c.execute('SELECT shipments,url,visits FROM iy_nodes WHERE norm=? AND kind=?', (n, 'supplier')).fetchone()
    shipments = max(len(rows), pool_shipments, int(iy['shipments']) if iy else 0)
    months = 0.0
    if len(dates) >= 2:
        months = max(1.0, (max(dates) - min(dates)) / 86400 / 30.4)
    tier, signals = _infer_tier(descs, _tier_rules())
    local_customers = len(importers)
    found = max(customers_found, local_customers)
    coverage = None
    if page_total and page_total > 0:
        coverage = round(min(1.0, found / page_total), 3)
    src = []
    if rows:
        src.append('customs_raw')
    if iy:
        src.append('importyeti')
    profile = {
        'supplier': name, 'norm': n,
        'product_mix': sorted(hs_mix.values(), key=lambda x: -x['shipments'])[:6],
        'tier': tier, 'tier_signals': signals,
        'tier_basis': 'keyword inference from BOL descriptions; not verified — 价格/质价比需要报价数据，当前无价格源，不做编造',
        'capacity': {
            'shipments': shipments,
            'bol_records_local': len(rows),
            'first_seen': time.strftime('%Y-%m-%d', time.localtime(min(dates))) if dates else '',
            'last_seen': time.strftime('%Y-%m-%d', time.localtime(max(dates))) if dates else '',
            'months_active': round(months, 1),
            'shipments_per_month': round(shipments / months, 2) if months else None,
            'avg_qty_per_bol': round(total_qty / len(rows), 1) if rows else None,
            'avg_weight_kg_per_bol': round(total_w / len(rows), 1) if rows else None,
            'total_teu': round(total_teu, 1) if rows else None,
        },
        'customers': {
            'found': found, 'local_bol_customers': local_customers,
            'page_total': int(page_total or 0) or None,
            'coverage': coverage,
            'complete': (coverage is None and 'unknown') or ('full' if coverage >= 0.99 else 'partial'),
            'note': 'page_total 来自 ImportYeti 关系区声明总数；为 0 表示页面未显示总数，覆盖度未知',
        },
        'sources': src, 'run_id': run_id, 'updated_at': now,
    }
    with _conn() as c:
        c.execute('INSERT INTO supplier_profiles(supplier_norm,name,profile,tier,shipments,coverage,updated_at) '
                  'VALUES(?,?,?,?,?,?,?) ON CONFLICT(supplier_norm) DO UPDATE SET '
                  'name=excluded.name,profile=excluded.profile,tier=excluded.tier,shipments=excluded.shipments,'
                  'coverage=excluded.coverage,updated_at=excluded.updated_at',
                  (n, name, json.dumps(profile, ensure_ascii=False), tier, shipments,
                   coverage if coverage is not None else -1, now))
    return profile


def get_profile(supplier_norm):
    ensure_table()
    with _conn() as c:
        r = c.execute('SELECT profile FROM supplier_profiles WHERE supplier_norm=?', (supplier_norm,)).fetchone()
    if not r:
        return None
    try:
        return json.loads(r['profile'])
    except Exception:
        return None


def list_profiles(limit=500):
    ensure_table()
    with _conn() as c:
        rows = c.execute('SELECT * FROM supplier_profiles ORDER BY shipments DESC LIMIT ?', (int(limit),)).fetchall()
    out = []
    for r in rows:
        try:
            p = json.loads(r['profile'])
        except Exception:
            p = {'supplier': r['name']}
        p['tier'] = r['tier']
        p['coverage'] = None if float(r['coverage'] or 0) < 0 else r['coverage']
        out.append(p)
    return out


def pending_graph_nodes():
    """图谱待展开节点数：未收割供应商 + 已发现但未访问的买家节点。
    让“反复运行即可完善图谱”变成可见、可度量的数字。"""
    ensure_table()
    with _conn() as c:
        unharvested = c.execute("SELECT COUNT(*) n FROM suppliers WHERE harvested_at IS NULL OR harvested_at=''").fetchone()['n']
        iy_total = c.execute('SELECT COUNT(*) n FROM iy_nodes').fetchone()['n']
        rel_total = c.execute('SELECT COUNT(*) n FROM relationships').fetchone()['n']
    return {'unharvested_suppliers': int(unharvested), 'iy_nodes': int(iy_total), 'relationships': int(rel_total)}
