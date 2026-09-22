-- Seed data for MVP demo (AAW as first tenant)

INSERT INTO airlines (airline_id, name, icao_code, iata_code, country)
VALUES ('AAW', 'Afriqiyah Airways', 'AAW', '8U', 'Libya');

INSERT INTO manual_versions (manual_version_id, airline_id, version_label, source_document, is_active, effective_date)
VALUES ('AAW-MAN-2021-R01', 'AAW', 'AAWSM Rev 01', 'AAW_Security_Manual_final_2021_2_.pdf', 1, '2021-10-01');

-- Users (password hashes are placeholders 'CHANGE_ME' -> real system must use bcrypt/argon2)
INSERT INTO users (user_id, airline_id, full_name, role, badge_id, certification_expiry, background_check_status, password_hash) VALUES
('u-cso',    'AAW', 'Salaheddin Enaami (CSO)', 'CSO',              'B-0001', '2027-01-01', 'CLEARED', 'CHANGE_ME'),
('u-sup1',   'AAW', 'Supervisor Demo',          'SUPERVISOR',       'B-0002', '2027-01-01', 'CLEARED', 'CHANGE_ME'),
('u-off1',   'AAW', 'Security Officer Demo',    'SECURITY_OFFICER', 'B-0003', '2027-01-01', 'CLEARED', 'CHANGE_ME'),
('u-guard1', 'AAW', 'Security Guard Demo',      'SECURITY_GUARD',   'B-0004', '2027-01-01', 'CLEARED', 'CHANGE_ME'),
('u-eng1',   'AAW', 'Ground Engineer Demo',     'SECURITY_OFFICER', 'B-0005', '2027-01-01', 'CLEARED', 'CHANGE_ME'),
('u-admin',  'AAW', 'Platform Admin',           'PLATFORM_ADMIN',   NULL,     NULL,          'CLEARED', 'CHANGE_ME');

-- Checklist templates (items_json summarised per 04_checklists.md)
INSERT INTO checklist_templates (template_id, airline_id, manual_version_id, code, name, applies_to_stage, aircraft_type_filter, items_json, min_signatures) VALUES
('tpl-cl01', 'AAW', 'AAW-MAN-2021-R01', 'CL-01', 'Aircraft Security Search', 'AIRCRAFT_SECURITY_CHECK', NULL,
 '[{"code":"flight_deck","label":"Flight Deck","role_required":"FLIGHT_CREW"},
   {"code":"fwd_entrance","label":"Forward Entrance & Coat Closet","role_required":"CABIN_CREW"},
   {"code":"fwd_galley","label":"Forward Galley(s)","role_required":"CABIN_CREW"},
   {"code":"fwd_toilet","label":"Forward Toilet(s)","role_required":"CABIN_CREW"},
   {"code":"main_cabin","label":"Main Cabin","role_required":"CABIN_CREW"},
   {"code":"rear_galley_toilet","label":"Rear Galley(s) & Toilet(s)","role_required":"CABIN_CREW"},
   {"code":"avionics_bay","label":"Avionics Bay","role_required":"GROUND_ENGINEER"},
   {"code":"cargo_holds","label":"Fwd/Aft Lower Cargo Hold","role_required":"GROUND_ENGINEER"},
   {"code":"gear_bays","label":"Landing Gear Bays","role_required":"GROUND_ENGINEER"},
   {"code":"inlets_outlets","label":"Inlets/Outlets/Fuel/Water/APU","role_required":"GROUND_ENGINEER"}]', 3),

('tpl-cl02', 'AAW', 'AAW-MAN-2021-R01', 'CL-02', 'Baggage Reconciliation', 'BAGGAGE_RECONCILIATION', NULL,
 '[{"code":"count_match","label":"Registered bags = reconciled bags"},
   {"code":"no_show_removed","label":"No-show passenger bags removed"},
   {"code":"unaccompanied_screened","label":"Unaccompanied bags screened & classified"},
   {"code":"crew_bags_matched","label":"Crew baggage matched & screened"}]', 1),

('tpl-cl03', 'AAW', 'AAW-MAN-2021-R01', 'CL-03', 'Catering Security', 'CATERING_SECURITY', NULL,
 '[{"code":"seal_match","label":"Truck seal number matches record"},
   {"code":"seal_intact","label":"Seal intact on arrival"},
   {"code":"manual_inspection","label":"Manual inspection performed (mandatory if seal broken)"},
   {"code":"receiver_signoff","label":"Onboard receiver sign-off"}]', 1),

('tpl-cl04', 'AAW', 'AAW-MAN-2021-R01', 'CL-04', 'Cargo/Mail Acceptance', 'CARGO_MAIL_SECURITY', NULL,
 '[{"code":"consignor_status","label":"Consignor status documented"},
   {"code":"screening_if_unknown","label":"Screening performed if Unknown"},
   {"code":"no_tamper_signs","label":"No visible tamper signs"}]', 1),

('tpl-cl05', 'AAW', 'AAW-MAN-2021-R01', 'CL-05', 'Aircraft Seal Verification', 'SEAL_VERIFICATION', NULL,
 '[{"code":"seal_numbers_match","label":"All seal numbers match issued record"},
   {"code":"no_missing_broken","label":"No missing or broken seal"}]', 1),

('tpl-cl06', 'AAW', 'AAW-MAN-2021-R01', 'CL-06', 'Security Declaration Pre-check', 'SECURITY_DECLARATION', NULL,
 '[{"code":"all_stages_passed","label":"CL-01..CL-05 all PASSED"},
   {"code":"no_open_major_incidents","label":"No open MAJOR/CRITICAL incidents"},
   {"code":"officer_authorized","label":"Signing officer authorized & certified"}]', 1);

-- Security rules (BR-01..BR-10 per 06_security_rules.md)
INSERT INTO security_rules (rule_id, manual_version_id, description, rule_type, parameters_json, overridable, overridable_roles) VALUES
('BR-01', 'AAW-MAN-2021-R01', 'Aircraft security check must be PASSED', 'STAGE_MUST_BE_PASSED', '{"stage_code":"AIRCRAFT_SECURITY_CHECK"}', 0, NULL),
('BR-02', 'AAW-MAN-2021-R01', 'No baggage/passenger mismatch allowed', 'BAGGAGE_MISMATCH_ZERO', NULL, 0, NULL),
('BR-03', 'AAW-MAN-2021-R01', 'No open MAJOR/CRITICAL incidents', 'NO_OPEN_MAJOR_INCIDENTS', NULL, 1, 'CSO'),
('BR-04', 'AAW-MAN-2021-R01', 'Broken catering seal requires manual inspection', 'CATERING_SEAL_CHECK', NULL, 0, NULL),
('BR-05', 'AAW-MAN-2021-R01', 'Unknown cargo must be screened before acceptance', 'CARGO_UNKNOWN_SCREENED', NULL, 0, NULL),
('BR-06', 'AAW-MAN-2021-R01', 'No broken/missing aircraft seal unresolved', 'AIRCRAFT_SEAL_CHECK', NULL, 1, 'SUPERVISOR,SUPERINTENDENT,CSO'),
('BR-07', 'AAW-MAN-2021-R01', 'Declaring officer certification must be valid', 'OFFICER_CERT_VALID', NULL, 0, NULL),
('BR-08', 'AAW-MAN-2021-R01', 'Declaring officer role must be authorized', 'OFFICER_ROLE_AUTHORIZED', '{"allowed_roles":["SECURITY_OFFICER","SUPERVISOR","SUPERINTENDENT","CSO"]}', 0, NULL),
('BR-09', 'AAW-MAN-2021-R01', 'No open emergency event linked to flight', 'NO_OPEN_EMERGENCY', NULL, 0, NULL),
('BR-10', 'AAW-MAN-2021-R01', 'Random screening percentage meets threat-level threshold', 'SCREENING_PCT_THRESHOLD', '{"required_pct":{"GREEN":10,"AMBER":20,"RED":50}}', 0, NULL);

-- Sample prohibited items (subset, category-level only — see R-016 for currency caveat)
INSERT INTO prohibited_items (item_id, airline_id, category, name, source_reference) VALUES
('pi-1','AAW','FIREARMS','Firearms and replica firearms','AAWSM Appendix F'),
('pi-2','AAW','EDGED','Knives with blades > 6cm','AAWSM Appendix F'),
('pi-3','AAW','EXPLOSIVE','Explosives and explosive devices','AAWSM Appendix F'),
('pi-4','AAW','LAGS','Liquids/Gels/Aerosols over 100ml (outside STEB)','AAWSM Appendix F'),
('pi-5','AAW','CHEMICAL','Corrosive or toxic substances','AAWSM Appendix F');
