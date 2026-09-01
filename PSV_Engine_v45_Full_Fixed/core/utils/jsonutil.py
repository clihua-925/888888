import json,re
def j(text):
    if not text: return None
    m=re.search(r'\{.*\}',str(text),re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None
def jl(text):
    if not text: return []
    m=re.search(r'\[.*\]',str(text),re.S)
    if not m: return []
    try:
        x=json.loads(m.group(0)); return x if isinstance(x,list) else []
    except Exception: return []
