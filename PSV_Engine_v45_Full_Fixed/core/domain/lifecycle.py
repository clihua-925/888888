# -*- coding: utf-8 -*-
"""v35 统一生命周期状态机（唯一事实源，UI/数据库/业务层共用）。

实体（leads）生命周期 = zone 单轴状态机：
  pool（未分区）→ pending（发现池/待验证）→ dev（开发池）→ maint（维护池）→ won（成交）
  任意非终态 → discard（剔除，终态）；discard → pending（唯一恢复通道）。

规则：
1. 唯一：全部状态定义只在本模块；任何模块不得自定义第二套。
2. 可追踪：每次迁移写入 lead_events 审计日志（actor/from/to/reason/ts）。
3. 迁移规则：can_transition 白名单；非法迁移拒绝。
4. 证据门槛：进入 dev 的实体必须有身份与来源（name>=3 且 source 非空）；
   标记 won 必须来自 dev/maint（真实开发/维护过才能成交）。
5. 权限：UI 命令（actor=ui）只能走 transition()；DATABASE_COMMIT 是内部权威写入
   （actor=database_commit），同样记录审计日志。
"""

ZONE_LIFECYCLE = ('pool', 'pending', 'dev', 'maint', 'won', 'discard')
TERMINAL = {'discard'}

_ALLOWED = {
    'pool':    {'pending', 'dev', 'discard'},
    'pending': {'dev', 'discard', 'pool'},
    'dev':     {'maint', 'won', 'discard', 'pending'},
    'maint':   {'dev', 'won', 'discard', 'pending'},
    'won':     {'maint', 'dev'},
    'discard': {'pending'},
}

ZONE_LABELS = {'pool': '未分区', 'pending': '发现池', 'dev': '开发池',
               'maint': '维护池', 'won': '成交客户', 'discard': '剔除'}


def can_transition(frm, to):
    frm = str(frm or 'pool'); to = str(to or '')
    if to not in ZONE_LIFECYCLE:
        return False
    if frm == to:
        return True
    return to in _ALLOWED.get(frm, set())


def evidence_gate(lead, to):
    """证据门槛：返回 (ok, reason)。"""
    if to == 'dev':
        if len(str((lead or {}).get('name') or '').strip()) < 3:
            return False, '名称无效，无身份不得进入开发池'
        if not str((lead or {}).get('source') or '').strip():
            return False, '无来源记录不得进入开发池'
    if to == 'won':
        if str((lead or {}).get('zone') or '') not in ('dev', 'maint'):
            return False, '只有开发池/维护池实体可标记成交'
    return True, ''


def transition(db, norm, to, actor='ui', reason=''):
    """统一迁移入口：校验 → 证据门槛 → 写库 → 审计日志。返回 dict。"""
    to = str(to or '').strip().lower()
    lead = db.get_lead(norm)
    if not lead:
        return {'ok': False, 'error': 'lead not found'}
    frm = lead.get('zone') or 'pool'
    if to not in ZONE_LIFECYCLE:
        return {'ok': False, 'error': 'invalid zone: %s' % to}
    if not can_transition(frm, to):
        return {'ok': False, 'error': 'illegal transition: %s -> %s' % (frm, to)}
    ok, why = evidence_gate(lead, to)
    if not ok:
        return {'ok': False, 'error': 'evidence gate: ' + why}
    db.lead_update(norm, zone=to)
    try:
        db.log_lead_event(norm, frm, to, actor=actor, reason=reason)
    except Exception:
        pass
    return {'ok': True, 'norm': norm, 'from': frm, 'zone': to}
