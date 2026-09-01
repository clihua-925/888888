import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ['DATABASE_PATH']=tempfile.mktemp(suffix='.db')
from core.config import settings
settings.DATABASE_PATH=os.environ['DATABASE_PATH']
settings.PUBLIC_CRAWLER_ENABLED=False
settings.EXHIBITION_FALLBACK_ENABLED=False
from core.memory.db import DB
DB()
from core.tools.data_sources.manager import DataSourceManager

def test_evolution_marks_customs_as_first_tier():
    p=DataSourceManager(); plan=p.last_evolution
    assert 'customs_bulk' in __import__('core.tools.data_sources.manager',fromlist=['Evolution']).Evolution().plan('USA','candle')['sources']
