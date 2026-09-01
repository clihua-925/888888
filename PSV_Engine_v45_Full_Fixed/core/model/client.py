import json,time,urllib.request
from core.config import settings
class ModelClient:
    _h={}
    def __init__(self): self.base=settings.LLM_BASE_URL.rstrip('/'); self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def health(self):
        now=time.time(); c=self._h.get(self.base)
        if c and c[0] and now-c[1]<10: return True
        ok=False
        try:
            req=urllib.request.Request(self.base+'/models',headers={'Authorization':'Bearer '+settings.LLM_API_KEY})
            with self.opener.open(req,timeout=5) as r: ok=r.status==200
        except Exception: ok=False
        self._h[self.base]=(ok,now); return ok
    def chat(self,prompt,system=None,temperature=0.3,max_tokens=None,timeout=None):
        body={'model':settings.LLM_MODEL,'messages':([] if not system else [{'role':'system','content':system}])+[{'role':'user','content':prompt}],'temperature':temperature,'max_tokens':int(max_tokens or settings.LLM_MAX_TOKENS),'stream':False}
        req=urllib.request.Request(self.base+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+settings.LLM_API_KEY})
        try:
            with self.opener.open(req,timeout=int(timeout or settings.LLM_TIMEOUT)) as r: return json.loads(r.read().decode())['choices'][0]['message']['content']
        except Exception:
            self._h.pop(self.base,None); return None
