# -*- coding: utf-8 -*-
"""v38 E2E 真实系统验收：临时库 + 真实 HTTP API + 真实 UI HTML，全链路连通性。
覆盖：客户库(业务状态) → 客户情报中心 → 编排层节点启动 → 开发信发送包 → 自动发送(失败可恢复)
     → 网络扩张预检/受理 → 图谱操作中心(norm/expanding) → 扩张任务 → AI观测 → UI 入口真实存在。
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
db.upsert_leads([{'name': 'E2E Kitchen Importer', 'country': 'USA', 'kind': 'customer', 'zone': 'dev',
                  'product_domain': 'cookware', 'shipments': 88, 'evidence': {'shipments': 88, 'customs': True}}])
norm = db._norm('E2E Kitchen Importer')
db.lead_update(norm, zone='dev', website='https://e2ekitchen.example.com', emails='buy@e2ekitchen.example.com',
               contact_person='Jane E2E', intro='E2E cookware importer.', audit=json.dumps({'ok': True}),
               icp_tier='A', icp_score=82, email_verified=1)
db.add_message(norm, 'out', 'email', 'Subject: E2E Hello\n\nHi Jane, PSV here.', draft=1)
with db.c() as x:
    x.execute("INSERT INTO relationships(from_name,from_type,to_name,to_type,relation,shipment_count,confidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
              ('E2E Kitchen Importer', 'buyer', 'E2E Supplier Ltd', 'supplier', 'buys_from', 12, 0.95, time.time()))

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

# 1 客户库：业务状态派生随列表下发
st, d = api('/api/leads?zone=dev')
lead = next((l for l in d.get('leads', []) if l['norm'] == norm), None)
check('E1 客户库列表携带业务状态标签', st == 200 and lead and lead.get('business_status') and lead.get('business_status_label'))

# 2 客户情报中心五问 + 业务状态 + 补全标志
st, d = api('/api/account/%s' % norm)
check('E2 情报中心(已知/缺失/下一步/完整度/已补全/状态)', st == 200 and d.get('known') and 'missing' in d
      and 'next_actions' in d and (d.get('completeness') or 0) > 0 and d.get('is_enriched') is True
      and d.get('business_status_label'))

# 3 编排层节点启动（异步 dev- 任务，可轮询到终态）
# 沙箱无外网确定性：钉死网页抓取/网站搜索（节点仍真实执行真实状态机，不伪造结果）
from core.intelligence import waterfall as _wf
from core.tools import contact_finder as _cf
_wf._fetch = lambda url, timeout=15: ''
_cf.ContactFinder._search_website_by_company = lambda self, *a, **k: None
# 钉死 LLM 出口为即时可判的本地桩（编排/状态机/落库全真实，仅模型返回 canned 文本）
from core.intelligence import ai_gateway as _gw
_GW_ORIG = dict(_gw.PROVIDERS)
_LETTER = 'Subject: Cookware supply for E2E Kitchen Importer\n\nHi Jane, we manufacture cookware in our own factory with free samples, fast quotation, flexible capacity and direct pricing for importers like you. Reply for our catalog and a free sample pack today.'
_REVIEW = '{"pass": true, "reason": "ok"}'
def _stub_chat(prompt, system=None, temperature=0.3, max_tokens=None, timeout=None):
    return _REVIEW if ('审核' in prompt or 'review' in prompt.lower()) else _LETTER
_gw.PROVIDERS['local'] = ('本地桩', _stub_chat)
_gw.PROVIDERS['webai:chatgpt'] = ('GPT桩', _stub_chat)
st, d = api('/api/account/%s/node' % norm, {'node': 'DEV_VERIFY'})
check('E3 节点经编排层受理', st == 200 and d.get('ok') and str(d.get('task_id', '')).startswith('dev-'))
tid = d.get('task_id')
final = None
for _ in range(60):
    _, t = api('/api/task/%s' % tid)
    if t.get('status') in ('done', 'failed'):
        final = t; break
    time.sleep(1)
check('E4 编排任务到达终态(真实执行)', final is not None and final.get('status') == 'done')

# 5 开发信发送包（compose：状态推进 approved + 真实 compose_url）
st, d = api('/api/outreach/compose', {'norm': norm})
check('E5 compose 发送包(approved+outlook链接)', st == 200 and d.get('ok') and 'outlook' in (d.get('compose_url') or '') and d.get('to') == 'buy@e2ekitchen.example.com')

# 6 自动发送：无可控浏览器时必须明确报错、停在可恢复位置（绝不假装 sent）
# （沙箱 9222 可能有残余浏览器但无外网，钉死 CDP 开关保证确定性——走预检失败路径）
_old_cdp = getattr(settings, 'IY_WEB_CDP_ENABLED', False)
settings.IY_WEB_CDP_ENABLED = False
st, d = api('/api/outreach/auto-send', {'norm': norm})
settings.IY_WEB_CDP_ENABLED = _old_cdp
msg = db.latest_out_message(norm)
if st == 200 and d.get('ok'):
    check('E6 自动发送真实成功(浏览器可用)', msg.get('status') == 'sent')
else:
    check('E6 自动发送失败明确报错+停在ready_to_send(可恢复)', st == 409 and d.get('error') and msg.get('status') in ('ready_to_send', 'approved', 'drafted') and msg.get('status') != 'sent')

# 7 网络扩张：web 策略未就绪 → 同步 503；本地策略 → 受理并产生 expansion_task
from core.tools import iy_web as _iy
_orig = _iy.available; _iy.available = lambda: False
st, d = api('/api/network-expansion', {'seed_norms': [norm], 'max_new': 5})
_iy.available = _orig
check('E7 扩张预检503(错误不再异步吞没)', st == 503 and 'ImportYeti' in (d.get('error') or ''))
st, d = api('/api/network-expansion', {'seed_norms': [norm], 'max_new': 5, 'strategies': ['same_product_importers']})
check('E8 本地策略扩张受理', st == 200 and d.get('ok'))
time.sleep(3)
st, d = api('/api/expansion-tasks')
check('E9 扩张任务真实落库可查', st == 200 and any(t.get('root') and norm in str(t.get('root')) for t in d.get('tasks', [])))

# 10 图谱操作中心：节点 norm + expanding 字段
st, d = api('/api/trade-network')
kw = next((n for n in d.get('nodes', []) if n['name'] == 'E2E Kitchen Importer'), None)
check('E10 图谱节点携带norm+expanding', st == 200 and kw and kw.get('norm') == norm and 'expanding' in kw)

# 11 AI 观测接口存在
st, d = api('/api/ai-calls')
check('E11 AI观测接口可用', st == 200 and 'calls' in d)

# 12 版本与 UI 入口真实存在（图谱操作中心/自动发送/业务状态/节点按钮）
st, html = api('/', raw=True)
need = ['graphNodeClick', 'autoSend', 'business_status_label', 'accNode', 'graph_node_detail']
missing = [x for x in need if x not in html]
check('E12 UI真实含v38入口(%s)' % ('缺:' + ','.join(missing) if missing else '全'), st == 200 and not missing)

# 13 第一链冻结（HTTP 层 stats 可用即编排完整）
st, d = api('/api/stats')
check('E13 stats/版本v38+', st == 200 and str(d.get('version', '')).startswith(('v38','v39','v40')))

srv.shutdown()
passed = sum(1 for _, ok in results if ok)
print('\n== v38 E2E: %d/%d ==' % (passed, len(results)))
if passed != len(results):
    sys.exit(1)
