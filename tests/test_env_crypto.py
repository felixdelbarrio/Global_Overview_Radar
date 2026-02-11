from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from reputation import env_crypto


def test_encrypt_decrypt_roundtrip_with_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        env_crypto.ENV_CRYPTO_KEY_ENV, Fernet.generate_key().decode("utf-8")
    )
    raw = "super-secret-value"
    encrypted = env_crypto.encrypt_env_secret(raw)
    assert encrypted.startswith(env_crypto.ENV_CRYPTO_PREFIX)
    assert raw not in encrypted
    assert env_crypto.decrypt_env_secret(encrypted) == raw


def test_encrypt_creates_local_key_file_when_no_env_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_path = tmp_path / ".env.reputation.key"
    monkeypatch.delenv(env_crypto.ENV_CRYPTO_KEY_ENV, raising=False)
    monkeypatch.setattr(env_crypto, "ENV_CRYPTO_KEY_PATH", key_path, raising=False)

    encrypted = env_crypto.encrypt_env_secret("value-123")
    assert key_path.exists()
    assert encrypted.startswith(env_crypto.ENV_CRYPTO_PREFIX)
    assert env_crypto.decrypt_env_secret(encrypted) == "value-123"


def test_decrypt_keeps_raw_when_key_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_path = tmp_path / ".env.reputation.key"
    monkeypatch.delenv(env_crypto.ENV_CRYPTO_KEY_ENV, raising=False)
    monkeypatch.setattr(env_crypto, "ENV_CRYPTO_KEY_PATH", key_path, raising=False)

    raw = "enc:v1:not-a-valid-token"
    assert env_crypto.decrypt_env_secret(raw) == raw


def test_is_encrypted_value() -> None:
    assert env_crypto.is_encrypted_value("enc:v1:abc")
    assert not env_crypto.is_encrypted_value("")
    assert not env_crypto.is_encrypted_value(None)
    assert not env_crypto.is_encrypted_value("plain-value")
