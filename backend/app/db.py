"""Database connection layer — dual backend.

- LOCAL DEV / this sandbox: SQLite (no `DATABASE_URL` set). This is what has
  been running and tested throughout this project so far.
- PRODUCTION (Supabase/Postgres): set `DATABASE_URL` (a standard Postgres
  connection string, e.g. the one Supabase shows under
  Project Settings → Database → Connection string → URI) and the app
  switches automatically. Requires `psycopg2-binary` (in requirements.txt).

⚠️ Honesty note: the Postgres path in this file could NOT be executed in
this sandbox — no `psycopg2` installed here and no network egress to test
against a live Supabase instance. It is written carefully and mirrors the
exact query patterns already proven against SQLite, but real verification
happens only once deployed (see docs/10_render_deployment.md).
"""
import os
import re
import uuid
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")  # Postgres connection string, if set
IS_POSTGRES = bool(DATABASE_URL)

# Local SQLite fallback (dev/demo path — proven working throughout this project)
SQLITE_PATH = os.environ.get(
    "AVSEC_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "db", "avsec.db"),
)

# Table/column names differ between the two schemas (db/schema.sql vs
# supabase/migrations/0001_init.sql) because Postgres identity/roles live
# in `profiles` (linked to Supabase auth.users), not a home-grown `users`
# table. Centralizing the difference here means the rest of the app never
# hardcodes either name.
PROFILE_TABLE = "profiles" if IS_POSTGRES else "users"
PROFILE_ID_COL = "id" if IS_POSTGRES else "user_id"

_PLACEHOLDER_RE = re.compile(r"\?")


class _PGRow(dict):
    """Makes a psycopg2 RealDictCursor row behave like sqlite3.Row for the
    `row["col"]` access pattern used everywhere in this codebase."""
    pass


class _PGCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        row = self._cursor.fetchone()
        return _PGRow(row) if row is not None else None

    def fetchall(self):
        return [_PGRow(r) for r in self._cursor.fetchall()]


class _PGConnWrapper:
    """Wraps a psycopg2 connection so callers can keep using the exact same
    `conn.execute(sql_with_question_marks, params)` pattern used for SQLite
    everywhere in this codebase — no call-site rewrites needed elsewhere."""
    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        # Our SQL is written with SQLite-style `?` placeholders throughout;
        # psycopg2 needs `%s`. None of our queries contain a literal `?`
        # inside string values, so a straight replace is safe here.
        pg_sql = _PLACEHOLDER_RE.sub("%s", sql)
        cur.execute(pg_sql, params)
        return _PGCursorWrapper(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_conn():
    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        pg_conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return _PGConnWrapper(pg_conn)
    else:
        import sqlite3
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def get_profile_by_id(conn, user_id: str):
    """The ONE place that knows whether identity lives in `users` (SQLite
    dev) or `profiles` (Postgres/Supabase prod)."""
    return conn.execute(
        f"SELECT * FROM {PROFILE_TABLE} WHERE {PROFILE_ID_COL}=?", (user_id,)
    ).fetchone()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_json(value):
    """SQLite stores our json.dumps()'d TEXT as-is (needs json.loads on
    read). Postgres jsonb columns are auto-adapted to native Python
    dict/list by psycopg2 on read — calling json.loads() on those would
    crash. This is the one place that normalizes the difference."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    import json as _json
    return _json.loads(value)


def date_str(value) -> str:
    """SQLite stores dates as plain 'YYYY-MM-DD' strings. Postgres `date`
    columns come back from psycopg2 as `datetime.date` objects. Both need
    to compare against `now_iso()[:10]` the same way — this normalizes it."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]
