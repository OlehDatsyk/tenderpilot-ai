"""File storage backends.

* ``database`` (default) - stores bytes in the ``stored_files`` table. Persistent wherever the
  PostgreSQL database is persistent (e.g. Render managed PostgreSQL), no extra provider needed.
* ``local`` - stores files on disk under LOCAL_STORAGE_DIR. Only safe in production when that
  directory is on a persistent disk (enforced by settings validation).

Storage keys are server-generated UUIDs - user-supplied filenames never touch the filesystem.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import StoredFile

_KEY_RE = re.compile(r"^[a-z0-9]{2}/[a-f0-9]{32}\.(pdf|docx|txt)$")


class StorageError(RuntimeError):
    pass


def new_storage_key(ext: str) -> str:
    token = uuid.uuid4().hex
    return f"{token[:2]}/{token}.{ext}"


def _validate_key(key: str) -> None:
    if not _KEY_RE.match(key):
        raise StorageError("Invalid storage key.")


def _local_path(key: str) -> Path:
    _validate_key(key)
    base = Path(get_settings().local_storage_dir).resolve()
    path = (base / key).resolve()
    if base not in path.parents:  # defence in depth against traversal
        raise StorageError("Invalid storage path.")
    return path


def save(db: Session, key: str, data: bytes) -> None:
    _validate_key(key)
    if get_settings().storage_backend == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError("Could not write the file to storage.") from exc
    else:
        db.add(StoredFile(key=key, data=data))


def load(db: Session, key: str) -> bytes:
    _validate_key(key)
    if get_settings().storage_backend == "local":
        try:
            return _local_path(key).read_bytes()
        except OSError as exc:
            raise StorageError("The stored file is missing.") from exc
    blob = db.scalar(select(StoredFile.data).where(StoredFile.key == key))
    if blob is None:
        raise StorageError("The stored file is missing.")
    return blob


def remove(db: Session, key: str) -> None:
    _validate_key(key)
    if get_settings().storage_backend == "local":
        try:
            _local_path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Could not delete the stored file.") from exc
    else:
        db.execute(delete(StoredFile).where(StoredFile.key == key))
