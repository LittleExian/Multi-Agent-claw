# Multi-Agent Claw TODO

这份清单用于把“设计目标”和“当前实现”之间的差距，整理成可执行的开发任务。

当前判断：

- 项目已经完成基础原型闭环：任务接入、任务分析、运行编排、审批恢复、事件流、真实 LLM、工具调用、本地 Sandbox。
- 项目当前更接近“Phase 1 已完成，Phase 2 起步”的状态。
- 项目离最初 SwarmOS 目标还有几块关键缺口：durable LangGraph checkpoint 与并行编排、Context/Memory/Skill、产品化 Gateway/UI、Docker/MCP/Undo 级工具安全体系。

## 已完成基础能力

- SQLite 持久化层、事件表、观测表、记忆表 schema
- Repository / DAO / Unit of Work
- Task Intake / Task Analyzer / Orchestrator 主链路
- FastAPI REST API 与 WebSocket 事件流
- 进程内实时事件总线
- Runtime worker loop 与最小调度器
- 最小 LangGraph 运行内核：`task_run_id == thread_id`、`interrupt/resume`、进程内 checkpointer
- OpenAI-compatible LLM client
- Tool Registry
- 本地 subprocess Sandbox Executor
- 审批请求、审批恢复、任务继续执行

## P0: 必须优先补齐

### 1. 把 LangGraph 内核补到 durable checkpoint / subgraph 级别

目标：

- 让任务运行真正具备 checkpoint、interrupt、resume、subgraph、故障恢复能力。

待做事项：

- 用 SQLite/Postgres saver 替换当前 `InMemorySaver`
- 把当前 LangGraph runtime 从单节点循环图升级为更明确的 graph/subgraph 结构
- 为并行节点补 fork-join / subgraph 编排
- 把 checkpoint 元数据与 `task_runs.last_checkpoint_at`、业务事件对齐
- 支持服务重启后恢复未完成 run

完成标准：

- 任务在进程重启后可以从 checkpoint 恢复
- 审批暂停后可通过 resume 正确续跑
- 已完成节点不会在恢复时重复执行

### 2. 补真正的 Context Builder

目标：

- 为分析、规划、执行提供统一上下文，而不是靠每个模块各自拼 prompt。

待做事项：

- 新增 `SessionService / ContextAssembler / ContextPruner / CompactionService`
- 按场景构建 `planning`、`execution`、`summary` 三种上下文视图
- 实现 token budget 分配
- 对大工具结果做 pruning
- 对旧会话做 compaction，并把摘要落库

完成标准：

- Analyzer / Planner / Runtime 都通过统一 Context API 获取上下文
- 长会话不会直接把完整 transcript 塞进 prompt

### 3. 把 Task Analyzer / Planner 升级为“规则 + LLM”

目标：

- 让任务分析和任务规划真正接近设计目标，而不是主要依赖关键词启发式。

待做事项：

- 在 `TaskAnalyzer` 中引入 LLM 结构化提取
- 为 `TaskSpec` 增加更稳定的 schema repair / fallback 流程
- 单独拆出 `Planner / Graph Builder`
- 让 Planner 独立生成 `ExecutionPlan`
- 控制 DAG 深度、节点数、并行度

完成标准：

- 复杂任务可稳定生成多节点计划
- 简单任务可退化为单节点
- Planner 和 Analyzer 解耦

### 4. 补 Result Aggregator 与最终回复输出

目标：

- 让系统不仅“任务状态完成”，还能给用户结构化、可信的最终结果。

待做事项：

- 新增 `ResultAggregator`
- 汇总 node outputs、tool outputs、artifacts
- 生成最终总结和结果摘要
- 生成 assistant outbound message 并落库
- 推送 `session.message_sent`

完成标准：

- 任务完成后能在 API 和消息流中拿到稳定 final answer
- 完成消息与 run summary、artifacts 对齐

## P1: 高优先级产品化能力

### 5. 升级 Tool Registry / Sandbox 安全模型

目标：

- 把当前本地 subprocess 工具体系升级到更接近设计目标的安全级别。

待做事项：

- 引入 Docker sandbox profile
- 支持只读、任务目录读写、带网络三档 profile
- 为 mutable / destructive 工具补 preview 流程
- 增加 undo log / rollback metadata
- 细化工具级审批，不再只停留在节点级审批

完成标准：

- 高风险命令不会直接在宿主进程裸跑
- 可变更工具具备 preview 或 undo 线索

### 6. 接 MCP 工具体系

目标：

- 让工具层不只支持 builtin，而是兼容更丰富的本地 agent tool 生态。

待做事项：

- 新增 MCP client manager
- 支持 stdio JSON-RPC
- 从 MCP manifest 生成 ToolDescriptor
- 把 MCP 工具并入 ToolCatalog / ToolRouter

完成标准：

- 可以从外部 MCP server 动态发现并调用工具

### 7. 补 Model Routing 与 Agent Profile

目标：

- 按阶段和角色切换模型，控制成本和质量。

待做事项：

- 新增 `ModelRouter`
- 为 analyzer / planner / worker / writer 配不同 profile
- 引入 tool turn 与 summary turn 的参数策略
- 为结构化输出失败增加二次修复逻辑

完成标准：

- 不同 phase/role 可以独立配置模型
- JSON/schema 输出失败可以自动修复一次

### 8. 补 Memory / Skill 主链路

目标：

- 把“一次性执行”升级为“可积累系统”。

待做事项：

- 新增 `MemoryService`
- 任务完成后写入 summary memory
- 从历史任务中召回相关 memory
- 生成 `SkillCandidate`
- 设计 Skill loader 与目录优先级

完成标准：

- 新任务可以利用历史摘要
- 完成任务后能沉淀 skill candidate

### 9. 补 Progress Projection / UI Projection

目标：

- 让事件流真正转成用户可读视图，而不只是原始 event list。

待做事项：

- 新增 timeline projection
- 新增 graph projection
- 新增 summary projection
- 把 run snapshot 扩展成更完整的任务投影

完成标准：

- API 能返回任务时间线、任务图、当前摘要

### 10. 补 Observability / Audit 真正使用链路

目标：

- 从“有表”升级到“可观测、可审计、可分析”。

待做事项：

- 把审批、任务取消、关键变更写入 audit log
- 增加基础 metrics 汇总
- 增加 token / cost 统计
- 增加大响应体裁剪和敏感信息脱敏

完成标准：

- 能按 run 查看 llm/tool/sandbox/audit 全链路信息
- 能计算首条进度耗时、任务成功率、工具失败率

## P2: 产品入口与生态

### 11. 补 Adapter Layer 与产品化 Gateway

目标：

- 接近设计里的“多入口统一消息网关”。

待做事项：

- 新增 CLI adapter
- 新增 WebChat adapter
- 新增 Telegram adapter
- 预留 Discord adapter
- 增加 AuthGuard / allowlist / token 校验
- 增加 outbound fanout 和 delivery retry

完成标准：

- 不同入口共用统一 Inbound/Outbound envelope
- Gateway 重启后能恢复事件推送能力

### 12. 补前端 Web UI

目标：

- 把现有 API 服务补成可直接使用的产品界面。

待做事项：

- 新建 WebChat 界面
- 任务列表页
- 任务详情页
- DAG / timeline / approval 卡片
- WebSocket 实时订阅

完成标准：

- 不依赖 curl，也能创建、查看、批准、回放任务

### 13. 补 Outbound Message / 通知体系

目标：

- 系统不仅能处理任务，也能主动把结果和进度“发回去”。

待做事项：

- assistant message 落库
- approval request 通知消息
- task completed / failed 通知消息
- 不同渠道的消息格式转换

完成标准：

- 用户在入口侧能看到自然语言进度和结果，不只靠查询 API

## P3: 工程完善

### 14. 测试体系

待做事项：

- 单元测试
- API 集成测试
- runtime 端到端测试
- approval / resume / failure / cancel 回归测试
- fake OpenAI-compatible provider 测试夹具

完成标准：

- 主链路具备可重复自动验证能力

### 15. 包管理与工程化

待做事项：

- 增加 `pyproject.toml`
- 增加格式化 / lint / type check 配置
- 增加 dev / prod 配置分层
- 增加 migration 框架

完成标准：

- 新环境一键安装
- schema 演进可管理

### 16. 部署与运行方式

待做事项：

- systemd/launchd 启动脚本
- Docker Compose 本地开发环境
- 日志目录与轮转策略
- 多进程/多实例事件总线替换方案

完成标准：

- 本机常驻运行和简单部署都可控

## 推荐推进顺序

1. LangGraph Orchestrator
2. Context Builder
3. LLM Analyzer + Planner
4. Result Aggregator + Outbound Message
5. Docker Sandbox + MCP
6. Memory / Skill
7. UI Projection + Web UI
8. Observability / Audit
9. Adapter / Gateway 产品化
10. 测试与工程化收尾

## 当前阶段判断

- 当前：可运行原型
- 下一阶段目标：进入“可恢复、多角色、可产品化演示”的 Beta 原型
