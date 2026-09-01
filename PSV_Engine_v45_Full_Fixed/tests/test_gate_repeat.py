import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ["EXPERT_MODE"]="false"
from core.config import settings
settings.EXPERT_MODE=False; settings.GATE_MIN_QUALIFIED=2
from core.runtime.nodes import n_gate
out=n_gate({"companies":[{"name":"Known A","source":"customs_bulk","evidence":{"shipments":12,"customs":True}}, {"name":"Known B","source":"importyeti_web","evidence":{"shipments":5,"products":"birthday candles"}}],"new_companies":[],"industry":"candle"})
assert out["gate"]["raw"]==2
assert out["gate"]["qualified"]==2
assert out["_success"] is True
print("GATE_REPEAT_REGRESSION_OK")
