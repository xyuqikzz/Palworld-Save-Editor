from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any, Iterable

from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.domain.commands import (
    AddPal,
    ClearItemSlot,
    ClonePal,
    DeletePal,
    MovePal,
    PutItem,
    RecoverDetachedPal,
    SessionCommand,
    UpdateItemCount,
    UpdateDynamicItemAttributes,
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
    UpdatePlayerIdentity,
    UpdatePlayerProgression,
    UpdatePlayerTechnology,
)
from palworld_pal_editor.domain.errors import DomainError

from .character_editor import CharacterEditor
from .inventory_editor import InventoryEditor
from .save_session import SaveSession
from .structural_pal_editor import StructuralPalEditor


InventoryCommand = (
    UpdateItemCount | PutItem | ClearItemSlot | UpdateDynamicItemAttributes
)
CharacterCommand = (
    UpdatePlayerIdentity
    | UpdatePlayerProgression
    | UpdatePlayerTechnology
    | UpdatePalIdentity
    | UpdatePalProgression
    | UpdatePalSkills
    | UpdatePalEnhancement
)
StructuralCommand = AddPal | ClonePal | MovePal | DeletePal | RecoverDetachedPal
BatchableCommand = InventoryCommand | CharacterCommand | StructuralCommand


class BatchEditor:
    """Whole-batch atomic execution over the existing command Interfaces."""

    # Five current inventory containers can legitimately exceed 100 occupied
    # slots, and multi-player preset application must still be one transaction.
    MAX_OPERATIONS = 1_000

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def preview(
        self,
        *,
        session_id: str,
        expected_revision: int,
        operations: Iterable[BatchableCommand],
    ) -> dict[str, Any]:
        commands = tuple(operations)
        self._validate_commands(
            session_id=session_id,
            expected_revision=expected_revision,
            commands=commands,
        )
        impact = {
            "operation_count": len(commands),
            "operations": [self._operation_impact(command) for command in commands],
            "atomicity": "all_or_nothing",
        }
        return {
            "session_id": session_id,
            "revision": expected_revision,
            "impact": impact,
            "impact_token": self._impact_token(commands, impact),
        }

    def execute(
        self,
        *,
        session_id: str,
        expected_revision: int,
        operations: Iterable[BatchableCommand],
        impact_token: str,
    ) -> dict[str, Any]:
        commands = tuple(operations)
        preview = self.preview(
            session_id=session_id,
            expected_revision=expected_revision,
            operations=commands,
        )
        if not isinstance(impact_token, str) or not impact_token:
            raise DomainError(
                code="IMPACT_PREVIEW_REQUIRED",
                message="Batch execution requires a current impact preview.",
                field="impact_token",
                http_status=409,
            )
        if impact_token != preview["impact_token"]:
            raise DomainError(
                code="IMPACT_PREVIEW_STALE",
                message="The batch impact changed; preview it again.",
                field="impact_token",
                retryable=True,
                http_status=409,
            )

        def mutate() -> list[Any]:
            return [self._execute_one(command) for command in commands]

        entry, results = self._session.run_batch(
            session_id=session_id,
            expected_revision=expected_revision,
            command="BatchCommand",
            target={
                "operation_count": len(commands),
                "commands": [type(command).__name__ for command in commands],
            },
            mutate=mutate,
            validate=self._validate_global,
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "operation_count": len(commands),
            "results": results,
        }

    def _execute_one(self, command: BatchableCommand):
        if isinstance(
            command,
            (
                UpdateItemCount,
                PutItem,
                ClearItemSlot,
                UpdateDynamicItemAttributes,
            ),
        ):
            if isinstance(command, UpdateDynamicItemAttributes):
                from .dynamic_attribute_editor import DynamicAttributeEditor

                return DynamicAttributeEditor(self._session).execute(command)
            return InventoryEditor(self._session).execute(command)
        if isinstance(
            command,
            (
                UpdatePlayerIdentity,
                UpdatePlayerProgression,
                UpdatePlayerTechnology,
                UpdatePalIdentity,
                UpdatePalProgression,
                UpdatePalSkills,
                UpdatePalEnhancement,
            ),
        ):
            return CharacterEditor(self._session).execute(command)
        if isinstance(
            command, (AddPal, ClonePal, MovePal, DeletePal, RecoverDetachedPal)
        ):
            return StructuralPalEditor(self._session).execute(command)
        raise DomainError(
            code="UNSUPPORTED_COMMAND",
            message="The batch contains an unsupported command.",
            http_status=400,
        )

    def _validate_commands(
        self,
        *,
        session_id: str,
        expected_revision: int,
        commands: tuple[BatchableCommand, ...],
    ) -> None:
        self._session.require_command(session_id, expected_revision)
        if not commands:
            raise DomainError(
                code="EMPTY_BATCH",
                message="A batch command must contain at least one operation.",
                http_status=400,
            )
        if len(commands) > self.MAX_OPERATIONS:
            raise DomainError(
                code="BATCH_TOO_LARGE",
                message="The batch exceeds the supported operation limit.",
                details={
                    "operation_count": len(commands),
                    "max_operations": self.MAX_OPERATIONS,
                },
                http_status=400,
            )
        for index, command in enumerate(commands):
            if not isinstance(command, SessionCommand):
                raise DomainError(
                    code="UNSUPPORTED_COMMAND",
                    message="The batch contains an unsupported command.",
                    details={"operation_index": index},
                    http_status=400,
                )
            if (
                command.session_id != session_id
                or command.expected_revision != expected_revision
            ):
                raise DomainError(
                    code="BATCH_REVISION_MISMATCH",
                    message="Every batch operation must use the batch session and revision.",
                    details={"operation_index": index},
                    http_status=409,
                )

    def _operation_impact(self, command: BatchableCommand) -> dict[str, Any]:
        payload = asdict(command)
        payload.pop("session_id", None)
        payload.pop("expected_revision", None)
        result: dict[str, Any] = {
            "command": type(command).__name__,
            "target": payload,
        }
        pal_id = getattr(command, "pal_id", None) or getattr(
            command, "source_pal_id", None
        )
        if pal_id is not None and all(
            hasattr(self._session.manager, name)
            for name in (
                "_entities_list",
                "container_data",
                "group_data",
                "player_mapping",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            result["character_references"] = CharacterIndex(
                self._session.manager
            ).delete_impact(str(pal_id))
        if isinstance(
            command,
            (
                UpdateItemCount,
                PutItem,
                ClearItemSlot,
                UpdateDynamicItemAttributes,
            ),
        ):
            _player, container = InventoryEditor(
                self._session
            )._resolve_owned_container(command.player_id, command.container_type)
            try:
                result["current_slot"] = container.slot_summary(command.slot_index)
            except KeyError:
                result["current_slot"] = {
                    "slot_index": command.slot_index,
                    "state": "empty",
                }
        return result

    def _validate_global(self) -> None:
        manager = self._session.manager
        dynamic_items = getattr(manager, "dynamic_item_data", None)
        if dynamic_items is not None:
            dynamic_items.assert_consistent()
        if all(
            hasattr(manager, name)
            for name in (
                "_entities_list",
                "container_data",
                "group_data",
                "player_mapping",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            issues = CharacterIndex(manager).hard_issues()
            if issues:
                raise DomainError(
                    code="CHARACTER_INDEX_INVARIANT_FAILED",
                    message="The batch produced inconsistent character references.",
                    details={"issues": [issue.to_dict() for issue in issues]},
                    http_status=409,
                )

    def _impact_token(
        self, commands: tuple[BatchableCommand, ...], impact: dict[str, Any]
    ) -> str:
        payload = {
            "session_id": self._session.session_id,
            "revision": self._session.revision,
            "commands": [asdict(command) for command in commands],
            "impact": impact,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
