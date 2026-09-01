# -*- coding: utf-8 -*-
"""v35 Node Contract Registry：每个正式节点的唯一契约定义 + 真实校验。

契约八要素：INPUT / RESPONSIBILITY / OUTPUT / SUCCESS / FAILURE / BLOCKING /
ALLOWED SIDE EFFECTS / DATABASE WRITE AUTHORITY。

校验原则：
- OUTPUT 校验是硬校验：必需字段缺失/空/类型错误 ⇒ 节点判定失败（accepted=false），
  不允许"空字段冒充成功"，不允许为了 accepted=true 降低标准。
- INPUT 校验是软校验：上游契约缺失记录为 warnings（单独调试执行时上游为空属正常）。
- 校验只认真实业务数据（列表非空/关键键存在且非空），不认统计数字本身。
"""
from core.runtime import experts

# ---------- 契约要素工具 ----------

def _nonempty_list(x):
    return isinstance(x, list) and len(x) > 0


def _nonempty_dict(x):
    return isinstance(x, dict) and len(x) > 0


# ---------- Node Contract Registry ----------

CONTRACTS = {
    'PRODUCT_DEFINITION': {
        'input': ['market', 'industry'],
        'responsibility': '16 维产品语义矩阵 + 产品域键；不做采集、不做过滤决策',
        'output': {'icp': _nonempty_dict, 'product_profile': _nonempty_dict, 'product_domain': _nonempty_dict},
        'success': 'icp/product_profile/product_domain 三件套齐备且非空',
        'failure': '任一产物缺失或为空',
        'blocking': '无（产物为纯内存对象）',
        'side_effects': 'none',
        'db_write': 'none',
        'data_semantics': 'product_domain.key=产品域唯一键（蜡烛/珐琅锅/毛毡严格隔离）；query_plan=16维矩阵产出的动态查询计划（含 qtype/role/pri）',
    },
    'TRADE_STRATEGY': {
        'input': ['icp', 'product_domain'],
        'responsibility': '12 要素贸易定位策略（含 expansion_policy/evidence_policy/动态查询计划）',
        'output': {'strategy': _nonempty_dict},
        'success': 'strategy 含 12 要素且 hs_strategy.policy=strong_signal_not_hard_filter',
        'failure': 'strategy 缺失或要素不全',
        'blocking': '无',
        'side_effects': 'none',
        'db_write': 'none',
        'data_semantics': 'strategy.expansion_policy.max_depth=纯安全上限（非质量终止条件）；precision_recall_split=精度/召回查询配比计量',
    },
    'CUSTOMS_NODE_COLLECTION': {
        'input': ['strategy', 'icp'],
        'responsibility': '海关源宽采集 + 贸易节点候选池登记 + 逐查询计量；不评分、不过度过滤',
        'output': {'companies': _nonempty_list, 'trade_nodes': _nonempty_list},
        'success': '至少产生 1 个身份有效候选；trade_nodes 候选池非空',
        'failure': '零候选（采集链失效）',
        'blocking': '零候选时编排层进入恢复机制，不盲目重试',
        'side_effects': 'trade_nodes 候选池登记、evidence_events 候选审计、query_stats 计量',
        'db_write': 'candidate-pool-only（禁止写 relationships/leads）',
        'data_semantics': 'companies=候选实体（含 UNRESOLVED）；trade_nodes=候选池登记（RESOLVED/UNRESOLVED_TRADE_NODE 都保留）；query_stats=逐查询真实命中计量',
    },
    'TRADE_EDGE_BUILD': {
        'input': ['trade_graph'],
        'responsibility': '图谱边 → 内存标准边（evidence_level 初标 + 非 STRONG 降权）+ 端点候选池登记',
        'output': {'trade_edges': lambda v: isinstance(v, list), 'edges_built': lambda v: isinstance(v, int)},
        'success': 'trade_edges 为真实内存标准边列表（每条含 evidence_level/标准字段）；空列表仅在图谱无边时合法',
        'failure': '字段缺失或类型错误（有图谱边但标准边为空属数据事实，由 EVIDENCE_VERIFY 核验证据面）',
        'blocking': '无',
        'side_effects': 'trade_nodes 端点候选池登记',
        'db_write': 'candidate-pool-only（relationships 写库唯一出口是 DATABASE_COMMIT）',
        'data_semantics': 'trade_edges=内存标准边（buyer/supplier/product/HS/票数/首末见/evidence_level/confidence/discovered_via/parent_node/expansion_path）；空列表=图谱无边（合法）',
    },
    'EVIDENCE_VERIFY': {
        'input': ['trade_edges'],
        'responsibility': '证据四级唯一核验（STRONG/MEDIUM/WEAK/UNVERIFIED）：给关系分级，不决定关系是否存在；降权不删除；存量 DB 对账',
        'output': {'evidence_verify': _nonempty_dict},
        'success': 'evidence_verify 含四级计数；全量边完成分级即成功（弱证据=降权保留，绝不判存亡/阻断主链）',
        'failure': 'evidence_verify 产物缺失或为空（未执行分级）',
        'blocking': '无（证据等级只决定 confidence/development_status/resource_priority）',
        'side_effects': '存量 relationships 等级补判（同一判定函数的对账，不是第二套逻辑）',
        'db_write': 'reconcile-only（UPDATE 存量边的等级/置信度，不 INSERT 新边）',
        'data_semantics': 'evidence_verify.{STRONG|MEDIUM|WEAK|UNVERIFIED}=本任务边+存量对账边的分级计数；samples=弱证据抽样（展示用，不影响判定）',
    },
    'ENTITY_RESOLUTION': {
        'input': ['companies'],
        'responsibility': '同名实体合并 + 角色判定（CUSTOMER/SUPPLIER/CUSTOMER_AND_SUPPLIER/UNKNOWN）；伪实体拦截',
        'output': {'company_entities': _nonempty_list, 'entity_resolution': _nonempty_dict},
        'success': '每个输入实体都有唯一 entity_id 与角色；伪实体（国家/城市/地址）不得成为公司实体',
        'failure': '有输入实体但解析结果为空',
        'blocking': '无（UNKNOWN 保留不删）',
        'side_effects': 'none',
        'db_write': 'none',
        'data_semantics': 'company_entities=唯一实体（entity_id=归一名）；entity_resolution.{merged,dual,unknown,non_entity_filtered}=数量变化解释',
    },
    'GRAPH_EXPANSION': {
        'input': ['companies', 'strategy'],
        'responsibility': '递归双向扩张（种子→挖矿→反向收割）+ 边际收益动态停止（max_depth 仅安全上限）；扩张边并入内存 trade_edges',
        'output': {'graph_expansion': _nonempty_dict, 'companies': _nonempty_list},
        'success': 'depths 非空且实体集合不丢（carry-merge）；stopped_by 为合法停止原因；每层含边际收益计量',
        'failure': '扩张结果丢失输入实体（召回率破坏）',
        'blocking': '无（零新增/frontier耗尽=正常终态，不是失败）',
        'side_effects': 'suppliers 池收割标记、supplier_profiles 画像、trade_nodes 候选池',
        'db_write': 'candidate-pool-only（禁止写 relationships）',
        'data_semantics': 'depths[]=每层 {new_entities,new_buyers,new_suppliers,new_edges,duplicate_rate,frontier_size,consecutive_zero_gain}；stopped_by∈{frontier_drained,no_new_entities,declining_new_rate,max_depth(安全上限)}',
    },
    'RESOURCE_CLASSIFICATION': {
        'input': ['companies'],
        'responsibility': '三维分类（角色 × 贸易状态 × 开发状态）+ 理由字段；证据门槛在此执行',
        'output': {'classified_entities': _nonempty_list, 'classification': _nonempty_dict},
        'success': '分类数 ≥ 输入实体数 - 纯贸易节点数；每条含 classification_reason',
        'failure': '有输入但零分类输出',
        'blocking': '无（DISCOVERED/UNKNOWN 不淘汰）',
        'side_effects': 'none',
        'db_write': 'none',
        'data_semantics': 'classified_entities 每条含 entity_role×trade_status×development_status 三维+classification_reason；分类不删除真实实体',
    },
    'DATABASE_COMMIT': {
        'input': ['classified_entities'],
        'responsibility': '唯一写库出口：Entity(leads) + Edge(relationships) + Evidence(evidence_events) 三类资产；数量恒等；回读自证',
        'output': {'database_commit': _nonempty_dict, 'commit_verify': _nonempty_dict},
        'success': '数量恒等式成立 + 同库回读 probe_ok',
        'failure': '写入失败非零或回读不可见',
        'blocking': '数量恒等式破坏 / 回读失败',
        'side_effects': 'leads/relationships/evidence_events/trade_nodes 正式写入',
        'db_write': 'SOLE-WRITER（relationships 与 leads 的唯一正式写库出口）',
        'data_semantics': 'database_commit=三类资产写入计数（Entity/Edge/Evidence）；commit_verify=同库回读自证；数量恒等式见 funnel 各 stage 的 in/out/drop_reasons',
    },
}

STRATEGY_12 = ('product_domain', 'buyer_types', 'supplier_types', 'target_roles', 'target_hs',
               'hs_strategy', 'target_countries', 'query_plan', 'precision_recall_split',
               'expansion_policy', 'evidence_policy', 'collection_budget')

GEO_FORBIDDEN_NOTE = 'geo/non-company name must never become a company entity'


def validate(node, out, state):
    """硬校验 OUTPUT 契约 + 软校验 INPUT 契约。
    返回 (ok, issues, warnings)。ok=False ⇒ 节点失败（不允许空字段冒充成功）。"""
    c = CONTRACTS.get(node)
    if not c:
        return True, [], [f'no contract registered for {node}']
    out = out or {}
    state = state or {}
    issues = []
    warnings = []
    # INPUT（软）：上游契约缺失只警告——调试单独执行时上游为空属正常
    for k in c['input']:
        v = state.get(k)
        if v is None or v == [] or v == {}:
            warnings.append(f'input[{k}] empty')
    # OUTPUT（硬）
    for k, pred in c['output'].items():
        v = out.get(k)
        try:
            good = pred(v)
        except Exception:
            good = False
        if not good:
            issues.append(f'output[{k}] missing/empty/wrong-type')
    # 节点特有成功准则
    if node == 'TRADE_STRATEGY' and not issues:
        s = out.get('strategy') or {}
        missing = [k for k in STRATEGY_12 if k not in s]
        if missing:
            issues.append('strategy missing elements: %s' % ','.join(missing))
    if node == 'DATABASE_COMMIT' and not issues:
        v = (out.get('commit_verify') or {})
        if v.get('probe_ok') is False:
            issues.append('commit readback probe failed')
    if node == 'GRAPH_EXPANSION' and not issues:
        gx = out.get('graph_expansion') or {}
        if gx.get('stopped_by') not in ('no_new_entities', 'declining_new_rate', 'max_depth',
                                        'frontier_drained', 'consecutive_low_gain'):
            issues.append('illegal stopped_by: %s' % gx.get('stopped_by'))
    return (not issues), issues, warnings


def registry_snapshot():
    """供 UI/报告读取的契约注册表快照（唯一事实源）。"""
    return {n: {'input': c['input'], 'output': list(c['output']),
                'responsibility': c['responsibility'], 'success': c['success'],
                'failure': c['failure'], 'blocking': c['blocking'],
                'side_effects': c['side_effects'], 'db_write': c['db_write'],
                'data_semantics': c.get('data_semantics', '')}
            for n, c in CONTRACTS.items()}
