"""Authentication: scrypt password hashing (stdlib) + JWT bearer tokens."""
import hashlib
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from .db import query

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def new_buddy_code():
    alphabet = string.ascii_uppercase + string.digits
    return "HB-" + "".join(secrets.choice(alphabet) for _ in range(6))


def issue_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=current_app.config["JWT_EXPIRY_DAYS"]),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"],
                      algorithm=current_app.config["JWT_ALGORITHM"])


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="Sign in to continue."), 401
        try:
            payload = jwt.decode(header[7:], current_app.config["SECRET_KEY"],
                                 algorithms=[current_app.config["JWT_ALGORITHM"]])
        except jwt.ExpiredSignatureError:
            return jsonify(error="Your session expired. Sign in again to pick up where you left off."), 401
        except jwt.InvalidTokenError:
            return jsonify(error="Sign in to continue."), 401
        user = query("SELECT * FROM users WHERE id=?", (int(payload["sub"]),), one=True)
        if user is None:
            return jsonify(error="Account not found."), 401
        g.user = user
        return f(*args, **kwargs)
    return wrapper
