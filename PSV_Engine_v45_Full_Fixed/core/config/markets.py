# -*- coding: utf-8 -*-
"""市场/地区配置管理"""
import json
from pathlib import Path
from core.config import settings

MARKETS_FILE = Path(settings.DATABASE_PATH).parent / "markets.json"

def load_markets():
    if MARKETS_FILE.exists():
        try:
            with open(MARKETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return [{"code": "USA", "name": "美国"}]

def save_market(market):
    markets = load_markets()
    code = market.get("code", "").strip().upper()
    name = market.get("name", "").strip()
    if not code or not name:
        return False
    # 更新或添加
    for m in markets:
        if m["code"] == code:
            m["name"] = name
            break
    else:
        markets.append({"code": code, "name": name})
    MARKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKETS_FILE.write_text(json.dumps(markets, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

def delete_market(code):
    markets = load_markets()
    new_markets = [m for m in markets if m.get("code") != code]
    MARKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKETS_FILE.write_text(json.dumps(new_markets, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
