import urllib.parse,urllib.request,json,sqlite3,time,socket
from core.config import settings
def q(s): return urllib.parse.quote_plus(str(s or ''))
def key(market,industry): return str(market or '').lower()+'|'+str(industry or '').lower()
_PX={}
def proxy_alive():
    """代理健康检查：SCRAPE_PROXY_URL 配了但端口没人听（Clash没开）时回退直连，5分钟缓存。"""
    px=getattr(settings,'SCRAPE_PROXY_URL','') or ''
    if not px: return False
    hit=_PX.get(px)
    if hit and time.time()-hit[1]<300: return hit[0]
    ok=False
    try:
        u=urllib.parse.urlparse(px)
        s=socket.create_connection((u.hostname,u.port or 80),timeout=2); s.close(); ok=True
    except Exception: ok=False
    _PX[px]=(ok,time.time())
    if not ok: print(f'[proxy] {px} 不可达，本次回退直连（Clash 未启动？）')
    return ok
class Quota:
    def __init__(self,db=None): self.db=db or settings.DATABASE_PATH
    def _c(self): return sqlite3.connect(self.db,timeout=10)
    def hit(self,source,n=1):
        day=time.strftime('%Y-%m-%d')
        with self._c() as c: c.execute('INSERT INTO source_quota VALUES(?,?,?) ON CONFLICT(source,day) DO UPDATE SET count=count+?',(source,day,n,n))
    def used(self,source):
        day=time.strftime('%Y-%m-%d')
        with self._c() as c: r=c.execute('SELECT count FROM source_quota WHERE source=? AND day=?',(source,day)).fetchone()
        return r[0] if r else 0
    def remaining(self,source,quota): return max(0,quota-self.used(source))
class Source:
    name='base'; label='源'; strength=1; config_hint=''
    def available(self): return True
    def search(self,market,industry,limit): raise NotImplementedError
    def _opener(self):
        px=(getattr(settings,'SCRAPE_PROXY_URL','') or '') if proxy_alive() else ''
        return urllib.request.build_opener(urllib.request.ProxyHandler({'http':px,'https':px} if px else {}))
    def _text(self,url):
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 PSV/12'})
        with self._opener().open(req,timeout=settings.DATA_SOURCE_TIMEOUT) as r: return r.read().decode(errors='ignore')
    def _json(self,url):
        with self._opener().open(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 PSV/12'}),timeout=settings.DATA_SOURCE_TIMEOUT) as r: return json.loads(r.read().decode())
