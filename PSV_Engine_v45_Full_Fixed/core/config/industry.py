# -*- coding: utf-8 -*-
"""行业品类配置加载模块"""
import json
from pathlib import Path
from core.config import settings

CONFIG_DIR = Path(settings.PROJECT_ROOT) / "data" / "industry_configs"

def load_industry(key=None):
    key = key or getattr(settings, 'INDUSTRY', 'candle')
    path = CONFIG_DIR / f"{key}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "key": key,
        "name": key,
        "name_en": key,
        "search_terms": [key],
        "hs_codes": [],
        "keywords": [key],
        "pitch_facts": [f"We specialize in {key}."],
        "industry_context": key,
    }

def list_industries():
    out = []
    for fp in CONFIG_DIR.glob("*.json"):
        with open(fp, "r", encoding="utf-8") as f:
            out.append(json.load(f))
    return out

def save_industry(config):
    key=str(config.get('key') or '').strip().lower().replace(' ','_')
    if not key or not key.replace('_','').isalnum(): return False
    path=CONFIG_DIR/f'{key}.json'; CONFIG_DIR.mkdir(parents=True,exist_ok=True)
    def _lst(v):
        if isinstance(v,(list,tuple)): return [str(x).strip() for x in v if str(x).strip()]
        return [x.strip() for x in str(v or '').split(',') if x.strip()]
    base={'key':key,'name':str(config.get('name') or key).strip(),'name_en':str(config.get('name_en') or key).strip(),
          'search_terms':_lst(config.get('search_terms')),
          'hs_codes':_lst(config.get('hs_codes')),
          'keywords':_lst(config.get('keywords')),
          'exclusions':_lst(config.get('exclusions')),
          'materials':_lst(config.get('materials')),
          'applications':_lst(config.get('applications')),
          'pitch_facts':[x.strip() for x in str(config.get('pitch_facts') or '').split('|') if x.strip()],
          'industry_context':str(config.get('industry_context') or config.get('name') or key).strip()}
    path.write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8'); return True

def delete_industry(key):
    path=CONFIG_DIR/f'{str(key).strip()}.json'
    if not path.exists(): return False
    path.unlink(); return True
