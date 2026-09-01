import os, sqlite3, tempfile, time, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
fd,path=tempfile.mkstemp(suffix=".db"); os.close(fd)
os.environ["DATABASE_PATH"]=path
os.environ["BING_ENABLED"]="true"
os.environ["DDG_ENABLED"]="true"
os.environ["IMPORTYETI_ENABLED"]="false"
os.environ["IY_WEB_ENABLED"]="false"
os.environ["HS_FINDER_ENABLED"]="false"  # 离线回归：HS 榜单需网络+浏览器，此处关闭保证测试确定性
from core.config import settings
settings.DATABASE_PATH=path; settings.BING_ENABLED=True; settings.DDG_ENABLED=True; settings.IMPORTYETI_ENABLED=False; settings.IY_WEB_ENABLED=False; settings.HS_FINDER_ENABLED=False; settings.SOURCE_PER_LIMIT=5
from core.memory.db import DB
DB()
with sqlite3.connect(path) as c:
    now=time.time()
    c.execute("INSERT INTO buyers_90d VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("acme","Acme Candle LLC",now-100*86400,now-2*86400,12,0,0,0,3,"CN","LAX","birthday candles",90,"trade",now))
from core.tools.data_sources.manager import DataSourceManager, ALLOWED_HARD_SOURCES
rows,used,errors,gate=DataSourceManager().search("USA","candle",5)
# v30 策略：第一采集链只允许海关贸易数据源（hs_finder 已恢复为第一链入口），
# 通用搜索引擎（bing/duckduckgo）即使被打开也绝不允许进入第一链。
assert "hs_finder" in ALLOWED_HARD_SOURCES, ALLOWED_HARD_SOURCES
assert used == ["customs_bulk"], used
assert not ({"bing","bing_cn","duckduckgo"} & set(used)), used
assert rows and all(r["source"] in {"hs_finder","customs_bulk","customs_raw","importyeti","importyeti_web","importkey_public","customs_web"} for r in rows)
assert all((r.get("evidence") or {}).get("shipments") for r in rows)
print("SOURCE_POLICY_REGRESSION_OK")
