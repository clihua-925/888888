# PSV Trade OS 9.4.0 LangGraph v1 升级 - 进度存档

## 一、项目基础信息

- 项目名：PSV Trade OS 9.4.0
- 当前工作目录：D:\chang\PSV_Trade_OS_9.4.0_Stage1b_FIX_v3
- venv 路径：D:\chang\venv
- Python 版本：3.12.10
- 环境变量：
  - LLM_BASE_URL=http://192.168.1.26:8081/v1
  - LLM_API_KEY=local-llama
  - LLM_MODEL=deepseek-r1-distill-llama-70b

## 二、冻结方案位置

- 文件名：LangGraph_v1_FreezePlan_v2.2.md（已上传公开仓库）
- 核心约束：
  - 五层架构、9 纯业务节点、Condition Edge 唯一路由
  - Shared State 16 字段（12 核心 + 4 envelope）
  - Runtime 依赖通过 contextvars 传递
  - DATABASE_COMMIT 唯一写入口
  - LangGraph 冻结在 1.2.11（langgraph==1.2.11, langgraph-checkpoint==4.1.1, langgraph-checkpoint-sqlite==3.1.1）
  - 旧脚本只参考不引用
  - 禁止修改业务层：business/**、state.py、conditions.py、recovery.py、runtime.py、scheduler.py、mission.py、decision.py、reasoning.py

## 三、当前进度台账

| 阶段 | 状态 |
|---|---|
| Stage 0 | PASS |
| Stage 1a | PASS |
| Stage 1b | HOLD（engine.py 队列死锁修复已完成，等待本机验证） |
| Stage 2-6 | 未启动 |

## 四、已完成的修复

1. requirements.txt 移除 langchain / langchain-openai
2. verify_install.py packages 字典改为 pip 包名 + importlib.metadata.version()
3. tests/test_acceptance.py generated_files 加入 upgrade_before_versions.txt 及 backup
4. upgrade_langgraph.ps1 / rollback_langgraph.ps1 使用完整 Python 路径 + Out-File -Encoding utf8
5. **engine.py 队列死锁修复**：run() 改为轮询 join + get_nowait（根因见下）
6. PROJECT_SOURCE_MANIFEST.txt 重建（File count: 57）

## 五、Stage 1b 根因确认

- Probe A 排除：LangGraph 1.2.11 + SqliteSaver 本身 1 秒正常退出
- Probe B 排除：spawn 子进程正常退出
- Probe C 实锤：engine.run() 先 join 后 get 导致 Windows 管道缓冲区死锁
  - 子进程 pickle 完整 TaskState（数百 KB）通过 result_queue.put 写入
  - QueueFeederThread 因超过 4KB 管道缓冲区阻塞
  - 父进程 join(1800) 等子进程退出 → 死锁
  - 修复：父进程在 join 等待期间并发 get_nowait() 排空队列

## 六、当前 ZIP

- 文件名：PSV_Trade_OS_9.4.0_Stage1b_FIX_v5_engine_queue_fix.zip
- SHA256：bd0ca1d2dd52cd1fe5d305bbdc2602f9e55861036652ce88e393217bf9804084
- 大小：145,269 字节
- 内容：57 个文件
- 变更文件：core/orchestration/engine.py、PROJECT_SOURCE_MANIFEST.txt

## 七、下一步要做什么

1. 解压 ZIP 到 D:\chang\
2. 只覆盖 core/orchestration/engine.py 和 PROJECT_SOURCE_MANIFEST.txt（不要整目录替换，否则会覆盖 .env）
3. 备份原 engine.py 到 D:\chang\engine.py.before_queue_fix
4. 跑 pytest：
   D:\chang\venv\Scripts\python.exe -m pytest tests/test_acceptance.py -v
   必须：23 passed
5. 跑 Runtime Gate（10-20 分钟，不按 Ctrl+C）：
   D:\chang\venv\Scripts\python.exe verify_install.py --runtime
   必须：RUNTIME_OK
6. 把输出回传给 Kimi，判定 Stage 1b PASS/FAIL

## 八、后续阶段预期

- Stage 2：Checkpoint 数据库验证（checkpoints 表 + writes 表行数 > 0）
- Stage 3：真实任务 E2E（trade_entities / trade_edges / evidence 三表有数据）
- Stage 4：Scheduler 恢复测试
- Stage 5：发布包整理（无瞬态文件 + Manifest 一致）
- Stage 6：冻结签署

每阶段独立验证 + 独立 ZIP + 独立台账 + 累积叠加。

## 九、新对话开场提示词

新对话请使用以下提示词：

---
你是资深 Python 工程师，接手 PSV Trade OS 9.4.0 LangGraph v1 升级项目。

## 资料位置

仓库链接：<仓库链接>

需要下载：
1. STAGE1B_HANDOFF.md（进度存档）
2. LangGraph_v1_FreezePlan_v2.2.md（冻结方案）
3. PSV_Trade_OS_9.4.0_Stage1b_FIX_v5_engine_queue_fix.zip（当前工作基线）

## 硬性约束

1. LangGraph 冻结在 1.2.11，禁止降级
2. 旧脚本只参考不引用（baseline 只读）
3. 严格串行，Stage N PASS 才能进 N+1
4. 每阶段 ZIP 必须累积（Stage N 包含 Stage 0 到 N 所有改动）
5. 只允许修改 engine.py（或方案明确允许的文件）
6. 禁止动业务层：business/**、state.py、conditions.py、recovery.py、runtime.py、scheduler.py、mission.py、decision.py、reasoning.py
7. 所有 PowerShell 命令用 D:\chang\venv\Scripts\python.exe

## 当前状态

Stage 1b HOLD，等待本机验证 engine.py 队列死锁修复。

## 你的第一件事

用户会先跑完本机验证，然后回传：
- pytest 输出
- verify_install.py --runtime 输出

你收到后：
1. 输出 Stage 1b 自审证据表
2. 判定 PASS/FAIL
3. PASS：生成 Stage 1b 累积 ZIP + SHA256 + 进度台账 + Stage 2 命令
4. FAIL：停留 Stage 1b 修复，不进入下一阶段
---

## 十、上传清单

请把以下三个文件上传到公开仓库：
1. STAGE1B_HANDOFF.md（本文档）
2. PSV_Trade_OS_9.4.0_Stage1b_FIX_v5_engine_queue_fix.zip
3. LangGraph_v1_FreezePlan_v2.2.md（已有）
