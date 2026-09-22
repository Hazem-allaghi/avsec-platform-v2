"""DEV-ONLY token minting.

This exists purely to test the auth.py verification chain locally without
network access to a real Supabase project. It signs tokens with the SAME
secret `auth.py` verifies against (`SUPABASE_JWT_SECRET` / the insecure dev
default). A real deployment NEVER uses this file — tokens come from
Supabase Auth itself (sign-in, magic link, etc.) and this module should not
even be imported outside tests/dev tooling.
"""
import os
import time
import jwt

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "dev-only-insecure-secret-change-me")


def mint_dev_token(user_id: str, ttl_seconds: int = 3600, aud: str = "authenticated") -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": aud,
        "role": "authenticated",  # Supabase's own auth role claim (not our business role)
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")


if __name__ == "__main__":
    import sys
    uid = sys.argv[1] if len(sys.argv) > 1 else "u-sup1"
    print(mint_dev_token(uid))
