# -*- coding: utf-8 -*-
"""PSV Engine 25.1 Deployment Edition.
长期运行安全：任务队列、开发队列、定时任务 claim lock、服务重启恢复、幂等开发序列。
"""
import json,threading,time,uuid,queue
from core.runtime.orchestrator import Orchestrator
from core.memory.db import DB
from core.runtime import graph,development
# v45: 已删除旧 expand_tool 导入，使用 core.intelligence.network_expansion
from core.config import settings
from core.webui.broadcaster import get_broadcaster

class PSVSystem:
    def __init__(self):
        self.orch=Orchestrator(); self.db=DB(); self.q=queue.Queue(); self.dev_q=queue.Queue(); self._stopping=False
        self._recover_queues()
        threading.Thread(target=self._worker,daemon=True,name='psv-discovery-worker').start()
        threading.Thread(target=self._dev_worker,daemon=True,name='psv-development-worker').start()
        if settings.SCHEDULER_ENABLED: threading.Thread(target=self._scheduler,daemon=True,name='psv-scheduler').start()
    def _recover_queues(self):
        now=time.time()
        with self.db.c() as x:
            rows=x.execute("SELECT task_id,request,status,result FROM tasks WHERE status IN ('running','queued')").fetchall()
        for tid,req,status,res in rows:
            try:p=json.loads(res or '{}')
            except Exception:p={}
            mode=p.get('mode')
            if status=='running':
                p['error']='服务重启：任务曾在运行中，已安全标记为可恢复'; p['recovered_at']=now
                self.db.save_task(tid,req,'queued',p)
            if mode=='development' or str(tid).startswith('dev-'):
                lead=p.get('lead_norm')
                if lead:self.dev_q.put((lead,tid))
            else:
                params=p.get('params') or {}
                if params.get('industry'):
                    self.q.put((tid,req,params.get('market') or 'USA',params['industry'],params.get('quantity') or 20))
    def _worker(self):
        while not self._stopping:
            item=self.q.get()
            if item is None: continue
            tid,request,market,industry,quantity=item
            try:self.orch.run(request,market,industry,int(quantity or 20),task_id=tid)
            except Exception as e:
                err_msg=str(e)[:800]
                self.db.save_task(tid,request,'failed',{'error':err_msg,'recovered':True})
                get_broadcaster().emit('task_failed',{'task_id':tid,'error':err_msg,'thread':'discovery-worker','ts':time.time()})
    def _dev_worker(self):
        while not self._stopping:
            item=self.dev_q.get()
            if not item:continue
            lead_norm,tid=item[0],item[1]
            start_node=item[2] if len(item)>2 else None
            try:self.orch.run_development(lead_norm,task_id=tid,start_node=start_node)
            except Exception as e:
                err_msg=str(e)[:800]
                self.db.save_task(tid,'Development sequence: '+lead_norm,'failed',{'error':err_msg})
                get_broadcaster().emit('dev_failed',{'task_id':tid,'lead':lead_norm,'error':err_msg,'thread':'development-worker','ts':time.time()})
    def _scheduler(self):
        while not self._stopping:
            try:
                now=time.time()
                for s in self.db.list_schedules(enabled=True):
                    if float(s.get('next_run') or 0)>now: continue
                    if not self.db.claim_due_schedule(s['id'],lock_seconds=max(120,int(s.get('interval_minutes') or 60)*60)): continue
                    try:
                        if s['job_type']=='discovery':
                            tid=self.start(f"Scheduled discovery: {s['industry']} / {s['market']}",s['market'],s['industry'],s['quantity'])
                            self.db.mark_schedule_run(s['id'],'queued')
                        elif s['job_type']=='development':
                            if not settings.DEVELOPMENT_SEQUENCE_ENABLED or self.db.get_setting('development_sequence_enabled','true').lower()!='true':
                                self.db.mark_schedule_run(s['id'],'paused:development_sequence_disabled'); continue
                            max_n=int((s.get('params') or {}).get('max_customers') or settings.DEVELOPMENT_MAX_CUSTOMERS)
                            leads=self.db.list_leads(kind='customer',zone='dev',limit=max_n)
                            queued=0
                            for lead in leads:
                                if str(lead.get('development_status') or '') in {'done','running'}: continue
                                self.start_development(lead['norm']); queued+=1
                            self.db.mark_schedule_run(s['id'],f'queued:{queued}')
                        else:self.db.mark_schedule_run(s['id'],'invalid_job')
                    except Exception as e:self.db.mark_schedule_run(s['id'],'error:'+str(e)[:120])
            except Exception as e: print('[scheduler]',str(e)[:200])
            time.sleep(max(2,settings.SCHEDULER_POLL_SECONDS))
    def start(self,request,market,industry,quantity):
        tid=uuid.uuid4().hex[:8]
        self.db.save_task(tid,request,'queued',{'mode':'discovery','params':{'market':market,'industry':industry,'quantity':int(quantity or 20)}})
        self.q.put((tid,request,market,industry,quantity)); return tid
    def start_development(self,lead_norm,start_node=None):
        if not settings.DEVELOPMENT_SEQUENCE_ENABLED or self.db.get_setting('development_sequence_enabled','true').lower()!='true':
            return 'development-sequence-disabled'
        lead=self.db.get_lead(lead_norm)
        if not lead:return 'lead-not-found'
        if str(lead.get('zone') or '')!='dev':return 'lead-not-in-development-pool'
        existing=self.db.latest_development(lead_norm)
        if existing and existing.get('status')=='running': return existing.get('result',{}).get('task_id') or 'already-running'
        tid='dev-'+uuid.uuid4().hex[:8]
        self.db.save_task(tid,'Development sequence: '+lead_norm,'queued',{'mode':'development','lead_norm':lead_norm,'start_node':start_node})
        self.db.lead_update(lead_norm,development_status='running')
        self.dev_q.put((lead_norm,tid,start_node)); return tid
    def start_development_batch(self,max_customers=20):
        if not settings.DEVELOPMENT_SEQUENCE_ENABLED or self.db.get_setting('development_sequence_enabled','true').lower()!='true':
            return {'ok':False,'error':'development-sequence-disabled','queued':0}
        leads=self.db.list_leads(kind='customer',zone='dev',limit=max(1,int(max_customers or settings.DEVELOPMENT_MAX_CUSTOMERS)))
        queued=0;ids=[]
        for lead in leads:
            if str(lead.get('development_status') or '') in {'running','done'}: continue
            tid=self.start_development(lead['norm'])
            if tid.startswith('dev-'): ids.append(tid);queued+=1
        return {'ok':True,'queued':queued,'task_ids':ids}

    def run_network(self,tid,params=None):
        params=params or {}
        seed_norms=params.get('seed_norms') or []
        if isinstance(seed_norms,str): seed_norms=[seed_norms]
        try:
            # v45 修复：使用新的 network_expansion 引擎，不再依赖旧 expand_tool
            from core.intelligence.network_expansion import expand_network
            out = expand_network(
                seed_norm=seed_norms[0] if seed_norms else '',
                category_id=params.get('category_id'),
                expansion_types=params.get('strategies'),
                max_depth=params.get('depth', 2),
                max_new=params.get('max_new', 50),
                task_id=tid
            )
            task=self.db.get_task(tid) or {'request':'network expansion'}
            status='done' if out.get('ok') else 'failed'
            self.db.save_task(tid,task.get('request','Network expansion'),'done' if status=='done' else 'failed',{'mode':'network_expansion','seed_norms':seed_norms,'expansion':out})
            return {'ok':status=='done','result':out}
        except Exception as e:
            return {'ok':False,'error':str(e)[:500]}
    def run_node(self,tid,node):
        """单独执行 = DEBUG_ONLY。仅 DEBUG_MODE 开放，且不写回正式任务状态——
        避免调试执行污染生产黑板（v34：正式状态只能由编排器主流程写入）。"""
        if not settings.DEBUG_MODE:
            return {'error':'单独执行为 DEBUG_ONLY 能力：请设置环境变量 DEBUG_MODE=true 后重启','debug_only':True}
        task=self.db.get_task(tid)
        if not task:return {'error':'task not found'}
        if (task.get('result') or {}).get('mode')=='development' or tid.startswith('dev-'): return self.run_dev_node(tid,node)
        state=dict(task.get('result') or {}); state['task_id']=tid
        if node not in graph.FN:return {'error':'unknown node','allowed':list(graph.FN)}
        ok,out,error=graph._run_once(state,node,1,lambda st:None)  # 不落库、不改正式状态
        return {'ok':ok,'node':node,'error':error,'debug':True,'result':state}
    def run_dev_node(self,tid,node):
        task=self.db.get_task(tid)
        if not task:return {'ok':False,'error':'task not found'}
        result=task.get('result') or {}; lead_norm=result.get('lead_norm')
        if node not in development.FN:return {'ok':False,'error':'unknown development node','allowed':list(development.FN)}
        try:
            out=self.orch.run_development(lead_norm,task_id=tid,start_node=node)
            status='done' if out.get('ok') else 'failed'
            self.db.save_task(tid,task.get('request',''),'done' if status=='done' else 'failed',out)
            return {'ok':bool(out.get('ok')),'node':node,'error':out.get('error',''),'result':out}
        except Exception as e:return {'ok':False,'node':node,'error':str(e)[:500]}
    def get(self,tid): return self.db.get_task(tid)

    # ==================== v40 后半段业务入口 ====================
    def process_intelligence(self, norm: str) -> dict:
        from core.intelligence.account_intelligence_center import process_intelligence as process
        return process(norm)

    def batch_intelligence(self, norms: list) -> dict:
        from core.intelligence.account_intelligence_center import get_center
        results = get_center().batch_process(norms)
        return {'ok': True, 'processed': len(results), 'results': results}

    def expand_network(self, seed_norm: str, **kwargs) -> dict:
        from core.intelligence.network_expansion import expand
        return expand(seed_norm, **kwargs)

    def create_dev_letter(self, norm: str, **kwargs) -> dict:
        from core.business_execution.execution_center import create_letter
        return create_letter(norm, **kwargs)

    def get_trade_graph(self, center_norm: str, **kwargs) -> dict:
        from core.trade_graph.visualization import network
        return network(center_norm, **kwargs)

    def start_network_expansion(self, lead_norm='', max_depth=2, max_new=50, strategies=None, category_id=None):
        """Start network expansion task (compatible with app.py legacy interface)"""
        tid = uuid.uuid4().hex[:8]
        result = self.expand_network(seed_norm=lead_norm, category_id=category_id, max_depth=max_depth, max_new=max_new, expansion_types=strategies)
        self.db.save_task(tid, 'Network expansion: '+lead_norm, 'done' if result.get('ok') else 'failed', {
            'mode': 'network_expansion',
            'params': {'seed_norm': lead_norm, 'max_depth': max_depth, 'max_new': max_new, 'strategies': strategies, 'category_id': category_id},
            'result': result
        })
        return tid
