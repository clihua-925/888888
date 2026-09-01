# PSV Engine v40 后半段业务架构升级包

## 升级内容

### 新建模块（6个文件）
1. `core/intelligence/ai_router.py` — AI统一路由（GPT/DeepSeek/Qwen自动降级）
2. `core/intelligence/account_intelligence_center.py` — 客户情报中心
3. `core/intelligence/network_expansion.py` — 网络扩张引擎（5种扩张方向）
4. `core/trade_graph/visualization.py` — 贸易图谱可视化（纯展示层）
5. `core/business_execution/execution_center.py` — 业务执行中心（开发信/Outlook草稿）
6. `core/business_execution/__init__.py`

### 修改模块（3个文件）
1. `core/memory/db.py` — 扩展情报中心表、网络扩张表、执行记录表
2. `core/system.py` — 集成新模块入口
3. `core/webui/app.py` — 新增API路由

### 删除的旧文件（2个）
- `core/intelligence/account.py` → 功能合并到 account_intelligence.py
- `core/intelligence/ai_gateway.py` → 被 ai_router.py 替代

## 安装步骤

### 1. 备份原文件
```bash
cp core/memory/db.py core/memory/db.py.bak
cp core/system.py core/system.py.bak
cp core/webui/app.py core/webui/app.py.bak
```

### 2. 复制新文件
```bash
# 新建目录
cp -r core/intelligence/ai_router.py your_project/core/intelligence/
cp -r core/intelligence/account_intelligence_center.py your_project/core/intelligence/
cp -r core/intelligence/network_expansion.py your_project/core/intelligence/
cp -r core/trade_graph/visualization.py your_project/core/trade_graph/
cp -r core/business_execution/ your_project/core/

# 修改文件（直接覆盖）
cp core/memory/db.py your_project/core/memory/
cp core/system.py your_project/core/
cp core/webui/app.py your_project/core/webui/
```

### 3. 删除旧文件
```bash
rm your_project/core/intelligence/account.py
rm your_project/core/intelligence/ai_gateway.py
```

### 4. 安装依赖（如需）
```bash
pip install openai  # AI Router 需要
```

### 5. 配置环境变量（AI Router）
```bash
export OPENAI_API_KEY="your-key"
export DEEPSEEK_API_KEY="your-key"
export QWEN_API_KEY="your-key"
```

### 6. 重启服务
```bash
python run_webui.py
```

## 新增API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/intelligence/<norm>` | GET | 获取客户完整情报档案 |
| `/api/intelligence` | GET | 列表查询情报档案 |
| `/api/intelligence/<norm>/process` | POST | 手动触发情报处理 |
| `/api/network/expand` | POST | 触发网络扩张 |
| `/api/graph/network` | GET | 获取网络图谱数据 |
| `/api/graph/path` | GET | 路径分析 |
| `/api/graph/evidence/<norm>` | GET | 贸易证据链 |
| `/api/execution/qualify/<norm>` | GET | 检查开发资格 |
| `/api/execution/dev-letter` | POST | 生成开发信草稿 |
| `/api/execution/mark-sent` | POST | 标记已发送 |
| `/api/execution/pipeline` | GET | 获取执行管道 |
| `/api/info-gain/<task_id>` | GET | 查询信息增益日志 |

## 架构变更

```
第一采集链（冻结）
    ↓
客户情报中心（补全、验证、评分、网络扩张）
    ↓
贸易图谱（关系展示、路径分析）
    ↓
业务执行中心（开发信、Outlook草稿、状态追踪）
```

## 关键规则

1. **第一采集链冻结**：不修改任何第一链代码
2. **禁止自动发送邮件**：只生成Outlook草稿链接，用户手动点击发送
3. **AI Router统一调用**：所有AI判断先输出自然语言，再转结构化
4. **信息增益停止**：连续3轮无新增客户/供应商/贸易边才停止网络扩张
5. **开发资格门槛**：客户真实存在 + 有贸易证据 + 信息完整度>=50% + 联系人存在 + 邮箱验证通过
