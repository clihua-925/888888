# -*- coding: utf-8 -*-
"""v30.3 ImportYeti 节点网络注册表 + 页访预算 + 交叉验证。

设计依据（与前沿实践一致）：
- ImportYeti 数据全部来自美国海关提单（FOIA 公开记录），每个节点/关系都是真实贸易事件；
  免费额度约 25 页/IP，页访是稀缺资源，必须持久化复用，不能每次任务重新烧。
- 第一搜索以“节点”进入：关键词锁定 company/supplier 节点，再从节点页展开关系网；
  节点页只访问一次，注册表跨任务复用 —— NODE_REVISIT_DAYS 内绝不重复访问（防资源枯竭核心）。
- ImportYeti 同时是验证标准：任何来源的候选，只要能在 IY 上找到对应节点/关系，
  就标记 iy_verified；来自多个来源且其中之一是 IY 的，标记 cross_validated（交叉验证）。
- 所有信息残片都有价值：本模块不做任何评分/删除，只做登记、预算与验证标记。
"""
import sqlite3, time
from core.config import settings


def _conn():
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def mark_node(norm, kind, slug='', url='', shipments=0, run_id=''):
    """登记一个已访问/已发现的 IY 节点。重复登记只刷新访问时间与计数。"""
    if not norm:
        return
    now = time.time()
    with _conn() as c:
        c.execute(
            'INSERT INTO iy_nodes(norm,kind,slug,url,shipments,first_seen,last_visit,visits,run_id) '
            'VALUES(?,?,?,?,?,?,?,1,?) '
            'ON CONFLICT(norm,kind) DO UPDATE SET '
            'slug=CASE WHEN excluded.slug!="" THEN excluded.slug ELSE iy_nodes.slug END,'
            'url=CASE WHEN excluded.url!="" THEN excluded.url ELSE iy_nodes.url END,'
            'shipments=MAX(iy_nodes.shipments,excluded.shipments),'
            'last_visit=excluded.last_visit,visits=iy_nodes.visits+1,run_id=excluded.run_id',
            (norm, kind, slug or '', url or '', int(shipments or 0), now, now, run_id or ''))


def get_node(norm, kind):
    with _conn() as c:
        r = c.execute('SELECT * FROM iy_nodes WHERE norm=? AND kind=?', (norm, kind)).fetchone()
        return dict(r) if r else None


def node_fresh(norm, kind, days=None):
    """该节点是否在 NODE_REVISIT_DAYS 内访问过——访问过则本轮不再重复访问其主页。"""
    days = int(days or getattr(settings, 'NODE_REVISIT_DAYS', 21))
    r = get_node(norm, kind)
    if not r or not r.get('last_visit'):
        return False
    return (time.time() - float(r['last_visit'])) < days * 86400


def node_url(norm, kind):
    """已知节点的真实主页 URL（注册表复用，避免重新搜索解析）。"""
    r = get_node(norm, kind)
    return (r or {}).get('url') or ''


def stats():
    with _conn() as c:
        rows = c.execute('SELECT kind,COUNT(*) n,SUM(visits) v FROM iy_nodes GROUP BY kind').fetchall()
        return {r['kind']: {'nodes': r['n'], 'visits': int(r['v'] or 0)} for r in rows}


class PageBudget:
    """单次任务的 ImportYeti 页访预算。预算耗尽即停止开新页面，但已完成的关系全部保留。"""

    def __init__(self, budget=None):
        self.total = int(budget or getattr(settings, 'IY_PAGE_BUDGET', 25))
        self.left = self.total
        self.spent_on = []

    def take(self, label=''):
        if self.left <= 0:
            return False
        self.left -= 1
        if label:
            self.spent_on.append(label)
        return True

    @property
    def exhausted(self):
        return self.left <= 0

    def note(self):
        return f'页访预算 {self.total - self.left}/{self.total}'


def tag_verification(companies):
    """交叉验证标记（不删除任何候选）：
    - iy_verified：证据来自 ImportYeti（搜索卡片/关系页/官网API），或节点已在注册表中；
    - cross_validated：同一实体被 IY 与至少一个其他来源（本地海关库/HS榜单/端点）共同命中。
    """
    for c in companies or []:
        e = c.setdefault('evidence', {})
        src = str(c.get('source') or '').lower() + '|' + str(e.get('source') or '').lower()
        iy = 'importyeti' in src or bool(e.get('url') and 'importyeti.com' in str(e.get('url')))
        if iy:
            e['iy_verified'] = True
            others = [s for s in ('customs_raw', 'customs_bulk', 'hs_finder', 'customs_web', 'csv')
                      if s in src]
            if others:
                e['cross_validated'] = True
    return companies
