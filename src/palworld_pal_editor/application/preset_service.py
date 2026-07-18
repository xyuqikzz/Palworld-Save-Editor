from __future__ import annotations

from typing import Any, Iterable

from palworld_pal_editor.domain.commands import (
    PutItem,
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import ItemContainerType

from .batch_editor import BatchEditor
from .character_editor import CharacterEditor
from .inventory_editor import InventoryEditor
from .save_session import SaveSession


class PresetService:
    """Minimal, versioned domain presets compiled into explicit batch commands."""

    SCHEMA = "palworld-pal-editor-preset"
    VERSION = 2
    SUPPORTED_VERSIONS = frozenset({1, 2})
    KINDS = {"inventory", "equipment", "skills", "pal"}

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def export_inventory(
        self,
        player_id: str,
        *,
        equipment_only: bool = False,
    ) -> dict[str, Any]:
        inventory = InventoryEditor(self._session).get_inventory(player_id)
        equipment = {
            ItemContainerType.ESSENTIAL,
            ItemContainerType.WEAPON_LOADOUT,
            ItemContainerType.PLAYER_EQUIP_ARMOR,
            ItemContainerType.FOOD_EQUIP,
        }
        containers = []
        editor = InventoryEditor(self._session)
        dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
        for container in inventory.containers:
            if container.status != "available":
                continue
            if equipment_only and container.container_type not in equipment:
                continue
            slots = []
            for slot in container.slots:
                if slot.state == "empty":
                    continue
                value = {
                    "slot_index": slot.slot_index,
                    "static_id": slot.static_id,
                    "count": slot.count,
                }
                if slot.dynamic_id is not None:
                    if dynamic_items is None:
                        raise DomainError(
                            code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                            message="Dynamic item data is not indexed for this save.",
                        )
                    _player, raw_container = editor._resolve_owned_container(
                        player_id, container.container_type
                    )
                    raw_slot = raw_container.get_occupied(slot.slot_index)
                    record = dynamic_items.require_writable_reference(raw_slot)
                    value["dynamic_init"] = (
                        dynamic_items.construction_initializer_for_record(record)
                    )
                slots.append(value)
            containers.append(
                {
                    "container_type": container.container_type.value,
                    "slots": slots,
                }
            )
        return {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "kind": "equipment" if equipment_only else "inventory",
            "containers": containers,
        }

    def export_skills(self, pal_id: str) -> dict[str, Any]:
        pal = self._require_pal(pal_id)
        skills = CharacterEditor._pal_skills(pal)
        skills["mastered"] = list(
            dict.fromkeys(skills["mastered"] + skills["active"])
        )
        return {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "kind": "skills",
            "skills": skills,
        }

    def export_pal(self, pal_id: str) -> dict[str, Any]:
        pal = self._require_pal(pal_id)
        enhancement = CharacterEditor._pal_enhancement(pal)
        enhancement.pop("derived", None)
        work_suitability = enhancement.pop("work_suitability", {})
        progression = CharacterEditor._pal_progression(pal)
        progression = {
            key: progression[key]
            for key in ("level", "experience", "friendship_level", "health", "satiety")
        }
        identity = CharacterEditor._pal_identity(pal)
        identity.pop("pal_id", None)
        skills = CharacterEditor._pal_skills(pal)
        skills["mastered"] = list(
            dict.fromkeys(skills["mastered"] + skills["active"])
        )
        return {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "kind": "pal",
            "identity": identity,
            "progression": progression,
            "skills": skills,
            "enhancement": enhancement,
            "work_suitability": work_suitability,
        }

    def preview_apply(
        self,
        *,
        session_id: str,
        expected_revision: int,
        preset: dict[str, Any],
        target_ids: Iterable[str],
    ) -> dict[str, Any]:
        targets = tuple(target_ids)
        operations = self._compile(
            session_id, expected_revision, preset, targets
        )
        result = BatchEditor(self._session).preview(
            session_id=session_id,
            expected_revision=expected_revision,
            operations=operations,
        )
        result["preset"] = {
            "kind": preset["kind"],
            "version": preset["version"],
            "target_count": len(targets),
        }
        return result

    def apply(
        self,
        *,
        session_id: str,
        expected_revision: int,
        preset: dict[str, Any],
        target_ids: Iterable[str],
        impact_token: str,
    ) -> dict[str, Any]:
        targets = tuple(target_ids)
        operations = self._compile(
            session_id, expected_revision, preset, targets
        )
        return BatchEditor(self._session).execute(
            session_id=session_id,
            expected_revision=expected_revision,
            operations=operations,
            impact_token=impact_token,
        )

    def _compile(
        self,
        session_id: str,
        expected_revision: int,
        preset: dict[str, Any],
        targets: tuple[str, ...],
    ):
        self._validate(preset)
        if not targets or len(targets) != len(set(targets)):
            raise DomainError(
                code="INVALID_PRESET_TARGETS",
                message="Preset targets must be a non-empty unique list.",
                field="target_ids",
                http_status=400,
            )
        base = {
            "session_id": session_id,
            "expected_revision": expected_revision,
        }
        operations = []
        kind = preset["kind"]
        if kind in {"inventory", "equipment"}:
            for player_id in targets:
                inventory = InventoryEditor(self._session).get_inventory(player_id)
                indexed = {
                    value.container_type: value for value in inventory.containers
                }
                for raw_container in preset["containers"]:
                    container_type = ItemContainerType(
                        raw_container["container_type"]
                    )
                    container = indexed.get(container_type)
                    if container is None or container.status != "available":
                        raise DomainError(
                            code="CONTAINER_NOT_FOUND",
                            message="A preset target container is unavailable.",
                            details={"container_type": container_type.value},
                            http_status=404,
                        )
                    slots = {slot.slot_index: slot for slot in container.slots}
                    for raw_slot in raw_container["slots"]:
                        slot_index = raw_slot["slot_index"]
                        current = slots.get(slot_index)
                        if current is None:
                            raise DomainError(
                                code="INVALID_SLOT_INDEX",
                                message="A preset slot is outside the target container.",
                                details={"slot_index": slot_index},
                                http_status=400,
                            )
                        operations.append(
                            PutItem(
                                **base,
                                player_id=player_id,
                                container_type=container_type,
                                slot_index=slot_index,
                                static_id=raw_slot["static_id"],
                                count=raw_slot["count"],
                                dynamic_init=raw_slot.get("dynamic_init"),
                                mode=(
                                    "empty_only"
                                    if current.state == "empty"
                                    else "replace"
                                ),
                            )
                        )
        elif kind == "skills":
            skills = preset["skills"]
            for pal_id in targets:
                operations.append(
                    UpdatePalSkills(
                        **base,
                        pal_id=pal_id,
                        active=tuple(skills["active"]),
                        mastered=tuple(skills["mastered"]),
                        passive=tuple(skills["passive"]),
                    )
                )
        else:
            identity = preset["identity"]
            for pal_id in targets:
                operations.extend(
                    (
                        UpdatePalIdentity(
                            **base,
                            pal_id=pal_id,
                            name=identity.get("name"),
                            gender=identity.get("gender"),
                            variant=identity.get("variant"),
                            boss=identity.get("boss"),
                            tower=identity.get("tower"),
                            rare=identity.get("rare"),
                        ),
                        UpdatePalEnhancement(
                            **base,
                            pal_id=pal_id,
                            values=dict(preset["enhancement"]),
                            work_suitability=dict(preset["work_suitability"]),
                        ),
                        UpdatePalProgression(
                            **base,
                            pal_id=pal_id,
                            values=dict(preset["progression"]),
                        ),
                        UpdatePalSkills(
                            **base,
                            pal_id=pal_id,
                            active=tuple(preset["skills"]["active"]),
                            mastered=tuple(preset["skills"]["mastered"]),
                            passive=tuple(preset["skills"]["passive"]),
                        ),
                    )
                )
        return tuple(operations)

    def _validate(self, preset: dict[str, Any]) -> None:
        if not isinstance(preset, dict):
            raise DomainError(
                code="INVALID_PRESET",
                message="A preset must be an object.",
                http_status=400,
            )
        if (
            preset.get("schema") != self.SCHEMA
            or preset.get("version") not in self.SUPPORTED_VERSIONS
        ):
            raise DomainError(
                code="PRESET_VERSION_UNSUPPORTED",
                message="The preset schema or version is not supported.",
                details={
                    "schema": preset.get("schema"),
                    "version": preset.get("version"),
                },
                http_status=400,
            )
        kind = preset.get("kind")
        if kind not in self.KINDS:
            raise DomainError(
                code="PRESET_KIND_UNSUPPORTED",
                message="The preset kind is not supported.",
                field="kind",
                http_status=400,
            )
        required = {
            "inventory": {"schema", "version", "kind", "containers"},
            "equipment": {"schema", "version", "kind", "containers"},
            "skills": {"schema", "version", "kind", "skills"},
            "pal": {
                "schema", "version", "kind", "identity", "progression",
                "skills", "enhancement", "work_suitability",
            },
        }[kind]
        if set(preset) != required:
            raise DomainError(
                code="INVALID_PRESET",
                message="The preset fields do not match its versioned schema.",
                details={
                    "missing": sorted(required - set(preset)),
                    "unknown": sorted(set(preset) - required),
                },
                http_status=400,
            )
        try:
            if kind in {"inventory", "equipment"}:
                if not isinstance(preset["containers"], list):
                    raise TypeError("containers")
                seen_containers = set()
                for container in preset["containers"]:
                    if not isinstance(container, dict) or set(container) != {
                        "container_type",
                        "slots",
                    }:
                        raise TypeError("container")
                    container_type = ItemContainerType(container["container_type"])
                    if container_type in seen_containers or not isinstance(
                        container["slots"], list
                    ):
                        raise TypeError("container")
                    seen_containers.add(container_type)
                    seen_slots = set()
                    for slot in container["slots"]:
                        allowed_slot_fields = {
                            "slot_index",
                            "static_id",
                            "count",
                        }
                        if preset["version"] >= 2:
                            allowed_slot_fields.add("dynamic_init")
                        if (
                            not isinstance(slot, dict)
                            or not {"slot_index", "static_id", "count"}
                            <= set(slot)
                            or not set(slot) <= allowed_slot_fields
                            or (
                                "dynamic_init" in slot
                                and not isinstance(slot["dynamic_init"], dict)
                            )
                        ):
                            raise TypeError("slot")
                        index = slot["slot_index"]
                        if (
                            isinstance(index, bool)
                            or not isinstance(index, int)
                            or index < 0
                            or index in seen_slots
                            or not isinstance(slot["static_id"], str)
                            or isinstance(slot["count"], bool)
                            or not isinstance(slot["count"], int)
                        ):
                            raise TypeError("slot")
                        seen_slots.add(index)
            if kind in {"skills", "pal"}:
                skills = preset["skills"]
                if not isinstance(skills, dict) or set(skills) != {
                    "active",
                    "mastered",
                    "passive",
                }:
                    raise TypeError("skills")
                if any(
                    not isinstance(values, list)
                    or any(not isinstance(value, str) for value in values)
                    for values in skills.values()
                ):
                    raise TypeError("skills")
            if kind == "pal":
                if not isinstance(preset["identity"], dict) or set(
                    preset["identity"]
                ) != {"name", "gender", "variant", "boss", "tower", "rare"}:
                    raise TypeError("identity")
                if not isinstance(preset["progression"], dict) or set(
                    preset["progression"]
                ) != {
                    "level",
                    "experience",
                    "friendship_level",
                    "health",
                    "satiety",
                }:
                    raise TypeError("progression")
                if not isinstance(preset["enhancement"], dict) or not isinstance(
                    preset["work_suitability"], dict
                ):
                    raise TypeError("enhancement")
        except (TypeError, ValueError, KeyError) as error:
            raise DomainError(
                code="INVALID_PRESET",
                message="The preset payload does not match its versioned schema.",
                http_status=400,
            ) from error

    def _require_pal(self, pal_id: str):
        pal = self._session.manager.get_pal(pal_id)
        if pal is None:
            raise DomainError(
                code="PAL_NOT_FOUND",
                message="Pal not found.",
                field="pal_id",
                http_status=404,
            )
        return pal
