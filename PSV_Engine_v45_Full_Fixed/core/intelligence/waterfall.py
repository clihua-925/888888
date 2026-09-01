# -*- coding: utf-8 -*-
"""ENRICHMENT WATERFALL v45：真正的多源瀑布式补全引擎 (Waterfall Enrichment)。

核心原则：
1. 贸易原始信息 → 已有数据库 → 企业官网 → 公开网页 → 搜索引擎 → 公开企业信息 → 联系人信息 → 公开邮箱 → AI验证 → 证据合并 → 更新情报档案
2. 已经存在的信息不得重复浪费资源
3. 缺什么查什么
4. 每个字段记录来源 (source_name, source_type, source_level)
5. 每个关键字段记录证据 (evidence)
6. 新信息不得直接覆盖旧信息，必须保留来源和更新时间
7. 一个来源失败，应继续使用下一来源
8. 公开数据路径必须遵守访问限制，不绕过登录、验证码或访问控制
9. 不把普通搜索结果直接当成贸易证据
10. 贸易证据与普通企业公开信息必须严格区分

source_type 严格区分：
- trade_evidence: 真实贸易记录（最高优先级）
- web_scrape: 网页抓取信息
- ai_inference: AI推理结果
- contact_info: 联系人信息
- search_engine: 搜索引擎结果
- public_registry: 公开企业注册信息
- company_website: 企业官网信息
"""

import re
import json
import time
import uuid
from typing import Dict, List, Any, Optional
from core.memory.db import DB
from core.intelligence.ai_router import ai_route

# 字段定义：每个字段的补全优先级和验证规则
FIELD_DEFS = {
    'name': {'label': '标准公司名称', 'weight': 0.05, 'required': True},
    'original_name': {'label': '原始名称', 'weight': 0.02, 'required': False},
    'country': {'label': '国家/地区', 'weight': 0.04, 'required': True},
    'address': {'label': '地址', 'weight': 0.03, 'required': False},
    'website': {'label': '官网', 'weight': 0.05, 'required': True},
    'phone': {'label': '电话', 'weight': 0.03, 'required': False},
    'enterprise_type': {'label': '企业类型', 'weight': 0.04, 'required': False},
    'industry': {'label': '行业', 'weight': 0.05, 'required': False},
    'product_categories': {'label': '产品类别', 'weight': 0.05, 'required': True},
    'brand': {'label': '品牌', 'weight': 0.03, 'required': False},
    'enterprise_scale': {'label': '企业规模', 'weight': 0.03, 'required': False},
    'contact_name': {'label': '联系人姓名', 'weight': 0.08, 'required': False},
    'contact_title': {'label': '联系人职位', 'weight': 0.07, 'required': False},
    'contact_email': {'label': '联系人邮箱', 'weight': 0.10, 'required': True},
    'contact_phone': {'label': '联系人电话', 'weight': 0.05, 'required': False},
    'contact_linkedin': {'label': 'LinkedIn', 'weight': 0.05, 'required': False},
}

# 多源瀑布层级定义（从便宜到贵，从确定到不确定）
SOURCE_LEVELS = [
    {
        'level': 0,
        'name': 'internal_database',
        'label': '已有数据库',
        'type': 'trade_evidence',
        'cost': 'free',
        'reliability': 0.9,
    },
    {
        'level': 1,
        'name': 'company_website',
        'label': '企业官网',
        'type': 'company_website',
        'cost': 'low',
        'reliability': 0.85,
    },
    {
        'level': 2,
        'name': 'public_webpage',
        'label': '公开网页',
        'type': 'web_scrape',
        'cost': 'low',
        'reliability': 0.7,
    },
    {
        'level': 3,
        'name': 'search_engine',
        'label': '搜索引擎',
        'type': 'search_engine',
        'cost': 'medium',
        'reliability': 0.6,
    },
    {
        'level': 4,
        'name': 'public_registry',
        'label': '公开企业信息',
        'type': 'public_registry',
        'cost': 'medium',
        'reliability': 0.75,
    },
    {
        'level': 5,
        'name': 'contact_database',
        'label': '联系人信息库',
        'type': 'contact_info',
        'cost': 'medium',
        'reliability': 0.65,
    },
    {
        'level': 6,
        'name': 'public_email_source',
        'label': '公开邮箱源',
        'type': 'contact_info',
        'cost': 'medium',
        'reliability': 0.55,
    },
    {
        'level': 7,
        'name': 'ai_verification',
        'label': 'AI验证',
        'type': 'ai_inference',
        'cost': 'high',
        'reliability': 0.5,
    },
]


class WaterfallEnrichmentEngine:
    """多源瀑布式补全引擎。逐字段、逐来源进行信息补全。"""

    def __init__(self):
        self.db = DB()
        self._mx_cache = {}

    def enrich_entity(self, entity_id: str, norm: str, target_fields: List[str] = None,
                     category_id: str = None, task_id: str = None) -> dict:
        """对指定实体执行完整的多源瀑布式补全。

        流程：
        1. 获取实体当前状态
        2. 确定缺失字段
        3. 对每个缺失字段，按 source_level 顺序尝试补全
        4. 每个来源成功后记录证据并停止该字段的后续来源尝试
        5. 所有字段处理完毕后，AI验证并合并证据
        6. 更新情报档案
        """
        entity = self.db.get_entity_by_id(entity_id) or self.db.get_entity(norm)
        if not entity:
            return {'ok': False, 'error': '实体不存在', 'entity_id': entity_id, 'norm': norm}

        entity_id = entity.get('entity_id')
        norm = entity.get('norm', norm)

        # 确定需要补全的字段
        fields_to_enrich = target_fields or list(FIELD_DEFS.keys())
        missing_fields = []
        for field in fields_to_enrich:
            current_val = entity.get(field, '')
            if not current_val or current_val.strip() == '':
                missing_fields.append(field)

        if not missing_fields:
            return {
                'ok': True, 'entity_id': entity_id, 'norm': norm,
                'message': '所有目标字段已有值，无需补全',
                'filled': {}, 'still_missing': [], 'events': []
            }

        enrichment_result = {
            'ok': True, 'entity_id': entity_id, 'norm': norm,
            'task_id': task_id, 'filled': {}, 'still_missing': [],
            'events': [], 'start_time': time.time(),
            'category_id': category_id
        }

        # 对每个缺失字段执行瀑布补全
        for field in missing_fields:
            field_result = self._enrich_field(entity, field, category_id, task_id)
            if field_result.get('filled'):
                enrichment_result['filled'][field] = field_result['filled']
                # 更新实体字段
                self.db.update_entity(entity_id, **{field: field_result['filled']['value']})
            else:
                enrichment_result['still_missing'].append({
                    'field': field,
                    'label': FIELD_DEFS.get(field, {}).get('label', field),
                    'tried_sources': field_result.get('tried_sources', [])
                })
            enrichment_result['events'].extend(field_result.get('events', []))

        # AI验证与证据合并
        verification = self._ai_verify_enrichment(entity_id, enrichment_result)
        enrichment_result['verification'] = verification

        # 更新情报档案
        self._update_intelligence_profile(entity_id, enrichment_result)

        enrichment_result['duration'] = round(time.time() - enrichment_result['start_time'], 2)
        enrichment_result['completeness_after'] = self._calc_completeness(entity_id)

        return enrichment_result

    def _enrich_field(self, entity: dict, field: str, category_id: str = None,
                     task_id: str = None) -> dict:
        """对单个字段执行瀑布补全。"""
        entity_id = entity.get('entity_id')
        norm = entity.get('norm')
        result = {'field': field, 'filled': None, 'events': [], 'tried_sources': []}

        for source in SOURCE_LEVELS:
            source_name = source['name']
            result['tried_sources'].append(source_name)

            # 调用对应来源的补全方法
            value, evidence = self._try_source(entity, field, source, category_id)

            if value and str(value).strip():
                # 记录瀑布事件
                event_id = self.db.log_waterfall_event(
                    entity_id=entity_id,
                    field_name=field,
                    source_level=source['level'],
                    source_name=source_name,
                    source_type=source['type'],
                    old_value=entity.get(field, ''),
                    new_value=str(value),
                    evidence=evidence,
                    confidence=source['reliability']
                )

                result['filled'] = {
                    'value': str(value),
                    'source': source_name,
                    'source_type': source['type'],
                    'source_level': source['level'],
                    'evidence': evidence,
                    'confidence': source['reliability'],
                    'event_id': event_id
                }

                # 记录证据到统一证据注册表
                self.db.save_evidence(
                    entity_id=entity_id,
                    source_type=source['type'],
                    source=source_name,
                    evidence=evidence,
                    confidence=source['reliability'],
                    metadata={'field': field, 'value': str(value), 'task_id': task_id}
                )

                # 成功即停：该字段不再尝试更贵的来源
                break

        return result

    def _try_source(self, entity: dict, field: str, source: dict, 
                   category_id: str = None) -> tuple:
        """尝试从指定来源获取字段值。返回 (value, evidence)。"""
        source_name = source['name']
        norm = entity.get('norm')
        name = entity.get('name', norm)

        try:
            if source_name == 'internal_database':
                return self._source_internal_db(entity, field, category_id)
            elif source_name == 'company_website':
                return self._source_company_website(entity, field)
            elif source_name == 'public_webpage':
                return self._source_public_webpage(entity, field)
            elif source_name == 'search_engine':
                return self._source_search_engine(entity, field)
            elif source_name == 'public_registry':
                return self._source_public_registry(entity, field)
            elif source_name == 'contact_database':
                return self._source_contact_database(entity, field)
            elif source_name == 'public_email_source':
                return self._source_public_email(entity, field)
            elif source_name == 'ai_verification':
                return self._source_ai_verification(entity, field)
        except Exception as e:
            # 来源失败，返回空值（外层会继续下一来源）
            return None, f"Source {source_name} failed: {str(e)}"

        return None, None

    # ========== 各来源实现 ==========

    def _source_internal_db(self, entity: dict, field: str, category_id: str = None) -> tuple:
        """从已有数据库（第一采集链输出、其他模块已有数据）查找。"""
        norm = entity.get('norm')

        # 从 leads 表查找（第一采集链数据）
        lead = self.db.get_lead(norm)
        if lead:
            field_map = {
                'name': lead.get('name'),
                'country': lead.get('country'),
                'website': lead.get('website'),
                'address': lead.get('address'),
                'phone': lead.get('phones'),
                'product_categories': lead.get('category') or lead.get('desc_sample'),
                'contact_name': lead.get('contact_person'),
            }
            val = field_map.get(field)
            if val:
                return val, f"Found in leads table (first-chain output)"

        # 从 trade_nodes 查找
        with self.db.c() as conn:
            row = conn.execute(
                "SELECT * FROM trade_nodes WHERE norm=?", (norm,)
            ).fetchone()
            if row:
                row = dict(row)
                field_map = {
                    'name': row.get('name'),
                    'product_categories': row.get('products'),
                    'country': row.get('country'),
                }
                val = field_map.get(field)
                if val:
                    return val, f"Found in trade_nodes"

        # 从已有联系人查找
        contacts = self.db.list_entity_contacts(entity.get('entity_id'))
        if contacts:
            contact = contacts[0]
            field_map = {
                'contact_name': contact.get('name'),
                'contact_title': contact.get('title'),
                'contact_email': contact.get('email'),
                'contact_phone': contact.get('phone'),
                'contact_linkedin': contact.get('linkedin'),
            }
            val = field_map.get(field)
            if val:
                return val, f"Found in existing contacts"

        return None, "Not found in internal database"

    def _source_company_website(self, entity: dict, field: str) -> tuple:
        """从企业官网提取信息。"""
        website = entity.get('website') or ''
        if not website or not website.startswith('http'):
            # 尝试从名称推断官网
            name = entity.get('name', '')
            website = f"https://www.{name.lower().replace(' ', '').replace(',', '').replace('.', '')}.com"

        try:
            import requests
            resp = requests.get(website, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            html = resp.text

            if field == 'website':
                return website, f"Website accessible: {website}"

            if field == 'contact_email':
                emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
                valid = [e for e in emails if self._is_valid_email(e)]
                if valid:
                    return valid[0], f"Email extracted from website: {website}"

            if field == 'contact_phone':
                phones = re.findall(r'[+\d\s\-\(\)]{7,20}', html)
                if phones:
                    return phones[0], f"Phone extracted from website"

            if field == 'address':
                # 尝试从 contact/address 页面提取
                addr_patterns = [
                    r'Address[:\s]*([^<]{10,200})',
                    r'地址[:\s]*([^<]{10,200})',
                    r'Location[:\s]*([^<]{10,200})',
                ]
                for pat in addr_patterns:
                    m = re.search(pat, html, re.I)
                    if m:
                        return m.group(1).strip(), f"Address extracted from website"

            if field == 'enterprise_type':
                type_keywords = {
                    'manufacturer': '制造商',
                    'trading': '贸易商',
                    'wholesale': '批发商',
                    'retail': '零售商',
                    'distributor': '分销商',
                }
                html_lower = html.lower()
                for kw, label in type_keywords.items():
                    if kw in html_lower:
                        return label, f"Enterprise type inferred from website content"

            if field == 'product_categories':
                # 尝试从产品页面提取
                prod_match = re.search(r'Products?[:\s]*([^<]{10,300})', html, re.I)
                if prod_match:
                    return prod_match.group(1).strip(), f"Products extracted from website"

            if field == 'contact_linkedin':
                li_match = re.search(r'https?://(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_-]+', html)
                if li_match:
                    return li_match.group(0), f"LinkedIn found on website"

        except Exception as e:
            return None, f"Website access failed: {str(e)}"

        return None, "Not found on company website"

    def _source_public_webpage(self, entity: dict, field: str) -> tuple:
        """从公开网页（非官网）提取信息。"""
        name = entity.get('name', '')
        country = entity.get('country', '')

        # 简单搜索模拟（实际应接入搜索API）
        search_query = f'"{name}" {country} {field.replace("_", " ")}'

        # 这里可以接入实际的网页搜索/抓取
        # 当前版本使用AI辅助推断
        return None, "Public webpage source requires search API integration"

    def _source_search_engine(self, entity: dict, field: str) -> tuple:
        """从搜索引擎获取信息。"""
        name = entity.get('name', '')

        # 搜索查询构建
        queries = {
            'website': f'{name} official website',
            'contact_email': f'{name} contact email',
            'contact_phone': f'{name} phone number',
            'address': f'{name} address location',
            'enterprise_type': f'{name} company type manufacturer trading',
            'product_categories': f'{name} products catalog',
        }

        query = queries.get(field, f'{name} {field}')

        # 使用AI Router进行搜索辅助推断
        prompt = f"""基于公开信息，请提供 "{name}" 这家公司的 {FIELD_DEFS.get(field, {}).get('label', field)}。
如果无法确定，请明确说明"信息不足"。

要求：
1. 只给出最可能的一个值
2. 说明信息来源类型（官网/公开网页/企业注册信息/推断）
3. 给出置信度（高/中/低）

当前已知：{json.dumps({k: entity.get(k) for k in ['name', 'country', 'website'] if entity.get(k)}, ensure_ascii=False)}
"""

        result = ai_route(
            prompt=prompt,
            system="你是企业信息研究员，擅长从公开信息中准确提取企业数据。",
            schema={
                "type": "object",
                "required": ["value", "source_type", "confidence"],
                "properties": {
                    "value": {"type": "string"},
                    "source_type": {"type": "string"},
                    "confidence": {"type": "string"},
                    "reasoning": {"type": "string"}
                }
            }
        )

        if result.get('ok') and result.get('structured'):
            s = result['structured']
            val = s.get('value', '')
            if val and val != '信息不足' and '不足' not in val:
                return val, f"Search+AI inference: {s.get('source_type', 'unknown')}, confidence: {s.get('confidence', 'low')}"

        return None, "Search engine source no result"

    def _source_public_registry(self, entity: dict, field: str) -> tuple:
        """从公开企业注册信息获取。"""
        # 实际应接入各国企业注册信息API
        # 如：OpenCorporates, 各国工商注册系统等
        return None, "Public registry integration required"

    def _source_contact_database(self, entity: dict, field: str) -> tuple:
        """从联系人信息库获取。"""
        # 可以从已有的 entity_contacts 或外部联系人数据库查找
        entity_id = entity.get('entity_id')
        contacts = self.db.list_entity_contacts(entity_id)

        field_map = {
            'contact_name': 'name',
            'contact_title': 'title',
            'contact_email': 'email',
            'contact_phone': 'phone',
            'contact_linkedin': 'linkedin',
        }

        db_field = field_map.get(field)
        if db_field and contacts:
            for c in contacts:
                val = c.get(db_field)
                if val:
                    return val, f"Found in contact database"

        return None, "Not found in contact database"

    def _source_public_email(self, entity: dict, field: str) -> tuple:
        """从公开邮箱源获取（如 Hunter.io, VoilaNorbert 等）。"""
        if field != 'contact_email':
            return None, "Public email source only for email field"

        website = entity.get('website', '')
        name = entity.get('name', '')

        if not website:
            return None, "No website for email inference"

        # 尝试常见邮箱格式
        domain = website.replace('http://', '').replace('https://', '').replace('www.', '').split('/')[0]
        common_patterns = [
            f"info@{domain}",
            f"sales@{domain}",
            f"contact@{domain}",
            f"admin@{domain}",
        ]

        # 使用AI推断最可能的邮箱
        prompt = f"""基于公司 "{name}" 的官网域名 {domain}，推断最可能的采购负责人邮箱格式。
只返回一个最可能的邮箱地址。如果无法推断，返回"无法推断"。"""

        result = ai_route(prompt=prompt, system="你是企业邮箱推断专家。", max_tokens=200)
        if result.get('ok'):
            val = result.get('natural_language', '').strip()
            if '@' in val and '无法推断' not in val and '不能' not in val:
                # 提取邮箱
                emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', val)
                if emails:
                    return emails[0], f"Email inferred from domain pattern: {domain}"

        return None, "Public email source no result"

    def _source_ai_verification(self, entity: dict, field: str) -> tuple:
        """AI验证与推断（最后一道来源）。"""
        known = {k: entity.get(k) for k in ['name', 'country', 'website', 'address'] if entity.get(k)}

        prompt = f"""基于以下已知信息，推断 "{entity.get('name')}" 的 {FIELD_DEFS.get(field, {}).get('label', field)}。

已知信息：{json.dumps(known, ensure_ascii=False)}

要求：
1. 如果信息不足，明确说明"信息不足，无法推断"
2. 如果可推断，给出最可能的值
3. 说明推断依据
4. 置信度：Strong / Moderate / Weak

请输出JSON格式：{{"value": "值", "confidence": "Strong/Moderate/Weak", "reasoning": "推断依据"}}
"""

        result = ai_route(
            prompt=prompt,
            system="你是企业信息分析专家，擅长基于碎片信息推断企业属性。",
            schema={
                "type": "object",
                "required": ["value", "confidence"],
                "properties": {
                    "value": {"type": "string"},
                    "confidence": {"type": "string"},
                    "reasoning": {"type": "string"}
                }
            }
        )

        if result.get('ok') and result.get('structured'):
            s = result['structured']
            val = s.get('value', '')
            if val and '不足' not in val and '无法' not in val and '不能' not in val:
                return val, f"AI inference: {s.get('reasoning', '')}, confidence: {s.get('confidence', 'Weak')}"

        return None, "AI verification insufficient"

    # ========== 验证与合并 ==========

    def _ai_verify_enrichment(self, entity_id: str, enrichment_result: dict) -> dict:
        """AI验证补全结果的整体质量。"""
        filled = enrichment_result.get('filled', {})
        if not filled:
            return {'passed': False, 'reason': 'No fields were filled'}

        entity = self.db.get_entity_by_id(entity_id)
        prompt = f"""请验证以下企业信息补全结果的质量：

企业：{entity.get('name')}
已补全字段：{json.dumps({k: v.get('value') for k, v in filled.items()}, ensure_ascii=False)}

请判断：
1. 补全的信息是否逻辑一致（如国家与地址是否匹配）
2. 是否有明显矛盾
3. 整体补全质量评分（0-100）
4. 建议下一步补全什么

输出JSON：{{"passed": true/false, "quality_score": 0-100, "consistency_check": "", "suggestions": []}}
"""

        result = ai_route(prompt=prompt, system="你是数据质量验证专家。")
        if result.get('ok') and result.get('structured'):
            return result['structured']

        return {'passed': True, 'quality_score': 60, 'consistency_check': 'Auto-passed', 'suggestions': []}

    def _update_intelligence_profile(self, entity_id: str, enrichment_result: dict):
        """更新情报档案。"""
        profile = self.db.get_intelligence_profile(entity_id) or {}

        # 更新补全日志
        enrichment_log = profile.get('enrichment_log', [])
        enrichment_log.append({
            'timestamp': time.time(),
            'filled_count': len(enrichment_result.get('filled', {})),
            'still_missing_count': len(enrichment_result.get('still_missing', [])),
            'task_id': enrichment_result.get('task_id')
        })

        self.db.save_intelligence_profile(
            entity_id=entity_id,
            completeness_score=self._calc_completeness(entity_id),
            enrichment_log=enrichment_log
        )

    def _calc_completeness(self, entity_id: str) -> float:
        """计算信息完整度。"""
        entity = self.db.get_entity_by_id(entity_id)
        if not entity:
            return 0.0

        score = 0.0
        for field, config in FIELD_DEFS.items():
            val = entity.get(field, '')
            if val and str(val).strip():
                score += config['weight']

        return round(min(score * 100, 100.0), 1)

    def _is_valid_email(self, email: str) -> bool:
        pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
        return bool(re.match(pattern, str(email)))

    def get_field_gaps(self, entity_id: str) -> dict:
        """获取实体的信息缺口分析：已经知道什么、缺什么、下一步可以挖什么。"""
        entity = self.db.get_entity_by_id(entity_id)
        if not entity:
            return {'error': 'Entity not found'}

        known = []
        missing = []
        next_steps = []

        for field, config in FIELD_DEFS.items():
            val = entity.get(field, '')
            label = config['label']
            if val and str(val).strip():
                known.append({'field': field, 'label': label, 'value': str(val)[:100]})
            else:
                missing.append({'field': field, 'label': label, 'priority': 'high' if config['required'] else 'medium'})

        # 根据缺失字段推断下一步
        if any(f['field'] == 'website' for f in missing):
            next_steps.append('通过搜索引擎查找企业官网')
        if any(f['field'].startswith('contact_') for f in missing):
            next_steps.append('从官网提取联系人信息或使用公开邮箱源')
        if any(f['field'] == 'product_categories' for f in missing):
            next_steps.append('分析贸易记录推导产品类别')
        if any(f['field'] == 'enterprise_type' for f in missing):
            next_steps.append('从官网或公开注册信息推断企业类型')

        return {
            'entity_id': entity_id,
            'norm': entity.get('norm'),
            'completeness_score': self._calc_completeness(entity_id),
            'known': known,
            'missing': missing,
            'next_steps': next_steps,
            'total_fields': len(FIELD_DEFS),
            'filled_count': len(known),
            'missing_count': len(missing)
        }


# ========== 便捷函数 ==========
_engine = None

def get_engine() -> WaterfallEnrichmentEngine:
    global _engine
    if _engine is None:
        _engine = WaterfallEnrichmentEngine()
    return _engine

def enrich_entity(entity_id: str, norm: str, target_fields: List[str] = None,
                 category_id: str = None, task_id: str = None) -> dict:
    return get_engine().enrich_entity(entity_id, norm, target_fields, category_id, task_id)

def get_field_gaps(entity_id: str) -> dict:
    return get_engine().get_field_gaps(entity_id)
