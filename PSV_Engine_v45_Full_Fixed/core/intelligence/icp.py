# -*- coding: utf-8 -*-
"""ICP 客户资格评分 v37（Fit × Intent × Timing 分层 + 可解释原因 + 分数带）。

前沿方案落地：
- 分层评分：Fit（产品域/规模匹配）× Intent（近期贸易/供应商变化）× Timing（采购周期窗口）
- 可联系性 Contactability 单独计分，不混进资格分（有邮箱≠好客户）
- 分数带 A/B/C/D，负面信号扣分，每条加减分都进 reasons（可解释）
"""
import datetime as dt
import json


def _days(value):
    if not value: return None
    s = str(value).strip()
    for c in (s, s[:10], s[:7], s[:4]):
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m', '%Y'):
            try: return (dt.date.today() - dt.datetime.strptime(c, fmt).date()).days
            except Exception: pass
    return None


def score_lead(lead, rels=None, contacts=None):
    rels = rels or []; contacts = contacts or []
    reasons, negatives = [], []
    # ---- Fit（0-40）：贸易规模 + 供应链复杂度 ----
    fit = 0.0
    ship = int(lead.get('shipments') or 0)
    if ship >= 50: fit += 25; reasons.append(f'历史贸易 {ship} 票，规模买家')
    elif ship >= 10: fit += 18; reasons.append(f'历史贸易 {ship} 票，稳定采购')
    elif ship > 0: fit += 10; reasons.append(f'历史贸易 {ship} 票，有采购记录')
    else: negatives.append('无海关贸易记录，买家身份待证')
    suppliers = len({str(r.get('from_norm') if r.get('from_type') == 'supplier' else r.get('to_norm'))
                     for r in rels if 'supplier' in (str(r.get('from_type')), str(r.get('to_type')))})
    if suppliers >= 3: fit += 15; reasons.append(f'{suppliers} 个供应商，供应链成熟可对比')
    elif suppliers >= 1: fit += 8; reasons.append(f'{suppliers} 个已知供应商')
    fit = min(40.0, fit)
    # ---- Intent（0-35）：近期活跃 + 变化信号 ----
    intent = 0.0
    d = _days(lead.get('last_shipment') or lead.get('last_seen'))
    if d is not None:
        if d <= 45: intent += 25; reasons.append('最近45天内有提货，活跃买家')
        elif d <= 120: intent += 18; reasons.append('最近120天内有提货')
        elif d <= 240: intent += 8; reasons.append('最近240天内有提货')
        else: negatives.append(f'距今 {d} 天无提货，需求可能休眠')
    strong = len([r for r in rels if str(r.get('evidence_level') or '').upper() == 'STRONG'])
    if strong >= 2: intent += 10; reasons.append(f'{strong} 条强证据贸易边')
    elif strong: intent += 5; reasons.append('存在强证据贸易边')
    intent = min(35.0, intent)
    # ---- Timing（0-15）：需求窗口 ----
    timing = 0.0
    win = str(lead.get('demand_window') or '').upper()
    timing = {'NOW': 15, 'SOON': 10, 'WATCH': 5}.get(win, 0)
    if timing: reasons.append(f'需求窗口 {win}')
    # ---- 负面信号（最多 -20） ----
    penalty = 0.0
    if str(lead.get('zone') or '') == 'discard': penalty += 20; negatives.append('已在剔除区')
    if lead.get('kind') == 'supplier': penalty += 10; negatives.append('实体角色是供应商而非买家')
    penalty = min(20.0, penalty)
    # ---- 可联系性（单独，0-100，不进资格分） ----
    contactability = 0
    if lead.get('emails'): contactability += 40
    if contacts: contactability += 20
    if lead.get('website'): contactability += 20
    if lead.get('phones'): contactability += 20
    score = round(max(0.0, min(100.0, fit + intent + timing - penalty)), 1)
    tier = 'A' if score >= 70 else ('B' if score >= 50 else ('C' if score >= 30 else 'D'))
    return {'score': score, 'tier': tier, 'fit': fit, 'intent': intent, 'timing': timing,
            'contactability': contactability, 'reasons': reasons, 'negatives': negatives,
            'caveat': 'ICP 是基于已有贸易证据的概率分层，不代表客户已提出采购需求。'}


def score_and_save(norm):
    """节点入口：评分并写回 leads（icp_score/icp_tier/icp_reasons）。"""
    from core.memory.db import DB
    db = DB(); lead = db.get_lead(norm)
    if not lead: return {'ok': False, 'error': '客户不存在'}
    rels = db.list_relationships(norm=norm, limit=200)
    contacts = db.list_contacts(norm)
    r = score_lead(lead, rels, contacts)
    db.lead_update(norm, icp_score=r['score'], icp_tier=r['tier'],
                   icp_reasons=json.dumps(r['reasons'] + ['⚠ ' + n for n in r['negatives']], ensure_ascii=False))
    return {'ok': True, **r}
