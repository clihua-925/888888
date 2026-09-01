# -*- coding: utf-8 -*-
"""v30 数据源编排（Customs Node Edition）：海关贸易节点第一优先。

第一采集链：关键词 → HS 编码 → 海关贸易数据源 → importer/supplier/shipper 节点。
通用搜索引擎不属于第一采集链；网页/展会只做第二阶段的画像补全。"""
import sqlite3,time,re,json,os
from core.config import settings
from core.tools.data_sources.sources import BulkCustomsSource, ImportYetiSource, ImportYetiWebSource, ImportKeyPublicSource, HsFinderSource
from core.tools.data_sources.base import Quota, q

ALLOWED_HARD_SOURCES={"customs_bulk","customs_raw","customs_provider","importyeti","importyeti_web","importkey_public","customs_web","hs_finder"}
SECONDARY_SOURCES={"public_crawler","exhibition","web_verify"}

def norm(s):
    """候选图谱 ID：去除常见公司后缀；数据库入池使用 DB.commit_discovery_lead，不再直接依赖本函数更新 leads。"""
    if not s:return ''
    s=str(s).lower().strip()
    s=re.sub(r'\b(the|inc|llc|co|ltd|corp|corporation|company|gmbh|sarl|limited|group|factory|trading|trade|international|intl)\b',' ',s)
    return re.sub(r'[^a-z0-9]+','',s)

def noise(name):
    return bool(re.search(r'freight|forwarder|logistics|cargo|shipping|customs broker|packaging|consulting|translation|dictionary|wiki|marketplace|software|media|association|expo|exhibition',name or '',re.I))

def identity_valid(c):
    name=(c.get('name') or '').strip()
    if len(norm(name))<2:return False
    if noise(name):return False
    from core.trade_graph.trade_node import is_non_company_name
    if is_non_company_name(name):return False  # v35：国家/城市/港口/地址伪实体不得成为公司实体
    typ=str(c.get('type') or c.get('kind') or '').lower()
    # 明确是贸易节点角色（importer/exporter/supplier/manufacturer/shipper/consignee/notify party）
    # 即使只有名字也保留；完整度不是淘汰条件（第一阶段不评分、不过度过滤）。
    if typ in {'importer','buyer','customer','exporter','supplier','manufacturer','shipper','consignee','notify','notify_party','notify party'}: return True
    e=c.get('evidence') or {}
    return bool(e.get('shipments') or e.get('customs') or e.get('trade_evidence') or e.get('supplier_relation') or e.get('hs') or e.get('bill_of_lading') or e.get('bol'))

def hard_evidence(c):
    e=c.get('evidence') or {}
    return bool(e.get('shipments') or e.get('bill_of_lading') or e.get('customs') or e.get('trade_evidence') or e.get('supplier_relation'))

def gate_check(companies):
    companies=companies or []
    return {'ok':bool(companies),'raw':len(companies),'qualified':len(companies),'strong':sum(1 for c in companies if hard_evidence(c)),'rejects':[]}

class Evolution:
    def plan(self,market,industry):
        try:
            from core.config.industry import load_industry
            cfg=load_industry(industry)
            base=list(cfg.get('search_terms') or [])
        except Exception:
            base=[industry]
        role=[f'{industry} importer',f'{industry} buyer',f'{industry} wholesaler',f'{industry} distributor']
        variants=list(dict.fromkeys([str(x).strip() for x in base+role if str(x).strip()]))
        return {'variants':variants[:8],'sources':['customs_bulk','customs_raw','customs_web','importyeti','importyeti_web','importkey_public'],'fallback':['public_crawler','exhibition'],'policy':'customs_trade_sources_first_incremental','rotation':'query variants + source checkpoints + unseen-first'}

class DataSourceManager:
    def __init__(self): self.last_evolution={}; self.quota=Quota()
    def _customs_raw_fallback(self,market,industry,limit,project_key):
        """本地海关库的增量候选器：新客户优先、最近变化次之、历史窗口轮换。
        目的不是每次重复取 TOP N，而是让同一个任务连续运行仍能不断发现新实体，并持续给旧实体补充海关证据。
        """
        out=[]
        try:
            db=__import__('core.memory.db',fromlist=['DB']).DB()
            cp=db.get_source_checkpoint('customs_raw',project_key)
            run_no=int(cp.get('run_count') or 0)
            cursor=int(cp.get('cursor') or 0)
            watermark=float(cp.get('watermark') or 0)
            page=max(int(limit),settings.SOURCE_PER_LIMIT)
            recent_limit=max(page, int(limit*2))
            with sqlite3.connect(settings.DATABASE_PATH) as c:
                c.row_factory=sqlite3.Row
                # A. 上次运行以后新增/变化过的进口商，即使已存在也必须重新进入画像合并。
                recent=c.execute("""SELECT importer,importer_norm,COUNT(*) shipments,MAX(ts) last_ts,
                    COUNT(DISTINCT shipper) supplier_count,MAX(hs) hs,MAX(descr) descr
                    FROM customs_raw WHERE importer IS NOT NULL AND TRIM(importer)!='' AND ts>?
                    GROUP BY importer_norm,importer ORDER BY last_ts DESC,shipments DESC LIMIT ?""",(watermark,recent_limit)).fetchall()
                # B. 数据库尚未见过的客户优先，防止第 2~N 次任务永远重复首批客户。
                unseen=c.execute("""SELECT r.importer,r.importer_norm,COUNT(*) shipments,MAX(r.ts) last_ts,
                    COUNT(DISTINCT r.shipper) supplier_count,MAX(r.hs) hs,MAX(r.descr) descr
                    FROM customs_raw r LEFT JOIN leads l ON l.norm=r.importer_norm
                    WHERE r.importer IS NOT NULL AND TRIM(r.importer)!='' AND l.norm IS NULL
                    GROUP BY r.importer_norm,r.importer ORDER BY last_ts DESC,shipments DESC LIMIT ?""",(page*2,)).fetchall()
                # C. 历史轮换窗口：没有新数据时也能继续遍历完整海关库，而不是第 5 次变成 0。
                all_rows=c.execute("""SELECT importer,importer_norm,COUNT(*) shipments,MAX(ts) last_ts,
                    COUNT(DISTINCT shipper) supplier_count,MAX(hs) hs,MAX(descr) descr
                    FROM customs_raw WHERE importer IS NOT NULL AND TRIM(importer)!=''
                    GROUP BY importer_norm,importer ORDER BY last_ts DESC,shipments DESC""").fetchall()
                total=len(all_rows)
                rot=[]
                if total:
                    start_at=cursor % total
                    rot=[all_rows[(start_at+i)%total] for i in range(min(page,total))]
                merged=[]; seen=set()
                for r in list(unseen)+list(recent)+rot:
                    n=r['importer_norm'] or norm(r['importer'])
                    if not n or n in seen: continue
                    seen.add(n)
                    merged.append(r)
                    if len(merged)>=max(page*2,int(limit)): break
            max_ts=max([float(r['last_ts'] or 0) for r in recent],default=watermark)
            # 不把 watermark 往后移动到“未来不可见”的位置；仅记录本地库当前最大时间。
            db.update_source_checkpoint('customs_raw',project_key,run_count=run_no+1,cursor=(cursor+page),watermark=max(watermark,max_ts),last_count=len(merged))
            for r in merged[:max(page,int(limit))]:
                out.append({'name':r['importer'],'country':'USA','industry':industry,'type':'importer','source':'customs_raw','strength':5,
                    'evidence':{'shipments':int(r['shipments'] or 0),'last_shipment':r['last_ts'] or '','supplier_count':int(r['supplier_count'] or 0),
                               'hs':r['hs'] or '','products':r['descr'] or '','customs':True,'incremental_run':run_no+1}})
            return out,None
        except Exception as e:return [],str(e)[:160]
    def _record_raw(self,source,query,rows):
        try:
            from core.memory.db import DB
            DB().save_raw_source(source,query,rows)
        except Exception: pass
    def search(self,market,industry,quantity,variants_override=None,source_queries=None,hs_codes=None):
        """v30.2 恢复 v10 原始采集链形态（最早效果最好的版本）：

        变体循环在外、数据源循环在内；源优先级 = v10 原序：
            hs_finder(ImportYeti HS榜单) → 本地海关库 → importyeti_web(关键词搜索)
            → importyeti API → customs_web 端点
        每源独立熔断（连续失败2次本轮跳过该源）；凑够目标数即停（省浏览器配额）。
        通用搜索引擎不属于第一采集链。v29 的增量检查点/轮换逻辑全部保留。
        """
        limit=max(1,int(quantity or 1)); companies=[];used=[];errors=[];breaker={}
        variants=[str(x).strip() for x in (variants_override or [industry]) if str(x).strip()][:4] or [industry]
        project_key=f"{market}:{industry}"
        target=max(limit,int(getattr(settings,'AGGREGATE_MIN_RESULTS',25)))
        per_source=max(5, min(settings.SOURCE_PER_LIMIT, max(1,(limit+1)//2)))
        seen=set()
        def add_rows(source,rows,query_label):
            if not rows:return 0
            added=0
            for c in rows:
                n=norm(c.get('name'))
                if not n or n in seen: continue
                seen.add(n); companies.append(c); added+=1
            if source not in used: used.append(source)
            self._record_raw(source,query_label,rows)
            return added
        def _db():
            return __import__('core.memory.db',fromlist=['DB']).DB()
        # ---- 各源单次调用（v29 增量逻辑原样保留，仅改成函数便于 v10 式循环）----
        def run_hs_finder(qv):
            if not getattr(settings,'HS_FINDER_ENABLED',False): return []
            codes=[str(x).strip() for x in (hs_codes or []) if str(x).strip()]
            if not codes:
                try:
                    from core.config.industry import load_industry
                    codes=[str(x) for x in (load_industry(industry).get('hs_codes') or [])]
                except Exception: codes=[]
            if not codes:
                codes=[c.strip() for c in str(getattr(settings,'HS_CODES','') or '').split(',') if c.strip()]
            if not codes: return []
            src=HsFinderSource(hs_codes=codes)
            if not src.available(): return []
            return src.search(market,industry,max(per_source,settings.SOURCE_PER_LIMIT))
        _hs_done={'v':False}
        def hs_once(qv):
            if _hs_done['v']: return []
            _hs_done['v']=True
            return run_hs_finder(qv)
        _local_done={'v':False}
        def customs_local(qv):
            if _local_done['v']: return []
            _local_done['v']=True; out=[]
            src=BulkCustomsSource()
            if src.available():
                cp=_db().get_source_checkpoint('customs_bulk',project_key)
                offset=int(cp.get('cursor') or 0)
                rows=src.search(market,industry,max(per_source*3,settings.SOURCE_PER_LIMIT),offset=offset)
                add_rows('customs_bulk',rows,industry)
                consumed=min(len(rows),max(1,limit))
                overlap=max(0,int(getattr(settings,'INCREMENTAL_SOURCE_OVERLAP',5)))
                next_offset=max(0,offset+max(1,consumed-overlap)) if rows else 0
                _db().update_source_checkpoint('customs_bulk',project_key,run_count=int(cp.get('run_count') or 0)+1,cursor=next_offset,last_count=len(rows),watermark=time.time())
            rows,err=self._customs_raw_fallback(market,industry,max(per_source*2,settings.SOURCE_PER_LIMIT),project_key)
            if rows: add_rows('customs_raw',rows,industry)
            elif err: errors.append('customs_raw:'+err)
            return out
        def iy_web_search(qv):
            if not getattr(settings,'IY_WEB_ENABLED',False): return []
            src=ImportYetiWebSource()
            if not src.available(): return []
            return src.search(market,qv,per_source)
        def iy_api_search(qv):
            if not getattr(settings,'IMPORTYETI_ENABLED',False): return []
            src=ImportYetiSource()
            if not src.available(): return []
            dbcp=_db().get_source_checkpoint('importyeti',project_key+'|'+qv)
            page_start=1+(int(dbcp.get('run_count') or 0)%max(1,int(settings.IMPORTYETI_MAX_PAGES)))
            rows=src.search(market,qv,per_source,query=qv,page_start=page_start)
            _db().update_source_checkpoint('importyeti',project_key+'|'+qv,run_count=int(dbcp.get('run_count') or 0)+1,cursor=page_start,last_count=len(rows),watermark=time.time())
            return rows
        def customs_web(qv):
            raw=getattr(settings,'CUSTOMS_WEB_SOURCES','').strip()
            if not raw: return []
            out=[]
            for item in raw.split(';'):
                parts=item.split('|',2)
                if len(parts)<2: continue
                name,url=parts[0].strip(),parts[1].strip()
                try:
                    rows=self._customs_web_source(name,url,qv,per_source)
                    add_rows(name,rows,qv)
                except Exception as e: errors.append(name+':'+str(e)[:120])
            return out
        # v10 原序管道：(名字, 调用, 每源变体上限)
        pipeline=[('hs_finder',hs_once,1),('customs_local',customs_local,1),
                  ('importyeti_web',iy_web_search,2),('importyeti',iy_api_search,2),
                  ('customs_web',customs_web,1)]
        src_calls={}
        for qv in variants:
            for name,fn,max_vars in pipeline:
                if breaker.get(name,0)>=2: continue          # 熔断：连续失败2次本轮跳过该源
                if src_calls.get(name,0)>=max_vars: continue # 每源变体上限（省浏览器/配额）
                try:
                    rows=fn(qv) or []
                    src_calls[name]=src_calls.get(name,0)+1
                    breaker[name]=0
                except Exception as e:
                    breaker[name]=breaker.get(name,0)+1
                    src_calls[name]=src_calls.get(name,0)+1
                    tip='；连续失败已熔断，本轮跳过后续变体' if breaker[name]>=2 else ''
                    errors.append(f'{name}[{qv}]: {str(e)[:90]}{tip}'); continue
                if rows: add_rows(name,rows,qv)
                if len(companies)>=target: break             # v10 行为：凑够目标即停
            if len(companies)>=target: break
        # 统一实体解析：同一客户来自多个海关源时合并证据，而不是重复占据数量名额。
        merged={}
        def merge_field(a,b):
            if not a:return b
            if not b:return a
            if isinstance(a,list) or isinstance(b,list):
                vals=[]
                for v in (a,b): vals.extend(v if isinstance(v,list) else [v])
                out=[];seen=set()
                for v in vals:
                    k=str(v).strip().lower()
                    if k and k not in seen: seen.add(k);out.append(v)
                return out
            return a if str(a)==str(b) else f"{a} | {b}"
        for c in companies:
            n=norm(c.get('name'))
            if not n: continue
            e=c.setdefault('evidence',{})
            if n not in merged:
                merged[n]=dict(c); merged[n]['evidence']=dict(e)
                continue
            m=merged[n]; me=m.setdefault('evidence',{})
            me['shipments']=max(int(me.get('shipments') or 0),int(e.get('shipments') or 0))
            me['last_shipment']=e.get('last_shipment') if str(e.get('last_shipment') or '')>str(me.get('last_shipment') or '') else me.get('last_shipment','')
            for k in ('hs','products','source_type','source_endpoint'):
                if e.get(k): me[k]=merge_field(me.get(k),e.get(k))
            me['customs']=bool(me.get('customs') or e.get('customs')); me['trade_evidence']=True
            m['source']=merge_field(m.get('source',''),c.get('source',''))
            if not m.get('website') and c.get('website'):m['website']=c['website']
        unique=list(merged.values())
        # v30：为每个合并后的候选标注贸易节点角色（importer/supplier/shipper/...）。
        # 第一阶段只做节点识别，不做评分、不做价值判断。
        try:
            from core.trade_graph.customs_node_pipeline import detect_role
            for c in unique:
                role=detect_role(c); c['node_role']=role
                c.setdefault('evidence',{})['node_role']=role
        except Exception: pass
        # v30.3：ImportYeti 是验证标准——IY 命中标 iy_verified，IY+其他源共同命中标 cross_validated。
        try:
            from core.trade_graph.iy_network import tag_verification
            tag_verification(unique)
        except Exception: pass
        # 新实体优先，其次是本轮发生海关变化的实体，最后才是普通历史轮换。
        try:
            from core.memory.db import DB
            db=DB(); existing={r['norm'] for r in db.list_leads(limit=100000)}
        except Exception: existing=set()
        unique.sort(key=lambda c:(norm(c.get('name')) in existing, -(int((c.get('evidence') or {}).get('shipments') or 0))))
        self.last_evolution={'sources':used,'hard_sources':[x for x in used if x in ALLOWED_HARD_SOURCES or x.startswith('customs')],
            'secondary_sources':[],'queries':variants[:8],'policy':'hard-customs fanout + incremental delta + rotating historical window; secondary web/exhibition are enrichment only',
            'project_key':project_key,'source_fanout':True,'incremental':True}
        return unique[:limit],used,errors,{'ok':bool(unique),'raw':len(companies),'qualified':0,'strong':sum(1 for c in unique if hard_evidence(c)),
            'new_candidates':sum(1 for c in unique if norm(c.get('name')) not in existing),'existing_enriched':sum(1 for c in unique if norm(c.get('name')) in existing)}

    def _customs_web_source(self,name,url,industry,limit):
        """读取用户明确配置的公开/授权海关数据端点；不登录、不绕验证码、不绕付费墙。"""
        import requests
        target=url.replace('{query}',q(industry))
        r=requests.get(target,timeout=settings.DATA_SOURCE_TIMEOUT,headers={'User-Agent':'PSV-CustomsCollector/27.0'})
        r.raise_for_status(); data=r.json() if 'json' in (r.headers.get('content-type') or '').lower() else {}
        rows=data.get('results') or data.get('data') or data if isinstance(data,list) else []
        out=[]
        for row in rows[:limit]:
            if not isinstance(row,dict): continue
            nm=row.get('importer') or row.get('importer_name') or row.get('company') or row.get('name')
            if not nm: continue
            ev={'customs':True,'trade_evidence':True,'shipments':row.get('shipments') or row.get('shipment_count') or row.get('totalShipments') or 0,
                'last_shipment':row.get('last_shipment') or row.get('last_date') or row.get('lastShipment') or '',
                'hs':row.get('hs') or row.get('hs_code') or '', 'products':row.get('descr') or row.get('product') or row.get('products') or '', 'source_endpoint':target}
            out.append({'name':nm,'country':row.get('country') or 'USA','industry':industry,'type':'importer','source':name,'strength':5,'website':row.get('website') or '','evidence':ev})
        return out

    def _public_crawler(self,industry,limit):
        # 不内置绕过站点限制的爬虫；支持用户配置的公开/授权端点或 Apify actor。
        raw=os.getenv('PUBLIC_CRAWLER_SOURCES','').strip()
        if not raw:return []
        out=[]
        for item in raw.split(';'):
            if len(out)>=limit:break
            parts=item.split('|',2)
            if len(parts)<2:continue
            name,url=parts[0],parts[1]
            try:
                from core.tools.data_sources.base import Source
                src=Source(); html=src._text(url.replace('{query}',q(industry)))
                titles=re.findall(r'<title[^>]*>(.*?)</title>',html,re.I|re.S)
                for t in titles[:limit-len(out)]:
                    nm=re.sub(r'<.*?>',' ',t);nm=re.sub(r'\s+',' ',nm).strip()
                    if nm:out.append({'name':nm,'country':'','industry':industry,'type':'lead','source':'public_crawler','strength':1,'evidence':{'public_page':url,'secondary':True}})
            except Exception:continue
        return out[:limit]
    def _exhibition_fallback(self,market,industry,limit):
        # 仅读取用户提供的 data/imports/*.csv，或显式配置的公开名录；不把网页搜索冒充展会证据。
        import csv
        from pathlib import Path
        out=[]; p=Path(settings.IMPORT_DIR)
        for fp in p.glob('*exhibition*.csv'):
            with fp.open(encoding='utf-8-sig',errors='ignore') as f:
                for r in csv.DictReader(f):
                    nm=(r.get('company') or r.get('company_name') or '').strip()
                    if not nm:continue
                    out.append({'name':nm,'country':r.get('country') or market,'industry':industry,'type':'lead','source':'exhibition','strength':2,'website':r.get('website') or '','evidence':{'exhibition':r.get('event') or fp.name,'secondary':True}})
                    if len(out)>=limit:return out
        return out
