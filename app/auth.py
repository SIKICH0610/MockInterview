"""Minimal auth: PBKDF2 password hashes + HMAC-signed session tokens.

No external dependencies; the signing secret lives in data/secret.key.
Swappable for the platform SSO later without touching the data model.
"""

import hashlib
import hmac
import os
import secrets
import time

from .db import DATA_DIR

SECRET_PATH = os.path.join(DATA_DIR, "secret.key")
TOKEN_TTL = 24 * 3600  # one sign-in lasts a day
_secret_cache = None

# Behind HTTPS (the cloud server) set MI_COOKIE_SECURE=1 so the sign-in cookie
# is never sent over plain HTTP. Leave unset for http://localhost development.
AUTH_COOKIE = {
    "httponly": True,
    "samesite": "lax",
    "secure": os.environ.get("MI_COOKIE_SECURE", "") == "1",
}


def _secret():
    global _secret_cache
    if _secret_cache is None:
        # On a server, MI_SECRET_KEY (a long random string) replaces the file,
        # so every app process / redeploy signs sessions with the same key.
        env_key = os.environ.get("MI_SECRET_KEY", "").strip()
        if env_key:
            if len(env_key) < 32:
                raise RuntimeError("MI_SECRET_KEY must be at least 32 characters")
            _secret_cache = env_key.encode()
            return _secret_cache
        if not os.path.exists(SECRET_PATH):
            with open(SECRET_PATH, "wb") as f:
                f.write(secrets.token_bytes(32))
        with open(SECRET_PATH, "rb") as f:
            _secret_cache = f.read()
    return _secret_cache


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(pw: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    try:
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    except ValueError:
        return False
    return hmac.compare_digest(calc, digest)


def make_token(teacher_id: int) -> str:
    exp = int(time.time()) + TOKEN_TTL
    msg = f"{teacher_id}.{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def parse_token(token: str):
    try:
        tid, exp, sig = token.split(".")
        msg = f"{tid}.{exp}"
        good = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        if int(exp) < time.time():
            return None
        return int(tid)
    except Exception:  # noqa: BLE001
        return None
