from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Callable
import uuid

from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.domain.commands import (
    AddPal,
    ClonePal,
    DeletePal,
    MovePal,
    RecoverDetachedPal,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import CharacterContainerType
from palworld_pal_editor.utils.data_provider import DataProvider

from .save_session import SaveSession


StructuralPalCommand = AddPal | ClonePal | MovePal | DeletePal | RecoverDetachedPal


class StructuralPalEditor:
    """Atomic structural edits across character records and their reverse indexes."""

    FAILURE_POINTS = (
        "after_character_record_insert",
        "after_source_slot_remove",
        "after_target_slot_add",
        "after_owner_index_update",
        "after_group_index_update",
        "before_invariant_commit",
    )

    def __init__(
        self,
        session: SaveSession,
        *,
        id_factory: Callable[[], object] | None = None,
        failure_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._session = session
        self._id_factory = id_factory or uuid.uuid4
        self._failure_hook = failure_hook

    def preview_delete(
        self,
        *,
        pal_id: str,
        session_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        self._session.require_command(session_id, expected_revision)
        index = CharacterIndex(self._session.manager)
        pal = index.pals.get(str(pal_id))
        if pal is None:
            raise self._error(
                "PAL_NOT_FOUND", "Pal not found.", "pal_id", status=404
            )
        self._assert_no_hard_issues(index)
        impact = index.delete_impact(str(pal_id))
        return {
            "session_id": self._session.session_id,
            "revision": self._session.revision,
            "impact": impact,
            "impact_token": self._impact_token(impact),
        }

    def preview_clone(self, command: ClonePal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        source = self._indexed_pal(index, command.source_pal_id)
        if source.is_unreferenced_pal:
            raise self._error(
                "PAL_NOT_ATTACHED",
                "A detached Pal must be recovered before it can be cloned.",
                "source_pal_id",
                status=409,
            )
        self._validate_clone_fields(source)
        player = self._player(command.target_player_id)
        container = self._target_container(
            player, command.container_type, command.target_slot
        )
        impact = self._clone_impact(source, player, container, command)
        return self._preview_result(impact)

    def preview_move(self, command: MovePal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        pal, source_ref, source_container, player, target_container = (
            self._resolve_move(index, command)
        )
        impact = self._move_impact(
            pal,
            source_ref,
            source_container,
            player,
            target_container,
            command,
        )
        return self._preview_result(impact)

    def execute(self, command: StructuralPalCommand) -> dict[str, Any]:
        if isinstance(command, AddPal):
            return self._add(command)
        if isinstance(command, ClonePal):
            return self._clone(command)
        if isinstance(command, MovePal):
            return self._move(command)
        if isinstance(command, DeletePal):
            return self._delete(command)
        if isinstance(command, RecoverDetachedPal):
            return self._recover(command)
        raise self._error(
            "UNSUPPORTED_COMMAND", "Unsupported structural Pal command.", status=400
        )

    def _add(self, command: AddPal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        player = self._player(command.player_id)
        self._validate_species(command.species_id)
        container = self._target_container(
            player, command.container_type, command.target_slot
        )
        group = self._group(player.group_id)
        pal_id = self._unique_id(index)
        context: dict[str, Any] = {"pal_id": pal_id}

        def mutate() -> None:
            pal_obj = PalObjects.PalSaveParameter(
                pal_id,
                player.PlayerUId,
                container.ID,
                command.target_slot or 0,
                player.group_id,
            )
            pal = PalEntity(pal_obj)
            pal.CharacterID = command.species_id
            if pal.IsHuman:
                pal.equip_all_pal_attacks()
            pal.is_new_pal = True
            context["pal"] = pal
            self._session.manager._entities_list.append(pal_obj)
            self._fail("after_character_record_insert", context)
            slot = container.add_pal(pal_id, command.target_slot)
            if slot < 0:
                raise self._error(
                    "CHARACTER_CONTAINER_FULL",
                    "The target character container has no available slot.",
                    "target_slot",
                    status=409,
                )
            pal.SlotId = (container.ID, slot)
            self._fail("after_target_slot_add", {**context, "slot": slot})
            self._assign_owner_if_changed(pal, player)
            if not player.add_pal(pal):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The generated Pal instance ID already exists.",
                    status=409,
                )
            self._fail("after_owner_index_update", context)
            if not group.add_pal(pal_id):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The generated Pal instance ID already exists in the group.",
                    status=409,
                )
            self._fail("after_group_index_update", context)
            player.record_new_pal(pal)
            self._fail("before_invariant_commit", context)

        entry = self._apply(
            command=command,
            command_name="add_pal",
            target={"player_id": str(player.PlayerUId), "pal_id": pal_id},
            before=lambda: self._world_summary(),
            mutate=mutate,
            validate=lambda: self._validate_attached_pal(pal_id),
            after=lambda: self._pal_summary(context["pal"]),
            affected_records=(
                "level:CharacterSaveParameterMap",
                f"player_file:{player.PlayerUId}",
            ),
        )
        return {"change": entry.to_dict(), "pal": self._pal_summary(context["pal"])}

    def _clone(self, command: ClonePal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        source = self._indexed_pal(index, command.source_pal_id)
        if source.is_unreferenced_pal:
            raise self._error(
                "PAL_NOT_ATTACHED",
                "A detached Pal must be recovered before it can be cloned.",
                "source_pal_id",
                status=409,
            )
        self._validate_clone_fields(source)
        player = self._player(command.target_player_id)
        container = self._target_container(
            player, command.container_type, command.target_slot
        )
        impact = self._clone_impact(source, player, container, command)
        self._require_impact_preview(command.impact_token, impact, "clone")
        group = self._group(player.group_id)
        pal_id = self._unique_id(index)
        equip_id = self._unique_id(index, extra={pal_id})
        context: dict[str, Any] = {"pal_id": pal_id}

        def mutate() -> None:
            pal_obj = deepcopy(source._pal_obj)
            pal = PalEntity(pal_obj)
            pal.assign_clone_identity(pal_id, equip_id)
            context["pal"] = pal
            self._session.manager._entities_list.append(pal_obj)
            self._fail("after_character_record_insert", context)
            slot = container.add_pal(pal_id, command.target_slot)
            if slot < 0:
                raise self._error(
                    "CHARACTER_CONTAINER_FULL",
                    "The target character container has no available slot.",
                    "target_slot",
                    status=409,
                )
            pal.SlotId = (container.ID, slot)
            self._fail("after_target_slot_add", {**context, "slot": slot})
            self._assign_owner_if_changed(pal, player)
            if not player.add_pal(pal):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The generated Pal instance ID already exists.",
                    status=409,
                )
            self._fail("after_owner_index_update", context)
            if not group.add_pal(pal_id):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The generated Pal instance ID already exists in the group.",
                    status=409,
                )
            self._fail("after_group_index_update", context)
            player.record_new_pal(pal)
            self._fail("before_invariant_commit", context)

        entry = self._apply(
            command=command,
            command_name="clone_pal",
            target={
                "source_pal_id": str(source.InstanceId),
                "target_player_id": str(player.PlayerUId),
                "pal_id": pal_id,
            },
            before=lambda: {
                "world": self._world_summary(),
                "source": self._pal_summary(source),
            },
            mutate=mutate,
            validate=lambda: self._validate_clone(source, context["pal"]),
            after=lambda: {
                "source": self._pal_summary(source),
                "clone": self._pal_summary(context["pal"]),
            },
            affected_records=(
                "level:CharacterSaveParameterMap",
                f"player_file:{player.PlayerUId}",
            ),
        )
        return {"change": entry.to_dict(), "pal": self._pal_summary(context["pal"])}

    def _move(self, command: MovePal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        pal, source_ref, source_container, player, target_container = (
            self._resolve_move(index, command)
        )
        impact = self._move_impact(
            pal,
            source_ref,
            source_container,
            player,
            target_container,
            command,
        )
        self._require_impact_preview(command.impact_token, impact, "move")
        group = self._group(player.group_id)
        pal_id = str(pal.InstanceId)
        before = self._pal_summary(pal)

        def mutate() -> None:
            source_container.del_pal(pal_id)
            self._fail("after_source_slot_remove", {"pal_id": pal_id})
            slot = target_container.add_pal(pal_id, command.target_slot)
            if slot < 0:
                raise self._error(
                    "CHARACTER_CONTAINER_FULL",
                    "The target character container has no available slot.",
                    "target_slot",
                    status=409,
                )
            pal.SlotId = (target_container.ID, slot)
            self._fail("after_target_slot_add", {"pal_id": pal_id, "slot": slot})
            self._remove_owner_references(pal_id)
            self._session.manager.baseworker_mapping.pop(pal_id, None)
            self._session.manager._dangling_pals.pop(pal_id, None)
            self._assign_owner_if_changed(pal, player)
            if not player.add_pal(pal):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The target owner already indexes this Pal.",
                    status=409,
                )
            self._fail("after_owner_index_update", {"pal_id": pal_id})
            self._remove_group_references(pal_id)
            if not group.add_pal(pal_id):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The target group already indexes this Pal.",
                    status=409,
                )
            self._fail("after_group_index_update", {"pal_id": pal_id})
            pal.is_unreferenced_pal = False
            self._fail("before_invariant_commit", {"pal_id": pal_id})

        entry = self._apply(
            command=command,
            command_name="move_pal",
            target={"pal_id": pal_id, "target_player_id": str(player.PlayerUId)},
            before=lambda: before,
            mutate=mutate,
            validate=lambda: self._validate_attached_pal(pal_id),
            after=lambda: self._pal_summary(pal),
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return {"change": entry.to_dict(), "pal": self._pal_summary(pal)}

    def _delete(self, command: DeletePal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        pal = self._indexed_pal(index, command.pal_id)
        impact = index.delete_impact(str(pal.InstanceId))
        if not isinstance(command.impact_token, str) or not command.impact_token:
            raise self._error(
                "IMPACT_PREVIEW_REQUIRED",
                "Delete requires a current impact preview token.",
                "impact_token",
                status=409,
            )
        if command.impact_token != self._impact_token(impact):
            raise self._error(
                "IMPACT_PREVIEW_STALE",
                "The delete impact changed; preview it again.",
                "impact_token",
                status=409,
            )
        if pal.IsExpeditionPal:
            raise self._error(
                "PROTECTED_CHARACTER",
                "An expedition-assigned Pal cannot be deleted.",
                "pal_id",
                status=409,
            )
        pal_id = str(pal.InstanceId)

        def mutate() -> None:
            for reference in index.container_references.get(pal_id, []):
                self._container(reference.container_id).del_pal(pal_id)
            self._fail("after_source_slot_remove", {"pal_id": pal_id})
            self._remove_owner_references(pal_id)
            self._session.manager.baseworker_mapping.pop(pal_id, None)
            self._session.manager._dangling_pals.pop(pal_id, None)
            self._fail("after_owner_index_update", {"pal_id": pal_id})
            self._remove_group_references(pal_id)
            self._fail("after_group_index_update", {"pal_id": pal_id})
            records = index.raw_records.get(pal_id, [])
            if len(records) != 1:
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The Pal character record is not unique.",
                    status=409,
                )
            self._session.manager._entities_list.remove(records[0])
            self._fail("before_invariant_commit", {"pal_id": pal_id})

        entry = self._apply(
            command=command,
            command_name="delete_pal",
            target={"pal_id": pal_id},
            before=lambda: impact,
            mutate=mutate,
            validate=lambda: self._validate_deleted_pal(pal_id),
            after=lambda: {"pal_id": pal_id, "exists": False},
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return {
            "change": entry.to_dict(),
            "deleted": {"pal_id": pal_id, "impact": impact},
        }

    def _recover(self, command: RecoverDetachedPal) -> dict[str, Any]:
        self._session.require_command(command.session_id, command.expected_revision)
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        pal = self._indexed_pal(index, command.pal_id)
        pal_id = str(pal.InstanceId)
        references = index.container_references.get(pal_id, [])
        if references:
            raise self._error(
                "PAL_NOT_DETACHED",
                "The Pal still has a character-container reference.",
                "pal_id",
                status=409,
            )
        target_issues = [
            issue for issue in index.issues_for(pal_id) if not issue.recoverable
        ]
        if target_issues:
            raise self._error(
                "AMBIGUOUS_CHARACTER_REFERENCE",
                "The detached Pal has ambiguous residual references.",
                "pal_id",
                details={"issues": [issue.to_dict() for issue in target_issues]},
                status=409,
            )
        player = self._player(command.target_player_id)
        container = self._target_container(
            player, command.container_type, command.target_slot
        )
        group = self._group(player.group_id)
        before = index.delete_impact(pal_id)

        def mutate() -> None:
            slot = container.add_pal(pal_id, command.target_slot)
            if slot < 0:
                raise self._error(
                    "CHARACTER_CONTAINER_FULL",
                    "The target character container has no available slot.",
                    "target_slot",
                    status=409,
                )
            pal.SlotId = (container.ID, slot)
            self._fail("after_target_slot_add", {"pal_id": pal_id, "slot": slot})
            self._remove_owner_references(pal_id)
            self._session.manager.baseworker_mapping.pop(pal_id, None)
            self._session.manager._dangling_pals.pop(pal_id, None)
            self._assign_owner_if_changed(pal, player)
            if not player.add_pal(pal):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The target owner already indexes this Pal.",
                    status=409,
                )
            self._fail("after_owner_index_update", {"pal_id": pal_id})
            self._remove_group_references(pal_id)
            if not group.add_pal(pal_id):
                raise self._error(
                    "DUPLICATE_INSTANCE_ID",
                    "The target group already indexes this Pal.",
                    status=409,
                )
            self._fail("after_group_index_update", {"pal_id": pal_id})
            pal.is_unreferenced_pal = False
            self._fail("before_invariant_commit", {"pal_id": pal_id})

        entry = self._apply(
            command=command,
            command_name="recover_detached_pal",
            target={"pal_id": pal_id, "target_player_id": str(player.PlayerUId)},
            before=lambda: before,
            mutate=mutate,
            validate=lambda: self._validate_attached_pal(pal_id),
            after=lambda: self._pal_summary(pal),
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return {"change": entry.to_dict(), "pal": self._pal_summary(pal)}

    def _apply(
        self,
        *,
        command: StructuralPalCommand,
        command_name: str,
        target: dict[str, Any],
        before: Callable[[], dict[str, Any]],
        mutate: Callable[[], None],
        validate: Callable[[], None],
        after: Callable[[], dict[str, Any]],
        affected_records: tuple[str, ...],
    ):
        try:
            return self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command=command_name,
                target=target,
                snapshot=self._snapshot,
                restore=self._restore,
                before=before,
                mutate=mutate,
                validate=validate,
                after=after,
                affected_records=affected_records,
            )
        except DomainError:
            raise
        except Exception as error:
            raise self._error(
                "COMMAND_EXECUTION_FAILED",
                "The structural Pal command failed and was rolled back.",
                details={"error": type(error).__name__},
                status=500,
            ) from error

    def _snapshot(self) -> dict[str, Any]:
        manager = self._session.manager
        players = list((manager.player_mapping or {}).values())
        pals = list(CharacterIndex(manager).pals.values())
        return {
            "entities": list(manager._entities_list),
            "player_mapping": dict(manager.player_mapping or {}),
            "baseworker_mapping": dict(manager.baseworker_mapping or {}),
            "dangling_pals": dict(manager._dangling_pals or {}),
            "containers": {
                str(container.ID): container.snapshot()
                for container in manager.container_data.get_containers()
            },
            "groups": {
                str(group.group_id): group.snapshot()
                for group in manager.group_data.get_groups()
            },
            "players": {
                id(player): {
                    "entity": player,
                    "palbox": dict(player._palbox),
                    "new_palbox": dict(player._new_palbox),
                    "save_data": deepcopy(player._player_save_data),
                }
                for player in players
            },
            "pals": {
                id(pal): {
                    "entity": pal,
                    "object": deepcopy(pal._pal_obj),
                    "owner": pal.owner_player_entity,
                    "unreferenced": pal.is_unreferenced_pal,
                    "new": pal.is_new_pal,
                }
                for pal in pals
            },
        }

    def _restore(self, state: dict[str, Any]) -> None:
        manager = self._session.manager
        manager._entities_list[:] = state["entities"]
        manager.player_mapping.clear()
        manager.player_mapping.update(state["player_mapping"])
        manager.baseworker_mapping.clear()
        manager.baseworker_mapping.update(state["baseworker_mapping"])
        manager._dangling_pals.clear()
        manager._dangling_pals.update(state["dangling_pals"])
        for container_id, snapshot in state["containers"].items():
            manager.container_data.get_container(container_id).restore(snapshot)
        for group_id, snapshot in state["groups"].items():
            manager.group_data.get_group(group_id).restore(snapshot)
        for item in state["players"].values():
            player = item["entity"]
            player._palbox.clear()
            player._palbox.update(item["palbox"])
            player._new_palbox.clear()
            player._new_palbox.update(item["new_palbox"])
            player._player_save_data.clear()
            player._player_save_data.update(deepcopy(item["save_data"]))
        for item in state["pals"].values():
            pal = item["entity"]
            pal._pal_obj.clear()
            pal._pal_obj.update(deepcopy(item["object"]))
            pal._pal_key = pal._pal_obj["key"]
            pal._pal_param = pal._pal_obj["value"]["RawData"]["value"]["object"][
                "SaveParameter"
            ]["value"]
            pal.owner_player_entity = item["owner"]
            pal.is_unreferenced_pal = item["unreferenced"]
            pal.is_new_pal = item["new"]

    def _assert_no_hard_issues(self, index: CharacterIndex) -> None:
        issues = index.hard_issues()
        if issues:
            raise self._error(
                "CHARACTER_INDEX_INVARIANT_FAILED",
                "Character records and their references are inconsistent.",
                details={"issues": [issue.to_dict() for issue in issues]},
                status=409,
            )

    def _validate_attached_pal(self, pal_id: str) -> None:
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        issues = index.issues_for(str(pal_id))
        if issues:
            raise self._error(
                "CHARACTER_INDEX_INVARIANT_FAILED",
                "The Pal is not consistently attached after the command.",
                details={"issues": [issue.to_dict() for issue in issues]},
                status=409,
            )

    def _validate_clone(self, source: PalEntity, clone: PalEntity) -> None:
        if str(source.InstanceId) == str(clone.InstanceId):
            raise self._error(
                "DUPLICATE_INSTANCE_ID",
                "The clone did not receive a unique instance ID.",
                status=409,
            )
        self._validate_attached_pal(str(clone.InstanceId))

    def _validate_deleted_pal(self, pal_id: str) -> None:
        index = CharacterIndex(self._session.manager)
        self._assert_no_hard_issues(index)
        if (
            pal_id in index.pals
            or pal_id in index.raw_records
            or pal_id in index.container_references
            or pal_id in index.owner_references
            or pal_id in index.group_references
        ):
            raise self._error(
                "DANGLING_CHARACTER_REFERENCE",
                "A reference to the deleted Pal remains.",
                status=409,
            )

    def _indexed_pal(self, index: CharacterIndex, pal_id: str) -> PalEntity:
        pal = index.pals.get(str(pal_id))
        if pal is None:
            raise self._error(
                "PAL_NOT_FOUND", "Pal not found.", "pal_id", status=404
            )
        return pal

    def _player(self, player_id: str):
        player = self._session.manager.get_player(player_id)
        if player is None:
            raise self._error(
                "PLAYER_NOT_FOUND", "Player not found.", "player_id", status=404
            )
        return player

    def _group(self, group_id):
        group = self._session.manager.group_data.get_group(group_id)
        if group is None:
            raise self._error(
                "GROUP_NOT_FOUND",
                "The target player's group is unavailable.",
                status=409,
            )
        return group

    def _container(self, container_id: str):
        container = self._session.manager.container_data.get_container(container_id)
        if container is None:
            raise self._error(
                "CHARACTER_CONTAINER_NOT_FOUND",
                "Character container not found.",
                status=409,
            )
        return container

    def _target_container(
        self,
        player,
        container_type: CharacterContainerType,
        target_slot: int | None,
        *,
        source_container_id: str | None = None,
        source_slot: int | None = None,
    ):
        if not isinstance(container_type, CharacterContainerType):
            raise self._error(
                "INVALID_CONTAINER_TYPE",
                "container_type is not supported.",
                "container_type",
                status=400,
            )
        if target_slot is not None and (
            isinstance(target_slot, bool)
            or not isinstance(target_slot, int)
            or target_slot < 0
        ):
            raise self._error(
                "INVALID_SLOT_INDEX",
                "target_slot must be a non-negative integer.",
                "target_slot",
                status=400,
            )
        candidates = []
        if container_type in (CharacterContainerType.AUTO, CharacterContainerType.PARTY):
            candidates.append(player.OtomoCharacterContainerId)
        if container_type in (
            CharacterContainerType.AUTO,
            CharacterContainerType.PAL_STORAGE,
        ):
            candidates.append(player.PalStorageContainerId)
        for container_id in candidates:
            if container_id is None:
                continue
            container = self._session.manager.container_data.get_container(container_id)
            if container is None:
                continue
            if target_slot is not None:
                if target_slot >= container.size:
                    continue
                if target_slot in container.available_inv_idx_set or (
                    str(container.ID) == str(source_container_id)
                    and target_slot == source_slot
                ):
                    return container
            elif container.get_empty_slot() != -1 or (
                str(container.ID) == str(source_container_id)
            ):
                return container
        raise self._error(
            "CHARACTER_CONTAINER_FULL",
            "No requested character container has an available slot.",
            "container_type",
            status=409,
        )

    def _resolve_move(self, index: CharacterIndex, command: MovePal):
        pal = self._indexed_pal(index, command.pal_id)
        if str(pal.InstanceId) in (self._session.manager.baseworker_mapping or {}):
            raise self._error(
                "PAL_LOCATION_UNSUPPORTED",
                "Base-worker moves require the base-container command.",
                "pal_id",
                status=409,
            )
        references = index.container_references.get(str(pal.InstanceId), [])
        if len(references) != 1:
            raise self._error(
                "CHARACTER_CONTAINER_MISMATCH",
                "The Pal does not have exactly one valid source slot.",
                "pal_id",
                status=409,
            )
        source_ref = references[0]
        source_container = self._container(source_ref.container_id)
        player = self._player(command.target_player_id)
        target_container = self._target_container(
            player,
            command.container_type,
            command.target_slot,
            source_container_id=source_ref.container_id,
            source_slot=source_ref.slot_index,
        )
        if str(target_container.ID) == source_ref.container_id and (
            command.target_slot is None
            or command.target_slot == source_ref.slot_index
        ):
            raise self._error(
                "NO_STRUCTURAL_CHANGE",
                "The Pal is already in the requested container and slot.",
                status=409,
            )
        return pal, source_ref, source_container, player, target_container

    def _clone_impact(self, source, player, container, command: ClonePal):
        return {
            "operation": "clone_pal",
            "source": self._pal_summary(source),
            "destination": self._destination_summary(
                player, container, command.target_slot
            ),
            "reference_delta": {
                "character_records": 1,
                "container_references": 1,
                "owner_references": 1,
                "group_references": 1,
            },
            "affected_records": [
                "level:CharacterSaveParameterMap",
                f"player_file:{player.PlayerUId}",
            ],
        }

    def _move_impact(
        self,
        pal,
        source_ref,
        source_container,
        player,
        target_container,
        command: MovePal,
    ):
        return {
            "operation": "move_pal",
            "pal": self._pal_summary(pal),
            "source": {
                "container_id": str(source_container.ID),
                "slot_index": source_ref.slot_index,
                "owner_id": (
                    None
                    if pal.OwnerPlayerUId is None
                    else str(pal.OwnerPlayerUId)
                ),
                "group_id": None if pal.group_id is None else str(pal.group_id),
            },
            "destination": self._destination_summary(
                player, target_container, command.target_slot
            ),
            "reference_delta": {
                "character_records": 0,
                "container_references": 0,
                "owner_references": 0,
                "group_references": 0,
            },
            "affected_records": ["level:CharacterSaveParameterMap"],
        }

    @staticmethod
    def _destination_summary(player, container, requested_slot: int | None):
        if str(container.ID) == str(player.OtomoCharacterContainerId):
            semantic_type = CharacterContainerType.PARTY.value
        elif str(container.ID) == str(player.PalStorageContainerId):
            semantic_type = CharacterContainerType.PAL_STORAGE.value
        else:
            semantic_type = "UNKNOWN"
        slot_index = (
            requested_slot
            if requested_slot is not None
            else container.get_empty_slot()
        )
        return {
            "player_id": str(player.PlayerUId),
            "group_id": str(player.group_id),
            "container_type": semantic_type,
            "container_id": str(container.ID),
            "slot_index": slot_index,
        }

    def _preview_result(self, impact: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": self._session.session_id,
            "revision": self._session.revision,
            "impact": impact,
            "impact_token": self._impact_token(impact),
        }

    def _require_impact_preview(
        self, impact_token: str | None, impact: dict[str, Any], operation: str
    ) -> None:
        if self._session.batch_active:
            return
        if not isinstance(impact_token, str) or not impact_token:
            raise self._error(
                "IMPACT_PREVIEW_REQUIRED",
                f"{operation.title()} requires a current impact preview token.",
                "impact_token",
                status=409,
            )
        if impact_token != self._impact_token(impact):
            raise self._error(
                "IMPACT_PREVIEW_STALE",
                f"The {operation} impact changed; preview it again.",
                "impact_token",
                status=409,
            )

    def _unique_id(
        self, index: CharacterIndex, *, extra: set[str] | None = None
    ) -> str:
        occupied = (
            set(index.raw_records)
            | set(index.container_references)
            | set(index.group_references)
        )
        occupied.update(str(value) for value in (extra or set()))
        occupied.update(
            str(container.ID)
            for container in self._session.manager.container_data.get_containers()
        )
        item_data = getattr(self._session.manager, "item_container_data", None)
        if item_data is not None:
            occupied.update(str(value) for value in item_data.container_map)
        for _ in range(128):
            candidate = str(self._id_factory())
            try:
                uuid.UUID(candidate)
            except (ValueError, TypeError, AttributeError):
                raise self._error(
                    "INVALID_GENERATED_ID",
                    "The ID generator returned an invalid UUID.",
                    status=500,
                )
            if candidate not in occupied:
                return candidate
        raise self._error(
            "UNIQUE_ID_EXHAUSTED",
            "A unique Pal identifier could not be generated.",
            status=500,
        )

    @staticmethod
    def _validate_species(species_id: str) -> None:
        if not isinstance(species_id, str) or not species_id:
            raise StructuralPalEditor._error(
                "INVALID_SPECIES_ID",
                "species_id must be a non-empty catalog ID.",
                "species_id",
                status=400,
            )
        if (
            not DataProvider.in_pal_data(species_id)
            or DataProvider.is_pal_invalid(species_id)
        ):
            raise StructuralPalEditor._error(
                "PAL_SPECIES_UNSUPPORTED",
                "The requested Pal species cannot be safely constructed.",
                "species_id",
            )

    @staticmethod
    def _validate_clone_fields(pal: PalEntity) -> None:
        unsafe = sorted(
            key
            for key in pal._pal_param
            if re.search(r"Dynamic.*(?:Id|ID)$", key, flags=re.IGNORECASE)
        )
        if unsafe:
            raise StructuralPalEditor._error(
                "CLONE_UNSUPPORTED_FIELD",
                "The source contains dynamic ownership fields that cannot be cloned safely.",
                details={"fields": unsafe},
                status=409,
            )

    def _remove_owner_references(self, pal_id: str) -> None:
        for player in self._session.manager.player_mapping.values():
            player.pop_pal(pal_id)

    @staticmethod
    def _assign_owner_if_changed(pal: PalEntity, player) -> None:
        if str(pal.OwnerPlayerUId) == str(player.PlayerUId):
            pal.set_owner_player_entity(player)
            return
        pal.assign_owner(player)

    def _remove_group_references(self, pal_id: str) -> None:
        for group in self._session.manager.group_data.get_groups():
            while group.has_pal(pal_id):
                group.del_pal(pal_id)

    def _impact_token(self, impact: dict[str, Any]) -> str:
        payload = {
            "session_id": self._session.session_id,
            "revision": self._session.revision,
            "impact": impact,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _world_summary(self) -> dict[str, Any]:
        index = CharacterIndex(self._session.manager)
        return {
            "pal_count": len(index.pals),
            "character_record_count": sum(
                len(value) for value in index.raw_records.values()
            ),
            "container_reference_count": sum(
                len(value) for value in index.container_references.values()
            ),
        }

    @staticmethod
    def _pal_summary(pal: PalEntity) -> dict[str, Any]:
        slot = pal.SlotId
        return {
            "pal_id": str(pal.InstanceId),
            "species_id": pal.CharacterID,
            "name": pal.NickName or "",
            "owner_id": None if pal.OwnerPlayerUId is None else str(pal.OwnerPlayerUId),
            "group_id": None if pal.group_id is None else str(pal.group_id),
            "container_id": None if slot is None else str(slot[0]),
            "slot_index": None if slot is None else slot[1],
            "detached": bool(pal.is_unreferenced_pal),
        }

    def _fail(self, stage: str, context: dict[str, Any]) -> None:
        if self._failure_hook is not None:
            self._failure_hook(stage, dict(context))

    @staticmethod
    def _error(
        code: str,
        message: str,
        field: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status: int = 422,
    ) -> DomainError:
        return DomainError(
            code=code,
            message=message,
            field=field,
            details=details or {},
            http_status=status,
        )
