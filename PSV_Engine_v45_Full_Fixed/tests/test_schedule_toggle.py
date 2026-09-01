import os, time, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import tempfile as _tf; os.environ["DATABASE_PATH"]=_tf.mktemp(suffix=".db")  # v35: 测试库不进数据根

from core.memory.db import DB
db=DB()
db.upsert_schedule("toggle-test","discovery","USA","candle",5,60,False,{})
s=db.list_schedules()[0]
assert s["enabled"]==0
assert db.set_schedule_enabled(s["id"],True)
s=db.list_schedules()[0]
assert s["enabled"]==1 and s["last_status"]=="enabled"
assert db.set_schedule_enabled(s["id"],False)
s=db.list_schedules()[0]
assert s["enabled"]==0 and s["last_status"]=="disabled"
print("SCHEDULE_TOGGLE_OK")
