# -*- coding: utf-8 -*-
"""v38 专项审计修复验收（基于真实状态/真实调用链路）：
 1  客户业务状态机：派生不存储，优先级 已成交>维护中>已剔除>已联系>开发中>可开发>已验证>补全中>新发现
 2  补全扩展：intro 进入 waterfall FIELDS；meta 简介提取；逐字段来源/验证时间；is_enriched 标志
 3  AI 网关三链路：qwen 引擎注册、AI_PROVIDER_CHAIN 可配路由、chat_json 结构化解析、全灭原因如实
 4  Outlook 自动发送：预检三类失败路径（无草稿/无收件人/浏览器未启动）全停在可恢复位置，绝不假装成功
 5  编排统一：/api/account/<norm>/node 经编排层异步任务入口（start_node），不再同步直跑
 6  图谱操作中心：/api/trade-network 节点携带 norm 与 expanding 标记
 7  扩张预检：web 策略在 IY 网页未就绪时同步 503 明确报错（不再异步吞没）
 8  扩张单源化：expansion_activity 读 expansion_tasks；expansion_jobs 表与 begin/finish_expansion 已删
 9  旧代码清理：build_development_diagnostic_package 删除；ContactFinder 精简（enrich 家族移除）
10  开发信个性化：pitch 素材含联系人与公司简介
11  第一采集链冻结：graph.ORDER 仍是 9 节点原序列（不增删不改序）
"""
import os, sys, json, time, sqlite3, tempfile
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
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')

# ---------- 夹具 ----------
db.upsert_leads([
    {'name':'Kitchen World Imports','country':'USA','kind':'customer','zone':'dev','product_domain':'cookware',
     'shipments':60,'website':'https://kitchenworld.example.com','evidence':{'shipments':60,'customs':True}},
    {'name':'Fresh Find Co','country':'USA','kind':'customer','zone':'pool','product_domain':'cookware',
     'shipments':5,'evidence':{'shipments':5,'customs':True}},
])
norm = db._norm('Kitchen World Imports')
norm2 = db._norm('Fresh Find Co')
db.lead_update(norm, website='https://kitchenworld.example.com', zone='dev', product_domain='cookware')

# ===== 1 业务状态机（派生，不存储；outreach_state 由 messages 表派生，单一事实源） =====
bs = DB.business_status
check('1.1 新发现(无验证无邮箱)', bs({'zone': 'pool'})[0] == 'new')
check('1.2 已验证', bs({'zone': 'pool', 'audit': '{"ok":true}'})[0] == 'verified')
check('1.3 可开发(A带+邮箱)', bs({'zone': 'pool', 'audit': '{"ok":true}', 'icp_tier': 'A', 'emails': 'a@b.com'})[0] == 'developable')
check('1.4 开发中(优先于可开发)', bs({'zone': 'pool', 'icp_tier': 'A', 'emails': 'a@b.com', 'development_status': 'running'})[0] == 'developing')
check('1.5 已联系(优先于可开发)', bs({'zone': 'pool', 'icp_tier': 'A', 'emails': 'a@b.com', 'outreach_state': 'sent'})[0] == 'contacted')
check('1.6 已剔除(优先于已联系)', bs({'zone': 'discard', 'outreach_state': 'sent'})[0] == 'discard')
check('1.7 维护中', bs({'zone': 'maint', 'outreach_state': 'sent'})[0] == 'maint')
check('1.8 已成交(最高优先级)', bs({'zone': 'won', 'outreach_state': 'sent', 'development_status': 'running'})[0] == 'won')
with db.c() as x: cols = {r[1] for r in x.execute('PRAGMA table_info(leads)').fetchall()}
check('1.9 派生状态不存库(leads无business_status列)', 'business_status' not in cols)
db.add_message(norm2, 'out', 'email', 'real sent letter', draft=0)
leads = {l['norm']: l for l in db.list_leads()}
check('1.10 list_leads 注解派生状态(真实消息→已联系)', leads[norm2].get('business_status') == 'contacted' and leads[norm2].get('business_status_label') == '已联系')
with db.c() as x: x.execute("DELETE FROM messages WHERE lead_norm=?", (norm2,))

# ===== 2 补全扩展：intro + 来源/验证时间 + is_enriched =====
from core.intelligence import waterfall as wf
check('2.1 intro 进入 waterfall FIELDS', 'intro' in wf.FIELDS and 'linkedin' in wf.FIELDS)
html = '<html><head><meta name="description" content="Kitchen World Imports is a cookware importer and distributor based in Chicago."><meta property="og:description" content="og fallback"></head><body></body></html>'
intro = wf._meta_intro(html)
check('2.2 meta 简介提取', intro and 'cookware' in intro)
got = wf._regex_extract('<a href="mailto:buy@kitchenworld.example.com">m</a> <a href="https://www.linkedin.com/in/janedoe">in</a>')
check('2.3 regex 提取邮箱+linkedin', 'buy@kitchenworld.example.com' in (got.get('emails') or '') and 'janedoe' in (got.get('linkedin') or ''))
from core.intelligence import account as acc
db.lead_update(norm, website='https://kitchenworld.example.com', emails='sales@kitchenworld.example.com',
               intro='A cookware importer.', contact_person='Jane', email_verified=1)
db.add_enrichment_event(norm, 'website', 'meta_regex', 'https://kitchenworld.example.com', True)
db.add_enrichment_event(norm, 'emails', 'regex', 'sales@kitchenworld.example.com', True)
a = acc.get(norm)
known = a.get('known') or {}
check('2.4 逐字段来源留痕', known.get('website', {}).get('source') == 'meta_regex')
check('2.5 逐字段验证时间', bool(known.get('emails', {}).get('verified_at')))
check('2.6 is_enriched 标志', a.get('is_enriched') is True)
check('2.7 完整度>0', (a.get('completeness') or 0) >= 0.5)
check('2.8 业务状态进入客户情报', a.get('business_status') in ('verified', 'developable', 'enriching') and a.get('business_status_label'))

# ===== 3 AI 网关三链路 =====
from core.intelligence import ai_gateway as gw
check('3.1 qwen 引擎注册', 'webai:qwen' in gw.PROVIDERS)
from core.tools import web_ai
check('3.2 qwen 浏览器引擎存在', 'qwen' in web_ai.ENGINES)
old_chain = getattr(settings, 'AI_PROVIDER_CHAIN', '')
settings.AI_PROVIDER_CHAIN = 'webai:qwen,local,bogus'
check('3.3 AI_PROVIDER_CHAIN 可配路由(过滤无效)', gw.route_order() == ['webai:qwen', 'local'])
settings.AI_PROVIDER_CHAIN = ''
check('3.4 兼容旧 AI_PRIMARY 回退', gw.route_order()[0] == str(getattr(settings, 'AI_PRIMARY', 'local') or 'local').lower())
_orig = dict(gw.PROVIDERS)
gw.PROVIDERS['local'] = ('本地', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
gw.PROVIDERS['webai:qwen'] = ('千问', lambda *a, **k: 'qwen says {"tier": "A"}')
settings.AI_PROVIDER_CHAIN = 'local,webai:qwen'
r = gw.chat('hello', task='v38test')
check('3.5 主失败自动切换+记录fallback', r['ok'] and r['provider'] == 'webai:qwen' and r['fallback_from'] == 'local')
j = gw.chat_json('give json', task='v38test')
check('3.6 chat_json 结构化解析', j['ok'] and j['json'] == {'tier': 'A'})
settings.AI_PROVIDER_CHAIN = 'local'
r2 = gw.chat('hello', task='v38test')
check('3.7 全灭诚实报错(带原因)', (not r2['ok']) and r2['errors'] and 'offline' in r2['errors'][0]['reason'])
gw.PROVIDERS.clear(); gw.PROVIDERS.update(_orig)
settings.AI_PROVIDER_CHAIN = old_chain
calls = db.list_ai_calls()
check('3.8 ai_calls 观测留痕', any(c.get('task') == 'v38test' for c in calls))

# ===== 4 Outlook 自动发送预检 =====
from core.tools import outlook_send as osl
ok, ctx, err = osl.preflight(norm)
check('4.1 无草稿→明确报错', (not ok) and '草稿' in err)
db.add_message(norm, 'out', 'email', 'Subject: Hi Jane\n\nHello from PSV', draft=1)
db.lead_update(norm, emails='', contact_person='')
ok, ctx, err = osl.preflight(norm)
check('4.2 无收件人→明确报错', (not ok) and '收件人' in err)
db.lead_update(norm, emails='sales@kitchenworld.example.com')
old_cdp = getattr(settings, 'IY_WEB_CDP_ENABLED', False)
settings.IY_WEB_CDP_ENABLED = False
ok, ctx, err = osl.preflight(norm)
check('4.3 浏览器未启动→明确报错', (not ok) and ('9222' in err or '浏览器' in err))
settings.IY_WEB_CDP_ENABLED = old_cdp
r = osl.auto_send(norm)
msg = db.latest_out_message(norm)
# v39 五态语义：失败为 ready_to_send(未尝试) 或 send_failed(尝试过+原因)，均不假装 sent
check('4.4 失败停在可恢复位置(不假装sent)', (not r['ok']) and r.get('status') in ('ready_to_send','send_failed') and msg.get('status') != 'sent')
settings.IY_WEB_CDP_ENABLED = True
import core.tools.web_ai as _wai
_wai._cdp_alive = lambda url: True
ok, ctx, err = osl.preflight(norm)
check('4.5 预检通过给出完整上下文', ok and ctx.get('to') == 'sales@kitchenworld.example.com' and ctx.get('subject') == 'Hi Jane' and 'PSV' in ctx.get('body', ''))
settings.IY_WEB_CDP_ENABLED = old_cdp

# ===== 5/6/7 路由级验收（真实 HTTP 调用链路） =====
import threading
from core.webui import app as webapp
srv = webapp.ThreadingHTTPServer(('127.0.0.1', 0), webapp.H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
import urllib.request, urllib.error
def api(path, payload=None):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    if payload is None:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')

# 6 图谱节点携带 norm
with db.c() as x:
    x.execute("INSERT INTO relationships(from_name,from_type,to_name,to_type,relation,shipment_count,confidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
              ('Kitchen World Imports', 'buyer', 'Shenzhen Pot Co', 'supplier', 'buys_from', 7, 0.9, time.time()))
st, d = api('/api/trade-network')
nodes = d.get('nodes') or []
kw = next((n for n in nodes if n['name'] == 'Kitchen World Imports'), None)
check('6.1 图谱节点携带稳定norm', st == 200 and kw and kw.get('norm') == norm)
check('6.2 未入库实体norm为空不伪造', any(n['name'] == 'Shenzhen Pot Co' and n.get('norm') == '' for n in nodes))
check('6.3 expanding 标记字段存在', all('expanding' in n for n in nodes))

# 7 扩张预检：web 策略 + IY 未就绪 → 503 同步报错（钉死 available=False 保证确定性）
from core.tools import iy_web as _iy
_orig_avail = _iy.available
_iy.available = lambda: False
st, d = api('/api/network-expansion', {'seed_norms': [norm], 'max_new': 5})
_iy.available = _orig_avail
check('7.1 web策略IY未就绪→503明确报错', st == 503 and (not d.get('ok')) and 'ImportYeti' in (d.get('error') or ''))
st, d = api('/api/network-expansion', {'seed_norms': [norm], 'max_new': 5, 'strategies': ['same_product_importers']})
check('7.2 本地策略正常受理', st == 200 and d.get('ok') and str(d.get('task_id', '')).startswith('expand-'))

# 5 编排统一：account node → 编排层异步任务
st, d = api('/api/account/%s/node' % norm, {'node': 'bogus'})
check('5.1 非法节点→400+allowed', st == 400 and d.get('allowed'))
st, d = api('/api/account/%s/node' % norm, {'node': 'DEV_VERIFY'})
check('5.2 节点经编排层异步受理(dev-任务)', st == 200 and d.get('ok') and str(d.get('task_id', '')).startswith('dev-'))
time.sleep(2.5)
st, t = api('/api/task/%s' % d['task_id'])
check('5.3 编排任务真实存在可轮询', st == 200 and t.get('status') in ('running', 'done', 'failed'))

# auto-send 路由：无草稿 norm → 409
st, d = api('/api/outreach/auto-send', {'norm': norm2})
check('5.4 auto-send失败路径409(不假装成功)', st == 409 and (not d.get('ok')) and d.get('error'))

# ===== 8 扩张单源化 =====
acts = db.expansion_activity()
check('8.1 expansion_activity 读 expansion_tasks', isinstance(acts, list))
with db.c() as x: tables = {r[0] for r in x.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
check('8.2 expansion_jobs 表已删除', 'expansion_jobs' not in tables)
check('8.3 begin/finish_expansion 已删', not hasattr(DB, 'begin_expansion') and not hasattr(DB, 'finish_expansion'))

# ===== 9 旧代码清理 =====
from core.runtime import experts
check('9.1 build_development_diagnostic_package 已删', not hasattr(experts, 'build_development_diagnostic_package'))
from core.tools import contact_finder as cf
check('9.2 ContactFinder.enrich 家族已删', not hasattr(cf.ContactFinder, 'enrich') and not hasattr(cf, 'enrich_one') and not hasattr(cf, 'PROGRESS'))
check('9.3 ContactFinder 核心能力保留', hasattr(cf.ContactFinder, '_extract_from_html'))

# ===== 10 开发信个性化素材 =====
from core.tools import pitch
db.lead_update(norm, contact_person='Jane Doe', intro='A cookware importer and distributor.')
src = pitch.letter_prompt(db.get_lead(norm)) if callable(getattr(pitch, 'letter_prompt', None)) else ''
check('10.1 联系人入素材', 'Jane Doe' in src)
check('10.2 公司简介入素材', 'cookware importer' in src)

# ===== 11 第一采集链冻结 =====
from core.runtime import graph
check('11.1 第一采集链9节点冻结', graph.ORDER == ['PRODUCT_DEFINITION', 'TRADE_STRATEGY', 'CUSTOMS_NODE_COLLECTION',
    'TRADE_EDGE_BUILD', 'EVIDENCE_VERIFY', 'ENTITY_RESOLUTION', 'GRAPH_EXPANSION', 'RESOURCE_CLASSIFICATION', 'DATABASE_COMMIT'])

srv.shutdown()
passed = sum(1 for _, ok, _ in results if ok)
print('\n== v38 验收: %d/%d ==' % (passed, len(results)))
if passed != len(results):
    sys.exit(1)
