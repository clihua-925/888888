# -*- coding: utf-8 -*-
"""v30.5 节点渗透（纯执行工具，非节点、不做流程决策）。

用户定义的第一采集链核心：
    关键词在 ImportYeti 网站锁定节点 → 打开节点把关联信息全部拉出 →
    残片（不管是直接还是间接连得上贸易关系的）全部保留 → 残片变成新节点继续渗透 →
    每一环都在 ImportYeti 页面上完成，天然满足“ImportYeti 是验证标准” →
    交叉连接，整张贸易关系网自己长出来。

防枯竭三件套（v30.3 建立）全部生效：
    - 页访预算 PageBudget：每个节点页真实消耗一次预算，耗尽即停，已挖关系全部保留；
    - 节点注册表 iy_nodes：NODE_REVISIT_DAYS 内访问过的节点不再打开；
    - visited 集合：单次渗透内同一节点（含环）绝不重复访问。

关系卡片自带 url，渗透过程零额外搜索；只有入口锁定节点缺 url 时才按名搜索解析。
"""
import time
from core.config import settings


def _norm(name):
    from core.tools.data_sources.manager import norm
    return norm(name)


def _node_dict(name, kind, url, shipments, depth, via, relation_from='', products='', hs=None, page_total=0):
    role = 'supplier' if kind == 'supplier' else 'importer'
    # v30.8 节点七要素之 country：只写有来源支撑的事实——ImportYeti 覆盖美国进口数据，
    # /company/ 页即美国进口商；供应商国别页面未给出时留空，绝不编造。
    country = 'USA' if kind == 'company' else ''
    ev = {'customs': True, 'trade_evidence': True, 'iy_verified': True,
          'shipments': int(shipments or 0), 'products': products or '',
          'hs': hs or [], 'url': url or '', 'depth': depth,
          'via': via, 'page_total': int(page_total or 0)}
    if relation_from:
        ev['supplier_relation' if role == 'supplier' else 'customer_relation'] = relation_from
    return {'name': name, 'country': country, 'industry': '', 'type': role,
            'website': '', 'source': 'importyeti_penetration', 'strength': 5, 'evidence': ev}


def penetrate(seeds, w, budget=None, max_depth=None, max_nodes=None, task_id=''):
    """从锁定节点做广度优先渗透。返回 {nodes, relations, stats}。

    seeds: [{name,url,kind,shipments}] —— 第一搜索锁定的节点卡片（company/supplier）。
    w: IYWeb 会话；budget: PageBudget（默认新建，读取 IY_PAGE_BUDGET）。
    """
    from core.trade_graph import iy_network as iyn
    budget = budget or iyn.PageBudget()
    max_depth = int(max_depth if max_depth is not None else getattr(settings, 'IY_PENETRATION_DEPTH', 2))
    max_nodes = int(max_nodes or getattr(settings, 'COLLECT_MAX_NODES', 300))
    nodes = {}
    relations = []
    visited = set()
    stats = {'pages': 0, 'skipped_fresh': 0, 'locked': len(seeds or []),
             'depth_reached': 0, 'stopped_by': ''}
    frontier = []
    for s in (seeds or []):
        nm = (s.get('name') or '').strip()
        if not nm:
            continue
        kind = 'supplier' if (s.get('kind') == 'supplier' or '/supplier/' in str(s.get('url') or '')) else 'company'
        n = _norm(nm)
        if n and n not in nodes:
            nodes[n] = _node_dict(nm, kind, s.get('url') or '', s.get('shipments') or 0, 0, 'iy_search_lock')
            frontier.append({'name': nm, 'url': s.get('url') or '', 'kind': kind,
                             'shipments': int(s.get('shipments') or 0), 'depth': 0})
    # v30.7：渗透发现的每一个节点都登记进贸易节点数据池（trade_nodes）——
    # 后续无论它成为客户、供应商还是仅作图谱证据，原始发现永不丢失。
    try:
        from core.memory.db import DB as _DB
        _db = _DB()
    except Exception:
        _db = None
    fails = 0
    while frontier:
        if len(nodes) >= max_nodes:
            stats['stopped_by'] = 'max_nodes'; break
        if budget.exhausted:
            stats['stopped_by'] = 'page_budget'; break
        if fails >= 3:
            stats['stopped_by'] = 'circuit_breaker'; break
        frontier.sort(key=lambda x: -x['shipments'])  # 预算优先烧给高票数节点
        cur = frontier.pop(0)
        key = (_norm(cur['name']), cur['kind'])
        if not key[0] or key in visited:
            continue
        visited.add(key)
        if iyn.node_fresh(*key):
            stats['skipped_fresh'] += 1
            continue
        url = cur.get('url') or iyn.node_url(*key)
        if not url:
            if not budget.take('search:' + cur['name'][:40]):
                stats['stopped_by'] = 'page_budget'; break
            stats['pages'] += 1
            url = (w.company_page_for(cur['name']) if cur['kind'] == 'company'
                   else w.supplier_page_for(cur['name'])) or ''
        if not url:
            fails += 1
            continue
        if not budget.take('page:' + url[-60:]):
            stats['stopped_by'] = 'page_budget'; break
        section = 'Suppliers' if cur['kind'] == 'company' else 'Customers'
        rows = w.relationships(url, section) or []
        stats['pages'] += 1
        if not rows and getattr(w, 'last_error', ''):
            fails += 1
            continue
        fails = 0
        # 原始页面关系行存档：验证客户/证明关系/复核图谱的一手证据，可回放。
        if _db is not None:
            try:
                _db.upsert_trade_node(cur['name'], role='supplier' if cur['kind'] == 'supplier' else 'importer',
                                      url=url, shipments=cur['shipments'], depth=cur['depth'],
                                      via='iy_penetration', source='importyeti_penetration',
                                      country='USA' if cur['kind'] == 'company' else '')
                _db.save_raw_source('importyeti_penetration', url, {'section': section, 'rows': rows[:100]})
            except Exception:
                pass
        stats['depth_reached'] = max(stats['depth_reached'], cur['depth'] + 1)
        page_total = int(getattr(w, 'last_total', 0) or 0)
        iyn.mark_node(key[0], key[1], slug=url.rstrip('/').split('/')[-1], url=url,
                      shipments=cur['shipments'], run_id=task_id)
        child_kind = 'supplier' if section == 'Suppliers' else 'company'
        pool_entries = []
        for r in rows:
            nm = (r.get('name') or '').strip()
            cn = _norm(nm)
            if not cn:
                continue
            rel = {'from_name': cur['name'],
                   'from_type': 'buyer' if cur['kind'] == 'company' else 'supplier',
                   'to_name': nm,
                   'to_type': 'supplier' if child_kind == 'supplier' else 'buyer',
                   'relation': 'buyer_to_supplier' if child_kind == 'supplier' else 'supplier_to_customer',
                   'evidence': {'customs': True, 'trade_evidence': True, 'iy_verified': True,
                                'shipments': r.get('shipments') or 0,
                                'products': r.get('products') or '', 'hs': r.get('hs') or [],
                                'url': r.get('url') or url},
                   'source': 'importyeti_penetration', 'confidence': .95}
            relations.append(rel)
            if cn not in nodes:
                nodes[cn] = _node_dict(nm, child_kind, r.get('url') or '',
                                       r.get('shipments') or 0, cur['depth'] + 1,
                                       'iy_penetration', relation_from=cur['name'],
                                       products=r.get('products') or '',
                                       hs=r.get('hs') or [], page_total=page_total)
            if _db is not None:
                try:
                    _db.upsert_trade_node(nm, role='supplier' if child_kind == 'supplier' else 'importer',
                                          url=r.get('url') or '', shipments=r.get('shipments') or 0,
                                          products=r.get('products') or '', hs=r.get('hs') or [],
                                          depth=cur['depth'] + 1, via=cur['name'],
                                          source='importyeti_penetration',
                                          country='USA' if child_kind == 'company' else '')
                except Exception:
                    pass
            if child_kind == 'supplier':
                pool_entries.append({'norm': cn, 'name': nm,
                                     'slug': (r.get('url') or '').rstrip('/').split('/')[-1] if r.get('url') else '',
                                     'shipments': int(r.get('shipments') or 0), 'last_seen': time.time()})
            # 残片继续渗透：深度内、未访问过的节点入队（卡片自带 url，零额外搜索）
            if cur['depth'] + 1 <= max_depth:
                frontier.append({'name': nm, 'url': r.get('url') or '', 'kind': child_kind,
                                 'shipments': int(r.get('shipments') or 0), 'depth': cur['depth'] + 1})
        if pool_entries:
            try:
                from core.tools import suppliers as sup
                sup.upsert_pool(pool_entries)
            except Exception:
                pass
    if not stats['stopped_by']:
        stats['stopped_by'] = 'frontier_drained'
    stats['nodes'] = len(nodes)
    stats['relations'] = len(relations)
    return {'nodes': list(nodes.values()), 'relations': relations, 'stats': stats}
