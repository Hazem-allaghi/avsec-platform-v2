"""Aviation Security Platform — API (MVP).

Run: python3 backend/app/main.py
"""
import json
import os
from flask import Flask, request, jsonify, g, send_from_directory

from .db import get_conn, new_id, now_iso
from . import audit, workflow
from .rules import engine as rules_engine
from . import auth as auth_mod

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

app = Flask(__name__)


@app.after_request
def add_cors(resp):
    # Permissive CORS for local MVP/demo only — tighten before any real deployment.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.get("/")
@app.get("/dashboard")
def serve_dashboard():
    return send_from_directory(FRONTEND_DIR, "dashboard.html")

STAGE_BY_CHECKLIST_CODE = {
    "CL-01": "AIRCRAFT_SECURITY_CHECK",
    "CL-02": "BAGGAGE_RECONCILIATION",
    "CL-03": "CATERING_SECURITY",
    "CL-04": "CARGO_MAIL_SECURITY",
    "CL-05": "SEAL_VERIFICATION",
    "CL-06": "SECURITY_DECLARATION",
}


def error(msg, code=400):
    return jsonify({"error": msg}), code


def require_user(conn, user_id):
    if not user_id:
        return None
    from .db import get_profile_by_id
    return get_profile_by_id(conn, user_id)


# ---------------------------------------------------------------- FLIGHTS --
@app.post("/flights")
def create_flight():
    body = request.get_json(force=True)
    conn = get_conn()
    try:
        airline_id = body.get("airline_id", "AAW")
        manual = conn.execute(
            "SELECT manual_version_id FROM manual_versions WHERE airline_id=? AND is_active=1",
            (airline_id,),
        ).fetchone()
        if not manual:
            return error(f"No active manual_version for airline {airline_id}", 400)

        flight_id = new_id("flt")
        conn.execute(
            """INSERT INTO flights
               (flight_id, airline_id, flight_number, aircraft_reg, aircraft_type,
                departure_airport, destination, scheduled_departure, gate,
                threat_level, security_status, manual_version_id, created_by, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'PENDING', ?,?,?,?)""",
            (
                flight_id, airline_id, body["flight_number"], body["aircraft_reg"],
                body["aircraft_type"], body.get("departure_airport"), body.get("destination"),
                body.get("scheduled_departure"), body.get("gate"),
                body.get("threat_level", "GREEN"), manual["manual_version_id"],
                body.get("created_by"), now_iso(), now_iso(),
            ),
        )
        flight = conn.execute("SELECT * FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        workflow.init_stages_for_flight(conn, flight)
        audit.record(conn, airline_id, "flight", flight_id, "CREATE",
                     actor_user_id=body.get("created_by"), after=dict(flight))
        conn.commit()
        return jsonify(dict(flight)), 201
    finally:
        conn.close()


@app.get("/flights")
def list_flights():
    conn = get_conn()
    try:
        airline_id = request.args.get("airline_id", "AAW")
        rows = conn.execute(
            "SELECT * FROM flights WHERE airline_id=? ORDER BY created_at DESC", (airline_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/flights/<flight_id>")
def get_flight(flight_id):
    conn = get_conn()
    try:
        flight = conn.execute("SELECT * FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        if not flight:
            return error("flight not found", 404)
        stages = conn.execute(
            "SELECT * FROM workflow_stages WHERE flight_id=? ORDER BY sequence_order",
            (flight_id,),
        ).fetchall()
        incidents = conn.execute(
            "SELECT * FROM security_incidents WHERE flight_id=? ORDER BY created_at DESC",
            (flight_id,),
        ).fetchall()
        emergencies = conn.execute(
            "SELECT * FROM emergency_events WHERE flight_id=? ORDER BY created_at DESC",
            (flight_id,),
        ).fetchall()
        return jsonify({
            "flight": dict(flight),
            "stages": [dict(s) for s in stages],
            "incidents": [dict(i) for i in incidents],
            "emergencies": [dict(e) for e in emergencies],
        })
    finally:
        conn.close()


# ------------------------------------------------------------- CHECKLISTS --
@app.post("/flights/<flight_id>/checklists/<code>/start")
def start_checklist(flight_id, code):
    conn = get_conn()
    try:
        flight = conn.execute("SELECT * FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        if not flight:
            return error("flight not found", 404)
        stage_code = STAGE_BY_CHECKLIST_CODE.get(code)
        if not stage_code:
            return error(f"unknown checklist code {code}", 400)

        ok, reason = workflow.can_start_stage(conn, flight_id, stage_code)
        if not ok:
            return error(f"Cannot start {code}: {reason}", 409)

        template = conn.execute(
            """SELECT * FROM checklist_templates
               WHERE airline_id=? AND manual_version_id=? AND code=?""",
            (flight["airline_id"], flight["manual_version_id"], code),
        ).fetchone()
        if not template:
            return error(f"no template for {code}", 404)

        instance_id = new_id("ckl")
        conn.execute(
            """INSERT INTO checklist_instances
               (instance_id, flight_id, template_id, status, started_at, created_at)
               VALUES (?,?,?, 'IN_PROGRESS', ?, ?)""",
            (instance_id, flight_id, template["template_id"], now_iso(), now_iso()),
        )
        workflow.set_stage_status(conn, flight_id, stage_code, "IN_PROGRESS")
        conn.commit()
        return jsonify({"instance_id": instance_id, "template": dict(template)}), 201
    finally:
        conn.close()


@app.post("/checklists/<instance_id>/submit")
def submit_checklist(instance_id):
    """body: { results: {item_code: 'PASS'|'FAIL', ...}, signatures: [user_id,...],
               lat, lng, gps_accuracy_m }"""
    body = request.get_json(force=True)
    conn = get_conn()
    try:
        inst = conn.execute(
            "SELECT * FROM checklist_instances WHERE instance_id=?", (instance_id,)
        ).fetchone()
        if not inst:
            return error("instance not found", 404)
        template = conn.execute(
            "SELECT * FROM checklist_templates WHERE template_id=?", (inst["template_id"],)
        ).fetchone()
        flight = conn.execute(
            "SELECT * FROM flights WHERE flight_id=?", (inst["flight_id"],)
        ).fetchone()

        results = body.get("results", {})
        signatures = body.get("signatures", [])

        if len(signatures) < template["min_signatures"]:
            return error(
                f"{template['code']} requires at least {template['min_signatures']} signature(s), "
                f"got {len(signatures)}", 400,
            )

        all_pass = all(v == "PASS" for v in results.values()) and len(results) > 0
        status = "PASSED" if all_pass else "FAILED"

        conn.execute(
            """UPDATE checklist_instances SET status=?, results_json=?, completed_at=?,
               lat=?, lng=?, gps_accuracy_m=?, captured_at=? WHERE instance_id=?""",
            (status, json.dumps(results), now_iso(),
             body.get("lat"), body.get("lng"), body.get("gps_accuracy_m"), now_iso(),
             instance_id),
        )
        for uid in signatures:
            from .db import get_profile_by_id
            user = get_profile_by_id(conn, uid)
            if not user:
                conn.rollback()
                return error(f"unknown signer {uid}", 400)
            conn.execute(
                """INSERT INTO checklist_signatures
                   (signature_id, instance_id, user_id, role_at_signing, signed_at)
                   VALUES (?,?,?,?,?)""",
                (new_id("sig"), instance_id, uid, user["role"], now_iso()),
            )

        stage_code = STAGE_BY_CHECKLIST_CODE[template["code"]]
        workflow.set_stage_status(
            conn, inst["flight_id"], stage_code, status,
            reason=None if all_pass else "Checklist item(s) FAILED",
            actor_user_id=signatures[0] if signatures else None,
        )

        if not all_pass and template["code"] == "CL-01":
            # AAWSM §14.1.3 — suspect item during aircraft search => incident + emergency
            incident_id = new_id("inc")
            conn.execute(
                """INSERT INTO security_incidents
                   (incident_id, flight_id, airline_id, incident_type, severity,
                    description, status, reported_by, created_at)
                   VALUES (?,?,?,'SUSPECT_ITEM','CRITICAL',?, 'OPEN', ?, ?)""",
                (incident_id, inst["flight_id"], flight["airline_id"],
                 "Auto-created: CL-01 aircraft search FAILED", signatures[0] if signatures else None,
                 now_iso()),
            )
            audit.record(conn, flight["airline_id"], "security_incident", incident_id,
                         "AUTO_CREATE_FROM_FAILED_CHECKLIST")

        audit.record(conn, flight["airline_id"], "checklist_instance", instance_id,
                     "SUBMIT", actor_user_id=signatures[0] if signatures else None,
                     after={"status": status, "results": results})
        conn.commit()
        return jsonify({"instance_id": instance_id, "status": status})
    finally:
        conn.close()


# ------------------------------------------------------- DOMAIN RECORDS ----
@app.post("/flights/<flight_id>/baggage")
def record_baggage(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        rid = new_id("bag")
        conn.execute(
            """INSERT INTO baggage_records
               (record_id, flight_id, total_hold_bags, reconciled_bags, unaccompanied_bags,
                mismatch_count, screened_pct, recorded_by, lat, lng, captured_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, flight_id, b.get("total_hold_bags", 0), b.get("reconciled_bags", 0),
             b.get("unaccompanied_bags", 0), b.get("mismatch_count", 0), b.get("screened_pct", 0),
             b.get("recorded_by"), b.get("lat"), b.get("lng"), now_iso(), now_iso()),
        )
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        audit.record(conn, flight["airline_id"], "baggage_record", rid, "CREATE",
                     actor_user_id=b.get("recorded_by"), after=b)
        conn.commit()
        return jsonify({"record_id": rid}), 201
    finally:
        conn.close()


@app.post("/flights/<flight_id>/catering")
def record_catering(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        rid = new_id("cat")
        conn.execute(
            """INSERT INTO catering_records
               (record_id, flight_id, truck_id, seal_number, seal_status,
                manual_inspection_done, checked_by, lat, lng, captured_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, flight_id, b.get("truck_id"), b.get("seal_number"), b.get("seal_status"),
             bool(b.get("manual_inspection_done")), b.get("checked_by"),
             b.get("lat"), b.get("lng"), now_iso(), now_iso()),
        )
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        audit.record(conn, flight["airline_id"], "catering_record", rid, "CREATE",
                     actor_user_id=b.get("checked_by"), after=b)
        conn.commit()
        return jsonify({"record_id": rid}), 201
    finally:
        conn.close()


@app.post("/flights/<flight_id>/cargo")
def record_cargo(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        rid = new_id("crg")
        conn.execute(
            """INSERT INTO cargo_records
               (record_id, flight_id, awb_number, consignor_status, screening_done,
                screening_method, accepted, recorded_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (rid, flight_id, b.get("awb_number"), b.get("consignor_status"),
             bool(b.get("screening_done")), b.get("screening_method"),
             bool(b.get("accepted")), b.get("recorded_by"), now_iso()),
        )
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        audit.record(conn, flight["airline_id"], "cargo_record", rid, "CREATE",
                     actor_user_id=b.get("recorded_by"), after=b)
        conn.commit()
        return jsonify({"record_id": rid}), 201
    finally:
        conn.close()


@app.post("/flights/<flight_id>/seals")
def record_seal(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        sid = new_id("sel")
        conn.execute(
            """INSERT INTO aircraft_seals
               (seal_id, flight_id, aircraft_reg, seal_number, location_code, status,
                verified_by, verified_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (sid, flight_id, b["aircraft_reg"], b["seal_number"], b.get("location_code"),
             b.get("status", "INTACT"), b.get("verified_by"), now_iso(), now_iso()),
        )
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        if b.get("status") in ("BROKEN", "MISSING"):
            incident_id = new_id("inc")
            conn.execute(
                """INSERT INTO security_incidents
                   (incident_id, flight_id, airline_id, incident_type, severity,
                    description, status, reported_by, created_at)
                   VALUES (?,?,?,'SEAL_ISSUE','MAJOR',?, 'OPEN', ?, ?)""",
                (incident_id, flight_id, flight["airline_id"],
                 f"Auto-created: aircraft seal {b['seal_number']} status={b.get('status')}",
                 b.get("verified_by"), now_iso()),
            )
        audit.record(conn, flight["airline_id"], "aircraft_seal", sid, "CREATE",
                     actor_user_id=b.get("verified_by"), after=b)
        conn.commit()
        return jsonify({"seal_id": sid}), 201
    finally:
        conn.close()


# ------------------------------------------------------------- INCIDENTS ---
@app.post("/flights/<flight_id>/incidents")
@auth_mod.require_auth()
def open_incident(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        iid = new_id("inc")
        conn.execute(
            """INSERT INTO security_incidents
               (incident_id, flight_id, airline_id, incident_type, severity, description,
                status, reported_by, lat, lng, captured_at, created_at)
               VALUES (?,?,?,?,?,?, 'OPEN', ?, ?, ?, ?, ?)""",
            (iid, flight_id, flight["airline_id"], b["incident_type"], b["severity"],
             b["description"], g.user_id, b.get("lat"), b.get("lng"), now_iso(), now_iso()),
        )
        audit.record(conn, flight["airline_id"], "security_incident", iid, "CREATE",
                     actor_user_id=g.user_id, after=b)
        conn.commit()
        return jsonify({"incident_id": iid}), 201
    finally:
        conn.close()


@app.post("/incidents/<incident_id>/close")
@auth_mod.require_auth(allowed_roles=["SUPERVISOR", "SUPERINTENDENT", "CSO"])
def close_incident(incident_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        inc = conn.execute("SELECT * FROM security_incidents WHERE incident_id=?", (incident_id,)).fetchone()
        if not inc:
            return error("incident not found", 404)
        closed_by = g.user_id
        conn.execute(
            """UPDATE security_incidents SET status='CLOSED', closed_by=?, close_reason=?, closed_at=?
               WHERE incident_id=?""",
            (closed_by, b.get("close_reason", ""), now_iso(), incident_id),
        )
        audit.record(conn, inc["airline_id"], "security_incident", incident_id, "CLOSE",
                     actor_user_id=closed_by, before=dict(inc), after={**b, "closed_by": closed_by})
        conn.commit()
        return jsonify({"status": "CLOSED"})
    finally:
        conn.close()


# ------------------------------------------------------------ EMERGENCY ----
@app.post("/flights/<flight_id>/emergency")
@auth_mod.require_auth()
def open_emergency(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        flight = conn.execute("SELECT * FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        eid = new_id("emg")
        conn.execute(
            """INSERT INTO emergency_events
               (event_id, flight_id, airline_id, event_type, status, opened_by, notes, created_at)
               VALUES (?,?,?,?, 'OPEN', ?, ?, ?)""",
            (eid, flight_id, flight["airline_id"], b["event_type"], g.user_id,
             b.get("notes"), now_iso()),
        )
        conn.execute("UPDATE flights SET security_status='EMERGENCY', updated_at=? WHERE flight_id=?",
                     (now_iso(), flight_id))
        audit.record(conn, flight["airline_id"], "emergency_event", eid, "OPEN",
                     actor_user_id=g.user_id, after=b)
        conn.commit()
        return jsonify({"event_id": eid}), 201
    finally:
        conn.close()


@app.post("/emergency/<event_id>/close")
@auth_mod.require_auth(allowed_roles=["SUPERVISOR", "SUPERINTENDENT", "CSO"])
def close_emergency(event_id):
    b = request.get_json(force=True) if request.data else {}
    conn = get_conn()
    try:
        ev = conn.execute("SELECT * FROM emergency_events WHERE event_id=?", (event_id,)).fetchone()
        if not ev:
            return error("event not found", 404)
        closed_by = g.user_id
        conn.execute(
            "UPDATE emergency_events SET status='CLOSED', closed_by=?, closed_at=? WHERE event_id=?",
            (closed_by, now_iso(), event_id),
        )
        remaining = conn.execute(
            "SELECT COUNT(*) c FROM emergency_events WHERE flight_id=? AND status='OPEN'",
            (ev["flight_id"],),
        ).fetchone()
        if remaining["c"] == 0:
            conn.execute("UPDATE flights SET security_status='IN_PROGRESS', updated_at=? WHERE flight_id=?",
                         (now_iso(), ev["flight_id"]))
        audit.record(conn, ev["airline_id"], "emergency_event", event_id, "CLOSE",
                     actor_user_id=closed_by, before=dict(ev), after={**b, "closed_by": closed_by})
        conn.commit()
        return jsonify({"status": "CLOSED"})
    finally:
        conn.close()


# --------------------------------------------------------- CLEARANCE -------
@app.get("/flights/<flight_id>/clearance")
def evaluate_clearance(flight_id):
    conn = get_conn()
    try:
        declaring_user_id = request.args.get("declaring_user_id")
        result = rules_engine.evaluate_clearance(conn, flight_id, declaring_user_id)
        return jsonify(result)
    finally:
        conn.close()


@app.post("/flights/<flight_id>/declaration")
@auth_mod.require_auth(allowed_roles=["SECURITY_OFFICER", "SUPERVISOR", "SUPERINTENDENT", "CSO"])
def sign_declaration(flight_id):
    b = request.get_json(force=True) if request.data else {}
    conn = get_conn()
    try:
        officer_id = g.user_id  # from verified JWT, never trusted from body (Waled decision #5)
        result = rules_engine.evaluate_clearance(conn, flight_id, officer_id)
        if not result["clearable"]:
            return jsonify({"error": "Cannot clear flight — blocking conditions unresolved",
                             "results": result["results"]}), 409

        did = new_id("dec")
        conn.execute(
            """INSERT INTO security_declarations
               (declaration_id, flight_id, declared_by, declaration_text, signed_at)
               VALUES (?,?,?,?,?)""",
            (did, flight_id, officer_id, b.get("declaration_text", ""), now_iso()),
        )
        workflow.set_stage_status(conn, flight_id, "SECURITY_DECLARATION", "PASSED",
                                   actor_user_id=officer_id)
        conn.execute("UPDATE flights SET security_status='CLEARED', updated_at=? WHERE flight_id=?",
                     (now_iso(), flight_id))
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        audit.record(conn, flight["airline_id"], "flight", flight_id, "CLEARED",
                     actor_user_id=officer_id, after={"declaration_id": did})
        conn.commit()
        return jsonify({"declaration_id": did, "security_status": "CLEARED"})
    finally:
        conn.close()


# -------------------------------------------------------------- OVERRIDE ---
@app.post("/flights/<flight_id>/overrides")
@auth_mod.require_auth(allowed_roles=["SUPERVISOR", "SUPERINTENDENT", "CSO"])
def create_override(flight_id):
    b = request.get_json(force=True)
    conn = get_conn()
    try:
        rule = conn.execute("SELECT * FROM security_rules WHERE rule_id=?", (b["rule_id"],)).fetchone()
        if not rule or not rule["overridable"]:
            return error("This rule is not overridable", 403)

        allowed_roles = (rule["overridable_roles"] or "").split(",")
        if g.user_role not in allowed_roles:
            return error(f"Role {g.user_role} not authorized to override this rule "
                         f"(needs one of {allowed_roles})", 403)
        if not b.get("reason", "").strip():
            return error("Override reason is mandatory", 400)

        # Waled decision #3: BR-06 (broken/missing aircraft seal) additionally
        # requires photographic evidence of the damaged seal before an
        # override can be recorded — no exceptions, enforced here.
        if b["rule_id"] == "BR-06" and not b.get("evidence_url", "").strip():
            return error("BR-06 override requires 'evidence_url' (photo of the damaged/missing seal)", 400)

        oid = new_id("ovr")
        conn.execute(
            """INSERT INTO rule_overrides
               (override_id, flight_id, rule_id, overridden_by, reason, evidence_url,
                linked_incident_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (oid, flight_id, b["rule_id"], g.user_id, b["reason"], b.get("evidence_url"),
             b.get("linked_incident_id"), now_iso()),
        )
        flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
        audit.record(conn, flight["airline_id"], "rule_override", oid, "CREATE",
                     actor_user_id=g.user_id, after={**b, "overridden_by": g.user_id})
        conn.commit()
        return jsonify({"override_id": oid}), 201
    finally:
        conn.close()


# ---------------------------------------------------------------- AUDIT ----
@app.get("/flights/<flight_id>/audit")
def get_audit(flight_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM audit_log WHERE entity_id LIKE ? OR entity_id=?
               ORDER BY created_at DESC""",
            (f"{flight_id}:%", flight_id),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})
    @app.get("/debug/env")
def debug_env():
    """Diagnostic endpoint — reports what THIS running process actually sees
    in its environment. No secret values are ever returned, only presence
    booleans and the (non-secret) backend selector. Safe to leave temporarily
    during setup; remove before real production use."""
    from . import db as db_mod
    database_url = os.environ.get("DATABASE_URL", "")
    return jsonify({
        "AVSEC_DB_BACKEND_env": os.environ.get("AVSEC_DB_BACKEND", "(not set)"),
        "DATABASE_URL_is_set": bool(database_url),
        "DATABASE_URL_starts_with": database_url[:13] if database_url else "(empty)",
        "SUPABASE_JWT_SECRET_is_set": bool(os.environ.get("SUPABASE_JWT_SECRET")),
        "SUPABASE_JWT_AUD_env": os.environ.get("SUPABASE_JWT_AUD", "(not set)"),
        "db_module_IS_POSTGRES": db_mod.IS_POSTGRES,
        "db_module_PROFILE_TABLE": db_mod.PROFILE_TABLE,
    })


if __name__ == "__main__":
    import os
    debug = os.environ.get("AVSEC_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", "5055"))  # Render/most PaaS inject $PORT
    app.run(host="0.0.0.0", port=port, debug=debug)
