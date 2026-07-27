from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any, Callable
import uuid

from palworld_save_tools.archive import UUID
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.paltypes import (
    PALWORLD_TYPE_HINTS,
)

from palworld_pal_editor.core.pal_objects import UUID2HexStr
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


@dataclass(frozen=True)
class _DocumentTarget:
    relative_path: str
    kind: str
    player_id: str | None
    compression_type: int
    custom_properties: dict[str, Any]
    affected_record: str
    get_gvas: Callable[[], GvasFile]
    set_gvas: Callable[[GvasFile], None]


class RawJsonEditor:
    """Full GVAS JSON access behind the current save-session boundary."""

    _BINARY_KEY = "$palworld_binary_base64"

    def list_files(self, session: SaveSession) -> list[dict[str, Any]]:
        workspace = session.workspace
        files: list[dict[str, Any]] = []
        level_path = workspace / "Level.sav"
        if level_path.is_file():
            files.append(self._file_summary(level_path, workspace, kind="level"))

        for player in session.list_players():
            path = workspace / "Players" / f"{UUID2HexStr(player.player_id)}.sav"
            if not path.is_file():
                continue
            summary = self._file_summary(path, workspace, kind="player")
            summary["player_name"] = player.name
            summary["player_id"] = player.player_id
            files.append(summary)
        return files

    def read_document(
        self, session: SaveSession, relative_path: str
    ) -> dict[str, Any]:
        started = perf_counter()
        target = self._resolve_target(session, relative_path)
        try:
            compact_gvas = deepcopy(target.get_gvas())
            raw_gvas = compact_gvas.write(target.custom_properties)
            text = json.dumps(
                self._json_safe(target.get_gvas().dump()),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="RAW_JSON_PARSE_FAILED",
                message="The selected save file could not be expanded into editable JSON.",
                field="path",
                details={
                    "path": target.relative_path,
                    "reason": str(error),
                },
                http_status=422,
            ) from error
        finally:
            session.record_operation_seconds(
                "raw_json.read", perf_counter() - started
            )

        encoded_size = len(text.encode("utf-8"))
        return {
            "path": target.relative_path,
            "kind": target.kind,
            "player_id": target.player_id,
            "revision": session.revision,
            "text": text,
            "json_size": encoded_size,
            "gvas_size": len(raw_gvas),
            "sha256": hashlib.sha256(raw_gvas).hexdigest(),
        }

    def apply_document(
        self,
        session: SaveSession,
        *,
        session_id: str,
        expected_revision: int,
        relative_path: str,
        text: str,
    ) -> dict[str, Any]:
        session.require_command(
            session_id,
            expected_revision,
            allow_raw_json=True,
        )
        target = self._resolve_target(session, relative_path)
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise DomainError(
                code="RAW_JSON_INVALID",
                message="The document is not valid JSON.",
                field="json",
                details={
                    "line": error.lineno,
                    "column": error.colno,
                    "position": error.pos,
                },
                http_status=400,
            ) from error

        try:
            edited_gvas = GvasFile.load(self._restore_json_safe(document))
            raw_gvas = edited_gvas.write(target.custom_properties)
            compact_gvas = GvasFile.read(
                raw_gvas,
                PALWORLD_TYPE_HINTS,
                target.custom_properties,
            )
            current_raw = deepcopy(target.get_gvas()).write(
                target.custom_properties
            )
        except Exception as error:
            raise DomainError(
                code="RAW_JSON_SERIALIZATION_FAILED",
                message=(
                    "The JSON syntax is valid, but the document cannot be "
                    "serialized as a Palworld save."
                ),
                field="json",
                details={
                    "path": target.relative_path,
                    "reason": str(error),
                },
                http_status=422,
            ) from error

        before_hash = hashlib.sha256(current_raw).hexdigest()
        after_hash = hashlib.sha256(raw_gvas).hexdigest()
        if raw_gvas == current_raw:
            return {
                "changed": False,
                "revision": session.revision,
                "pending_change_count": len(session.changes()),
                "path": target.relative_path,
                "sha256": after_hash,
            }

        entry = session.apply_atomic(
            session_id=session_id,
            expected_revision=expected_revision,
            command="ApplyRawJson",
            target={"path": target.relative_path, "kind": target.kind},
            snapshot=target.get_gvas,
            restore=target.set_gvas,
            before=lambda: {
                "sha256": before_hash,
                "gvas_size": len(current_raw),
            },
            mutate=lambda: target.set_gvas(compact_gvas),
            validate=lambda: None,
            after=lambda: {
                "sha256": after_hash,
                "gvas_size": len(raw_gvas),
            },
            affected_records=(target.affected_record,),
            allow_raw_json=True,
        )
        session.mark_raw_json_pending()
        return {
            "changed": True,
            "revision": session.revision,
            "pending_change_count": len(session.changes()),
            "path": target.relative_path,
            "sha256": after_hash,
            "change": entry.to_dict(),
        }

    def _resolve_target(
        self, session: SaveSession, relative_path: str
    ) -> _DocumentTarget:
        normalized = self._normalize_relative_path(relative_path)
        manager = session.manager
        if normalized == "Level.sav":
            gvas = getattr(manager, "gvas_file", None)
            compression_type = getattr(manager, "_compression_times", None)
            if gvas is None or compression_type is None:
                raise self._unsupported_file(normalized)
            return _DocumentTarget(
                relative_path=normalized,
                kind="level",
                player_id=None,
                compression_type=compression_type,
                custom_properties=MAIN_SKIP_PROPERTIES,
                affected_record="level:RawJson",
                get_gvas=lambda: manager.gvas_file,
                set_gvas=lambda value: setattr(manager, "gvas_file", value),
            )

        path = PurePosixPath(normalized)
        player_hex = path.stem.upper()
        player = next(
            (
                value
                for value in (getattr(manager, "player_mapping", None) or {}).values()
                if UUID2HexStr(value.PlayerUId) == player_hex
            ),
            None,
        )
        if player is None:
            raise self._unsupported_file(normalized)
        player_id = str(player.PlayerUId)
        player = session.load_player(player_id)
        if player.PlayerGVAS is None:
            raise self._unsupported_file(normalized)
        _gvas, compression_type = player.PlayerGVAS
        return _DocumentTarget(
            relative_path=f"Players/{UUID2HexStr(player_id)}.sav",
            kind="player",
            player_id=player_id,
            compression_type=compression_type,
            custom_properties=PLAYER_SKIP_PROPERTIES,
            affected_record=f"player_file:{player_id}",
            get_gvas=lambda: player.PlayerGVAS[0],
            set_gvas=lambda value: setattr(
                player,
                "PlayerGVAS",
                (value, compression_type),
            ),
        )

    @staticmethod
    def _normalize_relative_path(relative_path: str) -> str:
        if not isinstance(relative_path, str) or not relative_path:
            raise DomainError(
                code="RAW_JSON_FILE_UNSUPPORTED",
                message="Choose a supported save file.",
                field="path",
                http_status=400,
            )
        path = PurePosixPath(relative_path.replace("\\", "/"))
        parts = path.parts
        if parts == ("Level.sav",):
            return "Level.sav"
        if (
            len(parts) == 2
            and parts[0] == "Players"
            and parts[1].lower().endswith(".sav")
            and len(PurePosixPath(parts[1]).stem) == 32
        ):
            try:
                int(PurePosixPath(parts[1]).stem, 16)
            except ValueError:
                pass
            else:
                return f"Players/{parts[1]}"
        raise DomainError(
            code="RAW_JSON_FILE_UNSUPPORTED",
            message="Only Level.sav and mapped Players/*.sav files can be edited.",
            field="path",
            details={"path": relative_path},
            http_status=400,
        )

    @staticmethod
    def _file_summary(path: Path, workspace: Path, *, kind: str) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": path.relative_to(workspace).as_posix(),
            "name": path.name,
            "kind": kind,
            "size": stat.st_size,
            "modified_at_ns": stat.st_mtime_ns,
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, (UUID, uuid.UUID)):
            return str(value)
        if isinstance(value, bytes):
            return {
                RawJsonEditor._BINARY_KEY: base64.b64encode(value).decode("ascii"),
            }
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(
                "Non-finite float values cannot be represented as JSON."
            )
        if isinstance(value, dict):
            return {
                str(key): RawJsonEditor._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [RawJsonEditor._json_safe(item) for item in value]
        return value

    @staticmethod
    def _restore_json_safe(value: Any) -> Any:
        if (
            isinstance(value, dict)
            and set(value) == {RawJsonEditor._BINARY_KEY}
        ):
            encoded = value[RawJsonEditor._BINARY_KEY]
            if not isinstance(encoded, str):
                raise ValueError("Encoded binary save data must be a string.")
            return base64.b64decode(encoded, validate=True)
        if isinstance(value, dict):
            return {
                key: RawJsonEditor._restore_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [RawJsonEditor._restore_json_safe(item) for item in value]
        return value

    @staticmethod
    def _unsupported_file(relative_path: str) -> DomainError:
        return DomainError(
            code="RAW_JSON_FILE_UNSUPPORTED",
            message="The selected save file is not available for JSON editing.",
            field="path",
            details={"path": relative_path},
            http_status=404,
        )
