# -*- coding: utf-8 -*-
"""v16: ImportYeti Product Finder by HS Code 采集器。
/hs-codes/{code} 页面按 Top / New / Fast Growing 三个切片抓取进口商榜（每片约7家），
并解析页底的近期提单表得到带证据的供应商种子（slug/日期/重量/品类描述）。
全部产出写入标准化 leads 表；供应商种子同时进 suppliers 池（via=hs_bol）。"""
import re,time,json,urllib.parse
from pathlib import Path
from core.config import settings

HS_SLUG={3406:'3406-candles-tapers-and-the-like'}
CHIPS=['Top','New','Fast Growing']
BIRTHDAY=re.compile(r'birthday|spiral|number candle|party candle',re.I)
CANDLE=re.compile(r'candle|wax|tealight|taper',re.I)
FORWARDER=re.compile(r'logistics|freight|forwarder|shipping|transatlantic|worldwide\s|express|cargo|supply chain',re.I)

def segment_of(text):
    t=str(text or '')
    if BIRTHDAY.search(t): return 'birthday'
    if CANDLE.search(t): return 'candle'
    return ''

def _clean(s): return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',str(s or ''))).strip()

def parse_companies(html,chip):
    """公司榜表格：name/country/tags/shipments/desc。返回标准化 lead dict 列表。"""
    out=[]
    for rw in re.findall(r'<tr class="[^"]*">(.*?)</tr>',html,re.S):
        m=re.search(r'href="/company/([^"]+)"[^>]*>([^<]+)',rw)
        if not m: continue
        slug,name=m.group(1),m.group(2).strip()
        flag=re.search(r'fflag-([A-Z]{2})',rw)
        tds=re.findall(r'<td[^>]*>(.*?)</td>',rw,re.S)
        txt=[_clean(t) for t in tds]
        ship=0;desc=''
        for t in txt:
            mm=re.match(r'^([\d,]+)\s',t)
            if mm and not ship: ship=int(mm.group(1).replace(',',''))
            if 'bills of lading' in t: desc=re.sub(r'\s*See all bills of lading.*$','',t).strip()
        tags=[chip] if chip else []
        for extra in ('Top','Fast Growing','New'):
            if extra!=chip and re.search(r'\b'+re.escape(extra)+r'\b',rw) and extra not in tags: tags.append(extra)
        out.append({'name':name,'slug':slug,'country':flag.group(1) if flag else '',
                    'kind':'importer','shipments':ship,'tags':tags,
                    'segment':segment_of(desc),'desc_sample':desc[:300],'source':'hs_finder'})
    return out

def parse_bol_suppliers(html,hs_code):
    """页底近期提单表：date/BOL/supplier+slug/weight/desc → 供应商种子。"""
    out=[]
    for rw in re.findall(r'<tr class="[^"]*">(.*?)</tr>',html,re.S):
        m=re.search(r'href="/supplier/([^"]+)"[^>]*>([^<]+)',rw)
        if not m: continue
        slug,name=m.group(1),m.group(2).strip()
        tds=[_clean(t) for t in re.findall(r'<td[^>]*>(.*?)</td>',rw,re.S)]
        date=tds[0] if tds and re.match(r'\d{2}/\d{2}/\d{4}',tds[0]) else ''
        weight='';desc=''
        for t in tds:
            if re.search(r'kg$',t): weight=t
            if t in ('Candles','Candle') or CANDLE.search(t) and len(t)<60 and 'kg' not in t: desc=t
        if FORWARDER.search(name): continue  # 货代/物流不是同行工厂
        flag=re.search(r'fflag-([A-Z]{2})',rw)
        out.append({'name':name,'slug':slug,'country':flag.group(1) if flag else '',
                    'kind':'supplier','hs_code':str(hs_code),'last_shipment':date,
                    'weight':weight,'segment':segment_of(desc or 'candle'),'desc_sample':desc,
                    'source':'hs_finder'})
    return out

# ---------- 浏览器层（与 iy_web 同一套 CDP 思路） ----------
def _cdp_alive(url):
    import urllib.request
    try:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url+'/json/version',timeout=4) as r: return r.status==200
    except Exception: return False

class HsFinder:
    def __init__(self):
        self._pw=None; self._br=None; self._pg=None; self._via_cdp=False
    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw=sync_playwright().start()
        cdp=settings.IY_WEB_CDP_URL
        if settings.IY_WEB_CDP_ENABLED and _cdp_alive(cdp):
            self._br=self._pw.chromium.connect_over_cdp(cdp); self._via_cdp=True
            ctx=self._br.contexts[0]
            self._pg=ctx.pages[0] if ctx.pages else ctx.new_page(); return
        try: self._br=self._pw.chromium.launch(channel='chrome',headless=True)
        except Exception: self._br=self._pw.chromium.launch(headless=True)
        self._pg=self._br.new_context().new_page()
    def close(self):
        try:
            if self._br and not self._via_cdp: self._br.close()
            if self._pw: self._pw.stop()
        except Exception: pass
    def _page(self,url,wait=4500):
        self._pg.goto(url,timeout=60000,wait_until='domcontentloaded')
        self._pg.wait_for_timeout(wait)
        return self._pg.content()
    def fetch(self,hs_code=3406,chips=None):
        """返回 (companies_leads, supplier_seeds)。切片点击失败时降级为当前页。"""
        if not self._pg: self._launch()
        slug=HS_SLUG.get(int(hs_code),str(hs_code))
        url='https://www.importyeti.com/hs-codes/'+slug
        chips=chips if chips is not None else CHIPS
        companies=[];seen=set();suppliers=[]
        first=True
        for chip in chips:
            try:
                if first:
                    html=self._page(url); first=False
                else:
                    self._pg.click('text='+chip,timeout=8000)
                    self._pg.wait_for_timeout(3500)
                    html=self._pg.content()
            except Exception as e:
                print('[hs_finder] chip %s failed: %s'%(chip,str(e)[:80])); continue
            if not suppliers: suppliers=parse_bol_suppliers(html,hs_code)
            for c in parse_companies(html,chip):
                c['hs_code']=str(hs_code)
                k=c['slug'] or c['name'].lower()
                if k in seen: continue
                seen.add(k); companies.append(c)
        for c in companies: print('[hs_finder] importer: %s | %s | %s提单 | %s'%(c['name'],c['country'],c['shipments'],'/'.join(c['tags'])))
        print('[hs_finder] hs%s: %d importers, %d bol suppliers'%(hs_code,len(companies),len(suppliers)))
        return companies,suppliers

def run(hs_codes=None):
    """入口：按配置的 HS 编码列表采集，写 leads 表 + suppliers 池。"""
    from core.memory.db import DB
    from core.tools import suppliers as sup
    codes=hs_codes or [c.strip() for c in str(settings.HS_CODES).split(',') if c.strip()]
    f=HsFinder(); allc=[]; alls=[]
    try:
        for code in codes:
            try:
                c,s=f.fetch(code); allc+=c; alls+=s
            except Exception as e:
                print('[hs_finder] hs%s failed: %s'%(code,str(e)[:120]))
    finally: f.close()
    db=DB()
    if allc: db.upsert_leads(allc)
    if alls:
        db.upsert_leads(alls)
        sup.upsert_pool([{'norm':DB._norm(s['name']),'name':s['name'],'slug':s['slug'],'shipments':0,
                          'last_seen':time.time(),'via':'hs_bol'} for s in alls if s.get('slug')])
    return allc,alls

if __name__=='__main__':
    c,s=run()
    print('SELF-TEST: %d importers, %d suppliers'%(len(c),len(s)))
