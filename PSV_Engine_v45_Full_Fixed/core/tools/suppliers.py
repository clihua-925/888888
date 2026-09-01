# -*- coding: utf-8 -*-
"""供应商池：从海关提单的 shipper 字段透视"同行工厂"，生成 ImportYeti slug 供反向收割。"""
import re,sqlite3,time
from core.config import settings
SUF=re.compile(r'\b(inc|llc|ltd|co|corp|corporation|company|import|imports|export|exports|trading|trade|group|factory|industrial|industry|international|intl)\b\.?',re.I)
BAD=re.compile(r'on behalf of|freight|forwarder|logistics|express|cargo|customs broker|shipping',re.I)
def norm(s): return re.sub(r'[^a-z0-9一-鿿]+','',SUF.sub('',str(s or '').lower()))
def slugify(name):
    """公司名 → ImportYeti 风格 slug：Shenzhen Aroma Bay Trading Co., Ltd → shenzhen-aroma-bay"""
    s=SUF.sub(' ',str(name or '').lower())
    s=re.sub(r'[^a-z0-9一-鿿]+','-',s)
    s=re.sub(r'-{2,}','-',s).strip('-')
    return s
def pool(days=90,min_shipments=1):
    """近 N 天提单里的活跃供应商，附收割状态。返回 [{name,norm,slug,shipments,last_seen,harvested}]"""
    cutoff=time.time()-days*86400
    conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
    rows=conn.execute('SELECT shipper,COUNT(*) sh,MAX(ts) ls FROM customs_raw WHERE ts>=? AND shipper!="" GROUP BY shipper HAVING sh>=? ORDER BY sh DESC',(cutoff,min_shipments)).fetchall()
    done={r['supplier_norm']:r for r in conn.execute('SELECT * FROM suppliers')}
    conn.close()
    out=[]; seen=set()
    for r in rows:
        nm=r['shipper']
        if not nm or BAD.search(nm): continue
        n=norm(nm)
        if not n: continue
        d=done.get(n)
        seen.add(n)
        out.append({'name':nm,'norm':n,'slug':(d['slug'] if d and d['slug'] else slugify(nm)),
                    'shipments':r['sh'],'last_seen':r['ls'],'harvested':bool(d and d['harvested_at']),
                    'bol_fetched':(d['bol_fetched'] if d else 0),'via':'customs'})
    # 网页种子：ImportYeti 搜索卡片直接入池的同行工厂（slug 精确，未收割过的才放行）
    for n,d in done.items():
        if n in seen or d['harvested_at']: continue
        out.append({'name':d['name'],'norm':n,'slug':d['slug'],'shipments':d['shipments'] or 0,
                    'last_seen':d['last_seen'],'harvested':False,'bol_fetched':d['bol_fetched'] or 0,'via':'web'})
    out.sort(key=lambda x:-(x['shipments'] or 0))
    return out
def upsert_pool(entries):
    now=time.time()
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        from core.trade_graph.trade_node import is_non_company_name
        for e in entries:
            if is_non_company_name(e.get('name')): continue  # v35 伪实体最终闸
            c.execute('INSERT INTO suppliers(supplier_norm,name,slug,shipments,first_seen,last_seen,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(supplier_norm) DO UPDATE SET name=excluded.name,slug=excluded.slug,shipments=excluded.shipments,last_seen=excluded.last_seen,updated_at=excluded.updated_at',
                      (e['norm'],e['name'],e['slug'],e['shipments'],now,e['last_seen'],now))
def mark_harvested(supplier_norm,bol_count):
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('UPDATE suppliers SET harvested_at=?,bol_fetched=bol_fetched+?,updated_at=? WHERE supplier_norm=?',(time.time(),bol_count,time.time(),supplier_norm))
def log_harvest(task_id,slug,supplier,mode,status,items,note):
    with sqlite3.connect(settings.DATABASE_PATH) as c:
        c.execute('INSERT INTO harvest_log(task_id,slug,supplier,mode,status,items,note,created_at) VALUES(?,?,?,?,?,?,?,?)',(task_id,slug,supplier,mode,status,items,str(note or '')[:200],time.time()))
