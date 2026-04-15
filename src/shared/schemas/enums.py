from __future__ import annotations

from enum import Enum


class SwarmStrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class SessionStatus(SwarmStrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class SessionKind(SwarmStrEnum):
    WEB = "web"
    CLI = "cli"
    DM = "dm"
    GROUP = "group"
    THREAD = "thread"


class MessageDirection(SwarmStrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


class MessageRole(SwarmStrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class TaskStatus(SwarmStrEnum):
    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRunStatus(SwarmStrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(SwarmStrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ApprovalStatus(SwarmStrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class EventLevel(SwarmStrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class VisibilityScope(SwarmStrEnum):
    SYSTEM = "system"
    DEBUG = "debug"
    OPERATOR = "operator"
    USER = "user"


class Priority(SwarmStrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Complexity(SwarmStrEnum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class RiskLevel(SwarmStrEnum):
    READ = "read"
    MUTABLE = "mutable"
    DESTRUCTIVE = "destructive"


class TriggerKind(SwarmStrEnum):
    NEW = "new"
    RESUME = "resume"
    RETRY = "retry"
    MANUAL_REPLAN = "manual_replan"


class NodeType(SwarmStrEnum):
    PLANNER = "planner"
    WORKER = "worker"
    APPROVAL = "approval"
    SUMMARY = "summary"
    REDUCER = "reducer"
    SUBGRAPH = "subgraph"


class ApprovalKind(SwarmStrEnum):
    MUTABLE_TOOL = "mutable_tool"
    DESTRUCTIVE_TOOL = "destructive_tool"
    NETWORK_ACCESS = "network_access"
    EXTERNAL_ACCOUNT = "external_account"
    PLAN_CONFIRMATION = "plan_confirmation"


class ArtifactType(SwarmStrEnum):
    FILE = "file"
    TEXT = "text"
    REPORT = "report"
    IMAGE = "image"
    AUDIO = "audio"
    JSON = "json"
    PLAN = "plan"
    DIFF = "diff"
    SUMMARY = "summary"
    DATASET = "dataset"


class ArtifactDirection(SwarmStrEnum):
    INPUT = "input"
    INTERMEDIATE = "intermediate"
    OUTPUT = "output"


class ToolCategory(SwarmStrEnum):
    BUILTIN = "builtin"
    MCP = "mcp"
    SANDBOXED = "sandboxed"


class ToolCallStatus(SwarmStrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class LLMCallStatus(SwarmStrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ActorType(SwarmStrEnum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
    TOOL = "tool"


class MemoryScope(SwarmStrEnum):
    SESSION = "session"
    TASK = "task"
    WORKSPACE = "workspace"
    GLOBAL = "global"


class MemorySourceType(SwarmStrEnum):
    MESSAGE = "message"
    TASK_SUMMARY = "task_summary"
    ARTIFACT = "artifact"
    MANUAL_NOTE = "manual_note"
    SKILL = "skill"


class SkillCandidateStatus(SwarmStrEnum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class SkillSourceScope(SwarmStrEnum):
    WORKSPACE = "workspace"
    PROJECT_AGENTS = "project_agents"
    USER_AGENTS = "user_agents"
    USER_SHARED = "user_shared"
    BUILTIN = "builtin"


class TaskEventType(SwarmStrEnum):
    SESSION_MESSAGE_RECEIVED = "session.message_received"
    SESSION_MESSAGE_SENT = "session.message_sent"
    SESSION_COMPACTED = "session.compacted"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_CLARIFICATION_REQUESTED = "task.clarification_requested"
    TASK_CLARIFICATION_RESOLVED = "task.clarification_resolved"
    TASK_APPROVAL_REQUESTED = "task.approval_requested"
    TASK_APPROVAL_RESOLVED = "task.approval_resolved"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    RUN_CREATED = "run.created"
    RUN_PLAN_STARTED = "run.plan_started"
    RUN_PLAN_READY = "run.plan_ready"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_BLOCKED = "run.blocked"
    RUN_SUMMARIZING = "run.summarizing"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_CHECKPOINT_CREATED = "run.checkpoint_created"
    NODE_CREATED = "node.created"
    NODE_READY = "node.ready"
    NODE_STARTED = "node.started"
    NODE_PROGRESS = "node.progress"
    NODE_AWAITING_APPROVAL = "node.awaiting_approval"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_RETRIED = "node.retried"
    NODE_SKIPPED = "node.skipped"
    TOOL_PREVIEW_READY = "tool.preview_ready"
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    ARTIFACT_CREATED = "artifact.created"
    AUDIT_RECORDED = "audit.recorded"


class WebSocketMessageType(SwarmStrEnum):
    EVENT = "event"
    SNAPSHOT = "snapshot"
    ACK = "ack"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
