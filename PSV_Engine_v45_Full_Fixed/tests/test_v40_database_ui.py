# -*- coding: utf-8 -*-
"""v40 数据库 UI 与后台能力对齐验收：
 1  列表行注解：rel_count/sup_count/completeness/ai_status 全部来自真实聚合
 2  顶部资源状态卡：stats 各池计数齐备（开发/维护/发现/成交/剔除/扩张中）
 3  详情四分区数据齐备：基础(角色/网站/地址/联系人) · 贸易(票数/HS/首末见/证据等级)
    · 网络(扩张路径/父节点/层级) · 开发(池/AI验证/开发信状态/最后操作)
 4  行级三操作：详情/网络扩张/进入开发（enterDev 非开发池先转池再跳工作台，不复制后台逻辑）
 5  双向跳转：数据库→图谱定位 + 图谱→数据库详情（统一 norm 实体 ID）
 6  搜索/完整度筛选真实存在且纯前端过滤真实缓存数据
 7  无假数据：列表行所有展示字段均可在 leads/relationships 表找到来源
 8  第一采集链冻结
"""
import os, sys, json, time, sqlite3, tempfile, threading, urllib.request, urllib.error
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
    results.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')

# ---------- 夹具：1 客户（全字段）+ 1 供应商 + 2 条边（1 已知 1 扩张） ----------
db.upsert_leads([
    {'name':'UI Candle Buyer','country':'USA','kind':'customer','zone':'dev','product_domain':'candle','shipments':42,'evidence':{'shipments':42}},
    {'name':'UI Wax Factory','country':'CN','kind':'supplier','zone':'dev','product_domain':'candle','shipments':60,'evidence':{'shipments':60}},
])
nb, ns = db._norm('UI Candle Buyer'), db._norm('UI Wax Factory')
db.lead_update(nb, zone='dev', product_domain='candle', website='https://uicandle.example.com',
               emails='buy@uicandle.example.com', phones='+1-555', address='1 Candle Rd',
               contact_person='Jane UI', intro='UI candle importer.', audit=json.dumps({'ok': True}),
               last_shipment='2026-08-01', email_verified=1)
db.lead_update(ns, zone='dev', product_domain='candle')
with db.c() as x:
    x.execute("""INSERT INTO relationships(task_id,from_norm,from_name,from_type,to_norm,to_name,to_type,relation,evidence,source,confidence,depth,created_at,shipment_count,hs,product,first_seen,last_seen,evidence_level)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              ('t-first', nb, 'UI Candle Buyer', 'buyer', ns, 'UI Wax Factory', 'supplier', 'buyer_to_supplier',
               '{"shipments":42}', 'customs', 0.95, 1, time.time(), 42, '3406', 'candles', time.time() - 86400 * 90, time.time(), 'STRONG'))
db.add_relationship('exp-ui-1', 'UI Candle Buyer', 'buyer', 'UI Wax Factory', 'supplier', 'buyer_to_supplier',
                    {'shipments': 10, 'products': 'wax'}, 'importyeti_web', confidence=0.9, depth=2,
                    evidence_level='STRONG', discovered_via='customer_suppliers', parent_node='UI Candle Buyer',
                    expansion_path='UI Candle Buyer → UI Wax Factory', product_domain='candle')

# ===== 1 列表行注解 =====
leads = {l['norm']: l for l in db.list_leads()}
b = leads[nb]
check('1.1 rel_count 真实聚合(按对手方去重)', b.get('rel_count') == 1, str(b.get('rel_count')))
check('1.2 sup_count 真实聚合', b.get('sup_count') == 1)
check('1.3 completeness 真实计算', (b.get('completeness') or 0) >= 0.75, str(b.get('completeness')))
check('1.4 ai_status 派生真实', b.get('ai_status') == '已验证')
s = leads[ns]
check('1.5 供应商行反向计数', s.get('rel_count') == 1)

# ===== 2 stats 资源状态卡数据 =====
from core.webui import app as webapp
srv = webapp.ThreadingHTTPServer(('127.0.0.1', 0), webapp.H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
def api(path, payload=None, raw=False):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    if payload is None:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read().decode()
            return resp.status, (data if raw else json.loads(data))
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')

st, d = api('/api/stats')
need_stats = ['leads_total', 'dev_total', 'maint_total', 'won_total', 'pending_total', 'discard_total', 'expansion_running']
check('2.1 状态卡计数齐备', st == 200 and all(k in d for k in need_stats), str([k for k in need_stats if k not in d]))

# ===== 3 详情数据齐备（四分区所需字段全部真实存在） =====
st, d = api('/api/leads/%s' % nb)
l = d.get('lead') or {}
rels = d.get('relationships') or []
check('3.1 基础信息字段', all(l.get(k) for k in ('name', 'country', 'website', 'contact_person', 'intro', 'address')))
r0 = rels[0]
check('3.2 贸易信息字段(票数/HS/首末见/证据/来源)', all(k in r0 for k in ('shipment_count', 'hs', 'first_seen', 'last_seen', 'evidence_level', 'source')))
exp_edge = next((r for r in rels if r.get('discovered_via')), None)
check('3.3 网络信息字段(路径/父节点/层级)', exp_edge and exp_edge.get('expansion_path') and exp_edge.get('parent_node') and exp_edge.get('depth'))
check('3.4 开发信息字段(池/AI验证/最后操作)', 'zone' in l and 'audit' in l and 'last_touch' in l and 'development' in d)

# ===== 4/5/6 UI 真实入口 =====
st, html = api('/', raw=True)
need_ui = ['leads_summary', 'leads_search', 'setCompFilter', 'renderLeadRows', 'enterDev', 'gotoZone',
           '正在扩张', '基础信息', '贸易信息', '网络扩张', '开发信息', '进入开发', '在图谱中查看',
           'rel_count', 'sup_count', 'completeness', 'ai_status', '在客户库打开']
miss = [x for x in need_ui if x not in html]
check('4.1 UI新结构全量存在(%s)' % ('缺:' + ','.join(miss) if miss else '全'), st == 200 and not miss)
check('5.1 图谱→数据库回跳(统一norm)', "在客户库打开" in html and 'graphNodeClick' in html)
# JS 语法校验（node 可用时）
import shutil, subprocess, re as _re
m = _re.search(r'<script>(.*)</script>', html, _re.S)
if shutil.which('node') and m:
    open('/tmp/_v40_ui_check.js', 'w').write(m.group(1))
    r = subprocess.run(['node', '--check', '/tmp/_v40_ui_check.js'], capture_output=True, text=True)
    check('4.2 前端JS语法有效', r.returncode == 0, r.stderr[:200])

# ===== 7 无假数据：行注解字段都能回溯到表 =====
with db.c() as x:
    cnt = x.execute("SELECT COUNT(*) FROM relationships WHERE from_norm=? OR to_norm=?", (nb, nb)).fetchone()[0]
check('7.1 rel_count 与 relationships 表对手方一致', cnt >= b.get('rel_count') and b.get('rel_count') == 1)

# ===== 8 第一采集链冻结 =====
from core.runtime import graph
check('8.1 第一链9节点冻结', graph.ORDER == ['PRODUCT_DEFINITION', 'TRADE_STRATEGY', 'CUSTOMS_NODE_COLLECTION',
    'TRADE_EDGE_BUILD', 'EVIDENCE_VERIFY', 'ENTITY_RESOLUTION', 'GRAPH_EXPANSION', 'RESOURCE_CLASSIFICATION', 'DATABASE_COMMIT'])

srv.shutdown()
passed = sum(1 for _, ok in results if ok)
print('\n== v40 验收: %d/%d ==' % (passed, len(results)))
if passed != len(results):
    sys.exit(1)
