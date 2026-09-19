"""Security Rules Engine.

Rules are DATA (table `security_rules`), not hardcoded per-airline logic.
This module only knows how to evaluate a fixed vocabulary of `rule_type`s;
the actual thresholds/targets come from `parameters_json` per rule row, and
which rules apply comes from `manual_version_id` — i.e. a different airline
manual can define a different rule *set* without touching this code.

See docs/06_security_rules.md for the human-readable spec (BR-01..BR-10).
"""
import json
from .. import db as db_mod


def _stage_status(conn, flight_id, stage_code):
    row = conn.execute(
        "SELECT status FROM workflow_stages WHERE flight_id=? AND stage_code=?",
        (flight_id, stage_code),
    ).fetchone()
    return row["status"] if row else "PENDING"


def eval_stage_must_be_passed(conn, flight, params):
    stage_code = params["stage_code"]
    status = _stage_status(conn, flight["flight_id"], stage_code)
    if status != "PASSED":
        return False, f"Stage {stage_code} is {status}, not PASSED"
    return True, None


def eval_baggage_mismatch_zero(conn, flight, params):
    # "Latest wins": baggage reconciliation is one running summary per flight,
    # so we take the most-recently-inserted record (rowid, not created_at,
    # since created_at has 1-second resolution and can tie on rapid inserts).
    row = conn.execute(
        """SELECT mismatch_count FROM baggage_records WHERE flight_id=?
           ORDER BY rowid DESC LIMIT 1""",
        (flight["flight_id"],),
    ).fetchone()
    if row is None:
        return False, "No baggage reconciliation record found"
    if row["mismatch_count"] and row["mismatch_count"] > 0:
        return False, f"{row['mismatch_count']} baggage/passenger mismatch(es) unresolved"
    return True, None


def eval_no_open_major_incidents(conn, flight, params):
    rows = conn.execute(
        """SELECT incident_id, severity FROM security_incidents
           WHERE flight_id=? AND status!='CLOSED' AND severity IN ('MAJOR','CRITICAL')""",
        (flight["flight_id"],),
    ).fetchall()
    if rows:
        ids = ", ".join(r["incident_id"] for r in rows)
        return False, f"Open MAJOR/CRITICAL incident(s) unresolved: {ids}"
    return True, None


def eval_catering_seal_check(conn, flight, params):
    # Evaluate only the LATEST record per seal_number (a re-check supersedes
    # a prior broken/failed check for the same seal — not every historical row).
    rows = conn.execute(
        """SELECT c.record_id, c.seal_status, c.manual_inspection_done
           FROM catering_records c
           JOIN (SELECT seal_number, MAX(rowid) AS max_rowid
                 FROM catering_records WHERE flight_id=? GROUP BY seal_number) latest
             ON c.seal_number = latest.seal_number AND c.rowid = latest.max_rowid
           WHERE c.flight_id=?""",
        (flight["flight_id"], flight["flight_id"]),
    ).fetchall()
    for r in rows:
        if r["seal_status"] == "BROKEN" and not r["manual_inspection_done"]:
            return False, f"Catering record {r['record_id']}: seal broken, manual inspection not done"
        if r["seal_status"] == "MISSING":
            return False, f"Catering record {r['record_id']}: seal missing"
    return True, None


def eval_cargo_unknown_screened(conn, flight, params):
    # Latest record per AWB — a corrected re-submission supersedes the prior one.
    rows = conn.execute(
        """SELECT c.record_id, c.consignor_status, c.screening_done
           FROM cargo_records c
           JOIN (SELECT awb_number, MAX(rowid) AS max_rowid
                 FROM cargo_records WHERE flight_id=? GROUP BY awb_number) latest
             ON c.awb_number = latest.awb_number AND c.rowid = latest.max_rowid
           WHERE c.flight_id=? AND c.consignor_status='UNKNOWN' AND c.screening_done=0""",
        (flight["flight_id"], flight["flight_id"]),
    ).fetchall()
    if rows:
        ids = ", ".join(r["record_id"] for r in rows)
        return False, f"Unknown-consignor cargo not screened: {ids}"
    return True, None


def eval_aircraft_seal_check(conn, flight, params):
    # Latest record per physical seal_number — a re-verification supersedes
    # an earlier BROKEN/MISSING reading for that same seal.
    rows = conn.execute(
        """SELECT s.seal_id, s.status
           FROM aircraft_seals s
           JOIN (SELECT seal_number, MAX(rowid) AS max_rowid
                 FROM aircraft_seals WHERE flight_id=? GROUP BY seal_number) latest
             ON s.seal_number = latest.seal_number AND s.rowid = latest.max_rowid
           WHERE s.flight_id=? AND s.status IN ('BROKEN','MISSING')""",
        (flight["flight_id"], flight["flight_id"]),
    ).fetchall()
    if rows:
        ids = ", ".join(f"{r['seal_id']}({r['status']})" for r in rows)
        return False, f"Aircraft seal issue(s) unresolved: {ids}"
    return True, None


def eval_officer_cert_valid(conn, flight, params, declaring_user_id=None):
    if not declaring_user_id:
        return False, "No declaring officer provided"
    row = conn.execute(
        "SELECT certification_expiry FROM users WHERE user_id=?", (declaring_user_id,)
    ).fetchone()
    if not row or not row["certification_expiry"]:
        return False, "Declaring officer has no certification on file"
    # ISO date string comparison works for YYYY-MM-DD
    if db_mod.date_str(row["certification_expiry"]) < db_mod.now_iso()[:10]:
        return False, "Declaring officer certification expired"
    return True, None


def eval_officer_role_authorized(conn, flight, params, declaring_user_id=None):
    allowed = set(params.get("allowed_roles", []))
    if not declaring_user_id:
        return False, "No declaring officer provided"
    row = conn.execute("SELECT role FROM users WHERE user_id=?", (declaring_user_id,)).fetchone()
    if not row or row["role"] not in allowed:
        return False, f"Declaring officer role not authorized (must be one of {sorted(allowed)})"
    return True, None


def eval_no_open_emergency(conn, flight, params):
    rows = conn.execute(
        "SELECT event_id FROM emergency_events WHERE flight_id=? AND status='OPEN'",
        (flight["flight_id"],),
    ).fetchall()
    if rows:
        ids = ", ".join(r["event_id"] for r in rows)
        return False, f"Open emergency event(s) linked to flight: {ids}"
    return True, None


def eval_screening_pct_threshold(conn, flight, params):
    required = params.get("required_pct", {}).get(flight["threat_level"])
    if required is None:
        return True, None
    row = conn.execute(
        """SELECT screened_pct FROM baggage_records WHERE flight_id=?
           ORDER BY rowid DESC LIMIT 1""",
        (flight["flight_id"],),
    ).fetchone()
    actual = row["screened_pct"] if row else 0
    if actual is None or actual < required:
        return False, (
            f"Screening coverage {actual}% below required {required}% "
            f"for threat level {flight['threat_level']}"
        )
    return True, None


EVALUATORS = {
    "STAGE_MUST_BE_PASSED": eval_stage_must_be_passed,
    "BAGGAGE_MISMATCH_ZERO": eval_baggage_mismatch_zero,
    "NO_OPEN_MAJOR_INCIDENTS": eval_no_open_major_incidents,
    "CATERING_SEAL_CHECK": eval_catering_seal_check,
    "CARGO_UNKNOWN_SCREENED": eval_cargo_unknown_screened,
    "AIRCRAFT_SEAL_CHECK": eval_aircraft_seal_check,
    "OFFICER_CERT_VALID": eval_officer_cert_valid,
    "OFFICER_ROLE_AUTHORIZED": eval_officer_role_authorized,
    "NO_OPEN_EMERGENCY": eval_no_open_emergency,
    "SCREENING_PCT_THRESHOLD": eval_screening_pct_threshold,
}


def evaluate_clearance(conn, flight_id, declaring_user_id=None):
    """Evaluate ALL active rules for the flight's manual version.

    Returns dict: {
        "clearable": bool,
        "results": [ {rule_id, description, passed, reason, overridable,
                        overridden, overridden_by, override_reason} ... ]
    }
    """
    flight = conn.execute("SELECT * FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
    if not flight:
        raise ValueError("flight not found")

    rules = conn.execute(
        "SELECT * FROM security_rules WHERE manual_version_id=? AND active=1",
        (flight["manual_version_id"],),
    ).fetchall()

    results = []
    clearable = True

    for rule in rules:
        params = db_mod.parse_json(rule["parameters_json"]) if rule["parameters_json"] else {}
        fn = EVALUATORS.get(rule["rule_type"])
        if fn is None:
            results.append({
                "rule_id": rule["rule_id"], "description": rule["description"],
                "passed": False, "reason": f"Unknown rule_type {rule['rule_type']}",
                "overridable": False, "overridden": False,
            })
            clearable = False
            continue

        if rule["rule_type"] in ("OFFICER_CERT_VALID", "OFFICER_ROLE_AUTHORIZED"):
            passed, reason = fn(conn, flight, params, declaring_user_id=declaring_user_id)
        else:
            passed, reason = fn(conn, flight, params)

        overridden = False
        override_reason = None
        overridden_by = None
        if not passed and rule["overridable"]:
            ov = conn.execute(
                """SELECT * FROM rule_overrides WHERE flight_id=? AND rule_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (flight_id, rule["rule_id"]),
            ).fetchone()
            if ov:
                overridden = True
                override_reason = ov["reason"]
                overridden_by = ov["overridden_by"]
                passed = True  # cleared via override, but flagged clearly below

        results.append({
            "rule_id": rule["rule_id"],
            "description": rule["description"],
            "passed": passed,
            "reason": reason,
            "overridable": bool(rule["overridable"]),
            "overridable_roles": rule["overridable_roles"],
            "overridden": overridden,
            "overridden_by": overridden_by,
            "override_reason": override_reason,
        })
        if not passed:
            clearable = False

    return {"clearable": clearable, "results": results}
