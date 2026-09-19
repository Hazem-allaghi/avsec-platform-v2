"""Authentication layer (Waled decision #5 — Supabase Auth / auth.uid()).

Design:
- Supabase issues HS256 JWTs signed with the project's JWT secret
  (`SUPABASE_JWT_SECRET`). The `sub` claim IS `auth.uid()` — the same UUID
  that Postgres RLS policies in supabase/migrations/0001_init.sql check
  against via `auth.uid()`.
- This module ONLY verifies the token and resolves the caller's role/profile.
  It does NOT talk to Supabase's REST API (no network in this sandbox) — it
  reads the `profiles` row for that user id from whatever DB backend is
  configured (`AVSEC_DB_BACKEND`), so the SAME verified identity is used
  whether the app is pointed at local SQLite (dev/demo) or a real Supabase
  Postgres instance (production — untested live here, see
  docs/09_supabase_integration.md).

⚠️ Honesty note: real end-to-end testing against a live Supabase project
(actual login, actual token issuance, actual RLS enforcement in Postgres)
could NOT be performed in this sandbox — no outbound network access. What
IS tested here (see tests/test_auth.py) is the full verify → decorator →
role-check chain using tokens minted locally with a matching HS256 secret,
which exercises the exact same code path a real Supabase-issued token would
go through.
"""
import os
import functools
import jwt
from flask import request, g, jsonify

from .db import get_conn

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = os.environ.get("SUPABASE_JWT_AUD", "authenticated")  # Supabase default audience


class AuthError(Exception):
    def __init__(self, message, status=401):
        self.message = message
        self.status = status


def verify_jwt(token: str) -> dict:
    """Verify signature + expiry (+ audience, if present) of a bearer token.
    Returns the decoded claims dict. Raises AuthError on any failure.
    """
    try:
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired")
    except jwt.InvalidAudienceError:
        raise AuthError("Invalid token audience")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")
    return claims


def load_profile(conn, user_id: str):
    """Resolve role/certification/etc for a verified user id.
    Delegates to db.get_profile_by_id(), which is the single place that
    knows whether identity lives in `users` (SQLite dev) or `profiles`
    (Postgres/Supabase prod) — see backend/app/db.py.
    """
    from .db import get_profile_by_id
    return get_profile_by_id(conn, user_id)


def require_auth(allowed_roles=None):
    """Flask route decorator.

    - Extracts `Authorization: Bearer <token>`.
    - Verifies it (signature, expiry, audience).
    - Loads the caller's profile/role from the DB.
    - Rejects (401) if certification_expiry has passed or background check
      isn't CLEARED [R-017 / R-007 in docs/02_requirements_matrix.md].
    - Rejects (403) if `allowed_roles` is given and the caller's role isn't
      in it.
    - On success, sets `g.user_id`, `g.user_role`, `g.user_profile`.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing Authorization: Bearer <token> header"}), 401
            token = auth_header[len("Bearer "):].strip()
            try:
                claims = verify_jwt(token)
            except AuthError as e:
                return jsonify({"error": e.message}), e.status

            user_id = claims["sub"]
            conn = get_conn()
            try:
                profile = load_profile(conn, user_id)
            finally:
                conn.close()

            if not profile:
                return jsonify({"error": f"No profile found for authenticated user {user_id}"}), 403
            if not profile["active"]:
                return jsonify({"error": "User account is inactive"}), 403
            if profile["background_check_status"] != "CLEARED":
                return jsonify({"error": "Background check not CLEARED — cannot perform security actions"}), 403
            if profile["certification_expiry"]:
                from .db import now_iso, date_str
                if date_str(profile["certification_expiry"]) < now_iso()[:10]:
                    return jsonify({"error": "Certification expired"}), 403

            if allowed_roles and profile["role"] not in allowed_roles:
                return jsonify({
                    "error": f"Role {profile['role']} not authorized (needs one of {allowed_roles})"
                }), 403

            g.user_id = user_id
            g.user_role = profile["role"]
            g.user_profile = dict(profile)
            g.jwt_claims = claims
            return fn(*args, **kwargs)
        return wrapper
    return decorator
