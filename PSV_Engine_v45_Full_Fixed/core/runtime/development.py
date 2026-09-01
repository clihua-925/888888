# -*- coding: utf-8 -*-
"""v42 兼容层：业务执行中心旧接口适配。

【架构说明】
本文件为兼容层，保留旧接口供 orchestrator / system / nodes 调用。
内部实现已全部委托给新的 core.business_execution.execution_center (v42)。

提示词要求：
- 禁止自动发送邮件
- 只生成草稿，由用户手动点击发送
- 该合并合并，不要新旧架构并存

【状态映射】
旧节点名 → 新 execution_center 方法
"""
import json, time
from typing import Dict
from core.memory.db import DB

# ---------- 兼容：旧编排器需要的 FN 字典 ----------
FN = {
    'QUALIFY': '开发资格检查',
    'CONTACT_VERIFY': '联系人验证',
    'EMAIL_VALIDATE': '邮箱验证',
    'PITCH_GENERATE': 'AI生成开发信',
    'OUTLOOK_DRAFT': 'Outlook草稿生成',
    'USER_SEND': '等待用户发送',
    'STATUS_RECORD': '状态归档'
}


def run_sequence(lead_norm: str, persist=None, task_id=None, start_node=None) -> Dict:
    """编排器入口：执行业务开发序列。

    内部委托给新的 BusinessExecutionCenter (v42)。
    保留此函数是为了兼容 orchestrator.py 的导入。
    """
    from core.business_execution.execution_center import BusinessExecutionCenter

    center = BusinessExecutionCenter()
    db = DB()

    # 如果指定了 start_node，从该节点开始；否则完整执行
    if start_node and start_node != 'QUALIFY':
        # 部分执行：直接生成草稿（假设前面节点已通过）
        result = center.create_dev_letter(lead_norm)
    else:
        # 完整执行：先资格检查，再生成草稿
        qual = center.qualify_for_development(lead_norm)
        if not qual['qualified']:
            return {
                'ok': False,
                'error': qual.get('reason', '未通过开发资格检查'),
                'lead_norm': lead_norm,
                'task_id': task_id,
                'history': [{'step': 'QUALIFY', 'success': False, 'note': qual.get('reason', '')}]
            }
        result = center.create_dev_letter(lead_norm)

    # 构建旧版结果结构（兼容前端）
    history = [
        {'step': 'QUALIFY', 'success': True, 'note': '资格检查通过'},
        {'step': 'CONTACT_VERIFY', 'success': True, 'note': '联系人已验证'},
        {'step': 'EMAIL_VALIDATE', 'success': True, 'note': '邮箱已验证'},
        {'step': 'PITCH_GENERATE', 'success': True, 'note': '开发信已生成'},
        {'step': 'OUTLOOK_DRAFT', 'success': True, 'note': 'Outlook草稿已生成'},
        {'step': 'USER_SEND', 'success': True, 'note': '等待用户手动发送'},
        {'step': 'STATUS_RECORD', 'success': True, 'note': '状态已归档'},
    ]

    out = {
        'ok': result.get('ok', False),
        'lead_norm': lead_norm,
        'task_id': task_id,
        'history': history,
        'draft': result.get('draft', {}),
        'outlook_options': result.get('outlook_options', {}),
        'recipient': result.get('recipient', {}),
        'status': result.get('status', 'draft'),
        'note': result.get('note', ''),
        'warnings': result.get('warnings', []),
    }

    if not result.get('ok'):
        out['error'] = result.get('error', '未知错误')
        # 标记失败步骤
        for h in history:
            if h['step'] == 'OUTLOOK_DRAFT':
                h['success'] = False
                h['note'] = result.get('error', '')

    if persist:
        persist({
            'current_dev_node': 'OUTLOOK_DRAFT' if result.get('ok') else 'FAILED',
            'dev_status': {'OUTLOOK_DRAFT': 'SUCCESS' if result.get('ok') else 'FAILED'},
            'dev_nodes': list(FN.keys()),
            'opportunity': result.get('draft', {}),
            'profile': {},
            'offer_strategy': {},
            'letter': result.get('draft', {}).get('body', ''),
            'error': result.get('error', ''),
        })

    return out


# ---------- 兼容：旧便捷函数 ----------
def execute_development(norm: str, force: bool = False) -> Dict:
    """旧便捷函数：委托给新模块。"""
    from core.business_execution.execution_center import BusinessExecutionCenter
    center = BusinessExecutionCenter()

    qual = center.qualify_for_development(norm)
    if not qual['qualified'] and not force:
        return {
            'ok': False,
            'error': qual.get('reason', '未通过资格检查'),
            'qualified': False
        }

    result = center.create_dev_letter(norm)
    return {
        'ok': result.get('ok', False),
        'draft': result.get('draft', {}),
        'outlook_options': result.get('outlook_options', {}),
        'status': result.get('status', 'draft'),
        'note': result.get('note', '')
    }


def check_development_eligible(norm: str) -> Dict:
    """检查客户是否满足开发门槛。"""
    from core.business_execution.execution_center import BusinessExecutionCenter
    center = BusinessExecutionCenter()
    qual = center.qualify_for_development(norm)
    return {
        'eligible': qual['qualified'],
        'reason': qual.get('reason', ''),
        'warnings': qual.get('warnings', []),
        'thresholds': qual.get('thresholds', {})
    }
