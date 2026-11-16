"""Password hashing, JWT access tokens, opaque refresh tokens and secret encryption."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id with library defaults
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - token type label, not a secret


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> str | None:
    """Return an error message if the password is too weak, otherwise None."""
    if len(password) < 10:
        return "Password must be at least 10 characters long."
    if len(password) > 128:
        return "Password must be at most 128 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def create_access_token(user_id: uuid.UUID, token_version: int) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "ver": token_version,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub", "type"]})
    except jwt.PyJWTError:
        return None
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        return None
    return payload


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- secret encryption (AI keys)


class EncryptionUnavailableError(RuntimeError):
    pass


def _fernet() -> Fernet:
    # Accept standard base64 too (e.g. Render's generateValue), normalising to the URL-safe alphabet.
    key = get_settings().encryption_key.strip().replace("+", "-").replace("/", "_")
    if not key:
        raise EncryptionUnavailableError("ENCRYPTION_KEY is not configured on the server.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:  # malformed key
        raise EncryptionUnavailableError("ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encryption_available() -> bool:
    try:
        _fernet()
        return True
    except EncryptionUnavailableError:
        return False


def encrypt_secret(plaintext: str) -> str:
    """Authenticated encryption (Fernet = AES-128-CBC + HMAC-SHA256)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionUnavailableError("Stored secret could not be decrypted (wrong ENCRYPTION_KEY?).") from exc


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 8 else "•" * 8


def generate_fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
