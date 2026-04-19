from __future__ import annotations

import base64
import hashlib
import hmac
import os
import string


try:
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover
    bcrypt = None


PBKDF2_ITERATIONS = 200_000
HEXDIGITS = set(string.hexdigits)


def legacy_sha256(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_legacy_sha256_hash(value: str) -> bool:
    return len(value) == 64 and all(char in HEXDIGITS for char in value)


def hash_password(password: str) -> str:
    if bcrypt is not None:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return f"bcrypt${hashed.decode('utf-8')}"

    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        "pbkdf2_sha256$"
        f"{PBKDF2_ITERATIONS}$"
        f"{base64.urlsafe_b64encode(salt).decode('utf-8')}$"
        f"{base64.urlsafe_b64encode(derived).decode('utf-8')}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False

    if stored_hash.startswith("bcrypt$"):
        if bcrypt is None:
            return False
        raw_hash = stored_hash.split("$", 1)[1].encode("utf-8")
        return bcrypt.checkpw(password.encode("utf-8"), raw_hash)

    if stored_hash.startswith("$2") and bcrypt is not None:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))

    if stored_hash.startswith("pbkdf2_sha256$"):
        _, iterations, salt_text, digest_text = stored_hash.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_text.encode("utf-8"))
        expected = base64.urlsafe_b64decode(digest_text.encode("utf-8"))
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(candidate, expected)

    if is_legacy_sha256_hash(stored_hash):
        return hmac.compare_digest(legacy_sha256(password), stored_hash)

    return False


def password_needs_upgrade(stored_hash: str) -> bool:
    return is_legacy_sha256_hash(stored_hash)
