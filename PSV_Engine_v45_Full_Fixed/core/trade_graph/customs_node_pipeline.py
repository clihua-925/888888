# -*- coding: utf-8 -*-
"""v30 第一采集链：Customs Node Pipeline（恢复 v10 设计思想，落在 v29 底座上）。

链路定义（第一采集链必须以海关节点为中心，而不是搜索引擎结果为中心）：

    TRADE_ENTRY      关键词 → HS 编码 → 海关贸易数据源定位贸易节点
                     （本地提单库 customs_raw/buyers_90d、ImportYeti 海关榜单/摘要、
                       用户配置的授权海关端点；不使用通用搜索引擎结果）
    NODE_IDENTIFY    从海关记录确定 importer / supplier / shipper /
                     consignee / notify party 节点，保存贸易证据（BOL/HS/shipments）
    NETWORK_EXPAND   从节点展开关联企业：buyer→supplier、supplier→customer（customs_graph）
    GRAPH_SAVE       节点与边落盘（relationships / evidence_events），形成贸易关系图谱

第一阶段只建完整贸易节点图；客户价值判断（评分/分级）属于第二阶段，不在此处发生。
"""
import time

from core.config import settings
from core.trade_graph.trade_node import (TradeNode, TradeEdge, TradeGraph, is_non_company_name,
                                         TradeEvidence, norm_name, normalize_role,
                                         TRADE_SIGNALS)

STAGES = ['TRADE_ENTRY', 'NODE_IDENTIFY', 'NETWORK_EXPAND', 'GRAPH_SAVE']


# ---------- 关键词 → HS 编码（v10 入口：先定位 HS，再进海关榜单） ----------
def resolve_hs_codes(industry, icp=None):
    codes = []
    try:
        from core.config.industry import load_industry
        codes += [str(x) for x in (load_industry(industry).get('hs_codes') or [])]
    except Exception:
        pass
    for x in ((icp or {}).get('hs') or []):
        codes.append(str(x))
    for x in str(getattr(settings, 'HS_CODES', '') or '').split(','):
        if x.strip():
            codes.append(x.strip())
    out = []
    for c in codes:
        c = c.strip()
        if c and c not in out:
            out.append(c)
    return out


# ---------- 候选 → 贸易节点角色识别 ----------
def detect_role(candidate):
    """根据候选的 type/kind/来源/证据判定其贸易角色。不确定时按 importer（海关源的默认角色）。"""
    typ = str(candidate.get('type') or candidate.get('kind') or '').lower()
    if typ in ('supplier', 'manufacturer', 'factory', 'shipper', 'exporter',
               'consignee', 'notify', 'notify party', 'notify_party'):
        return normalize_role(typ)
    src = str(candidate.get('source') or '').lower()
    ev = candidate.get('evidence') or {}
    if ev.get('supplier_relation'):
        return 'importer'          # 通过供应商反查到的买家节点
    if 'hs_bol' in str(ev.get('via') or ''):
        return 'shipper'           # HS 榜页底提单表里的发货人种子
    if typ in ('importer', 'buyer', 'customer'):
        return 'importer'
    # 文本信号兜底：shipper/consignee/notify party 等角色词
    text = ' '.join([str(candidate.get('name') or ''), str(ev.get('products') or ''),
                     str(ev.get('reasons') or '')]).lower()
    for sig in ('notify party', 'consignee', 'shipper', 'exporter',
                'manufacturer', 'supplier'):
        if sig in text:
            return normalize_role(sig)
    return 'importer'


def candidate_to_node(candidate):
    """把一个候选公司卡片转成 TradeNode（携带全部贸易证据，不做评分）。
    v35：伪实体（国家/城市/港口/地址/占位文本）返回 None，调用方必须跳过。"""
    if is_non_company_name(candidate.get('name')):
        return None
    ev = candidate.get('evidence') or {}
    node = TradeNode(candidate.get('name'), detect_role(candidate),
                     candidate.get('source') or '')
    node.add_evidence(TradeEvidence(
        bol=ev.get('bol') or ev.get('bill_of_lading') or '',
        hs=ev.get('hs') or ([ev['hs_code']] if ev.get('hs_code') else []),
        shipments=ev.get('shipments') or 0,
        last_shipment=ev.get('last_shipment') or ev.get('last_seen') or '',
        products=ev.get('products') or ([ev['descr']] if ev.get('descr') else []),
        source=candidate.get('source') or '', url=ev.get('url') or '',
        raw_ids=ev.get('raw_ids') or [],
        confidence=0.95 if 'importyeti' in str(candidate.get('source') or '') else 1.0))
    return node


def build_trade_nodes(companies):
    """候选列表 → TradeGraph（纯内存；不评分、不淘汰，只识别角色与证据）。"""
    graph = TradeGraph()
    for c in (companies or []):
        node = candidate_to_node(c)
        if node is not None and node.norm:
            graph.add_node(node)
            c['node_role'] = node.role
            (c.setdefault('evidence', {}))['node_role'] = node.role
    return graph


# ---------- 节点 → 关联企业展开（委托 v27/v29 已验证的 customs_graph） ----------
def expand_from_nodes(seed_names, task_id='', per_supplier=None, per_customer=None):
    """从种子节点双向展开：buyer→supplier、supplier→customer。
    返回 (graph, relations)；relations 供节点落盘 relationships 表。"""
    from core.tools import customs_graph
    graph = TradeGraph()
    relations = []
    suppliers, rel1 = customs_graph.buyer_to_suppliers(
        [{'name': n} for n in seed_names], per_supplier)
    for s in suppliers:
        if is_non_company_name(s.get('name')):
            continue
        node = TradeNode(s.get('name'), 'supplier', s.get('via') or 'customs_raw')
        node.add_evidence(s.get('evidence') or {})
        graph.add_node(node)
    buyers, rel2 = customs_graph.supplier_to_buyers(suppliers, per_customer)
    for b in buyers:
        if is_non_company_name(b.get('name')):
            continue
        node = TradeNode(b.get('name'), 'importer', b.get('source') or 'customs_reverse')
        node.add_evidence(b.get('evidence') or {})
        graph.add_node(node)
    for rel in list(rel1 or []) + list(rel2 or []):
        edge = TradeEdge(rel.get('from_name'), rel.get('from_type'),
                         rel.get('to_name'), rel.get('to_type'),
                         rel.get('relation'), rel.get('evidence'),
                         rel.get('source'), rel.get('confidence', 1.0))
        graph.add_edge(edge)
        relations.append(rel)
    return graph, relations


def relations_to_edges(relations, depth=1):
    """把 runtime 节点产出的 relation dict 转成 TradeEdge 列表（供图谱合并）。"""
    out = []
    for rel in (relations or []):
        out.append(TradeEdge(rel.get('from_name'), rel.get('from_type'),
                             rel.get('to_name'), rel.get('to_type'),
                             rel.get('relation'), rel.get('evidence'),
                             rel.get('source'), rel.get('confidence', 1.0), depth))
    return out


def save_graph(graph, task_id='', depth=1):
    """GRAPH_SAVE：贸易证据事件落盘（候选审计层，失败不阻塞主流程）。
    v34 收敛：relationships 正式写库唯一出口是 DATABASE_COMMIT——本函数不再写关系边，
    边由 trade_graph → nodes._sync_edges_from_graph → DATABASE_COMMIT 单通道落库。"""
    saved_e = 0
    try:
        from core.memory.db import DB
        db = DB()
        for node in graph.nodes.values():
            for ev in node.evidence:
                if not ev.is_hard:
                    continue
                try:
                    db.add_evidence_event(task_id, node.norm, 'customs_trade_node',
                                          ev.source or 'customs',
                                          str(ev.to_dict())[:1800], ev.confidence)
                    saved_e += 1
                except Exception:
                    pass
    except Exception:
        pass
    return {'evidence_saved': saved_e, 'relations_saved': 0,
            'edges_deferred_to_commit': len(getattr(graph, 'edges', []) or [])}


def merge_graph_into_state(state, graph, depth=1):
    """把本轮图谱合并进黑板 state['trade_graph']（dict 形式，UI/落盘可读）。"""
    base = TradeGraph.from_state(state)
    for node in graph.nodes.values():
        base.add_node(node)
    for edge in graph.edges:
        edge.depth = depth
        base.add_edge(edge)
    state['trade_graph'] = base.to_dict()
    return state['trade_graph']


def trade_signal_hit(text):
    t = str(text or '').lower()
    return any(sig in t for sig in TRADE_SIGNALS)


class CustomsNodePipeline:
    """第一采集链编排器：供 runtime 的 A_COLLECT 调用。

    run() 内部委托 DataSourceManager 做海关源 fan-out（含 v10 的 HS 榜单入口），
    然后做节点识别与证据保存；网络展开由后续 SUPPLIER_MINING / REVERSE_HARVEST 完成，
    这里只建立“节点 + 待展开种子”。
    """

    def __init__(self):
        self.hs_codes = []
        self.graph = TradeGraph()
        self.last_evolution = {}

    def run(self, market, industry, quantity, queries=None, source_queries=None,
            icp=None, task_id='', penetrate_iy=True):
        """v30.5 节点渗透版第一链：

        1) 第一次动作 = 在 ImportYeti 网站用关键词搜索，锁定贸易节点（不是找客户名单）；
        2) 从锁定节点递归渗透（iy_penetration）：节点的供应商、供应商的客户……
           残片全部保留，每一环都在 IY 页面上完成（IY 即验证标准），图谱自己长出来；
        3) 本地提单库/HS榜单/API 等来源作为碎片补充并入（不占 IY 页访预算）；
        4) 残片不按 quantity 截断（仅 COLLECT_MAX_NODES 安全上限）——第一阶段建完整图谱。
        """
        from core.tools.data_sources.manager import DataSourceManager, norm
        self.hs_codes = resolve_hs_codes(industry, icp)
        errors = []
        pen_stats = {}
        pen_nodes, pen_relations = [], []
        variants = [q for q in (queries or [industry]) if q]
        # ---- 第 1+2 步：ImportYeti 节点进入 + 递归渗透 ----
        if penetrate_iy and getattr(settings, 'IY_WEB_ENABLED', False):
            try:
                from core.tools import iy_web
                if iy_web.available():
                    from core.trade_graph import iy_penetration
                    with iy_web.IYWeb() as w:
                        locked = []
                        for qv in variants[:int(getattr(settings, 'IY_SEARCH_VARIANTS', 3))]:
                            try:
                                locked.extend(w.search(qv, settings.IY_WEB_SEARCH_LIMIT) or [])
                            except Exception as e:
                                errors.append('iy_search:' + str(e)[:100])
                        out = iy_penetration.penetrate(locked, w, task_id=task_id)
                        pen_nodes, pen_relations = out['nodes'], out['relations']
                        pen_stats = out['stats']
            except Exception as e:
                errors.append('iy_penetration:' + str(e)[:120])
        # ---- 第 3 步：其他海关源碎片补充（本地提单库/HS榜单/API，免费） ----
        mgr = DataSourceManager()
        try:
            companies, used, errors2, gate = mgr.search(
                market, industry, quantity,
                variants_override=queries, source_queries=source_queries,
                hs_codes=self.hs_codes)
        except TypeError:
            # 兼容旧签名/测试桩：不支持 hs_codes 参数时降级为原调用
            companies, used, errors2, gate = mgr.search(
                market, industry, quantity,
                variants_override=queries, source_queries=source_queries)
        errors.extend(errors2 or [])
        self.last_evolution = mgr.last_evolution
        # ---- 合并：渗透残片 + 多源碎片，按实体去重，不按数量截断 ----
        # v30.8 统一 Trade Evidence 层：ImportYeti/customs_raw/buyers_90d/API 等所有来源的
        # 碎片一律先登记 trade_nodes 数据池——无论最终是否成为客户，发现即资产。
        try:
            from core.memory.db import DB as _DB
            _pool_db = _DB()
        except Exception:
            _pool_db = None
        merged = {}
        for c in list(pen_nodes) + list(companies or []):
            n = norm(c.get('name'))
            if not n:
                continue
            if n not in merged:
                merged[n] = c
            else:
                m = merged[n]
                me, e = m.setdefault('evidence', {}), c.get('evidence') or {}
                me['shipments'] = max(int(me.get('shipments') or 0), int(e.get('shipments') or 0))
                for k in ('url', 'products', 'last_shipment'):
                    if not me.get(k) and e.get(k):
                        me[k] = e[k]
                me['iy_verified'] = bool(me.get('iy_verified') or e.get('iy_verified'))
                m['source'] = (str(m.get('source') or '') + '+' + str(c.get('source') or '')).strip('+')
            if _pool_db is not None:
                try:
                    e0 = c.get('evidence') or {}
                    _pool_db.upsert_trade_node(c.get('name'),
                        role=('supplier' if (c.get('type') == 'supplier' or c.get('node_role') == 'supplier') else 'importer'),
                        url=e0.get('url') or '', shipments=e0.get('shipments') or 0,
                        products=e0.get('products') or '', hs=e0.get('hs') or [],
                        depth=e0.get('depth') or 0, via=e0.get('via') or '',
                        source=c.get('source') or '', country=c.get('country') or '')
                except Exception:
                    pass
        companies = list(merged.values())[:int(getattr(settings, 'COLLECT_MAX_NODES', 300))]
        if pen_nodes and 'importyeti_penetration' not in (used or []):
            used = list(used or []) + ['importyeti_penetration']
        gate = dict(gate or {})
        gate['raw'] = int(gate.get('raw') or 0) + len(pen_nodes)
        # ---- 节点识别 + 渗透边入图 ----
        self.graph = build_trade_nodes(companies)
        for e in relations_to_edges(pen_relations, 1):
            self.graph.add_edge(e)
        stats = self.graph.stats()
        stats['hs_codes'] = self.hs_codes
        stats['penetration'] = pen_stats
        # v30.8 图谱口径指标：买家/供应商分列 + 网络深度（图谱指标而非公司计数）
        stats['buyers'] = sum(1 for c in companies if (c.get('type') or c.get('node_role')) != 'supplier')
        stats['suppliers'] = sum(1 for c in companies if (c.get('type') or c.get('node_role')) == 'supplier')
        stats['network_depth'] = max([int((c.get('evidence') or {}).get('depth') or 0) for c in companies] + [0])
        return companies, used, errors, gate, self.graph, stats
