-- Phase 2: Anomaly Detection - Database Schema
-- Migration 001: Create anomaly_events and baselines tables

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Anomaly Events
-- ============================================================
CREATE TABLE anomaly_events (
    anomaly_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         INT NOT NULL DEFAULT 1,
    timestamp       TIMESTAMPTZ NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Entity
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(255) NOT NULL,
    namespace       VARCHAR(255),
    cluster         VARCHAR(255),

    -- Detection
    detector        VARCHAR(50) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    signal          VARCHAR(100) NOT NULL,
    severity        VARCHAR(20) NOT NULL,
    score           DECIMAL(5,4),
    confidence      DECIMAL(5,4),

    -- Values
    current_value   DOUBLE PRECISION,
    baseline_mean   DOUBLE PRECISION,
    baseline_std    DOUBLE PRECISION,
    z_score         DOUBLE PRECISION,

    -- Context
    rule_id         VARCHAR(100),
    time_window     VARCHAR(20),
    baseline_window VARCHAR(20),

    -- Status
    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    -- Metadata (JSONB for flexibility)
    metadata        JSONB,

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_anomaly_entity ON anomaly_events(entity_type, entity_id);
CREATE INDEX idx_anomaly_timestamp ON anomaly_events(timestamp);
CREATE INDEX idx_anomaly_severity ON anomaly_events(severity);
CREATE INDEX idx_anomaly_category ON anomaly_events(category);
CREATE INDEX idx_anomaly_status ON anomaly_events(status);
CREATE INDEX idx_anomaly_detector ON anomaly_events(detector);

-- ============================================================
-- Baselines (per entity/metric)
-- ============================================================
CREATE TABLE baselines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(255) NOT NULL,
    metric          VARCHAR(100) NOT NULL,
    namespace       VARCHAR(255),

    -- Baseline statistics
    mean            DOUBLE PRECISION NOT NULL,
    std             DOUBLE PRECISION NOT NULL,
    min_val         DOUBLE PRECISION,
    max_val         DOUBLE PRECISION,
    sample_count    INT NOT NULL DEFAULT 0,

    -- Window
    time_window     VARCHAR(20) NOT NULL DEFAULT '7d',

    -- Timestamps
    calculated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(entity_type, entity_id, metric, namespace)
);

CREATE INDEX idx_baseline_entity ON baselines(entity_type, entity_id);
CREATE INDEX idx_baseline_metric ON baselines(metric);

-- ============================================================
-- Detection Rules (persisted for custom rules via API)
-- ============================================================
CREATE TABLE detection_rules (
    rule_id         VARCHAR(100) PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    metric          VARCHAR(100) NOT NULL,
    entity_scope    VARCHAR(50) NOT NULL,
    condition_json  JSONB NOT NULL,
    duration        VARCHAR(20) DEFAULT '0m',
    severity        VARCHAR(20) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    is_builtin      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
