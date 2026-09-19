"""Workflow Engine — implements docs/03_master_workflow.md.

Stages 3 (CATERING_SECURITY) and 4 (CARGO_MAIL_SECURITY) share sequence_order
(parallel gates) per the documented open assumption in 03_master_workflow.md
(§ "نقاط تحتاج قرارك", item 1) — flagged as an engineering assumption, not a
literal manual requirement, pending confirmation.
"""
from .db import new_id, now_iso
from . import audit

STAGES = [
    ("AIRCRAFT_SECURITY_CHECK", 1),
    ("BAGGAGE_RECONCILIATION", 2),
    ("CATERING_SECURITY", 3),
    ("CARGO_MAIL_SECURITY", 3),   # parallel with catering — see docstring
    ("SEAL_VERIFICATION", 4),
    ("SECURITY_INCIDENT_REVIEW", 5),
    ("SECURITY_DECLARATION", 6),
]


def init_stages_for_flight(conn, flight):
    for stage_code, seq in STAGES:
        conn.execute(
            """INSERT INTO workflow_stages
               (stage_id, flight_id, stage_code, sequence_order, status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (new_id("stg"), flight["flight_id"], stage_code, seq, "PENDING", now_iso()),
        )
    audit.record(conn, flight["airline_id"], "flight", flight["flight_id"],
                 "STAGES_INITIALIZED", actor_user_id=flight["created_by"])


def can_start_stage(conn, flight_id, stage_code):
    """A stage can start only if all *lower sequence_order* stages are PASSED,
    and there is no OPEN emergency event blocking the whole flight."""
    open_emergency = conn.execute(
        "SELECT event_id FROM emergency_events WHERE flight_id=? AND status='OPEN'",
        (flight_id,),
    ).fetchone()
    if open_emergency:
        return False, f"Flight has an OPEN emergency event ({open_emergency['event_id']})"

    target = conn.execute(
        "SELECT sequence_order FROM workflow_stages WHERE flight_id=? AND stage_code=?",
        (flight_id, stage_code),
    ).fetchone()
    if not target:
        return False, "Unknown stage for this flight"

    blockers = conn.execute(
        """SELECT stage_code, status FROM workflow_stages
           WHERE flight_id=? AND sequence_order < ? AND status != 'PASSED'""",
        (flight_id, target["sequence_order"]),
    ).fetchall()
    if blockers:
        names = ", ".join(f"{b['stage_code']}({b['status']})" for b in blockers)
        return False, f"Prior stage(s) not PASSED: {names}"
    return True, None


def set_stage_status(conn, flight_id, stage_code, status, reason=None, actor_user_id=None):
    before = conn.execute(
        "SELECT * FROM workflow_stages WHERE flight_id=? AND stage_code=?",
        (flight_id, stage_code),
    ).fetchone()
    ts = now_iso()
    conn.execute(
        """UPDATE workflow_stages SET status=?, blocked_reason=?,
           completed_at=CASE WHEN ? IN ('PASSED','FAILED') THEN ? ELSE completed_at END
           WHERE flight_id=? AND stage_code=?""",
        (status, reason, status, ts, flight_id, stage_code),
    )
    flight = conn.execute("SELECT airline_id FROM flights WHERE flight_id=?", (flight_id,)).fetchone()
    audit.record(
        conn, flight["airline_id"], "workflow_stage", f"{flight_id}:{stage_code}",
        "STAGE_TRANSITION", actor_user_id=actor_user_id,
        before=dict(before) if before else None,
        after={"status": status, "reason": reason},
    )
