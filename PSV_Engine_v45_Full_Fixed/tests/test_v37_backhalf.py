# -*- coding: utf-8 -*-
"""v37 后半程架构重构验收：
 1  数据模型迁移：contacts/expansion_tasks/sender_profile/ai_calls/enrichment_events 新表
    + leads(icp_*/email_verified) + messages(status/sent_at) 新列
 2  AI_REASONING_GATEWAY：主备可配置路由 + 失败自动切换 + ai_calls 观测 + 结论优先包装
 3  字段级 WATERFALL：邮箱语法/去重/角色降级/MX缓存；enrich_lead 离线安全（不崩溃、留痕、缺口如实）
 4  联系人发现：邮箱排列排序 + 公司模式检测 + 推荐唯一第一名 + contacts 落库
 5  ICP 资格：Fit×Intent×Timing 分层 + 分数带 + 可解释原因 + 可联系性独立 + 写回 leads
 6  ACCOUNT_INTELLIGENCE：已知/缺失/下一步/为什么/证据 五问齐备
 7  开发序列重构：9 节点 DEV_ORDER；小编排删除；ENRICH/CONTACT/ICP 离线成功；
    LETTER 离线失败即停（不伪造成功）；n_send 半自动——绝不调用 SMTP，只产发送包
 8  扩张任务化：6 策略注册表、expansion_tasks 进度、本地策略真实执行、断点续跑不重跑
 9  第一采集链冻结：graph.ORDER 仍是 9 节点原序列
10  半自动消息状态机：drafted→approved→sent/followup
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
now = time.time()
# 夹具：一个开发池客户（有贸易规模、有网站、无邮箱）+ 一个同域未分区客户 + 一个跨角色实体
db.upsert_leads([
    {'name':'Kitchen World Imports','country':'USA','kind':'customer','zone':'dev','product_domain':'cookware',
     'shipments':60,'last_shipment':'2026-08-01','website':'https://kitchenworld.example.com',
     'evidence':{'shipments':60,'customs':True}},
    {'name':'Home Hearth Trading','country':'USA','kind':'customer','zone':'pool','product_domain':'cookware',
     'shipments':12,'evidence':{'shipments':12,'customs':True}},
    {'name':'Dual Role Co','country':'USA','kind':'customer','zone':'dev','product_domain':'cookware',
     'shipments':5,'evidence':{'shipments':5,'customs':True}},
])
db.add_relationship('t0','Kitchen World Imports','buyer','Linyi Enamel Works','supplier','buyer_to_supplier',
                    {'shipments':30,'products':'enamel cookware'},'customs_raw',confidence=0.9,depth=1,evidence_level='STRONG')
db.add_relationship('t0','Dual Role Co','buyer','Some Buyer Inc','supplier','buyer_to_supplier',
                    {'shipments':3},'customs_raw',confidence=0.8,depth=1,evidence_level='MEDIUM')
db.add_relationship('t0','Hebei Casting Co','supplier','Dual Role Co','buyer','supplier_to_customer',
                    {'shipments':8},'customs_raw',confidence=0.9,depth=1,evidence_level='STRONG')
NORM = DB._norm('Kitchen World Imports')
# upsert_leads 只保证基础列；夹具关键字段显式 lead_update 保证确定性
db.lead_update(NORM, zone='dev', product_domain='cookware', shipments=60,
               last_shipment='2026-08-01', website='https://kitchenworld.example.com', emails='')
db.lead_update(DB._norm('Home Hearth Trading'), zone='pool', product_domain='cookware', shipments=12)
db.lead_update(DB._norm('Dual Role Co'), zone='dev', product_domain='cookware', shipments=5, kind='customer')
# Dual Role Co 同时以供应商角色出现在关系中（跨市场/跨角色证据）
db.add_relationship('t0','Dual Role Co','supplier','East Coast Retail','buyer','supplier_to_customer',
                    {'shipments':6},'customs_raw',confidence=0.9,depth=1,evidence_level='STRONG')
settings.LLM_BASE_URL = 'http://127.0.0.1:9'  # 本地模型指向必拒端口，离线即时失败不悬挂
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), name, detail if not cond else '')

# ---------- 1 数据模型迁移 ----------
with sqlite3.connect(DBPATH) as c:
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    lead_cols = {r[1] for r in c.execute('PRAGMA table_info(leads)')}
    msg_cols = {r[1] for r in c.execute('PRAGMA table_info(messages)')}
check('1.1 新表齐备', {'contacts','expansion_tasks','sender_profile','ai_calls','enrichment_events'} <= tables,
      str({'contacts','expansion_tasks','sender_profile','ai_calls','enrichment_events'}-tables))
check('1.2 leads 新列', {'icp_score','icp_tier','icp_reasons','email_verified'} <= lead_cols)
check('1.3 messages 状态机列', {'status','sent_at'} <= msg_cols)

# ---------- 2 AI 网关 ----------
from core.intelligence import ai_gateway
check('2.1 主备可配置默认本地优先', ai_gateway.route_order()[0] == 'local')
# v38：'webai' 单键已拆分为 webai:chatgpt/deepseek/qwen 三链路，主备反转语义不变
settings.AI_PRIMARY = 'webai:chatgpt'
check('2.2 主备反转生效', ai_gateway.route_order()[0] == 'webai:chatgpt')
settings.AI_PRIMARY = 'local'
# 失败切换：主 provider 抛异常 → 自动切备并记录 fallback_from（用完恢复，避免污染后续用例）
_orig_providers = dict(ai_gateway.PROVIDERS)
_captured = {}
def _fake_webai(prompt, **k):
    _captured['prompt'] = prompt; return '结论：可用。'
ai_gateway.PROVIDERS['local'] = ('本地模型(测试)', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))
ai_gateway.PROVIDERS['webai:chatgpt'] = ('浏览器AI(测试)', _fake_webai)
r = ai_gateway.chat('测试', task='unit_test')
check('2.3 失败自动切换', r['ok'] and r['provider'] == 'webai:chatgpt' and 'local' in r['fallback_from'], str(r))
calls = db.list_ai_calls(limit=10)
check('2.4 调用全量观测', any(c['task'] == 'unit_test' for c in calls) and any(c['fallback_from'] for c in calls))
r2 = ai_gateway.conclude('给结论', task='unit_test2')
check('2.5 结论优先包装', '第一句必须是一句自然语言结论' in (_captured.get('prompt') or ''))
ai_gateway.PROVIDERS.clear(); ai_gateway.PROVIDERS.update(_orig_providers)

# ---------- 3 字段级 waterfall ----------
from core.intelligence import waterfall
pairs = waterfall.verify_emails(['INFO@Acme.com', 'info@acme.com', 'john.doe@acme.com', 'bad-email', 'sales@acme.com'])
emails = [e for e, s in pairs]
check('3.1 去重+小写', emails.count('info@acme.com') == 1 and 'INFO@Acme.com' not in emails)
check('3.2 非法邮箱标记', dict((e, s) for e, s in pairs).get('bad-email') == 'invalid')
check('3.3 个人邮箱排在角色邮箱前', emails.index('john.doe@acme.com') < emails.index('info@acme.com'))
waterfall._mx_cache['example.com'] = True
check('3.4 MX 缓存每域名一次', waterfall.mx_ok('example.com') is True and waterfall.mx_ok('') is None)
# enrich_lead 离线安全：网络/LLM 全灭也不崩溃、如实报告缺口（bing 搜索一并屏蔽，测试自持）
waterfall._fetch = lambda url, timeout=15: (_ for _ in ()).throw(RuntimeError('offline'))
import core.tools.contact_finder as _cf
_cf.ContactFinder._search_website_by_company = lambda self, name, country='USA': None
r = waterfall.enrich_lead(NORM)
check('3.5 离线补全不崩溃且如实报缺口', r.get('ok') and 'emails' in r.get('still_missing', []), str(r)[:200])
check('3.6 补全事件留痕', len(db.list_enrichment_events(NORM)) >= 1)

# ---------- 4 联系人发现 ----------
from core.intelligence import contacts as cm
cands = cm.generate_candidates('John Doe', 'acme.com')
check('4.1 first.last 排第一', cands and cands[0][0] == 'john.doe@acme.com', str(cands[:2]))
check('4.2 模式检测', cm.detect_pattern('j.smith@acme.com', 'john', 'smith') == 'f.last')
cands2 = cm.generate_candidates('Jane Roe', 'acme.com', known_emails=['j.smith@acme.com'])
check('4.3 已知模式置顶', cands2 and cands2[0][1] == 'f.last', str(cands2[:2]))
db.lead_update(NORM, contact_person='John Doe')
waterfall._mx_cache['kitchenworld.example.com'] = True  # 域名 MX 有效 → 推荐候选可得 mx_ok
r = cm.find_contacts(NORM)
rec = r.get('recommended') or {}
check('4.4 排列候选落库+推荐唯一', r['ok'] and rec.get('email') == 'john.doe@kitchenworld.example.com'
      and len([c for c in r['contacts'] if c.get('recommended')]) == 1, str(r)[:220])
check('4.5 contacts 表可读', len(db.list_contacts(NORM)) >= 1)

# ---------- 5 ICP 资格 ----------
from core.intelligence import icp as im
lead = db.get_lead(NORM)
rels = db.list_relationships(norm=NORM)
sc = im.score_lead(lead, rels, db.list_contacts(NORM))
check('5.1 分层分数带', sc['tier'] in 'ABCD' and 0 <= sc['score'] <= 100 and sc['fit'] > 0, str(sc))
check('5.2 可解释原因+可联系性独立', len(sc['reasons']) >= 2 and 'contactability' in sc and sc['contactability'] > 0)
r = im.score_and_save(NORM)
lead2 = db.get_lead(NORM)
check('5.3 写回 leads', lead2.get('icp_tier') == r['tier'] and lead2.get('icp_score') == r['score']
      and json.loads(lead2.get('icp_reasons') or '[]'))
neg = im.score_lead({'name': 'X', 'kind': 'supplier', 'zone': 'discard'}, [], [])
check('5.4 负面信号扣分降带', neg['tier'] in ('C', 'D') and neg['negatives'], str(neg['score']))

# ---------- 6 ACCOUNT_INTELLIGENCE 五问 ----------
from core.intelligence import account as acc
a = acc.get(NORM)
check('6.1 已知/缺失', a['known'] and any(m['field'] == 'emails' for m in a['missing']), str(a.get('missing')))
check('6.2 下一步+为什么', len(a['next_actions']) >= 1 and all(x.get('why') for x in a['next_actions']))
check('6.3 证据强度与计量', a['evidence_strength'] in ('strong', 'medium') and a['evidenced']['海关票数'] == 60)

# ---------- 7 开发序列重构 ----------
from core.runtime import development as dev
check('7.1 九节点流', dev.DEV_ORDER == ['DEV_VERIFY','ACCOUNT_INTEL','ENRICH','CONTACT','ICP','DEV_OFFER','DEV_LETTER','DEV_REVIEW','DEV_SEND'])
check('7.2 小编排已删除', not hasattr(dev, '_director') and not hasattr(dev, '_diagnose') and not hasattr(dev, '_handoff'))
check('7.3 FN 与 ORDER 一致', set(dev.FN) == set(dev.DEV_ORDER))
# 从 ENRICH 起跑：离线也应过 ENRICH/CONTACT/ICP/OFFER，LETTER 离线失败即停（不伪造成功）
state = dev.run_sequence(NORM, start_node='ENRICH', task_id='dev-test-1')
st = state.get('dev_status', {})
check('7.4 ENRICH/CONTACT/ICP 离线成功', all(st.get(n, {}).get('status') == 'SUCCESS' for n in ('ENRICH','CONTACT','ICP','DEV_OFFER')),
      json.dumps({k: v.get('status') for k, v in st.items()}, ensure_ascii=False))
check('7.5 LETTER 失败即停不伪造', st.get('DEV_LETTER', {}).get('status') == 'FAILED' and state.get('ok') is False)
# n_send 半自动：注入草稿 → 只产发送包，绝不 SMTP
# v39 注：DEV_SEND 默认自动执行（用户明确免审核）；半自动通道由 OUTLOOK_AUTO_SEND=false 保留，此处钉死测该通道
settings.OUTLOOK_AUTO_SEND = False
import core.tools.mailer as mailer
def _boom(*a, **k): raise AssertionError('半自动模式绝不允许自动 SMTP 发送')
mailer.smtp_send = _boom
db.add_message(NORM, 'out', 'email', 'Subject: Hi\n\nHello from PSV', draft=1)
msg = db.latest_out_message(NORM); db.set_message_status(msg['id'], 'review_pending')
out = dev.n_send({'lead_norm': NORM})
send = out.get('send') or {}
check('7.6 半自动发送包+无SMTP', out.get('_success') and send.get('status') == 'ready_to_send'
      and send.get('to') and 'compose_url' in send, str(send)[:200])
check('7.7 收件人取自推荐联系人', send.get('to') == 'john.doe@kitchenworld.example.com', str(send.get('to')))
check('7.8 状态置 ready_to_send', db.latest_out_message(NORM).get('status') == 'ready_to_send')

# ---------- 8 扩张任务化 ----------
from core.tools import expand as ex
check('8.1 六策略注册表', set(ex.STRATEGIES) == {'customer_suppliers','supplier_customers','importer_suppliers','exporter_customers','same_product_importers','cross_market_entity'})
stats = ex.run_network(task_id='exp-test-1', strategies=['same_product_importers','cross_market_entity'], max_new=50)
task = db.get_expansion_task('exp-test-1')
check('8.2 任务行+进度留痕', task and task['status'] == 'done' and len(task['rounds']) == 2 and task['stopped_by'], str(task and task['stopped_by']))
check('8.3 同产品策略真实生效', db.get_lead(DB._norm('Home Hearth Trading')).get('zone') == 'dev' and stats['new_leads'] >= 1)
check('8.4 跨市场角色修正', db.get_lead(DB._norm('Dual Role Co')).get('kind') == 'both')
stats2 = ex.run_network(task_id='exp-test-1', strategies=['same_product_importers','cross_market_entity'], max_new=50)
task2 = db.get_expansion_task('exp-test-1')
check('8.5 断点续跑不重跑', len(task2['rounds']) == 2 and stats2['new_leads'] == 0, str(len(task2['rounds'])))

# ---------- 9 第一采集链冻结 ----------
from core.runtime import graph
check('9.1 第一链 9 节点冻结', graph.ORDER == ['PRODUCT_DEFINITION','TRADE_STRATEGY','CUSTOMS_NODE_COLLECTION','TRADE_EDGE_BUILD','EVIDENCE_VERIFY','ENTITY_RESOLUTION','GRAPH_EXPANSION','RESOURCE_CLASSIFICATION','DATABASE_COMMIT'])

# ---------- 10 半自动消息状态机 ----------
mid = db.latest_out_message(NORM)['id']
db.set_message_status(mid, 'approved')
check('10.1 approved', db.latest_out_message(NORM)['status'] == 'approved')
db.set_message_status(mid, 'sent', sent=True)
m = db.latest_out_message(NORM)
check('10.2 sent+sent_at+draft清零', m['status'] == 'sent' and m['sent_at'] and not m['draft'])
prof = db.get_sender_profile()
db.save_sender_profile({'name_en': 'Test Sender', 'company': 'Test Co'})
check('10.3 发件人档案读写', db.get_sender_profile()['name_en'] == 'Test Sender')

fails = [r for r in results if not r[1]]
print('\n==== v37 验收：%d/%d 通过 ====' % (len(results) - len(fails), len(results)))
sys.exit(1 if fails else 0)
