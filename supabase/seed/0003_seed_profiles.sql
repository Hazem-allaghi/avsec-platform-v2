-- ============================================================
-- Seed Part 2 — profiles (linked to REAL auth.users created via
-- Supabase Dashboard). Run AFTER 0002_seed_core.sql.
--
-- ⚠️ ASSUMPTION (confirm or fix before/after running):
-- Mapped in the order Waled sent the UUIDs back, matching the role
-- table proposed earlier (CSO → Supervisor → Officer → Engineer → Guard).
-- If the real assignment differs, just swap which UUID sits on which
-- row below and re-run (safe: ON CONFLICT DO UPDATE).
-- ============================================================

insert into profiles (id, airline_id, full_name, role, badge_id, certification_expiry, background_check_status, active)
values
('1e31f6fe-7b30-4375-875d-b1d738800ac8', 'AAW', 'CSO (officer1@aaw.demo)',              'CSO',              'B-0001', '2027-01-01', 'CLEARED', true),
('d6e337c9-7537-4639-81fa-5b3b9cfdd67b', 'AAW', 'Supervisor (officer2@aaw.demo)',       'SUPERVISOR',       'B-0002', '2027-01-01', 'CLEARED', true),
('11e568c7-75ba-4a2f-a128-dacdd90f5d8f', 'AAW', 'Security Officer (officer3@aaw.demo)', 'SECURITY_OFFICER', 'B-0003', '2027-01-01', 'CLEARED', true),
('9118293b-e584-4f07-b57e-17676daf84ff', 'AAW', 'Ground Engineer (officer4@aaw.demo)',  'SECURITY_OFFICER', 'B-0004', '2027-01-01', 'CLEARED', true),
('7d4350ee-5c98-442c-a1a7-597ce3211563', 'AAW', 'Security Guard (officer5@aaw.demo)',   'SECURITY_GUARD',   'B-0005', '2027-01-01', 'CLEARED', true)
on conflict (id) do update set
    full_name = excluded.full_name,
    role = excluded.role,
    badge_id = excluded.badge_id,
    certification_expiry = excluded.certification_expiry,
    background_check_status = excluded.background_check_status,
    active = excluded.active;

-- Quick sanity check after running — should return 5 rows with correct roles:
-- select id, full_name, role from profiles order by role;
