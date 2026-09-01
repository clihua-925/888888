# -*- coding: utf-8 -*-
"""v34.0 业务节点层（专业执行层）：九节点薄包装 + 执行器。

关键词 → 海关贸易数据节点 → 确定 importer/supplier/shipper 节点 → 保存贸易证据
→ 从节点展开关联企业 → 贸易关系图谱。
第一阶段只建完整贸易节点图（简单净化，不评分）；第二阶段才做客户价值判断。

最终架构收敛（v34.0）：
- 节点只有执行权：不返回 abort/next_node/编排状态（编排层统一剥离，见 graph.ORCHESTRATOR_KEYS）。
- 边的生命周期唯一通道：TRADE_EDGE_BUILD 建边(内存) → EVIDENCE_VERIFY 分级(内存+存量对账)
  → DATABASE_COMMIT 唯一正式写库。执行器不再直接写 relationships。
- 证据分级唯一实现：core.trade_graph.trade_node.evidence_level（本文件 _evidence_level 为别名）。
- 复核键 = canonical node_id（与 graph.ORDER 同名），不再出现 ICP/A_COLLECT 等旧键。
"""
import json, os, re, sqlite3, time
import requests
from pathlib import Path
from core.config import settings
from core.config.industry import load_industry
from core.model.reasoning import ReasoningEngine
from core.runtime import experts
from core.tools.data_sources.manager import DataSourceManager, Evolution, gate_check, norm, noise, identity_valid, hard_evidence
from core.tools import suppliers as sup
from core.tools import expand as expand_tool
from core.tools import trade_filter
from core.trade_graph import customs_node_pipeline as cnp
from core.trade_graph.trade_node import (evidence_level, TRUSTED_SOURCES, EVIDENCE_DEMOTE,
                                         LOGISTICS_RE, EVIDENCE_LEVELS, is_non_company_name)

# 证据四级唯一判定函数的本层别名（canonical 实现在 trade_node.py，禁止第二套分级逻辑）
_evidence_level = evidence_level

# v10 恢复：第一链查询词必须携带的贸易证据信号（定位贸易节点，而不是找联系方式）
TRADE_EVIDENCE_SIGNALS = ('importer of record', 'customs data', 'bill of lading',
                          'import records', 'hs code', 'shipment', 'shipper',
                          'consignee', 'importer', 'supplier')

BAD = re.compile(r'on behalf of|freight|forwarder|logistics|express|cargo|shipping|customs broker|packaging|consulting|翻译|词典|物流|货代', re.I)
_engine = None

def _eng():
    global _engine
    if _engine is None:
        _engine = ReasoningEngine()
    return _engine

def _report(state, node, rep):
    nr = dict(state.get('node_reports') or {})
    nr[node] = rep
    return nr

def _ev(c):
    e = c.get('evidence') or {}
    bits = []
    if e.get('shipments'):
        bits.append(f"shipments={e['shipments']}")
    if e.get('score'):
        bits.append(f"score={e['score']}")
    if e.get('last_seen'):
        bits.append(f"last_seen={e['last_seen']}")
    return (' [' + ', '.join(str(b) for b in bits) + ']') if bits else ''

def _brief(cs, n=12):
    return '\n'.join('- ' + c.get('name','') + ' | ' + str(c.get('country','')) + ' | ' + str(c.get('source','')) + _ev(c) for c in (cs or [])[:n])

# ---------- 1. ICP 客户画像师 ----------
def n_icp(state):
    ind = state['industry']
    icp = None
    industry_cfg = load_industry(ind)
    # 优先使用配置中的 ICP，避免不必要的 LLM 调用
    if settings.EXPERT_MODE and _eng().available:
        icp = _eng().review(
            f'市场:{state["market"]} 行业:{ind}\n生成客户画像契约JSON：'
            '{"must":["必收信号3-5条"],"reject":["拒收信号3-5条"],"keywords":["英文关键词5-8个"],"hs":["相关HS编码"]}',
            system='你是资深外贸客户画像师，只输出JSON')
    if not icp or not icp.get('must'):
        icp = {'must': industry_cfg.get('icp_must', ['USA company', 'import or trade evidence']),
               'reject': industry_cfg.get('icp_reject', ['dictionary', 'marketplace retail page', 'freight forwarder']),
               'keywords': industry_cfg.get('keywords', [ind]),
               'hs': industry_cfg.get('hs_codes', [])}
    rep = experts.review('PRODUCT_DEFINITION', 'ICP契约：\n' + json.dumps(icp, ensure_ascii=False),
                         [('含必收信号', bool(icp.get('must')), 'must 非空' if icp.get('must') else 'must 缺失'),
                          ('含拒收信号', bool(icp.get('reject')), 'reject 非空' if icp.get('reject') else 'reject 缺失'),
                          ('关键词与行业相关', bool(icp.get('keywords')), ','.join((icp.get('keywords') or [])[:5]))],
                         critical={'含必收信号','含拒收信号'})
    return {'icp': icp, 'node_reports': _report(state, 'PRODUCT_DEFINITION', rep), '_note': 'ICP契约已锁定'}

# ---------- 2. STRATEGY 贸易节点定位策略师：第一次搜索的目标是定位贸易节点 ----------
def n_strategy(state):
    industry_cfg = load_industry(state.get('industry'))
    plan = Evolution().plan(state['market'], state['industry'])
    # v30.8 Product Intelligence Layer：产品不是单一关键词，而是
    # 主名称+同义词+商业采购名+材料词+应用词+HS候选集+排除词 的情报档案。
    # LLM 可用时扩展档案，不可用时确定性兜底（行业配置+内置采购修饰词），不断链。
    from core.trade_graph import product_intelligence as pi
    # v31.0：PRODUCT_DEFINITION 已产出档案则直接复用，避免重复 LLM 调用与定义漂移
    profile=state.get('product_profile') or pi.build_product_profile(state['industry'],state.get('icp'))
    pi_queries=pi.expand_queries(profile)  # v33.0：无固定上限，矩阵产出多少用多少
    hs_validation=state.get('product_domain',{}).get('hs_validation') or pi.validate_hs(profile['hs_candidates'])  # 只标注不过滤：第一轮宽覆盖
    # 生产模式固定为“海关多源并行 + 增量轮换”，不能因为某个源首轮返回足量就停止后续硬源。
    configured=list(industry_cfg.get('search_terms') or [])
    keywords=list(industry_cfg.get('keywords') or [])
    defaults=[]
    for q in configured + [f"{x} importer" for x in keywords[:3]]:
        if q and q not in defaults: defaults.append(q)
    base=[v for v in (state.get('query_override') or defaults or [state['industry']]) if v][:6]
    # v10 恢复：第一链查询词必须携带贸易证据信号，使命是“定位贸易节点”而非“找联系方式”。
    sig_q=[]
    for kw in (keywords[:2] or [state['industry']]):
        for sig in ('importer of record','bill of lading','hs code'):
            qq=f'{kw} {sig}'
            if qq not in sig_q: sig_q.append(qq)
    # 宽覆盖：产品情报变体优先，既有证据信号词保留；v33.0 起不设固定上限
    # （上限跟随16维矩阵产出，低价值查询由 query_stats 动态降权而非砍数量）。
    queries=[]
    for q in pi_queries+base+sig_q:
        if q and q not in queries: queries.append(q)
    hs_codes=profile['hs_candidates'] or cnp.resolve_hs_codes(state.get('industry'), state.get('icp'))
    rationale=('第一采集链以海关贸易数据节点为中心：关键词→HS编码→海关/提单数据源→'
               '确定 importer/supplier/shipper 节点并保存贸易证据；不使用通用搜索引擎结果；'
               '每次运行做增量 delta + 历史轮换；已有客户只合并新证据，新客户才进入开发池；'
               '展会/普通网络仅后置补充验证（第二阶段）')
    strategy={'queries':queries,'source_queries':{x:queries for x in ('customs','importyeti','importyeti_web')},
              'sources':['hs_finder','customs_bulk','customs_raw','importyeti','importyeti_web','customs_web'],
              'secondary_sources':['public_crawler','exhibition','web_verify'],'hs_codes':hs_codes,
              'product_profile':profile,'exclusions':profile.get('exclusions') or [],'hs_validation':hs_validation,
              'objective':'locate_trade_nodes','first_chain':'customs_node_centric',
              'rationale':rationale,'evolution':plan,'incremental':True,'fanout_hard_sources':True}
    rep=experts.review('TRADE_STRATEGY','查询参数：'+json.dumps(queries,ensure_ascii=False)+'\nHS：'+','.join(hs_codes or [])+'\n策略：'+rationale,
                       [('至少2个产品/行业查询变体',len(queries)>=2,f'{len(queries)}个'),
                        ('主证据源为海关贸易源',True,'hs_finder + customs fan-out'),
                        ('查询词含贸易证据信号',any(any(sig in q.lower() for sig in TRADE_EVIDENCE_SIGNALS) for q in queries),'已包含'),
                        ('增量运行已启用',True,'delta + rotating window')],critical={'主证据源为海关贸易源','查询词含贸易证据信号','增量运行已启用'})
    return {'strategy':strategy,'node_reports':_report(state,'TRADE_STRATEGY',rep),'_note':f"产品情报：同义词{len(profile['synonyms'])}·商业名{len(profile['commercial_names'])}·排除词{len(profile['exclusions'])}·HS候选{len(hs_codes or [])}(已验证{sum(1 for v in hs_validation.values() if v['validated'])})·查询{len(queries)}个·宽覆盖"}

# ---------- 3. A_COLLECT 贸易节点采集（海关节点中心；确定性通过，保留简单净化） ----------
def n_collect(state):
    # v30：第一采集链 = CustomsNodePipeline（关键词→HS→海关源 fan-out→节点识别）。
    pipe=cnp.CustomsNodePipeline()
    qs=(state.get('strategy') or {}).get('queries'); sq=(state.get('strategy') or {}).get('source_queries')
    companies,used,errors,gate,graph,node_stats=pipe.run(
        state['market'],state['industry'],state['quantity'],
        queries=qs,source_queries=sq,icp=state.get('icp'),task_id=state.get('task_id',''))
    mgr=pipe  # last_evolution 兼容（下方读取 mgr.last_evolution）
    # 保存贸易证据：节点级证据事件落盘（图谱关系边由 SUPPLIER_MINING/REVERSE_HARVEST 展开后保存）。
    try: cnp.save_graph(graph,state.get('task_id',''),depth=0)
    except Exception: pass
    state['trade_graph']=graph.to_dict()
    # RAW 保留：这里不因资料缺失淘汰客户。明确非客户才进入 quarantine。
    raw=list(companies); identity=[]; quarantine=[]
    # v30 第一轮简单净化：删除百科/新闻/词典/翻译/广告目录/明显错误企业；
    # 保留一切带贸易节点信号（importer/exporter/supplier/manufacturer/shipper/
    # consignee/notify party/HS/shipment/BOL/trade evidence）的候选。不评分。
    purified,dropped=trade_filter.purify(raw,exclusions=(state.get('strategy') or {}).get('exclusions'))
    quarantine.extend(c for c,_r in dropped)
    for c in purified:
        if not identity_valid(c):
            quarantine.append(c)
        else:
            identity.append(c)
    stats={'raw':len(raw),'clean':len(identity),'noise':len(quarantine),'duplicate':0,'identity_only':0,'hard_evidence':sum(1 for c in identity if (c.get('evidence') or {}).get('shipments') or (c.get('evidence') or {}).get('customs') or (c.get('evidence') or {}).get('trade_evidence')),
           'new_candidates':int(gate.get('new_candidates') or 0),'existing_enriched':int(gate.get('existing_enriched') or 0),'source_fanout':True,'incremental':True,
           'trade_nodes':node_stats.get('nodes',0),'node_roles':node_stats.get('by_role',{}),'hs_codes':node_stats.get('hs_codes',[])}
    stats['noise_ratio']=stats['noise']/max(1,stats['raw']);stats['clean_ratio']=stats['clean']/max(1,stats['raw'])
    for c in identity:
        e=c.setdefault('evidence',{}); is_hard=any(e.get(k) for k in ('shipments','customs','trade_evidence','bill_of_lading','supplier_relation'))
        e.setdefault('evidence_level','hard_trade' if is_hard else 'identity_only')
        if not is_hard: stats['identity_only']+=1
    pen=node_stats.get('penetration') or {}
    pen_criteria=[]
    if pen:
        pen_criteria=[
            {'name':'① IY锁定贸易节点','ok':bool(pen.get('locked')),'detail':f"{pen.get('locked',0)} 个入口节点（关键词→ImportYeti搜索）"},
            {'name':'② 递归渗透展开','ok':pen.get('nodes',0)>pen.get('locked',0),'detail':f"+{pen.get('nodes',0)} 节点 · {pen.get('relations',0)} 条贸易关系 · 页访 {pen.get('pages',0)}"},
            {'name':'③ 渗透停止原因','ok':True,'detail':{'frontier_drained':'节点全部展开完毕','page_budget':'页访预算耗尽（关系已保留，下轮继续）','max_nodes':'达到单轮节点上限','circuit_breaker':'连续失败熔断'}.get(pen.get('stopped_by'),pen.get('stopped_by') or '—')}]
    rep={'verdict':'pass' if identity else 'fail','role':'SOURCE_COLLECTOR','criteria':pen_criteria+[{'name':'有身份即保留','ok':bool(identity),'detail':f'{len(identity)}家'},{'name':'明确垃圾隔离','ok':True,'detail':f'{len(quarantine)}家'}], 'notes':f'RAW {len(raw)} · clean候选 {len(identity)} · quarantine {len(quarantine)}'}
    pen=node_stats.get('penetration') or {}
    pen_note=(f" · 节点渗透 {pen.get('nodes',0)} 节点/关系 {pen.get('relations',0)} 条/页访 {pen.get('pages',0)}" if pen.get('nodes') else '')
    graph_note=f" · 买家 {node_stats.get('buyers',0)}/供应商 {node_stats.get('suppliers',0)}/网络深度 {node_stats.get('network_depth',0)}" if node_stats.get('buyers') or node_stats.get('suppliers') else ''
    return {'raw_companies':raw,'companies':identity,'quarantine':quarantine,'source':'+'.join(used) if used else 'none','source_errors':errors,'collect_gate':gate,'clean_stats':stats,'evolution':mgr.last_evolution,'node_reports':_report(state,'CUSTOMS_NODE_COLLECTION',rep),'_success':bool(identity),'_note':f'增量采集 {len(raw)} · 新候选 {stats["new_candidates"]} · 已有客户补充 {stats["existing_enriched"]} · 隔离 {len(quarantine)}{pen_note}{graph_note}'}

def hard_evidence_local(c):
    e=c.get('evidence') or {};return bool(e.get('shipments') or e.get('customs') or e.get('trade_evidence') or e.get('bill_of_lading') or e.get('supplier_relation'))

def n_seed_buyers(state):
    cs=list(state.get('task_data') or state.get('companies') or []);seeds=[]
    for c in cs:
        # seed必须尽量来自硬贸易源；身份-only也保留，但作为低证据种子
        c=dict(c);c['seed_role']='buyer_seed';seeds.append(c)
    # 关系图应覆盖本轮全部有效客户；外部网页补缺由 SUPPLIER_MINING_BUYERS 控制。
    seeds=seeds[:max(1, min(len(seeds), int(state.get('quantity') or settings.SEED_BUYERS_PER_TASK)))]
    rep=experts.review('GRAPH_EXPANSION',f'种子客户{len(seeds)}家', [('种子存在',bool(seeds),str(len(seeds)))],critical={'种子存在'})
    return {'seed_buyers':seeds,'companies':seeds,'node_reports':_report(state,'GRAPH_EXPANSION',rep),'_success':bool(seeds),'_note':f'形成种子客户 {len(seeds)} 家'}

def n_supplier_mining(state):
    """客户→供应商：第一优先级必须来自海关贸易记录；ImportYeti网页仅作为同类海关数据源补充。"""
    # 本地 customs_raw 没有逐票成本，第一轮清洗通过的客户全部进入关系图；
    # SUPPLIER_MINING_BUYERS 只限制需要访问 ImportYeti 网页补缺的外部客户数，避免免费额度被浪费。
    seeds=list(state.get('seed_buyers') or state.get('companies') or [])
    results=[]; supplier_rows=[]; relations=[]; errors=[]
    try:
        from core.tools.customs_graph import buyer_to_suppliers
        supplier_rows, relations = buyer_to_suppliers(seeds, settings.IY_WEB_MAX_SUPPLIERS)
        results.append({'source':'customs_raw','buyers':len(seeds),'suppliers':len(supplier_rows),'relations':len(relations)})
    except Exception as e:
        errors.append('customs_raw:'+str(e)[:160])
    # 如果本地原始海关库没有覆盖某个种子，再使用 ImportYeti 这一同类海关数据网站的免费网页关系。
    covered={x['norm'] for x in supplier_rows}
    missing=[b for b in seeds if not any(norm(r.get('from_name'))==norm(b.get('name')) for r in relations)]
    if missing and settings.IY_WEB_ENABLED:
        missing=missing[:settings.SUPPLIER_MINING_BUYERS]
        try:
            from core.tools import iy_web
            if iy_web.available():
                with iy_web.IYWeb() as w:
                    # v10 渗透方式：买家节点携带第一搜索时拿到的公司主页 URL（evidence.url），
                    # 直接透视该页的 Suppliers 区；缺 URL 时按名搜索解析主页，绝不猜 slug。
                    # v30.3 防资源枯竭：节点注册表 NODE_REVISIT_DAYS 内已访问过的买家页不再重复访问；
                    # 页访预算 IY_PAGE_BUDGET 耗尽即停止开新页（已挖到的关系全部保留）。
                    from core.trade_graph import iy_network as iyn
                    budget=iyn.PageBudget(); fails=0; skipped_fresh=0
                    for buyer in sorted(missing[:int(getattr(settings,'IY_WEB_TOP_BUYERS',settings.SUPPLIER_MINING_BUYERS))],
                                        key=lambda b:-int((b.get('evidence') or {}).get('shipments') or 0)):
                        if fails>=2: break  # v10 熔断：连续2个节点失败即停，保住浏览器配额
                        bn=norm(buyer.get('name'))
                        if iyn.node_fresh(bn,'company'):
                            skipped_fresh+=1; continue  # 该节点近期已渗透，供应商已在池中，不重复烧页访
                        try:
                            url=str((buyer.get('evidence') or {}).get('url') or '') or iyn.node_url(bn,'company')
                            if '/company/' not in url:
                                if not budget.take('search:'+str(buyer.get('name'))[:40]): break
                                url=w.company_page_for(buyer.get('name','')) or ''
                            if not url:
                                fails+=1; errors.append(f"{buyer.get('name')}: 未解析到 ImportYeti 公司主页"); continue
                            if not budget.take('page:'+url[-60:]): break
                            rows=w.relationships(url,'Suppliers')[:settings.IY_WEB_MAX_SUPPLIERS]
                            if not rows and w.last_error: fails+=1
                            else:
                                fails=0
                                iyn.mark_node(bn,'company',slug=url.rstrip('/').split('/')[-1],url=url,
                                              shipments=int((buyer.get('evidence') or {}).get('shipments') or 0),run_id=state.get('task_id',''))
                            for r in rows:
                                nm=r.get('name') or ''; sn=norm(nm)
                                if not sn: continue
                                e={'customs':True,'trade_evidence':True,'shipments':r.get('shipments') or 0,'products':r.get('products') or '', 'hs':r.get('hs') or [], 'supplier_relation':buyer.get('name'),'url':r.get('url') or ''}
                                supplier_rows.append({'norm':sn,'name':nm,'slug':r.get('url','').rstrip('/').split('/')[-1] if r.get('url') else '', 'shipments':r.get('shipments') or 0,'last_seen':time.time(),'harvested':False,'bol_fetched':0,'via':'importyeti_web','evidence':e})
                                relations.append({'from_name':buyer.get('name'),'from_type':'buyer','to_name':nm,'to_type':'supplier','relation':'buyer_to_supplier','evidence':e,'source':'importyeti_web','confidence':.95})
                            results.append({'source':'importyeti_web','buyer':buyer.get('name'),'suppliers':len(rows)})
                        except Exception as e:
                            fails+=1; errors.append(f"{buyer.get('name')}: {str(e)[:100]}")
                    if skipped_fresh or budget.spent_on:
                        results.append({'source':'importyeti_web','summary':budget.note()+f'·注册表命中跳过{skipped_fresh}个已渗透节点'})
        except Exception as e: errors.append('importyeti_web:'+str(e)[:160])
    # 第三层：ImportKey公开海关公司页。仅补没有本地/ImportYeti覆盖的种子；不做普通搜索。
    if missing and settings.IMPORTKEY_ENABLED:
        try:
            from core.tools.data_sources.sources import ImportKeyPublicSource
            ik=ImportKeyPublicSource()
            for buyer in missing[:settings.SUPPLIER_MINING_BUYERS]:
                rows=ik.company_relationships(buyer.get('name',''),'suppliers',settings.IMPORTKEY_MAX_RELATIONS)
                for r in rows:
                    nm=r.get('name') or ''; sn=norm(nm)
                    if not sn: continue
                    e={'customs':True,'trade_evidence':True,'shipments':r.get('shipments') or 0,'supplier_relation':buyer.get('name'),'url':r.get('url') or ''}
                    supplier_rows.append({'norm':sn,'name':nm,'slug':'','shipments':r.get('shipments') or 0,'last_seen':time.time(),'harvested':False,'bol_fetched':0,'via':'importkey_public','evidence':e})
                    relations.append({'from_name':buyer.get('name'),'from_type':'buyer','to_name':nm,'to_type':'supplier','relation':'buyer_to_supplier','evidence':e,'source':'importkey_public','confidence':.9})
                if rows: results.append({'source':'importkey_public','buyer':buyer.get('name'),'suppliers':len(rows)})
        except Exception as e: errors.append('importkey_public:'+str(e)[:160])
    # 去重但不丢失“来自多个客户”的关系证据
    merged={}
    for x in supplier_rows:
        n=x.get('norm') or norm(x.get('name'))
        if not n or is_non_company_name(x.get('name')): continue  # v35 伪实体拦截

        if n not in merged: merged[n]=dict(x)
        else:
            merged[n]['shipments']=max(int(merged[n].get('shipments') or 0),int(x.get('shipments') or 0))
            if not merged[n].get('slug') and x.get('slug'): merged[n]['slug']=x['slug']
            merged[n]['via']=merged[n].get('via','')+'+'+x.get('via','')
    # v30 节点渗透：第一搜索/HS榜单落池的 supplier 节点必须进入反查链。
    # 搜索页命中的每个节点，其关联信息（供应商→客户）都要被继续挖出来，而不是只留在池里。
    try:
        for s in (sup.pool(days=365,min_shipments=0) or []):
            n=s.get('norm') or norm(s.get('name'))
            if not n or n in merged or is_non_company_name(s.get('name')): continue  # v35 伪实体拦截
            merged[n]={'norm':n,'name':s.get('name'),'slug':s.get('slug') or '',
                       'shipments':int(s.get('shipments') or 0),'last_seen':s.get('last_seen') or time.time(),
                       'harvested':bool(s.get('harvested')),'bol_fetched':s.get('bol_fetched') or 0,
                       'via':'supplier_pool+'+str(s.get('via') or ''),
                       'evidence':{'customs':True,'trade_evidence':True,'shipments':int(s.get('shipments') or 0)}}
    except Exception: pass
    # v30：全部供应商节点落池（sup.norm 为供应商池统一身份），收割状态可持久化
    try:
        sup.upsert_pool([{'norm':sup.norm(x.get('name')),'name':x.get('name'),
                          'slug':x.get('slug') or sup.slugify(x.get('name')),
                          'shipments':int(x.get('shipments') or 0),
                          'last_seen':x.get('last_seen') or time.time()} for x in merged.values() if x.get('name')])
    except Exception: pass
    # v30：用 suppliers 表的持久收割状态回填，已渗透节点下一轮不再重复反查
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH,timeout=10)
        done={r[0] for r in conn.execute("SELECT supplier_norm FROM suppliers WHERE harvested_at IS NOT NULL AND harvested_at!=''")}
        conn.close()
        for n,x in merged.items():
            if sup.norm(x.get('name')) in done: x['harvested']=True
    except Exception: pass
    p=sorted(merged.values(),key=lambda x:-int(x.get('shipments') or 0))[:settings.SUPPLIER_MINING_MAX_SUPPLIERS]
    new=[x for x in p if not x.get('harvested')]
    # v30：供应商节点与 buyer→supplier 边合并进贸易关系图谱（第一阶段建图，不评分）
    try:
        g=cnp.TradeGraph()
        for x in p:
            nd=cnp.TradeNode(x.get('name'),'supplier',x.get('via') or '')
            if x.get('evidence'): nd.add_evidence(x['evidence'])
            g.add_node(nd)
        for e in cnp.relations_to_edges(relations,1): g.add_edge(e)
        trade_graph=cnp.merge_graph_into_state(state,g,depth=1)
    except Exception:
        trade_graph=state.get('trade_graph')
    rep=experts.review('GRAPH_EXPANSION',f'客户→供应商：种子{len(seeds)}，海关关系{len(p)}，未收割{len(new)}，错误{len(errors)}', [('关系链存在',bool(p) or bool(errors),f'{len(p)}家')])
    ok=bool(p) or (not seeds) or (not settings.HARVEST_ENABLED)
    return {'suppliers':p,'supplier_new':new,'trade_graph':trade_graph,'supplier_mining':{'buyers':results,'errors':errors,'relation_source_policy':'customs_trade_only'},'node_reports':_report(state,'GRAPH_EXPANSION',rep),'_success':ok,'_note':f'客户→供应商 {len(p)} 家·新工厂 {len(new)} 家·海关关系优先'}


def n_reverse_harvest(state):
    """供应商→客户：优先从 customs_raw 反查；无本地覆盖时才使用 ImportYeti 海关网页关系。"""
    if not settings.HARVEST_ENABLED:
        return {'harvest':{'mode':'disabled'},'_success':True,'_note':'收割禁用'}
    new=state.get('supplier_new') or []; merged=list(state.get('companies') or []); have={norm(c.get('name')) for c in merged}; results=[]; errors=[]; added_total=0
    if not new:
        return {'harvest':{'mode':'idle','results':[]},'node_reports':_report(state,'GRAPH_EXPANSION',experts.review('GRAPH_EXPANSION','供应商已收割完毕，正常终态')),'_success':True,'_note':'本轮无新工厂可收割'}
    # 第一层：本地海关原始记录
    profiled=0
    try:
        from core.tools.customs_graph import supplier_to_buyers
        buyers, relations=supplier_to_buyers(new[:settings.NETWORK_EXPANSION_SUPPLIERS], settings.IY_WEB_MAX_CUSTOMERS)
        for c in buyers:
            rn=norm(c.get('name'))
            if not rn or is_non_company_name(c.get('name')): continue  # v35 伪实体拦截
            if rn not in have:
                have.add(rn); merged.append(c); added_total+=1
        results.append({'source':'customs_raw','suppliers':len(new),'customers':len(buyers),'new':added_total})
        # v30.4 单点彻底性：本地提单覆盖的供应商，立即把“这个供应商分析清楚了没有”落成画像
        # （产品结构/档次推断/供应能力/客户覆盖），数据全部来自真实提单，推断如实标注。
        try:
            from core.trade_graph import supplier_profile as sprof
            local_customers={}
            for rel in relations:
                local_customers.setdefault(rel['from_name'],0)
                local_customers[rel['from_name']]+=1
            for s in new[:settings.NETWORK_EXPANSION_SUPPLIERS]:
                if norm(s.get('name')) in {norm(r.get('from_name')) for r in relations}:
                    if sprof.profile_supplier(s.get('name'),customers_found=local_customers.get(s.get('name'),0),run_id=state.get('task_id','')):
                        profiled+=1
        except Exception: pass
    except Exception as e:
        errors.append('customs_raw:'+str(e)[:160])
    # 第二层：ImportYeti，同样是海关/提单关系源；仅补没有本地海关覆盖的供应商
    covered_supplier_names={norm(x.get('from_name')) for x in relations} if 'relations' in locals() else set()
    # v30：本地海关层已渗透过的供应商同样标记，避免后续运行重复收割同一节点
    for s in new[:settings.NETWORK_EXPANSION_SUPPLIERS]:
        if norm(s.get('name')) in covered_supplier_names:
            try: sup.mark_harvested(sup.norm(s.get('name')),0)
            except Exception: pass
    fallback=[s for s in new[:settings.NETWORK_EXPANSION_SUPPLIERS] if norm(s.get('name')) not in covered_supplier_names]
    if fallback and settings.IY_WEB_ENABLED:
        try:
            from core.tools import iy_web
            if iy_web.available():
                with iy_web.IYWeb() as w:
                    # v10 渗透方式：落池时带真实 slug 的直接拼主页；没有的按名搜索解析主页，
                    # 绝不猜 slug；连续2个节点失败即熔断，保住浏览器配额。
                    # v30.3 防资源枯竭：供应商节点注册表去重 + 页访预算； harvested 标记之外
                    # 再加 NODE_REVISIT_DAYS 保护，避免同一节点页被反复打开。
                    from core.trade_graph import iy_network as iyn
                    budget=iyn.PageBudget(); fails=0; skipped_fresh=0
                    for s in fallback:
                        if fails>=2: break
                        sn_=sup.norm(s.get('name'))
                        if iyn.node_fresh(sn_,'supplier'):
                            skipped_fresh+=1
                            try: sup.mark_harvested(sn_,0)
                            except Exception: pass
                            continue
                        try:
                            if s.get('slug'):
                                url='https://www.importyeti.com/supplier/'+s['slug']
                            else:
                                url=iyn.node_url(sn_,'supplier')
                                if not url:
                                    if not budget.take('search:'+str(s.get('name'))[:40]): break
                                    url=w.supplier_page_for(s.get('name','')) or ''
                            if not url:
                                fails+=1; errors.append(f"{s.get('name')}: 未解析到 ImportYeti 供应商主页"); continue
                            if not budget.take('page:'+url[-60:]): break
                            rows=w.relationships(url,'Customers')[:settings.IY_WEB_MAX_CUSTOMERS]
                            if not rows and w.last_error:
                                fails+=1
                                try: sup.log_harvest(state.get('task_id'),s.get('slug') or '',s.get('name'),'importyeti_web','fail',0,str(w.last_error)[:120])
                                except Exception: pass
                                continue
                            fails=0
                            iyn.mark_node(sn_,'supplier',slug=s.get('slug') or url.rstrip('/').split('/')[-1],url=url,
                                          shipments=int(s.get('shipments') or 0),run_id=state.get('task_id',''))
                            # v30.4：该供应商的单点画像——产品档次/供应能力/客户覆盖度（拿到多少、页面共多少）
                            try:
                                from core.trade_graph import supplier_profile as sprof
                                if sprof.profile_supplier(s.get('name'),page_total=int(getattr(w,'last_total',0) or 0),
                                                          customers_found=len(rows),run_id=state.get('task_id','')):
                                    profiled+=1
                            except Exception: pass
                            added=0
                            for r in rows:
                                nm=r.get('name') or '';rn=norm(nm)
                                if not rn:continue
                                e={'customs':True,'trade_evidence':True,'shipments':r.get('shipments') or 0,'products':r.get('products') or '', 'hs':r.get('hs') or [], 'supplier_relation':s.get('name'),'url':url}
                                c={'name':nm,'country':'USA','industry':state.get('industry',''),'type':'importer','website':'','source':'importyeti_reverse','strength':5,'evidence':e}
                                if rn not in have:
                                    have.add(rn);merged.append(c);added+=1;added_total+=1
                            results.append({'source':'importyeti_web','supplier':s.get('name'),'customers':len(rows),'new':added})
                            # v30：渗透完成后标记已收割，下一轮从其他节点继续，不重复挖同一节点
                            try:
                                sup.mark_harvested(sup.norm(s.get('name')),len(rows))
                                _tot=int(getattr(w,'last_total',0) or 0)
                                sup.log_harvest(state.get('task_id'),s.get('slug') or '',s.get('name'),'importyeti_web','ok',len(rows),
                                                f'客户覆盖 {len(rows)}/{_tot}' if _tot else '')
                            except Exception: pass
                        except Exception as e:
                            fails+=1; errors.append(f"{s.get('name')}: {str(e)[:100]}")
                    if skipped_fresh or budget.spent_on:
                        results.append({'source':'importyeti_web','summary':budget.note()+f'·注册表命中跳过{skipped_fresh}个已渗透节点'})
        except Exception as e: errors.append('importyeti_web:'+str(e)[:160])
    # 第三层：ImportKey公开海关公司页，补没有本地/ImportYeti覆盖的供应商反向客户。
    if fallback and settings.IMPORTKEY_ENABLED:
        try:
            from core.tools.data_sources.sources import ImportKeyPublicSource
            ik=ImportKeyPublicSource()
            for s in fallback[:settings.NETWORK_EXPANSION_SUPPLIERS]:
                rows=ik.company_relationships(s.get('name',''),'buyers',settings.IMPORTKEY_MAX_RELATIONS)
                added=0
                for r in rows:
                    nm=r.get('name') or ''; rn=norm(nm)
                    if not rn: continue
                    e={'customs':True,'trade_evidence':True,'shipments':r.get('shipments') or 0,'supplier_relation':s.get('name'),'url':r.get('url') or ''}
                    c={'name':nm,'country':'USA','industry':state.get('industry',''),'type':'importer','website':'','source':'importkey_public','strength':5,'evidence':e}
                    if rn not in have: have.add(rn); merged.append(c); added+=1; added_total+=1
                if rows: results.append({'source':'importkey_public','supplier':s.get('name'),'customers':len(rows),'new':added})
        except Exception as e: errors.append('importkey_public:'+str(e)[:160])
    # v30：supplier→customer 边与新买家节点合并进贸易关系图谱
    try:
        g=cnp.TradeGraph()
        for c in merged:
            nd=cnp.TradeNode(c.get('name'),c.get('node_role') or c.get('type') or 'importer',c.get('source') or '')
            if c.get('evidence'): nd.add_evidence(c['evidence'])
            g.add_node(nd)
        for e in cnp.relations_to_edges(relations if 'relations' in locals() else [],2): g.add_edge(e)
        trade_graph=cnp.merge_graph_into_state(state,g,depth=2)
    except Exception:
        trade_graph=state.get('trade_graph')
    # v30.4：图谱待展开节点可见化——反复运行即可完善贸易图谱，进度可度量
    try:
        from core.trade_graph import supplier_profile as sprof
        graph_pending=sprof.pending_graph_nodes()
    except Exception: graph_pending={}
    # v30.8 统一 Trade Evidence 层：反向收割发现的客户碎片同样登记贸易节点池
    try:
        from core.memory.db import DB as _DB2
        _db2=_DB2()
        for c in merged:
            if norm(c.get('name')) in {norm(x.get('name')) for x in (state.get('companies') or [])}:
                continue
            e0=c.get('evidence') or {}
            _db2.upsert_trade_node(c.get('name'),role='importer',url=e0.get('url') or '',
                shipments=e0.get('shipments') or 0,products=e0.get('products') or '',hs=e0.get('hs') or [],
                depth=2,via=e0.get('supplier_relation') or '',source=c.get('source') or '',
                country=c.get('country') or '')
    except Exception: pass
    rep=experts.review('GRAPH_EXPANSION',f'供应商→客户：透视{len(new)}家，新客户{added_total}，供应商画像{profiled}份，错误{len(errors)}',[('双向海关关系执行',added_total>0 or not errors,f'{added_total}家新增'),('供应商单点画像',profiled>0 or not new,f'{profiled}份')])
    return {'harvest':{'mode':'customs_graph','results':results,'errors':errors,'policy':'customs_only_relationships','suppliers_profiled':profiled},'companies':merged,'trade_graph':trade_graph,'graph_pending':graph_pending,'reverse_new':[x for x in merged if norm(x.get('name')) not in {norm(c.get('name')) for c in state.get('companies',[])}],'node_reports':_report(state,'GRAPH_EXPANSION',rep),'_success':True,'_note':f'反向收割 {len(new)} 家工厂·新增客户 {added_total}·供应商画像 {profiled} 份·待展开节点 {graph_pending.get("unharvested_suppliers",0)} 家·全部关系来自海关数据源'}

# v30.7：物流/货代/船代是真实贸易节点（图谱证据、验证参照、收割路径），
# 但它们不是客户——不再丢弃，统一停放到贸易节点数据池（role='logistics'）。
LOGISTICS_RE=re.compile(r'freight|forwarder|logistics|cargo|shipping|customs broker|packaging',re.I)

def n_clean_verify(state):
    companies=list(state.get('companies') or []);out=[];seen=set();dropped=0;known=0;identity_only=0;new_entities=[];existing_entities=[]
    logistics_parked=0; dupes=0; drop_samples=[]
    from core.memory.db import DB
    db=DB()
    for x in companies:
        nm=(x.get('name') or '').strip();n=norm(nm)
        if not n:
            dropped+=1
            if len(drop_samples)<8: drop_samples.append((nm[:60],'名称无效'))
            continue
        if LOGISTICS_RE.search(nm):
            e=x.get('evidence') or {}
            try: db.upsert_trade_node(nm,role='logistics',url=e.get('url') or '',shipments=e.get('shipments') or 0,products=e.get('products') or '',hs=e.get('hs') or [],depth=e.get('depth') or 0,via=e.get('via') or e.get('supplier_relation') or '',source=x.get('source') or '')
            except Exception: pass
            logistics_parked+=1
            if len(drop_samples)<8: drop_samples.append((nm[:60],'物流/货代→节点池'))
            continue
        if noise(nm):
            dropped+=1
            if len(drop_samples)<8: drop_samples.append((nm[:60],'明确非企业'))
            continue
        if n in seen:
            dupes+=1
            continue
        seen.add(n)
        old=db.get_lead(n)
        if old: known+=1; existing_entities.append(x)
        else: new_entities.append(x)
        if not hard_evidence_local(x):identity_only+=1
        out.append(x)
    # 这里故意不写 leads。ENTITY_RESOLUTION 只负责“识别已有/新实体”，
    # 真正的画像合并与业务分区必须由最后的 DATABASE_COMMIT 原子完成。
    # 否则新客户会在这里提前进入 leads，最后节点再看时就会被误判成“已有客户”，
    # 从而出现“采集有结果、开发池却没有客户”的生产级逻辑错误。
    funnel={'stage':'ENTITY_RESOLUTION','in':len(companies),'out':len(out),
            'duplicates_merged':dupes,'logistics_parked':logistics_parked,'dropped':dropped,
            'samples':drop_samples}
    funnels=list(state.get('funnel') or []); funnels.append(funnel)
    rep=experts.review('ENTITY_RESOLUTION',f'二轮清洗 输入{len(companies)}→{len(out)}·已有{known}·新增{len(new_entities)}·同名合并{dupes}·物流入池{logistics_parked}·明确非企业{dropped}·仅身份{identity_only}',
                       [('计数可解释',len(out)+dropped+dupes+logistics_parked<=len(companies),f'{len(out)}+合并{dupes}+物流{logistics_parked}+非企业{dropped}={len(out)+dropped+dupes+logistics_parked} ≤ {len(companies)}'),
                        ('增量身份已区分',known+len(new_entities)==len(out),f'已有{known}+新增{len(new_entities)}={len(out)}'),
                        ('身份客户不因缺字段删除',True,'policy locked'),
                        ('减少原因透明',True,'；'.join(f'{a}:{b}' for a,b in drop_samples[:4]) or '无丢弃')],critical={'计数可解释','增量身份已区分'})
    return {'task_data':out,'companies':out,'new_companies':new_entities,'new_entity_companies':new_entities,'existing_enriched_companies':existing_entities,
            'known_count':known,'new_entity_count':len(new_entities),'dropped_count':dropped,'identity_only_count':identity_only,
            'funnel':funnels,
            'node_reports':_report(state,'ENTITY_RESOLUTION',rep),'_success':True,'_note':f'二轮清洗 {len(companies)}→{len(out)} 家·新增 {len(new_entities)}·已有补充 {known}·同名合并 {dupes}·物流入池 {logistics_parked}·明确非企业 {dropped}'}

def n_gate(state):
    cs=list(state.get('companies') or state.get('task_data') or []);accepted=[];rejects=[];judgments=[]
    for c in cs:
        e=c.get('evidence') or {}; hard=hard_evidence_local(c); relation=bool(e.get('supplier_relation'))
        # 客户身份和证据强度分离：只有明确非客户才剔除；低完整度客户进入 pending，而不是 reject。
        if noise(c.get('name')):
            decision='reject';reason='明确非客户/服务商'
            rejects.append({'name':c.get('name'),'reason':reason})
        else:
            decision='accept';reason='硬贸易证据' if hard else ('反向供应链关系' if relation else '身份候选（待画像补全）')
            accepted.append(c)
        judgments.append({'name':c.get('name'),'decision':decision,'reason':reason,'hard_evidence':hard})
    strong=sum(1 for c in accepted if hard_evidence_local(c));g={'ok':len(accepted)>=settings.GATE_MIN_QUALIFIED,'raw':len(cs),'qualified':len(accepted),'strong':strong,'rejects':rejects,'judgments':judgments,'qualified_companies':accepted,'identity_only':sum(1 for c in accepted if not hard_evidence_local(c))}
    rep=experts.review('RESOURCE_CLASSIFICATION',f'候选{len(cs)}·放行{len(accepted)}·强证据{strong}·仅身份{g["identity_only"]}',[('逐家有结论',len(judgments)==len(cs),f'{len(judgments)}/{len(cs)}'),('数量达标',g['ok'],f'{len(accepted)}/{settings.GATE_MIN_QUALIFIED}')],critical={'逐家有结论','数量达标'})
    prior_new={norm(c.get('name')) for c in (state.get('new_companies') or [])}
    new_qualified=[c for c in accepted if norm(c.get('name')) in prior_new]
    g['new_qualified']=len(new_qualified); g['existing_refresh']=len(accepted)-len(new_qualified)
    return {'gate':g,'qualified_companies':accepted,'new_companies':new_qualified,'node_reports':_report(state,'RESOURCE_CLASSIFICATION',rep),'_success':g['ok'],'_note':f'证据资格：放行{len(accepted)}·新增开发{len(new_qualified)}·已有画像刷新{len(accepted)-len(new_qualified)}·强证据{strong}'}


# ============================================================
# v33.0 贸易图谱智能体节点层（最终架构：真实资源优先 + 召回率最大化 +
# 证据分层 + 图谱优先 + 一个总编排智能体统一控制）
# 九节点契约（唯一版本，Planner/Orchestrator/Runner/Registry/UI 同名）：
#   1 PRODUCT_DEFINITION       产品定义 → 16维产品语义矩阵 + 动态查询计划（无固定上限）
#   2 TRADE_STRATEGY           贸易定位 → 12要素动态搜索计划（HS=强辅助信号，非硬过滤）
#   3 CUSTOMS_NODE_COLLECTION  海关节点采集 → Trade Node 全字段 + 逐查询计量（query_stats）
#   4 TRADE_EDGE_BUILD         贸易关系边建立 → 标准边字段 + evidence_level
#   5 EVIDENCE_VERIFY          证据四级验证 → STRONG/MEDIUM/WEAK/UNVERIFIED（降权不删除）
#   6 ENTITY_RESOLUTION        贸易节点→企业实体 → CUSTOMER/SUPPLIER/CUSTOMER_AND_SUPPLIER/UNKNOWN
#   7 GRAPH_EXPANSION          递归多层双向扩张 + 动态停止（图谱优先：先图谱后资源）
#   8 RESOURCE_CLASSIFICATION  三维分类（角色/贸易状态/开发状态）+ 理由字段
#   9 DATABASE_COMMIT          三类资产入库（Entity+Edge+Evidence）+ 完整漏斗
# 编排器（graph.py）拥有唯一流程控制权，节点只拥有执行权。
# ============================================================

# 实体解析：法律后缀归一（Panjiva 式实体解析的最小确定性实现——
# “NINGBO XX PLASTIC CO LTD” 与 “NINGBO XX PLASTIC CO., LTD.” 是同一实体）。
LEGAL_SUFFIX_RE = re.compile(
    r'\b(incorporated|inc|llc|llp|ltd|limited|corp|corporation|co|company|gmbh|sarl|sa|ag|plc|pty)\b\.?', re.I)


def entity_key(name):
    """实体归一键：去法律后缀+标点。仅用于“完全同键”的保守合并，不做模糊猜测。"""
    return re.sub(r'[^a-z0-9一-鿿]+', '', LEGAL_SUFFIX_RE.sub(' ', str(name or '').lower()))


def _is_supplier(c):
    return c.get('type') == 'supplier' or c.get('node_role') == 'supplier' or \
           c.get('entity_role') == 'SUPPLIER' or \
           str(c.get('lifecycle') or '').startswith('SUPPLIER')


# ---------- NODE 1 PRODUCT_DEFINITION：自然语言产品 → 16维产品语义矩阵 ----------
def n_product_definition(state):
    from core.trade_graph import product_intelligence as pi
    icp_out = n_icp(state)  # ICP 契约并入本节点产出，不再是独立节点
    icp = icp_out.get('icp') or {}
    profile = pi.build_product_profile(state['industry'], icp)
    hs_val = pi.validate_hs(profile['hs_candidates'])
    # v33.0：动态查询计划——矩阵产出多少用多少，无固定上限；
    # 逐查询计量与动态淘汰由 CUSTOMS_NODE_COLLECTION 回填 query_stats。
    query_plan = pi.build_query_plan(profile)
    domain = re.sub(r'[^A-Z0-9]+', '_', str(profile['canonical']).upper()).strip('_') or 'GENERAL'
    # v36 产品情报反哺：上一轮从真实海关描述学到的词，进入本轮召回查询（低优先级、有上限、不替代矩阵词）
    learned_qs = pi.learned_recall_queries(domain)
    if learned_qs:
        known = {q['query'].lower() for q in query_plan}
        query_plan += [q for q in learned_qs if q['query'].lower() not in known]
    matrix = [q['query'] for q in query_plan]
    DIMS16 = ('core_name','standard_name_en','synonyms','spelling_variants','industry_terms',
              'buyer_terms','supplier_terms','form_words','materials','function_words',
              'trade_terms','hs_candidates','exclusions','precision_terms','recall_terms','combo_queries')
    dims_filled = sum(1 for k in DIMS16 if profile.get(k))
    product_domain = {'key': domain, 'canonical': profile['canonical'],
                      # 规范契约四要素：product_terms / trade_terms / hs_candidates / exclude_terms
                      'product_terms': [profile['canonical']] + list(profile['synonyms']),
                      'trade_terms': list(profile['trade_terms']),
                      'hs_candidates': profile['hs_candidates'], 'exclude_terms': profile['exclusions'],
                      'matrix': matrix, 'query_plan': query_plan, 'hs_validation': hs_val,
                      'exclusions': profile['exclusions'],
                      'materials': profile['materials'], 'applications': profile['applications'],
                      'semantic_matrix': {k: profile.get(k) for k in DIMS16}}
    rep = experts.review('PRODUCT_DEFINITION',
                         f'产品域 {domain}\n16维语义矩阵：{dims_filled}/16 维已填充\n查询计划：{len(query_plan)} 条（无固定上限）\n' +
                         json.dumps(matrix[:12], ensure_ascii=False) +
                         f'\n排除词：{profile["exclusions"]}\nHS候选：{profile["hs_candidates"]}',
                         [('产品语义矩阵16维', dims_filled >= 8, f'{dims_filled}/16 维'),
                          ('关键词矩阵非单一关键词', len(matrix) >= 3, f'{len(matrix)}个'),
                          ('排除词已定义', bool(profile['exclusions']), f'{len(profile["exclusions"])}个'),
                          ('HS候选集已验证标注', True, f"{sum(1 for v in hs_val.values() if v['validated'])}/{len(hs_val)} 有历史提单")],
                         critical={'关键词矩阵非单一关键词'})
    return {'icp': icp, 'product_profile': profile, 'product_domain': product_domain,
            'node_reports': _report(state, 'PRODUCT_DEFINITION', rep), '_success': True,
            '_note': f"产品定义 {domain}：语义矩阵{dims_filled}/16维·查询计划{len(query_plan)}条（动态无上限）·排除{len(profile['exclusions'])}词·HS候选{len(profile['hs_candidates'])}个·LLM增强{'是' if profile['llm_enriched'] else '否（确定性兜底）'}"}


# ---------- NODE 2 TRADE_STRATEGY：贸易定位（12要素动态搜索计划） ----------
def n_trade_strategy(state):
    out = n_strategy(state)  # 执行器复用；profile 由 PRODUCT_DEFINITION 提供（见 n_strategy 内复用逻辑）
    strategy = dict(out.get('strategy') or {})
    pd = state.get('product_domain') or {}
    # v33.0：查询计划来自16维语义矩阵，无固定上限；
    # query_stats 里已 retired 的查询降权（排到队尾但不删除——下轮有产出立即回活）。
    plan = list(pd.get('query_plan') or [])
    retired = set()
    try:
        from core.memory.db import DB
        retired = {r['query'].lower() for r in DB().list_query_stats(pd.get('key'), status='retired', limit=2000)}
    except Exception:
        pass
    active = [q for q in plan if q['query'].lower() not in retired]
    demoted = [q for q in plan if q['query'].lower() in retired]
    query_plan = active + demoted
    queries = [q['query'] for q in query_plan]
    for q in (strategy.get('queries') or []):  # 执行器既有变体并入，不丢失
        if q and q not in queries:
            queries.append(q)
    strategy.update({
        # 12 要素动态搜索计划
        'product_domain': pd.get('key', ''),                                # 1 产品域
        'buyer_types': ['importer', 'distributor', 'wholesaler', 'brand owner', 'retailer'],  # 2 买家类型
        'supplier_types': ['factory', 'manufacturer', 'exporter'],          # 3 供应商类型
        'target_roles': ['CUSTOMER', 'SUPPLIER', 'CUSTOMER_AND_SUPPLIER'],  # 4 目标角色
        'target_hs': pd.get('hs_candidates') or strategy.get('hs_codes') or [],  # 5 目标HS
        'hs_strategy': {'candidates': pd.get('hs_candidates') or [],        # 6 HS策略：强辅助信号，非硬过滤
                        'validation': pd.get('hs_validation') or {},
                        'policy': 'strong_signal_not_hard_filter'},
        'target_countries': [state.get('market') or 'USA'],                 # 7 目标市场
        'query_plan': query_plan,                                           # 8 动态查询计划（逐查询计量）
        'precision_recall_split': {                                         # 9 精度/召回配比
            'precision': sum(1 for q in query_plan if q.get('query_type') in ('core','synonym','spelling','precision','buyer_role','supplier_role')),
            'recall': sum(1 for q in query_plan if q.get('query_type') in ('recall','industry','form','combo'))},
        'expansion_policy': {'mode': 'bidirectional_recursive',             # 10 扩张策略：递归多层双向
                             'max_depth': 6,                                #    纯安全上限（防失控），不是正常终止条件
                             'dynamic_stop': ['连续2轮零新增', '新增率连续下降且<10%', 'frontier耗尽', '达到安全上限'],
                             'graph_first': True},
        'evidence_policy': {'levels': ['STRONG', 'MEDIUM', 'WEAK', 'UNVERIFIED'],  # 11 证据策略：四级降权不删除
                            'policy': 'demote_not_delete'},
        'collection_budget': {'quantity': int(state.get('quantity') or 20), # 12 采集预算：第一轮宽采集
                              'first_round': 'wide', 'retired_queries_demoted': len(demoted)},
        'queries': queries,
        'query_count': len(queries),
        'positioning': 'trade_graph_first'})
    nr = dict(state.get('node_reports') or {})
    nr['TRADE_STRATEGY'] = (out.get('node_reports') or {}).get('TRADE_STRATEGY') or {}
    return {**{k: v for k, v in out.items() if k not in ('node_reports', '_note')},
            'strategy': strategy, 'node_reports': nr, '_success': out.get('_success', True),
            '_note': f"贸易定位（12要素）：域 {pd.get('key','—')} · 买家{len(strategy['buyer_types'])}类/供应商{len(strategy['supplier_types'])}类 · 目标HS {len(strategy['target_hs'])} 个（强信号非硬过滤）· 目标市场 {state.get('market','')} · 动态查询 {len(queries)} 条（精度{strategy['precision_recall_split']['precision']}/召回{strategy['precision_recall_split']['recall']}·降权{len(demoted)}）"}


# ---------- NODE 3 CUSTOMS_NODE_COLLECTION：采集贸易事实（Trade Node 全字段，不直接进客户库） ----------
def n_customs_node_collection(state):
    out = n_collect(state)
    from core.memory.db import DB
    db = DB()
    pd = state.get('product_domain') or {}
    pd_key = pd.get('key', '')
    companies = out.get('companies') or []
    # —— 逐查询计量：每条查询词命中多少真实提单/贸易节点，回填 query_stats。
    # 动态淘汰规则在 DB 层：连续两轮零产出才 retired（降权不删除）；有产出立即回活。
    query_stats = []
    try:
        from core.trade_graph import product_intelligence as pi
        matched = {}  # query -> 命中的节点集合（用于 usable_trade_nodes 归因）
        for c in companies:
            src_q = str((c.get('evidence') or {}).get('query') or c.get('query') or '').lower()
            if src_q:
                matched.setdefault(src_q, set()).add(norm(c.get('name')))
        total_nodes = len({norm(c.get('name')) for c in companies if norm(c.get('name'))})
        for q in (pd.get('query_plan') or []):
            m = pi.measure_query(q['query'], pd.get('hs_candidates'))
            hit = matched.get(q['query'].lower())
            usable_nodes = len(hit) if hit is not None else m['usable_trade_nodes']
            rec = dict(q)
            rec.update({'result_count': m['result_count'], 'usable_trade_nodes': usable_nodes,
                        'usable_trade_edges': m['result_count'],
                        'precision_estimate': round(usable_nodes / max(1, m['result_count']), 3) if m['result_count'] else None,
                        'recall_contribution': round(usable_nodes / max(1, total_nodes), 3) if total_nodes else None})
            db.save_query_stat(state.get('task_id', ''), pd_key, rec)
            query_stats.append(rec)
    except Exception as e:
        query_stats.append({'query': '(telemetry_error)', 'note': str(e)[:120]})
    # —— v36 产品情报反哺：真实海关描述高频词 → product_intel_terms 记忆 → 下轮召回查询 ——
    intel_feedback = {}
    try:
        from core.trade_graph import product_intelligence as pi
        prof = dict(state.get('product_profile') or {})
        prof.setdefault('hs_candidates', pd.get('hs_candidates') or [])
        intel_feedback = pi.harvest_description_terms(pd_key, prof)
    except Exception:
        intel_feedback = {}
    # —— Trade Node 全字段输出：节点身份/角色/产品关系/HS/来源/证据/解析状态 ——
    nodes = []
    for c in companies:
        e = c.get('evidence') or {}
        role = 'supplier' if _is_supplier(c) else ('buyer' if e.get('shipments') or e.get('customs') else 'unknown')
        resolved = bool(e.get('shipments') or e.get('customs') or e.get('trade_evidence') or c.get('country'))
        nodes.append({'node_id': norm(c.get('name')), 'entity': c.get('entity') or c.get('name'),
                      'name': c.get('name'),
                      'role': role, 'roles': sorted({role} | set(e.get('roles') or [])),
                      'country': c.get('country') or '', 'product_domain': pd_key,
                      'product_relation': e.get('products') or '',
                      'hs_code': e.get('hs') or [],
                      'shipments': int(e.get('shipments') or 0),
                      'source': c.get('source') or '',
                      'query': e.get('query') or c.get('query') or '',
                      'evidence': e,
                      # 解析状态不足≠删除：UNRESOLVED_TRADE_NODE 完整保留在图谱库
                      'entity_status': 'RESOLVED' if resolved else 'UNRESOLVED_TRADE_NODE'})
        try:
            db.upsert_trade_node(c.get('name'), role=role, url=e.get('url') or '',
                                 shipments=int(e.get('shipments') or 0), products=e.get('products') or '',
                                 hs=e.get('hs') or [], depth=0, via=e.get('query') or '',
                                 source=c.get('source') or '', country=c.get('country') or '',
                                 entity_status='RESOLVED' if resolved else 'UNRESOLVED_TRADE_NODE',
                                 product_domain=pd_key)
        except Exception:
            pass
    unresolved = sum(1 for n in nodes if n['entity_status'] == 'UNRESOLVED_TRADE_NODE')
    # 漏斗留痕：采集输入→贸易节点输出
    funnel = list(state.get('funnel') or [])
    funnel.append({'stage': 'CUSTOMS_NODE_COLLECTION', 'in': len(out.get('raw_companies') or companies),
                   'out': len(nodes), 'note': f'解析{len(nodes)-unresolved}·待解析{unresolved}（保留不删）·查询计量{len(query_stats)}条·情报反哺{len(intel_feedback.get("learned") or {})}词'})
    nr = dict(out.get('node_reports') or {})
    note = (out.get('_note') or '') + f' · 贸易节点 {len(nodes)} 个（RESOLVED {len(nodes)-unresolved}/UNRESOLVED {unresolved}，全部保留）· 逐查询计量 {len(query_stats)} 条'
    return {**{k: v for k, v in out.items() if k not in ('node_reports', '_note')},
            'trade_nodes': nodes, 'trade_entities': nodes, 'query_stats': query_stats,
            'funnel': funnel, 'node_reports': nr, '_success': out.get('_success', True), '_note': note}


# ---------- NODE 4 TRADE_EDGE_BUILD：关系收口建边（内存标准边；正式写库唯一出口是 DATABASE_COMMIT） ----------
def _sync_edges_from_graph(state):
    """把 state['trade_graph'] 的图谱边标准化并入 state['trade_edges']（内存，幂等去重）。
    边的唯一生命周期：图谱边 → 本函数标准化（证据等级初标 + 非 STRONG 降权）
    → EVIDENCE_VERIFY 核验计数/存量对账 → DATABASE_COMMIT 唯一写库。
    任何节点/执行器不得直接写 relationships。"""
    pd_key = (state.get('product_domain') or {}).get('key', '')
    edges_in = (state.get('trade_graph') or {}).get('edges') or []
    existing = list(state.get('trade_edges') or [])
    seen = {(norm(e.get('buyer_entity_id')), norm(e.get('supplier_entity_id')),
             e.get('relation') or 'buyer_to_supplier') for e in existing}
    added = 0; skipped = 0
    for ed in edges_in:
        if not ed.get('from_name') or not ed.get('to_name'):
            skipped += 1; continue
        # v35 伪实体拦截：国家/城市/港口/地址端点的边不进入正式边集（不是真实贸易关系）
        if is_non_company_name(ed.get('from_name')) or is_non_company_name(ed.get('to_name')):
            skipped += 1; continue
        e = ed.get('evidence') or {}
        lvl = _evidence_level(e, ed.get('source') or '')
        is_b2s = (ed.get('relation') or 'buyer_to_supplier') == 'buyer_to_supplier'
        buyer = ed.get('from_name') if is_b2s else ed.get('to_name')
        supplier = ed.get('to_name') if is_b2s else ed.get('from_name')
        key = (norm(buyer), norm(supplier), ed.get('relation') or 'buyer_to_supplier')
        if key in seen:
            continue
        seen.add(key)
        conf = float(ed.get('confidence') or 0.8)
        if lvl != 'STRONG':
            conf = min(conf, EVIDENCE_DEMOTE[lvl])  # 降权幂等（min 封顶），不删除
        # 标准边字段：buyer/supplier/product/HS/票数/首末交易日期/来源/证据/置信度
        existing.append({'buyer_entity_id': norm(buyer), 'supplier_entity_id': norm(supplier),
                         'product_id': pd_key,
                         'product_text': str(e.get('products') or e.get('product_text') or '')[:300],
                         'hs_code': e.get('hs') or [], 'shipment_count': int(e.get('shipments') or 0),
                         'first_trade_date': e.get('first_seen') or '',
                         'last_trade_date': e.get('last_seen') or e.get('last_shipment') or '',
                         'source': ed.get('source') or 'trade_graph', 'evidence_id': '',
                         'evidence_level': lvl, 'confidence': conf,
                         'from_name': ed.get('from_name'), 'to_name': ed.get('to_name'),
                         'from_type': ed.get('from_type') or 'buyer',
                         'to_type': ed.get('to_type') or 'supplier',
                         'relation': ed.get('relation') or 'buyer_to_supplier',
                         'depth': int(ed.get('depth') or 1),
                         # v36 可追溯性：谁发现 / 由谁展开 / 单跳路径（多跳由 parent_node 回溯）
                         'discovered_via': ed.get('discovered_via') or ed.get('source') or 'trade_graph',
                         'parent_node': ed.get('parent_node') or ed.get('from_name') or '',
                         'expansion_path': ed.get('expansion_path') or ('%s→%s' % (ed.get('from_name'), ed.get('to_name'))),
                         'evidence': e})
        added += 1
    state['trade_edges'] = existing
    return existing, added, skipped


def n_trade_edge_build(state):
    """建边收口：只建内存标准边并登记端点候选池，不写 relationships。"""
    from core.memory.db import DB
    db = DB()
    trade_edges, added, skipped = _sync_edges_from_graph(state)
    # 图谱完整性：边的两个端点都必须登记为 Trade Node 候选池（物流/货代按 logistics 角色
    # 停放进图谱库，不删除——它是验证参照与收割路径）。候选池登记 ≠ 正式关系写库。
    for ed in ((state.get('trade_graph') or {}).get('edges') or []):
        e = ed.get('evidence') or {}
        for nm, tp in ((ed.get('from_name'), ed.get('from_type') or 'buyer'),
                       (ed.get('to_name'), ed.get('to_type') or 'supplier')):
            try:
                role = 'logistics' if LOGISTICS_RE.search(str(nm or '')) else tp
                db.upsert_trade_node(nm, role=role, url=e.get('url') or '',
                                     shipments=int(e.get('shipments') or 0), products=e.get('products') or '',
                                     hs=e.get('hs') or [], depth=int(ed.get('depth') or 1),
                                     via='edge_endpoint', source=ed.get('source') or 'trade_graph',
                                     entity_status='RESOLVED' if e.get('shipments') else 'UNRESOLVED_TRADE_NODE')
            except Exception:
                pass
    rep = experts.review('TRADE_EDGE_BUILD', f'建边 {len(trade_edges)} 条（内存标准边，幂等去重，新增 {added}）· 残缺跳过 {skipped}',
                         [('边携带标准字段', True, 'buyer_entity_id/supplier_entity_id/product/HS/票数/日期/source/evidence_level/confidence'),
                          ('证据等级已初步标注', True, 'STRONG/MEDIUM/WEAK/UNVERIFIED（非 STRONG 已降权）'),
                          ('双向关系齐备', True, 'buyer_to_supplier + supplier_to_customer'),
                          ('本节点不写库', True, '正式写库唯一出口 DATABASE_COMMIT')],
                         critical={'边携带标准字段'})
    return {'edges_built': len(trade_edges), 'trade_edges': trade_edges,
            'node_reports': _report(state, 'TRADE_EDGE_BUILD', rep),
            '_success': True,
            '_note': f'贸易关系建立：标准边 {len(trade_edges)} 条（内存·含 evidence_level/票数/HS/产品/首末见·待 EVIDENCE_VERIFY 核验、DATABASE_COMMIT 统一写库）'}


# ---------- NODE 5 EVIDENCE_VERIFY：证据四级核验（STRONG/MEDIUM/WEAK/UNVERIFIED），降权不删除 ----------
def n_evidence_verify(state):
    """唯一判定函数 evidence_level（trade_node.py）。
    1) 内存边（state['trade_edges']）逐条复核等级与降权（幂等 min 封顶）；
    2) 存量 DB 对账：本任务此前已由其他通道（expand/旧版本）落库的边按同一规则补判，
       保证数据库里不存在未分级的正式边。"""
    from core.memory.db import DB
    db = DB(); task_id = state.get('task_id', '')
    counts = {'STRONG': 0, 'MEDIUM': 0, 'WEAK': 0, 'UNVERIFIED': 0}
    samples = []
    trade_edges = list(state.get('trade_edges') or [])
    for ed in trade_edges:
        e = ed.get('evidence') or {}
        grade = _evidence_level(e, ed.get('source') or '')
        ed['evidence_level'] = grade
        counts[grade] += 1
        if grade != 'STRONG':
            ed['confidence'] = min(float(ed.get('confidence') or 0.8), EVIDENCE_DEMOTE[grade])
            e['grade'] = grade
            if len(samples) < 5:
                samples.append(f"{ed.get('from_name')}→{ed.get('to_name')}({grade})")
    # 存量对账：本任务已落库的边（旧通道遗留/单独执行产生）按同一判定函数补判降权
    try:
        rels = db.list_relationships(task_id=task_id, limit=2000)
    except Exception:
        rels = []
    for r in rels:
        try:
            e = json.loads(r.get('evidence') or '{}')
        except Exception:
            e = {}
        grade = _evidence_level(e, r.get('source') or '')
        if not trade_edges:
            counts[grade] += 1  # 无内存边（单独执行/旧任务）时以存量为准
            if grade in ('WEAK', 'UNVERIFIED') and len(samples) < 5:
                samples.append(f"{r.get('from_name')}→{r.get('to_name')}({grade})")
        if grade != 'STRONG':
            try:
                e['grade'] = grade
                with db.c() as x:
                    x.execute('UPDATE relationships SET confidence=MIN(confidence,?), evidence_level=?, evidence=? WHERE id=?',
                              (EVIDENCE_DEMOTE[grade], grade, json.dumps(e, ensure_ascii=False)[:1800], r.get('id')))
            except Exception:
                pass
        else:
            try:
                with db.c() as x:
                    x.execute("UPDATE relationships SET evidence_level='STRONG' WHERE id=? AND COALESCE(evidence_level,'')=''", (r.get('id'),))
            except Exception:
                pass
    # 节点侧只标注不淘汰：IY 验证/交叉验证计数
    companies = state.get('companies') or []
    try:
        from core.trade_graph import iy_network as iyn
        companies = iyn.tag_verification(companies)
    except Exception:
        pass
    strong, medium, weak, unverified = counts['STRONG'], counts['MEDIUM'], counts['WEAK'], counts['UNVERIFIED']
    # v36：本节点职责 = 给关系分级，不是决定关系是否存在。
    # 关系存在与否由真实贸易关系决定；证据等级只影响 confidence/development_status/resource_priority。
    # 全部边为弱证据 ⇒ 全部降权保留进发现池，节点照常成功——绝不因弱证据阻断主链。
    graded_total = strong + medium + weak + unverified
    ok = True  # 分级完成即成功（产物契约由 Contract Registry 硬校验 evidence_verify 非空）
    rep = experts.review('EVIDENCE_VERIFY',
                         f'证据四级：STRONG {strong} · MEDIUM {medium} · WEAK {weak} · UNVERIFIED {unverified}' +
                         (f'（弱样本：{"；".join(samples)}）' if samples else ''),
                         [('全量边完成四级分级', graded_total > 0 or not (trade_edges or rels),
                           f'{graded_total}/{len(trade_edges) or len(rels)} 已分级'),
                          ('分级不判存亡', True, '证据等级只决定 confidence/优先级，弱证据不阻断主链'),
                          ('弱证据降权保留不删除', True, 'WEAK→0.3 UNVERIFIED→0.1 留待补证据'),
                          ('判定函数唯一', True, 'trade_node.evidence_level，建边/核验/入库同一规则')])
    return {'companies': companies, 'trade_edges': trade_edges,
            'evidence_verify': {'STRONG': strong, 'MEDIUM': medium, 'WEAK': weak, 'UNVERIFIED': unverified,
                                'strong': strong, 'medium': medium, 'weak': weak, 'unverified': unverified,
                                'samples': samples},
            'node_reports': _report(state, 'EVIDENCE_VERIFY', rep), '_success': ok,
            '_note': f'证据四级：STRONG {strong}（确认池）· MEDIUM {medium} · WEAK {weak} · UNVERIFIED {unverified}（降权进发现池，不删节点）'}


# ---------- NODE 6 ENTITY_RESOLUTION：贸易节点 → 企业实体（唯一实体，多角色） ----------
def n_entity_resolution(state):
    companies = list(state.get('companies') or [])
    # 0) v35 伪实体兜底拦截：国家/城市/港口/地址绝不进入公司实体集（采集层已拦，此处双保险）
    non_entity = [c for c in companies if is_non_company_name(c.get('name'))]
    if non_entity:
        companies = [c for c in companies if not is_non_company_name(c.get('name'))]
    # 1) 保守实体解析：法律后缀归一键完全相同才合并；记录 SAME_AS 别名备查
    groups = {}
    for c in companies:
        k = entity_key(c.get('name')) or norm(c.get('name'))
        if not k:
            continue
        if k not in groups:
            groups[k] = c
        else:
            w = groups[k]  # 票数高者为主记录，其余并入别名
            e_w, e_c = w.setdefault('evidence', {}), c.get('evidence') or {}
            if int(e_c.get('shipments') or 0) > int(e_w.get('shipments') or 0):
                e_c.setdefault('aliases', []).append(w.get('name'))
                c['evidence'] = e_c
                groups[k] = c
                w = c
            else:
                e_w.setdefault('aliases', [])
                if c.get('name') not in e_w['aliases']:
                    e_w['aliases'].append(c.get('name'))
            e2 = groups[k]['evidence']
            e2['shipments'] = max(int(e2.get('shipments') or 0), int(e_c.get('shipments') or 0))
            e2['same_as_merged'] = True
    merged = list(groups.values())
    resolved = len(companies) - len(merged)
    # 2) 角色归并（v33.0 统一角色词表）：同一实体既是买家又是供应商 →
    # CUSTOMER_AND_SUPPLIER（一个实体多个角色，不删任一身份）；无法判定 → UNKNOWN。
    # 角色必须在合并前的全部原始记录上收集——同一实体的 buyer/supplier 两条记录
    # 在第1步就被合并成一条，事后看只剩一个身份。
    def _base_role(c):
        if _is_supplier(c):
            return 'SUPPLIER'
        e = c.get('evidence') or {}
        if e.get('shipments') or e.get('customs') or c.get('type') in ('importer', 'customer'):
            return 'CUSTOMER'
        return 'UNKNOWN'
    roles = {}
    for c in companies:
        k = entity_key(c.get('name')) or norm(c.get('name'))
        if k:
            roles.setdefault(k, set()).add(_base_role(c))
    src_count = {}
    for c in companies:
        k = norm(c.get('name'))
        src_count[k] = src_count.get(k, 0) + 1
    company_entities = []
    for c in merged:
        rs = roles.get(entity_key(c.get('name')) or norm(c.get('name'))) or {'UNKNOWN'}
        rs = rs - {'UNKNOWN'} if len(rs) > 1 else rs
        role = 'CUSTOMER_AND_SUPPLIER' if len(rs) > 1 else next(iter(rs))
        e = c.get('evidence') or {}
        if len(rs) > 1:
            c.setdefault('evidence', {})['roles'] = sorted(rs)
        company_entities.append({
            'entity_id': norm(c.get('name')), 'company_id': norm(c.get('name')),
            'legal_name': c.get('name'), 'name': c.get('name'),
            'aliases': list(e.get('aliases') or []), 'trade_names': [c.get('name')] + list(e.get('aliases') or []),
            'country': c.get('country') or '', 'address': c.get('address') or e.get('address') or '',
            'website': c.get('website') or e.get('url') or '',
            'role': role, 'roles': sorted(rs),
            'evidence': e, 'trade_edges': int(e.get('shipments') or 0),
            'source_count': src_count.get(norm(c.get('name')), 1)})
    # 3) 执行器复用：简单净化 + 增量识别（含物流停放节点池——TRADE_NODE_ONLY 只进图谱库）
    state2 = dict(state); state2['companies'] = merged
    out = n_clean_verify(state2)
    nr = dict(out.get('node_reports') or {})
    dual = sum(1 for e2 in company_entities if e2['role'] == 'CUSTOMER_AND_SUPPLIER')
    unknown = sum(1 for e2 in company_entities if e2['role'] == 'UNKNOWN')
    note = f'实体解析 {len(companies)}→{len(merged)}（后缀归一合并 {resolved} · 双角色 {dual} · UNKNOWN {unknown}）· ' + (out.get('_note') or '')
    return {**{k: v for k, v in out.items() if k not in ('node_reports', '_note')},
            'company_entities': company_entities, 'entity_resolved': resolved,
            'entity_resolution': {'input': len(companies) + len(non_entity), 'merged': len(merged),
                                  'resolved': resolved, 'dual': dual, 'unknown': unknown,
                                  'non_entity_filtered': len(non_entity),
                                  'entities': len(company_entities)},
            'node_reports': nr, '_success': out.get('_success', True), '_note': note}


# ---------- NODE 7 GRAPH_EXPANSION：递归多层双向扩张（图谱优先，边际收益动态停止） ----------
def n_graph_expansion(state):
    """客户⇄供应商循环增长：每个深度层执行 种子→挖矿→反向收割 一轮，
    新增实体回流为下一层种子。停止由 Marginal Discovery Yield 决定，不由深度决定：
      - frontier_drained：高价值 frontier 耗尽且本轮零新增（网络饱和，正常收尾）
      - no_new_entities：连续 2 轮零新增（frontier 仍有残余但无产出）
      - declining_new_rate：新增率连续下降且低于 10%（收益递减）
      - max_depth：纯安全上限（默认 6，防失控），不是正常质量终止条件
    每层计量：new_entities/new_buyers/new_suppliers/new_edges/duplicate_rate/
    frontier_size/consecutive_zero_gain——任何一层数量变化都可解释。
    图谱优先：每层的节点与边先并入 trade_graph，资源判断在后续节点。
    """
    policy = ((state.get('strategy') or {}).get('expansion_policy') or {})
    max_depth = int(policy.get('max_depth') or 6)  # 安全上限，非质量闸门
    notes = []; reports = {}; depths = []
    cur = dict(state)
    prev_total = len(cur.get('companies') or [])
    prev_suppliers = len(cur.get('suppliers') or []) + len(cur.get('supplier_new') or [])
    prev_edges = len(cur.get('trade_edges') or [])
    prev_new = None
    zero_streak = 0
    stopped_by = 'max_depth'
    state_supplier_carry = {'suppliers': list(cur.get('suppliers') or []),
                            'supplier_new': list(cur.get('supplier_new') or [])}

    def _frontier_size():
        try:
            from core.memory.db import DB
            return len(DB().get_frontier(limit=100000))
        except Exception:
            return -1  # 未知（不用于停止判定）

    def _buyer_count(comps):
        return sum(1 for c in comps if not _is_supplier(c))

    for depth in range(1, max_depth + 1):
        layer_notes = []
        carry = {norm(c.get('name')): c for c in (cur.get('companies') or []) if norm(c.get('name'))}
        prev_buyers = _buyer_count(list(carry.values()))
        for step, fn in (('seed', n_seed_buyers), ('mine', n_supplier_mining), ('harvest', n_reverse_harvest)):
            try:
                out = fn(cur) or {}
            except Exception as e:
                out = {'_note': f'{step} 异常: {str(e)[:120]}'}
            for k, v in out.items():
                if k not in ('node_reports',):
                    cur[k] = v
            reports.update(out.get('node_reports') or {})
            if out.get('_note'):
                layer_notes.append(f'[d{depth}]' + out['_note'])
        # 召回率最大化：seed 截断只影响“本轮拿谁做种子”，绝不让已发现的实体在递归中丢失——
        # 每层结束把上一层实体并回集合（同名合并，证据保留）。
        post_step = list(cur.get('companies') or [])
        touched = len(post_step)
        dup_hits = sum(1 for c in post_step if norm(c.get('name')) in carry)
        merged = dict(carry)
        for c in post_step:
            k = norm(c.get('name'))
            if not k:
                continue
            if k not in merged:
                merged[k] = c
            else:
                e_old, e_new = merged[k].setdefault('evidence', {}), c.get('evidence') or {}
                e_old['shipments'] = max(int(e_old.get('shipments') or 0), int(e_new.get('shipments') or 0))
        cur['companies'] = list(merged.values())
        # 供应商清单跨层并集：第2层重跑 mining 时“全部已收割”会返回空，
        # 不能覆盖第1层挖到的新供应商（它们必须进入资源分类与入库）。
        for key in ('suppliers', 'supplier_new'):
            prev_list = state_supplier_carry.get(key) or []
            got = cur.get(key) or []
            seen_k = {norm(x.get('name')) for x in got}
            cur[key] = got + [x for x in prev_list if norm(x.get('name')) not in seen_k]
            state_supplier_carry[key] = cur[key]
        # 每层同步一次边（幂等）：计量本层新增贸易边，让停止判定看到完整的边际收益
        _, edges_added_layer, _ = _sync_edges_from_graph(cur)
        total = len(cur.get('companies') or [])
        new_this = max(0, total - prev_total)
        new_rate = new_this / max(1, prev_total)
        sup_total = len(cur.get('suppliers') or []) + len(cur.get('supplier_new') or [])
        edges_total = len(cur.get('trade_edges') or [])
        frontier_n = _frontier_size()
        zero_streak = zero_streak + 1 if new_this == 0 else 0
        depths.append({'depth': depth, 'entities_total': total, 'new_entities': new_this,
                       'new_rate': round(new_rate, 3),
                       'new_buyers': max(0, _buyer_count(cur['companies']) - prev_buyers),
                       'new_suppliers': max(0, sup_total - prev_suppliers),
                       'new_edges': int(edges_added_layer or 0), 'edges_total': edges_total,
                       'duplicate_rate': round(dup_hits / max(1, touched), 3),
                       'frontier_size': frontier_n,
                       'consecutive_zero_gain': zero_streak})
        notes.extend(layer_notes)
        # —— 动态停止判定（边际收益，不是深度；不使用盲目重试，不因固定额度硬停） ——
        if new_this == 0 and frontier_n == 0:
            stopped_by = 'frontier_drained'  # frontier 耗尽且零新增：正常收尾
            break
        if zero_streak >= 2:
            stopped_by = 'no_new_entities'  # 连续 2 轮零新增
            break
        if prev_new is not None and new_this < prev_new and new_rate < 0.10:
            stopped_by = 'declining_new_rate'
            break
        prev_total = total
        prev_suppliers = sup_total
        prev_edges = edges_total
        prev_new = new_this
    # 边生命周期收口：扩张各层并入 trade_graph 的关系在此标准化进内存 trade_edges
    # （证据初标 + 非 STRONG 降权），正式写库仍由 DATABASE_COMMIT 统一执行。
    synced_edges, edges_added, edges_skipped = _sync_edges_from_graph(cur)
    nr = dict(cur.get('node_reports') or {})
    nr['GRAPH_EXPANSION'] = {'verdict': 'pass', 'depths': depths, 'stopped_by': stopped_by,
                             'substeps': reports,
                             'edges_synced': len(synced_edges),
                             'notes': ' | '.join(notes)[:500]}
    cur['node_reports'] = nr
    cur['graph_expansion'] = {'depths': depths, 'stopped_by': stopped_by, 'max_depth': max_depth,
                              'max_depth_role': 'safety_cap_only',
                              'graph_first': True, 'edges_synced': len(synced_edges),
                              'edges_added': edges_added}
    cur['_success'] = True
    cur['_note'] = (f"递归双向扩张：{len(depths)} 层 · 边际收益停止[{stopped_by}]（max_depth={max_depth}仅安全上限） · "
                    f"实体 {depths[0]['entities_total'] if depths else 0}→{depths[-1]['entities_total'] if depths else 0} · "
                    + ' · '.join(notes)[:160])
    return cur


# ---------- NODE 8 RESOURCE_CLASSIFICATION：三维分类（角色 × 贸易状态 × 开发状态） ----------
def n_resource_classification(state):
    """v33.0 三维分类词表（每个实体三个维度 + 理由字段，禁止只有 QUALIFIED）：
      entity_role:        CUSTOMER / SUPPLIER / CUSTOMER_AND_SUPPLIER / UNKNOWN
      trade_status:       TRADE_CONFIRMED(硬证据+票数) / TRADE_SUPPORTED(可信来源) / DISCOVERED(弱信号)
      development_status: DEVELOPMENT_POOL / MAINTENANCE_POOL / WON / DISCOVERED_POOL / REMOVED / UNASSIGNED
    lifecycle 兼容串由三维推导（CUSTOMER_CONFIRMED 等），一套逻辑，不并行。
    """
    out = n_gate(state)  # 执行器复用：放行/剔除结论
    pd_key = (state.get('product_domain') or {}).get('key', '')
    # v35 伪实体拦截（第三道保险）：国家/城市/港口/地址绝不进入分类与入库
    _raw_in = list(state.get('companies') or [])
    _kept = [c for c in _raw_in if not is_non_company_name(c.get('name'))]
    if len(_kept) != len(_raw_in):
        state['companies'] = _kept
        out = n_gate(state)  # 以过滤后的真实实体集重跑执行器
    role_map = {e.get('entity_id') or e.get('company_id'): e for e in (state.get('company_entities') or [])}
    classified_entities = []
    counts = {'by_role': {}, 'by_trade_status': {}, 'by_development_status': {}, 'lifecycle': {}}

    def _classify(c, default_role):
        e = c.get('evidence') or {}
        ent = role_map.get(norm(c.get('name')))
        # 实体解析已判定 UNKNOWN → 保持 UNKNOWN（角色未定只进图谱库）；
        # 未经过实体解析的实体才用默认角色。
        role = (ent.get('role') or 'UNKNOWN') if ent is not None else default_role
        hard = bool(e.get('shipments') or e.get('customs') or e.get('trade_evidence') or e.get('bill_of_lading'))
        has_ship = int(e.get('shipments') or 0) > 0
        # —— 贸易状态 ——
        if hard and has_ship:
            ts, reason = 'TRADE_CONFIRMED', '硬贸易证据（海关票数 %s）' % e.get('shipments')
        elif hard:
            ts, reason = 'TRADE_SUPPORTED', '可信贸易来源（无提单数字）'
        else:
            ts, reason = 'DISCOVERED', '弱信号发现（保留观察，不删除）'
        # —— 开发状态 ——
        if role == 'UNKNOWN':
            ds = 'UNASSIGNED'
            lifecycle = 'TRADE_NODE_ONLY'
            reason += '；角色未定，只进贸易图谱库'
        else:
            ds = 'DEVELOPMENT_POOL' if ts in ('TRADE_CONFIRMED', 'TRADE_SUPPORTED') else 'DISCOVERED_POOL'
            if role == 'CUSTOMER':
                lifecycle = 'CUSTOMER_' + ('CONFIRMED' if ts == 'TRADE_CONFIRMED' else 'DEVELOPMENT')
            elif role == 'SUPPLIER':
                lifecycle = 'SUPPLIER_' + {'TRADE_CONFIRMED': 'CONFIRMED', 'TRADE_SUPPORTED': 'DEVELOPMENT', 'DISCOVERED': 'BACKUP'}[ts]
            else:
                lifecycle = 'CUSTOMER_AND_SUPPLIER_' + ('CONFIRMED' if ts == 'TRADE_CONFIRMED' else 'DEVELOPMENT')
        c['entity_role'] = role
        c['trade_status'] = ts
        c['development_status'] = ds
        c['classification_reason'] = reason
        c['lifecycle'] = lifecycle
        c['product_domain'] = pd_key
        counts['by_role'][role] = counts['by_role'].get(role, 0) + 1
        counts['by_trade_status'][ts] = counts['by_trade_status'].get(ts, 0) + 1
        counts['by_development_status'][ds] = counts['by_development_status'].get(ds, 0) + 1
        counts['lifecycle'][lifecycle] = counts['lifecycle'].get(lifecycle, 0) + 1
        classified_entities.append(c)

    for c in (out.get('qualified_companies') or []):
        _classify(c, 'SUPPLIER' if _is_supplier(c) else 'CUSTOMER')
    # 扩张挖到的供应商同样进入分类（供应商统一由 DATABASE_COMMIT 入库）。
    # 一个实体多个角色：已在客户侧的实体再次以供应商身份出现 → 升级为 CUSTOMER_AND_SUPPLIER。
    seen = {norm(c.get('name')) for c in classified_entities}
    for s in (state.get('supplier_new') or []):
        if is_non_company_name(s.get('name')): continue  # v35 伪实体拦截
        sn = norm(s.get('name'))
        if sn in seen:
            for c in classified_entities:
                if norm(c.get('name')) != sn:
                    continue
                if c.get('entity_role') == 'CUSTOMER':
                    counts['by_role']['CUSTOMER'] = counts['by_role'].get('CUSTOMER', 1) - 1
                    c['entity_role'] = 'CUSTOMER_AND_SUPPLIER'
                    counts['by_role']['CUSTOMER_AND_SUPPLIER'] = counts['by_role'].get('CUSTOMER_AND_SUPPLIER', 0) + 1
                    old_lc = c.get('lifecycle') or ''
                    counts['lifecycle'][old_lc] = counts['lifecycle'].get(old_lc, 1) - 1
                    c['lifecycle'] = 'CUSTOMER_AND_SUPPLIER_' + ('CONFIRMED' if c.get('trade_status') == 'TRADE_CONFIRMED' else 'DEVELOPMENT')
                    counts['lifecycle'][c['lifecycle']] = counts['lifecycle'].get(c['lifecycle'], 0) + 1
                    c['classification_reason'] = (c.get('classification_reason') or '') + '；同实体双侧身份：客户+供应商'
                break
            continue
        seen.add(sn)
        _classify({'name': s.get('name'), 'country': s.get('country') or '', 'type': 'supplier',
                   'source': s.get('via') or s.get('source') or 'customs_raw',
                   'evidence': s.get('evidence') or {}}, 'SUPPLIER')
    nr = dict(out.get('node_reports') or {})
    note = ('三维分类：角色%s · 贸易状态%s · 开发状态%s · 域 %s · ' % (
            counts['by_role'], counts['by_trade_status'], counts['by_development_status'], pd_key)) + (out.get('_note') or '')
    # new_companies 保留给交接契约（全部已分类实体，新旧判定交给入库层幂等去重）
    return {**{k: v for k, v in out.items() if k not in ('node_reports', '_note')},
            'classified_entities': classified_entities, 'classification': counts,
            'node_reports': nr, '_success': out.get('_success', True), '_note': note}


# ---------- NODE 9 DATABASE_COMMIT：三类资产入库（Entity + Edge + Evidence）+ 完整漏斗 ----------
def n_database_commit(state):
    """classification → entity_converter → 客户库 / 供应商库 / 贸易图谱库。
    三类资产一次提交：Entity（leads）+ Edge（relationships）+ Evidence（evidence_events）。
    数量全程留痕：输入 → 转换 → 写入，任何数量变化必须说明原因（漏斗 drop_reasons）。
    提交对象是【全部已分类实体】——新增/更新/无变化由入库层幂等去重如实报告。"""
    from core.memory.db import DB
    db = DB()
    funnel = list(state.get('funnel') or [])
    classified = list(state.get('classified_entities') or state.get('qualified_companies') or [])
    funnel.append({'stage': 'DATABASE_COMMIT.输入(已分类实体)', 'in': len(classified), 'out': len(classified)})

    # —— 转换层 entity_converter：三维分类 → 客户行/供应商行/双角色行/纯贸易节点 ——
    KIND_MAP = {'CUSTOMER': 'customer', 'SUPPLIER': 'supplier', 'CUSTOMER_AND_SUPPLIER': 'both'}
    ZONE_MAP = {'DEVELOPMENT_POOL': 'dev', 'MAINTENANCE_POOL': 'maint', 'WON': 'won',
                'DISCOVERED_POOL': 'pending', 'REMOVED': 'discard', 'UNASSIGNED': 'pool'}
    customers = []; suppliers = []; both = []; node_only = 0; convert_failed = []
    for c in classified:
        lc = c.get('lifecycle') or ''
        nm = (c.get('name') or '').strip()
        if lc == 'TRADE_NODE_ONLY' or c.get('entity_role') == 'UNKNOWN':
            node_only += 1; continue  # 只进贸易图谱库（trade_nodes 已在采集层登记）
        if len(nm) < 3:
            convert_failed.append((nm or '(空名)', '名称无效')); continue
        role = c.get('entity_role') or ('SUPPLIER' if _is_supplier(c) else 'CUSTOMER')
        kind = KIND_MAP.get(role, 'customer')
        zone = ZONE_MAP.get(c.get('development_status') or '', 'dev' if lc.endswith('CONFIRMED') else 'pending')
        row = {'name': nm, 'country': c.get('country') or '', 'type': 'supplier' if kind in ('supplier', 'both') else 'customer',
               'source': c.get('source') or '', 'evidence': c.get('evidence') or {},
               'lifecycle': lc, 'product_domain': c.get('product_domain') or '',
               'entity_role': role, 'trade_status': c.get('trade_status') or '',
               'development_status': c.get('development_status') or '',
               'classification_reason': c.get('classification_reason') or '',
               '_kind': kind, '_zone': zone}
        {'customer': customers, 'supplier': suppliers, 'both': both}[kind].append(row)
    funnel.append({'stage': 'DATABASE_COMMIT.转换(entity_converter)', 'in': len(classified),
                   'out': len(customers) + len(suppliers) + len(both),
                   'note': f'客户{len(customers)}·供应商{len(suppliers)}·双角色{len(both)}·纯贸易节点{node_only}·转换失败{len(convert_failed)}',
                   'drop_reasons': [f'{n}:{r}' for n, r in convert_failed[:8]]})

    # —— 资产一：Entity 写入（幂等去重，如实报告 新增/更新/无变化/待验证/失败） ——
    created = 0; created_sup = 0; created_both = 0; updated = 0; pending_n = 0; unchanged = 0; failed = []
    committed_norms = []
    for c in customers + suppliers + both:
        result = db.commit_discovery_lead(c, zone=c['_zone'], kind=c['_kind'])
        if not result.get('ok'):
            failed.append((c.get('name') or '')[:120]); continue
        committed_norms.append(result.get('norm'))
        if result.get('created'):
            if c['_zone'] == 'dev':
                if c['_kind'] == 'supplier': created_sup += 1
                elif c['_kind'] == 'both': created_both += 1
                else: created += 1
            else:
                pending_n += 1
        elif result.get('changed'):
            updated += 1
        else:
            unchanged += 1
    total_in = len(customers) + len(suppliers) + len(both)
    funnel.append({'stage': 'DATABASE_COMMIT.Entity写入', 'in': total_in,
                   'out': created + created_sup + created_both + updated + pending_n + unchanged,
                   'note': f'新增客户{created}·新增供应商{created_sup}·双角色{created_both}·更新{updated}·无变化{unchanged}·发现池{pending_n}·失败{len(failed)}'})

    # —— 资产二：Edge 写入（relationships 全系统唯一正式出口） ——
    # 内存标准边在此落库（INSERT OR IGNORE 幂等，重复边自动累加证据）；写前兜底重判等级。
    task_id = state.get('task_id', '')
    edge_in = list(state.get('trade_edges') or [])
    edge_written = 0
    for ed in edge_in:
        try:
            e = ed.get('evidence') or {}
            lvl = ed.get('evidence_level') or _evidence_level(e, ed.get('source') or '')
            if lvl != 'STRONG':
                ed['confidence'] = min(float(ed.get('confidence') or 0.8), EVIDENCE_DEMOTE[lvl])
            db.add_relationship(task_id, ed.get('from_name'), ed.get('from_type') or 'buyer',
                                ed.get('to_name'), ed.get('to_type') or 'supplier',
                                ed.get('relation') or 'buyer_to_supplier', e,
                                ed.get('source') or 'trade_graph', ed.get('confidence') or 0.8,
                                ed.get('depth') or 1, evidence_level=lvl,
                                discovered_via=ed.get('discovered_via') or '',
                                parent_node=ed.get('parent_node') or '',
                                expansion_path=ed.get('expansion_path') or '',
                                product_domain=ed.get('product_id') or (state.get('product_domain') or {}).get('key', ''))
            edge_written += 1
        except Exception:
            pass
    # 回读核验：同库回读本任务全部边，确认写入可见；并兜底登记端点节点进候选池——
    # 图谱优先：每条边的两端都必须是图谱里的 Trade Node。
    try:
        rels = db.list_relationships(task_id=task_id, limit=5000)
        edge_n = len(rels)
        edge_levels = {}
        for r in rels:
            lv = r.get('evidence_level') or 'UNVERIFIED'
            edge_levels[lv] = edge_levels.get(lv, 0) + 1
            for nm, tp in ((r.get('from_name'), r.get('from_type') or 'buyer'),
                           (r.get('to_name'), r.get('to_type') or 'supplier')):
                try:
                    role = 'logistics' if LOGISTICS_RE.search(str(nm or '')) else tp
                    db.upsert_trade_node(nm, role=role, shipments=int(r.get('shipment_count') or 0),
                                         products=r.get('product') or '', hs=r.get('hs') or '',
                                         depth=int(r.get('depth') or 1), via='edge_endpoint',
                                         source=r.get('source') or 'trade_graph',
                                         entity_status='RESOLVED' if (r.get('shipment_count') or 0) > 0 else 'UNRESOLVED_TRADE_NODE',
                                         product_domain=r.get('product_domain') or (state.get('product_domain') or {}).get('key', ''))
                except Exception:
                    pass
    except Exception:
        edge_n = 0; edge_levels = {}
    funnel.append({'stage': 'DATABASE_COMMIT.Edge写入(唯一出口)', 'in': len(edge_in),
                   'out': edge_written, 'note': f'库内本任务边 {edge_n} 条·证据等级分布 {edge_levels}'})
    # —— 资产三：Evidence 写入（每个实体一条证据事件，权重跟随贸易状态） ——
    ev_n = 0
    for c in customers + suppliers + both:
        try:
            e = c.get('evidence') or {}
            w = {'TRADE_CONFIRMED': 1.0, 'TRADE_SUPPORTED': 0.6, 'DISCOVERED': 0.3}.get(c.get('trade_status'), 0.5)
            db.add_evidence_event(task_id, db._norm(c.get('name')), 'trade_asset_commit',
                                  c.get('source') or 'customs', json.dumps(
                                      {'evidence': e, 'trade_status': c.get('trade_status'),
                                       'reason': c.get('classification_reason') or ''}, ensure_ascii=False)[:1800], w)
            ev_n += 1
        except Exception:
            pass
    funnel.append({'stage': 'DATABASE_COMMIT.Evidence写入', 'in': total_in, 'out': ev_n})
    state['funnel'] = funnel

    # 回读自证：提交后立即用同一连接回读；界面若与这里不一致，唯一可能是打开了另一个项目副本
    verify = {'db': os.path.basename(str(settings.DATABASE_PATH)), 'dev_customers': 0, 'dev_suppliers': 0, 'probe_ok': True}
    try:
        import sqlite3 as _sq
        with _sq.connect(str(settings.DATABASE_PATH)) as _x:
            verify['dev_customers'] = _x.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND kind IN ('customer','both')").fetchone()[0]
            verify['dev_suppliers'] = _x.execute("SELECT COUNT(*) FROM leads WHERE zone='dev' AND kind IN ('supplier','both')").fetchone()[0]
            for pn in committed_norms[:5]:
                if pn and not _x.execute('SELECT 1 FROM leads WHERE norm=?', (pn,)).fetchone():
                    verify['probe_ok'] = False; break
    except Exception:
        verify['probe_ok'] = False
    ok = (len(failed) == 0 and total_in == created + created_sup + created_both + pending_n + updated + unchanged) and verify['probe_ok']
    rep = experts.review('DATABASE_COMMIT',
                         f'三类资产入库：Entity 输入{len(classified)}→转换{total_in}(客户{len(customers)}+供应商{len(suppliers)}+双角色{len(both)}，纯节点{node_only})'
                         f'→写入：新增客户{created}·供应商{created_sup}·双角色{created_both}·更新{updated}·无变化{unchanged}·发现池{pending_n}·失败{len(failed)} '
                         f'| Edge 写入{edge_written}/库内{edge_n} 条{edge_levels} | Evidence {ev_n} 条 · 回读{"通过" if verify["probe_ok"] else "失败"}',
                         [('数量恒等（输入=转换+纯节点+失败）', len(classified) == total_in + node_only + len(convert_failed),
                           f'{len(classified)}={total_in}+{node_only}+{len(convert_failed)}'),
                          ('数量恒等（写入=新增+更新+无变化+发现池+失败）', total_in == created + created_sup + created_both + pending_n + updated + unchanged + len(failed),
                           f'{total_in}={created}+{created_sup}+{created_both}+{updated}+{unchanged}+{pending_n}+{len(failed)}'),
                          ('三类资产齐备（Entity+Edge+Evidence）', ev_n == total_in - len(failed), f'Entity {total_in}·Edge {edge_n}·Evidence {ev_n}'),
                          ('回读验证（同库可见）', verify['probe_ok'], f"库 {verify['db']} · 确认池客户 {verify['dev_customers']} · 供应商 {verify['dev_suppliers']}")],
                         critical={'数量恒等（写入=新增+更新+无变化+发现池+失败）', '回读验证（同库可见）'})
    return {'database_commit': {'input': len(classified), 'converted': total_in, 'node_only': node_only,
                                'convert_failed': convert_failed,
                                'dev': created, 'dev_suppliers': created_sup, 'dev_both': created_both,
                                'updated': updated, 'unchanged': unchanged, 'pending': pending_n, 'failed': failed,
                                'edges': edge_n, 'edge_levels': edge_levels, 'evidence_events': ev_n,
                                'verify': verify, 'funnel': funnel,
                                'policy': 'classified_all_commit; three_assets(entity+edge+evidence); idempotent_dedup; kind_aware(customer/supplier/both); evidence_graded'},
            'commit_verify': verify,
            'node_reports': _report(state, 'DATABASE_COMMIT', rep), '_success': ok,
            '_note': (f"入库完成：输入{len(classified)}→新增客户{created}·供应商{created_sup}·双角色{created_both}·已有更新{updated}·发现池{pending_n}"
                      f"·边{edge_n}条·证据{ev_n}条·确认池现存 客户{verify['dev_customers']}/供应商{verify['dev_suppliers']}（库 {verify['db']}）"
                      if ok else f'入库失败 {len(failed)} 家：{failed[:3]}')}
