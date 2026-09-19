-- ============================================================
-- Aviation Security Platform — Database Schema (v0.1)
-- Target: SQLite (MVP runtime) — written Postgres-compatible
-- for straightforward migration later.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------- TENANCY ----------
CREATE TABLE airlines (
    airline_id      TEXT PRIMARY KEY,          -- e.g. 'AAW'
    name            TEXT NOT NULL,
    icao_code       TEXT,
    iata_code       TEXT,
    country         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Each airline can have multiple versions of its security manual over time.
-- Only one is 'active' per airline at any moment.
CREATE TABLE manual_versions (
    manual_version_id TEXT PRIMARY KEY,
    airline_id         TEXT NOT NULL REFERENCES airlines(airline_id),
    version_label      TEXT NOT NULL,           -- e.g. 'AAWSM Rev01 2021-10-01'
    source_document    TEXT,                    -- filename/reference, not full text
    is_active          INTEGER NOT NULL DEFAULT 0,
    effective_date     TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- USERS / RBAC ----------
CREATE TABLE users (
    user_id                 TEXT PRIMARY KEY,
    airline_id               TEXT NOT NULL REFERENCES airlines(airline_id),
    full_name                TEXT NOT NULL,
    role                      TEXT NOT NULL CHECK (role IN (
                                'SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR',
                                'SUPERINTENDENT','CSO','PLATFORM_ADMIN')),
    badge_id                 TEXT,
    certification_expiry     TEXT,               -- ISO date; NULL = not certified
    background_check_status  TEXT CHECK (background_check_status IN
                                ('PENDING','CLEARED','REJECTED')) DEFAULT 'PENDING',
    active                    INTEGER NOT NULL DEFAULT 1,
    password_hash             TEXT NOT NULL,
    created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- FLIGHTS ----------
CREATE TABLE flights (
    flight_id        TEXT PRIMARY KEY,
    airline_id         TEXT NOT NULL REFERENCES airlines(airline_id),
    flight_number     TEXT NOT NULL,
    aircraft_reg      TEXT NOT NULL,
    aircraft_type     TEXT NOT NULL,             -- drives checklist template selection
    departure_airport TEXT,
    destination       TEXT,
    scheduled_departure TEXT,
    gate              TEXT,
    threat_level      TEXT NOT NULL CHECK (threat_level IN ('GREEN','AMBER','RED'))
                        DEFAULT 'GREEN',
    security_status   TEXT NOT NULL CHECK (security_status IN
                        ('PENDING','IN_PROGRESS','BLOCKED','CLEARED','DEPARTED','EMERGENCY'))
                        DEFAULT 'PENDING',
    manual_version_id TEXT NOT NULL REFERENCES manual_versions(manual_version_id),
    created_by         TEXT REFERENCES users(user_id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- CHECKLIST TEMPLATES (versioned, per airline) ----------
CREATE TABLE checklist_templates (
    template_id       TEXT PRIMARY KEY,
    airline_id          TEXT NOT NULL REFERENCES airlines(airline_id),
    manual_version_id  TEXT NOT NULL REFERENCES manual_versions(manual_version_id),
    code                TEXT NOT NULL,            -- 'CL-01', 'CL-02', ...
    name                TEXT NOT NULL,
    applies_to_stage    TEXT NOT NULL,            -- workflow stage code
    aircraft_type_filter TEXT,                     -- NULL = applies to all
    items_json          TEXT NOT NULL,            -- JSON array of {code,label,role_required}
    min_signatures       INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE checklist_instances (
    instance_id      TEXT PRIMARY KEY,
    flight_id         TEXT NOT NULL REFERENCES flights(flight_id),
    template_id       TEXT NOT NULL REFERENCES checklist_templates(template_id),
    status             TEXT NOT NULL CHECK (status IN
                         ('PENDING','IN_PROGRESS','PASSED','FAILED')) DEFAULT 'PENDING',
    results_json        TEXT,                      -- JSON: item_code -> {result, note, photo_ref}
    started_at           TEXT,
    completed_at         TEXT,
    lat                   REAL,
    lng                   REAL,
    gps_accuracy_m        REAL,
    captured_at            TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE checklist_signatures (
    signature_id     TEXT PRIMARY KEY,
    instance_id       TEXT NOT NULL REFERENCES checklist_instances(instance_id),
    user_id            TEXT NOT NULL REFERENCES users(user_id),
    role_at_signing    TEXT NOT NULL,
    signed_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- WORKFLOW ENGINE ----------
CREATE TABLE workflow_stages (
    stage_id         TEXT PRIMARY KEY,
    flight_id          TEXT NOT NULL REFERENCES flights(flight_id),
    stage_code          TEXT NOT NULL,            -- AIRCRAFT_SECURITY_CHECK, BAGGAGE_RECON, ...
    sequence_order       INTEGER NOT NULL,
    status                 TEXT NOT NULL CHECK (status IN
                            ('PENDING','IN_PROGRESS','PASSED','FAILED','BLOCKED','SKIPPED'))
                            DEFAULT 'PENDING',
    blocked_reason          TEXT,
    started_at               TEXT,
    completed_at             TEXT,
    created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(flight_id, stage_code)
);

-- ---------- DOMAIN-SPECIFIC TABLES ----------
CREATE TABLE baggage_records (
    record_id       TEXT PRIMARY KEY,
    flight_id         TEXT NOT NULL REFERENCES flights(flight_id),
    total_hold_bags    INTEGER DEFAULT 0,
    reconciled_bags     INTEGER DEFAULT 0,
    unaccompanied_bags   INTEGER DEFAULT 0,
    mismatch_count        INTEGER DEFAULT 0,
    screened_pct            REAL DEFAULT 0,
    recorded_by              TEXT REFERENCES users(user_id),
    lat REAL, lng REAL, captured_at TEXT,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE catering_records (
    record_id       TEXT PRIMARY KEY,
    flight_id         TEXT NOT NULL REFERENCES flights(flight_id),
    truck_id           TEXT,
    seal_number          TEXT,
    seal_status            TEXT CHECK (seal_status IN ('INTACT','BROKEN','MISSING')),
    manual_inspection_done INTEGER NOT NULL DEFAULT 0,
    checked_by               TEXT REFERENCES users(user_id),
    lat REAL, lng REAL, captured_at TEXT,
    created_at                   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE cargo_records (
    record_id         TEXT PRIMARY KEY,
    flight_id           TEXT NOT NULL REFERENCES flights(flight_id),
    awb_number            TEXT,
    consignor_status        TEXT CHECK (consignor_status IN
                             ('KNOWN','REGULATED_AGENT','UNKNOWN')),
    screening_done            INTEGER NOT NULL DEFAULT 0,
    screening_method            TEXT,
    accepted                      INTEGER NOT NULL DEFAULT 0,
    recorded_by                    TEXT REFERENCES users(user_id),
    created_at                       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE aircraft_seals (
    seal_id           TEXT PRIMARY KEY,
    flight_id           TEXT REFERENCES flights(flight_id),
    aircraft_reg          TEXT NOT NULL,
    seal_number              TEXT NOT NULL,
    location_code               TEXT,             -- e.g. door/hatch id from manual decal ref
    status                         TEXT CHECK (status IN ('INTACT','BROKEN','MISSING'))
                                    DEFAULT 'INTACT',
    verified_by                      TEXT REFERENCES users(user_id),
    verified_at                        TEXT,
    created_at                           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- INCIDENTS & EMERGENCY ----------
CREATE TABLE security_incidents (
    incident_id       TEXT PRIMARY KEY,
    flight_id           TEXT REFERENCES flights(flight_id),
    airline_id            TEXT NOT NULL REFERENCES airlines(airline_id),
    incident_type            TEXT NOT NULL,        -- SUSPECT_ITEM, SEAL_BROKEN, ACCESS_BREACH...
    severity                    TEXT NOT NULL CHECK (severity IN
                                 ('MINOR','MAJOR','CRITICAL')),
    description                    TEXT NOT NULL,
    status                            TEXT NOT NULL CHECK (status IN ('OPEN','UNDER_REVIEW','CLOSED'))
                                       DEFAULT 'OPEN',
    reported_by                         TEXT REFERENCES users(user_id),
    closed_by                             TEXT REFERENCES users(user_id),
    close_reason                            TEXT,
    lat REAL, lng REAL, captured_at TEXT,
    created_at                                 TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at                                    TEXT
);

CREATE TABLE emergency_events (
    event_id          TEXT PRIMARY KEY,
    flight_id            TEXT REFERENCES flights(flight_id),
    airline_id              TEXT NOT NULL REFERENCES airlines(airline_id),
    event_type                 TEXT NOT NULL,      -- BOMB_THREAT, SUSPECT_ITEM, UNLAWFUL_INTERFERENCE
    status                        TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')) DEFAULT 'OPEN',
    opened_by                        TEXT REFERENCES users(user_id),
    closed_by                          TEXT REFERENCES users(user_id),
    notes                                 TEXT,
    created_at                              TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at                                 TEXT
);

-- ---------- SECURITY DECLARATION / CLEARANCE ----------
CREATE TABLE security_declarations (
    declaration_id      TEXT PRIMARY KEY,
    flight_id              TEXT NOT NULL REFERENCES flights(flight_id) UNIQUE,
    declared_by                TEXT NOT NULL REFERENCES users(user_id),
    declaration_text              TEXT,
    signed_at                        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- RULES ENGINE (data-driven, per manual_version) ----------
CREATE TABLE security_rules (
    rule_id             TEXT PRIMARY KEY,          -- 'BR-01', 'BR-02', ...
    manual_version_id      TEXT NOT NULL REFERENCES manual_versions(manual_version_id),
    description                TEXT NOT NULL,
    rule_type                     TEXT NOT NULL,    -- maps to a Python evaluator key
    parameters_json                  TEXT,          -- e.g. {"required_pct": {"RED":50}}
    overridable                        INTEGER NOT NULL DEFAULT 0,
    overridable_roles                     TEXT,      -- CSV of roles allowed to override
    active                                   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE rule_overrides (
    override_id      TEXT PRIMARY KEY,
    flight_id           TEXT NOT NULL REFERENCES flights(flight_id),
    rule_id                TEXT NOT NULL REFERENCES security_rules(rule_id),
    overridden_by              TEXT NOT NULL REFERENCES users(user_id),
    reason                        TEXT NOT NULL,
    evidence_url                    TEXT,     -- required in app layer when rule_id='BR-06' (Waled decision #3)
    linked_incident_id                 TEXT REFERENCES security_incidents(incident_id),
    created_at                          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- AUDIT TRAIL (append-only) ----------
CREATE TABLE audit_log (
    audit_id          TEXT PRIMARY KEY,
    airline_id           TEXT NOT NULL REFERENCES airlines(airline_id),
    entity_type             TEXT NOT NULL,          -- 'flight','checklist_instance','incident',...
    entity_id                  TEXT NOT NULL,
    action                        TEXT NOT NULL,      -- 'CREATE','UPDATE','STAGE_TRANSITION','OVERRIDE'
    actor_user_id                    TEXT REFERENCES users(user_id),
    before_json                         TEXT,
    after_json                             TEXT,
    device_id                                 TEXT,
    created_at                                   TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Audit log is treated as append-only at application layer (no UPDATE/DELETE routes exposed).

-- ---------- OFFLINE SYNC ----------
CREATE TABLE sync_log (
    sync_id            TEXT PRIMARY KEY,
    device_id             TEXT NOT NULL,
    user_id                  TEXT REFERENCES users(user_id),
    entity_type                 TEXT NOT NULL,
    entity_id                      TEXT NOT NULL,
    client_timestamp                   TEXT NOT NULL,  -- captured offline, may be earlier than server time
    server_received_at                    TEXT NOT NULL DEFAULT (datetime('now')),
    conflict_resolution                      TEXT,       -- NULL / 'SERVER_WON' / 'CLIENT_WON' / 'MERGED'
    payload_json                                TEXT NOT NULL
);

-- ---------- PROHIBITED ITEMS (admin-editable reference data) ----------
CREATE TABLE prohibited_items (
    item_id         TEXT PRIMARY KEY,
    airline_id         TEXT NOT NULL REFERENCES airlines(airline_id),
    category              TEXT NOT NULL,           -- FIREARMS, EDGED, BLUNT, EXPLOSIVE, CHEMICAL, LAGS...
    name                     TEXT NOT NULL,
    notes                       TEXT,
    source_reference               TEXT,            -- 'AAWSM Appendix F' / 'ICAO Annex 17'
    active                            INTEGER NOT NULL DEFAULT 1
);

-- ---------- INDEXES ----------
CREATE INDEX idx_flights_status ON flights(security_status);
CREATE INDEX idx_flights_airline ON flights(airline_id);
CREATE INDEX idx_stages_flight ON workflow_stages(flight_id);
CREATE INDEX idx_incidents_flight ON security_incidents(flight_id, status);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_rules_manualversion ON security_rules(manual_version_id, active);
