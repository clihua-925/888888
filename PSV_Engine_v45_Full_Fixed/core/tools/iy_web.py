# -*- coding: utf-8 -*-
"""ImportYeti 网页收割器（Playwright 真人节奏模拟）。
数据源是手工验证过的免费网页：/search → /company/{slug} → /supplier/{slug}。
v14.2 强化：
- Cloudflare 挑战轮询等待（默认最长30秒，IY_WEB_CHALLENGE_WAIT 可调）
- headless 被拦截时自动切换【可视窗口】重试一次（IY_WEB_AUTO_HEADED=true）
- 全程 last_error 诊断：cloudflare / parse_empty / no_playwright / launch:*
- 命令行自检：python -m core.tools.iy_web "birthday candles"
- 解析失败自动把页面 HTML 存到 data/iy_debug_*.html 供迭代选择器"""
import json,random,re,time
from pathlib import Path
from core.config import settings
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
CHALLENGE=re.compile(r'just a moment|attention required|cf-chl|challenge-platform|verify you are human|cf-turnstile|performing security verification',re.I)
# ---------- 文本解析（基于真实页面结构，纯函数可单测）----------
def _num(s):
    m=re.match(r'^([\d,]+)$',s.strip()); return int(m.group(1).replace(',','')) if m else None
def _shipments_from(text):
    """从任意卡片文本里提取出货量：兼容 'Total Shipments\\n12,345'、'12,345 Shipments'、'Total Shipments: 12' 等写法。"""
    t=text or ''
    for pat in (r'([\d,]{1,12})\s*(?:Total\s+)?Shipments?\b',
                r'(?:Total\s+)?Shipments?\s*[:\-–]?\s*([\d,]{1,12})'):
        m=re.search(pat,t,re.I)
        if m:
            try: return int(m.group(1).replace(',',''))
            except Exception: pass
    lines=[l.strip() for l in t.splitlines() if l.strip()]
    for i,l in enumerate(lines):
        if re.match(r'^(Total\s+)?Shipments?$',l,re.I):
            for j in (i+1,i-1):
                if 0<=j<len(lines):
                    n=_num(lines[j])
                    if n is not None: return n
    return 0
def parse_search_card(text):
    """搜索结果卡片文本 → {kind,address,shipments,last_seen}。宽松解析：字段缺失不丢弃节点。"""
    lines=[l.strip() for l in (text or '').splitlines() if l.strip()]
    kind=''; address=''; shipments=0; last_seen=''
    for i,l in enumerate(lines):
        if l.lower() in ('company','supplier') and not kind: kind=l.lower()
        if l=='Total Shipments' and i+1<len(lines):
            shipments=_num(lines[i+1]) or 0
            if i>0: address=lines[i-1]
        if l=='Most recent shipment' and i+1<len(lines): last_seen=lines[i+1]
    if not shipments: shipments=_shipments_from(text)
    if not last_seen:
        m=re.search(r'Most recent shipment\s*[:\n]\s*([^\n]{4,30})',text or '',re.I)
        if m: last_seen=m.group(1).strip()
    return {'kind':kind,'address':address,'shipments':shipments,'last_seen':last_seen}
def parse_rel_card(text):
    """关系卡片文本（单个供应商/客户）→ {shipments,products,hs,location}。宽松解析。"""
    t=text or ''
    lines=[l.strip() for l in t.splitlines() if l.strip()]
    shipments=_shipments_from(t)
    if not shipments:
        for l in lines:
            n=_num(l)
            if n is not None: shipments=n; break
    hm=re.search(r'HS Codes?:\s*\(?\s*([\d.,\s)]+)',t,re.I)
    hs=[x for x in re.split(r'[,\s]+',hm.group(1).strip(' )')) if re.match(r'^\d',x)] if hm else []
    # 产品描述：去掉 HS/出货量/“See all bills”行后剩下的短文本
    prods=[]
    for l in lines:
        if _num(l) is not None: continue
        if re.match(r'^(Total\s+)?Shipments?$',l,re.I): continue
        if l.startswith(('See all bills','HS Codes','CSV')) or l in ('company','supplier'): continue
        prods.append(l)
    location=prods[0] if prods else ''
    products=' '.join(prods[1:6])[:200] if len(prods)>1 else ''
    return {'shipments':shipments,'products':products,'hs':hs[:6],'location':location}
def parse_rel_text(text,section):
    """公司/供应商主页的关系区文本（Suppliers|Customers）→ [{name,location,shipments,products,hs}]"""
    m=re.search(r"'s\s*"+section,text or '')
    if not m: return []
    lines=[l.strip() for l in text[m.start():].splitlines() if l.strip()]
    try: start=lines.index('Product Descriptions')+1
    except ValueError: start=0
    rows=[]; i=start
    STOP=re.compile(r'^(Cost Structure|Top 10|Recent Sea Shipments|Addresses and Contact|Imports Per Country)')
    while i<len(lines) and len(rows)<25:
        l=lines[i]
        if STOP.search(l): break
        if l in ('CSV','See all bills of lading with this supplier','See all bills of lading with this company') or l.startswith('HS Codes'):
            i+=1; continue
        # 一行关系记录：名称开头 → 地点行 → 纯数字(出货量) → 产品/HS → 直到 "See all bills..."
        name=l; j=i+1; loc=[]; shipments=0; products=[]; hs=[]
        while j<len(lines):
            s=lines[j]
            if s in (',',): j+=1; continue
            n=_num(s)
            if n is not None and not shipments: shipments=n; j+=1; break
            if s.startswith('HS Codes') or STOP.search(s): break
            loc.append(s); j+=1
        while j<len(lines):
            s=lines[j]
            if s.startswith('See all bills of lading'): j+=1; break
            if STOP.search(s): break
            if s=='(': j+=1; continue
            products.append(s); j+=1
        # 提取 HS 编码
        prod_txt=' '.join(products)
        hm=re.search(r'HS Codes?:\s*\(?\s*([\d.,\s)]+)',prod_txt)
        if hm: hs=[x for x in re.split(r'[,\s]+',hm.group(1).strip(' )')) if re.match(r'^\d',x)]
        if name and shipments:
            rows.append({'name':name,'location':' '.join(loc),'shipments':shipments,
                         'products':re.sub(r'HS Codes?:.*','',prod_txt).strip(' (')[:200],'hs':hs[:6]})
        i=max(j,i+1)
    return rows
# ---------- 浏览器层 ----------
_PW=None
def _pw():
    global _PW
    if _PW is None:
        try:
            from playwright.sync_api import sync_playwright
            _PW=sync_playwright
        except Exception:
            _PW=False
    return _PW
def _cdp_alive(url):
    """桌面浏览器调试端口是否已开（start_chrome_debug.bat 启动的 Chrome/Edge）"""
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip('/')+'/json/version',timeout=2) as r:
            return r.status==200
    except Exception: return False
class IYWeb:
    """一个实例 = 一个浏览器会话。用法：with IYWeb() as w: w.search(...) / w.relationships(...)
    优先级：CDP 接管桌面浏览器（真实profile，Cloudflare视为真人）→ 自启动 headless/可视窗口"""
    def __init__(self,headless=None):
        self.headless=settings.IY_WEB_HEADLESS if headless is None else bool(headless)
        self.ok=False; self.last_error=''; self.escalated=False; self._via_cdp=False
        self.last_total=0  # 最近一次 relationships() 页面声明的关系总数（0=未显示）
        self._p=None; self._b=None; self._pg=None
        if not _pw(): self.last_error='no_playwright'; return
        self._launch(self.headless)
    def _launch(self,headless):
        self._close_browser()
        try:
            if self._p is None: self._p=_pw()().start()
            # 1) 优先接管桌面浏览器（CDP）：真实 Chrome/Edge + 持久 profile，验证一次后长期免验证
            cdp_url=getattr(settings,'IY_WEB_CDP_URL','http://127.0.0.1:9222')
            if getattr(settings,'IY_WEB_CDP_ENABLED',True) and _cdp_alive(cdp_url):
                self._b=self._p.chromium.connect_over_cdp(cdp_url)
                ctx=self._b.contexts[0] if self._b.contexts else self._b.new_context()
                self._pg=ctx.pages[0] if ctx.pages else ctx.new_page()
                self.ok=True; self._via_cdp=True
                print('[iy_web] attached to DESKTOP browser via CDP (%s)'%cdp_url)
                return
            # 2) 自启动浏览器（优先系统 Chrome，其次内置 Chromium）
            args=['--disable-blink-features=AutomationControlled','--no-first-run']
            try:
                self._b=self._p.chromium.launch(headless=headless,channel='chrome',args=args)
            except Exception:
                self._b=self._p.chromium.launch(headless=headless,args=args)
            ctx=self._b.new_context(user_agent=UA,viewport={'width':1366,'height':900},locale='en-US',timezone_id='America/New_York')
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            self._pg=ctx.new_page(); self.ok=True
            print('[iy_web] browser ready (%s; tip: run start_chrome_debug.bat to use your desktop browser)'%('headless' if headless else 'VISIBLE window'))
        except Exception as e:
            self.last_error='launch:'+str(e)[:120]; self.ok=False
    def _close_browser(self):
        try:
            if self._b: self._b.close()  # CDP 模式下只是断开连接，不会关掉用户的桌面浏览器
        except Exception: pass
        self._b=None; self._pg=None
    def close(self):
        self._close_browser()
        try:
            if self._p: self._p.stop()
        except Exception: pass
        self._p=None; self.ok=False
    def __enter__(self): return self
    def __exit__(self,*a): self.close()
    def _pace(self):
        time.sleep(random.uniform(settings.IY_WEB_DELAY_MIN,settings.IY_WEB_DELAY_MAX))
    def _is_challenge(self):
        try:
            if CHALLENGE.search(self._pg.title() or ''): return True
            return bool(CHALLENGE.search((self._pg.content() or '')[:6000]))
        except Exception: return False
    def _goto(self,url):
        self._pace()
        self._pg.goto(url,timeout=45000,wait_until='domcontentloaded')
        self._pg.wait_for_timeout(2500)
        if self._is_challenge():
            wait_s=float(getattr(settings,'IY_WEB_CHALLENGE_WAIT','30'))
            print('[iy_web] Cloudflare challenge, waiting up to %.0fs ...'%wait_s)
            if self._via_cdp: print('[iy_web] >> click the checkbox in your desktop browser window, the script is waiting <<')
            t0=time.time()
            while time.time()-t0<wait_s:
                self._pg.wait_for_timeout(2000)
                if not self._is_challenge(): break
        return self._pg
    def _run(self,tag,fn):
        """执行一次采集；headless 被 Cloudflare 拦住时自动升级可视窗口重试一次（CDP 模式已是真实桌面浏览器，无需升级）"""
        rows=fn()
        if not rows and self.last_error=='cloudflare' and not self._via_cdp and self.headless and getattr(settings,'IY_WEB_AUTO_HEADED',True):
            print('[iy_web] headless blocked by Cloudflare; retrying with a VISIBLE browser window')
            print('[iy_web] (if a checkbox/captcha appears, just click it - the script waits)')
            self._launch(False); self.escalated=True
            if self.ok: rows=fn()
        if not rows and self.last_error: self._debug_dump(tag)  # 真实空结果不落调试快照
        return rows
    def _debug_dump(self,tag):
        try:
            fp=Path(settings.DATABASE_PATH).parent/f'iy_debug_{tag}_{int(time.time())}.html'
            fp.write_text(self._pg.content(),encoding='utf-8')
            print('[iy_web] debug snapshot saved:',fp.name)
            return fp.name
        except Exception: return ''
    def _search_once(self,query,limit):
        """ImportYeti 搜索页 → 贸易节点卡片。v30 宽松定位：先等结果锚点出现，
        以 /company/ /supplier/ 链接为节点锚（该站所有卡片都是海关记录，天然有效），
        出货量等证据尽量解析，缺字段不丢节点。"""
        self.last_error=''
        import urllib.parse
        print('[iy_web] search:',query)
        pg=self._goto('https://www.importyeti.com/search?q='+urllib.parse.quote_plus(query))
        if self._is_challenge(): self.last_error='cloudflare'; return []
        try: pg.wait_for_selector('a[href*="/company/"],a[href*="/supplier/"]',timeout=15000)
        except Exception: pass
        cards=pg.eval_on_selector_all('a[href*="/company/"],a[href*="/supplier/"]',"""els=>{
            const out=[],seen=new Set();
            for(const a of els){
                const href=(a.href||'').split('#')[0];
                let name=(a.innerText||'').trim().split('\\n')[0].trim();
                if(!name||name.length<2||seen.has(href)) continue;
                seen.add(href);
                let box=a,txt='';
                for(let i=0;i<10&&box;i++){box=box.parentElement;
                    if(box&&/shipments/i.test(box.innerText||'')){txt=box.innerText;break;}}
                if(!txt){let b2=a;for(let i=0;i<6&&b2;i++){b2=b2.parentElement;
                    if(b2&&(b2.innerText||'').length>name.length){txt=b2.innerText;}}}
                out.push({name,href,text:txt||''});
            }
            return out;
        }""")
        # 兜底：动态锚点失败时，从原始 HTML 直接提取公司/供应商链接
        if not cards:
            html=pg.content() or ''
            seen=set()
            for m in re.finditer(r'href="((?:https?://www\.importyeti\.com)?/(?:company|supplier)/[a-z0-9\-]+)"[^>]*>([^<]{2,120})<',html):
                href,name=m.group(1),m.group(2).strip()
                if href in seen or not name: continue
                seen.add(href)
                if not href.startswith('http'): href='https://www.importyeti.com'+href
                cards.append({'name':name,'href':href,'text':''})
        out=[]
        for c in cards[:limit]:
            info=parse_search_card(c.get('text') or '')
            if not info.get('kind'):  # 卡片文本里没有 company/supplier 行时，从 URL 补判
                info['kind']='company' if '/company/' in c['href'] else ('supplier' if '/supplier/' in c['href'] else '')
            out.append({'name':c['name'],'url':c['href'],**info})
        if not out:
            body_txt=''
            try: body_txt=pg.eval_on_selector('body','e=>e.innerText') or ''
            except Exception: pass
            if re.search(r'No results|0 results|did not match',body_txt,re.I):
                self.last_error=''  # 真实无结果，不是解析失败
                print('[iy_web] search: genuine 0 results for query')
            else:
                self.last_error='parse_empty'
        else: print('[iy_web] %d cards parsed'%len(out))
        return out
    def search(self,query,limit=10):
        """搜索页 → [{name,url,kind,address,shipments,last_seen}]（公司/供应商卡片）"""
        return self._run('search',lambda:self._search_once(query,limit))
    def _rel_once(self,url,section):
        """公司/供应商主页 → 关系区。v30 改为 DOM 区域解析：
        定位 "'s Suppliers" / "'s Customers" 标题所在区域，抓区域内目标链接作为关系节点，
        卡片文本宽松解析出货量/产品/HS；文本行解析作为兜底。"""
        self.last_error=''
        pg=self._goto(url)
        if self._is_challenge(): self.last_error='cloudflare'; return []
        want='/supplier/' if section=='Suppliers' else '/company/'
        data=pg.evaluate("""(args)=>{
            const sec=args.section, want=args.want, body=document.body;
            const re=new RegExp("'s\\\\s*"+sec+"\\\\b");
            const walker=document.createTreeWalker(body,NodeFilter.SHOW_ELEMENT);
            let node;const cands=[];
            while(node=walker.nextNode()){
                const t=(node.textContent||'');
                if(re.test(t)&&t.length<300) cands.push(node);
            }
            const header=cands[cands.length-1]||null;
            if(!header) return {rows:[],found:false,empty:false,total:0};
            let region=header;
            for(let i=0;i<12&&region&&region!==body;i++){
                if(region.querySelector&&region.querySelector('a[href*="'+want+'"]')) break;
                region=region.parentElement;
            }
            const regionText=(region&&region.innerText)||'';
            // v30.4 单点彻底性：尽力读出该关系区的总数（如 "Suppliers (42)" / "42 suppliers" / "of 42"），
            // 用于回答“这个节点的全部提票关系是否都拿到了”。
            let total=0;let m=regionText.match(/\(([\d,]{1,7})\)/)||regionText.match(/([\d,]{1,7})\s+(?:suppliers|customers|companies|results|buyers)/i)||regionText.match(/of\s+([\d,]{1,7})/i);
            if(m) total=parseInt(m[1].replace(/,/g,''),10)||0;
            const hasLinks=region&&region.querySelector&&region.querySelector('a[href*="'+want+'"]');
            if(!hasLinks) return {rows:[],found:true,empty:/No results/i.test(regionText),total:total};
            const out=[],seen=new Set();
            region.querySelectorAll('a[href*="'+want+'"]').forEach(a=>{
                const href=(a.href||'').split('#')[0];
                const name=(a.innerText||'').trim().split('\\n')[0].trim();
                if(!name||name.length<2||seen.has(href))return; seen.add(href);
                let box=a,txt='';
                for(let i=0;i<8&&box;i++){box=box.parentElement;
                    if(box&&/(shipments|bills of lading|HS Codes)/i.test(box.innerText||'')){txt=box.innerText;break;}}
                out.push({name,href,text:txt||''});
            });
            return {rows:out,found:true,empty:false};
        }""",{'section':section,'want':want})
        rows=[]
        max_rows=int(getattr(settings,'IY_REL_MAX_ROWS',100))
        if data.get('rows'):
            for r in data['rows'][:max_rows]:
                info=parse_rel_card(r.get('text') or '')
                rows.append({'name':r['name'],'url':r['href'],
                             'location':info['location'],'shipments':info['shipments'],
                             'products':info['products'],'hs':info['hs']})
        self.last_total=int(data.get('total') or 0)  # 该关系区页面声明的总数（0=页面未显示）
        if not rows and not data.get('found'):
            # 兜底：旧的整页文本行解析
            txt=pg.eval_on_selector('body','e=>e.innerText')
            rows=parse_rel_text(txt,section)
        if not rows:
            if data.get('empty'):
                self.last_error=''  # 该节点确实没有此类关系，不是解析失败
                print('[iy_web] %s: genuine empty section'%section)
            else:
                self.last_error='parse_empty'
        else: print('[iy_web] %s: %d rows'%(section,len(rows)))
        return rows
    def relationships(self,url,section):
        """公司/供应商主页 → 关系区（'Suppliers'|'Customers'）行列表"""
        return self._run('rel_'+section.lower(),lambda:self._rel_once(url,section))
    def supplier_page_for(self,name):
        """按供应商名搜索，取第一个 supplier 卡片的主页 URL"""
        for c in self.search(name,limit=5):
            if c.get('kind')=='supplier' or '/supplier/' in c.get('url',''):
                return c['url']
        return None
    def company_page_for(self,name):
        """按公司名搜索，取第一个 company 卡片的主页 URL（v10：搜索解析主页，绝不猜 slug）"""
        for c in self.search(name,limit=5):
            if c.get('kind')=='company' or '/company/' in c.get('url',''):
                return c['url']
        return None
def available():
    return bool(_pw())
def main():
    """命令行自检：python -m core.tools.iy_web "birthday candles" """
    import sys
    query=' '.join(sys.argv[1:]).strip() or 'birthday candles'
    with IYWeb() as w:
        if not w.ok:
            print('FAIL: browser not ready:',w.last_error); return 2
        rows=w.search(query,10)
        mode='desktop_cdp' if w._via_cdp else ('headless' if w.headless else 'visible')
        print(json.dumps({'query':query,'mode':mode,'count':len(rows),'last_error':w.last_error,
                          'escalated_to_visible':w.escalated,'sample':rows[:3]},ensure_ascii=False,indent=2))
        if rows:
            print('SELF-TEST OK: importyeti_web usable'); return 0
        print('SELF-TEST EMPTY: check data/iy_debug_*.html (send it back for selector fix)')
        return 1
if __name__=='__main__': raise SystemExit(main())
