# -*- coding: utf-8 -*-
"""资料审核：机器兜底 + GPT 复核，质量优先，标准务实"""
import re, time, json
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '../..')))
from core.config import settings
from core.memory.db import DB

PROGRESS = None

def _prog(msg):
    try:
        if PROGRESS: PROGRESS(msg)
    except Exception: pass

VERDICT_CN = {'pass': '审核通过', 'suspect': '有疑点', 'fail': '未通过'}

def _extract_from_text(txt):
    """从 GPT 自然语言回复中提取官网、邮箱、电话、地址"""
    if not txt:
        return {}
    emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', txt)
    websites = re.findall(r'https?://[A-Za-z0-9./_-]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}', txt)
    phones = re.findall(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}', txt)
    addresses = re.findall(r'\d{1,6}\s+[A-Za-z0-9][\w .#-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy)[\w .,#-]*', txt)
    out = {}
    if websites:
        out['website'] = websites[0].strip('.,;')
    if emails:
        out['emails'] = list(dict.fromkeys(emails[:5]))
    if phones:
        out['phones'] = list(dict.fromkeys(phones[:2]))
    if addresses:
        out['address'] = addresses[0].strip()
    return out

def _call_gpt(lead, webai=None):
    """结构化询问 GPT，要求返回 JSON"""
    from core.tools import web_ai
    own = False
    w = webai
    if w is None:
        try:
            w = web_ai.WebAI(); w._launch(); own = True
        except Exception:
            return None
    try:
        name = lead.get('name') or ''
        prompt = (
            f'请提供 "{name}" 这家公司的详细公开联系信息。\n'
            '只返回一个JSON对象，格式如下：\n'
            '{"website":"官网URL","emails":["邮箱1","邮箱2"],"phones":["电话1"],"address":"地址"}\n'
            '如果某个字段不知道，就省略该字段。不要输出任何多余文字。'
        )
        txt = w.ask(prompt)
        # 尝试提取 JSON 部分
        if txt:
            # 寻找第一个 { 和最后一个 }
            start = txt.find('{')
            end = txt.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(txt[start:end+1])
                except Exception:
                    return _extract_from_text(txt)
            else:
                return _extract_from_text(txt)
        return None
    finally:
        if own:
            try: w.close()
            except Exception: pass

def audit_and_update(lead, db=None, use_ai=True, webai=None):
    """审核并自动更新客户资料，返回 (更新后的 lead, 审核报告)"""
    if db is None:
        db = DB()

    rep = {'ts': time.time(), 'day': time.strftime('%Y-%m-%d %H:%M'), 'verdict': 'pass',
           'fields': {}, 'ai': {'ran': False, 'suggest': None}}

    name = lead.get('name') or ''
    _prog(f'GPT验证并更新：{name}')

    if use_ai and settings.WEBAI_ENABLED:
        info = _call_gpt(lead, webai=webai)
        if info:
            kw = {}
            if info.get('website'):
                kw['website'] = info['website']
            if info.get('emails'):
                kw['emails'] = ','.join(info['emails'])
            if info.get('phones'):
                kw['phones'] = ','.join(info['phones'])
            if info.get('address'):
                kw['address'] = info['address']
            if kw:
                db.lead_update(lead['norm'], **kw)
                lead = db.get_lead(lead['norm']) or lead
                rep['ai']['ran'] = True
                rep['ai']['suggest'] = kw
                rep['ai']['notes'] = 'GPT已提供结构化更新'
                _prog(f'{name} 已应用GPT更新')
            else:
                rep['ai']['notes'] = 'GPT未提取到更新'
        else:
            rep['ai']['notes'] = 'GPT未回复'

    # 机器审核：有邮箱或电话之一即可通过
    if lead.get('emails') or lead.get('phones'):
        rep['verdict'] = 'pass'
    else:
        rep['verdict'] = 'suspect'

    # 记录字段状态
    for field in ['website','emails','phones','address']:
        if lead.get(field):
            rep['fields'][field] = {'st': 'ok', 'why': []}
        else:
            rep['fields'][field] = {'st': 'missing', 'why': [f'缺{field}']}

    db.lead_update(lead['norm'], audit=json.dumps(rep, ensure_ascii=False))
    return lead, rep

def audit_lead(lead, use_ai=True, webai=None):
    db = DB()
    updated, rep = audit_and_update(lead, db=db, use_ai=use_ai, webai=webai)
    return rep