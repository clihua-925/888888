# -*- coding: utf-8 -*-
"""PSV Engine Web UI v40"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import json,time,os,sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','..'))
from core.config import settings
from core.system import PSVSystem
from core.memory.db import DB
from core.runtime import contracts as _ct
from core.tools import data_sources as _ds,hs_finder as _hs,auditor as _aud
from core.tools.data_sources import manager as _dsm
from core.intelligence import icp as _icp
from core.webui.broadcaster import get_broadcaster
from core.trade_graph import supplier_profile as sprof
from core.trade_graph import product_intelligence as _pi
from core.trade_graph import iy_network as _iy

HTML='''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>PSV Engine</title><style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:#f5f7fa;color:#1a1a2e;line-height:1.6}
.container{max-width:1200px;margin:0 auto;padding:20px}.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:30px;border-radius:12px;margin-bottom:24px;box-shadow:0 4px 15px rgba(102,126,234,0.3)}
.header h1{font-size:28px;font-weight:700;margin-bottom:8px}.header p{opacity:.9;font-size:14px}
.card{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.06);border:1px solid #e8ecf1}
.card h2{font-size:18px;color:#2d3748;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid #f0f4f8}
.form-group{margin-bottom:16px}.form-group label{display:block;font-weight:600;color:#4a5568;margin-bottom:6px;font-size:13px;text-transform:uppercase;letter-spacing:.5px}
input,select,textarea{width:100%;padding:12px 14px;border:2px solid #e2e8f0;border-radius:8px;font-size:14px;transition:all .2s;background:#fff}
input:focus,select:focus,textarea:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,.1)}
textarea{min-height:100px;resize:vertical;font-family:inherit}
.btn{display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;transition:all .2s;margin-right:10px;margin-bottom:10px}
.btn:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(102,126,234,.3)}.btn:active{transform:translateY(0)}
.btn-secondary{background:#718096}.btn-secondary:hover{background:#4a5568}
.btn-success{background:#48bb78}.btn-success:hover{background:#38a169}
.btn-warning{background:#ed8936}.btn-warning:hover{background:#dd6b20}
.btn-sm{padding:8px 16px;font-size:12px}
.btn-group{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.status-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}
.status-pending{background:#fef3c7;color:#92400e}.status-running{background:#dbeafe;color:#1e40af}
.status-done{background:#d1fae5;color:#065f46}.status-failed{background:#fee2e2;color:#991b1b}
.lead-item{padding:16px;border:2px solid #e2e8f0;border-radius:10px;margin-bottom:12px;transition:all .2s;cursor:pointer}
.lead-item:hover{border-color:#667eea;box-shadow:0 2px 8px rgba(102,126,234,.1)}
.lead-item.selected{border-color:#667eea;background:#f8faff}
.lead-name{font-weight:700;color:#2d3748;font-size:15px}.lead-meta{font-size:12px;color:#718096;margin-top:4px}
.lead-score{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;background:#e2e8f0;color:#4a5568}
.lead-score.A{background:#d1fae5;color:#065f46}.lead-score.B{background:#dbeafe;color:#1e40af}
.lead-score.C{background:#fef3c7;color:#92400e}.lead-score.D{background:#fee2e2;color:#991b1b}
.tabs{display:flex;border-bottom:2px solid #e2e8f0;margin-bottom:20px}.tab{padding:12px 20px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;font-weight:600;color:#718096}
.tab.active{border-bottom-color:#667eea;color:#667eea}.tab-content{display:none}.tab-content.active{display:block}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:10px;text-align:left;border-bottom:1px solid #e2e8f0}
th{font-weight:600;color:#4a5568;text-transform:uppercase;font-size:11px;letter-spacing:.5px;background:#f8fafc}
tr:hover{background:#f8fafc}.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:#e2e8f0;color:#4a5568;margin-right:4px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center}
.modal.active{display:flex}.modal-content{background:#fff;border-radius:12px;padding:24px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto}
.modal-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.modal-close{font-size:24px;cursor:pointer;color:#718096}.modal-close:hover{color:#1a202c}
.progress-bar{height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;background:linear-gradient(90deg,#667eea,#764ba2);transition:width .3s}
.network-graph{height:400px;background:#f8fafc;border-radius:8px;border:2px solid #e2e8f0;display:flex;align-items:center;justify-content:center;color:#718096}
pre{background:#1a1a2e;color:#e2e8f0;padding:16px;border-radius:8px;overflow-x:auto;font-size:12px;line-height:1.5}
.notification{position:fixed;top:20px;right:20px;padding:16px 20px;border-radius:8px;color:#fff;font-weight:600;z-index:2000;transform:translateX(400px);transition:transform .3s;box-shadow:0 4px 12px rgba(0,0,0,.15)}
.notification.show{transform:translateX(0)}.notification.success{background:#48bb78}.notification.error{background:#f56565}
.empty-state{text-align:center;padding:40px;color:#718096}.empty-state svg{width:64px;height:64px;margin-bottom:16px;opacity:.5}
.loading{display:inline-block;width:16px;height:16px;border:2px solid #e2e8f0;border-top-color:#667eea;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:768px){.grid{grid-template-columns:1fr}.btn-group{flex-direction:column}.btn{width:100%;margin-right:0}}
.intelligence-card{border-left:4px solid #667eea;padding-left:16px;margin-bottom:16px}
.completeness-bar{height:20px;background:#e2e8f0;border-radius:10px;overflow:hidden;position:relative}
.completeness-fill{height:100%;border-radius:10px;transition:width .3s}
.completeness-text{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:11px;font-weight:700;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.3)}
.expansion-node{padding:12px;border:2px solid #e2e8f0;border-radius:8px;margin:8px 0;cursor:pointer}
.expansion-node:hover{border-color:#48bb78;background:#f0fff4}
</style></head><body>
<div class="container">
  <div class="header"><h1>PSV Engine v40</h1><p>第一采集链 → 客户情报中心 → 贸易图谱 → 业务执行中心</p></div>
  <div class="tabs">
    <div class="tab active" data-tab="tasks">任务中心</div>
    <div class="tab" data-tab="leads">客户情报中心</div>
    <div class="tab" data-tab="network">贸易图谱</div>
    <div class="tab" data-tab="execution">业务执行中心</div>
    <div class="tab" data-tab="settings">设置</div>
  </div>
  <div class="tab-content active" id="tasks-tab">...</div>
  <div class="tab-content" id="leads-tab">...</div>
  <div class="tab-content" id="network-tab">...</div>
  <div class="tab-content" id="execution-tab">...</div>
  <div class="tab-content" id="settings-tab">...</div>
</div>
<script>
/* v43 FIX: SSE 实时同步后台状态，根治后台与UI不同步 */
(function(){
    const logContainer = document.querySelector('.card:last-child') || document.body;

    function appendLog(msg, level){
        const div = document.createElement('div');
        div.style.cssText = 'padding:4px 8px;margin:2px 0;border-radius:4px;font-size:12px;font-family:monospace;';
        div.style.background = level === 'error' ? '#fee2e2' : level === 'success' ? '#d1fae5' : '#f0f4f8';
        div.style.color = level === 'error' ? '#991b1b' : level === 'success' ? '#065f46' : '#4a5568';
        div.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
        logContainer.appendChild(div);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function connectSSE(){
        const es = new EventSource('/api/events/stream');
        es.onmessage = function(e){
            try{
                const ev = JSON.parse(e.data);
                if(ev.type === 'task_failed' || ev.type === 'dev_failed'){
                    appendLog('【后台异常】' + ev.payload.error, 'error');
                    alert('后台任务异常: ' + ev.payload.error);
                } else if (ev.type === 'db_updated'){
                    appendLog('数据已更新，请刷新页面查看最新结果', 'success');
                    if(typeof loadLeads === 'function') loadLeads();
                } else {
                    appendLog(ev.type + ': ' + JSON.stringify(ev.payload).slice(0,100), 'info');
                }
            }catch(err){}
        };
        es.onerror = function(){
            es.close();
            appendLog('SSE断线，降级为轮询', 'info');
            setInterval(pollEvents, 3000);
        };
    }

    let lastPollTs = 0;
    function pollEvents(){
        fetch('/api/events/poll?last_ts=' + lastPollTs)
            .then(r=>r.json())
            .then(data=>{
                if(data.events && data.events.length){
                    data.events.forEach(ev => {
                        lastPollTs = Math.max(lastPollTs, ev.ts);
                        if(ev.type === 'task_failed'){
                            appendLog('【后台异常】' + ev.payload.error, 'error');
                        }
                    });
                }
            })
            .catch(()=>{});
    }

    if(typeof EventSource !== 'undefined'){
        connectSSE();
    } else {
        setInterval(pollEvents, 3000);
    }
})();
</script>
</body></html>'''

SYS=PSVSystem()

def list_industries():return sorted(set(v.get('industry','')for v in SYS.db.list_schedules()if v.get('industry')))
def load_markets():return getattr(settings,'MARKETS',{})

class H(BaseHTTPRequestHandler):
    def _s(self,d,code=200,html_out=False):
        self.send_response(code)
        if html_out:
            self.send_header('Content-Type','text/html; charset=utf-8')
        else:
            self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        if html_out:
            self.wfile.write(d.encode('utf-8') if isinstance(d,str) else d)
        else:
            self.wfile.write(json.dumps(d,default=str,ensure_ascii=False).encode())
    def do_OPTIONS(self):self.send_response(200);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Methods','GET,POST,DELETE,OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()
    def do_GET(self):
        u=urlparse(self.path);path=u.path;qs=parse_qs(u.query)
        # v40 后半段API路由（放在最前面处理）
        if path.startswith('/api/intelligence/'):
            parts=path.split('/')
            if len(parts)>=4 and parts[3]:
                norm=parts[3]
                from core.intelligence.account_intelligence_center import get
                data=get(norm)
                if not data: return self._s({'ok':False,'error':'not found'},404)
                return self._s({'ok':True,'data':data})
        if path=='/api/intelligence':
            from core.intelligence.account_intelligence_center import list_all
            kind=(qs.get('kind') or [None])[0]; zone=(qs.get('zone') or [None])[0]
            min_c=int((qs.get('min_completeness') or ['0'])[0])
            min_s=float((qs.get('min_score') or ['0'])[0])
            limit=int((qs.get('limit') or ['50'])[0])
            offset=int((qs.get('offset') or ['0'])[0])
            data=list_all(kind=kind,zone=zone,min_completeness=min_c,min_score=min_s,limit=limit,offset=offset)
            return self._s({'ok':True,'data':data,'count':len(data)})
        if path.startswith('/api/graph/network'):
            from core.trade_graph.visualization import network
            center=(qs.get('center') or [''])[0]
            if not center: return self._s({'ok':False,'error':'center required'},400)
            depth=int((qs.get('depth') or ['2'])[0])
            return self._s(network(center,depth=depth))
        if path.startswith('/api/graph/path'):
            from core.trade_graph.visualization import path
            from_norm=(qs.get('from') or [''])[0]; to_norm=(qs.get('to') or [''])[0]
            if not from_norm or not to_norm: return self._s({'ok':False,'error':'from and to required'},400)
            return self._s(path(from_norm,to_norm))
        if path.startswith('/api/graph/evidence/'):
            parts=path.split('/'); norm=parts[4] if len(parts)>=5 else ''
            from core.trade_graph.visualization import evidence
            return self._s(evidence(norm))
        if path.startswith('/api/execution/qualify/'):
            parts=path.split('/'); norm=parts[4] if len(parts)>=5 else ''
            from core.business_execution.execution_center import qualify
            return self._s(qualify(norm))
        if path=='/api/execution/pipeline':
            from core.business_execution.execution_center import pipeline
            norm=(qs.get('norm') or [None])[0]
            return self._s(pipeline(norm))
        if path.startswith('/api/info-gain/'):
            parts=path.split('/'); task_id=parts[3] if len(parts)>=4 else ''
            db=DB(); logs=db.get_latest_info_gain(task_id)
            return self._s({'ok':True,'logs':logs})
        # 原始路由
        if path=='/':return self._s(HTML,html_out=True)
        if path=='/api/stats':return self._s(_stats())
        if path=='/api/contracts':return self._s({'contract_version':'v34.0','contracts':_ct.registry_snapshot()})
        if path=='/api/industries':return self._s({'industries':list_industries()})
        if path=='/api/settings':return self._s({'default_industry':SYS.db.get_setting('default_industry',settings.INDUSTRY),'default_market':SYS.db.get_setting('default_market','USA'),'default_quantity':int(SYS.db.get_setting('default_quantity','20')),'development_sequence_enabled':SYS.db.get_setting('development_sequence_enabled','true')})
        if path=='/api/markets':return self._s({'markets':load_markets()})
        if path=='/api/schedules':return self._s({'schedules':SYS.db.list_schedules()})
        if path=='/api/leads':return self._s({'leads':SYS.db.list_leads(kind=(qs.get('kind') or [None])[0],zone=(qs.get('zone') or [None])[0],domain=(qs.get('domain') or [None])[0],limit=300)})
        if path=='/api/expansion-activity':return self._s({'active':SYS.db.expansion_activity()})
        if path.startswith('/api/leads/') and path.endswith('/detail'):
            norm=path.split('/')[3] if len(path.split('/'))>3 else ''
            d=SYS.db.get_lead_detail(norm); return self._s(d or {'error':'lead not found'},200 if d else 404)
        if path=='/api/tasks':
            rows=SYS.db.list_tasks(limit=50)
            for t in rows:
                t['stopped_by_label']=_lbl.get(t.get('stopped_by') or '',t.get('stopped_by') or '—')
                try:
                    rels=SYS.db.list_relationships(task_id=t.get('task_id') or '',limit=12)
                    t['trail']=[{'from':r['from_name'],'to':r['to_name'],'rel':r['relation'],'sc':r.get('shipment_count') or 0,'lvl':r.get('evidence_level') or '','path':r.get('expansion_path') or ''} for r in rels]
                except Exception: t['trail']=[]
            return self._s({'tasks':rows})
        if path=='/api/sender-profile':return self._s({'profile':SYS.db.get_sender_profile()})
        if path=='/api/ai-calls':return self._s({'calls':SYS.db.list_ai_calls()})
        return self._s({'error':'not found'},404)
    def do_POST(self):
        u=urlparse(self.path);path=u.path;length=int(self.headers.get('Content-Length',0));body=json.loads(self.rfile.read(length).decode() or '{}')
        # v40 后半段API路由（放在最前面处理）
        if path.startswith('/api/intelligence/') and path.endswith('/process'):
            parts=path.split('/'); norm=parts[3] if len(parts)>=4 else ''
            from core.intelligence.account_intelligence_center import process
            return self._s(process(norm))
        if path=='/api/network/expand':
            from core.intelligence.network_expansion import expand
            seed_norm=body.get('seed_norm')
            if not seed_norm: return self._s({'ok':False,'error':'seed_norm required'},400)
            result=expand(seed_norm=seed_norm,expansion_types=body.get('expansion_types'),depth=int(body.get('depth',1)),max_new=int(body.get('max_new',50)),stop_on_no_gain=body.get('stop_on_no_gain',True))
            return self._s(result)
        if path=='/api/execution/dev-letter':
            from core.business_execution.execution_center import create_letter
            norm=body.get('norm')
            if not norm: return self._s({'ok':False,'error':'norm required'},400)
            return self._s(create_letter(norm,template=body.get('template')))
        if path=='/api/execution/mark-sent':
            from core.business_execution.execution_center import get_center
            record_id=body.get('record_id')
            if not record_id: return self._s({'ok':False,'error':'record_id required'},400)
            return self._s(get_center().mark_sent(record_id,body.get('sender_email')))
        # 原始路由
        if path=='/api/task':return self._s({'task_id':SYS.start(body.get('request',''),body.get('market','USA'),body.get('industry','candle'),int(body.get('quantity',20)))})
        if path=='/api/development':return self._s({'task_id':SYS.start_development(body.get('lead_norm',''))})
        if path=='/api/development-sequence/start':return self._s(SYS.start_development_batch(int(body.get('max_customers',20))))
        if path.startswith('/api/leads/') and path.endswith('/zone'):
            norm=path.split('/')[3] if len(path.split('/'))>3 else ''; return self._s(SYS.db.move_lead(norm,body.get('zone','pending')))
        if path=='/api/network-expansion':
            from core.tools import expand as _ex
            strategies=body.get('strategies')
            if any(_ex.STRATEGIES.get(x,{}).get('kind')=='web' for x in (strategies or _ex.DEFAULT_ORDER)):
                from core.tools import iy_web
                if not iy_web.available():
                    return self._s({'ok':False,'error':'ImportYeti 网页未就绪：请先启动 start_chrome_debug.bat 并确认能访问 importyeti.com；也可用 strategies=["same_product_importers","cross_market_entity"] 只跑本地策略'},503)
            return self._s({'task_id':SYS.start_network_expansion(body.get('lead_norm',''),body.get('max_depth',2),body.get('max_new',50),strategies)})
        if path=='/api/schedules':return self._s({'schedule_id':SYS.db.save_schedule(body)})
        if path=='/api/schedules/toggle':
            sid=body.get('schedule_id');en=body.get('enabled');SYS.db.toggle_schedule(sid,en);return self._s({'ok':True})
        if path=='/api/settings':return self._s({'ok':SYS.db.save_setting(body.get('key'),body.get('value'))})
        if path=='/api/sender-profile':return self._s({'ok':True})
        return self._s({'error':'not found'},404)
    def do_DELETE(self):
        u=urlparse(self.path);path=u.path
        if path.startswith('/api/industries/'):
            return self._s({'ok':delete_industry(path.split('/')[-1])})
        if path.startswith('/api/markets/'):
            return self._s({'ok':delete_market(path.split('/')[-1])})
        if path.startswith('/api/schedules/'):
            SYS.db.delete_schedule(int(path.split('/')[-1]));return self._s({'ok':True})
        return self._s({'error':'not found'},404)
    def log_message(self,*a):pass

def _stats():
    db=SYS.db
    return {'tasks':db.count('tasks'),'leads':db.count('leads'),'buyers':db.count('buyers_90d'),'suppliers':db.count('suppliers'),'customs':db.count('customs_raw'),'relationships':db.count('relationships'),'schedules':db.count('schedules')}

_lbl={'max_depth':'达到最大深度','max_new':'达到最大新增数','no_frontier':'前沿队列为空','time_budget':'时间预算耗尽','user_stop':'用户手动停止','error':'发生错误'}

def run():
    srv=ThreadingHTTPServer((settings.WEB_HOST,settings.WEB_PORT),H);print('Server running at http://localhost:'+str(settings.WEB_PORT));srv.serve_forever()

if __name__=='__main__':run()