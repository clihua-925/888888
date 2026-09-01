# -*- coding: utf-8 -*-
"""v14 编排入口：组装初始状态 → 跑状态图 → 每节点快照 → 终态落库。结果结构与 v13 兼容，前端无需大改。"""
import time,uuid
from core.memory.db import DB
from core.runtime import graph
class Orchestrator:
    def __init__(self): self.db=DB()
    def run(self,request,market='USA',industry='birthday candles',quantity=20,task_id=None):
        tid=task_id or uuid.uuid4().hex[:8]; t0=time.time()
        state={'task_id':tid,'request':request,'market':market,'industry':industry,
               'quantity':int(quantity or 20),'nodes':[],'companies':[],
               'success':False,
               'node_reports':{},'strategy':{},'query_override':None,
               'current_node':'INIT','node_status':{},'handoffs':{},'retry_history':[],'plans':[],
               'diagnostics':[],'mission_decisions':[],'funnel':[]}
        def persist(st):
            res={k:v for k,v in st.items() if k!='traceback'}
            self.db.save_task(tid,request,'running',res)
        persist(state)
        state=graph.run_graph(state,persist)
        abort=state.get('abort')
        status={'failed':'failed','failed_gate':'failed_gate','done_degraded':'done_degraded','error':'error'}.get(abort,'done')
        state['success']=status in ('done','done_degraded')
        state['duration_sec']=round(time.time()-t0,2)
        res={k:v for k,v in state.items() if k!='traceback'}
        self.db.save_task(tid,request,status,res)
        return res

    def run_development(self,lead_norm,task_id=None,start_node=None):
        from core.runtime.development import run_sequence
        tid=task_id or ('dev-'+uuid.uuid4().hex[:8]); t0=time.time()
        self.db.finish_development(lead_norm,{'task_id':tid,'lead_norm':lead_norm,'status':'running'},'running')
        def persist(st):
            payload={'mode':'development','task_id':tid,'lead_norm':lead_norm,'current_node':st.get('current_dev_node'),
                     'node_status':st.get('dev_status',{}),'nodes':st.get('dev_nodes',[]),'opportunity':st.get('opportunity',{}),
                     'profile':st.get('profile',{}),'offer_strategy':st.get('offer_strategy',{}),'letter':st.get('letter',''),
                     'error':st.get('error','')}
            self.db.save_task(tid,f'Development sequence: {lead_norm}','running',payload)
        try:
            result=run_sequence(lead_norm,persist=persist,task_id=tid,start_node=start_node)
            status='done' if result.get('ok') else 'failed'
            self.db.finish_development(lead_norm,result,status)
            result['task_id']=tid; result['duration_sec']=round(time.time()-t0,2)
            self.db.save_task(tid,f'Development sequence: {lead_norm}',status,result)
            return result
        except Exception as e:
            result={'ok':False,'error':str(e)[:500],'task_id':tid}
            self.db.finish_development(lead_norm,result,'failed'); self.db.save_task(tid,f'Development sequence: {lead_norm}','failed',result)
            return result
