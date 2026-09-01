# -*- coding: utf-8 -*-
"""ACCOUNT_INTELLIGENCE_CENTER v42：客户情报中心（后半段唯一入口）。

职责：把第一采集链发现的客户/供应商，加工为完整商业情报资产。
禁止：重复第一采集链的采集逻辑；禁止修改采集流程。
"""
import json, time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from core.memory.db import DB
from core.intelligence.ai_router import ai_route

# ========== 数据契约（唯一权威定义） ==========

@dataclass
class EnterpriseInfo:
    name: str = ""
    website: str = ""
    address: str = ""
    country: str = ""
    enterprise_type: str = ""      # 制造商/贸易商/批发商/零售商
    product_category: str = ""
    brand_info: str = ""
    enterprise_scale: str = ""     # 员工数/营收规模
    contact_methods: Dict[str, str] = field(default_factory=dict)

@dataclass
class TradeInfo:
    products: List[str] = field(default_factory=list)
    hs_codes: List[str] = field(default_factory=list)
    import_records: int = 0
    export_records: int = 0
    transaction_count: int = 0
    last_transaction_date: str = ""
    current_suppliers: List[str] = field(default_factory=list)
    current_customers: List[str] = field(default_factory=list)
    trade_intensity: str = ""      # high/medium/low
    evidence_source: str = ""

@dataclass
class ContactPerson:
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    is_verified: bool = False
    email_verified: bool = False
    confidence: str = "low"        # high/medium/low

@dataclass
class AccountProfile:
    norm: str = ""
    enterprise: EnterpriseInfo = field(default_factory=EnterpriseInfo)
    trade: TradeInfo = field(default_factory=TradeInfo)
    contacts: List[ContactPerson] = field(default_factory=list)
    completeness_score: float = 0.0
    info_status: Dict[str, Any] = field(default_factory=dict)
    icp_score: Dict[str, Any] = field(default_factory=dict)
    development_eligible: bool = False
    development_blockers: List[str] = field(default_factory=list)
    trade_network: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class AccountIntelligenceCenter:
    """客户情报中心：补全、验证、评分、资格判断（唯一入口）"""

    def __init__(self):
        self.db = DB()

    # ---------- 核心流程入口 ----------

    def process_lead(self, norm: str) -> dict:
        """主流程：贸易节点 → 情报中心 → 补全 → 验证 → 评分 → 资格判断"""
        lead = self.db.get_lead(norm)
        if not lead:
            return {'ok': False, 'error': 'lead not found', 'norm': norm}

        profile = self._build_profile(norm, lead)
        profile = self._enrich_info(profile, lead)
        profile.completeness_score = self._calc_completeness(profile)
        profile.info_status = self._build_info_status(profile)

        verification = self._ai_verify(profile)
        profile.icp_score = self._value_scoring(profile, verification)
        profile.development_eligible, profile.development_blockers = self._dev_qualification(profile, verification)
        profile.updated_at = time.strftime('%Y-%m-%d %H:%M:%S')

        # 持久化
        self._save_profile(profile)
        self._save_trade_records(norm, profile.trade)
        self._save_contacts(norm, profile.contacts)

        return {
            'ok': True,
            'norm': norm,
            'completeness_score': profile.completeness_score,
            'info_status': profile.info_status,
            'ai_verified': verification.get('passed', False),
            'ai_verification_result': verification,
            'value_score': profile.icp_score.get('total_score', 0),
            'value_grade': profile.icp_score.get('grade', 'D'),
            'dev_qualified': profile.development_eligible,
            'dev_blockers': profile.development_blockers,
            'profile': self._profile_to_dict(profile)
        }

    def get_intelligence(self, norm: str) -> Optional[dict]:
        """查询已处理的情报（供业务执行中心、网络扩张调用）"""
        row = self.db.get_account_intelligence(norm)
        if not row:
            return None
        # 统一返回格式，兼容旧版调用
        if isinstance(row, dict):
            return row
        try:
            return json.loads(row) if isinstance(row, str) else dict(row)
        except:
            return None

    # ---------- 档案构建与补全 ----------

    def _build_profile(self, norm: str, lead: dict) -> AccountProfile:
        p = AccountProfile(norm=norm, created_at=time.strftime('%Y-%m-%d %H:%M:%S'))
        p.enterprise.name = lead.get('name', '')
        p.enterprise.website = lead.get('website', '')
        p.enterprise.address = lead.get('address', '')
        p.enterprise.country = lead.get('country', '')
        p.enterprise.enterprise_type = lead.get('company_type', lead.get('type', ''))
        p.enterprise.product_category = lead.get('product_category', lead.get('category', ''))
        p.enterprise.brand_info = lead.get('brand_info', '')
        p.enterprise.enterprise_scale = lead.get('company_size', '')
        p.enterprise.contact_methods = {
            'phone': lead.get('phone', ''),
            'fax': lead.get('fax', ''),
        }
        return p

    def _enrich_from_db(self, profile: AccountProfile, lead: dict) -> AccountProfile:
        """从已有数据库补充贸易与联系人信息（基础层）"""
        # 贸易信息补全
        trades = self.db.list_lead_trades(profile.norm)
        if trades:
            profile.trade.products = list({t.get('product', '') for t in trades if t.get('product')})
            profile.trade.hs_codes = list({t.get('hs_code', '') for t in trades if t.get('hs_code')})
            profile.trade.transaction_count = len(trades)
            profile.trade.import_records = sum(1 for t in trades if t.get('direction') == 'import')
            profile.trade.export_records = sum(1 for t in trades if t.get('direction') == 'export')
            dates = [t.get('date', '') for t in trades if t.get('date')]
            profile.trade.last_transaction_date = max(dates) if dates else ''
            profile.trade.current_suppliers = list({t.get('supplier') for t in trades if t.get('supplier')})
            profile.trade.current_customers = list({t.get('buyer') for t in trades if t.get('buyer')})
            profile.trade.trade_intensity = 'high' if len(trades) >= 10 else 'medium' if len(trades) >= 3 else 'low'
            profile.trade.evidence_source = trades[0].get('source', '') if trades else ''

        # 联系人补全
        db_contacts = self.db.list_contacts(profile.norm)
        profile.contacts = []
        for c in db_contacts:
            cp = ContactPerson(
                name=c.get('name', c.get('contact_name', '')),
                title=c.get('title', ''),
                email=c.get('email', ''),
                phone=c.get('phone', ''),
                linkedin=c.get('linkedin', ''),
                is_verified=c.get('is_verified', False),
                email_verified=c.get('email_verified', False),
                confidence=c.get('confidence', 'low')
            )
            profile.contacts.append(cp)

        return profile

    def _enrich_info(self, profile: AccountProfile, lead: dict) -> AccountProfile:
        """信息补全：多源瀑布式补全（v45 修复：集成 Waterfall 引擎）"""
        # 1. 先从已有数据库补充（基础层）
        profile = self._enrich_from_db(profile, lead)

        # 2. 调用瀑布式补全引擎进行外部信息补全
        try:
            from core.intelligence.waterfall import get_engine as get_waterfall_engine
            waterfall = get_waterfall_engine()

            entity = self.db.get_or_create_entity(
                norm=profile.norm,
                name=profile.enterprise.name,
                country=profile.enterprise.country,
                website=profile.enterprise.website,
                address=profile.enterprise.address,
                phone=profile.enterprise.contact_methods.get('phone'),
                product_categories=profile.enterprise.product_category
            )
            entity_id = entity.get('entity_id')

            enrichment = waterfall.enrich_entity(
                entity_id=entity_id,
                norm=profile.norm,
                category_id=profile.enterprise.product_category,
                task_id=f"intel-{profile.norm}"
            )

            if enrichment.get('ok'):
                filled = enrichment.get('filled', {})

                if 'website' in filled and not profile.enterprise.website:
                    profile.enterprise.website = filled['website']['value']
                if 'address' in filled and not profile.enterprise.address:
                    profile.enterprise.address = filled['address']['value']
                if 'phone' in filled and not profile.enterprise.contact_methods.get('phone'):
                    profile.enterprise.contact_methods['phone'] = filled['phone']['value']
                if 'enterprise_type' in filled and not profile.enterprise.enterprise_type:
                    profile.enterprise.enterprise_type = filled['enterprise_type']['value']
                if 'product_categories' in filled and not profile.enterprise.product_category:
                    profile.enterprise.product_category = filled['product_categories']['value']
                if 'brand' in filled and not profile.enterprise.brand_info:
                    profile.enterprise.brand_info = filled['brand']['value']

                if 'contact_email' in filled:
                    existing_emails = [c.email for c in profile.contacts]
                    if filled['contact_email']['value'] not in existing_emails:
                        new_contact = ContactPerson(
                            email=filled['contact_email']['value'],
                            confidence='medium' if filled['contact_email'].get('confidence', 0) > 0.6 else 'low',
                            is_verified=False
                        )
                        if 'contact_name' in filled:
                            new_contact.name = filled['contact_name']['value']
                        if 'contact_title' in filled:
                            new_contact.title = filled['contact_title']['value']
                        profile.contacts.append(new_contact)

                profile.trade_network['last_enrichment'] = {
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'filled_fields': list(filled.keys()),
                    'still_missing': [m['field'] for m in enrichment.get('still_missing', [])],
                    'completeness_after': enrichment.get('completeness_after', 0)
                }
        except Exception as e:
            profile.trade_network['enrichment_error'] = str(e)[:200]

        return profile

    # ---------- 完整度评分 ----------

    def _calc_completeness(self, profile: AccountProfile) -> float:
        score = 0.0
        # 企业信息 (35%)
        if profile.enterprise.name: score += 0.05
        if profile.enterprise.website: score += 0.05
        if profile.enterprise.address: score += 0.03
        if profile.enterprise.country: score += 0.04
        if profile.enterprise.enterprise_type: score += 0.04
        if profile.enterprise.product_category: score += 0.05
        if profile.enterprise.brand_info: score += 0.03
        if profile.enterprise.enterprise_scale: score += 0.03
        if any(profile.enterprise.contact_methods.values()): score += 0.03
        # 贸易信息 (40%)
        if profile.trade.products: score += 0.06
        if profile.trade.hs_codes: score += 0.04
        if profile.trade.import_records or profile.trade.export_records: score += 0.04
        if profile.trade.transaction_count: score += 0.05
        if profile.trade.last_transaction_date: score += 0.05
        if profile.trade.current_suppliers: score += 0.04
        if profile.trade.current_customers: score += 0.04
        if profile.trade.trade_intensity: score += 0.04
        if profile.trade.evidence_source: score += 0.04
        # 联系人 (25%)
        if profile.contacts: score += 0.15
        if any(c.email for c in profile.contacts): score += 0.05
        if any(c.phone for c in profile.contacts): score += 0.05
        return round(min(score * 100, 100.0), 1)

    def _build_info_status(self, profile: AccountProfile) -> dict:
        completed = []
        missing = []
        checks = {
            '公司信息': bool(profile.enterprise.name),
            '官网': bool(profile.enterprise.website),
            '地址': bool(profile.enterprise.address),
            '国家地区': bool(profile.enterprise.country),
            '企业类型': bool(profile.enterprise.enterprise_type),
            '产品类别': bool(profile.enterprise.product_category),
            '品牌信息': bool(profile.enterprise.brand_info),
            '企业规模': bool(profile.enterprise.enterprise_scale),
            '联系方式': bool(any(profile.enterprise.contact_methods.values())),
            '产品': bool(profile.trade.products),
            'HS编码': bool(profile.trade.hs_codes),
            '贸易记录': bool(profile.trade.transaction_count > 0),
            '最近交易时间': bool(profile.trade.last_transaction_date),
            '当前供应商': bool(profile.trade.current_suppliers),
            '当前客户': bool(profile.trade.current_customers),
            '贸易强度': bool(profile.trade.trade_intensity),
            '贸易证据来源': bool(profile.trade.evidence_source),
            '联系人': bool(profile.contacts),
            '邮箱': any(c.email for c in profile.contacts),
            '电话': any(c.phone for c in profile.contacts),
        }
        for label, ok in checks.items():
            (completed if ok else missing).append(label)
        return {
            'completeness_score': profile.completeness_score,
            'completed': completed,
            'missing': missing,
            'total_items': len(checks),
            'completed_count': len(completed)
        }

    # ---------- AI验证 ----------

    def _ai_verify(self, profile: AccountProfile) -> dict:
        prompt = f"""请验证以下企业的真实性与采购意向。

企业：{profile.enterprise.name}
国家：{profile.enterprise.country}
类型：{profile.enterprise.enterprise_type}
产品：{profile.enterprise.product_category}
贸易记录数：{profile.trade.transaction_count}
最近交易：{profile.trade.last_transaction_date}
供应商：{profile.trade.current_suppliers[:3] if profile.trade.current_suppliers else []}

要求：
1. 先以自然语言说明判断结果和原因（至少3条）
2. 给出置信度（Strong/Moderate/Weak）
3. 输出结构化JSON：{{"passed": true/false, "confidence": "Strong", "reasons": ["原因1"]}}
"""
        result = ai_route(
            prompt=prompt,
            system="你是B2B客户验证专家，严格判断企业是否为真实采购客户。",
            schema={"type": "object", "required": ["passed", "confidence", "reasons"], 
                    "properties": {"passed": {"type": "boolean"}, "confidence": {"type": "string"}, "reasons": {"type": "array"}}}
        )
        if not result['ok']:
            return {'passed': False, 'confidence': 'Weak', 'reasons': [result.get('error', 'AI调用失败')], 'raw_error': result.get('error')}
        s = result['structured'] or {}
        return {
            'passed': s.get('passed', False),
            'confidence': s.get('confidence', result.get('confidence', 'Weak')),
            'reasons': s.get('reasons', []),
            'natural_language': result.get('natural_language', '')
        }

    # ---------- 价值评分 ----------

    def _value_scoring(self, profile: AccountProfile, verification: dict) -> dict:
        score = 0.0
        if verification.get('passed'): score += 30
        conf_map = {'Strong': 20, 'Moderate': 10, 'Weak': 0}
        score += conf_map.get(verification.get('confidence', 'Weak'), 0)
        score += min(profile.completeness_score * 0.3, 30)
        score += 20 if profile.trade.transaction_count >= 10 else 10 if profile.trade.transaction_count >= 3 else 0

        grade = 'A' if score >= 80 else 'B' if score >= 60 else 'C' if score >= 40 else 'D'
        return {
            'total_score': round(score, 1), 
            'grade': grade, 
            'breakdown': {
                'verification': 30 if verification.get('passed') else 0,
                'confidence': conf_map.get(verification.get('confidence', 'Weak'), 0),
                'completeness': round(min(profile.completeness_score * 0.3, 30), 1),
                'trade_volume': 20 if profile.trade.transaction_count >= 10 else 10 if profile.trade.transaction_count >= 3 else 0
            }
        }

    # ---------- 开发资格判断 ----------

    def _dev_qualification(self, profile: AccountProfile, verification: dict) -> (bool, List[str]):
        blockers = []
        if not profile.enterprise.name:
            blockers.append('客户信息不存在')
        if not verification.get('passed'):
            blockers.append('AI验证未通过：' + '; '.join(verification.get('reasons', [])[:2]))
        if profile.completeness_score < 50:
            blockers.append(f"信息完整度不足：{profile.completeness_score}% < 50%")
        if not profile.contacts:
            blockers.append('无联系人信息')
        if not any(c.email_verified for c in profile.contacts):
            blockers.append('无验证通过的联系人邮箱')
        # value_grade 不再作为硬性门槛，仅作参考
        return len(blockers) == 0, blockers

    # ---------- 持久化 ----------

    def _save_profile(self, profile: AccountProfile):
        self.db.save_account_intelligence(profile.norm, self._profile_to_dict(profile))

    def _save_trade_records(self, norm: str, trade: TradeInfo):
        for prod in trade.products:
            self.db.save_trade_intelligence(norm, {
                'product': prod,
                'hs_code': trade.hs_codes[0] if trade.hs_codes else '',
                'trade_direction': 'import' if trade.import_records > trade.export_records else 'export',
                'shipment_count': trade.transaction_count,
                'last_trade_at': trade.last_transaction_date,
                'current_suppliers': trade.current_suppliers,
                'current_customers': trade.current_customers,
                'trade_strength': 1.0 if trade.trade_intensity == 'high' else 0.5 if trade.trade_intensity == 'medium' else 0.2,
                'evidence_source': trade.evidence_source
            })

    def _save_contacts(self, norm: str, contacts: List[ContactPerson]):
        for c in contacts:
            self.db.save_contact_intelligence(norm, {
                'contact_name': c.name,
                'title': c.title,
                'email': c.email,
                'phone': c.phone,
                'linkedin': c.linkedin,
                'email_verified': c.email_verified,
                'email_verify_result': {},
                'is_primary': False
            })

    def _profile_to_dict(self, profile: AccountProfile) -> dict:
        return {
            'norm': profile.norm,
            'name': profile.enterprise.name,
            'website': profile.enterprise.website,
            'address': profile.enterprise.address,
            'country': profile.enterprise.country,
            'company_type': profile.enterprise.enterprise_type,
            'product_categories': [profile.enterprise.product_category] if profile.enterprise.product_category else [],
            'brand_info': [profile.enterprise.brand_info] if profile.enterprise.brand_info else [],
            'company_size': profile.enterprise.enterprise_scale,
            'contact_info': {
                'phones': [profile.enterprise.contact_methods.get('phone', '')],
                'fax': profile.enterprise.contact_methods.get('fax', '')
            },
            'info_completeness': profile.completeness_score,
            'info_completeness_detail': profile.info_status,
            'ai_verified': profile.icp_score.get('total_score', 0) > 40,  # 简化逻辑
            'ai_verification_result': {},
            'value_score': profile.icp_score.get('total_score', 0),
            'value_grade': profile.icp_score.get('grade', 'D'),
            'dev_qualified': profile.development_eligible,
            'dev_qualification_reason': '; '.join(profile.development_blockers),
            'contacts': [asdict(c) for c in profile.contacts],
            'trades': [asdict(profile.trade)],
        }


# ---------- 便捷函数 ----------
_center = None
def get_center() -> AccountIntelligenceCenter:
    global _center
    if _center is None:
        _center = AccountIntelligenceCenter()
    return _center

def process(norm: str) -> dict:
    return get_center().process_lead(norm)


# ---------- 前端兼容函数 ----------

def get(norm: str) -> dict:
    """前端API兼容：获取单个客户情报。"""
    center = get_center()
    data = center.get_intelligence(norm)
    if not data:
        return None
    return data


def list_all(kind=None, zone=None, min_completeness=0, min_score=0.0, limit=50, offset=0) -> list:
    """前端API兼容：列出客户情报列表。"""
    db = DB()
    # 从 leads 表查询，结合情报中心数据
    leads = db.list_leads(kind=kind, zone=zone, limit=limit + offset)
    results = []
    center = get_center()
    for lead in leads[offset:]:
        norm = lead.get('norm')
        if not norm:
            continue
        intel = center.get_intelligence(norm)
        if not intel:
            continue
        # 过滤条件
        completeness = intel.get('info_completeness', 0)
        if completeness < min_completeness:
            continue
        score = intel.get('value_score', {}).get('total', 0)
        if score < min_score:
            continue
        results.append({
            'norm': norm,
            'name': intel.get('name', ''),
            'country': intel.get('country', ''),
            'completeness': completeness,
            'score': score,
            'grade': intel.get('value_grade', 'D'),
            'status': intel.get('development_status', 'pending'),
            'contacts_count': len(intel.get('contacts', [])),
            'last_trade': intel.get('last_trade_date', ''),
        })
    return results
