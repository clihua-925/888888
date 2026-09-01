# -*- coding: utf-8 -*-
"""联系人发现 v37：联系人 + 邮箱排列生成 + 模式检测 + 验证（绝不群发）。

前沿方案落地：
- 从官网 about/team 页找联系人（正则抽名 → LLM 提炼）
- 邮箱排列：规范化名 → 候选生成 → 按流行度排序（first.last@ ~40-45%，first@ ~20-25%）
- 模式检测：若已知该公司任一邮箱，反推公司邮箱模式，只生成同模式候选
- 域名 MX 只查一次；只把第一名作为推荐（rank，不 shotgun）
"""
import re
from core.memory.db import DB
from core.intelligence import ai_gateway, waterfall

# 流行度排序的邮箱模式（生成函数接收 first/last 小写）
PATTERNS = [
    ('first.last', lambda f, l: f'{f}.{l}'),
    ('first', lambda f, l: f'{f}'),
    ('last', lambda f, l: f'{l}'),
    ('firstlast', lambda f, l: f'{f}{l}'),
    ('f.last', lambda f, l: f'{f[:1]}.{l}'),
    ('first_last', lambda f, l: f'{f}_{l}'),
]


def _clean_name(name):
    parts = re.sub(r'[^a-zA-Z\s-]', '', str(name or '')).split()
    parts = [p.lower() for p in parts if len(p) > 1 or p.isupper()]
    if not parts: return None, None
    return parts[0], (parts[-1] if len(parts) > 1 else '')


def detect_pattern(existing_email, first, last):
    """从已知邮箱与已知人名反推公司模式；匹配则返回模式名。"""
    local = str(existing_email or '').split('@')[0].lower()
    for name, fn in PATTERNS:
        try:
            if fn(first, last) == local: return name
        except Exception: pass
    return None


def infer_pattern(local):
    """只看 local 部分的形状推断公司邮箱模式（不知道对方名字也能用）。"""
    local = str(local or '').lower()
    if re.fullmatch(r'[a-z]\.[a-z]{2,}', local): return 'f.last'
    if re.fullmatch(r'[a-z]{2,}\.[a-z]{2,}', local): return 'first.last'
    if re.fullmatch(r'[a-z]{2,}_[a-z]{2,}', local): return 'first_last'
    return None  # 纯字母无法区分 first/last/firstlast，保持默认流行度排序


def generate_candidates(name, domain, known_emails=None):
    """生成排序候选；已知该公司任一邮箱时先推断模式，同模式候选置顶。"""
    first, last = _clean_name(name)
    if not first or not domain: return []
    pattern = None
    for e in known_emails or []:
        e = str(e).lower()
        if e.endswith('@' + domain.lower()):
            pattern = infer_pattern(e.split('@')[0])
            if pattern: break
    cands = []
    for pname, fn in PATTERNS:
        if not last and pname not in ('first',): continue
        try: cands.append((fn(first, last or first) + '@' + domain.lower(), pname))
        except Exception: pass
    if pattern:
        cands.sort(key=lambda t: 0 if t[1] == pattern else 1)
    seen = set(); out = []
    for e, p in cands:
        if e not in seen: seen.add(e); out.append((e, p))
    return out[:4]


def find_contacts(norm):
    """节点入口：发现联系人 + 生成验证邮箱，写 contacts 表。返回推荐（第一名）。"""
    db = DB(); lead = db.get_lead(norm)
    if not lead: return {'ok': False, 'error': '客户不存在'}
    found = []
    # 1) 已有 contact_person 字段
    person = str(lead.get('contact_person') or '').strip()
    # 2) 官网 about/team 页 LLM 提炼
    if not person and lead.get('website'):
        try:
            html = waterfall._fetch(lead['website'])
            names = re.findall(r'(?:CEO|Founder|Owner|President|Purchasing|Buyer|Manager)[,:\s]+([A-Z][a-z]+ [A-Z][a-z]+)', html)[:5]
            if names:
                person = names[0]
            elif html:
                r = ai_gateway.chat(
                    '从以下公司官网文本中找出采购/负责人姓名（ Buyer / Purchasing / Owner / CEO / Founder 优先）。'
                    '只输出JSON {"name":"","role":""}，找不到就输出{}。\n文本前4000字符：' + re.sub(r'\s+', ' ', html)[:4000],
                    task='contact_extract', temperature=0.1, max_tokens=150, timeout=120)
                if r['ok']:
                    import json
                    j = json.loads(r['text'][r['text'].find('{'):r['text'].rfind('}') + 1])
                    person = str(j.get('name') or '').strip()
        except Exception:
            pass
    if person:
        db.lead_update(norm, contact_person=person)
        db.add_enrichment_event(norm, 'contact_person', 'contacts_finder', person, True)
    # 3) 邮箱：已有邮箱先入表；有联系人+域名时生成排列候选
    domain = ''
    if lead.get('website'):
        m = re.search(r'https?://(?:www\.)?([^/]+)', str(lead['website']))
        domain = m.group(1) if m else ''
    known = [e.strip() for e in str(lead.get('emails') or '').split(',') if '@' in e]
    mx = waterfall.mx_ok(domain) if domain else None
    for e in known:
        db.upsert_contact(norm, e, name=person, email_status='mx_ok' if mx else 'syntax_ok', source='lead_field')
        found.append({'email': e, 'source': 'lead_field', 'recommended': False})
    recommended = None
    if person and domain:
        company_pattern = next((p for p in (infer_pattern(k.split('@')[0]) for k in known
                                if str(k).lower().endswith('@' + domain.lower())) if p), None)
        for i, (cand, pat) in enumerate(generate_candidates(person, domain, known)):
            # 模式检测命中→pattern；域名 MX 有效→mx_ok；否则只是语法猜测→guessed
            status = 'pattern' if (company_pattern and pat == company_pattern) else ('mx_ok' if mx else 'guessed')
            db.upsert_contact(norm, cand, name=person, email_status=status, source='permutation', pattern=pat)
            entry = {'email': cand, 'source': 'permutation', 'pattern': pat, 'status': status, 'recommended': i == 0}
            found.append(entry)
            if i == 0: recommended = entry
    return {'ok': True, 'contact_person': person, 'domain': domain, 'mx_ok': mx,
            'contacts': found, 'recommended': recommended,
            'note': '推荐只发第一名候选，绝不群发' if recommended else '无排列候选'}
