# Multi-Agent-claw

Multi-Agent Claw 是一个基于 FastAPI + SQLite + OpenAI-compatible LLM 的多代理任务执行原型。
当前已经具备这些核心能力：

- 任务接入与分析
- 基于 LangGraph 内核的任务运行编排与审批恢复
- 实时事件流与 WebSocket 推送
- 真实 LLM 调用、工具调用与本地 Sandbox 执行

当前形态是 API 服务，不是前端页面应用。

## 当前进度

当前项目已经跑通基础原型闭环，但还没有达到最初设计中的完整 SwarmOS 目标。

已完成：

- 任务接入、任务分析、任务运行编排
- LangGraph `thread_id + interrupt/resume + SQLite checkpoint` 主链路
- 审批暂停与审批恢复
- REST API 与 WebSocket 事件流
- 真实 LLM 调用、工具调用、本地 Sandbox
- SQLite 持久化、事件记录、基础观测落库

仍有关键差距：

- 还没有 subgraph / fork-join 级并行编排
- 还没有完整的 Context Builder / Session Engine
- 还没有 Result Aggregator / Outbound Message 主链路
- 还没有 Docker / MCP / Undo 级工具安全体系
- 还没有 Memory / Skill 主链路
- 还没有前端 UI 和多渠道 Adapter

完整任务清单见 [TODO.md](./TODO.md)。

## 项目结构

```text
src/
├── application/   # FastAPI API、WebSocket、事件总线
├── llm/           # 模型配置与 OpenAI-compatible client
├── runtime/       # 节点执行器、调度器、worker loop
├── services/      # Task Intake / Analyzer / Orchestrator / UoW
├── shared/        # 公共 schema 和 enum
├── storage/       # SQLite 和 repository/DAO
└── tools/         # Tool Registry 与 Sandbox Executor
sql/
└── 001_init.sql   # 初始化数据库 schema
```

## 环境要求

- Python 3.10+
- 一个 OpenAI-compatible 模型服务
- 推荐直接使用本地 LM Studio

## 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置环境变量

仓库根目录已经提供：

- `.env.example`：示例模板
- `.env`：当前本地开发配置

如果你使用 LM Studio，并且模型服务起在 `http://127.0.0.1:1234`，可以参考下面这组配置：

```env
SWARM_DB_PATH=/home/exian/project/Multi-Agent-claw/data/swarm.sqlite3
SWARM_CHECKPOINT_DB_PATH=/home/exian/project/Multi-Agent-claw/data/swarm.checkpoints.sqlite3
SWARM_WORKSPACE_ROOT=/home/exian/project/Multi-Agent-claw

SWARM_LLM_BASE_URL=http://127.0.0.1:1234/v1
SWARM_LLM_MODEL=gemma-4-31b-it
SWARM_LLM_API_KEY=lmstudio

SWARM_LLM_SUPPORTS_TOOLS=true
SWARM_LLM_TEMPERATURE=0.2
SWARM_LLM_MAX_TOKENS=1400
SWARM_LLM_TIMEOUT_SECONDS=90
SWARM_LLM_MAX_TOOL_ROUNDS=6

SWARM_MAX_READ_CHARS=12000
SWARM_BROWSER_TIMEOUT_SECONDS=15
SWARM_SHELL_TIMEOUT_SECONDS=60
SWARM_SHELL_NETWORK_ENABLED=false
```

说明：

- `SWARM_LLM_BASE_URL` 要带 `/v1`
- `SWARM_LLM_API_KEY` 对 LM Studio 通常填任意非空值即可
- 数据库会在首次启动时自动初始化
- `SWARM_CHECKPOINT_DB_PATH` 不填时会默认派生为主库同目录下的 `*.checkpoints.sqlite3`

## 启动服务

```bash
uvicorn --env-file .env src.application.api.main:app --reload
```

如果你想固定 host/port：

```bash
uvicorn --env-file .env src.application.api.main:app --host 127.0.0.1 --port 8000 --reload
```

启动入口在 `src/application/api/main.py`。

## 运行验证

### 1. 健康检查

```bash
curl http://127.0.0.1:8000/healthz
```

### 2. 发起一个任务

```bash
curl -X POST http://127.0.0.1:8000/api/v1/gateway/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "demo",
    "channel": "cli",
    "content": "开始任务，分析仓库结构并输出总结"
  }'
```

正常情况下会返回：

- `session`
- `result`
- `task`
- `run`
- 在高风险任务下可能还有 `approval`

### 3. 处理审批

如果返回里包含 `approval.approval_id`，可以这样批准：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/approvals/<approval_id>/resolve \
  -H 'Content-Type: application/json' \
  -d '{
    "decision": "approve",
    "decided_by": "demo",
    "edited_actions": []
  }'
```

## 常用接口

- `GET /healthz`
- `POST /api/v1/gateway/messages`
- `GET /api/v1/runs/{task_run_id}/events`
- `GET /api/v1/runs/{task_run_id}/snapshot`
- `GET /api/v1/runs/{task_run_id}/approvals`
- `POST /api/v1/approvals/{approval_id}/resolve`
- `WS /api/v1/ws/runs/{task_run_id}`

## 运行机制说明

- 数据库存储使用 SQLite
- 首次启动会自动执行 `sql/001_init.sql`
- LangGraph checkpoint 默认持久化到独立的 SQLite 文件
- 如果没有配置模型，runtime 会退回 deterministic fallback executor
- 如果任务涉及写文件或执行命令，系统可能先进入审批状态
- 审批恢复优先走 LangGraph `resume`，服务重启后也可以基于 SQLite checkpoint 继续恢复
- 当前 Sandbox 是本地 subprocess 方案，不是容器级隔离

## 已知边界

- 当前没有前端 UI，主要通过 REST/WebSocket 使用
- 当前没有正式的 migration 框架
- 当前 `shell.exec` 仍然属于单机本地执行能力，适合开发环境
- 较大的本地模型在 agent 场景下可能响应较慢

## 开发路线

建议优先顺序：

1. LangGraph Subgraph / Fork-Join
2. Context Builder
3. LLM Analyzer + Planner
4. Result Aggregator + Outbound Message
5. Docker Sandbox + MCP
6. Memory / Skill
7. UI Projection + Web UI
8. Observability / Audit

详细拆解见 [TODO.md](./TODO.md)。
