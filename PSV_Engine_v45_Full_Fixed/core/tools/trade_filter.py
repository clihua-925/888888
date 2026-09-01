# -*- coding: utf-8 -*-
"""v30 第一轮简单净化器（Trade Purifier）。

原则：第一轮只做简单净化，不评分、不过度过滤。

删除：
  - 百度百科类页面（百科/维基/知道/知乎类）
  - 无贸易关系网页（文章标题、资讯页、与企业无关的页面）
  - 新闻
  - 词典
  - 翻译页面
  - 广告目录（B2B 平台目录页、黄页聚合页）
  - 明显错误企业（货代/物流/软件/媒体等明确非贸易节点，或无名字的脏数据）

保留（命中任一即保留）：
  importer / exporter / supplier / manufacturer / shipper / consignee /
  notify party / HS code / shipment / BOL / trade evidence

客户价值判断属于第二阶段（A_GATE / SCORING），这里不做。
"""
import re

# ---------- 删除规则 ----------
DELETE_DOMAINS = (
    # 百科 / 问答 / 社区
    'baike.baidu.com', 'baidu.com', 'zhihu.com', 'wikipedia.org', 'wikiwand.com',
    'quora.com', 'reddit.com', 'fandom.com', 'moegirl.org', 'csdn.net',
    'stackoverflow.com', 'github.com',
    # 词典 / 翻译
    'dictionary.com', 'cambridge.org', 'merriam-webster.com', 'thefreedictionary.com',
    'wordreference.com', 'collinsdictionary.com', 'ldoceonline.com',
    'oxfordlearnersdictionaries.com', 'youdao.com', 'fanyi', 'translate.google',
    'deepl.com', 'bing.com/translator', 'iciba.com',
    # 社交媒体 / 视频（非贸易节点）
    'youtube.com', 'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'tiktok.com', 'pinterest.com',
    # 广告目录 / B2B 平台聚合页 / 电商零售
    'alibaba.com', 'made-in-china.com', 'globalsources.com', 'tradekey.com',
    'ec21.com', 'dhgate.com', 'aliexpress.com', 'amazon.com', 'ebay.com',
    'yellowpages.com', 'yelp.com', 'thomasnet.com/browse', 'kompass.com',
)

DELETE_KEYWORDS = (
    # 中文干扰页
    '百科', '词典', '翻译', '是什么意思', '英语单词', '新闻', '资讯',
    # 英文干扰页
    'dictionary', 'meaning', 'definition', 'translate', 'translation',
    'usage', 'example sentence', 'news', 'article', 'blog', 'press release',
    'wikipedia', 'how to', 'what is',
)

# 明确错误企业：物流/货代/软件/媒体/协会/展会等，不可能成为贸易买卖双方节点
WRONG_ENTITY_RE = re.compile(
    r'freight|forwarder|forwarding|logistics|cargo|shipping\s*(line|agent|company)?|'
    r'customs\s*broker|packaging|consulting|translation|dictionary|wiki|'
    r'software|media|association|expo|exhibition|物流|货代|报关',
    re.I)

# ---------- 保留信号 ----------
KEEP_SIGNALS = (
    'importer', 'importer of record', 'exporter', 'supplier', 'manufacturer',
    'shipper', 'consignee', 'notify party', 'hs code', 'hs_code', 'hts code',
    'shipment', 'shipments', 'bill of lading', 'bol', 'b/l',
    'trade evidence', 'customs', 'import records', 'import record',
    '提单', '海关', '进口商', '出口商', '供应商', '制造商',
)

# 公司身份后缀（用于“无贸易信号时是否仍是企业”的兜底判断）
COMPANY_SUFFIX_RE = re.compile(
    r'\b(inc|llc|ltd|corp|corporation|co|company|gmbh|sarl|sa|ag|group|'
    r'international|trading|imports?|exports?|wholesale|distribution|'
    r'manufacturing|industries|enterprises|factory)\b', re.I)


def _text_of(c):
    ev = c.get('evidence') or {}
    parts = [c.get('name'), c.get('website'), ev.get('url'), ev.get('description'),
             ev.get('products'), ev.get('reasons'), c.get('type'), c.get('kind')]
    if isinstance(ev.get('hs'), (list, tuple)):
        parts.append('hs code ' + ' '.join(str(x) for x in ev['hs']))
    elif ev.get('hs'):
        parts.append('hs code ' + str(ev['hs']))
    return ' '.join(str(p) for p in parts if p)


def has_keep_signal(c):
    """命中任一贸易节点/证据信号。"""
    ev = c.get('evidence') or {}
    # 硬证据字段直接保留
    if ev.get('shipments') or ev.get('bill_of_lading') or ev.get('bol') \
            or ev.get('customs') or ev.get('trade_evidence') \
            or ev.get('supplier_relation') or ev.get('raw_ids') or ev.get('hs'):
        return True
    typ = str(c.get('type') or c.get('kind') or '').lower()
    if typ in ('importer', 'exporter', 'supplier', 'manufacturer', 'shipper',
               'consignee', 'notify', 'notify_party', 'notify party', 'buyer', 'customer'):
        return True
    text = _text_of(c).lower()
    return any(sig in text for sig in KEEP_SIGNALS)


def drop_reason(c, exclusions=None):
    """返回删除原因；返回 None 表示保留。规则刻意保守：拿不准就保留。
    v30.8：产品排除词（Product Intelligence）——命中即确定无关（如珐琅锅排除
    enamel paint / dental enamel），优先于保留信号判断。"""
    name = str(c.get('name') or '').strip()
    url = str(c.get('website') or (c.get('evidence') or {}).get('url') or '').lower()
    if not name or len(name) < 2:
        return '无有效企业名'
    low = name.lower()
    if exclusions:
        text = _text_of(c).lower()
        for ex in exclusions:
            exs = str(ex).strip().lower()
            if exs and exs in text:
                return f'排除词命中:{exs}'
    for d in DELETE_DOMAINS:
        if d in url:
            return f'删除域名:{d}'
    for kw in DELETE_KEYWORDS:
        if kw in low:
            return f'删除关键词:{kw}'
    if WRONG_ENTITY_RE.search(name):
        return '明确非贸易节点企业'
    if has_keep_signal(c):
        return None
    # 无贸易信号时：像企业名则保留（第一阶段不过度过滤），像文章标题则删除
    if COMPANY_SUFFIX_RE.search(low):
        return None
    if len(name) > 60 or low.count(' ') > 6:
        return '无贸易关系网页(标题式文本)'
    return None   # 拿不准：保留到第二阶段判断


def purify(companies, exclusions=None):
    """简单净化入口。返回 (kept, dropped)；dropped 元素为 (candidate, reason)。
    v30.8：exclusions 为产品排除词集合（来自 Product Intelligence Layer）。"""
    kept, dropped = [], []
    for c in (companies or []):
        r = drop_reason(c, exclusions=exclusions)
        if r:
            dropped.append((c, r))
        else:
            kept.append(c)
    return kept, dropped
