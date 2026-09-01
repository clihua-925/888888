# -*- coding: utf-8 -*-
"""PSV Engine v45 Unified Database Layer
核心原则：
1. 一个实体 = 一个 entity_id + 多个角色/关系/证据/品类关联
2. 情报中心/贸易图谱/业务中心共享统一 entities 表
3. 禁止同一公司三个模块各存一份数据
4. 所有后半程表增加 category_id 字段，三品类严格隔离
5. 第一采集链表 100% 冻结，不修改
"""
import re, sqlite3, time, json
from typing import Dict, List, Any, Optional
from core.config import settings

# ========== 第一采集链表定义（100% 冻结，不得修改） ==========
# 以下表结构和字段名与第一采集链输出契约严格绑定，禁止任何修改
LEAD_COLS = [
    ('category', 'TEXT'), ('website', 'TEXT'), ('emails', 'TEXT'), 
    ('phones', 'TEXT'), ('address', 'TEXT'), ('linkedin', 'TEXT'),
    ('contact_person', 'TEXT'), ('score', 'REAL'), ('grade', 'TEXT'),
    ('profile', 'TEXT'), ('zone', 'TEXT'), ('touch_status', 'TEXT'),
    ('last_touch', 'REAL'), ('audit', 'TEXT')
]

MSG_SQL = """CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_norm TEXT, direction TEXT, channel TEXT, content TEXT, 
    draft INT, ts REAL
);"""


class DB:
    """统一数据库访问层。后半程所有模块通过此层操作数据。"""

    def __init__(self, path=None):
        self.path = path or settings.DATABASE_PATH
        self.init()

    def c(self):
        return sqlite3.connect(self.path, timeout=10)

    def init(self):
        """初始化所有表。第一采集链表冻结，后半程表按标准架构创建。"""
        with self.c() as x:
            # ========== 第一采集链表（100% 冻结） ==========
            x.executescript('''
            CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY, request TEXT, status TEXT, 
                result TEXT, created_at REAL, updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS raw_sources(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, query TEXT, payload TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS clean_batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, 
                stage TEXT, raw_count INT, clean_count INT, noise_count INT,
                duplicate_count INT, identity_only_count INT, 
                hard_evidence_count INT, noise_ratio REAL, clean_ratio REAL, 
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS expansion_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, 
                depth INT, buyers_scanned INT, suppliers_scanned INT,
                new_customers INT, max_new INT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS expansion_frontier(
                norm TEXT PRIMARY KEY, depth INT, source_task TEXT, 
                status TEXT, updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS search_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT,
                market TEXT, industry TEXT, limit_n INT, result_count INT,
                used_sources TEXT, source_errors TEXT, gate TEXT, 
                evolved INT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS project_evolution(
                project_key TEXT PRIMARY KEY, run_count INT, evolved INT, 
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS source_quota(
                source TEXT, day TEXT, count INT, 
                UNIQUE(source, day)
            );
            CREATE TABLE IF NOT EXISTS source_checkpoints(
                source TEXT, project_key TEXT, run_count INT DEFAULT 0,
                cursor INT DEFAULT 0, watermark REAL DEFAULT 0,
                last_count INT DEFAULT 0, last_fingerprint TEXT,
                updated_at REAL, PRIMARY KEY(source, project_key)
            );
            CREATE TABLE IF NOT EXISTS customs_raw(
                id INTEGER PRIMARY KEY AUTOINCREMENT, row_hash TEXT UNIQUE,
                bol TEXT, ts REAL, importer TEXT, importer_norm TEXT,
                shipper TEXT, notify TEXT, hs TEXT, descr TEXT, qty REAL,
                weight REAL, teu REAL, origin TEXT, port_load TEXT,
                port_discharge TEXT, source_file TEXT, 
                direct_importer INT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS buyers_90d(
                importer_norm TEXT PRIMARY KEY, importer TEXT,
                first_seen REAL, last_seen REAL, shipments INT,
                total_weight REAL, total_qty REAL, total_teu REAL,
                supplier_count INT, origins TEXT, ports TEXT,
                sample_desc TEXT, score REAL, reasons TEXT, updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS suppliers(
                supplier_norm TEXT PRIMARY KEY, name TEXT, slug TEXT,
                shipments INT, first_seen REAL, last_seen REAL,
                harvested_at REAL, bol_fetched INT, updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS company_state(
                norm TEXT PRIMARY KEY, name TEXT, first_seen REAL,
                last_seen REAL, runs_seen INT, profiled INT, source TEXT
            );
            CREATE TABLE IF NOT EXISTS harvest_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                slug TEXT, supplier TEXT, mode TEXT, status TEXT, 
                items INT, note TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS iy_nodes(
                norm TEXT, kind TEXT, slug TEXT, url TEXT, shipments INT,
                first_seen REAL, last_visit REAL, visits INT, run_id TEXT,
                PRIMARY KEY(norm, kind)
            );
            CREATE TABLE IF NOT EXISTS trade_nodes(
                norm TEXT PRIMARY KEY, name TEXT, role TEXT, url TEXT,
                shipments INT, products TEXT, hs TEXT, depth INT, via TEXT,
                source TEXT, first_seen REAL, last_seen REAL, runs_seen INT,
                raw TEXT
            );
            CREATE TABLE IF NOT EXISTS relationships(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                from_norm TEXT, from_name TEXT, from_type TEXT,
                to_norm TEXT, to_name TEXT, to_type TEXT, relation TEXT,
                evidence TEXT, source TEXT, confidence REAL, depth INT,
                created_at REAL,
                UNIQUE(task_id, from_norm, to_norm, relation)
            );
            CREATE TABLE IF NOT EXISTS evidence_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                norm TEXT, kind TEXT, source TEXT, content TEXT, 
                weight REAL, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS query_stats(
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_domain TEXT,
                query TEXT, query_type TEXT, expected_role TEXT,
                expected_product_relation TEXT, result_count INT,
                usable_trade_nodes INT, usable_trade_edges INT,
                precision_estimate REAL, recall_contribution REAL,
                runs_zero INT DEFAULT 0, status TEXT DEFAULT 'active',
                created_at REAL, updated_at REAL,
                UNIQUE(product_domain, query)
            );
            CREATE TABLE IF NOT EXISTS product_intel_terms(
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_domain TEXT,
                term TEXT, kind TEXT, hits INT DEFAULT 0, 
                status TEXT DEFAULT 'learned', first_seen REAL, 
                last_seen REAL, UNIQUE(product_domain, term)
            );
            CREATE TABLE IF NOT EXISTS usitc_cache(
                id INTEGER PRIMARY KEY AUTOINCREMENT, hs TEXT, kind TEXT,
                payload TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS leads(
                norm TEXT PRIMARY KEY, name TEXT, country TEXT, kind TEXT,
                hs_code TEXT, shipments INT, last_shipment TEXT, tags TEXT,
                segment TEXT, desc_sample TEXT, source TEXT,
                first_seen REAL, last_seen REAL, status TEXT
            );
            CREATE TABLE IF NOT EXISTS development_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT, lead_norm TEXT,
                status TEXT, result TEXT, created_at REAL, updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS schedules(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE,
                job_type TEXT, market TEXT, industry TEXT, quantity INT,
                interval_minutes INT, enabled INT, next_run REAL,
                last_run REAL, last_status TEXT, params TEXT,
                created_at REAL, updated_at REAL,
                locked_until REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS app_settings(
                key TEXT PRIMARY KEY, value TEXT, updated_at REAL
            );
            ''' + MSG_SQL + '''

            # ========== v45 后半程统一架构表（核心重构） ==========
            self._init_unified_schema(x)

            # ========== 第一采集链索引（冻结） ==========
            x.executescript('''
            CREATE INDEX IF NOT EXISTS idx_customs_importer_norm_ts 
                ON customs_raw(importer_norm, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_customs_shipper_ts 
                ON customs_raw(shipper, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_customs_ts 
                ON customs_raw(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_relationships_from_norm 
                ON relationships(from_norm, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_relationships_to_norm 
                ON relationships(to_norm, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_evidence_events_norm 
                ON evidence_events(norm, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_leads_zone_score 
                ON leads(zone, score DESC, shipments DESC, last_seen DESC);
            ''')

            # ========== 第一采集链字段迁移（冻结兼容） ==========
            have = {r[1] for r in x.execute('PRAGMA table_info(leads)').fetchall()}
            for col, typ in LEAD_COLS + [
                ('opportunity_score', 'REAL'), ('demand_window', 'TEXT'),
                ('demand_confidence', 'REAL'), ('opportunity', 'TEXT'),
                ('development_status', 'TEXT')
            ]:
                if col not in have:
                    x.execute(f'ALTER TABLE leads ADD COLUMN {col} {typ}')
            x.execute("UPDATE leads SET zone='pool' WHERE zone IS NULL OR zone=''")

            have_s = {r[1] for r in x.execute('PRAGMA table_info(schedules)').fetchall()}
            if 'locked_until' not in have_s:
                x.execute("ALTER TABLE schedules ADD COLUMN locked_until REAL DEFAULT 0")

            # v30.8 Trade Edge 升级
            have_r = {r[1] for r in x.execute('PRAGMA table_info(relationships)').fetchall()}
            for col, typ in [
                ('shipment_count', 'INT'), ('hs', 'TEXT'),
                ('product', 'TEXT'), ('first_seen', 'REAL'),
                ('last_seen', 'REAL')
            ]:
                if col not in have_r:
                    x.execute(f'ALTER TABLE relationships ADD COLUMN {col} {typ}')

            if 'evidence_level' not in have_r:
                x.execute("ALTER TABLE relationships ADD COLUMN evidence_level TEXT")

            # v36 边完整可追溯性
            have_r = {r[1] for r in x.execute('PRAGMA table_info(relationships)').fetchall()}
            for col, typ in [
                ('discovered_via', 'TEXT'), ('parent_node', 'TEXT'),
                ('expansion_path', 'TEXT'), ('product_domain', 'TEXT')
            ]:
                if col not in have_r:
                    x.execute(f'ALTER TABLE relationships ADD COLUMN {col} {typ}')

            # v33.0 Trade Node 全字段
            have_t = {r[1] for r in x.execute('PRAGMA table_info(trade_nodes)').fetchall()}
            for col, typ in [
                ('country', 'TEXT'), ('entity_status', 'TEXT'),
                ('product_domain', 'TEXT')
            ]:
                if col not in have_t:
                    x.execute(f'ALTER TABLE trade_nodes ADD COLUMN {col} {typ}')

            # v33.0 统一角色命名
            x.execute("UPDATE leads SET kind='customer' WHERE kind='importer'")

            x.execute("""CREATE TABLE IF NOT EXISTS lead_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, norm TEXT, 
                from_zone TEXT, to_zone TEXT, actor TEXT, reason TEXT, ts REAL
            )""")

            # v45 死表清理：旧架构遗留表
            for _t in ('icp_cards', 'companies', 'evidence', 
                       'expansion_jobs', 'expansion_tasks'):
                x.execute(f"DROP TABLE IF EXISTS {_t}")

    # ========== v45 统一架构表初始化 ==========
    def _init_unified_schema(self, x):
        """初始化后半程统一架构表。一个实体 = 一个 entity_id + 多角色 + 多关系 + 多证据 + 多品类。"""

        # 1. 统一权威实体表（entities）
        # 这是整个后半程的唯一权威实体入口
        x.execute('''
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            norm TEXT UNIQUE NOT NULL,
            name TEXT,
            original_name TEXT,
            country TEXT,
            address TEXT,
            website TEXT,
            phone TEXT,
            enterprise_type TEXT,
            industry TEXT,
            product_categories TEXT,
            brand TEXT,
            entity_status TEXT DEFAULT 'active',
            data_source TEXT,
            created_at REAL,
            updated_at REAL,
            first_seen REAL,
            last_seen REAL
        )''')

        # 2. 实体角色关联表（一个实体可同时是客户和供应商）
        x.execute('''
        CREATE TABLE IF NOT EXISTS entity_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            role TEXT NOT NULL,
            trade_node_id TEXT,
            trade_count INT DEFAULT 0,
            first_trade_date TEXT,
            last_trade_date TEXT,
            created_at REAL,
            updated_at REAL,
            UNIQUE(entity_id, role),
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 3. 实体品类关联表（同一企业多品类，不复制实体）
        x.execute('''
        CREATE TABLE IF NOT EXISTS entity_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            category_id TEXT NOT NULL,
            category_name TEXT,
            product_ids TEXT,
            relevance_score REAL DEFAULT 0,
            created_at REAL,
            updated_at REAL,
            UNIQUE(entity_id, category_id),
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 4. 实体生命周期历史表
        x.execute('''
        CREATE TABLE IF NOT EXISTS entity_lifecycle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT,
            reason TEXT,
            actor TEXT,
            metadata TEXT,
            created_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 5. 统一证据注册表
        # source_type: trade_evidence | web_scrape | ai_inference | contact_info
        x.execute('''
        CREATE TABLE IF NOT EXISTS evidence_registry (
            evidence_id TEXT PRIMARY KEY,
            entity_id TEXT,
            trade_edge_id TEXT,
            source_type TEXT NOT NULL,
            source TEXT,
            evidence TEXT,
            confidence REAL DEFAULT 0,
            discovered_at REAL,
            verified_at REAL,
            metadata TEXT,
            created_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 6. 贸易边表（扩展 relationships，增加 entity_id 关联）
        x.execute('''
        CREATE TABLE IF NOT EXISTS trade_edges (
            edge_id TEXT PRIMARY KEY,
            from_entity_id TEXT,
            to_entity_id TEXT,
            from_norm TEXT,
            to_norm TEXT,
            relation TEXT,
            product TEXT,
            hs_code TEXT,
            shipment_count INT DEFAULT 0,
            first_seen REAL,
            last_seen REAL,
            evidence_level TEXT,
            discovered_via TEXT,
            parent_node TEXT,
            expansion_path TEXT,
            category_id TEXT,
            confidence REAL DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (from_entity_id) REFERENCES entities(entity_id),
            FOREIGN KEY (to_entity_id) REFERENCES entities(entity_id)
        )''')

        # 7. 联系人表（与 entity_id 关联）
        x.execute('''
        CREATE TABLE IF NOT EXISTS entity_contacts (
            contact_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            name TEXT,
            title TEXT,
            email TEXT,
            phone TEXT,
            linkedin TEXT,
            is_verified INT DEFAULT 0,
            email_verified INT DEFAULT 0,
            confidence TEXT DEFAULT 'low',
            source TEXT,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 8. 情报档案表（实体扩展表）
        x.execute('''
        CREATE TABLE IF NOT EXISTS intelligence_profiles (
            profile_id TEXT PRIMARY KEY,
            entity_id TEXT UNIQUE NOT NULL,
            completeness_score REAL DEFAULT 0,
            info_status TEXT,
            icp_score TEXT,
            development_eligible INT DEFAULT 0,
            development_blockers TEXT,
            trade_network TEXT,
            enrichment_log TEXT,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 9. 网络扩张日志表（实时可视化数据）
        x.execute('''
        CREATE TABLE IF NOT EXISTS network_expansion_log (
            log_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            seed_entity_id TEXT,
            round_num INT DEFAULT 0,
            strategy TEXT,
            discovered_entity_id TEXT,
            discovered_norm TEXT,
            discovered_name TEXT,
            discovered_role TEXT,
            relation_type TEXT,
            from_entity_id TEXT,
            evidence TEXT,
            confidence REAL DEFAULT 0,
            is_processed INT DEFAULT 0,
            is_enriched INT DEFAULT 0,
            category_id TEXT,
            created_at REAL
        )''')

        # 10. 信息增益曲线表
        x.execute('''
        CREATE TABLE IF NOT EXISTS info_gain_curve (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            round_num INT,
            strategy TEXT,
            new_customers INT DEFAULT 0,
            new_suppliers INT DEFAULT 0,
            new_edges INT DEFAULT 0,
            new_evidence INT DEFAULT 0,
            new_contacts INT DEFAULT 0,
            new_valid_emails INT DEFAULT 0,
            new_high_value_nodes INT DEFAULT 0,
            total_gain INT DEFAULT 0,
            stop_reason TEXT,
            remaining_nodes INT DEFAULT 0,
            created_at REAL
        )''')

        # 11. 统一任务面板表
        x.execute('''
        CREATE TABLE IF NOT EXISTS task_panel (
            task_id TEXT PRIMARY KEY,
            task_name TEXT,
            category_id TEXT,
            market TEXT,
            current_stage TEXT,
            current_node TEXT,
            run_status TEXT DEFAULT 'pending',
            progress_pct REAL DEFAULT 0,
            discovered_customers INT DEFAULT 0,
            discovered_suppliers INT DEFAULT 0,
            new_trade_edges INT DEFAULT 0,
            new_evidence INT DEFAULT 0,
            enrichment_count INT DEFAULT 0,
            contact_count INT DEFAULT 0,
            verified_count INT DEFAULT 0,
            development_count INT DEFAULT 0,
            failed_nodes TEXT,
            failure_reason TEXT,
            current_tasks TEXT,
            history_tasks TEXT,
            parent_task_id TEXT,
            task_type TEXT,
            metadata TEXT,
            created_at REAL,
            updated_at REAL,
            completed_at REAL
        )''')

        # 12. 业务执行记录表
        x.execute('''
        CREATE TABLE IF NOT EXISTS execution_records (
            record_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            task_id TEXT,
            execution_type TEXT,
            recipient_email TEXT,
            draft_subject TEXT,
            draft_body TEXT,
            personalized_content TEXT,
            used_intelligence TEXT,
            used_evidence TEXT,
            used_ai_model TEXT,
            mail_version TEXT,
            send_status TEXT DEFAULT 'draft',
            sent_at REAL,
            opened_at REAL,
            replied_at REAL,
            sender_email TEXT,
            outlook_draft_url TEXT,
            failure_reason TEXT,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 13. 瀑布补全事件表
        x.execute('''
        CREATE TABLE IF NOT EXISTS waterfall_events (
            event_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            field_name TEXT,
            source_level INT,
            source_name TEXT,
            source_type TEXT,
            old_value TEXT,
            new_value TEXT,
            evidence TEXT,
            confidence REAL DEFAULT 0,
            is_verified INT DEFAULT 0,
            created_at REAL,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )''')

        # 14. 品类配置表
        x.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            category_id TEXT PRIMARY KEY,
            category_name TEXT,
            product_ids TEXT,
            hs_codes TEXT,
            config TEXT,
            created_at REAL
        )''')

        # 创建索引
        x.executescript('''
        CREATE INDEX IF NOT EXISTS idx_entities_norm ON entities(norm);
        CREATE INDEX IF NOT EXISTS idx_entities_country ON entities(country);
        CREATE INDEX IF NOT EXISTS idx_entity_roles_entity ON entity_roles(entity_id);
        CREATE INDEX IF NOT EXISTS idx_entity_roles_role ON entity_roles(role);
        CREATE INDEX IF NOT EXISTS idx_entity_categories_entity ON entity_categories(entity_id);
        CREATE INDEX IF NOT EXISTS idx_entity_categories_cat ON entity_categories(category_id);
        CREATE INDEX IF NOT EXISTS idx_entity_lifecycle_entity ON entity_lifecycle(entity_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence_registry(entity_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence_registry(source_type);
        CREATE INDEX IF NOT EXISTS idx_trade_edges_from ON trade_edges(from_entity_id);
        CREATE INDEX IF NOT EXISTS idx_trade_edges_to ON trade_edges(to_entity_id);
        CREATE INDEX IF NOT EXISTS idx_trade_edges_category ON trade_edges(category_id);
        CREATE INDEX IF NOT EXISTS idx_entity_contacts_entity ON entity_contacts(entity_id);
        CREATE INDEX IF NOT EXISTS idx_intelligence_entity ON intelligence_profiles(entity_id);
        CREATE INDEX IF NOT EXISTS idx_expansion_log_task ON network_expansion_log(task_id, round_num);
        CREATE INDEX IF NOT EXISTS idx_info_gain_task ON info_gain_curve(task_id, round_num);
        CREATE INDEX IF NOT EXISTS idx_task_panel_status ON task_panel(run_status);
        CREATE INDEX IF NOT EXISTS idx_execution_entity ON execution_records(entity_id);
        CREATE INDEX IF NOT EXISTS idx_execution_status ON execution_records(send_status);
        CREATE INDEX IF NOT EXISTS idx_waterfall_entity ON waterfall_events(entity_id, field_name);
        # v45 修复：新增 entity_pools 和 task_logs 表
        x.execute('''CREATE TABLE IF NOT EXISTS entity_pools (
            entity_id TEXT,
            pool_type TEXT,
            category_id TEXT,
            source TEXT,
            task_id TEXT,
            added_at REAL,
            PRIMARY KEY (entity_id, pool_type, category_id)
        )''')
        x.execute('''CREATE TABLE IF NOT EXISTS task_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            event_type TEXT,
            message TEXT,
            created_at REAL
        )''')
        x.execute('''CREATE INDEX IF NOT EXISTS idx_entity_pools_entity ON entity_pools(entity_id)''')
        x.execute('''CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)''')

        ''')

    # ========== 统一实体操作（后半程核心） ==========

    def get_or_create_entity(self, norm: str, name: str = None, **kwargs) -> dict:
        """获取或创建统一实体。所有后半程模块必须通过此入口创建/获取实体。"""
        with self.c() as x:
            row = x.execute(
                "SELECT * FROM entities WHERE norm=?", (norm,)
            ).fetchone()
            if row:
                return dict(row)
            entity_id = f"ent-{uuid.uuid4().hex[:12]}"
            now = time.time()
            x.execute('''
                INSERT INTO entities 
                (entity_id, norm, name, original_name, country, address, 
                 website, phone, enterprise_type, industry, product_categories,
                 brand, entity_status, data_source, created_at, updated_at,
                 first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                entity_id, norm, name or norm, kwargs.get('original_name', name),
                kwargs.get('country', ''), kwargs.get('address', ''),
                kwargs.get('website', ''), kwargs.get('phone', ''),
                kwargs.get('enterprise_type', ''), kwargs.get('industry', ''),
                kwargs.get('product_categories', ''), kwargs.get('brand', ''),
                'active', kwargs.get('data_source', ''), now, now, now, now
            ))
            return {
                'entity_id': entity_id, 'norm': norm, 'name': name or norm,
                'created_at': now, 'is_new': True
            }

    def get_entity(self, norm: str) -> Optional[dict]:
        with self.c() as x:
            row = x.execute("SELECT * FROM entities WHERE norm=?", (norm,)).fetchone()
            return dict(row) if row else None

    def get_entity_by_id(self, entity_id: str) -> Optional[dict]:
        with self.c() as x:
            row = x.execute("SELECT * FROM entities WHERE entity_id=?", (entity_id,)).fetchone()
            return dict(row) if row else None

    def update_entity(self, entity_id: str, **fields) -> bool:
        if not fields:
            return False
        now = time.time()
        fields['updated_at'] = now
        sets = ", ".join([f"{k}=?" for k in fields])
        vals = list(fields.values()) + [entity_id]
        with self.c() as x:
            x.execute(f"UPDATE entities SET {sets} WHERE entity_id=?", vals)
            return x.rowcount > 0

    def set_entity_role(self, entity_id: str, role: str, **kwargs):
        """设置实体角色：customer | supplier | both"""
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO entity_roles 
                (entity_id, role, trade_node_id, trade_count, first_trade_date,
                 last_trade_date, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
            ''', (
                entity_id, role, kwargs.get('trade_node_id', ''),
                kwargs.get('trade_count', 0), kwargs.get('first_trade_date', ''),
                kwargs.get('last_trade_date', ''), now, now
            ))

    def get_entity_roles(self, entity_id: str) -> List[str]:
        with self.c() as x:
            rows = x.execute(
                "SELECT role FROM entity_roles WHERE entity_id=?", (entity_id,)
            ).fetchall()
            return [r[0] for r in rows]

    def set_entity_category(self, entity_id: str, category_id: str, category_name: str = None, **kwargs):
        """设置实体品类关联。同一企业多品类不复制实体。"""
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO entity_categories
                (entity_id, category_id, category_name, product_ids, relevance_score, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
            ''', (
                entity_id, category_id, category_name or category_id,
                kwargs.get('product_ids', ''), kwargs.get('relevance_score', 0),
                now, now
            ))

    def get_entity_categories(self, entity_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM entity_categories WHERE entity_id=?", (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== 生命周期管理 ==========

    def transition_lifecycle(self, entity_id: str, from_state: str, to_state: str, 
                            reason: str = "", actor: str = "system", metadata: dict = None):
        """记录生命周期状态转换。"""
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT INTO entity_lifecycle 
                (entity_id, from_state, to_state, reason, actor, metadata, created_at)
                VALUES (?,?,?,?,?,?,?)
            ''', (
                entity_id, from_state, to_state, reason, actor,
                json.dumps(metadata, ensure_ascii=False) if metadata else '', now
            ))

    def get_lifecycle_history(self, entity_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM entity_lifecycle WHERE entity_id=? ORDER BY created_at DESC",
                (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_current_lifecycle_state(self, entity_id: str) -> str:
        """获取实体当前生命周期状态。"""
        history = self.get_lifecycle_history(entity_id)
        return history[0]['to_state'] if history else 'DISCOVERED'

    # ========== 证据体系 ==========

    def save_evidence(self, evidence_id: str = None, entity_id: str = None, 
                     trade_edge_id: str = None, source_type: str = None,
                     source: str = None, evidence: str = None, 
                     confidence: float = 0, metadata: dict = None) -> str:
        """保存证据。source_type: trade_evidence | web_scrape | ai_inference | contact_info"""
        eid = evidence_id or f"evi-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO evidence_registry
                (evidence_id, entity_id, trade_edge_id, source_type, source,
                 evidence, confidence, discovered_at, metadata, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            ''', (
                eid, entity_id, trade_edge_id, source_type, source,
                evidence, confidence, now,
                json.dumps(metadata, ensure_ascii=False) if metadata else '', now
            ))
        return eid

    def list_evidence(self, entity_id: str = None, source_type: str = None) -> List[dict]:
        with self.c() as x:
            sql = "SELECT * FROM evidence_registry WHERE 1=1"
            params = []
            if entity_id:
                sql += " AND entity_id=?"
                params.append(entity_id)
            if source_type:
                sql += " AND source_type=?"
                params.append(source_type)
            sql += " ORDER BY created_at DESC"
            rows = x.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def verify_evidence(self, evidence_id: str):
        with self.c() as x:
            x.execute(
                "UPDATE evidence_registry SET verified_at=? WHERE evidence_id=?",
                (time.time(), evidence_id)
            )

    # ========== 贸易边操作 ==========

    def save_trade_edge(self, edge_id: str = None, from_entity_id: str = None, 
                       to_entity_id: str = None, from_norm: str = None, 
                       to_norm: str = None, relation: str = None,
                       product: str = None, hs_code: str = None,
                       shipment_count: int = 0, evidence_level: str = None,
                       discovered_via: str = None, parent_node: str = None,
                       expansion_path: str = None, category_id: str = None,
                       confidence: float = 0) -> str:
        eid = edge_id or f"edge-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO trade_edges
                (edge_id, from_entity_id, to_entity_id, from_norm, to_norm,
                 relation, product, hs_code, shipment_count, first_seen, last_seen,
                 evidence_level, discovered_via, parent_node, expansion_path,
                 category_id, confidence, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                eid, from_entity_id, to_entity_id, from_norm, to_norm,
                relation, product, hs_code, shipment_count, now, now,
                evidence_level, discovered_via, parent_node, expansion_path,
                category_id, confidence, now
            ))
        return eid

    def list_trade_edges(self, entity_id: str = None, category_id: str = None) -> List[dict]:
        with self.c() as x:
            sql = "SELECT * FROM trade_edges WHERE 1=1"
            params = []
            if entity_id:
                sql += " AND (from_entity_id=? OR to_entity_id=?)"
                params.extend([entity_id, entity_id])
            if category_id:
                sql += " AND category_id=?"
                params.append(category_id)
            sql += " ORDER BY created_at DESC"
            rows = x.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # ========== 联系人操作 ==========

    def save_contact(self, contact_id: str = None, entity_id: str = None, **kwargs) -> str:
        cid = contact_id or f"ctc-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO entity_contacts
                (contact_id, entity_id, name, title, email, phone, linkedin,
                 is_verified, email_verified, confidence, source, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                cid, entity_id, kwargs.get('name', ''), kwargs.get('title', ''),
                kwargs.get('email', ''), kwargs.get('phone', ''),
                kwargs.get('linkedin', ''), int(kwargs.get('is_verified', False)),
                int(kwargs.get('email_verified', False)), kwargs.get('confidence', 'low'),
                kwargs.get('source', ''), now, now
            ))
        return cid

    def list_entity_contacts(self, entity_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM entity_contacts WHERE entity_id=? ORDER BY created_at DESC",
                (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== 情报档案操作 ==========

    def save_intelligence_profile(self, entity_id: str, **kwargs) -> bool:
        now = time.time()
        profile_id = f"prof-{entity_id}"
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO intelligence_profiles
                (profile_id, entity_id, completeness_score, info_status, icp_score,
                 development_eligible, development_blockers, trade_network,
                 enrichment_log, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                profile_id, entity_id, kwargs.get('completeness_score', 0),
                json.dumps(kwargs.get('info_status', {}), ensure_ascii=False),
                json.dumps(kwargs.get('icp_score', {}), ensure_ascii=False),
                int(kwargs.get('development_eligible', False)),
                json.dumps(kwargs.get('development_blockers', []), ensure_ascii=False),
                json.dumps(kwargs.get('trade_network', {}), ensure_ascii=False),
                json.dumps(kwargs.get('enrichment_log', []), ensure_ascii=False),
                kwargs.get('created_at', now), now
            ))
        return True

    def get_intelligence_profile(self, entity_id: str) -> Optional[dict]:
        with self.c() as x:
            row = x.execute(
                "SELECT * FROM intelligence_profiles WHERE entity_id=?", (entity_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for k in ['info_status', 'icp_score', 'development_blockers', 'trade_network', 'enrichment_log']:
                if d.get(k) and isinstance(d[k], str):
                    try:
                        d[k] = json.loads(d[k])
                    except:
                        d[k] = {} if k != 'development_blockers' else []
            return d

    # ========== 网络扩张日志 ==========

    def log_expansion(self, task_id: str, round_num: int, strategy: str,
                     discovered_entity_id: str, discovered_norm: str,
                     discovered_name: str, discovered_role: str,
                     relation_type: str, from_entity_id: str = None,
                     evidence: str = None, confidence: float = 0,
                     category_id: str = None) -> str:
        log_id = f"exp-{task_id}-{round_num}-{uuid.uuid4().hex[:6]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT INTO network_expansion_log
                (log_id, task_id, seed_entity_id, round_num, strategy,
                 discovered_entity_id, discovered_norm, discovered_name,
                 discovered_role, relation_type, from_entity_id, evidence,
                 confidence, is_processed, is_enriched, category_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                log_id, task_id, '', round_num, strategy,
                discovered_entity_id, discovered_norm, discovered_name,
                discovered_role, relation_type, from_entity_id, evidence,
                confidence, 0, 0, category_id, now
            ))
        return log_id

    def get_expansion_log(self, task_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM network_expansion_log WHERE task_id=? ORDER BY round_num, created_at",
                (task_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_expansion_processed(self, log_id: str, is_enriched: bool = False):
        with self.c() as x:
            x.execute(
                "UPDATE network_expansion_log SET is_processed=1, is_enriched=? WHERE log_id=?",
                (int(is_enriched), log_id)
            )

    # ========== 信息增益曲线 ==========

    def record_info_gain(self, task_id: str, round_num: int, strategy: str,
                        new_customers: int = 0, new_suppliers: int = 0,
                        new_edges: int = 0, new_evidence: int = 0,
                        new_contacts: int = 0, new_valid_emails: int = 0,
                        new_high_value_nodes: int = 0, total_gain: int = 0,
                        stop_reason: str = None, remaining_nodes: int = 0):
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT INTO info_gain_curve
                (task_id, round_num, strategy, new_customers, new_suppliers,
                 new_edges, new_evidence, new_contacts, new_valid_emails,
                 new_high_value_nodes, total_gain, stop_reason, remaining_nodes, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                task_id, round_num, strategy, new_customers, new_suppliers,
                new_edges, new_evidence, new_contacts, new_valid_emails,
                new_high_value_nodes, total_gain, stop_reason, remaining_nodes, now
            ))

    def get_info_gain_curve(self, task_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM info_gain_curve WHERE task_id=? ORDER BY round_num",
                (task_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== 任务面板 ==========

    def create_task(self, task_id: str, task_name: str, task_type: str = None,
                   category_id: str = None, market: str = None,
                   parent_task_id: str = None, metadata: dict = None) -> dict:
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO task_panel
                (task_id, task_name, category_id, market, current_stage,
                 current_node, run_status, progress_pct, discovered_customers,
                 discovered_suppliers, new_trade_edges, new_evidence,
                 enrichment_count, contact_count, verified_count,
                 development_count, failed_nodes, failure_reason,
                 current_tasks, history_tasks, parent_task_id, task_type,
                 metadata, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                task_id, task_name, category_id, market, 'init', '',
                'pending', 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', '', '',
                parent_task_id, task_type,
                json.dumps(metadata, ensure_ascii=False) if metadata else '',
                now, now
            ))
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[dict]:
        with self.c() as x:
            row = x.execute("SELECT * FROM task_panel WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get('metadata') and isinstance(d['metadata'], str):
                try:
                    d['metadata'] = json.loads(d['metadata'])
                except:
                    d['metadata'] = {}
            return d

    def update_task(self, task_id: str, **fields) -> bool:
        if not fields:
            return False
        now = time.time()
        fields['updated_at'] = now
        sets = ", ".join([f"{k}=?" for k in fields])
        vals = list(fields.values()) + [task_id]
        with self.c() as x:
            x.execute(f"UPDATE task_panel SET {sets} WHERE task_id=?", vals)
            return x.rowcount > 0

    def list_tasks(self, status: str = None, task_type: str = None, 
                  category_id: str = None, limit: int = 100) -> List[dict]:
        with self.c() as x:
            sql = "SELECT * FROM task_panel WHERE 1=1"
            params = []
            if status:
                sql += " AND run_status=?"
                params.append(status)
            if task_type:
                sql += " AND task_type=?"
                params.append(task_type)
            if category_id:
                sql += " AND category_id=?"
                params.append(category_id)
            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = x.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def pause_task(self, task_id: str) -> bool:
        return self.update_task(task_id, run_status='paused')

    def resume_task(self, task_id: str) -> bool:
        return self.update_task(task_id, run_status='running')

    # ========== 业务执行记录 ==========

    def create_execution_record(self, entity_id: str, execution_type: str,
                                task_id: str = None, **kwargs) -> str:
        record_id = f"exe-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT INTO execution_records
                (record_id, entity_id, task_id, execution_type, recipient_email,
                 draft_subject, draft_body, personalized_content, used_intelligence,
                 used_evidence, used_ai_model, mail_version, send_status,
                 outlook_draft_url, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                record_id, entity_id, task_id, execution_type,
                kwargs.get('recipient_email', ''),
                kwargs.get('draft_subject', ''),
                kwargs.get('draft_body', ''),
                kwargs.get('personalized_content', ''),
                json.dumps(kwargs.get('used_intelligence', {}), ensure_ascii=False),
                json.dumps(kwargs.get('used_evidence', []), ensure_ascii=False),
                kwargs.get('used_ai_model', ''),
                kwargs.get('mail_version', 'v1'),
                kwargs.get('send_status', 'draft'),
                kwargs.get('outlook_draft_url', ''), now, now
            ))
        return record_id

    def update_execution_status(self, record_id: str, status: str, **kwargs) -> bool:
        now = time.time()
        fields = {'send_status': status, 'updated_at': now}
        if 'sent_at' in kwargs:
            fields['sent_at'] = kwargs['sent_at']
        if 'opened_at' in kwargs:
            fields['opened_at'] = kwargs['opened_at']
        if 'replied_at' in kwargs:
            fields['replied_at'] = kwargs['replied_at']
        if 'sender_email' in kwargs:
            fields['sender_email'] = kwargs['sender_email']
        if 'failure_reason' in kwargs:
            fields['failure_reason'] = kwargs['failure_reason']
        sets = ", ".join([f"{k}=?" for k in fields])
        vals = list(fields.values()) + [record_id]
        with self.c() as x:
            x.execute(f"UPDATE execution_records SET {sets} WHERE record_id=?", vals)
            return x.rowcount > 0

    def list_execution_records(self, entity_id: str = None, status: str = None, 
                               limit: int = 100) -> List[dict]:
        with self.c() as x:
            sql = "SELECT * FROM execution_records WHERE 1=1"
            params = []
            if entity_id:
                sql += " AND entity_id=?"
                params.append(entity_id)
            if status:
                sql += " AND send_status=?"
                params.append(status)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = x.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # ========== 瀑布补全事件 ==========

    def log_waterfall_event(self, entity_id: str, field_name: str, source_level: int,
                           source_name: str, source_type: str, old_value: str,
                           new_value: str, evidence: str = None, 
                           confidence: float = 0) -> str:
        event_id = f"wfe-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT INTO waterfall_events
                (event_id, entity_id, field_name, source_level, source_name,
                 source_type, old_value, new_value, evidence, confidence, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                event_id, entity_id, field_name, source_level, source_name,
                source_type, old_value, new_value, evidence, confidence, now
            ))
        return event_id

    def get_waterfall_history(self, entity_id: str) -> List[dict]:
        with self.c() as x:
            rows = x.execute(
                "SELECT * FROM waterfall_events WHERE entity_id=? ORDER BY created_at DESC",
                (entity_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ========== 第一采集链兼容方法（冻结，只读/只追加） ==========

    def get_lead(self, norm: str) -> Optional[dict]:
        with self.c() as x:
            x.row_factory = sqlite3.Row
            row = x.execute("SELECT * FROM leads WHERE norm=?", (norm,)).fetchone()
            return dict(row) if row else None

    def list_leads(self, kind=None, zone=None, limit=100):
        with self.c() as x:
            x.row_factory = sqlite3.Row
            sql = "SELECT * FROM leads WHERE 1=1"
            params = []
            if kind:
                sql += " AND kind=?"
                params.append(kind)
            if zone:
                sql += " AND zone=?"
                params.append(zone)
            sql += " ORDER BY score DESC, shipments DESC LIMIT ?"
            params.append(limit)
            return [dict(r) for r in x.execute(sql, params).fetchall()]

    def list_lead_trades(self, norm: str) -> List[dict]:
        with self.c() as x:
            x.row_factory = sqlite3.Row
            rows = x.execute(
                "SELECT * FROM customs_raw WHERE importer_norm=? ORDER BY ts DESC",
                (norm,)
            ).fetchall()
            return [dict(r) for r in rows]

    def list_contacts(self, norm: str) -> List[dict]:
        with self.c() as x:
            x.row_factory = sqlite3.Row
            rows = x.execute(
                "SELECT * FROM entity_contacts WHERE entity_id IN (SELECT entity_id FROM entities WHERE norm=?)",
                (norm,)
            ).fetchall()
            return [dict(r) for r in rows]

    def lead_update(self, norm: str, **kwargs):
        if not kwargs:
            return
        sets = ", ".join([f"{k}=?" for k in kwargs])
        vals = list(kwargs.values()) + [norm]
        with self.c() as x:
            x.execute(f"UPDATE leads SET {sets} WHERE norm=?", vals)

    def save_task(self, task_id, request, status, result):
        now = time.time()
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO tasks (task_id, request, status, result, created_at, updated_at)
                VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM tasks WHERE task_id=?), ?), ?)
            ''', (task_id, request, status, json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result), task_id, now, now))

    def get_task(self, task_id):
        with self.c() as x:
            x.row_factory = sqlite3.Row
            row = x.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d['result'] = json.loads(d.get('result', '{}'))
            except:
                d['result'] = {}
            return d

    def get_account_intelligence(self, norm: str) -> Optional[dict]:
        """兼容旧接口：从统一实体表查询情报。"""
        entity = self.get_entity(norm)
        if not entity:
            return None
        profile = self.get_intelligence_profile(entity['entity_id'])
        if profile:
            entity.update(profile)
        entity['roles'] = self.get_entity_roles(entity['entity_id'])
        entity['categories'] = self.get_entity_categories(entity['entity_id'])
        entity['contacts'] = self.list_entity_contacts(entity['entity_id'])
        entity['evidence'] = self.list_evidence(entity['entity_id'])
        entity['lifecycle'] = self.get_lifecycle_history(entity['entity_id'])
        return entity

    def add_enrichment_event(self, norm: str, field: str, provider: str, 
                            value: str, success: bool):
        """兼容旧接口：记录到 waterfall_events。"""
        entity = self.get_entity(norm)
        if entity:
            self.log_waterfall_event(
                entity_id=entity['entity_id'],
                field_name=field,
                source_level=1,
                source_name=provider,
                source_type='enrichment',
                old_value='',
                new_value=value,
                confidence=1.0 if success else 0
            )

    def finish_development(self, lead_norm, result, status):
        with self.c() as x:
            x.execute(
                "INSERT OR REPLACE INTO development_runs (lead_norm, status, result, created_at, updated_at) VALUES (?,?,?,?,?)",
                (lead_norm, status, json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result), time.time(), time.time())
            )

    def latest_development(self, lead_norm):
        with self.c() as x:
            x.row_factory = sqlite3.Row
            row = x.execute("SELECT * FROM development_runs WHERE lead_norm=? ORDER BY created_at DESC LIMIT 1", (lead_norm,)).fetchone()
            return dict(row) if row else None

    def create_execution_record_old(self, norm, execution_type, draft_subject, 
                                    draft_body, personalized_content, recipient_email):
        """兼容旧接口。"""
        entity = self.get_entity(norm)
        entity_id = entity['entity_id'] if entity else None
        return self.create_execution_record(
            entity_id=entity_id, execution_type=execution_type,
            draft_subject=draft_subject, draft_body=draft_body,
            personalized_content=personalized_content,
            recipient_email=recipient_email
        )

    def update_execution_status_old(self, record_id, status, **kwargs):
        """兼容旧接口。"""
        return self.update_execution_status(record_id, status, **kwargs)

    def list_execution_records_old(self, status=None, limit=100):
        """兼容旧接口。"""
        return self.list_execution_records(status=status, limit=limit)

    def list_schedules(self, enabled=None):
        with self.c() as x:
            x.row_factory = sqlite3.Row
            sql = "SELECT * FROM schedules"
            params = []
            if enabled is not None:
                sql += " WHERE enabled=?"
                params.append(1 if enabled else 0)
            sql += " ORDER BY next_run"
            return [dict(r) for r in x.execute(sql, params).fetchall()]

    def claim_due_schedule(self, sid, lock_seconds=120):
        now = time.time()
        with self.c() as x:
            r = x.execute("SELECT locked_until FROM schedules WHERE id=?", (sid,)).fetchone()
            if r and (r[0] or 0) > now:
                return False
            x.execute("UPDATE schedules SET locked_until=? WHERE id=?", (now + lock_seconds, sid))
            return x.rowcount > 0

    def mark_schedule_run(self, sid, status):
        with self.c() as x:
            x.execute("UPDATE schedules SET last_run=?, last_status=? WHERE id=?", (time.time(), status, sid))

    def get_setting(self, key, default=None):
        with self.c() as x:
            r = x.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return r[0] if r else default

    def set_setting(self, key, value):
        with self.c() as x:
            x.execute("INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?,?,?)", (key, value, time.time()))


    # ===== v45 修复：新增缺失方法 =====

    def queue_intelligence_task(self, norm: str, category_id: str = None, source_task_id: str = None) -> str:
        """将情报补全任务加入队列，供后台 worker 处理。"""
        task_id = f"enrich-{uuid.uuid4().hex[:8]}"
        with self.c() as x:
            x.execute('''
                INSERT INTO tasks (task_id, request, status, result, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                task_id,
                f'Waterfall enrichment: {norm}',
                'queued',
                json.dumps({
                    'mode': 'waterfall_enrichment',
                    'norm': norm,
                    'category_id': category_id,
                    'source_task_id': source_task_id,
                    'queued_at': time.time()
                }),
                time.time()
            ))
        return task_id

    def add_to_customer_pool(self, norm: str, category_id: str = None, source: str = '', task_id: str = None):
        """将实体标记为客户资源池成员。"""
        entity = self.get_or_create_entity(norm=norm, name=norm)
        entity_id = entity.get('entity_id')
        self.set_entity_role(entity_id, 'customer')
        if category_id:
            self.set_entity_category(entity_id, category_id)
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO entity_pools 
                (entity_id, pool_type, category_id, source, task_id, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (entity_id, 'customer', category_id, source, task_id, time.time()))

    def add_to_supplier_pool(self, norm: str, category_id: str = None, source: str = '', task_id: str = None):
        """将实体标记为供应商资源池成员。"""
        entity = self.get_or_create_entity(norm=norm, name=norm)
        entity_id = entity.get('entity_id')
        self.set_entity_role(entity_id, 'supplier')
        if category_id:
            self.set_entity_category(entity_id, category_id)
        with self.c() as x:
            x.execute('''
                INSERT OR REPLACE INTO entity_pools 
                (entity_id, pool_type, category_id, source, task_id, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (entity_id, 'supplier', category_id, source, task_id, time.time()))

    def save_task_log(self, task_id: str, event_type: str, message: str):
        """记录任务运行日志。"""
        with self.c() as x:
            x.execute('''
                INSERT INTO task_logs (task_id, event_type, message, created_at)
                VALUES (?, ?, ?, ?)
            ''', (task_id, event_type, message, time.time()))
