-- ContextGraph Postgres Schema
-- Append-only event log + temporal graph projection

-- Events table (append-only source of truth)
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    actor_type TEXT,
    actor_id TEXT,
    payload JSONB NOT NULL,
    prev_hash TEXT,
    hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_tenant ON events(tenant_id);

-- Decision records (materialized from events)
CREATE TABLE IF NOT EXISTS decision_records (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    trace_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    actor_type TEXT,
    actor_id TEXT,
    outcome TEXT NOT NULL,
    outcome_reason TEXT,
    subject_entities JSONB DEFAULT '[]',
    evidence JSONB DEFAULT '[]',
    policies JSONB DEFAULT '[]',
    approvals JSONB DEFAULT '[]',
    actions JSONB DEFAULT '[]',
    precedent_refs JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_run_id ON decision_records(run_id);
CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decision_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_outcome ON decision_records(outcome);
CREATE INDEX IF NOT EXISTS idx_decisions_tenant ON decision_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_decisions_entities ON decision_records USING GIN(subject_entities);

-- Graph nodes (projected from events)
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    namespace TEXT,
    external_id TEXT,
    properties JSONB DEFAULT '{}',
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    tenant_id TEXT DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_external ON nodes(namespace, external_id);
CREATE INDEX IF NOT EXISTS idx_nodes_properties ON nodes USING GIN(properties);

-- Graph edges (temporal, with validity period)
CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    from_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    to_node_id TEXT NOT NULL REFERENCES nodes(node_id),
    properties JSONB DEFAULT '{}',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    tenant_id TEXT DEFAULT 'default'
);

CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_valid ON edges(valid_from, valid_to);

-- Tool classification (user-defined read vs write)
CREATE TABLE IF NOT EXISTS tool_classifications (
    tool_name TEXT PRIMARY KEY,
    classification TEXT NOT NULL CHECK (classification IN ('read', 'write', 'both')),
    tenant_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
