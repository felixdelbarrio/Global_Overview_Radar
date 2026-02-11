from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

gcs_storage: Any | None = None
NOT_FOUND_EXCEPTION: type[Exception] | None = None

try:
    import google.cloud.storage as _gcs_storage
    from google.api_core.exceptions import NotFound as _NotFound
except Exception:  # pragma: no cover - optional in local/offline environments
    pass
else:
    gcs_storage = _gcs_storage
    NOT_FOUND_EXCEPTION = _NotFound

logger = logging.getLogger(__name__)

_CLIENT_LOCK = Lock()
_CLIENT: Any | None = None
_CLIENT_INIT_FAILED = False


def _safe_local_path(path: Path, repo_root: Path | None = None) -> Path:
    resolved = path.resolve()
    if repo_root is not None:
        root = repo_root.resolve()
        resolved.relative_to(root)
        return resolved

    # Keep state sync constrained to the local workspace/temp areas.
    allowed_roots = (
        Path.cwd().resolve(),
        Path("/tmp").resolve(),
        Path("/private/var").resolve(),
        Path("/var/folders").resolve(),
    )
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Path outside allowed roots: {resolved}")


def state_bucket_name() -> str:
    return os.getenv("REPUTATION_STATE_BUCKET", "").strip()


def state_prefix() -> str:
    raw = os.getenv("REPUTATION_STATE_PREFIX", "reputation-state").strip()
    return raw.strip("/")


def state_store_enabled() -> bool:
    return bool(state_bucket_name())


def _get_client() -> Any | None:
    global _CLIENT, _CLIENT_INIT_FAILED
    if _CLIENT_INIT_FAILED:
        return None
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if gcs_storage is None:
            _CLIENT_INIT_FAILED = True
            logger.warning(
                "REPUTATION_STATE_BUCKET is set but google-cloud-storage is unavailable."
            )
            return None
        try:
            _CLIENT = gcs_storage.Client()
        except Exception:
            _CLIENT_INIT_FAILED = True
            logger.exception("Failed to initialize Google Cloud Storage client.")
            return None
        return _CLIENT


def _object_key(raw_key: str) -> str:
    key = raw_key.strip().lstrip("/")
    prefix = state_prefix()
    if not prefix:
        return key
    return f"{prefix}/{key}" if key else prefix


def _resolve_relative_key(
    path: Path,
    *,
    key: str | None = None,
    repo_root: Path | None = None,
) -> str:
    if key:
        return key.strip().lstrip("/")
    if repo_root is not None:
        try:
            return path.relative_to(repo_root.resolve()).as_posix()
        except Exception:
            pass
    return f"misc/{path.name}"


def sync_from_state(
    local_path: Path,
    *,
    key: str | None = None,
    repo_root: Path | None = None,
) -> bool:
    if not state_store_enabled():
        return False
    client = _get_client()
    if client is None:
        return False
    bucket_name = state_bucket_name()
    if not bucket_name:
        return False
    try:
        safe_local_path = _safe_local_path(local_path, repo_root=repo_root)
    except ValueError:
        logger.warning("Ignoring unsafe local path for sync_from_state: %s", local_path)
        return False

    object_key = _object_key(_resolve_relative_key(safe_local_path, key=key, repo_root=repo_root))
    blob = client.bucket(bucket_name).blob(object_key)
    try:
        safe_local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(safe_local_path))
        return True
    except Exception as exc:
        if NOT_FOUND_EXCEPTION is not None and isinstance(exc, NOT_FOUND_EXCEPTION):
            return False
        logger.exception("Failed to download state object gs://%s/%s", bucket_name, object_key)
        return False


def sync_to_state(
    local_path: Path,
    *,
    key: str | None = None,
    repo_root: Path | None = None,
) -> bool:
    if not state_store_enabled():
        return False
    client = _get_client()
    if client is None:
        return False
    bucket_name = state_bucket_name()
    if not bucket_name:
        return False
    try:
        safe_local_path = _safe_local_path(local_path, repo_root=repo_root)
    except ValueError:
        logger.warning("Ignoring unsafe local path for sync_to_state: %s", local_path)
        return False
    if not safe_local_path.exists():
        return False
    object_key = _object_key(_resolve_relative_key(safe_local_path, key=key, repo_root=repo_root))
    blob = client.bucket(bucket_name).blob(object_key)
    try:
        blob.upload_from_filename(str(safe_local_path))
        return True
    except Exception:
        logger.exception("Failed to upload state object gs://%s/%s", bucket_name, object_key)
        return False


def delete_from_state(
    local_path: Path,
    *,
    key: str | None = None,
    repo_root: Path | None = None,
) -> bool:
    if not state_store_enabled():
        return False
    client = _get_client()
    if client is None:
        return False
    bucket_name = state_bucket_name()
    if not bucket_name:
        return False
    try:
        safe_local_path = _safe_local_path(local_path, repo_root=repo_root)
    except ValueError:
        logger.warning("Ignoring unsafe local path for delete_from_state: %s", local_path)
        return False
    object_key = _object_key(_resolve_relative_key(safe_local_path, key=key, repo_root=repo_root))
    blob = client.bucket(bucket_name).blob(object_key)
    try:
        blob.delete()
        return True
    except Exception as exc:
        if NOT_FOUND_EXCEPTION is not None and isinstance(exc, NOT_FOUND_EXCEPTION):
            return False
        logger.exception("Failed to delete state object gs://%s/%s", bucket_name, object_key)
        return False
