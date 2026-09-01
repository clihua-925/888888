# -*- coding: utf-8 -*-
"""v42 Outlook Draft Generator —— 微软邮箱草稿生成器（销售执行层）。

原则（提示词硬性要求）：
- 禁止自动发送邮件。
- 禁止后台自动点击"发送"按钮。
- 只生成邮件草稿，由用户手动打开 Outlook 并点击发送。

链路：预检 → 生成草稿数据 → 提供多种打开方式（Web Outlook / 本地Outlook / Mailto）→ 状态写为 draft_created。
"""
import time
import urllib.parse
from typing import Dict, Optional
from core.config import settings
from core.memory.db import DB


def preflight(norm: str) -> tuple:
    """预检：返回 (ok, ctx, error)。ctx 含 msg/to/subject/body；error 是人话原因。"""
    db = DB()
    msg = db.latest_out_message(norm)
    if not msg or not msg.get('draft'):
        return False, {}, '没有可发送的开发信草稿'

    content = msg.get('content', '')
    subject, body = 'PSV introduction', content
    lines = content.splitlines()
    if lines and lines[0].lower().startswith('subject:'):
        subject = lines[0].split(':', 1)[1].strip() or subject
        body = '\n'.join(lines[1:]).strip()

    to = ''
    contacts = db.list_contacts(norm)
    rec = next((c for c in contacts if c.get('email') and c.get('email_status') in ('mx_ok', 'pattern', 'syntax_ok')), None)
    if rec:
        to = rec['email']
    if not to:
        import re
        lead = db.get_lead(norm) or {}
        to = next((e for e in re.split(r'[,;\s]+', str(lead.get('emails') or '')) if '@' in e), '')
    if not to:
        return False, {}, '无收件人：请先补全或找联系人'

    return True, {'msg': msg, 'to': to, 'subject': subject, 'body': body}, ''


def generate_draft_options(to: str, subject: str, body: str) -> Dict:
    """生成多种 Outlook 草稿打开选项，供用户手动选择。"""

    # 1. Web Outlook（Office 365 / Outlook.com）
    web_base = "https://outlook.office.com/mail/deeplink/compose"
    web_url = web_base + "?" + urllib.parse.urlencode({
        'to': to,
        'subject': subject,
        'body': body
    })

    # 2. Mailto 链接（跨平台通用）
    mailto = f"mailto:{urllib.parse.quote(to)}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body[:2000])}"

    # 3. 本地 Outlook COM（仅 Windows）
    local_outlook_available = False
    try:
        import win32com.client
        local_outlook_available = True
    except ImportError:
        pass

    return {
        'web_outlook_url': web_url,
        'mailto_link': mailto,
        'local_outlook_available': local_outlook_available,
        'instruction': (
            "请选择以下任一方式打开 Outlook 草稿并手动发送：\n"
            "1) Web Outlook：在浏览器中打开 web_outlook_url\n"
            "2) Mailto：点击 mailto_link（将唤起系统默认邮件客户端）\n"
            "3) 本地 Outlook（Windows）：调用 open_local_outlook_draft()"
        )
    }


def open_local_outlook_draft(to: str, subject: str, body: str) -> Dict:
    """Windows 环境下直接打开本地 Outlook 草稿窗口（需用户手动点击发送）。

    禁止：任何自动点击发送的行为。
    """
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = to
        mail.Subject = subject
        mail.HTMLBody = body
        mail.Display(True)  # True = 模态显示，用户必须手动关闭/发送
        return {
            'ok': True,
            'method': 'local_outlook',
            'note': 'Outlook 草稿窗口已打开。请检查内容并手动点击"发送"。'
        }
    except ImportError:
        return {
            'ok': False,
            'error': '未安装 pywin32，无法调用本地 Outlook。请使用 Web Outlook 或 Mailto 链接。',
            'fallback': 'web_outlook_url'
        }
    except Exception as e:
        return {
            'ok': False,
            'error': f'打开本地 Outlook 失败：{str(e)[:200]}',
            'fallback': 'web_outlook_url'
        }


def create_draft(norm: str) -> Dict:
    """为客户生成 Outlook 草稿，状态写为 draft_created。

    返回值：
        {'ok': True, 'status': 'draft_created', 'options': {...}, 'to': ..., 'subject': ..., 'body': ...}
        {'ok': False, 'status': 'ready_to_send', 'error': ...}
    """
    db = DB()
    ok, ctx, err = preflight(norm)
    if not ok:
        return {'ok': False, 'status': 'ready_to_send', 'error': err}

    msg, to, subject, body = ctx['msg'], ctx['to'], ctx['subject'], ctx['body']

    # 生成草稿选项
    options = generate_draft_options(to, subject, body)

    # 更新状态为草稿已创建（禁止自动发送）
    db.set_message_status(msg['id'], 'draft_created')
    db.add_enrichment_event(norm, 'outreach', 'outlook_draft_created', to, True)

    return {
        'ok': True,
        'status': 'draft_created',
        'to': to,
        'subject': subject,
        'body_preview': body[:500],
        'options': options,
        'note': '草稿已生成。请用户选择上述任一方式打开 Outlook 并手动点击发送。'
    }


def mark_user_sent(norm: str, msg_id: Optional[str] = None, sender_email: Optional[str] = None) -> Dict:
    """用户手动发送后，由外部系统（如 WebUI 用户点击"我已发送"）调用，记录状态。"""
    db = DB()
    if not msg_id:
        msg = db.latest_out_message(norm)
        if not msg:
            return {'ok': False, 'error': '未找到消息记录'}
        msg_id = msg['id']

    db.set_message_status(msg_id, 'sent', sent=True, sender_email=sender_email)
    db.add_enrichment_event(norm, 'outreach', 'user_confirmed_sent', sender_email or '', True)
    return {'ok': True, 'status': 'sent', 'note': '已记录用户发送状态'}
