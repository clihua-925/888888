# -*- coding: utf-8 -*-
"""v17: 开发信话术内核——宁晋集群叙事 + 真实署名 + 按客户画像定制钩子。
D_OUTREACH 节点和通信模块共用这一套，保证口径一致。
所有"事实"只允许来自这里登记的素材，禁止大模型编造数字。"""
from core.config import settings
from core.config.industry import load_industry

# 宁晋生日蜡烛产业集群（老板亲述素材，可直接引用的事实）
facts = [
 'Our factory is based in Ningjin, Hebei — the hometown of birthday candles, a cluster that supplies roughly 60% of the world\'s birthday candles.',
 'The cluster works like one giant production line: hundreds of specialized workshops each master a single step or category, and full-chain manufacturers handle R&D to finished product — so capacity is flexible, sampling is fast, and pricing stays very competitive.',
]

# 新增业务事实：免费打样/寄样、常规产品无起订量、定制产品详谈
EXTRA_FACTS = [
    'We offer free samples for candle products — free sampling and free shipping for evaluation.',
    'For our regular market products, there is no minimum order quantity (MOQ).',
    'For customized products, we can discuss details based on your specific requirements.',
]

def signature():
    """真实署名块：优先读 USER_PROFILE（sender_profile 表，UI 可改），回退 settings/.env。"""
    try:
        from core.memory.db import DB
        p = DB().get_sender_profile() or {}
    except Exception:
        p = {}
    name_en = p.get('name_en') or settings.SENDER_NAME_EN
    name_cn = p.get('name_cn') or settings.SENDER_NAME
    company = p.get('company') or 'Birthday Candle Manufacturer, Ningjin, Hebei, China'
    em = (p.get('email') or getattr(settings, 'SENDER_EMAIL', '') or '').strip()
    phone = p.get('phone') or settings.SENDER_PHONE
    if p.get('signature'):
        return p['signature']
    lines = ['Best regards,', '%s (%s)' % (name_en, name_cn), company]
    if em:
        lines.append('Email: %s' % em)
    lines.append('WhatsApp / Mobile: %s' % phone)
    return '\n'.join(lines)

def hooks_for(lead):
    """按客户画像选钩子（最多2个，宁缺毋滥）。返回英文要点列表。"""
    hooks = []
    seg = lead.get('segment') or ''
    tags = str(lead.get('tags') or '')
    ship = int(lead.get('shipments') or 0)
    score = float(lead.get('score') or 0)
    if seg == 'birthday':
        hooks.append('Lead with the Ningjin birthday-candle cluster story; mention spiral candles, number candles and party candles specifically (their product line matches).')
    elif seg == 'candle':
        hooks.append('Position us as candle specialists (scented/pillar/decorative), with the birthday-candle cluster as proof of category depth.')
    else:
        hooks.append('Open with the candle-manufacturing capability and OEM/ODM service; mention the Ningjin cluster briefly as credibility.')
    if score >= 75 or ship >= 500:
        hooks.append('They buy at scale — emphasize stable capacity, consistent quality control, and competitive cluster pricing for large volumes.')
    if 'New' in tags:
        hooks.append('They recently started importing candles — emphasize low MOQ trial orders and fast free samples to lower their entry risk.')
    if 'Fast Growing' in tags:
        hooks.append('They are growing fast — emphasize flexible capacity that scales with their orders and short lead times.')
    return hooks[:2]

def letter_prompt(lead, ammo='', industry_key=None):
    # 从品类配置获取事实素材，若没有则回退到全局 facts
    industry_cfg = load_industry(industry_key or getattr(settings, 'INDUSTRY', 'candle'))
    facts_from_cfg = industry_cfg.get('pitch_facts')
    if facts_from_cfg:
        facts = facts_from_cfg
    else:
        facts = globals().get('facts', [])

    """生成给 LLM 的完整写信指令。"""
    who = '; '.join([x for x in [
        lead.get('name'),
        lead.get('country'),
        ('联系人 %s' % lead['contact_person']) if lead.get('contact_person') else '',
        '生日蜡烛品类买家' if lead.get('segment') == 'birthday' else ('蜡烛品类买家' if lead.get('segment') else ''),
        ('年提单约%d条' % lead['shipments']) if lead.get('shipments') else '',
        ('公司简介: %s' % str(lead.get('intro'))[:160]) if lead.get('intro') else '',
        (lead.get('desc_sample') or '')[:120]
    ] if x])
    hooks = '\n'.join('- ' + h for h in hooks_for(lead))
    return (
        '你是资深外贸业务员，为以下客户写一封简短的英文开发信（正文120词以内）。\n'
        '【可引用的事实素材，只允许用这些，禁止编造其他数字】\n' + '\n'.join('- ' + f for f in facts) + '\n'
        + (('【市场情报】' + ammo[:300] + '\n') if ammo else '')
        + '【客户】' + who + '\n'
        '【针对此客户的钩子，选1-2个自然融入，不要全堆】\n' + hooks + '\n'
        '【我方身份】公司名固定写作 ' + getattr(settings, 'SENDER_COMPANY', 'Ningjin Birthday Candle Factory') + '，是宁晋的生日蜡烛制造工厂（不是贸易/物流/包装公司）；\n'
        '【要求】第一行写 Subject: ...；称呼用采购团队即可（Hi team 或 Hello）；'
        '正文简短、具体、无空话；结尾给一个低门槛动作（回复要目录/报价单/免费样品）；\n'
        '严禁出现 [Your Company Name] 之类的占位符，自我介绍直接写公司名；\n'
        '署名必须原样使用以下内容：\n' + signature() + '\n'
        '只输出成稿本身，不要解释。'
    )