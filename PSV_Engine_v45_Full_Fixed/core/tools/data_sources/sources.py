import csv,re,sqlite3,time,json
from pathlib import Path
from core.config import settings
from core.tools.data_sources.base import Source,Quota,q
try:
    from curl_cffi import requests as creq
except Exception: creq=None
def card(name,country,industry,typ,source,strength,website='',evidence=None):
    return {'name':str(name or '').strip(),'country':country or '','industry':industry or '','type':typ or 'lead','website':website or '','source':source,'strength':strength,'evidence':evidence or {}}
class BulkCustomsSource(Source):
    name='customs_bulk'; label='90天提单库'; strength=5; config_hint='用 customs_clean.py 导入CSV后自动启用'
    def available(self):
        try:
            conn=sqlite3.connect(settings.DATABASE_PATH); n=conn.execute('SELECT COUNT(*) FROM buyers_90d').fetchone()[0]; conn.close(); return n>0
        except Exception: return False
    def search(self,market,industry,limit,offset=0):
        conn=sqlite3.connect(settings.DATABASE_PATH); conn.row_factory=sqlite3.Row
        rows=conn.execute('SELECT * FROM buyers_90d ORDER BY score DESC,last_seen DESC LIMIT ? OFFSET ?',(max(limit,settings.SOURCE_PER_LIMIT),int(offset or 0))).fetchall(); conn.close()
        return [card(r['importer'],'USA',industry,'importer',self.name,self.strength,'',{'shipments':r['shipments'],'score':r['score'],'last_seen':r['last_seen'],'reasons':r['reasons']}) for r in rows]
class CsvSource(Source):
    name='csv_import'; label='CSV手工导入'; strength=4; config_hint='放CSV到 data/imports'
    def available(self): return any(Path(settings.IMPORT_DIR).glob('*.csv'))
    def search(self,market,industry,limit):
        out=[]
        for fp in Path(settings.IMPORT_DIR).glob('*.csv'):
            with fp.open(encoding='utf-8-sig',errors='ignore') as f:
                for row in csv.DictReader(f):
                    name=(row.get('name') or row.get('company') or '').strip()
                    if name: out.append(card(name,row.get('country') or market,row.get('industry') or industry,row.get('type') or 'lead',self.name,self.strength,row.get('website') or '',{'email':row.get('email') or ''}))
                    if len(out)>=limit: return out
        return out
class ImportYetiSource(Source):
    name='importyeti'; label='ImportYeti海关摘要'; strength=4; config_hint='公开摘要，配额保护'
    def __init__(self): self.quota=Quota()
    def available(self): return settings.IMPORTYETI_ENABLED
    def _get(self,url):
        if creq:
            kw={'impersonate':'chrome','timeout':settings.DATA_SOURCE_TIMEOUT}
            if settings.SCRAPE_PROXY_URL: kw['proxies']={'http':settings.SCRAPE_PROXY_URL,'https':settings.SCRAPE_PROXY_URL}
            r=creq.get(url,**kw)
            if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code}')
            self.quota.hit(self.name); return r.json()
        data=self._json(url); self.quota.hit(self.name); return data
    def search(self,market,industry,limit,query=None,page_start=1):
        if str(market).lower() not in ('usa','us','united states','美国','america',''): return []
        if self.quota.remaining(self.name,settings.IMPORTYETI_DAILY_QUOTA)<=settings.IMPORTYETI_QUOTA_RESERVE: raise RuntimeError('ImportYeti配额触及保留线')
        items=[]; query=query or industry
        for page in range(max(1,int(page_start or 1)),max(1,int(page_start or 1))+max(1,settings.IMPORTYETI_MAX_PAGES)):
            data=self._get(f"{settings.IMPORTYETI_SEARCH_URL}?q={q(query)}&page={page}")
            rows=data.get('searchResults') or data.get('results') or data.get('data') or []
            if not rows: break
            items.extend(rows)
            if len(items)>=max(limit,settings.SOURCE_PER_LIMIT): break
        return [card(r.get('title') or r.get('name') or r.get('companyName'),'USA',industry,'importer',self.name,self.strength,r.get('website') or '',{'shipments':r.get('totalShipments'),'address':r.get('address') or ''}) for r in items if (r.get('title') or r.get('name') or r.get('companyName'))][:limit]
class ImportYetiWebSource(Source):
    name='importyeti_web'; label='ImportYeti网页'; strength=4; config_hint='Playwright真人节奏，直连'
    def available(self):
        if not getattr(settings,'IY_WEB_ENABLED',False): return False
        from core.tools import iy_web
        return iy_web.available()
    def search(self,market,industry,limit):
        if str(market).lower() not in ('usa','us','united states','美国','america',''): return []
        from core.tools import iy_web
        with iy_web.IYWeb() as w:
            if not w.ok: raise RuntimeError('Playwright/Chromium 未就绪（pip install playwright && playwright install chromium）')
            rows=w.search(industry,max(1,min(int(limit or 10),settings.IY_WEB_SEARCH_LIMIT)))
            err=w.last_error
        if not rows and err=='cloudflare':
            raise RuntimeError('被人机验证(Cloudflare)拦截：headless与可视窗口均未通过。请手工打开 importyeti.com 过一次验证再跑；快照见 data/iy_debug_*.html')
        if not rows and err=='parse_empty':
            raise RuntimeError('页面0条解析结果（结构可能变化），调试快照已存 data/iy_debug_*.html')
        # 同行工厂种子：搜索结果里的 supplier 卡片直接入池（slug 精确，收割时免二次搜索）
        try:
            from core.tools import suppliers as _sup
            seeds=[]
            for r in rows:
                if r.get('kind')!='supplier': continue
                n=_sup.norm(r['name'])
                if not n: continue
                seeds.append({'norm':n,'name':r['name'],'slug':r['url'].rstrip('/').split('/')[-1],
                              'shipments':r.get('shipments') or 0,'last_seen':time.time()})
            if seeds:
                _sup.upsert_pool(seeds)
                print('[importyeti_web] %d supplier seeds -> pool'%len(seeds))
        except Exception as e:
            print('[importyeti_web] seed pool skipped:',str(e)[:80])
        out=[]
        for r in rows:
            if r.get('kind')!='company': continue
            slug=r['url'].rstrip('/').split('/')[-1]
            out.append(card(r['name'],'USA',industry,'importer',self.name,self.strength,'',
                {'shipments':r.get('shipments'),'last_seen':r.get('last_seen'),
                 'address':r.get('address') or '','slug':slug,'url':r['url']}))
        return out

class ImportKeyPublicSource(Source):
    """ImportKey public customs pages. Opt-in only; reads publicly exposed company pages, never login/captcha.
    It is a relationship-enrichment source rather than a broad keyword discovery engine.
    """
    name='importkey_public'; label='ImportKey公开海关页'; strength=4; config_hint='公开公司页，增量补充 importer↔supplier/customer 关系'
    def available(self): return bool(getattr(settings,'IMPORTKEY_ENABLED',False))
    def _slug(self,name):
        return re.sub(r'-+','-',re.sub(r'[^a-z0-9]+','-',str(name or '').lower())).strip('-')
    def _fetch(self,url):
        headers={'User-Agent':'PSV-CustomsCollector/27.2 (+public-page-only)'}
        if creq:
            r=creq.get(url,timeout=settings.DATA_SOURCE_TIMEOUT,headers=headers)
            if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code}')
            return r.text
        return self._text(url)
    def company_relationships(self,name,kind='suppliers',limit=10):
        if not self.available() or not name: return []
        url='https://importkey.com/i/'+self._slug(name)
        html=self._fetch(url)
        # ImportKey renders relationship lists server-side on public company pages.
        text=re.sub(r'<script.*?</script>|<style.*?</style>',' ',html,flags=re.S|re.I)
        text=re.sub(r'<[^>]+>',' ',text)
        text=re.sub(r'\s+',' ',text)
        section='Suppliers available for' if kind=='suppliers' else 'Buyers available for'
        pos=text.lower().find(section.lower())
        if pos<0: return []
        tail=text[pos:pos+50000]
        stop=re.search(r'(Learn More|Discover trading relationships)',tail,re.I)
        if stop: tail=tail[:stop.start()]
        # Conservative extraction: company-like uppercase lines followed by shipment counts.
        out=[]
        for m in re.finditer(r'(?:Total Shipments|Address)\s+(\d+)\s+([A-Z0-9][A-Z0-9 .,&\-\/]{2,100}?)(?=\s+Learn More|\s+\d+\s+[A-Z]|$)',tail):
            try: ships=int(m.group(1)); nm=m.group(2).strip(' ,')
            except Exception: continue
            if len(nm)<3 or len(nm)>100: continue
            out.append({'name':nm,'shipments':ships,'url':url,'source':'importkey_public'})
            if len(out)>=limit: break
        return out

class BingCnSource(Source):
    name='bing_cn'; label='必应中国补充'; strength=1; config_hint='弱来源，只做补充'
    def available(self): return settings.BING_CN_ENABLED
    def search(self,market,industry,limit):
        bad=re.compile(r'翻译|词典|百科|英语单词|是什么意思|amazon|ikea|walmart|alibaba|made-in-china|globalsource|buy .*candle|scented candles|packaging|\.com|_|\||…|&amp;',re.I)
        html=self._text('https://cn.bing.com/search?q='+q(str(industry)+' USA importer company -amazon -ikea -翻译 -词典'))
        out=[]
        for m in re.finditer(r'<h2.*?>(.*?)</h2>',html,re.S|re.I):
            t=re.sub(r'<.*?>','',m.group(1)).strip(); t=re.sub(r'\s+',' ',t)
            if bad.search(t): continue
            if not re.search(r'candle|importer|import|distributor|wholesale|trading|inc|llc|ltd',t,re.I): continue
            if 3<=len(t)<=90: out.append(card(t,market,industry,'lead',self.name,self.strength))
            if len(out)>=limit: break
        return out

class HsFinderSource(Source):
    """v30 第一采集链入口：关键词→HS编码→Product Finder 海关榜单（提单硬证据种子）。
    榜单进口商成为 importer 节点；页底提单表的 shipper 种子同时写入同行工厂池（via=hs_bol）。"""
    name='hs_finder'; label='HS编码榜'; strength=5; config_hint='Product Finder by HS Code，提单硬证据'
    def __init__(self,hs_codes=None):
        self._done=False
        self.hs_codes=[str(x).strip() for x in (hs_codes or []) if str(x).strip()] or None
    def available(self): return settings.HS_FINDER_ENABLED and not self._done
    def search(self,market,industry,limit):
        self._done=True
        from core.tools import hs_finder
        companies,sups=hs_finder.run(hs_codes=self.hs_codes)
        out=[]
        for c in companies:
            cd=card(c['name'],market,industry,'buyer',self.name,self.strength)
            cd['country']=c.get('country') or ''
            cd['node_role']='importer'
            cd['evidence']={'shipments':c.get('shipments'),'last_shipment':c.get('last_shipment',''),
                            'hs':c.get('hs_code',''),'products':c.get('desc_sample',''),
                            'customs':True,'trade_evidence':True,'node_role':'importer',
                            'reasons':'HS%s榜[%s]'%(c.get('hs_code',''),'/'.join(c.get('tags') or []))}
            out.append(cd)
        return out
