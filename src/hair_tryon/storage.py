from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4


class StorageError(RuntimeError):
    """Base error for temporary image storage operations."""


class ReadAccessRevoked(StorageError):
    """Raised when an ended session attempts to read an image."""


class StorageSessionState(str, Enum):
    ACTIVE = "active"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class StoredImage:
    image_id: str
    sha256: str


@dataclass
class _SessionStorage:
    directory: Path
    images: dict[str, Path] = field(default_factory=dict)
    state: StorageSessionState = StorageSessionState.ACTIVE
    read_authorized: bool = True
    deletion_retries: int = 0


class TempImageStore:
    MAX_DELETION_RETRIES = 3

    def __init__(
        self,
        root: Path,
        *,
        delete_tree: Callable[[Path], None] = shutil.rmtree,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._delete_tree = delete_tree
        self._sessions: dict[str, _SessionStorage] = {}

    def create_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            return
        directory = self._root / uuid4().hex
        directory.mkdir()
        self._sessions[session_id] = _SessionStorage(directory=directory)

    def save_image(self, session_id: str, image_bytes: bytes) -> StoredImage:
        session = self._sessions[session_id]
        image_id = uuid4().hex
        path = session.directory / image_id
        path.write_bytes(image_bytes)
        session.images[image_id] = path
        return StoredImage(
            image_id=image_id,
            sha256=hashlib.sha256(image_bytes).hexdigest(),
        )

    def read_image(self, session_id: str, image_id: str) -> bytes:
        session = self._sessions[session_id]
        if not session.read_authorized:
            raise ReadAccessRevoked(f"session {session_id} read access was revoked")
        return session.images[image_id].read_bytes()

    def end_session(self, session_id: str) -> StorageSessionState:
        session = self._sessions[session_id]
        session.read_authorized = False
        try:
            self._delete_tree(session.directory)
        except OSError:
            session.state = StorageSessionState.DELETION_PENDING
            return session.state
        session.images.clear()
        session.state = StorageSessionState.DELETED
        return session.state

    def retry_deletion(self, session_id: str) -> StorageSessionState:
        session = self._sessions[session_id]
        if session.state is not StorageSessionState.DELETION_PENDING:
            return session.state
        if session.deletion_retries >= self.MAX_DELETION_RETRIES:
            return session.state

        session.deletion_retries += 1
        try:
            self._delete_tree(session.directory)
        except OSError:
            return session.state
        session.images.clear()
        session.state = StorageSessionState.DELETED
        return session.state
