-- Phase 4: Root Cause Analysis (RCA) & Incident Lifecycle
-- Migration 003: Upgrade incidents table, create timeline and notification history tables

-- 1. Add RCA & Lifecycle tracking columns to incidents
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS root_causes JSONB DEFAULT '[]'::jsonb;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS blast_radius JSONB DEFAULT '{}'::jsonb;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS evidence JSONB DEFAULT '[]'::jsonb;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS investigating_at TIMESTAMPTZ;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS mitigated_at TIMESTAMPTZ;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS mttr_seconds DOUBLE PRECISION;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS mttd_seconds DOUBLE PRECISION;

-- 2. Incident Timeline Events (audit log and chronological investigation)
CREATE TABLE IF NOT EXISTS incident_timeline_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      VARCHAR(50) NOT NULL, -- state_change, rca_computed, anomaly_added, evidence_collected, comment, notification_sent
    actor           VARCHAR(100) NOT NULL DEFAULT 'system',
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_timeline_incident ON incident_timeline_events(incident_id, timestamp ASC);

-- 3. Notification History (record alerts dispatched to Slack, Telegram, etc.)
CREATE TABLE IF NOT EXISTS notification_history (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel         VARCHAR(50) NOT NULL, -- slack, telegram, alertmanager, webhook
    status          VARCHAR(20) NOT NULL DEFAULT 'sent', -- sent, failed, mocked
    payload         JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_notification_incident ON notification_history(incident_id, timestamp DESC);
