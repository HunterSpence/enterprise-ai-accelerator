-- PolicyGuard V2 — Database Schema
-- Runs once on first postgres container start

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- AI System Registry
CREATE TABLE IF NOT EXISTS ai_systems (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    description     TEXT,
    system_type     TEXT NOT NULL,   -- 'llm', 'classifier', 'recommendation', etc.
    risk_tier       TEXT,            -- 'unacceptable', 'high', 'limited', 'minimal'
    owner_team      TEXT,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- Compliance Scans
CREATE TABLE IF NOT EXISTS scans (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    system_id       UUID REFERENCES ai_systems(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending, running, complete, failed
    frameworks      TEXT[] NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    overall_score   NUMERIC(5,2),
    critical_count  INT DEFAULT 0,
    high_count      INT DEFAULT 0,
    report_path     TEXT,
    result          JSONB DEFAULT '{}'
);

-- Individual Findings
CREATE TABLE IF NOT EXISTS findings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id         UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    framework       TEXT NOT NULL,
    control_id      TEXT NOT NULL,
    severity        TEXT NOT NULL,   -- critical, high, medium, low
    title           TEXT NOT NULL,
    description     TEXT,
    remediation     TEXT,
    estimated_hours INT,
    cross_frameworks TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- AI Incidents
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    system_id       UUID REFERENCES ai_systems(id) ON DELETE SET NULL,
    severity        TEXT NOT NULL,   -- P0, P1, P2, P3
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'open',  -- open, investigating, resolved, closed
    article_62_required  BOOLEAN DEFAULT FALSE,
    notification_deadline TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'
);

-- Audit Log (append-only for tamper evidence)
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    actor           TEXT,
    resource_type   TEXT,
    resource_id     TEXT,
    details         JSONB DEFAULT '{}',
    event_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_started_at ON scans(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_at ON audit_log(event_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
