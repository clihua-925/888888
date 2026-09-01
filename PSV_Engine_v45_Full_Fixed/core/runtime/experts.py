# -*- coding: utf-8 -*-
"""v15 ExpertGraph 专家层：每个节点一位有验收标准的专家。
三段式：执行(确定性代码) → 专家复核(LLM 人设+验收清单) → 判定(pass/fail/degraded)。
复核结论写入 state['node_reports'] 共享认知通道：下游节点可读上游判断，UI 可展开验收明细。
LLM 离线时自动降级为规则验收（verdict=degraded），流程不中断。"""
import time, json
from core.config import settings
from core.model.reasoning import ReasoningEngine
# ---------- 专家注册表：人设 + 使命 + 验收标准说明 ----------
# v34.0 收敛：注册表键 = canonical node_id（与 graph.ORDER / development.DEV_ORDER 同名），
# 不再保留已废弃流程（USITC/RANK/CONTACT/B_PROFILE...）的专家人设——死注册项已清除。
EXPERTS={
 'PRODUCT_DEFINITION':{'role':'资深外贸产品定义师','mission':'把行业输入转化为16维产品语义矩阵与动态查询计划：同义词/拼写变体/买卖方术语/材料/功能/贸易术语/HS候选/排除词。契约是后续所有节点的判定基准。',
        'accept':['语义矩阵维度齐备','查询计划覆盖精度与召回两条线','排除词明确']},
 'TRADE_STRATEGY':{'role':'贸易定位策略师','mission':'基于产品语义矩阵制定12要素搜索计划，覆盖买家直搜与供应商反查两条线；HS是强辅助信号不是硬过滤。',
        'accept':['查询计划非空且与矩阵一致','HS策略为强信号非硬过滤','有复盘建议时必须回应建议']},
 'CUSTOMS_NODE_COLLECTION':{'role':'海关节点采集质检员','mission':'检验采集到的贸易节点：是否真实存在于海关数据、是否携带贸易证据、逐查询计量是否留痕。',
        'accept':['贸易节点数≥1','无明显的词典/翻译/电商垃圾','每条查询有计量记录']},
 'TRADE_EDGE_BUILD':{'role':'贸易关系构建师','mission':'把图谱关系收敛为标准贸易边：buyer/supplier/产品/HS/票数/首末日期/来源/证据等级/置信度，边必须来自真实海关关系。',
        'accept':['边携带标准字段','每条边有初步证据等级','端点已登记贸易节点池']},
 'EVIDENCE_VERIFY':{'role':'证据审查官','mission':'对全部贸易边做四级验证（STRONG/MEDIUM/WEAK/UNVERIFIED），弱证据降权不删除。',
        'accept':['每条边有证据等级','弱证据降权保留不删除','核心图谱关系有证据支撑']},
 'ENTITY_RESOLUTION':{'role':'实体解析师','mission':'贸易节点归并为企业实体：名称标准化/法律后缀归一/去重/别名/known-new；同一实体多角色合并为 CUSTOMER_AND_SUPPLIER，无法判定为 UNKNOWN。',
        'accept':['计数自洽（合并数可解释）','已知实体只做合并不重置','UNKNOWN 保留不删除']},
 'GRAPH_EXPANSION':{'role':'贸易网络扩张师','mission':'递归多层双向扩张（客户→供应商→客户），新增实体全部回流，动态停止条件明确。',
        'accept':['递归不丢实体','停止原因明确','扩张边进入统一建边通道']},
 'RESOURCE_CLASSIFICATION':{'role':'资源分类审判官','mission':'按 实体角色×贸易状态×开发状态 三维分类，每个实体必须有 classification_reason；分类依据来自证据/贸易关系/业务规则，不是LLM随机判断。',
        'accept':['逐实体有三维结论与理由','放行标准与证据一致','UNKNOWN 只进图谱库']},
 'DATABASE_COMMIT':{'role':'入库对账员','mission':'三类资产（Entity+Edge+Evidence）幂等入库，数量恒等可解释，回读自证。',
        'accept':['数量恒等式成立','幂等去重如实报告','回读验证通过']},
 'DEV_VERIFY':{'role':'客户真实性验证员','mission':'验证客户资料真实可用后才允许进入开发序列。','accept':['有硬证据或已审核资料']},
 'ACCOUNT_INTEL':{'role':'客户情报官','mission':'整理客户贸易背景/供应商关系/证据事件并指出缺口，证据可追溯。','accept':['实体存在','证据可追溯','缺口如实报告']},
 'ENRICH':{'role':'字段级补全专家','mission':'按字段 waterfall 补全缺口：成功即停、便宜优先、最后验证；补不上如实报告不编造。','accept':['逐字段留痕','邮箱经过验证','无编造值']},
 'CONTACT':{'role':'联系人发现专家','mission':'发现采购联系人并生成验证后的候选邮箱；只推荐第一名，绝不群发。','accept':['候选有验证状态','推荐唯一']},
 'ICP':{'role':'客户资格分析师','mission':'Fit×Intent×Timing 分层评分+分数带+可解释原因；证据不足保持低带，不编造需求。','accept':['有证据才加分','原因可解释','可联系性单独计分']},
 'DEV_OFFER':{'role':'Offer策略师','mission':'按机会窗口生成低风险报价策略，不声称未经证据支持的采购行为。','accept':['策略与证据一致']},
 'DEV_LETTER':{'role':'开发信撰稿人','mission':'写简短英文开发信，自然引用品类相关性，不编造数字。','accept':['英文简短','无编造数据']},
 'DEV_REVIEW':{'role':'人工审核门','mission':'开发信草稿必须经人工审核才能进入发送准备。','accept':['草稿状态正确']},
 'DEV_SEND':{'role':'发送准备守门员','mission':'半自动：只生成发送包（收件人+compose URL），绝不自动发送；已发送不重复。','accept':['不自动发送','不重复发送','无邮箱如实停止']},
 'MISSION_DIRECTOR':{'role':'任务总统筹与决策规划专家','mission':'掌握全局任务状态、节点交接、证据质量和失败诊断，决定下一步执行、重试、换策略、跳过或终止。不得编造事实；优先保护证据质量。','accept':['计划与当前任务一致','失败时给出可执行的替代方案','不得让无硬证据候选直接进入高质量客户池']},
 'REFLECT':{'role':'复盘诊断师','mission':'诊断上游失败根因（查询词太窄/垃圾结果/风控/闸门过严），开出可执行的纠正处方：新查询词+调整建议。',
        'accept':['诊断指到具体根因','给出新的查询词或明确放弃理由']},
}
_SYS='你是{role}。{mission}\n以专家标准复核给你的工作结果，只输出JSON：{{"verdict":"pass或fail","thinking":"推理过程,150字内","criteria":[{{"name":"验收项","ok":true或false,"detail":"一句依据"}}],"notes":"给下游节点的一句话交接建议"}}'
def _engine():
    global _ENG
    try: return _ENG
    except NameError:
        _ENG=ReasoningEngine(); return _ENG
def review(node,subject,rule_checks=None,critical=None):
    """专家复核主入口。
    node: 节点名；subject: 给专家看的工作结果摘要；
    rule_checks: [(name,ok,detail)] 确定性规则验收；critical: 其中一票否决的项名集合。
    返回 report: {role,verdict,criteria,thinking,notes,offline,ts}"""
    rule_checks=rule_checks or []; critical=critical or set()
    exp=EXPERTS.get(node,{'role':'专家','mission':'复核工作结果','accept':[]})
    report={'role':exp['role'],'mission':exp['mission'],'verdict':'pass',
            'criteria':[{'name':n,'ok':bool(ok),'detail':d,'by':'rule'} for n,ok,d in rule_checks],
            'thinking':'','notes':'','offline':False,'ts':time.time()}
    rule_fail=[c for c in report['criteria'] if not c['ok'] and c['name'] in critical]
    if not settings.EXPERT_MODE:
        report['thinking']='EXPERT_MODE 关闭，仅规则验收'
        report['verdict']='fail' if rule_fail else 'pass'
        return report
    eng=_engine()
    if not eng.available:
        report['offline']=True
        report['thinking']='LLM 离线，降级为规则验收'
        report['verdict']='fail' if rule_fail else 'degraded'
        return report
    accept_txt='\n'.join('- '+a for a in exp['accept']) or '- 结果合理可用'
    prompt=('验收标准：\n'+accept_txt+'\n\n规则预检结果（可参考，可推翻非关键项）：\n'
            +('\n'.join('- %s: %s %s'%(c['name'],'OK' if c['ok'] else 'FAIL',c['detail']) for c in report['criteria']) or '（无）')
            +'\n\n待验收的工作结果：\n'+str(subject)[:3500])
    r=eng.review(prompt,system=_SYS.format(**exp))
    if not r:
        report['offline']=True
        report['thinking']='LLM 复核未返回有效JSON，降级为规则验收'
        report['verdict']='fail' if rule_fail else 'degraded'
        return report
    # LLM 结论并入（规则关键项失败不可被推翻——硬底线）
    report['thinking']=str(r.get('thinking') or '')[:600]
    report['notes']=str(r.get('notes') or '')[:300]
    for c in (r.get('criteria') or [])[:8]:
        report['criteria'].append({'name':str(c.get('name') or '?')[:60],'ok':bool(c.get('ok')),
                                   'detail':str(c.get('detail') or '')[:160],'by':'llm'})
    llm_verdict=str(r.get('verdict') or '').lower()
    if rule_fail: report['verdict']='fail'
    elif llm_verdict=='fail': report['verdict']='fail'
    else: report['verdict']='pass'
    return report
def diagnose(fail_node,fail_report,context):
    """REFLECT 节点的诊断调用 → {diagnosis,advice,new_queries[]}；LLM 离线给规则处方"""
    exp=EXPERTS['REFLECT']
    eng=_engine()
    if eng.available:
        prompt=(f'失败节点：{fail_node}\n失败验收报告：\n{fail_report}\n\n任务上下文：\n{context}'
                '\n\n只输出JSON：{"diagnosis":"根因,120字内","advice":"纠正处方,120字内","new_queries":["改写后的英文搜索词,最多4个"]}')
        r=eng.review(prompt,system='你是'+exp['role']+'。'+exp['mission'])
        if r:
            qs=[str(x).strip() for x in (r.get('new_queries') or []) if str(x).strip()][:4]
            return {'diagnosis':str(r.get('diagnosis') or '')[:300],'advice':str(r.get('advice') or '')[:300],
                    'new_queries':qs,'by':'llm'}
    # 规则处方：换一批未用过的进化变体
    return {'diagnosis':'LLM 离线，按规则处方：换用更宽/更窄的查询词组合重试',
            'advice':'试试加 importer/buyer/wholesale 后缀，或换成 HS 3406 相关词',
            'new_queries':[],'by':'rule'}

def _call_with_timeout(fn, timeout):
    """硬时限执行：LLM 端点“连得上但不返回”时，HTTP 超时可能迟迟不触发，
    这里用线程 join 强制封顶，超时就放弃本次规划，绝不让任务冻结在 INIT。"""
    import threading
    box = {}
    def run():
        try: box['r'] = fn()
        except Exception: box['r'] = None
    t = threading.Thread(target=run, daemon=True)
    t.start(); t.join(max(5, int(timeout or 60)))
    return box.get('r')


def mission_plan(state, event='continue', failure=None):
    """MISSION_DIRECTOR（总统筹）独立模型调用：输出行动决策，不直接执行节点。
    v34.0 收口：决策字段只有 action/reason/plan/questions——没有 next_node，
    流程走向由编排层（graph.run_graph）根据 action 唯一裁决，顾问不选路。"""
    if not settings.MISSION_DIRECTOR_ENABLED:
        return {'action':'continue','reason':'总统筹模型关闭','plan':[],'by':'rule'}
    eng=_engine()
    if not eng.available:
        return {'action':'continue','reason':'本地模型不可用，按固定拓扑继续','plan':[],'by':'rule'}
    snapshot={
      'task_id':state.get('task_id'),'goal':state.get('request'),'market':state.get('market'),'industry':state.get('industry'),
      'current_node':state.get('current_node'),'event':event,'failure':failure or {},
      'node_status':state.get('node_status',{}),'handoffs':state.get('handoffs',{}),
      'evidence_summary':state.get('evidence_summary',{}),'candidate_counts':{'companies':len(state.get('companies') or []),'new':len(state.get('new_companies') or []),'suppliers':len(state.get('suppliers') or [])},
      'reflection':state.get('reflection',{}), 'constraints':['FIRST ROUND DATA SOURCES MUST BE CUSTOMS/SHIPMENT DATA PROVIDERS ONLY','derive buyer→supplier→supplier→buyer relations from customs/shipment data only','public crawlers may be used only for enrichment/verification after the customs graph','exhibitions/web directories are fallback verification only and must never replace customs evidence','do not bypass access controls','prefer stable public evidence']
    }
    prompt=('你是整个外贸客户采集任务的总统筹。你不直接执行工具，只负责决定下一步。\n'
            '任务状态：\n'+json.dumps(snapshot,ensure_ascii=False)[:10000]+
            '\n请输出JSON：{"action":"continue|retry|replan|skip|abort","reason":"简短原因","plan":["最多3个具体动作"],"questions":["需要补查的问题"]}')
    r=_call_with_timeout(lambda: eng.review(prompt,system='你是任务总统筹与决策规划专家。第一采集链只能使用海关/提单数据源（包括ImportYeti及其他有海关数据的站点）；禁止用B2B、普通搜索、展会替代第一采集。供应商和反向客户也必须优先从海关关系图谱提取。证据优先，宁缺毋滥。只输出JSON。'),
                         getattr(settings,'MISSION_DIRECTOR_TIMEOUT',90))
    if not r:
        return {'action':'continue','reason':'总统筹未返回有效方案或超时，按固定拓扑继续','plan':[],'by':'fallback'}
    return {'action':str(r.get('action') or 'continue'),'reason':str(r.get('reason') or '')[:500],
            'plan':[str(x)[:300] for x in (r.get('plan') or [])[:3]],
            'questions':[str(x)[:200] for x in (r.get('questions') or [])[:5]],'by':'llm'}

def build_diagnostic_package(state,node,error,attempts):
    """给网页GPT的详细事实包：描述事实、已尝试、可用工具和约束，不把错误当作根因。"""
    return {
      'task':{'id':state.get('task_id'),'goal':state.get('request'),'market':state.get('market'),'industry':state.get('industry')},
      'stage':{'node':node,'attempts':attempts,'current':state.get('current_node')},
      'observed_error':str(error or '')[:1500],
      'successful_work':{'node_status':state.get('node_status',{}),'handoffs':state.get('handoffs',{}),
                         'companies':len(state.get('companies') or []),'suppliers':len(state.get('suppliers') or []),
                         'new_companies':len(state.get('new_companies') or [])},
      'evidence':state.get('evidence_summary',{}),
      'source_errors':(state.get('source_errors') or [])[-10:],
      'attempt_history':(state.get('retry_history') or [])[-8:],
      'constraints':['use public/stable data paths','do not bypass login/captcha/access controls','do not treat generic search results as trade evidence'],
      'required_answer':['likely root causes ranked','what to test next','what to skip if blocked','whether the task can continue safely']
    }
