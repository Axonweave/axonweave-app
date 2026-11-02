"""Cryptographic utilities: password hashing, token generation, CSRF."""

import hashlib
import hmac
import secrets
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id parameters benchmarked on a 2-core / 2 GB dev container.
# See docs/argon2-parameters.md for benchmark notes.
_ph = PasswordHasher(
    time_cost=2,       # iterations
    memory_cost=65536, # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


# ── Token generation and hashing (D-20) ──────────────────────────────────────

def generate_token() -> str:
    """Generate a 32-byte URL-safe random token (raw value — never stored)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hash of the raw token — this is what gets stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ── Common passwords list (D-21) ─────────────────────────────────────────────

def _load_common_passwords() -> frozenset[str]:
    path = Path(__file__).parent / "common_passwords.txt"
    if not path.exists():
        return frozenset()
    return frozenset(line.strip().lower() for line in path.read_text().splitlines() if line.strip())


_COMMON_PASSWORDS: frozenset[str] = _load_common_passwords()


def is_password_compromised(password: str) -> bool:
    return password.lower() in _COMMON_PASSWORDS
