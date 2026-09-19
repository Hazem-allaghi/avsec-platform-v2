"""Audit Trail Service — append-only writes.

Design rule (per docs/01_architecture.md): there is NO update/delete route
exposed for audit_log anywhere in the API. Every mutation to a security-
relevant entity MUST call `record()` in the same transaction.
"""
import json
from .db import new_id, now_iso


def record(conn, airline_id, entity_type, entity_id, action, actor_user_id=None,
           before=None, after=None, device_id=None):
    conn.execute(
        """INSERT INTO audit_log
           (audit_id, airline_id, entity_type, entity_id, action, actor_user_id,
            before_json, after_json, device_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id("aud"),
            airline_id,
            entity_type,
            entity_id,
            action,
            actor_user_id,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            device_id,
            now_iso(),
        ),
    )
