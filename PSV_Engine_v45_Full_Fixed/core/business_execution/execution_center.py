# -*- coding: utf-8 -*-
"""Business Execution Center v42
核心职责：承接客户情报中心，执行开发信和销售动作。
硬性门槛：客户真实存在、有贸易证据、信息补全>=50%、联系人存在、邮箱验证通过
禁止：自动发送邮件。必须生成草稿，由用户手动点击发送。
流程：客户情报中心 → 开发资格客户 → 联系人 → 邮箱验证 → AI生成开发信 → Outlook草稿 → 用户发送 → 记录状态
"""

import json, time, uuid, os, sys
from typing import Dict, List, Optional
from core.memory.db import DB
from core.intelligence.ai_router import ai_route
from core.intelligence.account_intelligence_center import get_center as get_ai_center

class BusinessExecutionCenter:
    def __init__(self):
        self.db = DB()

    def qualify_for_development(self, norm: str) -> dict:
        intelligence = get_ai_center().get_intelligence(norm)
        if not intelligence:
            return {'ok': False, 'qualified': False, 'reason': '客户情报不存在，请先进入客户情报中心处理', 'thresholds': {}}

        thresholds = {
            'customer_exists': bool(intelligence.get('name')),
            'has_trade_evidence': intelligence.get('ai_verified', False),
            'info_completeness': intelligence.get('info_completeness', 0) >= 50,
            'has_contact': len(intelligence.get('contacts', [])) > 0,
            'email_verified': any(c.get('email_verified') for c in intelligence.get('contacts', [])),
        }
        # v42：移除 value_grade_not_d 硬性门槛，改为软性警告
        qualified = all(thresholds.values())
        reasons = []
        if not thresholds['customer_exists']: reasons.append('客户信息不存在')
        if not thresholds['has_trade_evidence']: reasons.append('无贸易证据或AI验证未通过')
        if not thresholds['info_completeness']: reasons.append(f"信息完整度不足：{intelligence.get('info_completeness', 0)}% < 50%")
        if not thresholds['has_contact']: reasons.append('无联系人信息')
        if not thresholds['email_verified']: reasons.append('无验证通过的联系人邮箱')

        warnings = []
        if intelligence.get('value_grade', 'D') == 'D':
            warnings.append('价值评分为D级，建议先通过情报中心提升档案质量')

        return {
            'ok': True, 
            'qualified': qualified, 
            'reason': '；'.join(reasons), 
            'warnings': warnings,
            'thresholds': thresholds, 
            'intelligence': intelligence
        }

    def create_dev_letter(self, norm: str, template: str = None, personalization_hints: dict = None) -> dict:
        qual = self.qualify_for_development(norm)
        if not qual['qualified']:
            return {'ok': False, 'error': '未通过开发资格检查', 'qualification': qual}

        intelligence = qual['intelligence']
        primary_contact = None
        for c in intelligence.get('contacts', []):
            if c.get('is_primary') or c.get('email_verified'):
                primary_contact = c
                break
        if not primary_contact:
            return {'ok': False, 'error': '无有效主联系人'}

        letter_result = self._ai_generate_letter(intelligence, primary_contact, template, personalization_hints)
        if not letter_result['ok']:
            return {'ok': False, 'error': 'AI生成开发信失败：' + letter_result.get('error', '')}

        record_id = self.db.create_execution_record(
            norm=norm, execution_type='dev_letter',
            draft_subject=letter_result['subject'], draft_body=letter_result['body'],
            personalized_content=letter_result['personalized'],
            recipient_email=primary_contact.get('email', '')
        )

        # v42：生成多种Outlook草稿方式
        outlook_options = self._generate_outlook_options(
            to=primary_contact.get('email', ''),
            subject=letter_result['subject'], 
            body=letter_result['body']
        )
        self.db.update_execution_status(record_id, 'draft', outlook_draft_url=outlook_options.get('web_url'))

        return {
            'ok': True, 
            'record_id': record_id, 
            'norm': norm,
            'recipient': {
                'name': primary_contact.get('contact_name'), 
                'email': primary_contact.get('email'), 
                'title': primary_contact.get('title')
            },
            'draft': {
                'subject': letter_result['subject'], 
                'body': letter_result['body'], 
                'personalized': letter_result['personalized']
            },
            'outlook_options': outlook_options,
            'status': 'draft',
            'note': '草稿已生成。请选择以下任一方式打开Outlook预览并手动发送：1) Web Outlook 2) 本地Outlook 3) Mailto链接',
            'warnings': qual.get('warnings', [])
        }

    def _generate_outlook_options(self, to: str, subject: str, body: str) -> dict:
        """生成Web和本地Outlook草稿选项"""
        import urllib.parse
        # Web Outlook
        web_base = "https://outlook.office.com/mail/deeplink/compose"
        web_url = web_base + "?" + urllib.parse.urlencode({
            'to': to, 
            'subject': subject, 
            'body': body
        })

        # 本地 Outlook COM 命令（Windows）
        local_type = 'win32com' if sys.platform == 'win32' else 'mailto'

        # Mailto 作为跨平台备选
        mailto = f"mailto:{urllib.parse.quote(to)}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body[:1000])}"

        return {
            'web_url': web_url,
            'local_type': local_type,
            'mailto': mailto,
            'instruction': 'Windows用户建议用本地Outlook打开；Mac/Linux用户可用mailto或Web Outlook'
        }

    def open_local_outlook_draft(self, to: str, subject: str, body: str) -> dict:
        """Windows环境下直接打开本地Outlook草稿（需用户手动点击发送）"""
        if sys.platform != 'win32':
            return {'ok': False, 'error': '本地Outlook草稿仅支持Windows，请使用Web Outlook或mailto链接'}
        try:
            import win32com.client
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            mail.To = to
            mail.Subject = subject
            mail.HTMLBody = body
            mail.Display(True)  # True = 模态显示，用户必须手动关闭/发送
            return {'ok': True, 'method': 'local_outlook', 'note': 'Outlook草稿窗口已打开，请检查并手动点击发送'}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'fallback': '请使用web_url或mailto'}

    def _ai_generate_letter(self, intelligence: dict, contact: dict, template: str = None, hints: dict = None) -> dict:
        company_name = intelligence.get('name', 'Valued Partner')
        country = intelligence.get('country', '')
        products = intelligence.get('product_categories', [])
        if isinstance(products, str):
            products = [products] if products else []
        trades = intelligence.get('trades', [])
        recent_trade = trades[0] if trades else {}
        if isinstance(recent_trade, dict):
            recent_product = recent_trade.get('product', '相关')
            recent_count = recent_trade.get('shipment_count', 0)
        else:
            recent_product = '相关'
            recent_count = 0

        prompt = f"""请为以下潜在客户生成一封专业的外贸开发信。

客户信息：
- 公司名称：{company_name}
- 国家：{country}
- 联系人：{contact.get('contact_name', contact.get('name', 'Manager'))}
- 职位：{contact.get('title', 'Purchasing Manager')}
- 产品类别：{', '.join(products) if products else '相关品类'}
- 最近贸易：{recent_product}，{recent_count}票记录

要求：
1. 邮件标题简洁有力，包含客户公司名或产品
2. 正文不超过200词
3. 必须个性化：提及客户的贸易背景或产品
4. 语气专业、礼貌、不推销过度
5. 包含明确的CTA（行动号召）
6. 签名包含发件人信息

{f'参考模板：{template}' if template else ''}

请输出JSON格式：
{{"subject": "邮件标题", "body": "邮件正文（HTML格式）", "personalized_snippets": ["片段1"], "tone": "professional", "cta": "行动号召"}}

如果信息不足，请明确说明。"""

        result = ai_route(
            prompt=prompt,
            system="你是资深外贸销售文案专家，擅长写高回复率的开发信。只输出JSON。",
            schema={"type": "object", "required": ["subject", "body"], "properties": {
                "subject": {"type": "string"}, "body": {"type": "string"},
                "personalized_snippets": {"type": "array"}, "tone": {"type": "string"}, "cta": {"type": "string"}
            }}
        )

        if not result['ok']:
            return {'ok': False, 'error': result.get('error', 'AI调用失败')}
        s = result['structured'] or {}
        return {
            'ok': True,
            'subject': s.get('subject', f"Partnership Opportunity with {company_name}"),
            'body': s.get('body', ''),
            'personalized': json.dumps(s.get('personalized_snippets', []), ensure_ascii=False),
            'tone': s.get('tone', 'professional'),
            'cta': s.get('cta', '')
        }

    def mark_sent(self, record_id: int, sender_email: str = None) -> dict:
        self.db.update_execution_status(record_id, 'sent', sent_at=time.time(), sender_email=sender_email)
        return {'ok': True, 'status': 'sent', 'record_id': record_id}

    def mark_opened(self, record_id: int) -> dict:
        self.db.update_execution_status(record_id, 'opened', opened_at=time.time())
        return {'ok': True, 'status': 'opened'}

    def mark_replied(self, record_id: int) -> dict:
        self.db.update_execution_status(record_id, 'replied', replied_at=time.time())
        return {'ok': True, 'status': 'replied'}

    def list_pending_review(self, limit: int = 50) -> List[dict]:
        return self.db.list_execution_records(status='draft', limit=limit)

    def get_execution_pipeline(self, norm: str = None) -> dict:
        records = self.db.list_execution_records(norm=norm, limit=100)
        pipeline = {'draft': [], 'review_pending': [], 'sent': [], 'opened': [], 'replied': [], 'bounced': []}
        for r in records:
            status = r.get('status', 'draft')
            if status in pipeline: pipeline[status].append(r)
        return {
            'ok': True, 'total': len(records), 'pipeline': pipeline,
            'conversion': {
                'sent_rate': len(pipeline['sent']) / max(1, len(pipeline['draft']) + len(pipeline['sent'])),
                'reply_rate': len(pipeline['replied']) / max(1, len(pipeline['sent']))
            }
        }

_center = None
def get_center() -> BusinessExecutionCenter:
    global _center
    if _center is None: _center = BusinessExecutionCenter()
    return _center

def qualify(norm: str) -> dict: return get_center().qualify_for_development(norm)
def create_letter(norm: str, **kwargs) -> dict: return get_center().create_dev_letter(norm, **kwargs)
def pipeline(norm: str = None) -> dict: return get_center().get_execution_pipeline(norm)
