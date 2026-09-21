-- Phase 3: Correlation Engine & Incident Intelligence
-- Migration 002: Create Service Graph, Correlation Groups, Incidents, and Deployment Events

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. Service Dependency Graph
-- ============================================================
CREATE TABLE IF NOT EXISTS service_graph_nodes (
    node_id         VARCHAR(255) PRIMARY KEY,
    node_type       VARCHAR(50) NOT NULL DEFAULT 'service',    -- service, database, queue, external
    namespace       VARCHAR(255),
    cluster         VARCHAR(255),
    metadata        JSONB DEFAULT '{}'::jsonb,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_graph_edges (
    edge_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       VARCHAR(255) NOT NULL REFERENCES service_graph_nodes(node_id) ON DELETE CASCADE,
    target_id       VARCHAR(255) NOT NULL REFERENCES service_graph_nodes(node_id) ON DELETE CASCADE,
    dependency_type VARCHAR(50) NOT NULL DEFAULT 'http',      -- http, grpc, database, queue, external
    metadata        JSONB DEFAULT '{}'::jsonb,
    discovered_by   VARCHAR(50) NOT NULL DEFAULT 'otel_traces',-- otel_traces, k8s_metadata, manual
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_id, target_id, dependency_type)
);

CREATE INDEX IF NOT EXISTS idx_edge_source ON service_graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edge_target ON service_graph_edges(target_id);

-- ============================================================
-- 2. Correlation Groups
-- ============================================================
CREATE TABLE IF NOT EXISTS correlation_groups (
    correlation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL DEFAULT 'active', -- active, closed, merged
    correlation_type    VARCHAR(50) NOT NULL DEFAULT 'hybrid', -- temporal, topology, deployment, hybrid
    entity_count        INT NOT NULL DEFAULT 0,
    severity_max        VARCHAR(20) NOT NULL DEFAULT 'warning',
    topology_context    JSONB,
    deployment_context  JSONB,
    metadata            JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS correlation_anomalies (
    correlation_id  UUID NOT NULL REFERENCES correlation_groups(correlation_id) ON DELETE CASCADE,
    anomaly_id      UUID NOT NULL REFERENCES anomaly_events(anomaly_id) ON DELETE CASCADE,
    PRIMARY KEY (correlation_id, anomaly_id)
);

CREATE INDEX IF NOT EXISTS idx_correlation_status ON correlation_groups(status);
CREATE INDEX IF NOT EXISTS idx_correlation_updated ON correlation_groups(updated_at DESC);

-- ============================================================
-- 3. Incidents
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS incident_id_seq START WITH 1001;

CREATE TABLE IF NOT EXISTS incidents (
    incident_id         VARCHAR(20) PRIMARY KEY,               -- INC-1001, INC-1002
    title               TEXT NOT NULL,
    severity            VARCHAR(20) NOT NULL DEFAULT 'warning',-- critical, high, warning, info
    status              VARCHAR(20) NOT NULL DEFAULT 'OPEN',   -- OPEN, ACKNOWLEDGED, RESOLVED, CLOSED
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,

    correlation_id      UUID REFERENCES correlation_groups(correlation_id) ON DELETE SET NULL,
    anomaly_count       INT NOT NULL DEFAULT 0,
    entity_count        INT NOT NULL DEFAULT 0,
    impacted_entities   JSONB DEFAULT '[]'::jsonb,
    namespaces          JSONB DEFAULT '[]'::jsonb,
    cluster             VARCHAR(255),

    topology_context    JSONB,
    deployment_context  JSONB,
    metadata            JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS incident_anomalies (
    incident_id     VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    anomaly_id      UUID NOT NULL REFERENCES anomaly_events(anomaly_id) ON DELETE CASCADE,
    PRIMARY KEY (incident_id, anomaly_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incident_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incident_created ON incidents(created_at DESC);

-- ============================================================
-- 4. Deployment Events
-- ============================================================
CREATE TABLE IF NOT EXISTS deployment_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      VARCHAR(50) NOT NULL DEFAULT 'deployment_rollout',
    entity_type     VARCHAR(50) NOT NULL DEFAULT 'deployment',
    entity_id       VARCHAR(255) NOT NULL,
    namespace       VARCHAR(255),
    cluster         VARCHAR(255),
    details         JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deployment_entity ON deployment_events(entity_id, namespace);
CREATE INDEX IF NOT EXISTS idx_deployment_timestamp ON deployment_events(timestamp DESC);
