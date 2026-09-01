# -*- coding: utf-8 -*-
"""[DEPRECATED v42] mailer.py 已废弃。

原功能已被以下模块取代：
- core/tools/outlook_send.py —— Outlook 草稿生成器
- core/business_execution/execution_center.py —— 业务执行中心（内含 _generate_outlook_options）

保留此文件仅为防止遗留测试引用报错。
请勿在新代码中使用。
"""
import urllib.parse
from core.config import settings

COMPOSE = {
    'gmail': 'https://mail.google.com/mail/?view=cm&fs=1&to={to}&su={su}&body={body}&cc={cc}',
    'outlook': 'https://outlook.live.com/mail/0/deeplink/compose?to={to}&subject={su}&body={body}&cc={cc}',
}

def compose_url(to, subject, body, cc_list=None, provider=None):
    tpl = COMPOSE.get(str(provider or getattr(settings, 'MAIL_PROVIDER', 'outlook') or 'outlook').lower(), COMPOSE['outlook'])
    q = lambda s: urllib.parse.quote(str(s or ''), safe='')
    cc = ','.join(cc_list) if cc_list else ''
    return tpl.format(to=q(to), su=q(su), body=q(body), cc=q(cc))

def smtp_configured():
    return bool(getattr(settings, 'SMTP_HOST', '') and getattr(settings, 'SMTP_USER', '') and getattr(settings, 'SMTP_PASS', ''))
