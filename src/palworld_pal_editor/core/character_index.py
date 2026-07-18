from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects

if TYPE_CHECKING:
    from palworld_pal_editor.core.save_manager import SaveManager


@dataclass(frozen=True)
class CharacterContainerReference:
    container_id: str
    slot_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "slot_index": self.slot_index,
        }


@dataclass(frozen=True)
class CharacterIndexIssue:
    code: str
    pal_id: str | None
    details: dict[str, object]
    recoverable: bool = False

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "code": self.code,
            "details": dict(self.details),
            "recoverable": self.recoverable,
        }
        if self.pal_id is not None:
            result["pal_id"] = self.pal_id
        return result


class CharacterIndex:
    """Cross-record index for Pal records, slots, owners, and guild handles."""

    def __init__(self, manager: "SaveManager") -> None:
        self.manager = manager
        self.raw_records: dict[str, list[dict]] = {}
        self.pals: dict[str, PalEntity] = {}
        self.container_references: dict[str, list[CharacterContainerReference]] = {}
        self.owner_references: dict[str, list[str]] = {}
        self.group_references: dict[str, list[str]] = {}
        self.player_owned_ids: set[str] = set()
        self.issues: list[CharacterIndexIssue] = []
        self._build()

    def _build(self) -> None:
        self._index_raw_records()
        self._index_pal_wrappers()
        self._index_containers()
        self._index_owners()
        self._index_groups()
        self._validate()

    def _index_raw_records(self) -> None:
        for position, entity in enumerate(self.manager._entities_list or []):
            try:
                save_parameter = entity["value"]["RawData"]["value"]["object"][
                    "SaveParameter"
                ]
                if save_parameter.get("struct_type") != (
                    "PalIndividualCharacterSaveParameter"
                ):
                    continue
                entity_id = PalObjects.get_BaseType(
                    entity.get("key", {}).get("InstanceId")
                )
                if entity_id is None:
                    self.issues.append(
                        CharacterIndexIssue(
                            code="CHARACTER_RECORD_ID_MISSING",
                            pal_id=None,
                            details={"position": position},
                        )
                    )
                    continue
                key = str(entity_id)
                self.raw_records.setdefault(key, []).append(entity)
            except (KeyError, TypeError, AttributeError) as error:
                self.issues.append(
                    CharacterIndexIssue(
                        code="CHARACTER_RECORD_MALFORMED",
                        pal_id=None,
                        details={
                            "position": position,
                            "error": type(error).__name__,
                        },
                    )
                )

    def _all_wrapper_candidates(self) -> Iterable[PalEntity]:
        for player in (self.manager.player_mapping or {}).values():
            yield from player._palbox.values()
        yield from (self.manager.baseworker_mapping or {}).values()
        yield from (self.manager._dangling_pals or {}).values()

    def _index_pal_wrappers(self) -> None:
        wrapper_objects: dict[str, set[int]] = {}
        for pal in self._all_wrapper_candidates():
            pal_id = str(pal.InstanceId)
            wrapper_objects.setdefault(pal_id, set()).add(id(pal))
            self.pals.setdefault(pal_id, pal)
        for pal_id, identities in wrapper_objects.items():
            if len(identities) > 1:
                self.issues.append(
                    CharacterIndexIssue(
                        code="DUPLICATE_PAL_WRAPPER",
                        pal_id=pal_id,
                        details={"count": len(identities)},
                    )
                )

    def _index_containers(self) -> None:
        container_data = self.manager.container_data
        for container in container_data.get_containers() if container_data else []:
            container_id = str(container.ID)
            for slot in container.slots:
                pal_id = str(slot.instance_id)
                self.container_references.setdefault(pal_id, []).append(
                    CharacterContainerReference(
                        container_id=container_id,
                        slot_index=slot.inv_idx,
                    )
                )

    def _index_owners(self) -> None:
        for player_id, player in (self.manager.player_mapping or {}).items():
            for pal_id, pal in player._palbox.items():
                normalized = str(pal.InstanceId)
                if str(pal_id) != normalized:
                    self.issues.append(
                        CharacterIndexIssue(
                            code="OWNER_INDEX_KEY_MISMATCH",
                            pal_id=normalized,
                            details={
                                "owner_id": str(player_id),
                                "index_key": str(pal_id),
                            },
                        )
                    )
                self.owner_references.setdefault(normalized, []).append(
                    str(player_id)
                )
                self.player_owned_ids.add(normalized)

    def _index_groups(self) -> None:
        for group in (
            self.manager.group_data.get_groups() if self.manager.group_data else []
        ):
            group_id = str(group.group_id)
            seen: set[str] = set()
            for handle in group.individual_character_handle_ids or []:
                pal_id = str(handle.get("instance_id"))
                if pal_id in seen:
                    self.issues.append(
                        CharacterIndexIssue(
                            code="DUPLICATE_GROUP_HANDLE",
                            pal_id=pal_id,
                            details={"group_id": group_id},
                        )
                    )
                seen.add(pal_id)
                self.group_references.setdefault(pal_id, []).append(group_id)

    def _validate(self) -> None:
        for record_id, records in self.raw_records.items():
            if len(records) > 1:
                self.issues.append(
                    CharacterIndexIssue(
                        code="DUPLICATE_CHARACTER_RECORD",
                        pal_id=record_id,
                        details={"count": len(records)},
                    )
                )

        player_instance_ids = {
            str(player.InstanceId)
            for player in (self.manager.player_mapping or {}).values()
        }
        for record_id in self.raw_records:
            if record_id in player_instance_ids:
                continue
            if record_id not in self.pals:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_RECORD_UNMANAGED",
                        pal_id=record_id,
                        details={},
                    )
                )

        for pal_id, pal in self.pals.items():
            records = self.raw_records.get(pal_id, [])
            if len(records) != 1 or records[0] is not pal._pal_obj:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_RECORD_INDEX_MISMATCH",
                        pal_id=pal_id,
                        details={"record_count": len(records)},
                    )
                )

            container_refs = self.container_references.get(pal_id, [])
            if not container_refs:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_DETACHED",
                        pal_id=pal_id,
                        details={
                            "declared_slot": self._declared_slot(pal),
                        },
                        recoverable=True,
                    )
                )
            elif len(container_refs) > 1:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_CONTAINER_REFERENCE_AMBIGUOUS",
                        pal_id=pal_id,
                        details={
                            "references": [ref.to_dict() for ref in container_refs]
                        },
                    )
                )
            elif self._declared_slot(pal) != container_refs[0].to_dict():
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_SLOT_REFERENCE_MISMATCH",
                        pal_id=pal_id,
                        details={
                            "declared": self._declared_slot(pal),
                            "actual": container_refs[0].to_dict(),
                        },
                    )
                )

            owner_refs = self.owner_references.get(pal_id, [])
            owner_id = self._normalized_owner(pal)
            if len(owner_refs) > 1:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_OWNER_REFERENCE_AMBIGUOUS",
                        pal_id=pal_id,
                        details={"owner_ids": owner_refs},
                    )
                )
            elif pal_id in self.player_owned_ids and owner_refs != [owner_id]:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_OWNER_REFERENCE_MISMATCH",
                        pal_id=pal_id,
                        details={
                            "declared_owner_id": owner_id,
                            "indexed_owner_ids": owner_refs,
                        },
                    )
                )

            group_refs = self.group_references.get(pal_id, [])
            group_id = str(pal.group_id) if pal.group_id is not None else None
            if len(group_refs) > 1:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_GROUP_REFERENCE_AMBIGUOUS",
                        pal_id=pal_id,
                        details={"group_ids": group_refs},
                    )
                )
            elif group_id is not None and group_refs != [group_id]:
                self.issues.append(
                    CharacterIndexIssue(
                        code="PAL_GROUP_REFERENCE_MISMATCH",
                        pal_id=pal_id,
                        details={
                            "declared_group_id": group_id,
                            "indexed_group_ids": group_refs,
                        },
                    )
                )

    @staticmethod
    def _normalized_owner(pal: PalEntity) -> str | None:
        owner_id = pal.OwnerPlayerUId
        if owner_id is None or str(owner_id) == str(PalObjects.EMPTY_UUID):
            return None
        return str(owner_id)

    @staticmethod
    def _declared_slot(pal: PalEntity) -> dict[str, object] | None:
        slot = pal.SlotId
        if slot is None:
            return None
        return {"container_id": str(slot[0]), "slot_index": slot[1]}

    def hard_issues(self) -> list[CharacterIndexIssue]:
        return [issue for issue in self.issues if not issue.recoverable]

    def issues_for(self, pal_id: str) -> list[CharacterIndexIssue]:
        normalized = str(pal_id)
        return [issue for issue in self.issues if issue.pal_id == normalized]

    def delete_impact(self, pal_id: str) -> dict[str, object]:
        normalized = str(pal_id)
        pal = self.pals.get(normalized)
        if pal is None:
            return {"pal_id": normalized, "exists": False}
        return {
            "pal_id": normalized,
            "exists": True,
            "character_record_count": len(self.raw_records.get(normalized, [])),
            "container_references": [
                reference.to_dict()
                for reference in self.container_references.get(normalized, [])
            ],
            "owner_references": list(self.owner_references.get(normalized, [])),
            "group_references": list(self.group_references.get(normalized, [])),
            "expedition_assigned": bool(pal.IsExpeditionPal),
            "issues": [issue.to_dict() for issue in self.issues_for(normalized)],
        }


def inspect_decoded_character_graph(gvas_file) -> list[CharacterIndexIssue]:
    """Validate serialized Level.sav character links without loading Player files."""
    from palworld_pal_editor.core.container_data import ContainerData
    from palworld_pal_editor.core.group_data import GroupData

    world = gvas_file.properties.get("worldSaveData", {}).get("value", {})
    records = world.get("CharacterSaveParameterMap", {}).get("value", [])
    raw_pals: dict[str, list[tuple[dict, dict]]] = {}
    issues: list[CharacterIndexIssue] = []
    for position, entity in enumerate(records):
        try:
            parameter = entity["value"]["RawData"]["value"]["object"][
                "SaveParameter"
            ]["value"]
            if PalObjects.get_BaseType(parameter.get("IsPlayer")):
                continue
            pal_id = PalObjects.get_BaseType(entity["key"].get("InstanceId"))
            if pal_id is None:
                raise KeyError("InstanceId")
            raw_pals.setdefault(str(pal_id), []).append((entity, parameter))
        except (KeyError, TypeError, AttributeError) as error:
            issues.append(
                CharacterIndexIssue(
                    code="CHARACTER_RECORD_MALFORMED",
                    pal_id=None,
                    details={
                        "position": position,
                        "error": type(error).__name__,
                    },
                )
            )

    containers = ContainerData(gvas_file)
    groups = GroupData(gvas_file)
    container_refs: dict[str, list[CharacterContainerReference]] = {}
    for container in containers.get_containers():
        for slot in container.slots:
            container_refs.setdefault(str(slot.instance_id), []).append(
                CharacterContainerReference(str(container.ID), slot.inv_idx)
            )
    group_refs: dict[str, list[str]] = {}
    known_pal_ids = set(raw_pals)
    for group in groups.get_groups():
        seen: set[str] = set()
        for handle in group.individual_character_handle_ids or []:
            pal_id = str(handle.get("instance_id"))
            if pal_id not in known_pal_ids:
                continue
            if pal_id in seen:
                issues.append(
                    CharacterIndexIssue(
                        code="DUPLICATE_GROUP_HANDLE",
                        pal_id=pal_id,
                        details={"group_id": str(group.group_id)},
                    )
                )
            seen.add(pal_id)
            group_refs.setdefault(pal_id, []).append(str(group.group_id))

    for pal_id, values in raw_pals.items():
        if len(values) != 1:
            issues.append(
                CharacterIndexIssue(
                    code="DUPLICATE_CHARACTER_RECORD",
                    pal_id=pal_id,
                    details={"count": len(values)},
                )
            )
            continue
        parameter = values[0][1]
        declared_slot = PalObjects.get_PalCharacterSlotId(parameter.get("SlotId"))
        declared = (
            None
            if declared_slot is None
            else {
                "container_id": str(declared_slot[0]),
                "slot_index": declared_slot[1],
            }
        )
        references = container_refs.get(pal_id, [])
        if not references:
            issues.append(
                CharacterIndexIssue(
                    code="PAL_DETACHED",
                    pal_id=pal_id,
                    details={"declared_slot": declared},
                    recoverable=True,
                )
            )
        elif len(references) != 1:
            issues.append(
                CharacterIndexIssue(
                    code="PAL_CONTAINER_REFERENCE_AMBIGUOUS",
                    pal_id=pal_id,
                    details={
                        "references": [value.to_dict() for value in references]
                    },
                )
            )
        elif references[0].to_dict() != declared:
            issues.append(
                CharacterIndexIssue(
                    code="PAL_SLOT_REFERENCE_MISMATCH",
                    pal_id=pal_id,
                    details={
                        "declared": declared,
                        "actual": references[0].to_dict(),
                    },
                )
            )
        raw_group_id = values[0][0]["value"]["RawData"]["value"].get(
            "group_id"
        )
        declared_group_id = (
            None if raw_group_id is None else str(raw_group_id)
        )
        indexed_groups = group_refs.get(pal_id, [])
        if len(indexed_groups) > 1 or (
            declared_group_id is not None
            and indexed_groups != [declared_group_id]
        ):
            issues.append(
                CharacterIndexIssue(
                    code="PAL_GROUP_REFERENCE_MISMATCH",
                    pal_id=pal_id,
                    details={
                        "declared_group_id": declared_group_id,
                        "indexed_group_ids": indexed_groups,
                    },
                )
            )
    return issues
