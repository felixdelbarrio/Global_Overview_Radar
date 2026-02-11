from __future__ import annotations

from pathlib import Path

from reputation import state_store


class _FakeNotFound(Exception):
    pass


class _FakeBlob:
    def __init__(self, objects: dict[str, bytes], key: str) -> None:
        self._objects = objects
        self._key = key

    def download_to_filename(self, path: str) -> None:
        if self._key not in self._objects:
            raise _FakeNotFound("missing object")
        Path(path).write_bytes(self._objects[self._key])

    def upload_from_filename(self, path: str) -> None:
        self._objects[self._key] = Path(path).read_bytes()

    def delete(self) -> None:
        if self._key not in self._objects:
            raise _FakeNotFound("missing object")
        del self._objects[self._key]


class _FakeBucket:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self._objects, key)


class _FakeClient:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def bucket(self, _: str) -> _FakeBucket:
        return _FakeBucket(self._objects)


class _FakeStorageModule:
    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    def Client(self) -> _FakeClient:  # noqa: N802
        return self._client


def _reset_state_store() -> None:
    state_store._CLIENT = None
    state_store._CLIENT_INIT_FAILED = False


def test_state_store_disabled_without_bucket(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("REPUTATION_STATE_BUCKET", raising=False)
    _reset_state_store()

    target = tmp_path / "state.json"
    assert state_store.state_store_enabled() is False
    assert state_store.sync_from_state(target) is False
    assert state_store.sync_to_state(target) is False
    assert state_store.delete_from_state(target) is False


def test_state_store_sync_roundtrip_with_relative_key(
    monkeypatch, tmp_path: Path
) -> None:
    objects: dict[str, bytes] = {}
    fake_client = _FakeClient(objects)
    monkeypatch.setenv("REPUTATION_STATE_BUCKET", "test-bucket")
    monkeypatch.setenv("REPUTATION_STATE_PREFIX", "gor-state")
    monkeypatch.setattr(
        state_store, "gcs_storage", _FakeStorageModule(fake_client), raising=False
    )
    monkeypatch.setattr(state_store, "NotFound", _FakeNotFound, raising=False)
    _reset_state_store()

    repo_root = tmp_path
    local_file = tmp_path / "data" / "cache" / "reputation_cache.json"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_text('{"ok":true}', encoding="utf-8")

    assert state_store.sync_to_state(local_file, repo_root=repo_root) is True
    local_file.unlink()
    assert state_store.sync_from_state(local_file, repo_root=repo_root) is True
    assert local_file.read_text(encoding="utf-8") == '{"ok":true}'

    stored_key = "gor-state/data/cache/reputation_cache.json"
    assert stored_key in objects

    assert state_store.delete_from_state(local_file, repo_root=repo_root) is True
    assert state_store.sync_from_state(local_file, repo_root=repo_root) is False


def test_state_store_handles_client_init_error(monkeypatch, tmp_path: Path) -> None:
    class _BrokenStorageModule:
        def Client(self):  # noqa: N802
            raise RuntimeError("boom")

    monkeypatch.setenv("REPUTATION_STATE_BUCKET", "test-bucket")
    monkeypatch.setattr(
        state_store, "gcs_storage", _BrokenStorageModule(), raising=False
    )
    _reset_state_store()

    local_file = tmp_path / "state.json"
    local_file.write_text("{}", encoding="utf-8")
    assert state_store.sync_to_state(local_file, key="state.json") is False
    assert state_store._CLIENT_INIT_FAILED is True
