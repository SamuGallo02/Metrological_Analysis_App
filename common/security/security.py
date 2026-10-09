"""Passwords and tokens. No password or token is stored in plain text. Used by server and client."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Tuple

from ..errors import AppError

ITERATIONS = 240_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 8


def validate_username(name: str) -> str:
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        raise AppError("Invalid username: 3-32 characters among letters, digits, '_', '.', '-'.")
    return name


def validate_password(pw: str) -> str:
    if not isinstance(pw, str) or len(pw) < MIN_PASSWORD:
        raise AppError("The password must be at least {n} characters long.", n=MIN_PASSWORD)
    if len(pw) > 256:
        raise AppError("Password too long.")
    return pw


def hash_password(password: str, salt_hex: str | None = None, iterations: int = ITERATIONS) -> Tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    return salt.hex(), hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def verify_password(password: str, salt_hex: str, hash_hex: str, iterations: int = ITERATIONS) -> bool:
    return hmac.compare_digest(hash_password(password, salt_hex, iterations)[1], hash_hex)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
