# -*- coding: utf-8 -*-
"""v34.0 编排引擎（MISSION_DIRECTOR 唯一编排层）：Trade Graph Pipeline 总统筹 + 统一节点契约 + handoff 契约。

架构铁律（最终收敛版）：
1) 本文件是唯一拥有流程控制权的编排层：节点顺序、重试、恢复、终止全部在这里裁决。
2) 节点只有执行权：节点返回的 abort/next_node/nodes/node_status/handoffs 等编排字段
   一律在 _run_once 剥离——节点"返回"控制字段或编排状态视同无效。
3) 节点失败最多自动重试 NODE_RETRIES 次；仍失败生成诊断包给网页AI顾问，再由总统筹决定
   retry/replan/skip/abort。总统筹的决策字段只有 action/reason/plan/questions（无 next_node）。
4) 节点状态机全系统统一（settings.NODE_STATUS）：PENDING/RUNNING/SUCCESS/FAILED/BLOCKED/SKIPPED/CANCELLED。
5) 每次节点状态实时落盘；handoff 契约含 payload_checksum（对真实业务 payload 计算，
   summary 仅供日志/UI，绝不可替代 payload）。
"""
import time, traceback, json, hashlib, uuid
from typing import TypedDict
from core.config import settings
from core.runtime import nodes as N
from core.runtime import experts

# v34.0 统一交接契约版本：node_id/from_node/to_node/task_id/run_id/contract_version/
# payload_keys/payload_checksum(对真实payload)/node_report/status/metrics/errors/warnings/created_at
HANDOFF_CONTRACT_VERSION = 'v34.0'

# 节点输出中属于"编排层私有"的键：节点即使返回也必须剥离（防御性收口，
# 根治"节点返回整份state导致handoffs/node_status被旧快照覆盖"的架构事故）。
ORCHESTRATOR_KEYS = ('nodes', 'node_status', 'handoffs', 'current_handoff', 'current_node',
                     'mission_decisions', 'plans', 'diagnostics', 'retry_history',
                     'abort', 'next_node', 'traceback', 'run_id', 'engine', 'success',
                     'duration_sec', 'current_dev_node')

# handoff payload 的业务数据键（真实交接内容；checksum 对它们的完整内容计算）
PAYLOAD_KEYS = ('icp', 'strategy', 'product_profile', 'product_domain', 'companies',
                'new_companies', 'qualified_companies', 'classified_entities', 'company_entities',
                'trade_nodes', 'trade_edges', 'query_stats', 'suppliers', 'supplier_new',
                'trade_graph', 'graph_expansion', 'evidence_verify', 'classification',
                'database_commit', 'collect_gate', 'gate', 'funnel')


class S(TypedDict, total=False):
    """v34.0 统一 state 契约：只保留九节点真正读写的字段。"""
    task_id: str; run_id: str; request: str; market: str; industry: str; quantity: int
    icp: dict; strategy: dict; query_override: list; product_profile: dict; product_domain: dict
    companies: list; new_companies: list; qualified_companies: list; classified_entities: list
    company_entities: list; trade_nodes: list; trade_entities: list; trade_edges: list
    query_stats: list; suppliers: list; supplier_new: list
    gate: dict; collect_gate: dict; evidence_verify: dict; database_commit: dict; commit_verify: dict
    classification: dict; edges_built: int; entity_resolved: int; graph_expansion: dict; funnel: list
    nodes: list; node_reports: dict
    source: str; source_errors: list
    abort: str; skip_llm: bool; error: str; warning: str; success: bool; duration_sec: float
    engine: str; traceback: str
    current_node: str; node_status: dict; handoffs: dict; retry_history: list; plans: list
    diagnostics: list; mission_decisions: list; current_handoff: dict
    trade_graph: dict  # 贸易关系图谱（海关节点 + 关系边），第一阶段产物
    count_semantics: dict  # v34.0 统计字段语义（见 nodes.COUNT_SEMANTICS，全链路同一口径）

# PSV 主流程：Trade Graph Pipeline —— 从"寻找企业"升级为"构建贸易网络"。
# 九节点，每个节点职责单一，不为加节点而加节点：
# 产品定义先行 → 贸易定位 → 海关节点产生企业 → 关系建边 → 证据分级
# → 实体解析(合并不删除) → 双向网络扩张 → 资源分类(生命周期) → 贸易资产沉淀
ORDER = ['PRODUCT_DEFINITION', 'TRADE_STRATEGY', 'CUSTOMS_NODE_COLLECTION', 'TRADE_EDGE_BUILD',
         'EVIDENCE_VERIFY', 'ENTITY_RESOLUTION', 'GRAPH_EXPANSION', 'RESOURCE_CLASSIFICATION',
         'DATABASE_COMMIT']
# 编排器（本文件）唯一拥有流程控制权；节点只拥有执行权。
# FN 只注册 ORDER 内的执行节点，与 ORDER 完全一致（同一套 canonical node_id）。
FN = {'PRODUCT_DEFINITION': N.n_product_definition, 'TRADE_STRATEGY': N.n_trade_strategy,
      'CUSTOMS_NODE_COLLECTION': N.n_customs_node_collection, 'TRADE_EDGE_BUILD': N.n_trade_edge_build,
      'EVIDENCE_VERIFY': N.n_evidence_verify, 'ENTITY_RESOLUTION': N.n_entity_resolution,
      'GRAPH_EXPANSION': N.n_graph_expansion, 'RESOURCE_CLASSIFICATION': N.n_resource_classification,
      'DATABASE_COMMIT': N.n_database_commit}
# 节点注册唯一性断言：一套节点名贯穿 Planner/Orchestrator/Runner/Registry/UI，
# 禁止新旧两套逻辑并行。
assert len(ORDER) == len(set(ORDER)), 'ORDER 内节点名重复'
assert list(FN.keys()) == ORDER, '节点注册表必须与 ORDER 完全一致（同一套节点名）'

# 上游产物的最低结构要求（交接输入契约）——唯一定义在 contracts.Node Contract Registry。
from core.runtime import contracts as node_contracts
CONTRACTS = {n: tuple(c['input']) for n, c in node_contracts.CONTRACTS.items()}
# 真正需要强证据的节点：不允许"搜索看起来像"替代证据。
STRICT_EVIDENCE = {'EVIDENCE_VERIFY', 'RESOURCE_CLASSIFICATION', 'DATABASE_COMMIT'}


def _entry(name, status='SUCCESS', note='', dur=0.0, attempt=1, **kw):
    e = {'node': name, 'status': status, 'success': status in ('SUCCESS', 'SKIPPED'), 'attempt': attempt, 'ts': time.time()}
    if note: e['note'] = note
    if dur: e['duration'] = round(dur, 2)
    e.update(kw); return e


def _persist(persist, state):
    # 清理不可序列化对象，只保留可观察黑板
    try: persist(state)
    except Exception: pass


def _handoff_check(state, name, out):
    missing = [k for k in CONTRACTS.get(name, ()) if out.get(k, state.get(k)) is None]
    # 结果级最低质量检查
    issues = []
    if name == 'PRODUCT_DEFINITION':
        if not (out.get('icp', state.get('icp'))):
            issues.append('产品定义未产出结构化ICP契约')
        pd = out.get('product_domain', state.get('product_domain')) or {}
        if not pd.get('matrix'):
            issues.append('产品定义未产出关键词矩阵')
        if not pd.get('query_plan'):
            issues.append('产品定义未产出动态查询计划（16维语义矩阵）')
    if name == 'TRADE_STRATEGY' and not (out.get('strategy', state.get('strategy'))):
        issues.append('贸易定位策略未产出')
    if name == 'CUSTOMS_NODE_COLLECTION' and not (out.get('companies', state.get('companies')) or out.get('trade_nodes', state.get('trade_nodes')) or out.get('trade_entities', state.get('trade_entities'))):
        issues.append('海关节点采集未产出贸易实体')
    if name == 'TRADE_EDGE_BUILD' and out.get('edges_built') is None and state.get('edges_built') is None:
        issues.append('贸易关系构建未产出建边计数')
    if name == 'EVIDENCE_VERIFY' and not isinstance(out.get('evidence_verify', state.get('evidence_verify')), dict):
        issues.append('证据验证未产出报告')
    if name == 'GRAPH_EXPANSION' and state.get('companies') is None and out.get('companies') is None:
        issues.append('双向扩张后贸易实体集合缺失')
    if name == 'RESOURCE_CLASSIFICATION':
        g = out.get('gate', state.get('gate')) or {}
        if g.get('ok') and not (g.get('qualified_companies') or out.get('new_companies') or state.get('new_companies')):
            issues.append('资源分类标记通过但没有放行候选')
    if name in STRICT_EVIDENCE:
        candidates = out.get('new_companies', state.get('new_companies')) or []
        if candidates:
            no_evidence = 0
            for c in candidates:
                e = c.get('evidence') or {}
                src = str(c.get('source') or '').lower()
                hard = bool(e.get('shipments') or e.get('bill_of_lading') or e.get('customs') or e.get('trade_evidence'))
                if not hard and 'importyeti' not in src and 'customs' not in src: no_evidence += 1
            if no_evidence and name == 'RESOURCE_CLASSIFICATION':
                issues.append(f'{no_evidence}个候选缺少硬贸易证据')
    return missing + issues


def _set_status(state, name, status, **extra):
    """统一节点状态机：只写 settings.NODE_STATUS 内的 canonical 状态。"""
    status = str(status or '').upper()
    if status not in settings.NODE_STATUS:
        status = 'FAILED' if 'FAIL' in status else 'RUNNING'
    ns = dict(state.get('node_status') or {})
    ns[name] = {'status': status, 'updated_at': time.time(), 'attempt': extra.pop('attempt', ns.get(name, {}).get('attempt', 0))}
    ns[name].update(extra); state['node_status'] = ns


def _payload_snapshot(state, out):
    """handoff 真实业务 payload：合并"节点新产出 + 黑板已有"，取 PAYLOAD_KEYS 中存在的完整内容。
    summary 仅供 UI/日志；checksum 必须对这里的完整 payload 计算。"""
    payload = {}
    for k in PAYLOAD_KEYS:
        v = out.get(k, state.get(k))
        if v is not None:
            payload[k] = v
    return payload


def _record_handoff(state, name, prev_name, out, accepted, issues, warnings=None):
    """v34.0 统一 handoff 契约：
    node_id/from_node/to_node/task_id/run_id/contract_version/payload_keys/payload_checksum/
    node_report/status/metrics/errors/warnings/created_at。
    payload_checksum 对真实业务 payload（PAYLOAD_KEYS 完整内容）计算——
    下游可校验上游产物在交接中未被篡改/截断；summary 只是 metrics 的展示别名。"""
    payload = _payload_snapshot(state, out)
    checksum = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]
    metrics = {'companies': len(payload.get('companies') or []),
               'new_companies': len(payload.get('new_companies') or []),
               'suppliers': len(payload.get('suppliers') or []),
               'trade_nodes': len(payload.get('trade_nodes') or []),
               'trade_edges': len(payload.get('trade_edges') or []),
               'classified': len(payload.get('classified_entities') or [])}
    report = (state.get('node_reports') or {}).get(name) or (out.get('node_reports') or {}).get(name) or {}
    item = {'node_id': name, 'from_node': prev_name, 'to_node': name,
            'task_id': state.get('task_id') or '', 'run_id': state.get('run_id') or '',
            'contract_version': HANDOFF_CONTRACT_VERSION,
            'payload_keys': sorted(payload.keys()), 'payload_checksum': checksum,
            'node_report': {'verdict': report.get('verdict'), 'notes': str(report.get('notes') or '')[:200]},
            'status': 'SUCCESS' if accepted else 'FAILED',
            'metrics': metrics, 'errors': issues[:8] if not accepted else [],
            'warnings': list(warnings or []) + (['handoff: ' + i for i in issues[:8]] if accepted else []),
            'created_at': time.time(),
            # 兼容字段：from/to/accepted/summary 供既有 UI/测试读取（同一数据，不是第二套）
            'from': prev_name, 'to': name, 'accepted': bool(accepted), 'issues': issues[:8],
            'ts': time.time(), 'summary': dict(metrics, keys=sorted(payload.keys()))}
    hs = dict(state.get('handoffs') or {})
    hs[name] = item; state['handoffs'] = hs; state['current_handoff'] = item
    return item


def _run_once(state, name, attempt, persist):
    fn = FN[name]; state['current_node'] = name; _set_status(state, name, 'RUNNING', attempt=attempt)
    state['nodes'] = state.get('nodes', []) + [_entry(name, 'RUNNING', '开始执行', attempt=attempt)]
    _persist(persist, state)
    missing = [k for k in CONTRACTS.get(name, ()) if state.get(k) is None]
    if missing:
        err = f'{name} 交接输入缺失: {missing}'
        _set_status(state, name, 'FAILED', attempt=attempt, error=err)
        state['error'] = err; state['nodes'].append(_entry(name, 'FAILED', err, attempt=attempt))
        _persist(persist, state); return False, {}, err
    t0 = time.time(); out = {}
    try:
        out = fn(state) or {}
        # 架构铁律（最终收口）：节点只有执行权。流程控制字段与编排层私有状态
        # 一律在此剥离——节点"返回"它们视同无效（含节点误返回整份 state 的情形）。
        for k in ORCHESTRATOR_KEYS:
            out.pop(k, None)
        ok = bool(out.pop('_success', True)); note = str(out.pop('_note', ''))
        issues = _handoff_check(state, name, out)
        # v35 契约硬校验：OUTPUT 必需字段缺失/空/类型错误 ⇒ 节点失败（不放宽契约换 success）
        cok, cissues, cwarn = node_contracts.validate(name, out, state)
        issues.extend('contract: ' + x for x in cissues)
        if not cok:
            ok = False
        if not ok: issues.append(note or '专家节点返回失败')
        if issues and settings.HANDOFF_VALIDATION_ENABLED:
            ok = False
        # 先合入业务产出，再生成交接验收（handoff 看到的是节点真实产出后的黑板）
        if out: state.update(out)
        prev = (ORDER[ORDER.index(name) - 1] if name in ORDER and ORDER.index(name) > 0 else 'MISSION_DIRECTOR')
        _record_handoff(state, name, prev, out, ok, issues, warnings=['contract-input: ' + x for x in cwarn])
        status = 'SUCCESS' if ok else 'FAILED'
        _set_status(state, name, status, attempt=attempt, note=note, error='; '.join(issues[:3]) if issues else '')
        state['nodes'].append(_entry(name, status, note, time.time() - t0, attempt=attempt, issues=issues[:8]))
        _persist(persist, state)
        return ok, out, '' if ok else ('; '.join(issues[:4]) or note or '节点返回失败')
    except Exception as e:
        err = f'{name} 节点异常: {str(e)[:500]}'
        state['traceback'] = traceback.format_exc()[-1600:]
        state['error'] = err
        _set_status(state, name, 'FAILED', attempt=attempt, error=err)
        state['nodes'].append(_entry(name, 'FAILED', err, time.time() - t0, attempt=attempt, exception=True))
        _persist(persist, state); return False, out, err


def _web_diagnose(state, name, error, attempts, persist):
    package = experts.build_diagnostic_package(state, name, error, attempts)
    diag = {'node': name, 'attempts': attempts, 'package': package, 'ts': time.time(), 'by': 'local'}
    # 本地诊断先做一次：不是让本地模型猜错误，而是总结事实。
    try:
        d = experts.diagnose(name, json.dumps(package, ensure_ascii=False)[:9000], json.dumps(state.get('node_reports', {}).get(name, {}), ensure_ascii=False)[:2500])
        diag['local'] = d
    except Exception as e: diag['local'] = {'diagnosis': '本地诊断失败', 'advice': str(e)[:200]}
    # 三次失败后才咨询网页AI，并把完整事实包交给它。
    if settings.WEBAI_ENABLED and attempts >= settings.WEB_AI_AFTER_RETRIES:
        try:
            from core.tools import web_ai
            prompt = '''你是外贸客户采集系统的故障诊断顾问。下面是结构化事实包。注意：observed_error只是“观察到的错误”，绝不能直接当作根因。请根据成功路径、尝试历史、节点职责、数据状态和约束，给出根因候选排序与下一步方案。不要要求付费API，不要绕过登录/验证码/访问控制。输出JSON：{"diagnosis":"最可能根因","alternatives":["其他可能根因"],"actions":["按优先级最多4个动作"],"continue_safe":true,"skip_node":false,"confidence":0.0}'''
            ans = web_ai.solve(prompt, context=json.dumps(package, ensure_ascii=False), timeout=settings.WEBAI_TIMEOUT)
            if ans:
                from core.utils import jsonutil
                j = jsonutil.j(ans)
                if j:
                    diag['web_ai'] = {'diagnosis': str(j.get('diagnosis') or '')[:500],
                                      'alternatives': [str(x)[:300] for x in (j.get('alternatives') or [])[:5]],
                                      'actions': [str(x)[:300] for x in (j.get('actions') or [])[:5]],
                                      'continue_safe': bool(j.get('continue_safe', True)),
                                      'skip_node': bool(j.get('skip_node', False)),
                                      'confidence': float(j.get('confidence') or 0), 'ts': time.time()}
                    diag['by'] = 'web_ai'
        except Exception as e:
            diag['web_ai_error'] = str(e)[:300]
    state['diagnostics'] = list(state.get('diagnostics') or []) + [diag]
    _persist(persist, state)
    return diag


def _director(state, event, failure, persist):
    """MISSION_DIRECTOR（总统筹）：唯一编排决策点。决策字段只有 action/reason/plan/questions，
    没有 next_node——流程走向由本编排层根据 action 裁决，节点与顾问都不选路。"""
    decision = experts.mission_plan(state, event=event, failure=failure)
    decision.pop('next_node', None)  # 防御：任何 next_node 建议都不被采纳
    state['mission_decisions'] = list(state.get('mission_decisions') or []) + [dict(decision, ts=time.time(), event=event)]
    state['plans'] = list(state.get('plans') or []) + [decision]
    _persist(persist, state)
    return decision


def _recovery(state, name, error, attempts, persist):
    # 先做总统筹规划；三次失败后再增加网页AI诊断。
    failure = {'node': name, 'error': error, 'attempts': attempts, 'last_report': (state.get('node_reports') or {}).get(name, {}),
               'diagnostic_count': len(state.get('diagnostics') or [])}
    decision = _director(state, 'node_failed', failure, persist)
    if attempts >= settings.NODE_RETRIES:
        diag = _web_diagnose(state, name, error, attempts, persist)
        decision = _director(state, 'diagnosis_ready', {'node': name, 'diagnosis': diag}, persist)
    action = str(decision.get('action') or 'replan')
    if action not in {'retry', 'replan', 'skip', 'abort', 'continue'}: action = 'replan'
    # 保护证据质量：严格节点无硬证据时不能简单“skip”成通过。
    if name in STRICT_EVIDENCE and action == 'skip':
        state['warning'] = '严格证据节点被总统筹建议跳过：保持阻断，不把不合格数据当合格客户。'
        _set_status(state, name, 'BLOCKED', reason='严格证据节点禁止跳过')
        action = 'abort'
    return action, decision


def run_graph(state, persist):
    state.setdefault('engine', 'trade-graph-pipeline-v34')
    state.setdefault('run_id', (state.get('task_id') or 'task') + '-' + uuid.uuid4().hex[:6])
    state.setdefault('node_status', {}); state.setdefault('handoffs', {})
    state.setdefault('retry_history', []); state.setdefault('plans', []); state.setdefault('diagnostics', [])
    state.setdefault('failure_history', [])  # v36：失败事实档案（节点/错误/尝试/恢复动作/保留数据量）
    state.setdefault('mission_decisions', []); state.setdefault('evidence_summary', {}); state.setdefault('nodes', [])
    state.setdefault('count_semantics', dict(settings.COUNT_SEMANTICS))  # 数字口径语义固化（83/85/87 非错误）
    # 初始总统筹计划：决定整体任务模式，但不越权执行节点。
    _director(state, 'task_start', {}, persist)
    i = 0; steps = 0; attempts = {}; max_steps = settings.GRAPH_MAX_STEPS
    while i < len(ORDER) and steps < max_steps:
        steps += 1; name = ORDER[i]
        # 采集/分类节点失败不再用无限 reflect loop；统一进入恢复机制。
        ok, out, error = _run_once(state, name, attempts.get(name, 0) + 1, persist)
        attempts[name] = attempts.get(name, 0) + 1
        if ok:
            attempts[name] = 0
            i += 1
            continue
        # 节点失败：结构化诊断→总统筹换方案（失败事实+已保留数据量入档，禁止从零重采）
        state['retry_history'] = list(state.get('retry_history') or []) + [{'node': name, 'attempt': attempts[name], 'error': error, 'ts': time.time()}]
        state['failure_history'] = list(state.get('failure_history') or []) + [{
            'node': name, 'attempt': attempts[name], 'error': str(error)[:300], 'ts': time.time(),
            'preserved': {'trade_nodes': len(state.get('trade_nodes') or []),
                          'trade_edges': len(state.get('trade_edges') or []),
                          'companies': len(state.get('companies') or []),
                          'queries': len((state.get('product_domain') or {}).get('query_plan') or [])}}]
        action, decision = _recovery(state, name, error, attempts[name], persist)
        state['failure_history'][-1]['recovery_action'] = action
        if action in ('retry', 'continue') and attempts[name] < settings.NODE_RETRIES:
            state['current_node'] = name; _set_status(state, name, 'RUNNING', attempt=attempts[name], reason='retry: ' + str(decision.get('reason', ''))[:120])
            _persist(persist, state); continue
        if action == 'replan' and attempts[name] < settings.NODE_RETRIES:
            # 总统筹可以要求更换查询策略；最常见的恢复路径回到TRADE_STRATEGY，而不是原地循环。
            if name in {'CUSTOMS_NODE_COLLECTION', 'EVIDENCE_VERIFY', 'RESOURCE_CLASSIFICATION', 'GRAPH_EXPANSION'}:
                state['query_override'] = (decision.get('plan') or [])[:6] or state.get('query_override')
                target = 'TRADE_STRATEGY' if name in {'CUSTOMS_NODE_COLLECTION', 'RESOURCE_CLASSIFICATION'} else 'GRAPH_EXPANSION'
                attempts[name] = 0; i = ORDER.index(target); continue
            attempts[name] = 0; i = max(0, i - 1); continue
        if action == 'skip' and name not in STRICT_EVIDENCE:
            _set_status(state, name, 'SKIPPED', attempt=attempts[name], reason=decision.get('reason', ''))
            i += 1; continue
        # 到这里表示安全终止，不把失败伪装成成功。
        # v36：终止前保存完整 checkpoint（已发现数据+未完成队列+query frontier），上下文不丢失。
        state['abort'] = 'failed'; state['error'] = error or f'{name} 无法安全完成'
        try:
            from core.memory.db import DB
            frontier_left = len(DB().get_frontier(limit=100000))
        except Exception:
            frontier_left = -1
        state['checkpoints'] = list(state.get('checkpoints') or []) + [{
            'kind': 'abort_checkpoint', 'node': name, 'ts': time.time(),
            'preserved': {'trade_nodes': len(state.get('trade_nodes') or []),
                          'trade_edges': len(state.get('trade_edges') or []),
                          'companies': len(state.get('companies') or []),
                          'classified': len(state.get('classified_entities') or []),
                          'expansion_frontier_pending': frontier_left,
                          'query_override': list(state.get('query_override') or [])[:20]},
            'note': '已发现数据全部保留在黑与库中；frontier 与 query 队列可供下一轮续跑，不从零重采'}]
        break
    if steps >= max_steps and not state.get('abort'):
        state['abort'] = 'error'; state['error'] = '达到编排最大步数，防止循环失控'
    state['current_node'] = 'END'; _persist(persist, state); return state
