from __future__ import annotations

import logging
import os
from contextlib import suppress
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_CRYPTO_KEY_ENV = "REPUTATION_ENV_CRYPTO_KEY"
ENV_CRYPTO_KEY_PATH = REPO_ROOT / "backend" / "reputation" / ".env.reputation.key"
ENV_CRYPTO_PREFIX = "enc:v1:"


def is_encrypted_value(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(ENV_CRYPTO_PREFIX)


def _load_key_bytes(*, create_if_missing: bool) -> bytes | None:
    key_from_env = os.getenv(ENV_CRYPTO_KEY_ENV, "").strip()
    if key_from_env:
        return key_from_env.encode("utf-8")

    if ENV_CRYPTO_KEY_PATH.exists():
        key_from_file = ENV_CRYPTO_KEY_PATH.read_text(encoding="utf-8").strip()
        if key_from_file:
            return key_from_file.encode("utf-8")

    if not create_if_missing:
        return None

    ENV_CRYPTO_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated_key = Fernet.generate_key()
    ENV_CRYPTO_KEY_PATH.write_text(generated_key.decode("utf-8"), encoding="utf-8")
    with suppress(OSError):
        ENV_CRYPTO_KEY_PATH.chmod(0o600)
    return generated_key


def _fernet_or_none(*, create_if_missing: bool) -> Fernet | None:
    key_bytes = _load_key_bytes(create_if_missing=create_if_missing)
    if not key_bytes:
        return None
    try:
        return Fernet(key_bytes)
    except Exception:
        logger.warning("Invalid env crypto key format; keeping raw value.")
        return None


def encrypt_env_secret(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if is_encrypted_value(cleaned):
        return cleaned
    fernet = _fernet_or_none(create_if_missing=True)
    if fernet is None:
        return cleaned
    encrypted = fernet.encrypt(cleaned.encode("utf-8")).decode("utf-8")
    return f"{ENV_CRYPTO_PREFIX}{encrypted}"


def decrypt_env_secret(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if not is_encrypted_value(cleaned):
        return cleaned
    token = cleaned[len(ENV_CRYPTO_PREFIX) :].strip()
    if not token:
        return cleaned
    fernet = _fernet_or_none(create_if_missing=False)
    if fernet is None:
        return cleaned
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Unable to decrypt env secret token; keeping raw value.")
        return cleaned
