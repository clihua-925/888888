# -*- coding: utf-8 -*-
"""v39 E2E 真实系统验收：临时库 + 真实 HTTP API + 真实 UI HTML。
按本轮验收标准链路逐项验证：
采集产出→客户库→补全→AI切换→扩张→新实体入库→新关系入图谱→图谱展示→开发信序列→AI写信→
微软邮箱执行（自动尝试+五态记录）。
"""
import os, sys, json, time, tempfile, threading, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='false', MISSION_DIRECTOR_ENABLED='false',
    WEBAI_ENABLED='false', IY_WEB_ENABLED='false', IMPORTYETI_ENABLED='false',
    SCHEDULER_ENABLED='false', OUTREACH_ENABLED='false')
from core.config import settings
settings.DATABASE_PATH = DBPATH
for k in ('EXPERT_MODE','MISSION_DIRECTOR_ENABLED','WEBAI_ENABLED','IY_WEB_ENABLED','IMPORTYETI_ENABLED','SCHEDULER_ENABLED','OUTREACH_ENABLED'):
    setattr(settings, k, False)

from core.memory.db import DB
db = DB()
db.upsert_leads([{'name': 'V39 Candle Importer', 'country': 'USA', 'kind': 'customer', 'zone': 'dev',
                  'product_domain': 'candle', 'shipments': 66, 'evidence': {'shipments': 66, 'customs': True}}])
norm = db._norm('V39 Candle Importer')
db.lead_update(norm, zone='dev', product_domain='candle', website='https://v39candle.example.com',
               emails='buy@v39candle.example.com', contact_person='Jane V39', intro='V39 candle importer.',
               audit=json.dumps({'ok': True}), icp_tier='A', icp_score=85, email_verified=1)
with db.c() as x:
    x.execute("INSERT INTO relationships(task_id,from_norm,from_name,from_type,to_norm,to_name,to_type,relation,evidence,source,confidence,depth,created_at,shipment_count,hs,product,evidence_level,discovered_via,parent_node,expansion_path,product_domain) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ('exp-v39e2e', norm, 'V39 Candle Importer', 'buyer', db._norm('V39 Wax Supplier'), 'V39 Wax Supplier', 'supplier',
               'buyer_to_supplier', '{"shipments":15}', 'importyeti_web', 0.9, 1, time.time(), 15, '3406', 'candle wax', 'STRONG',
               'customer_suppliers', 'V39 Candle Importer', 'V39 Candle Importer → V39 Wax Supplier', 'candle'))
db.save_expansion_task('exp-v39e2e', root=norm, params={'depth': 2}, strategies=['customer_suppliers'])
db.update_expansion_task('exp-v39e2e', gained=1, status='done', stopped_by='strategies_exhausted')

# 网络确定性：钉死抓取与 LLM（编排/状态机/落库全真实）
from core.intelligence import waterfall as _wf
from core.tools import contact_finder as _cf
_wf._fetch = lambda url, timeout=15: ''
_cf.ContactFinder._search_website_by_company = lambda self, *a, **k: None
from core.intelligence import ai_gateway as _gw
_LETTER = 'Subject: Birthday candles for V39 Candle Importer\n\nHi Jane, we are a birthday candle factory in Ningjin. We offer free samples, fast quotation and flexible capacity for importers. Reply for our catalog and a free sample pack today.'
def _stub_chat(prompt, **k):
    return _LETTER
_gw.PROVIDERS['local'] = ('本地桩', _stub_chat)
_gw.PROVIDERS['webai:chatgpt'] = ('GPT桩', _stub_chat)

from core.webui import app as webapp
srv = webapp.ThreadingHTTPServer(('127.0.0.1', 0), webapp.H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def api(path, payload=None, raw=False):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    if payload is None:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode()
            return resp.status, (data if raw else json.loads(data))
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')

# V1 客户库：采集产出的客户在库且状态派生
st, d = api('/api/leads?zone=dev&domain=candle')
lead = next((l for l in d.get('leads', []) if l['norm'] == norm), None)
check('V1 客户在库+品类过滤+业务状态', st == 200 and lead and lead.get('business_status_label'))

# V2 情报中心：补全状态/来源/验证时间
st, d = api('/api/account/%s' % norm)
check('V2 补全入口(完整度/已补全/来源)', st == 200 and (d.get('completeness') or 0) > 0 and d.get('known'))

# V3 编排层完整序列：从 DEV_VERIFY 跑到终态（含 ENRICH→ICP→LETTER→REVIEW(免审)→SEND(自动尝试)）
st, d = api('/api/account/%s/node' % norm, {'node': 'DEV_VERIFY'})
check('V3 序列启动', st == 200 and str(d.get('task_id', '')).startswith('dev-'))
final = None
for _ in range(90):
    _, t = api('/api/task/%s' % d['task_id'])
    if t.get('status') in ('done', 'failed'):
        final = t; break
    time.sleep(1)
res = (final or {}).get('result') or {}
ns = res.get('dev_status') or {}
check('V4 序列到终态', final is not None and final.get('status') == 'done', str(final and final.get('status')))
check('V5 补全/评分/写信节点真实执行', all(ns.get(n, {}).get('status') == 'SUCCESS' for n in ('ENRICH', 'ICP', 'DEV_LETTER')), str({k: v.get('status') for k, v in ns.items()}))
check('V6 质检免审自动通过', ns.get('DEV_REVIEW', {}).get('status') == 'SUCCESS' and 'approved' in str(ns.get('DEV_REVIEW', {}).get('note', '')) + str(res.get('review', '')), str(ns.get('DEV_REVIEW')))
# 发送：沙箱无浏览器 → 自动尝试失败但状态明确（不假装成功）
msg = db.latest_out_message(norm)
send = res.get('send') or {}
check('V7 发送自动尝试+状态明确(不伪装)', send and send.get('status') in ('ready_to_send', 'send_failed', 'sent') and msg.get('status') != 'sent' or send.get('status') == 'sent', str(send.get('status')) + '/' + str(msg.get('status')))

# V8 图谱：节点+边证据元数据
st, d = api('/api/trade-network?domain=candle')
e = next((x for x in d.get('edges', []) if x['f'] == 'V39 Candle Importer'), None)
check('V8 图谱边带证据(票数/等级/来源/HS/路径)', st == 200 and e and e.get('w') == 15 and e.get('lvl') == 'STRONG'
      and e.get('src') == 'importyeti_web' and e.get('hs') == '3406' and '→' in (e.get('epath') or ''))
n = next((x for x in d.get('nodes', []) if x['name'] == 'V39 Candle Importer'), None)
check('V9 图谱节点带norm可点击', n and n.get('norm') == norm and 'expanding' in n)

# V9 品类隔离：cookware 域看不到 candle 的边
st, d2 = api('/api/trade-network?domain=cookware')
check('V10 品类隔离(他域不见本域边)', not any(x['f'] == 'V39 Candle Importer' for x in d2.get('edges', [])))

# V10 扩张任务：人话停止原因 + 轨迹
st, d = api('/api/expansion-tasks')
t = next((x for x in d.get('tasks', []) if x.get('task_id') == 'exp-v39e2e'), None)
check('V11 扩张任务人话停止原因', t and t.get('stopped_by_label') == '策略全部耗尽')
check('V12 扩张轨迹(客户→供应商链)', t and any(x.get('from') == 'V39 Candle Importer' and x.get('to') == 'V39 Wax Supplier' for x in (t.get('trail') or [])))

# V11 客户详情：双向关联 + 已知/新发现可区分
st, d = api('/api/leads/%s' % norm)
rel = next((r for r in d.get('relationships', []) if r.get('to_name') == 'V39 Wax Supplier'), None)
check('V13 客户→供应商双向关联+来源可区分', st == 200 and rel and rel.get('source') and 'discovered_via' in rel)

# V12 UI 真实入口
st, html = api('/', raw=True)
need = ['graphEdgeClick', 'send_failed', 'stopped_by_label', '免人工审核', '扩张新发现', '在图谱中查看']
miss = [x for x in need if x not in html]
check('V14 UI含v39全部新入口(%s)' % ('缺:' + ','.join(miss) if miss else '全'), st == 200 and not miss)

srv.shutdown()
passed = sum(1 for _, ok in results if ok)
print('\n== v39 E2E: %d/%d ==' % (passed, len(results)))
if passed != len(results):
    sys.exit(1)
