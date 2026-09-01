# -*- coding: utf-8 -*-
"""v30.4.1 INIT 防冻结回归：总统筹 LLM“连得上但不返回”时，
mission_plan 必须在 MISSION_DIRECTOR_TIMEOUT 内放弃并按固定拓扑继续，
任务绝不冻结在 INIT；正常 LLM 路径不受影响。"""
import os, sys, time, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fd, DBPATH = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ.update(DATABASE_PATH=DBPATH, EXPERT_MODE='true', MISSION_DIRECTOR_ENABLED='true',
                  SCHEDULER_ENABLED='false', MISSION_DIRECTOR_TIMEOUT='5')
from core.config import settings
settings.DATABASE_PATH = DBPATH
settings.SCHEDULER_ENABLED = False
settings.MISSION_DIRECTOR_TIMEOUT = 5
from core.runtime import experts


class HangEngine:
    @property
    def available(self): return True
    def review(self, *a, **k):
        time.sleep(60)
        return {'action': 'continue'}


class OkEngine:
    @property
    def available(self): return True
    def review(self, *a, **k):
        return {'action': 'retry', 'reason': 'r', 'next_node': '', 'plan': ['a'], 'questions': []}


def test_init_antifreeze():
    experts._ENG = HangEngine()
    t0 = time.time()
    d = experts.mission_plan({'task_id': 't', 'request': 'x'}, event='task_start')
    el = time.time() - t0
    assert el < 15, f'INIT 防冻结失败：{el:.1f}s'
    assert d['action'] == 'continue' and d['by'] == 'fallback', d
    experts._ENG = OkEngine()
    d2 = experts.mission_plan({'task_id': 't'}, event='task_start')
    assert d2['action'] == 'retry' and d2['by'] == 'llm', d2
    print('INIT_ANTIFREEZE_OK hang->fallback in %.1fs, normal path intact' % el)


if __name__ == '__main__':
    test_init_antifreeze()
    print('V30_4_1_ALL_OK')
