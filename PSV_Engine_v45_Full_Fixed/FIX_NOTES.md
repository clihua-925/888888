# PSV Engine v45 修复说明

## 修复日期
2026-09-01

## 修复内容总览

本次修复针对 v45 架构审计中发现的 4 个关键问题进行了修复：

### 1. core/system.py — 删除旧架构残留
- **问题**：仍然导入已废弃的 `core.tools.expand` 模块
- **修复**：
  - 删除 `from core.tools import expand as expand_tool`
  - `run_network()` 现在使用 `core.intelligence.network_expansion.expand_network`
  - `start_network_expansion()` 增加 `category_id` 参数支持品类隔离

### 2. core/intelligence/network_expansion.py — 实时可视化 + 自动补全闭环
- **问题A**：网络扩张没有实时广播进度，前端无法看到真实运行过程
- **修复A**：在 while 循环中每处理一个节点后，通过 broadcaster 实时推送：
  - `network_expansion_progress`：当前节点、轮次、深度、策略、新增统计
  - `network_expansion_node`：每个新发现节点的详细信息
- **问题B**：新发现的节点只进入池子，没有自动触发情报补全
- **修复B**：在 `_add_to_pool()` 末尾，自动后台线程触发 `waterfall.enrich_entity()`
  - 新节点进入 ENRICHING 状态后，自动启动多源瀑布式补全
  - 补全完成后广播 `auto_enrich_complete` 事件

### 3. core/intelligence/account_intelligence_center.py — 集成 Waterfall 引擎
- **问题**：`_enrich_info()` 只从已有数据库读取，没有调用外部多源补全
- **修复**：
  - 将原有逻辑提取为 `_enrich_from_db()`（基础层）
  - 新的 `_enrich_info()` 先调用 `_enrich_from_db()`，再调用 `WaterfallEnrichmentEngine.enrich_entity()`
  - 瀑布补全结果合并到 profile（仅补充缺失字段，不覆盖已有）
  - 记录补全日志到 `profile.trade_network['last_enrichment']`

### 4. core/memory/db.py — 补充缺失的数据库方法和表
- **新增方法**：
  - `queue_intelligence_task()`：将情报补全任务加入队列
  - `add_to_customer_pool()`：标记实体为客户池成员
  - `add_to_supplier_pool()`：标记实体为供应商池成员
  - `save_task_log()`：记录任务运行日志
- **新增表**：
  - `entity_pools`：实体资源池关系表（支持品类隔离）
  - `task_logs`：任务运行日志表
  - 对应索引：`idx_entity_pools_entity`、`idx_task_logs_task`

## 应用步骤

1. 备份当前项目
2. 解压 `PSV_Engine_v45_Full_Fixed.zip`
3. 覆盖以下文件：
   - `core/system.py`
   - `core/intelligence/network_expansion.py`
   - `core/intelligence/account_intelligence_center.py`
   - `core/memory/db.py`
4. 确认删除旧文件（如果还存在）：
   - `core/tools/expand.py`
   - `core/tools/customs_graph.py`
   - `core/intelligence/account.py`
   - `core/intelligence/ai_gateway.py`
5. 重启服务：`python run_webui.py`

## 验证清单

- [ ] 启动无 ImportError
- [ ] 网络扩张任务能实时看到进度广播
- [ ] 新发现的节点自动进入 ENRICHING 状态
- [ ] 情报中心处理时调用 waterfall 引擎进行多源补全
- [ ] 三个品类数据严格隔离
- [ ] 第一采集链代码未被修改

## 架构闭环验证

修复后系统形成完整闭环：

```
第一采集链（冻结）
    ↓
真实贸易节点 → 情报中心
    ↓
信息补全（Waterfall 多源瀑布）
    ↓
网络扩张（实时可视化 + 自动入池）
    ↓
新节点 → 自动情报补全
    ↓
AI验证 → 证据累积 → 价值判断
    ↓
贸易图谱同步更新
    ↓
达到开发条件 → 业务中心
    ↓
开发信生成 → Outlook 草稿 → 发送
    ↓
跟进反馈 → 情报中心更新
```
