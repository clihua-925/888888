# -*- coding: utf-8 -*-
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
def _env():
    p=PROJECT_ROOT/'.env'
    if p.exists():
        raw=p.read_bytes()
        text=''
        for enc in ('utf-8-sig','utf-16'):
            try: text=raw.decode(enc); break
            except Exception: continue
        if not text: text=raw.decode('utf-8','ignore')
        for line in text.replace('\x00','').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k.strip(), v.strip())
_env()

# 当前品类
INDUSTRY=os.getenv('INDUSTRY','candle')
VERSION='v40.0-database-ui-alignment'
# v34.0 统一节点状态机（前后端同一份定义；UI 对历史小写值做兼容映射，不产生新值）
NODE_STATUS=('PENDING','RUNNING','SUCCESS','FAILED','BLOCKED','SKIPPED','CANCELLED')
# DEBUG_ONLY：UI"单独执行"按钮与 /api/task/<id>/node 端点仅在显式调试模式下可用，
# 且只返回结果不落正式任务状态（不得绕过 MISSION_DIRECTOR/契约/证据要求/状态机）。
DEBUG_MODE=os.getenv('DEBUG_MODE','false').lower()=='true'

# v34 数字口径语义固化：83/85/87 类数字不是错误，是不同阶段的资产口径
COUNT_SEMANTICS = {
    'trade_nodes': 'CUSTOMS_NODE_COLLECTION 登记的贸易图谱候选节点数（含 UNRESOLVED，宽采集不删除）',
    'companies': 'GRAPH_EXPANSION 扩张后的实体集合（深度层反向收割并入，同名合并证据保留）',
    'classified_entities': 'RESOURCE_CLASSIFICATION 分类实体数（含 supplier_new 池供应商，可能 > companies）',
    'relationships': 'DATABASE_COMMIT 唯一写库出口的正式关系边（含双向关系 buyer_to_supplier/supplier_to_customer）',
    'leads': 'leads 表实体资产（customer/supplier/both，kind 语义唯一）',
}
LLM_BASE_URL=os.getenv('LLM_BASE_URL','http://192.168.1.26:8081/v1')
LLM_MODEL=os.getenv('LLM_MODEL','deepseek-r1-distill-llama-70b')
LLM_API_KEY=os.getenv('LLM_API_KEY','not-needed')
LLM_TIMEOUT=int(os.getenv('LLM_TIMEOUT','480'))
LLM_MAX_TOKENS=int(os.getenv('LLM_MAX_TOKENS','4096'))
DATABASE_PATH=str(Path(os.getenv('DATABASE_PATH', str(PROJECT_ROOT/'data'/'psv.db'))).expanduser().resolve())
# v35 单一数据源铁律：一个运行实例 = 一个数据根目录 = 一个数据库。
# 相对路径一律解析为绝对路径（杜绝 cwd 不同导致的"另一个 psv.db"）。
DATA_ROOT=str(Path(DATABASE_PATH).parent)
IMPORT_DIR=str(PROJECT_ROOT/'data'/'imports')
CUSTOMS_DIR=str(PROJECT_ROOT/'data'/'customs')
WEB_HOST=os.getenv('WEB_HOST','0.0.0.0'); WEB_PORT=int(os.getenv('WEB_PORT','8090'))
SOURCE_PER_LIMIT=int(os.getenv('SOURCE_PER_LIMIT','30'))
AGGREGATE_MIN_RESULTS=int(os.getenv('AGGREGATE_MIN_RESULTS','25'))
PROFILE_TOP_N=int(os.getenv('PROFILE_TOP_N','10')); ANALYSIS_TOP_N=int(os.getenv('ANALYSIS_TOP_N','10')); LETTER_TOP_N=int(os.getenv('LETTER_TOP_N','5'))
IMPORTYETI_ENABLED=os.getenv('IMPORTYETI_ENABLED','false').lower()=='true'
IMPORTYETI_SEARCH_URL=os.getenv('IMPORTYETI_SEARCH_URL','https://www.importyeti.com/api/search')
IMPORTYETI_DAILY_QUOTA=int(os.getenv('IMPORTYETI_DAILY_QUOTA','25'))
IMPORTYETI_QUOTA_RESERVE=int(os.getenv('IMPORTYETI_QUOTA_RESERVE','5'))
IMPORTYETI_MAX_PAGES=int(os.getenv('IMPORTYETI_MAX_PAGES','1'))
BING_CN_ENABLED=os.getenv('BING_CN_ENABLED','false').lower()=='true'
HS_FINDER_ENABLED=os.getenv('HS_FINDER_ENABLED','true').lower()=='true'
HS_CODES=os.getenv('HS_CODES','3406')
CONTACT_ENABLED=os.getenv('CONTACT_ENABLED','true').lower()=='true'
CONTACT_TOP_N=int(os.getenv('CONTACT_TOP_N','10'))
CONTACT_HARD_STD=os.getenv('CONTACT_HARD_STD','true').lower()=='true'
CONTACT_MODE=os.getenv('CONTACT_MODE','webai_first')
# ---- v18.3.0 资料审核 ----
AUDIT_ENABLED=os.getenv('AUDIT_ENABLED','true').lower()=='true'
AUDIT_AI_MODE=os.getenv('AUDIT_AI_MODE','always')
AUDIT_AI_PER_RUN=int(os.getenv('AUDIT_AI_PER_RUN','30'))
# ---- v18.0 邮件发送 ----
MAIL_PROVIDER=os.getenv('MAIL_PROVIDER','outlook')
SMTP_HOST=os.getenv('SMTP_HOST','smtp-mail.outlook.com')
SMTP_PORT=int(os.getenv('SMTP_PORT','587'))
SMTP_USER=os.getenv('SMTP_USER','changlihua925@outlook.com')
SMTP_PASS=os.getenv('SMTP_PASS','')
SMTP_FROM=os.getenv('SMTP_FROM','')
# ---- v16.5 网页AI ----
WEBAI_ENABLED=os.getenv('WEBAI_ENABLED','true').lower()=='true'
WEBAI_ENGINE=os.getenv('WEBAI_ENGINE','chatgpt')   # 主引擎 GPT，备用 DeepSeek
WEBAI_DAILY_MAX=int(os.getenv('WEBAI_DAILY_MAX','200'))
WEBAI_MIN_INTERVAL=int(os.getenv('WEBAI_MIN_INTERVAL','15'))
WEBAI_TIMEOUT=int(os.getenv('WEBAI_TIMEOUT','150'))
WEBAI_PER_RUN=int(os.getenv('WEBAI_PER_RUN','50'))
# ---- v37/v38 AI_REASONING_GATEWAY：多模型 Fallback 链路 ----
# AI_PROVIDER_CHAIN 逗号分隔（local / webai:chatgpt / webai:deepseek / webai:qwen），空则用 AI_PRIMARY 单主+浏览器备
AI_PROVIDER_CHAIN=os.getenv('AI_PROVIDER_CHAIN','')
AI_PRIMARY=os.getenv('AI_PRIMARY','local')
# v38 微软邮箱自动发送（Playwright 点击发送）：默认关闭=半自动人工门；开启后 DEV_SEND 自动完成发送动作
OUTLOOK_AUTO_SEND=os.getenv('OUTLOOK_AUTO_SEND','true').lower()=='true'  # v39 默认自动执行；=false 回到半自动
# ---- v17 署名与工厂档案 ----
SENDER_NAME=os.getenv('SENDER_NAME','常立华')
SENDER_NAME_EN=os.getenv('SENDER_NAME_EN','Lihua Chang')
SENDER_PHONE=os.getenv('SENDER_PHONE','+86 17303304256')
SENDER_EMAIL=os.getenv('SENDER_EMAIL','changlihua925@outlook.com')
SENDER_COMPANY=os.getenv('SENDER_COMPANY','Ningjin Birthday Candle Factory')
# ---- v17 网络扩张预算 ----
EXPAND_BUYERS=int(os.getenv('EXPAND_BUYERS','5'))
EXPAND_CUSTOMERS=int(os.getenv('EXPAND_CUSTOMERS','15'))
EXPAND_MAX_NEW=int(os.getenv('EXPAND_MAX_NEW','40'))
DDG_ENABLED=os.getenv('DDG_ENABLED','false').lower()=='true'
DATA_SOURCE_TIMEOUT=int(os.getenv('DATA_SOURCE_TIMEOUT','12'))
SCRAPE_PROXY_URL=os.getenv('SCRAPE_PROXY_URL','')
EVOLUTION_TRIGGER_RUNS=int(os.getenv('EVOLUTION_TRIGGER_RUNS','3'))
EVOLUTION_MAX_QUERY_VARIANTS=int(os.getenv('EVOLUTION_MAX_QUERY_VARIANTS','2'))
GATE_MIN_QUALIFIED=int(os.getenv('GATE_MIN_QUALIFIED','3'))
GATE_MIN_STRONG=int(os.getenv('GATE_MIN_STRONG','1'))
# ---- v14 反向收割 ----
APIFY_TOKEN=os.getenv('APIFY_TOKEN','')
APIFY_ACTOR=os.getenv('APIFY_ACTOR','logiover~importyeti-scraper')
APIFY_RUN_TIMEOUT=int(os.getenv('APIFY_RUN_TIMEOUT','420'))
APIFY_MAX_SUPPLIERS_PER_RUN=int(os.getenv('APIFY_MAX_SUPPLIERS_PER_RUN','3'))
APIFY_COMPANY_INPUT=os.getenv('APIFY_COMPANY_INPUT','{"mode":"companySearch","companySlug":"{slug}","maxResults":50}')
HARVEST_ENABLED=os.getenv('HARVEST_ENABLED','true').lower()=='true'
HARVEST_MIN_SHIPMENTS=int(os.getenv('HARVEST_MIN_SHIPMENTS','1'))
# ---- v14.1 ImportYeti 网页收割 ----
IY_WEB_ENABLED=os.getenv('IY_WEB_ENABLED','true').lower()=='true'
IY_WEB_HEADLESS=os.getenv('IY_WEB_HEADLESS','true').lower()=='true'
IY_WEB_AUTO_HEADED=os.getenv('IY_WEB_AUTO_HEADED','true').lower()=='true'
IY_WEB_CHALLENGE_WAIT=float(os.getenv('IY_WEB_CHALLENGE_WAIT','30'))
IY_WEB_CDP_ENABLED=os.getenv('IY_WEB_CDP_ENABLED','true').lower()=='true'
IY_WEB_CDP_URL=os.getenv('IY_WEB_CDP_URL','http://127.0.0.1:9222')
IY_WEB_DELAY_MIN=float(os.getenv('IY_WEB_DELAY_MIN','4'))
IY_WEB_DELAY_MAX=float(os.getenv('IY_WEB_DELAY_MAX','8'))
IY_WEB_SEARCH_LIMIT=int(os.getenv('IY_WEB_SEARCH_LIMIT','25'))
IY_WEB_TOP_BUYERS=int(os.getenv('IY_WEB_TOP_BUYERS','5'))
IY_WEB_MAX_SUPPLIERS=int(os.getenv('IY_WEB_MAX_SUPPLIERS','5'))
IY_WEB_MAX_CUSTOMERS=int(os.getenv('IY_WEB_MAX_CUSTOMERS','25'))
# v30.3 节点网络与页访预算：ImportYeti 免费额度约 25 页/IP，页访是稀缺资源。
# 单次任务页访预算；节点页访问历史持久化，NODE_REVISIT_DAYS 内绝不重复访问同一节点。
IY_PAGE_BUDGET=int(os.getenv('IY_PAGE_BUDGET','25'))
NODE_REVISIT_DAYS=int(os.getenv('NODE_REVISIT_DAYS','21'))
IY_REL_MAX_ROWS=int(os.getenv('IY_REL_MAX_ROWS','100'))  # 单节点关系区一次最多抓取的行数（尽量拿全该节点全部提票关系）
# v30.5 节点渗透：第一搜索在 ImportYeti 锁定节点后，递归展开关系网的深度与安全上限。
# 渗透残片不按 quantity 截断——第一阶段建完整图谱，数量闸门属于第二阶段。
IY_PENETRATION_DEPTH=int(os.getenv('IY_PENETRATION_DEPTH','2'))
IY_SEARCH_VARIANTS=int(os.getenv('IY_SEARCH_VARIANTS','3'))
COLLECT_MAX_NODES=int(os.getenv('COLLECT_MAX_NODES','300'))
# ---- v15 ExpertGraph ----
EXPERT_MODE=os.getenv('EXPERT_MODE','true').lower()=='true'
REFLECT_MAX_ROUNDS=int(os.getenv('REFLECT_MAX_ROUNDS','3'))
LLM_REVIEW_MAX_TOKENS=int(os.getenv('LLM_REVIEW_MAX_TOKENS','900'))
LLM_REVIEW_TIMEOUT=int(os.getenv('LLM_REVIEW_TIMEOUT','240'))
MISSION_DIRECTOR_TIMEOUT=int(os.getenv('MISSION_DIRECTOR_TIMEOUT','120'))  # 总统筹规划硬时限：质量优先、时间放宽；超时按固定拓扑继续，任务不冻结在 INIT
# v24 orchestration: each expert is independently reviewed; recovery changes plan after 3 failed attempts
NODE_RETRIES=int(os.getenv('NODE_RETRIES','3'))
MISSION_DIRECTOR_ENABLED=os.getenv('MISSION_DIRECTOR_ENABLED','true').lower()=='true'
HANDOFF_VALIDATION_ENABLED=os.getenv('HANDOFF_VALIDATION_ENABLED','true').lower()=='true'
WEB_AI_AFTER_RETRIES=int(os.getenv('WEB_AI_AFTER_RETRIES','3'))
GRAPH_MAX_STEPS=int(os.getenv('GRAPH_MAX_STEPS','180'))
# ---- v14 USITC ----
USITC_TOKEN=os.getenv('USITC_TOKEN','')
USITC_API_URL=os.getenv('USITC_API_URL','https://datawebws.usitc.gov/dataweb/api/v2/report2/runReport')
USITC_HS_CODE=os.getenv('USITC_HS_CODE','3406')
USITC_NOTES_FILE=os.getenv('USITC_NOTES_FILE', str(PROJECT_ROOT/'data'/'usitc_notes.txt'))
for p in (Path(DATABASE_PATH).parent, Path(IMPORT_DIR), Path(CUSTOMS_DIR)): p.mkdir(parents=True, exist_ok=True)

def data_root_info():
    """启动自检：返回唯一数据根的事实信息（供启动横幅与 UI 展示）。"""
    p = Path(DATABASE_PATH)
    return {'data_root': DATA_ROOT, 'database': str(p),
            'exists': p.exists(), 'size_bytes': p.stat().st_size if p.exists() else 0}

# === 自动补齐的配置 ===

OUTREACH_ENABLED=os.getenv('OUTREACH_ENABLED','false').lower()=='true'

BING_ENABLED=os.getenv('BING_ENABLED','false').lower()=='true'

# scheduler / dual-pipeline
SCHEDULER_ENABLED=os.getenv('SCHEDULER_ENABLED','true').lower()=='true'
SCHEDULER_POLL_SECONDS=int(os.getenv('SCHEDULER_POLL_SECONDS','10'))
DEVELOPMENT_MAX_CUSTOMERS=int(os.getenv('DEVELOPMENT_MAX_CUSTOMERS','20'))
DEVELOPMENT_SEQUENCE_ENABLED=os.getenv('DEVELOPMENT_SEQUENCE_ENABLED','true').lower()=='true'



# Customs Graph Core
RAW_MIN_CLEAN=int(os.getenv('RAW_MIN_CLEAN','1'))
RAW_MAX_NOISE_RATIO=float(os.getenv('RAW_MAX_NOISE_RATIO','0.55'))
RAW_MAX_DUP_RATIO=float(os.getenv('RAW_MAX_DUP_RATIO','0.70'))
RAW_MIN_HARD_EVIDENCE_RATIO=float(os.getenv('RAW_MIN_HARD_EVIDENCE_RATIO','0.25'))
CLEAN_KEEP_IDENTITY_ONLY=True
SEED_BUYERS_PER_TASK=int(os.getenv('SEED_BUYERS_PER_TASK','10'))
SUPPLIER_MINING_BUYERS=int(os.getenv('SUPPLIER_MINING_BUYERS','5'))
SUPPLIER_MINING_MAX_SUPPLIERS=int(os.getenv('SUPPLIER_MINING_MAX_SUPPLIERS','25'))
NETWORK_EXPANSION_ENABLED=os.getenv('NETWORK_EXPANSION_ENABLED','true').lower()=='true'
NETWORK_EXPANSION_DEPTH=int(os.getenv('NETWORK_EXPANSION_DEPTH','2'))
NETWORK_EXPANSION_BUYERS=int(os.getenv('NETWORK_EXPANSION_BUYERS','5'))
NETWORK_EXPANSION_SUPPLIERS=int(os.getenv('NETWORK_EXPANSION_SUPPLIERS','5'))
NETWORK_EXPANSION_CUSTOMERS=int(os.getenv('NETWORK_EXPANSION_CUSTOMERS','15'))
NETWORK_EXPANSION_MAX_NEW=int(os.getenv('NETWORK_EXPANSION_MAX_NEW','40'))
NETWORK_EXPANSION_MAX_NODES=int(os.getenv('NETWORK_EXPANSION_MAX_NODES','80'))
EXHIBITION_FALLBACK_ENABLED=os.getenv('EXHIBITION_FALLBACK_ENABLED','true').lower()=='true'
PUBLIC_CRAWLER_ENABLED=os.getenv('PUBLIC_CRAWLER_ENABLED','false').lower()=='true'
PUBLIC_CRAWLER_MAX_RESULTS=int(os.getenv('PUBLIC_CRAWLER_MAX_RESULTS','20'))
PUBLIC_CRAWLER_DAILY_QUOTA=int(os.getenv('PUBLIC_CRAWLER_DAILY_QUOTA','20'))

# v27 海关数据源层：所有能提供海关/提单证据的来源均归入第一采集层。
# 格式：NAME|PUBLIC_OR_AUTHORIZED_JSON_URL_WITH_{query}[;NAME2|URL2]
CUSTOMS_WEB_SOURCES=os.getenv('CUSTOMS_WEB_SOURCES','')
CUSTOMS_WEB_DAILY_QUOTA=int(os.getenv('CUSTOMS_WEB_DAILY_QUOTA','30'))
CUSTOMS_SOURCE_POLICY=os.getenv('CUSTOMS_SOURCE_POLICY','customs_first')
# ImportKey：仅读取其公开公司海关页，默认关闭；开启后只做关系补充，不绕过登录/验证码。
IMPORTKEY_ENABLED=os.getenv('IMPORTKEY_ENABLED','true').lower()=='true'
IMPORTKEY_MAX_RELATIONS=int(os.getenv('IMPORTKEY_MAX_RELATIONS','10'))

# v27.1.3 增量采集：硬海关源多查询词轮换 + 已知实体刷新预算。
INCREMENTAL_COLLECTION_ENABLED=os.getenv('INCREMENTAL_COLLECTION_ENABLED','true').lower()=='true'
INCREMENTAL_REFRESH_RATIO=float(os.getenv('INCREMENTAL_REFRESH_RATIO','0.25'))
INCREMENTAL_SOURCE_PAGE_SIZE=int(os.getenv('INCREMENTAL_SOURCE_PAGE_SIZE','50'))
INCREMENTAL_SOURCE_OVERLAP=int(os.getenv('INCREMENTAL_SOURCE_OVERLAP','5'))
INCREMENTAL_WATERMARK_OVERLAP_SECONDS=int(os.getenv('INCREMENTAL_WATERMARK_OVERLAP_SECONDS','86400'))

