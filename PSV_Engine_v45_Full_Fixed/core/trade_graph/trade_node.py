# -*- coding: utf-8 -*-
"""v30 贸易节点模型（Customs Node Edition）。

第一采集链的基本单元不再是“网页搜索结果”，而是“海关贸易数据节点”：

    关键词 → 海关贸易数据节点 → 确定 importer / supplier / shipper 节点
           → 保存贸易证据 → 从节点展开关联企业 → 贸易关系图谱

本模块只定义数据结构，不做网络请求，不做评分。
第一阶段目标：建立完整贸易节点图；客户价值判断属于第二阶段（A_GATE / SCORING）。
"""
import re

# 海关提单上可识别的贸易角色（第一轮保留清单）
ROLES = ('importer', 'exporter', 'supplier', 'manufacturer',
         'shipper', 'consignee', 'notify_party')

# 角色别名归一：来自不同数据源的 type/kind 标注统一映射到 ROLES
ROLE_ALIASES = {
    'importer': 'importer', 'buyer': 'importer', 'customer': 'importer',
    'consignee': 'consignee', 'notify': 'notify_party', 'notify party': 'notify_party',
    'notify_party': 'notify_party',
    'exporter': 'exporter', 'shipper': 'shipper', 'supplier': 'supplier',
    'manufacturer': 'manufacturer', 'factory': 'manufacturer',
}

# 贸易证据信号：候选文本/证据中出现即视为“贸易节点”，第一轮必须保留
TRADE_SIGNALS = (
    'importer', 'importer of record', 'exporter', 'supplier', 'manufacturer',
    'shipper', 'consignee', 'notify party', 'hs code', 'hs_code', 'hts',
    'shipment', 'shipments', 'bill of lading', 'bol', 'b/l', 'teu',
    'customs', 'trade evidence', 'import records', 'port of loading',
    'port of discharge', '提单', '海关',
)

_SUFFIX_RE = re.compile(
    r'\b(the|inc|llc|co|ltd|corp|corporation|company|gmbh|sarl|limited|group|factory|trading|trade|international|intl)\b')


def norm_name(name):
    """与 customs_graph.norm 保持一致的实体归一（图谱节点 ID）。"""
    s = str(name or '').lower().strip()
    s = _SUFFIX_RE.sub(' ', s)
    return re.sub(r'[^a-z0-9]+', '', s)


def normalize_role(role, default='importer'):
    r = str(role or '').lower().strip()
    return ROLE_ALIASES.get(r, r if r in ROLES else default)


class TradeEvidence:
    """一条贸易证据：BOL / HS / shipment / 日期 / 来源。证据是节点存在的前提。"""

    __slots__ = ('bol', 'hs', 'shipments', 'last_shipment', 'products',
                 'source', 'url', 'raw_ids', 'confidence')

    def __init__(self, bol='', hs=None, shipments=0, last_shipment='', products=None,
                 source='', url='', raw_ids=None, confidence=1.0):
        self.bol = str(bol or '')
        self.hs = [str(x) for x in (hs or []) if str(x).strip()][:8] if isinstance(hs, (list, tuple)) \
            else ([str(hs)] if str(hs or '').strip() else [])
        self.shipments = int(shipments or 0)
        self.last_shipment = last_shipment
        self.products = [str(x) for x in (products or [])][:8] if isinstance(products, (list, tuple)) \
            else ([str(products)] if str(products or '').strip() else [])
        self.source = str(source or '')
        self.url = str(url or '')
        self.raw_ids = list(raw_ids or [])[:8]
        self.confidence = float(confidence or 0)

    @property
    def is_hard(self):
        """硬贸易证据：有提单号 / 出货次数 / 海关标记来源 / 原始记录号 任一即可。"""
        return bool(self.bol or self.shipments or self.raw_ids or
                    any(k in self.source for k in ('customs', 'importyeti', 'importkey', 'hs_finder')))

    def to_dict(self):
        return {'bol': self.bol, 'hs': self.hs, 'shipments': self.shipments,
                'last_shipment': self.last_shipment, 'products': self.products,
                'source': self.source, 'url': self.url, 'raw_ids': self.raw_ids,
                'confidence': self.confidence, 'customs': True, 'trade_evidence': True}


# ---------- v34.0 证据四级：全项目唯一判定实现（canonical implementation） ----------
# 任何节点/工具需要判定证据等级时必须调用本函数，禁止并行第二套分级逻辑。
EVIDENCE_LEVELS = ('STRONG', 'MEDIUM', 'WEAK', 'UNVERIFIED')

# 可信贸易来源词表：海关/提单/海关图谱扩张来源（用于 MEDIUM 判定）
TRUSTED_SOURCES = ('customs_raw', 'importyeti_penetration', 'importyeti_web', 'importkey_public',
                   'hs_finder', 'customs_local', 'customs_web', 'network_expand', 'customs_bulk',
                   'importyeti_reverse', 'importyeti')

# 非 STRONG 证据的置信度降权系数（降权不删除：UNVERIFIED 也保留在图谱中）
EVIDENCE_DEMOTE = {'MEDIUM': 0.6, 'WEAK': 0.3, 'UNVERIFIED': 0.1}


def evidence_level(e, source=''):
    """证据四级（唯一判定函数）：
    STRONG=硬贸易证据(票数/提单/海关记录)；MEDIUM=可信来源但无提单数字；
    WEAK=有来源有内容但不可信级；UNVERIFIED=无任何证据内容。"""
    e = e or {}
    hard = bool(e.get('shipments') or e.get('customs') or e.get('trade_evidence') or e.get('bill_of_lading'))
    if hard:
        return 'STRONG'
    if e.get('url') or source in TRUSTED_SOURCES:
        return 'MEDIUM'
    if e:
        return 'WEAK'
    return 'UNVERIFIED'


# 物流/货代/船代是真实贸易节点（图谱证据、验证参照、收割路径），
# 但它们不是客户——不丢弃，统一停放到贸易节点数据池（role='logistics'）。
LOGISTICS_RE = re.compile(r'freight|forwarder|logistics|cargo|shipping|customs broker|packaging', re.I)


# ---------- v35 伪实体拦截：国家/城市/州/港口/地址绝不成为公司实体 ----------
# 精确匹配（归一化后整名命中才拦截），杜绝误伤真实公司（如 El Dorado Furniture 是真实企业）。
_GEO_COUNTRIES = {
    'united states', 'united states of america', 'usa', 'u s a', 'us', 'u s', 'america',
    'china', 'canada', 'mexico', 'germany', 'france', 'italy', 'spain', 'portugal', 'netherlands',
    'belgium', 'united kingdom', 'uk', 'england', 'ireland', 'japan', 'korea', 'south korea',
    'india', 'vietnam', 'thailand', 'malaysia', 'indonesia', 'philippines', 'singapore',
    'taiwan', 'hong kong', 'australia', 'new zealand', 'brazil', 'argentina', 'chile', 'peru',
    'colombia', 'poland', 'czech republic', 'austria', 'switzerland', 'sweden', 'norway',
    'denmark', 'finland', 'greece', 'turkey', 'egypt', 'south africa', 'israel', 'russia',
    'ukraine', 'romania', 'hungary', 'pakistan', 'bangladesh', 'sri lanka', 'united arab emirates',
    'saudi arabia', 'morocco', 'nigeria', 'kenya', 'ecuador', 'guatemala', 'costa rica', 'panama',
    'dominican republic', 'honduras', 'el salvador', 'nicaragua', 'uruguay', 'paraguay', 'bolivia',
}
_GEO_US_STATES = {
    'alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware',
    'florida','georgia','hawaii','idaho','illinois','indiana','iowa','kansas','kentucky',
    'louisiana','maine','maryland','massachusetts','michigan','minnesota','mississippi',
    'missouri','montana','nebraska','nevada','new hampshire','new jersey','new mexico',
    'new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania',
    'rhode island','south carolina','south dakota','tennessee','texas','utah','vermont',
    'virginia','washington','west virginia','wisconsin','wyoming','district of columbia',
}
_GEO_US_CITIES_PORTS = {
    'new york city','los angeles','long beach','oakland','seattle','tacoma','houston','savannah',
    'charleston','norfolk','newark','miami','baltimore','boston','chicago','atlanta','dallas',
    'denver','phoenix','portland','san francisco','san diego','philadelphia','detroit','memphis',
    'minneapolis','cleveland','columbus','indianapolis','kansas city','st louis','saint louis',
    'new orleans','jacksonville','louisville','nashville','charlotte','raleigh','richmond',
    'salt lake city','las vegas','albuquerque','tucson','oklahoma city','omaha','des moines',
    'asheboro','asheville','el dorado','birmingham','mobile','anchorage','honolulu','buffalo',
    'rochester','syracuse','albany','pittsburgh','cincinnati','milwaukee','madison','fresno',
    'sacramento','spokane','boise','billings','fargo','sioux falls','little rock','jackson',
}
_GEO_GENERIC = {
    'port', 'harbor', 'harbour', 'airport', 'terminal', 'city', 'county', 'town', 'village',
    'unknown', 'n a', 'na', 'none', 'null', 'to order', 'to the order', 'same as consignee',
}


def norm_text(s):
    import re as _re
    return _re.sub(r'\s+', ' ', _re.sub(r'[^a-z0-9 ]', ' ', str(s or '').lower())).strip()


def is_non_company_name(name):
    """True ⇒ 该字符串是地理/占位伪实体，绝不能成为公司实体或图谱边的端点。
    只整名精确命中（归一化后），不做子串匹配，避免误伤真实公司。"""
    n = norm_text(name)
    if not n:
        return True
    if n in _GEO_COUNTRIES or n in _GEO_US_STATES or n in _GEO_US_CITIES_PORTS or n in _GEO_GENERIC:
        return True
    # 形如 "Tacoma WA" / "Houston TX" 的 城市+州 组合（州可用全称或两字母缩写）
    _ST_ABBR = {'al','ak','az','ar','ca','co','ct','de','fl','ga','hi','id','il','in','ia','ks',
                'ky','la','me','md','ma','mi','mn','ms','mo','mt','ne','nv','nh','nj','nm','ny',
                'nc','nd','oh','ok','or','pa','ri','sc','sd','tn','tx','ut','vt','va','wa','wv','wi','wy','dc'}
    parts = n.split()
    if len(parts) == 2 and parts[0] in _GEO_US_CITIES_PORTS and (
            parts[1] in _ST_ABBR or parts[1] in {s.replace(' ', '') for s in _GEO_US_STATES}):
        return True
    return False


class TradeEdge:
    """节点间的贸易关系边：buyer_to_supplier / supplier_to_customer / 历史交易。
    v36：携带可追溯性 discovered_via（谁发现的）/ parent_node（由哪个节点展开而来）/
    expansion_path（from→to 单跳路径，多跳链由 parent_node 逐级回溯重建）。"""

    __slots__ = ('from_norm', 'from_name', 'from_role', 'to_norm', 'to_name',
                 'to_role', 'relation', 'evidence', 'source', 'confidence', 'depth',
                 'discovered_via', 'parent_node', 'expansion_path')

    def __init__(self, from_name, from_role, to_name, to_role, relation,
                 evidence=None, source='customs_raw', confidence=1.0, depth=1,
                 discovered_via='', parent_node='', expansion_path=''):
        self.from_name = from_name
        self.from_role = normalize_role(from_role, 'importer')
        self.from_norm = norm_name(from_name)
        self.to_name = to_name
        self.to_role = normalize_role(to_role, 'supplier')
        self.to_norm = norm_name(to_name)
        self.relation = str(relation or '')
        self.evidence = evidence or {}
        self.source = str(source or '')
        self.confidence = float(confidence or 0)
        self.depth = int(depth or 1)
        # 默认：扩张边由 from 端（种子节点）展开而来
        self.discovered_via = str(discovered_via or source or '')
        self.parent_node = str(parent_node or from_name or '')
        self.expansion_path = str(expansion_path or ('%s→%s' % (from_name, to_name) if from_name and to_name else ''))

    def to_dict(self):
        return {'from_name': self.from_name, 'from_type': self.from_role,
                'to_name': self.to_name, 'to_type': self.to_role,
                'relation': self.relation, 'evidence': self.evidence,
                'source': self.source, 'confidence': self.confidence, 'depth': self.depth,
                'discovered_via': self.discovered_via, 'parent_node': self.parent_node,
                'expansion_path': self.expansion_path}


class TradeNode:
    """贸易图谱节点：一家企业 + 它在海关数据中的角色 + 贸易证据 + 关系边。"""

    def __init__(self, name, role='importer', source=''):
        self.name = str(name or '').strip()
        self.norm = norm_name(self.name)
        self.role = normalize_role(role)
        self.source = str(source or '')
        self.evidence = []   # list[TradeEvidence]
        self.edges = []      # list[TradeEdge]

    @property
    def has_trade_evidence(self):
        return any(e.is_hard for e in self.evidence)

    @property
    def shipments(self):
        return max((e.shipments for e in self.evidence), default=0)

    def add_evidence(self, ev):
        if isinstance(ev, dict):
            ev = TradeEvidence(
                bol=ev.get('bol') or ev.get('bill_of_lading') or '',
                hs=ev.get('hs') or ([ev['hs_code']] if ev.get('hs_code') else []),
                shipments=ev.get('shipments') or 0,
                last_shipment=ev.get('last_shipment') or ev.get('last_seen') or '',
                products=ev.get('products') or ([ev['descr']] if ev.get('descr') else []),
                source=ev.get('source') or self.source,
                url=ev.get('url') or '', raw_ids=ev.get('raw_ids') or [],
                confidence=ev.get('confidence', 1.0))
        self.evidence.append(ev)
        return ev

    def add_edge(self, edge):
        self.edges.append(edge)
        return edge

    def to_dict(self):
        return {'name': self.name, 'norm': self.norm, 'role': self.role,
                'source': self.source, 'shipments': self.shipments,
                'evidence': [e.to_dict() for e in self.evidence],
                'edges': [e.to_dict() for e in self.edges]}


class TradeGraph:
    """贸易关系图谱：节点表 + 边表。第一阶段只建图，不评分。"""

    def __init__(self):
        self.nodes = {}   # norm -> TradeNode
        self.edges = []   # list[TradeEdge]

    def add_node(self, node):
        if not node.norm:
            return None
        old = self.nodes.get(node.norm)
        if old:
            for e in node.evidence:
                old.add_evidence(e)
            return old
        self.nodes[node.norm] = node
        return node

    def ensure_node(self, name, role='importer', source=''):
        n = norm_name(name)
        if not n:
            return None
        if n not in self.nodes:
            self.nodes[n] = TradeNode(name, role, source)
        return self.nodes[n]

    def add_edge(self, edge):
        if not edge.from_norm or not edge.to_norm or edge.from_norm == edge.to_norm:
            return None
        self.ensure_node(edge.from_name, edge.from_role, edge.source)
        self.ensure_node(edge.to_name, edge.to_role, edge.source)
        self.edges.append(edge)
        return edge

    def stats(self):
        by_role = {}
        for n in self.nodes.values():
            by_role[n.role] = by_role.get(n.role, 0) + 1
        return {'nodes': len(self.nodes), 'edges': len(self.edges),
                'by_role': by_role,
                'nodes_with_evidence': sum(1 for n in self.nodes.values() if n.has_trade_evidence)}

    def to_dict(self):
        return {'nodes': [n.to_dict() for n in self.nodes.values()],
                'edges': [e.to_dict() for e in self.edges],
                'stats': self.stats()}

    @classmethod
    def from_state(cls, state):
        """从黑板状态恢复/新建图谱（state['trade_graph'] 以 dict 形式存放）。"""
        g = cls()
        raw = (state or {}).get('trade_graph') or {}
        for nd in (raw.get('nodes') or []):
            node = TradeNode(nd.get('name'), nd.get('role'), nd.get('source'))
            for e in (nd.get('evidence') or []):
                node.add_evidence(e)
            g.add_node(node)
        for ed in (raw.get('edges') or []):
            g.add_edge(TradeEdge(ed.get('from_name'), ed.get('from_type'),
                                 ed.get('to_name'), ed.get('to_type'),
                                 ed.get('relation'), ed.get('evidence'),
                                 ed.get('source'), ed.get('confidence', 1.0),
                                 ed.get('depth', 1), ed.get('discovered_via', ''),
                                 ed.get('parent_node', ''), ed.get('expansion_path', '')))
        return g
