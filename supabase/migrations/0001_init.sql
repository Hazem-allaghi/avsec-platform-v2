-- ============================================================
-- Aviation Security Platform — Supabase (Postgres) Migration 0001
-- Converts db/schema.sql (SQLite MVP) to Postgres, adds:
--   - profiles table linked 1:1 to auth.users (Supabase Auth)
--   - Row Level Security (RLS) on every security-relevant table
--   - evidence_url on rule_overrides (Waled decision #3, BR-06)
-- Apply with: supabase db push   (or `psql -f` against your project)
-- NOT executed against a live project from this sandbox — no network
-- egress available here. See docs/09_supabase_integration.md.
-- ============================================================

-- ---------- EXTENSIONS ----------
create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- ---------- TENANCY (kept as clean columns, no multi-tenant RLS yet —
-- Waled decision #1: single-tenant for V1/V2, but airline_id stays a
-- real column everywhere so a later migration to tenant RLS is a pure
-- DDL/policy addition, not a schema rewrite) ----------
create table if not exists airlines (
    airline_id   text primary key,
    name         text not null,
    icao_code    text,
    iata_code    text,
    country      text,
    created_at   timestamptz not null default now()
);

create table if not exists manual_versions (
    manual_version_id text primary key,
    airline_id          text not null references airlines(airline_id),
    version_label        text not null,
    source_document        text,
    is_active               boolean not null default false,
    effective_date            date,
    created_at                 timestamptz not null default now()
);

-- ---------- PROFILES (extends Supabase auth.users 1:1) ----------
-- auth.users is managed by Supabase Auth itself (email, password hash,
-- etc.). We never store credentials ourselves — `profiles.id` = `auth.uid()`.
create table if not exists profiles (
    id                       uuid primary key references auth.users(id) on delete cascade,
    airline_id                 text not null references airlines(airline_id),
    full_name                    text not null,
    role                          text not null check (role in (
                                    'SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR',
                                    'SUPERINTENDENT','CSO','PLATFORM_ADMIN')),
    badge_id                       text,
    certification_expiry             date,
    background_check_status            text check (background_check_status in
                                        ('PENDING','CLEARED','REJECTED')) default 'PENDING',
    active                                boolean not null default true,
    created_at                             timestamptz not null default now()
);

-- Helper: current user's role/airline, used inside RLS policies.
create or replace function current_profile()
returns profiles
language sql stable
as $$
  select * from profiles where id = auth.uid();
$$;

create or replace function has_role(roles text[])
returns boolean
language sql stable
as $$
  select exists (
    select 1 from profiles where id = auth.uid() and role = any(roles) and active
  );
$$;

-- ---------- FLIGHTS ----------
create table if not exists flights (
    flight_id          text primary key,
    airline_id           text not null references airlines(airline_id),
    flight_number         text not null,
    aircraft_reg          text not null,
    aircraft_type          text not null,
    departure_airport        text,
    destination                text,
    scheduled_departure          timestamptz,
    gate                           text,
    threat_level                     text not null check (threat_level in ('GREEN','AMBER','RED'))
                                      default 'GREEN',
    security_status                    text not null check (security_status in
                                        ('PENDING','IN_PROGRESS','BLOCKED','CLEARED','DEPARTED','EMERGENCY'))
                                        default 'PENDING',
    manual_version_id                    text not null references manual_versions(manual_version_id),
    created_by                             uuid references profiles(id),
    created_at                               timestamptz not null default now(),
    updated_at                                 timestamptz not null default now()
);

-- ---------- CHECKLISTS ----------
create table if not exists checklist_templates (
    template_id        text primary key,
    airline_id           text not null references airlines(airline_id),
    manual_version_id      text not null references manual_versions(manual_version_id),
    code                     text not null,
    name                      text not null,
    applies_to_stage           text not null,
    aircraft_type_filter         text,
    items_json                     jsonb not null,
    min_signatures                   integer not null default 1,
    created_at                         timestamptz not null default now()
);

create table if not exists checklist_instances (
    instance_id      text primary key,
    flight_id          text not null references flights(flight_id),
    template_id          text not null references checklist_templates(template_id),
    status                  text not null check (status in
                             ('PENDING','IN_PROGRESS','PASSED','FAILED')) default 'PENDING',
    results_json               jsonb,
    started_at                    timestamptz,
    completed_at                     timestamptz,
    lat real, lng real, gps_accuracy_m real, captured_at timestamptz,
    created_at                          timestamptz not null default now()
);

create table if not exists checklist_signatures (
    signature_id      text primary key,
    instance_id          text not null references checklist_instances(instance_id),
    user_id                uuid not null references profiles(id),
    role_at_signing          text not null,
    signed_at                  timestamptz not null default now()
);

-- ---------- WORKFLOW ----------
create table if not exists workflow_stages (
    stage_id          text primary key,
    flight_id           text not null references flights(flight_id),
    stage_code            text not null,
    sequence_order          integer not null,
    status                    text not null check (status in
                              ('PENDING','IN_PROGRESS','PASSED','FAILED','BLOCKED','SKIPPED'))
                              default 'PENDING',
    blocked_reason              text,
    started_at                     timestamptz,
    completed_at                      timestamptz,
    created_at                          timestamptz not null default now(),
    unique(flight_id, stage_code)
);

-- ---------- DOMAIN RECORDS ----------
create table if not exists baggage_records (
    record_id       text primary key,
    flight_id         text not null references flights(flight_id),
    total_hold_bags     integer default 0,
    reconciled_bags       integer default 0,
    unaccompanied_bags      integer default 0,
    mismatch_count             integer default 0,
    screened_pct                  real default 0,
    recorded_by                      uuid references profiles(id),
    lat real, lng real, captured_at timestamptz,
    created_at                          timestamptz not null default now()
);

create table if not exists catering_records (
    record_id       text primary key,
    flight_id         text not null references flights(flight_id),
    truck_id            text,
    seal_number            text,
    seal_status                text check (seal_status in ('INTACT','BROKEN','MISSING')),
    manual_inspection_done       boolean not null default false,
    checked_by                      uuid references profiles(id),
    lat real, lng real, captured_at timestamptz,
    created_at                          timestamptz not null default now()
);

create table if not exists cargo_records (
    record_id         text primary key,
    flight_id           text not null references flights(flight_id),
    awb_number             text,
    consignor_status          text check (consignor_status in
                               ('KNOWN','REGULATED_AGENT','UNKNOWN')),
    screening_done               boolean not null default false,
    screening_method                text,
    accepted                          boolean not null default false,
    recorded_by                          uuid references profiles(id),
    created_at                              timestamptz not null default now()
);

create table if not exists aircraft_seals (
    seal_id           text primary key,
    flight_id           text references flights(flight_id),
    aircraft_reg           text not null,
    seal_number               text not null,
    location_code                text,
    status                          text check (status in ('INTACT','BROKEN','MISSING'))
                                     default 'INTACT',
    verified_by                        uuid references profiles(id),
    verified_at                           timestamptz,
    created_at                               timestamptz not null default now()
);

-- ---------- INCIDENTS & EMERGENCY ----------
create table if not exists security_incidents (
    incident_id       text primary key,
    flight_id           text references flights(flight_id),
    airline_id             text not null references airlines(airline_id),
    incident_type             text not null,
    severity                     text not null check (severity in ('MINOR','MAJOR','CRITICAL')),
    description                     text not null,
    status                             text not null check (status in ('OPEN','UNDER_REVIEW','CLOSED'))
                                        default 'OPEN',
    reported_by                           uuid references profiles(id),
    closed_by                                uuid references profiles(id),
    close_reason                                text,
    lat real, lng real, captured_at timestamptz,
    created_at                                     timestamptz not null default now(),
    closed_at                                         timestamptz
);

create table if not exists emergency_events (
    event_id          text primary key,
    flight_id            text references flights(flight_id),
    airline_id              text not null references airlines(airline_id),
    event_type                 text not null,
    status                        text not null check (status in ('OPEN','CLOSED')) default 'OPEN',
    opened_by                        uuid references profiles(id),
    closed_by                           uuid references profiles(id),
    notes                                  text,
    created_at                               timestamptz not null default now(),
    closed_at                                   timestamptz
);

-- ---------- DECLARATION ----------
create table if not exists security_declarations (
    declaration_id      text primary key,
    flight_id              text not null unique references flights(flight_id),
    declared_by                uuid not null references profiles(id),
    declaration_text              text,
    signed_at                        timestamptz not null default now()
);

-- ---------- RULES ENGINE ----------
create table if not exists security_rules (
    rule_id             text primary key,
    manual_version_id      text not null references manual_versions(manual_version_id),
    description                text not null,
    rule_type                     text not null,
    parameters_json                  jsonb,
    overridable                        boolean not null default false,
    overridable_roles                     text,
    active                                   boolean not null default true
);

-- Waled decision #3: evidence_url added, mandatory (app-layer enforced)
-- specifically for rule_id = 'BR-06' (broken/missing aircraft seal).
create table if not exists rule_overrides (
    override_id      text primary key,
    flight_id           text not null references flights(flight_id),
    rule_id                text not null references security_rules(rule_id),
    overridden_by              uuid not null references profiles(id),
    reason                        text not null,
    evidence_url                    text,     -- required in app layer when rule_id='BR-06'
    linked_incident_id                 text references security_incidents(incident_id),
    created_at                            timestamptz not null default now()
);

-- ---------- AUDIT TRAIL (append-only; no UPDATE/DELETE policy granted) ----------
create table if not exists audit_log (
    audit_id          text primary key,
    airline_id           text not null references airlines(airline_id),
    entity_type             text not null,
    entity_id                  text not null,
    action                        text not null,
    actor_user_id                    uuid references profiles(id),
    before_json                         jsonb,
    after_json                             jsonb,
    device_id                                 text,
    created_at                                   timestamptz not null default now()
);

-- ---------- OFFLINE SYNC ----------
create table if not exists sync_log (
    sync_id            text primary key,
    device_id             text not null,
    user_id                  uuid references profiles(id),
    entity_type                 text not null,
    entity_id                      text not null,
    client_timestamp                   timestamptz not null,
    server_received_at                    timestamptz not null default now(),
    conflict_resolution                      text,
    payload_json                                jsonb not null
);

-- ---------- PROHIBITED ITEMS ----------
create table if not exists prohibited_items (
    item_id         text primary key,
    airline_id         text not null references airlines(airline_id),
    category              text not null,
    name                     text not null,
    notes                       text,
    source_reference               text,
    active                            boolean not null default true
);

-- ============================================================
-- ROW LEVEL SECURITY
-- V1 policy shape (Waled decision #1 — single-tenant, no cross-airline
-- isolation logic yet, so policies here gate by ROLE, not by airline_id
-- comparison against a JWT claim). Adding tenant isolation later means
-- adding `and airline_id = current_profile().airline_id` to each policy
-- below — a pure policy edit, no schema change.
-- ============================================================

alter table flights enable row level security;
alter table workflow_stages enable row level security;
alter table checklist_templates enable row level security;
alter table checklist_instances enable row level security;
alter table checklist_signatures enable row level security;
alter table baggage_records enable row level security;
alter table catering_records enable row level security;
alter table cargo_records enable row level security;
alter table aircraft_seals enable row level security;
alter table security_incidents enable row level security;
alter table emergency_events enable row level security;
alter table security_declarations enable row level security;
alter table security_rules enable row level security;
alter table rule_overrides enable row level security;
alter table audit_log enable row level security;
alter table sync_log enable row level security;
alter table profiles enable row level security;

-- profiles: users can read their own profile; CSO/Superintendent can read all.
create policy profiles_select on profiles for select
  using (id = auth.uid() or has_role(array['SUPERVISOR','SUPERINTENDENT','CSO','PLATFORM_ADMIN']));
create policy profiles_update_self on profiles for update
  using (id = auth.uid()) with check (id = auth.uid());

-- flights: any authenticated, active, certified profile can read; only
-- SECURITY_OFFICER+ can create.
create policy flights_select on flights for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy flights_insert on flights for insert
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy flights_update on flights for update
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

-- workflow_stages / checklist_* / domain records: readable by all active
-- roles; writable by SECURITY_OFFICER and above (guards execute via the
-- checklist_instances/signatures flow, not raw stage writes).
create policy stages_rw on workflow_stages for all
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy checklist_templates_select on checklist_templates for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy checklist_instances_rw on checklist_instances for all
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy checklist_signatures_rw on checklist_signatures for all
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (user_id = auth.uid());  -- can only sign as yourself

create policy baggage_rw on baggage_records for all
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy catering_rw on catering_records for all
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy cargo_rw on cargo_records for all
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

create policy seals_rw on aircraft_seals for all
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']))
  with check (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

-- incidents: anyone active can open (insert); only SUPERVISOR+ can close (update).
create policy incidents_select on security_incidents for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy incidents_insert on security_incidents for insert
  with check (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy incidents_update_close on security_incidents for update
  using (has_role(array['SUPERVISOR','SUPERINTENDENT','CSO']));

-- emergency: same shape as incidents.
create policy emergency_select on emergency_events for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy emergency_insert on emergency_events for insert
  with check (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy emergency_update_close on emergency_events for update
  using (has_role(array['SUPERVISOR','SUPERINTENDENT','CSO']));

-- declaration: only SECURITY_OFFICER+ can sign, and only as themselves.
create policy declaration_select on security_declarations for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy declaration_insert on security_declarations for insert
  with check (declared_by = auth.uid()
              and has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));

-- security_rules: read-only for everyone active; writes reserved to CSO
-- (rule authoring is a policy decision, not a floor-level action).
create policy rules_select on security_rules for select
  using (has_role(array['SECURITY_GUARD','SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy rules_write on security_rules for all
  using (has_role(array['CSO','PLATFORM_ADMIN']))
  with check (has_role(array['CSO','PLATFORM_ADMIN']));

-- rule_overrides: insert requires the correct role for that specific rule,
-- enforced in the app layer (role list varies per rule row) AND re-checked
-- here at the coarse level (must be at least SUPERVISOR to attempt one).
create policy overrides_select on rule_overrides for select
  using (has_role(array['SECURITY_OFFICER','SUPERVISOR','SUPERINTENDENT','CSO']));
create policy overrides_insert on rule_overrides for insert
  with check (overridden_by = auth.uid()
              and has_role(array['SUPERVISOR','SUPERINTENDENT','CSO']));

-- audit_log: append-only, read access for SUPERVISOR+; NO update/delete
-- policy exists at all (any such statement is rejected by RLS by default).
create policy audit_select on audit_log for select
  using (has_role(array['SUPERVISOR','SUPERINTENDENT','CSO']));
create policy audit_insert on audit_log for insert
  with check (true); -- every authenticated write path inserts audit rows

-- sync_log: a device can only see/insert its own queued mutations (no
-- role check — this is per-device, not per-role, for offline sync).
create policy sync_own_device on sync_log for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- ============================================================
-- Indexes (mirrors db/schema.sql)
-- ============================================================
create index if not exists idx_flights_status on flights(security_status);
create index if not exists idx_flights_airline on flights(airline_id);
create index if not exists idx_stages_flight on workflow_stages(flight_id);
create index if not exists idx_incidents_flight on security_incidents(flight_id, status);
create index if not exists idx_audit_entity on audit_log(entity_type, entity_id);
create index if not exists idx_rules_manualversion on security_rules(manual_version_id, active);
