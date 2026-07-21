from __future__ import annotations

from typing import Protocol

from palworld_pal_editor.domain.models import (
    OpenedSave,
    SaveSource,
    StorageCommitRequest,
    StorageCommitResult,
)


class SaveStorage(Protocol):
    def open(self, source: SaveSource) -> OpenedSave: ...

    def commit(self, request: StorageCommitRequest) -> StorageCommitResult: ...

    def close(self, opened: OpenedSave) -> None: ...
