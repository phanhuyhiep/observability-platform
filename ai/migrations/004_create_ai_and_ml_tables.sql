-- Phase 5: AI Enhancement & Machine Learning
-- Migration 004: Create ML Model Registry, AI Incident Summaries, Recommendations, and Feedback tables

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. ML Model Registry
-- ============================================================
CREATE TABLE IF NOT EXISTS ml_model_registry (
    model_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           VARCHAR(255) NOT NULL,
    model_type          VARCHAR(50) NOT NULL,            -- isolation_forest, forecaster, dynamic_baseline
    version             VARCHAR(50) NOT NULL DEFAULT 'v1.0.0',
    features            JSONB DEFAULT '[]'::jsonb,
    hyperparameters     JSONB DEFAULT '{}'::jsonb,
    metrics             JSONB DEFAULT '{}'::jsonb,        -- contamination, train_score, val_score
    model_artifact      BYTEA,                           -- Serialized pickled model or weights
    status              VARCHAR(20) NOT NULL DEFAULT 'active', -- active, archived, training
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ml_models_entity ON ml_model_registry(entity_id, model_type, status);

-- ============================================================
-- 2. Incident AI Summaries
-- ============================================================
CREATE TABLE IF NOT EXISTS incident_ai_summaries (
    summary_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id             VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    provider                VARCHAR(50) NOT NULL,        -- gemini, openai, sre_expert
    model_name              VARCHAR(100) NOT NULL,
    summary_text            TEXT NOT NULL,
    root_cause_explanation  TEXT NOT NULL,
    suggested_actions       JSONB DEFAULT '[]'::jsonb,
    executive_overview      TEXT,
    tokens_used             INT DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(incident_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_ai_summaries_incident ON incident_ai_summaries(incident_id);

-- ============================================================
-- 3. AI Investigation Recommendations & Runbooks
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_investigation_recommendations (
    recommendation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id         VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    step_order          INT NOT NULL DEFAULT 1,
    action_title        VARCHAR(255) NOT NULL,
    command             TEXT,
    reasoning           TEXT,
    runbook_url         TEXT,
    metadata            JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_rec_incident ON ai_investigation_recommendations(incident_id, step_order);

-- ============================================================
-- 4. AI Feedback Loop
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_feedback (
    feedback_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id         VARCHAR(20) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    recommendation_id   UUID REFERENCES ai_investigation_recommendations(recommendation_id) ON DELETE SET NULL,
    rating              INT CHECK (rating >= 1 AND rating <= 5),
    helpful             BOOLEAN NOT NULL DEFAULT true,
    comments            TEXT,
    actor               VARCHAR(100) NOT NULL DEFAULT 'sre-engineer',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_feedback_incident ON ai_feedback(incident_id);
