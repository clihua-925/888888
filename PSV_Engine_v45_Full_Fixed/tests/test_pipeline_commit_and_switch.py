import json
import sqlite3


def _classified(name, lc='CUSTOMER_CONFIRMED', typ='importer', shipments=4):
    return {'name': name, 'country': 'USA', 'type': typ, 'source': 'customs_raw',
            'lifecycle': lc, 'product_domain': 'CANDLE',
            'evidence': {'shipments': shipments, 'customs': True}}


def test_database_commit_merges_existing_lead_without_resetting_zone(tmp_path, monkeypatch):
    db_path = tmp_path / 'psv.db'
    monkeypatch.setenv('DATABASE_PATH', str(db_path))
    from core.memory import db as dbmod
    from core.runtime import nodes
    from core.config import settings
    monkeypatch.setattr(settings, 'DATABASE_PATH', str(db_path))
    db = dbmod.DB(str(db_path))
    monkeypatch.setattr(nodes.experts, 'review', lambda *a, **k: {'verdict': 'pass', 'notes': ''})
    name = 'The Felt Store Inc.'
    db.upsert_leads([{'name': name, 'country': 'USA', 'kind': 'importer', 'shipments': 4, 'source': 'customs_raw'}])
    db.lead_update(db._norm(name), zone='maint')  # 已有实体在维护池
    state = {'task_id': 't1', 'industry': 'candle', 'classified_entities': [_classified(name)], 'node_reports': {}}
    out = nodes.n_database_commit(state)
    assert out['_success'] is True
    dc = out['database_commit']
    assert dc['dev'] == 0 and dc['updated'] + dc['unchanged'] == 1, dc
    lead = db.get_lead(db._norm(name))
    assert lead['zone'] == 'maint', '已有实体区域不得被重置'
    assert lead['lifecycle'] == 'CUSTOMER_CONFIRMED', '已有实体只补空分类字段'


def test_lead_outreach_state(tmp_path):
    from core.memory.db import DB
    db = DB(str(tmp_path / 'psv.db'))
    name = 'Example Importer LLC'
    db.upsert_leads([{'name': name, 'country': 'USA', 'kind': 'importer', 'source': 'customs_raw'}])
    norm = db._norm(name)
    assert db.list_leads()[0]['outreach_state'] == 'not_started'
    db.add_message(norm, 'out', 'email', 'Subject: test\n\nbody', draft=1)
    assert db.list_leads()[0]['outreach_state'] == 'draft'
    db.add_message(norm, 'out', 'email', 'Subject: test\n\nbody', draft=0)
    assert db.list_leads()[0]['outreach_state'] == 'sent'


def test_full_chain_clean_classify_commit(tmp_path, monkeypatch):
    """ENTITY_RESOLUTION 不预写客户；DATABASE_COMMIT 提交全部已分类实体。"""
    db_path = tmp_path / 'psv.db'
    monkeypatch.setenv('DATABASE_PATH', str(db_path))
    from core.memory import db as dbmod
    from core.runtime import nodes
    from core.config import settings
    monkeypatch.setattr(settings, 'DATABASE_PATH', str(db_path))
    db = dbmod.DB(str(db_path))
    monkeypatch.setattr(nodes.experts, 'review', lambda *a, **k: {'verdict': 'pass', 'notes': ''})
    state = {'task_id': 't-clean-commit', 'industry': 'candle', 'companies': [
        {'name': 'Brand New Candle LLC', 'country': 'USA', 'source': 'customs_raw',
         'evidence': {'shipments': 5, 'customs': True, 'trade_evidence': True}}
    ], 'node_reports': {}}
    cleaned = nodes.n_entity_resolution(state)
    assert db.get_lead(db._norm('Brand New Candle LLC')) is None, '实体解析不得预写客户库'
    state.update(cleaned)
    cls = nodes.n_resource_classification(state)
    state.update(cls)
    assert state['classified_entities'][0]['lifecycle'] == 'CUSTOMER_CONFIRMED'
    committed = nodes.n_database_commit(state)
    assert committed['_success'] is True
    assert committed['database_commit']['dev'] == 1
    assert db.get_lead(db._norm('Brand New Candle LLC'))['zone'] == 'dev'


def test_repeat_run_reports_update_not_zero(tmp_path, monkeypatch):
    """回归锁（QUALIFIED 40→入库0）：重复运行时同一批实体必须报"更新N"，
    而不是被新旧判定过滤成"提交0"。"""
    db_path = tmp_path / 'psv.db'
    monkeypatch.setenv('DATABASE_PATH', str(db_path))
    from core.memory import db as dbmod
    from core.runtime import nodes
    from core.config import settings
    monkeypatch.setattr(settings, 'DATABASE_PATH', str(db_path))
    db = dbmod.DB(str(db_path))
    monkeypatch.setattr(nodes.experts, 'review', lambda *a, **k: {'verdict': 'pass', 'notes': ''})
    ents = [_classified(f'Repeat Buyer {i} Co') for i in range(5)]
    state = {'task_id': 'r1', 'classified_entities': ents, 'node_reports': {}}
    first = nodes.n_database_commit(state)
    assert first['database_commit']['dev'] == 5
    # 第二次运行：票数增加 = 有新证据
    ents2 = [_classified(f'Repeat Buyer {i} Co', shipments=10) for i in range(5)]
    second = nodes.n_database_commit({'task_id': 'r2', 'classified_entities': ents2, 'node_reports': {}})
    dc2 = second['database_commit']
    assert dc2['input'] == 5 and dc2['converted'] == 5, dc2
    assert dc2['updated'] + dc2['unchanged'] == 5, '重复运行必须是更新/无变化，而不是提交0'
    assert dc2['dev'] == 0
