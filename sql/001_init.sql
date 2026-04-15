PRAGMA foreign_keys = ON;

-- Core sessions and transcript tables.
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_kind TEXT NOT NULL CHECK (
        session_kind IN ('web', 'cli', 'dm', 'group', 'thread')
    ),
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'archived', 'deleted')
    ),
    source_ref TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_user_channel
    ON sessions(user_id, channel);

CREATE INDEX idx_sessions_last_message_at
    ON sessions(last_message_at);

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (
        direction IN ('inbound', 'outbound', 'system')
    ),
    role TEXT NOT NULL CHECK (
        role IN ('user', 'assistant', 'tool', 'system')
    ),
    channel_message_id TEXT,
    reply_to_message_id TEXT REFERENCES messages(message_id),
    content_text TEXT,
    content_json TEXT NOT NULL DEFAULT '{}',
    token_count INTEGER,
    task_id TEXT,
    task_run_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    received_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_messages_session_created
    ON messages(session_id, created_at);

CREATE INDEX idx_messages_task_run
    ON messages(task_run_id, created_at);

CREATE INDEX idx_messages_reply_to
    ON messages(reply_to_message_id);

CREATE TABLE message_attachments (
    attachment_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    storage_uri TEXT NOT NULL,
    extracted_text_uri TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_message_attachments_message
    ON message_attachments(message_id);

CREATE TABLE session_compactions (
    compaction_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    decisions_json TEXT NOT NULL DEFAULT '[]',
    source_message_from TEXT,
    source_message_to TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_session_compactions_session
    ON session_compactions(session_id, created_at);

-- Task lifecycle tables.
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    source_message_id TEXT REFERENCES messages(message_id),
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    task_kind TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL CHECK (
        status IN (
            'draft', 'needs_clarification', 'awaiting_approval', 'queued',
            'planning', 'running', 'blocked', 'summarizing',
            'completed', 'failed', 'cancelled'
        )
    ),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (
        priority IN ('low', 'normal', 'high', 'urgent')
    ),
    complexity TEXT NOT NULL CHECK (
        complexity IN ('simple', 'moderate', 'complex')
    ),
    risk_level TEXT NOT NULL DEFAULT 'read' CHECK (
        risk_level IN ('read', 'mutable', 'destructive')
    ),
    current_run_id TEXT,
    latest_run_id TEXT,
    success_criteria_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    expected_outputs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX idx_tasks_session_created
    ON tasks(session_id, created_at);

CREATE INDEX idx_tasks_status
    ON tasks(status, updated_at);

CREATE TABLE task_runs (
    task_run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL UNIQUE,
    run_no INTEGER NOT NULL,
    trigger_kind TEXT NOT NULL CHECK (
        trigger_kind IN ('new', 'resume', 'retry', 'manual_replan')
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'queued', 'planning', 'running', 'paused',
            'blocked', 'summarizing', 'completed', 'failed', 'cancelled'
        )
    ),
    spec_json TEXT NOT NULL,
    plan_json TEXT,
    context_snapshot_json TEXT NOT NULL DEFAULT '{}',
    summary_text TEXT,
    error_json TEXT,
    queue_wait_ms INTEGER,
    approval_wait_ms INTEGER,
    checkpoint_backend TEXT,
    checkpoint_ref TEXT,
    last_checkpoint_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id, run_no)
);

CREATE INDEX idx_task_runs_task_created
    ON task_runs(task_id, created_at);

CREATE INDEX idx_task_runs_status
    ON task_runs(status, updated_at);

CREATE TABLE task_nodes (
    node_id TEXT PRIMARY KEY,
    task_run_id TEXT NOT NULL REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
    parent_node_id TEXT REFERENCES task_nodes(node_id),
    step_key TEXT NOT NULL,
    node_type TEXT NOT NULL CHECK (
        node_type IN ('planner', 'worker', 'approval', 'summary', 'reducer', 'subgraph')
    ),
    role TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'ready', 'running', 'awaiting_approval',
            'blocked', 'completed', 'failed', 'skipped', 'cancelled'
        )
    ),
    order_index INTEGER,
    depth INTEGER NOT NULL DEFAULT 0,
    approval_required INTEGER NOT NULL DEFAULT 0,
    inputs_json TEXT NOT NULL DEFAULT '[]',
    outputs_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    tools_hint_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX idx_task_nodes_run_order
    ON task_nodes(task_run_id, order_index);

CREATE INDEX idx_task_nodes_run_status
    ON task_nodes(task_run_id, status);

CREATE TABLE task_node_runs (
    node_run_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES task_nodes(node_id) ON DELETE CASCADE,
    task_run_id TEXT NOT NULL REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'failed', 'cancelled')
    ),
    model_profile TEXT,
    agent_role TEXT NOT NULL,
    input_context_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT,
    error_json TEXT,
    latency_ms INTEGER,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(node_id, attempt_no)
);

CREATE INDEX idx_task_node_runs_node
    ON task_node_runs(node_id, attempt_no);

CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    task_run_id TEXT NOT NULL REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
    node_id TEXT REFERENCES task_nodes(node_id),
    approval_kind TEXT NOT NULL CHECK (
        approval_kind IN (
            'mutable_tool', 'destructive_tool', 'network_access',
            'external_account', 'plan_confirmation'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'approved', 'rejected', 'edited', 'expired', 'cancelled')
    ),
    risk_level TEXT NOT NULL CHECK (
        risk_level IN ('read', 'mutable', 'destructive')
    ),
    title TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    preview_json TEXT NOT NULL DEFAULT '{}',
    requested_actions_json TEXT NOT NULL DEFAULT '[]',
    decision_json TEXT,
    requested_by TEXT NOT NULL,
    decided_by TEXT,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_approvals_run_status
    ON approvals(task_run_id, status, requested_at);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    node_id TEXT REFERENCES task_nodes(node_id) ON DELETE SET NULL,
    source_message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL CHECK (
        artifact_type IN (
            'file', 'text', 'report', 'image', 'audio', 'json',
            'plan', 'diff', 'summary', 'dataset'
        )
    ),
    direction TEXT NOT NULL CHECK (
        direction IN ('input', 'intermediate', 'output')
    ),
    title TEXT,
    mime_type TEXT,
    storage_uri TEXT NOT NULL,
    size_bytes INTEGER,
    sha256 TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_artifacts_task_run
    ON artifacts(task_run_id, created_at);

CREATE INDEX idx_artifacts_source_message
    ON artifacts(source_message_id);

-- Events and observability tables.
CREATE TABLE task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE CASCADE,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    node_id TEXT REFERENCES task_nodes(node_id),
    approval_id TEXT REFERENCES approvals(approval_id),
    trace_id TEXT,
    event_seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_level TEXT NOT NULL CHECK (
        event_level IN ('info', 'warn', 'error')
    ),
    visibility_scope TEXT NOT NULL CHECK (
        visibility_scope IN ('system', 'debug', 'operator', 'user')
    ),
    emitted_by TEXT NOT NULL,
    causation_event_id TEXT,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    persisted_at TEXT NOT NULL,
    UNIQUE(task_run_id, event_seq)
);

CREATE INDEX idx_task_events_run_seq
    ON task_events(task_run_id, event_seq);

CREATE INDEX idx_task_events_session_time
    ON task_events(session_id, occurred_at);

CREATE INDEX idx_task_events_type
    ON task_events(event_type, occurred_at);

CREATE TABLE llm_calls (
    llm_call_id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    node_id TEXT REFERENCES task_nodes(node_id) ON DELETE SET NULL,
    node_run_id TEXT REFERENCES task_node_runs(node_run_id) ON DELETE SET NULL,
    trace_id TEXT,
    phase TEXT NOT NULL,
    role TEXT,
    model_profile TEXT NOT NULL,
    provider TEXT NOT NULL,
    endpoint TEXT,
    supports_tools INTEGER NOT NULL DEFAULT 0,
    request_tokens INTEGER,
    response_tokens INTEGER,
    total_tokens INTEGER,
    cached_tokens INTEGER,
    cost_usd REAL,
    latency_ms INTEGER,
    status TEXT NOT NULL CHECK (
        status IN ('success', 'error', 'timeout', 'cancelled')
    ),
    request_summary_json TEXT NOT NULL DEFAULT '{}',
    response_summary_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX idx_llm_calls_run_phase
    ON llm_calls(task_run_id, phase, started_at);

CREATE INDEX idx_llm_calls_trace
    ON llm_calls(trace_id);

CREATE TABLE tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    node_id TEXT REFERENCES task_nodes(node_id) ON DELETE SET NULL,
    node_run_id TEXT REFERENCES task_node_runs(node_run_id) ON DELETE SET NULL,
    approval_id TEXT REFERENCES approvals(approval_id),
    trace_id TEXT,
    tool_name TEXT NOT NULL,
    tool_category TEXT NOT NULL CHECK (
        tool_category IN ('builtin', 'mcp', 'sandboxed')
    ),
    risk_level TEXT NOT NULL CHECK (
        risk_level IN ('read', 'mutable', 'destructive')
    ),
    preview_only INTEGER NOT NULL DEFAULT 0,
    server_name TEXT,
    arguments_json TEXT NOT NULL,
    result_summary_json TEXT,
    latency_ms INTEGER,
    status TEXT NOT NULL CHECK (
        status IN ('success', 'error', 'timeout', 'blocked', 'cancelled')
    ),
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX idx_tool_calls_run_tool
    ON tool_calls(task_run_id, tool_name, started_at);

CREATE INDEX idx_tool_calls_trace
    ON tool_calls(trace_id);

CREATE TABLE sandbox_runs (
    sandbox_run_id TEXT PRIMARY KEY,
    tool_call_id TEXT NOT NULL REFERENCES tool_calls(tool_call_id) ON DELETE CASCADE,
    profile_name TEXT NOT NULL,
    image_name TEXT,
    network_enabled INTEGER NOT NULL DEFAULT 0,
    mounts_json TEXT NOT NULL DEFAULT '[]',
    command_text TEXT,
    exit_code INTEGER,
    timed_out INTEGER NOT NULL DEFAULT 0,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX idx_sandbox_runs_tool_call
    ON sandbox_runs(tool_call_id);

CREATE TABLE run_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    task_run_id TEXT NOT NULL REFERENCES task_runs(task_run_id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT,
    saver_backend TEXT NOT NULL,
    saver_ref TEXT NOT NULL,
    state_digest TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_run_checkpoints_run_created
    ON run_checkpoints(task_run_id, created_at);

CREATE TABLE audit_log (
    audit_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    node_id TEXT REFERENCES task_nodes(node_id) ON DELETE SET NULL,
    trace_id TEXT,
    action_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (
        actor_type IN ('user', 'system', 'agent', 'tool')
    ),
    actor_id TEXT,
    summary_text TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_audit_log_run_created
    ON audit_log(task_run_id, created_at);

-- Memory and reuse tables.
CREATE TABLE memory_entries (
    memory_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
    task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
    task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    scope TEXT NOT NULL CHECK (
        scope IN ('session', 'task', 'workspace', 'global')
    ),
    source_type TEXT NOT NULL CHECK (
        source_type IN ('message', 'task_summary', 'artifact', 'manual_note', 'skill')
    ),
    title TEXT,
    content_text TEXT NOT NULL,
    summary_text TEXT,
    embedding_ref TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_memory_entries_scope_created
    ON memory_entries(scope, created_at);

CREATE INDEX idx_memory_entries_task
    ON memory_entries(task_id, created_at);

CREATE TABLE skill_candidates (
    skill_candidate_id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    source_task_run_id TEXT REFERENCES task_runs(task_run_id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    applicability_text TEXT,
    plan_template_json TEXT NOT NULL,
    tool_requirements_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (
        status IN ('draft', 'accepted', 'rejected', 'archived')
    ),
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_skill_candidates_status
    ON skill_candidates(status, created_at);

CREATE TABLE skill_catalog_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_scope TEXT NOT NULL CHECK (
        source_scope IN ('workspace', 'project_agents', 'user_agents', 'user_shared', 'builtin')
    ),
    version_text TEXT,
    sha256 TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    loaded_at TEXT NOT NULL
);

CREATE INDEX idx_skill_catalog_skill_name
    ON skill_catalog_snapshots(skill_name, loaded_at);
