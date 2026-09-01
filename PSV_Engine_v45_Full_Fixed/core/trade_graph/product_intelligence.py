# -*- coding: utf-8 -*-
"""v33.0 Product Intelligence Layer —— 产品语义矩阵（纯执行工具，非节点、不做流程决策）。

每个产品是一份 16 维语义矩阵，不是单一关键词：
    core_name          1 核心产品名称
    standard_name_en   2 英文标准名称
    synonyms           3 同义词
    spelling_variants  4 拼写变体（enamel/enameled/enamelled、单复数）
    industry_terms     5 行业叫法
    buyer_terms        6 买家常用叫法
    supplier_terms     7 供应商常用叫法
    form_words         8 产品形态词（pot/pan/saucepan/stock pot/set…）
    materials          9 材料词
    function_words    10 功能词
    trade_terms       11 贸易描述词（manufacturer/exporter/importer/distributor/wholesaler）
    hs_candidates     12 HS候选（强辅助信号，不作硬过滤）
    exclusions        13 排除词
    precision_terms   14 高精度词（具体组合，定位准）
    recall_terms      15 高召回词（宽泛覆盖，如 enamelware/kitchenware）
    combo_queries     16 组合查询词

查询不设固定上限：矩阵产出多少就用多少，由 CUSTOMS_NODE_COLLECTION 逐查询计量
（result_count/usable_trade_nodes/usable_trade_edges），低价值查询动态淘汰、
高价值查询下轮保留——上限跟随产出，不写死。

来源优先级（全部确定性兜底，LLM 只是增强、不是依赖）：
    1. 行业配置（设置页可维护）
    2. 内置规则（拼写变体/形态词/角色修饰词组合）
    3. LLM 扩展（超时或失败自动略过）
"""
import re

# 贸易描述词（买卖双侧角色修饰）
BUYER_MODIFIERS = ('importer', 'buyer', 'distributor', 'wholesaler', 'retailer', 'brand')
SUPPLIER_MODIFIERS = ('manufacturer', 'factory', 'exporter', 'supplier', 'OEM')
COMMERCIAL_MODIFIERS = ('wholesale', 'bulk', 'OEM', 'custom', 'private label')

# 拼写变体规则（确定性）：美式/英式、单复数
def _spelling_variants(word):
    out = set()
    w = word.strip()
    if not w:
        return []
    out.add(w)
    if 'enamel' in w:
        out.add(w.replace('enamelware', 'enamelled ware').replace('enamel', 'enameled'))
        out.add(w.replace('enamelware', 'enameled ware').replace('enamel', 'enamelled'))
    if w.endswith(' pot'):
        out.add(w + 's')
    if w.endswith(' pan'):
        out.add(w + 's')
    if not w.endswith('s') and ' ' not in w:
        out.add(w + 's')
    return sorted(out)


def _split_cfg(v):
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').replace('；', ';').replace(';', ',').split(',') if x.strip()]


def _dedup(seq):
    out = []; seen = set()
    for x in seq:
        k = str(x or '').strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(str(x).strip())
    return out


def _llm_expand(industry, cfg_terms):
    """LLM 增强：补齐语义矩阵各维。任何失败都返回 None（确定性兜底）。"""
    try:
        from core.utils import jsonutil
        from core.model.client import ModelClient
        mc = ModelClient()
        if not mc.health():
            return None
        prompt = (
            '你是外贸采购情报专家。产品：%s。已知搜索词：%s。\n'
            '只输出JSON：{"synonyms":[],"spelling_variants":[],"industry_terms":[],"form_words":[],'
            '"materials":[],"function_words":[],"precision_terms":[],"recall_terms":[],"exclusions":[]}\n'
            '要求：synonyms=英文同义表达；spelling_variants=拼写/单复数/英美变体；'
            'industry_terms=行业内部叫法；form_words=产品形态词(如 pot/pan/saucepan/set)；'
            'materials=材料词；function_words=功能词；'
            'precision_terms=高精度具体组合词；recall_terms=高召回宽泛词；'
            'exclusions=同名无关领域词(如珐琅锅要排除 enamel paint/dental enamel)。'
            '每类最多10个，全部英文小写。') % (industry, ','.join(cfg_terms[:8]))
        txt = mc.chat(prompt, timeout=45)
        j = jsonutil.j(txt or '')
        keys = ('synonyms', 'spelling_variants', 'industry_terms', 'form_words',
                'materials', 'function_words', 'precision_terms', 'recall_terms', 'exclusions')
        if isinstance(j, dict) and any(j.get(k) for k in keys):
            return {k: _split_cfg(j.get(k)) for k in keys}
    except Exception:
        pass
    return None


def build_product_profile(industry, icp=None, use_llm=True):
    """构建 16 维产品语义矩阵。确定性兜底：LLM 不可用时矩阵仍然完整可用。"""
    from core.config.industry import load_industry
    cfg = load_industry(industry)
    terms = _dedup(_split_cfg(cfg.get('search_terms')) or [industry])
    keywords = _split_cfg(cfg.get('keywords'))
    icp_kw = _split_cfg((icp or {}).get('keywords'))
    core = terms[0]
    synonyms = _dedup(terms[1:] + keywords + icp_kw)
    cfg_exclusions = _split_cfg(cfg.get('exclusions'))
    cfg_materials = _split_cfg(cfg.get('materials'))
    cfg_applications = _split_cfg(cfg.get('applications'))

    # 确定性维度：拼写变体 / 买家词 / 供应商词 / 贸易描述词
    spelling = []
    for t in [core] + synonyms[:6]:
        spelling.extend(_spelling_variants(t))
    spelling = _dedup(spelling)[1:] or []  # 去掉 core 自身
    base_words = _dedup([core] + synonyms)[:5]
    buyer_terms = _dedup('%s %s' % (b, m) for b in base_words[:3] for m in BUYER_MODIFIERS)
    supplier_terms = _dedup('%s %s' % (b, m) for b in base_words[:3] for m in SUPPLIER_MODIFIERS)
    trade_terms = _dedup(list(BUYER_MODIFIERS) + list(SUPPLIER_MODIFIERS))

    llm = _llm_expand(industry, terms) if use_llm else None
    industry_terms = []; form_words = []; function_words = []; precision = []; recall = []
    if llm:
        synonyms = _dedup(synonyms + llm['synonyms'])
        spelling = _dedup(spelling + llm['spelling_variants'])
        industry_terms = llm['industry_terms']
        form_words = llm['form_words']
        function_words = llm['function_words']
        precision = llm['precision_terms']
        recall = llm['recall_terms']
        cfg_materials = _dedup(cfg_materials + llm['materials'])
        cfg_exclusions = _dedup(cfg_exclusions + llm['exclusions'])

    # 高精度词（确定性补充）：材料/形态 × 核心词
    for mat in cfg_materials[:3]:
        precision.append('%s %s' % (mat, core))
    for fw in form_words[:3]:
        precision.append('%s %s' % (core.split()[0], fw) if ' ' in core else '%s %s' % (core, fw))
    precision = _dedup(precision)
    # 高召回词（确定性补充）：核心词的上位词
    if not recall:
        tokens = core.split()
        if len(tokens) > 1:
            recall = _dedup([tokens[-1], tokens[0] + 'ware' if not tokens[0].endswith('ware') else tokens[0]])
        else:
            recall = [core]

    # 组合查询词：高精度×贸易角色 + 商业采购语境
    combo = []
    for b in base_words[:3]:
        for mod in COMMERCIAL_MODIFIERS[:3]:
            combo.append('%s %s' % (b, mod))
    for p in precision[:4]:
        combo.append('%s importer' % p)
    combo = _dedup(combo)

    hs_candidates = [str(x).strip() for x in (cfg.get('hs_codes') or []) if str(x).strip()]
    for x in ((icp or {}).get('hs') or []):
        if str(x).strip() and str(x).strip() not in hs_candidates:
            hs_candidates.append(str(x).strip())

    return {'core_name': core, 'standard_name_en': terms[0], 'canonical': core,
            'synonyms': synonyms, 'spelling_variants': spelling,
            'industry_terms': industry_terms, 'buyer_terms': buyer_terms, 'supplier_terms': supplier_terms,
            'form_words': form_words, 'materials': cfg_materials, 'function_words': function_words,
            'trade_terms': trade_terms, 'hs_candidates': hs_candidates, 'exclusions': cfg_exclusions,
            'precision_terms': precision, 'recall_terms': recall, 'combo_queries': combo,
            'commercial_names': combo,  # 兼容键
            'applications': cfg_applications,
            'llm_enriched': bool(llm)}


def build_query_plan(profile):
    """16维矩阵 → 带类型标注的动态查询计划（无固定上限）。
    每条：query / query_type / expected_role / expected_product_relation / priority。"""
    p = profile
    plan = []

    def add(q, qtype, role, rel, pri):
        q = str(q or '').strip()
        if q:
            plan.append({'query': q, 'query_type': qtype, 'expected_role': role,
                         'expected_product_relation': rel, 'priority': pri,
                         # 以下由 CUSTOMS_NODE_COLLECTION 实测回填
                         'result_count': None, 'usable_trade_nodes': None,
                         'usable_trade_edges': None, 'precision_estimate': None,
                         'recall_contribution': None})

    add(p['core_name'], 'core', 'both', 'exact', 100)
    for q in p['synonyms']: add(q, 'synonym', 'both', 'exact', 90)
    for q in p['spelling_variants']: add(q, 'spelling', 'both', 'exact', 85)
    for q in p['precision_terms']: add(q, 'precision', 'both', 'exact', 80)
    for q in p['buyer_terms']: add(q, 'buyer_role', 'buyer', 'exact', 75)
    for q in p['supplier_terms']: add(q, 'supplier_role', 'supplier', 'exact', 75)
    for q in p['combo_queries']: add(q, 'combo', 'both', 'exact', 70)
    for q in p['industry_terms']: add(q, 'industry', 'both', 'close', 65)
    for q in p['form_words']: add('%s %s' % (p['core_name'].split()[0], q) if q not in p['core_name'] else q, 'form', 'both', 'close', 60)
    for q in p['recall_terms']: add(q, 'recall', 'both', 'broad', 50)
    # 去重保序（优先级高者先出现）
    seen = set(); out = []
    for it in sorted(plan, key=lambda x: -x['priority']):
        k = it['query'].lower()
        if k not in seen:
            seen.add(k); out.append(it)
    return out


def expand_queries(profile, limit=None):
    """兼容接口：返回查询字符串列表。limit=None 表示不设固定上限。"""
    qs = [it['query'] for it in build_query_plan(profile)]
    return qs if limit is None else qs[:int(limit)]


def is_excluded(text, profile):
    """排除词命中=确定无关（如 dental enamel 之于珐琅锅）。拿不准不排除。"""
    t = str(text or '').lower()
    if not t:
        return ''
    for ex in (profile or {}).get('exclusions') or []:
        ex = str(ex).strip().lower()
        if ex and ex in t:
            return ex
    return ''


def validate_hs(hs_candidates):
    """历史贸易验证：每个候选 HS 在 customs_raw 里的真实提单记录数。
    只做标注不过滤：HS 是强辅助信号，不是硬过滤条件。"""
    out = {}
    if not hs_candidates:
        return out
    try:
        from core.memory.db import DB
        db = DB()
        with db.c() as x:
            for hs in hs_candidates:
                like = str(hs).strip() + '%'
                n = x.execute("SELECT COUNT(*) FROM customs_raw WHERE hs LIKE ?", (like,)).fetchone()[0]
                out[str(hs)] = {'rows': int(n), 'validated': n > 0}
    except Exception:
        for hs in hs_candidates:
            out.setdefault(str(hs), {'rows': 0, 'validated': False})
    return out


def measure_query(query, hs_candidates=None):
    """逐查询实测（对本地海关库 customs_raw）：该查询词能命中多少真实提单、
    涉及多少贸易节点（进口商+发货人）。供 CUSTOMS_NODE_COLLECTION 回填 query_stats，
    低价值查询（连续 0 产出）下轮淘汰。"""
    q = str(query or '').strip()
    if not q:
        return {'result_count': 0, 'usable_trade_nodes': 0}
    try:
        from core.memory.db import DB
        db = DB()
        like = '%' + q.lower() + '%'
        with db.c() as x:
            rows = x.execute(
                "SELECT importer, shipper FROM customs_raw WHERE LOWER(descr) LIKE ? OR LOWER(importer) LIKE ? LIMIT 5000",
                (like, like)).fetchall()
        nodes = set()
        for imp, shp in rows:
            if imp: nodes.add(('b', imp.strip().lower()))
            if shp: nodes.add(('s', shp.strip().lower()))
        return {'result_count': len(rows), 'usable_trade_nodes': len(nodes)}
    except Exception:
        return {'result_count': 0, 'usable_trade_nodes': 0}


# ---------- v36 真实海关描述反哺产品情报 ----------
_STOP_TOKENS = {'and', 'or', 'the', 'of', 'for', 'with', 'in', 'on', 'to', 'a', 'an',
                'pcs', 'pc', 'set', 'sets', 'ctn', 'ctns', 'carton', 'cartons', 'kg', 'kgs',
                'no', 'nos', 'type', 'item', 'code', 'po', 'style', 'size', 'color', 'colour',
                'material', 'product', 'products', 'goods', 'made', 'china', 'usa', 'new',
                'per', 'as', 'by', 'at', 'from', 'hs', 'shipment', 'cargo', 'container'}


def harvest_description_terms(product_domain_key, profile, min_hits=2, max_terms=30):
    """从 customs_raw 真实提单描述中收割高频产品表达，写入产品情报记忆（product_intel_terms）。

    反哺闭环：产品情报 → 搜索 → 真实贸易描述 → 产品情报更新 → 下一轮搜索。
    采纳规则（保守，防噪声）：
      - 只扫描 HS 候选命中 或 含核心词根的提单描述；
      - 候选词 = 描述中的单词/二元组，须含字母、非停用词、非排除词、非纯数字；
      - 词须与核心词根同现（同一提单描述内），保证是"本产品的真实商业叫法"；
      - 命中 ≥min_hits 条提单才入库。
    返回 {'scanned': n, 'learned': {term: hits}}。"""
    try:
        from core.memory.db import DB
    except Exception:
        return {'scanned': 0, 'learned': {}}
    profile = profile or {}
    core_roots = set()
    for w in str(profile.get('core_name') or '').lower().split():
        w = re.sub(r'[^a-z]', '', w)
        if len(w) >= 3:
            core_roots.add(w)
    if not core_roots:
        return {'scanned': 0, 'learned': {}}
    exclusions = {str(x).lower() for x in (profile.get('exclusions') or [])}
    hs_codes = [str(h) for h in (profile.get('hs_candidates') or [])][:8]
    db = DB()
    rows = []
    try:
        with db.c() as x:
            for root in list(core_roots)[:3]:
                rows += x.execute("SELECT descr FROM customs_raw WHERE LOWER(descr) LIKE ? LIMIT 3000",
                                  ('%' + root + '%',)).fetchall()
            for hs in hs_codes[:4]:
                rows += x.execute("SELECT descr FROM customs_raw WHERE hs LIKE ? LIMIT 1000",
                                  (str(hs) + '%',)).fetchall()
    except Exception:
        return {'scanned': 0, 'learned': {}}
    counts = {}
    for (descr,) in rows:
        t = str(descr or '').lower()
        if not t or not any(r in t for r in core_roots):
            continue
        if any(ex and ex in t for ex in exclusions):
            continue
        words = [w for w in re.split(r'[^a-z]+', t) if len(w) >= 3 and w not in _STOP_TOKENS]
        wset = set(words)
        # 二元组：含核心词根的相邻组合（"cast iron"、"enamel pot" 这类真实商业叫法）
        for i in range(len(words) - 1):
            bg = words[i] + ' ' + words[i + 1]
            if any(r in (words[i], words[i + 1]) for r in core_roots) and not any(ex in bg for ex in exclusions):
                counts[bg] = counts.get(bg, 0) + 1
        # 单词：修饰/形态词（与核心词同现的才叫法，如 cast / iron / coated）
        for w in wset - core_roots:
            counts[w] = counts.get(w, 0) + 1
    learned = {t: c for t, c in counts.items() if c >= int(min_hits)}
    learned = dict(sorted(learned.items(), key=lambda kv: -kv[1])[:int(max_terms)])
    # 已经在 16 维矩阵里的词不重复学习
    existing = set()
    for k in ('core_name', 'synonyms', 'precision_terms', 'recall_terms', 'combo_queries'):
        v = profile.get(k)
        for q in ([v] if isinstance(v, str) else (v or [])):
            existing.add(str(q).lower().strip())
    learned = {t: c for t, c in learned.items() if t not in existing}
    if learned:
        try:
            db.save_intel_terms(product_domain_key, learned)
        except Exception:
            pass
    return {'scanned': len(rows), 'learned': learned}


def learned_recall_queries(product_domain_key, min_hits=2, limit=10):
    """读取产品情报记忆中学到的词，生成 learned_recall 查询（低优先级、有上限）。"""
    try:
        from core.memory.db import DB
        rows = DB().list_intel_terms(product_domain_key, status='learned', min_hits=min_hits, limit=limit)
        return [{'query': r['term'], 'query_type': 'learned_recall', 'expected_role': 'both',
                 'expected_product_relation': 'broad', 'priority': 55,
                 'result_count': None, 'usable_trade_nodes': None,
                 'usable_trade_edges': None, 'precision_estimate': None,
                 'recall_contribution': None, 'learned_hits': r['hits']} for r in rows]
    except Exception:
        return []
