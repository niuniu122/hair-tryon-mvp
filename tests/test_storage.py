from __future__ import annotations

import hashlib
import shutil

import pytest


def test_saved_image_is_addressed_by_opaque_id_and_sha256(tmp_path) -> None:
    from hair_tryon.storage import TempImageStore

    image_bytes = b"private-image-content"
    store = TempImageStore(tmp_path)
    store.create_session("session-1")

    stored = store.save_image("session-1", image_bytes)

    assert stored.sha256 == hashlib.sha256(image_bytes).hexdigest()
    assert stored.image_id
    assert "/" not in stored.image_id
    assert "\\" not in stored.image_id
    assert not hasattr(stored, "path")
    assert store.read_image("session-1", stored.image_id) == image_bytes


def test_ending_session_revokes_reads_and_physically_deletes_images(tmp_path) -> None:
    from hair_tryon.storage import (
        ReadAccessRevoked,
        StorageSessionState,
        TempImageStore,
    )

    store = TempImageStore(tmp_path)
    store.create_session("session-1")
    stored = store.save_image("session-1", b"private-image-content")

    state = store.end_session("session-1")

    assert state is StorageSessionState.DELETED
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ReadAccessRevoked):
        store.read_image("session-1", stored.image_id)


def test_failed_physical_deletion_is_pending_but_read_access_stays_revoked(
    tmp_path,
) -> None:
    from hair_tryon.storage import (
        ReadAccessRevoked,
        StorageSessionState,
        TempImageStore,
    )

    def fail_delete(_path) -> None:
        raise PermissionError("file is still in use")

    store = TempImageStore(tmp_path, delete_tree=fail_delete)
    store.create_session("session-1")
    stored = store.save_image("session-1", b"private-image-content")

    state = store.end_session("session-1")

    assert state is StorageSessionState.DELETION_PENDING
    assert any(tmp_path.iterdir())
    with pytest.raises(ReadAccessRevoked):
        store.read_image("session-1", stored.image_id)


def test_pending_deletion_retries_at_most_three_times(tmp_path) -> None:
    from hair_tryon.storage import StorageSessionState, TempImageStore

    delete_calls = []

    def fail_delete(path) -> None:
        delete_calls.append(path)
        raise PermissionError("file is still in use")

    store = TempImageStore(tmp_path, delete_tree=fail_delete)
    store.create_session("session-1")
    store.save_image("session-1", b"private-image-content")
    assert store.end_session("session-1") is StorageSessionState.DELETION_PENDING

    states = [store.retry_deletion("session-1") for _ in range(4)]

    assert states == [StorageSessionState.DELETION_PENDING] * 4
    assert len(delete_calls) == 4  # one initial attempt plus three retries


def test_successful_retry_physically_deletes_pending_session(tmp_path) -> None:
    from hair_tryon.storage import StorageSessionState, TempImageStore

    delete_attempt = 0

    def fail_once_then_delete(path) -> None:
        nonlocal delete_attempt
        delete_attempt += 1
        if delete_attempt == 1:
            raise PermissionError("file is still in use")
        shutil.rmtree(path)

    store = TempImageStore(tmp_path, delete_tree=fail_once_then_delete)
    store.create_session("session-1")
    store.save_image("session-1", b"private-image-content")
    assert store.end_session("session-1") is StorageSessionState.DELETION_PENDING

    state = store.retry_deletion("session-1")

    assert state is StorageSessionState.DELETED
    assert list(tmp_path.iterdir()) == []
