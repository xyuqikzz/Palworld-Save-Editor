from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable

from palworld_pal_editor.core.pal_objects import PalGender, PalObjects, PalSuitability
from palworld_pal_editor.domain.commands import (
    UnlockPalExpedition,
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
    UpdatePlayerIdentity,
    UpdatePlayerProgression,
    UpdatePlayerTechnology,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider

from .save_session import SaveSession


MAX_NAME_LENGTH = 24
MAX_LEVEL = 100
MAX_EXPERIENCE = 9_223_372_036_854_775_807
MAX_TECHNOLOGY_POINTS = 65_535
MAX_HEALTH = 2_147_483_647
MAX_MASTERED_SKILLS = 255
MAX_ENHANCEMENT_CHEAT_LEVEL = 255
MAX_WORK_SUITABILITY_LEVEL = 10


class CharacterEditor:
    """Explicit, atomic player and Pal field commands."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(self, command):
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        if isinstance(command, UpdatePlayerIdentity):
            return self._update_player_identity(command)
        if isinstance(command, UpdatePlayerProgression):
            return self._update_player_progression(command)
        if isinstance(command, UpdatePlayerTechnology):
            return self._update_player_technology(command)
        if isinstance(command, UpdatePalIdentity):
            return self._update_pal_identity(command)
        if isinstance(command, UpdatePalProgression):
            return self._update_pal_progression(command)
        if isinstance(command, UpdatePalSkills):
            return self._update_pal_skills(command)
        if isinstance(command, UpdatePalEnhancement):
            return self._update_pal_enhancement(command)
        if isinstance(command, UnlockPalExpedition):
            return self._unlock_pal_expedition(command)
        raise DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported character command.",
            http_status=400,
        )

    def _update_player_identity(self, command: UpdatePlayerIdentity) -> dict:
        player = self._require_player(command.player_id)
        self._validate_name(command.name, "name")

        def mutate() -> None:
            player.NickName = command.name

        def validate() -> None:
            if (player.NickName or "") != command.name:
                self._postcondition("The player name did not update as requested.")

        entry = self._apply_player(
            command=command,
            player=player,
            command_name="UpdatePlayerIdentity",
            target={"player_id": str(player.PlayerUId)},
            before=lambda: self._player_identity(player),
            mutate=mutate,
            validate=validate,
            after=lambda: self._player_identity(player),
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return self._result(entry, self._player_identity(player))

    def _update_player_progression(
        self, command: UpdatePlayerProgression
    ) -> dict:
        player = self._require_player(command.player_id)
        supplied = {
            "level": command.level,
            "experience": command.experience,
            "technology_points": command.technology_points,
            "boss_technology_points": command.boss_technology_points,
        }
        if not any(value is not None for value in supplied.values()):
            self._empty_command()
        if command.level is not None:
            self._require_int_range(command.level, 1, MAX_LEVEL, "level")
            if DataProvider.get_player_level_xp(command.level) is None:
                raise DomainError(
                    code="COMPATIBILITY_FIELD_MISSING",
                    message="No experience rule exists for this player level.",
                    field="level",
                )
        if command.experience is not None:
            self._require_int_range(
                command.experience, 0, MAX_EXPERIENCE, "experience"
            )
        if command.technology_points is not None:
            self._require_int_range(
                command.technology_points,
                0,
                MAX_TECHNOLOGY_POINTS,
                "technology_points",
            )
        if command.boss_technology_points is not None:
            self._require_int_range(
                command.boss_technology_points,
                0,
                MAX_TECHNOLOGY_POINTS,
                "boss_technology_points",
            )

        def mutate() -> None:
            if command.level is not None:
                player.Level = command.level
            if command.experience is not None:
                player.Exp = command.experience
            if command.technology_points is not None:
                player.TechnologyPoint = command.technology_points
            if command.boss_technology_points is not None:
                player.bossTechnologyPoint = command.boss_technology_points

        def validate() -> None:
            actual = self._player_progression(player)
            for field_name, expected in supplied.items():
                if expected is not None and actual[field_name] != expected:
                    self._postcondition(
                        f"Player field {field_name} did not update as requested."
                    )

        affected: list[str] = []
        if command.level is not None or command.experience is not None:
            affected.append("level:CharacterSaveParameterMap")
        if (
            command.technology_points is not None
            or command.boss_technology_points is not None
        ):
            affected.append(f"player_file:{player.PlayerUId}")
        entry = self._apply_player(
            command=command,
            player=player,
            command_name="UpdatePlayerProgression",
            target={
                "player_id": str(player.PlayerUId),
                "fields": [key for key, value in supplied.items() if value is not None],
            },
            before=lambda: self._player_progression(player),
            mutate=mutate,
            validate=validate,
            after=lambda: self._player_progression(player),
            affected_records=tuple(affected),
        )
        return self._result(entry, self._player_progression(player))

    def _update_player_technology(
        self, command: UpdatePlayerTechnology
    ) -> dict:
        player = self._require_player(command.player_id)
        if command.unlock_all:
            if command.recipe_id is not None or command.unlocked is not None:
                raise DomainError(
                    code="CONFLICTING_COMMAND_FIELDS",
                    message="unlock_all cannot be combined with recipe_id or unlocked.",
                    http_status=400,
                )
        else:
            if not isinstance(command.recipe_id, str) or not isinstance(
                command.unlocked, bool
            ):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="recipe_id and unlocked are required.",
                    http_status=400,
                )
            if command.recipe_id not in DataProvider.get_tech_data():
                raise DomainError(
                    code="UNKNOWN_TECHNOLOGY",
                    message="The requested technology ID is unknown.",
                    field="recipe_id",
                )

        def mutate() -> None:
            if command.unlock_all:
                player.unlock_all_techs()
            else:
                player.toggle_UnlockedRecipeTechnologyNames(
                    command.recipe_id, command.unlocked
                )

        def validate() -> None:
            unlocked = set(player.UnlockedRecipeTechnologyNames or [])
            if command.unlock_all:
                if not set(DataProvider.get_tech_data()).issubset(unlocked):
                    self._postcondition("Not all technologies were unlocked.")
            elif (command.recipe_id in unlocked) is not command.unlocked:
                self._postcondition("The technology state did not update.")

        entry = self._apply_player(
            command=command,
            player=player,
            command_name="UpdatePlayerTechnology",
            target={
                "player_id": str(player.PlayerUId),
                "recipe_id": command.recipe_id,
                "unlock_all": command.unlock_all,
            },
            before=lambda: self._player_technology(player),
            mutate=mutate,
            validate=validate,
            after=lambda: self._player_technology(player),
            affected_records=(f"player_file:{player.PlayerUId}",),
        )
        return self._result(entry, self._player_technology(player))

    def _update_pal_identity(self, command: UpdatePalIdentity) -> dict:
        pal = self._require_pal(command.pal_id)
        supplied = {
            "name": command.name,
            "gender": command.gender,
            "variant": command.variant,
            "boss": command.boss,
            "tower": command.tower,
            "rare": command.rare,
        }
        if not any(value is not None for value in supplied.values()):
            self._empty_command()
        if command.name is not None:
            self._validate_name(command.name, "name")
        gender_value = None
        if command.gender is not None:
            gender_value = self._validate_gender(
                pal, command.gender, command.variant
            )
        if command.variant is not None and not DataProvider.in_pal_data(
            command.variant
        ):
            raise DomainError(
                code="INVALID_VARIANT",
                message="The requested Pal variant is not in the local catalog.",
                field="variant",
            )
        for field_name in ("boss", "tower", "rare"):
            value = supplied[field_name]
            if value is not None and not isinstance(value, bool):
                raise DomainError(
                    code="INVALID_FIELD_TYPE",
                    message=f"{field_name} must be a boolean.",
                    field=field_name,
                    http_status=400,
                )
        if sum(
            value is True for value in (command.boss, command.tower, command.rare)
        ) > 1:
            raise DomainError(
                code="CONFLICTING_COMMAND_FIELDS",
                message="A Pal cannot enable multiple exclusive variants at once.",
                http_status=400,
            )

        def mutate() -> None:
            if command.variant is not None:
                pal.CharacterID = command.variant
            if command.name is not None:
                pal.NickName = command.name
            if gender_value is not None:
                pal.Gender = gender_value
            if command.tower is not None:
                pal.IsTower = command.tower
            if command.boss is not None:
                pal.IsBOSS = command.boss
            if command.rare is not None:
                pal.IsRarePal = command.rare

        def validate() -> None:
            actual = self._pal_identity(pal)
            if command.name is not None and actual["name"] != command.name:
                self._postcondition("The Pal name did not update as requested.")
            if command.gender is not None and actual["gender"] != command.gender:
                self._postcondition("The Pal gender did not update as requested.")
            if (
                command.variant is not None
                and command.boss is None
                and command.tower is None
                and actual["variant"] != command.variant
            ):
                self._postcondition("The Pal variant did not update as requested.")
            for field_name in ("boss", "tower", "rare"):
                expected = supplied[field_name]
                if expected is not None and actual[field_name] is not expected:
                    self._postcondition(
                        f"The Pal {field_name} flag did not update as requested."
                    )

        entry = self._apply_pal(
            command=command,
            pal=pal,
            command_name="UpdatePalIdentity",
            target={
                "pal_id": str(pal.InstanceId),
                "fields": [key for key, value in supplied.items() if value is not None],
            },
            before=lambda: self._pal_identity(pal),
            mutate=mutate,
            validate=validate,
            after=lambda: self._pal_identity(pal),
        )
        return self._result(entry, self._pal_identity(pal))

    def _update_pal_progression(self, command: UpdatePalProgression) -> dict:
        pal = self._require_pal(command.pal_id)
        allowed = {
            "level",
            "experience",
            "friendship_level",
            "health",
            "satiety",
            "heal",
        }
        self._reject_unknown_fields(command.values, allowed)
        if not command.values:
            self._empty_command()
        values = command.values
        if "level" in values:
            self._require_int_range(values["level"], 1, MAX_LEVEL, "level")
            if DataProvider.get_pal_level_xp(values["level"]) is None:
                raise DomainError(
                    code="COMPATIBILITY_FIELD_MISSING",
                    message="No experience rule exists for this Pal level.",
                    field="level",
                )
        if "experience" in values:
            self._require_int_range(
                values["experience"], 0, MAX_EXPERIENCE, "experience"
            )
        if "friendship_level" in values:
            self._require_int_range(
                values["friendship_level"], 0, 10, "friendship_level"
            )
            if DataProvider.get_pal_friendship(values["friendship_level"]) is None:
                raise DomainError(
                    code="COMPATIBILITY_FIELD_MISSING",
                    message="No trust rule exists for this level.",
                    field="friendship_level",
                )
        if "health" in values:
            self._require_int_range(
                values["health"], 0, MAX_HEALTH, "health"
            )
        if "satiety" in values:
            maximum_food = DataProvider.get_pal_stats(pal.DataAccessKey, "FOOD")
            if maximum_food is None:
                raise DomainError(
                    code="COMPATIBILITY_FIELD_MISSING",
                    message="No satiety rule exists for this Pal variant.",
                    field="satiety",
                )
            self._require_number_range(
                values["satiety"], 0, maximum_food, "satiety"
            )
        if "heal" in values and values["heal"] is not True:
            raise DomainError(
                code="INVALID_FIELD_VALUE",
                message="heal must be true when supplied.",
                field="heal",
                http_status=400,
            )

        def mutate() -> None:
            if "level" in values:
                pal.Level = values["level"]
            if "experience" in values:
                pal.Exp = values["experience"]
            if "friendship_level" in values:
                pal.FriendshipLevel = values["friendship_level"]
            if values.get("heal") is True:
                pal.heal_pal()
            if "health" in values:
                pal.Hp = values["health"]
            if "satiety" in values:
                pal.FullStomach = values["satiety"]

        def validate() -> None:
            actual = self._pal_progression(pal)
            for field_name in (
                "level",
                "experience",
                "friendship_level",
                "health",
                "satiety",
            ):
                if field_name in values and actual[field_name] != values[field_name]:
                    self._postcondition(
                        f"Pal field {field_name} did not update as requested."
                    )
            if values.get("heal") and any(
                (
                    actual["worker_sick"],
                    actual["fainted"],
                    actual["hunger_status"],
                    actual["physical_status"],
                )
            ):
                self._postcondition("The Pal abnormal status was not cleared.")

        entry = self._apply_pal(
            command=command,
            pal=pal,
            command_name="UpdatePalProgression",
            target={"pal_id": str(pal.InstanceId), "fields": sorted(values)},
            before=lambda: self._pal_progression(pal),
            mutate=mutate,
            validate=validate,
            after=lambda: self._pal_progression(pal),
        )
        return self._result(entry, self._pal_progression(pal))

    def _update_pal_skills(self, command: UpdatePalSkills) -> dict:
        pal = self._require_pal(command.pal_id)
        if (
            command.active is None
            and command.mastered is None
            and command.passive is None
        ):
            self._empty_command()
        current_active = tuple(pal.EquipWaza or [])
        current_mastered = tuple(pal.MasteredWaza or [])
        current_passive = tuple(pal.PassiveSkillList or [])
        active = current_active if command.active is None else command.active
        mastered = (
            current_mastered if command.mastered is None else command.mastered
        )
        passive = current_passive if command.passive is None else command.passive
        if command.active is not None:
            self._validate_skill_ids(
                active, "active", DataProvider.has_attack, 3, current_active
            )
        if command.mastered is not None:
            self._validate_skill_ids(
                mastered,
                "mastered",
                DataProvider.has_attack,
                MAX_MASTERED_SKILLS,
                current_mastered,
            )
        if command.passive is not None:
            self._validate_skill_ids(
                passive,
                "passive",
                DataProvider.has_passive_skill,
                4,
                current_passive,
            )
        missing = sorted(set(active) - set(mastered))
        existing_missing = set(current_active) - set(current_mastered)
        introduced_missing = sorted(set(missing) - existing_missing)
        if (
            (command.active is not None or command.mastered is not None)
            and introduced_missing
        ):
            raise DomainError(
                code="ACTIVE_SKILL_NOT_MASTERED",
                message="Every active skill must also be mastered.",
                details={"skills": introduced_missing},
            )

        def mutate() -> None:
            if command.mastered is not None:
                self._replace_array(pal, "MasteredWaza", "EnumProperty", mastered)
            if command.active is not None:
                self._replace_array(pal, "EquipWaza", "EnumProperty", active)
            if command.passive is not None:
                self._replace_array(
                    pal, "PassiveSkillList", "NameProperty", passive
                )

        expected = {
            "active": list(active),
            "mastered": list(mastered),
            "passive": list(passive),
        }

        def validate() -> None:
            if self._pal_skills(pal) != expected:
                self._postcondition("The Pal skill sets did not update atomically.")

        entry = self._apply_pal(
            command=command,
            pal=pal,
            command_name="UpdatePalSkills",
            target={
                "pal_id": str(pal.InstanceId),
                "fields": [
                    name
                    for name, value in (
                        ("active", command.active),
                        ("mastered", command.mastered),
                        ("passive", command.passive),
                    )
                    if value is not None
                ],
            },
            before=lambda: self._pal_skills(pal),
            mutate=mutate,
            validate=validate,
            after=lambda: self._pal_skills(pal),
        )
        return self._result(entry, self._pal_skills(pal))

    def _update_pal_enhancement(self, command: UpdatePalEnhancement) -> dict:
        pal = self._require_pal(command.pal_id)
        field_map = {
            "iv_hp": ("Talent_HP", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "iv_melee": ("Talent_Melee", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "iv_shot": ("Talent_Shot", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "iv_defense": ("Talent_Defense", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "soul_hp": ("Rank_HP", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "soul_attack": ("Rank_Attack", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "soul_defense": ("Rank_Defence", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "soul_craft_speed": ("Rank_CraftSpeed", 0, MAX_ENHANCEMENT_CHEAT_LEVEL),
            "condensation": ("Rank", 1, MAX_ENHANCEMENT_CHEAT_LEVEL),
        }
        self._reject_unknown_fields(command.values, set(field_map))
        if not command.values and not command.work_suitability:
            self._empty_command()
        for field_name, value in command.values.items():
            _property_name, minimum, maximum = field_map[field_name]
            self._require_int_range(value, minimum, maximum, field_name)

        suitability_rules = DataProvider.get_pal_suitabilities(pal.DataAccessKey)
        normalized_suitabilities: dict[PalSuitability, int] = {}
        for work_type, value in command.work_suitability.items():
            suitability = PalSuitability.from_value(work_type)
            if suitability is None:
                raise DomainError(
                    code="UNKNOWN_WORK_TYPE",
                    message="The requested work suitability type is unknown.",
                    field="work_suitability",
                    details={"work_type": work_type},
                )
            self._require_int_range(
                value, 0, MAX_WORK_SUITABILITY_LEVEL, "work_suitability"
            )
            if (
                suitability_rules is None
                or suitability.value not in suitability_rules
            ):
                raise DomainError(
                    code="COMPATIBILITY_FIELD_MISSING",
                    message="No work suitability rule exists for this Pal variant.",
                    details={"work_type": work_type},
                )
            base_value = suitability_rules[suitability.value]
            condensation_bonus = int(
                (pal.Rank or 0) >= 5 and base_value < 5
            )
            minimum_value = base_value + condensation_bonus
            if value < minimum_value:
                raise DomainError(
                    code="VALUE_OUT_OF_RANGE",
                    message="Work suitability cannot be lower than the species base value.",
                    field="work_suitability",
                    details={"minimum": minimum_value, "actual": value},
                )
            normalized_suitabilities[suitability] = value

        def mutate() -> None:
            for field_name, value in command.values.items():
                property_name = field_map[field_name][0]
                if property_name == "Talent_HP":
                    pal.Talent_HP = value
                elif property_name == "Talent_Melee":
                    pal.Talent_Melee = value
                elif property_name == "Talent_Shot":
                    pal.Talent_Shot = value
                elif property_name == "Talent_Defense":
                    pal.Talent_Defense = value
                elif property_name == "Rank_HP":
                    pal.Rank_HP = value
                elif property_name == "Rank_Attack":
                    pal.Rank_Attack = value
                elif property_name == "Rank_Defence":
                    pal.Rank_Defence = value
                elif property_name == "Rank_CraftSpeed":
                    pal.Rank_CraftSpeed = value
                else:
                    pal.Rank = value
            for suitability, value in normalized_suitabilities.items():
                pal.set_WorkSuitability(suitability, value)

        def validate() -> None:
            actual = self._pal_enhancement(pal)
            for field_name, expected in command.values.items():
                if actual[field_name] != expected:
                    self._postcondition(
                        f"Pal enhancement {field_name} did not update."
                    )
            actual_suitabilities = pal.WorkSuitabilities or {}
            for suitability, expected in normalized_suitabilities.items():
                if actual_suitabilities.get(suitability.value, 0) != expected:
                    self._postcondition(
                        f"Pal work suitability {suitability.value} did not update."
                    )

        entry = self._apply_pal(
            command=command,
            pal=pal,
            command_name="UpdatePalEnhancement",
            target={
                "pal_id": str(pal.InstanceId),
                "fields": sorted(command.values),
                "work_types": sorted(command.work_suitability),
            },
            before=lambda: self._pal_enhancement(pal),
            mutate=mutate,
            validate=validate,
            after=lambda: self._pal_enhancement(pal),
        )
        return self._result(entry, self._pal_enhancement(pal))

    def _unlock_pal_expedition(self, command: UnlockPalExpedition) -> dict:
        pal = self._require_pal(command.pal_id)
        if not pal.IsExpeditionPal:
            raise DomainError(
                code="PAL_NOT_EXPEDITION_ASSIGNED",
                message="The Pal is not assigned to an expedition.",
                field="pal_id",
                details={"pal_id": str(pal.InstanceId)},
                http_status=409,
            )

        def state() -> dict[str, Any]:
            return {
                "pal_id": str(pal.InstanceId),
                "expedition_locked": bool(pal.IsExpeditionPal),
            }

        def validate() -> None:
            if pal.IsExpeditionPal:
                self._postcondition("The Pal expedition assignment was not removed.")

        entry = self._apply_pal(
            command=command,
            pal=pal,
            command_name="UnlockPalExpedition",
            target={"pal_id": str(pal.InstanceId)},
            before=state,
            mutate=pal.unlock_expedition,
            validate=validate,
            after=state,
        )
        return self._result(entry, state())

    def _apply_player(
        self,
        *,
        command,
        player,
        command_name: str,
        target: dict[str, Any],
        before: Callable[[], dict[str, Any]],
        mutate: Callable[[], None],
        validate: Callable[[], None],
        after: Callable[[], dict[str, Any]],
        affected_records: tuple[str, ...],
    ):
        def snapshot():
            return (
                deepcopy(player._player_param),
                deepcopy(player._player_save_data),
            )

        def restore(state) -> None:
            player_param, player_save_data = state
            player._player_param.clear()
            player._player_param.update(deepcopy(player_param))
            player._player_save_data.clear()
            player._player_save_data.update(deepcopy(player_save_data))

        return self._apply(
            command=command,
            command_name=command_name,
            target=target,
            snapshot=snapshot,
            restore=restore,
            before=before,
            mutate=mutate,
            validate=validate,
            after=after,
            affected_records=affected_records,
        )

    def _apply_pal(
        self,
        *,
        command,
        pal,
        command_name: str,
        target: dict[str, Any],
        before: Callable[[], dict[str, Any]],
        mutate: Callable[[], None],
        validate: Callable[[], None],
        after: Callable[[], dict[str, Any]],
    ):
        def restore(snapshot) -> None:
            pal._pal_param.clear()
            pal._pal_param.update(deepcopy(snapshot))
            cache = getattr(pal, "_display_name_cache", None)
            if isinstance(cache, dict):
                cache.clear()

        return self._apply(
            command=command,
            command_name=command_name,
            target=target,
            snapshot=lambda: deepcopy(pal._pal_param),
            restore=restore,
            before=before,
            mutate=mutate,
            validate=validate,
            after=after,
            affected_records=("level:CharacterSaveParameterMap",),
        )

    def _apply(self, **kwargs):
        command = kwargs.pop("command")
        try:
            return self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command=kwargs.pop("command_name"),
                **kwargs,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="COMMAND_EXECUTION_FAILED",
                message="The character update could not be applied safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error

    def _require_player(self, player_id: str):
        player = self._session.manager.get_player(player_id)
        if player is None:
            raise DomainError(
                code="PLAYER_NOT_FOUND",
                message="Player not found.",
                field="player_id",
                details={"player_id": player_id},
                http_status=404,
            )
        return player

    def _require_pal(self, pal_id: str):
        pal = self._session.manager.get_pal(pal_id)
        if pal is None:
            raise DomainError(
                code="PAL_NOT_FOUND",
                message="Pal not found.",
                field="pal_id",
                details={"pal_id": pal_id},
                http_status=404,
            )
        return pal

    @staticmethod
    def _validate_name(value: str, field: str) -> None:
        if not isinstance(value, str):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message=f"{field} must be a string.",
                field=field,
                http_status=400,
            )
        if len(value) > MAX_NAME_LENGTH or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise DomainError(
                code="INVALID_CHARACTER_NAME",
                message="Character names must be at most 24 characters and contain no control characters.",
                field=field,
            )

    @staticmethod
    def _validate_gender(pal, gender: str, target_variant: str | None = None) -> str:
        mapping = {
            "male": PalGender.MALE.value,
            "female": PalGender.FEMALE.value,
            "none": "NONE",
        }
        if gender not in mapping:
            raise DomainError(
                code="INVALID_GENDER",
                message="gender must be male, female, or none.",
                field="gender",
            )
        if target_variant is None:
            genderless = pal.IsHuman or pal.IsOtomoTower
        else:
            genderless = bool(DataProvider.is_pal_human(target_variant)) or (
                target_variant.startswith("GYM_")
                and target_variant.endswith("_Otomo")
            )
        if genderless and gender != "none":
            raise DomainError(
                code="INVALID_GENDER",
                message="This Pal variant does not support a gender value.",
                field="gender",
            )
        if not genderless and gender == "none":
            raise DomainError(
                code="INVALID_GENDER",
                message="This Pal variant requires a gender value.",
                field="gender",
            )
        return mapping[gender]

    @staticmethod
    def _validate_skill_ids(
        values,
        field: str,
        exists: Callable[[str], bool],
        limit: int,
        existing=(),
    ) -> None:
        if not isinstance(values, (tuple, list)) or any(
            not isinstance(value, str) for value in values
        ):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message=f"{field} must be a list of skill IDs.",
                field=field,
                http_status=400,
            )
        if len(values) > limit:
            raise DomainError(
                code="SKILL_SLOT_LIMIT_EXCEEDED",
                message=f"{field} contains too many skills.",
                field=field,
                details={"maximum": limit, "actual": len(values)},
            )
        if len(set(values)) != len(values):
            raise DomainError(
                code="DUPLICATE_SKILL",
                message=f"{field} contains a duplicate skill ID.",
                field=field,
            )
        existing_values = set(existing or ())
        unknown = sorted(
            value
            for value in values
            if value not in existing_values and not exists(value)
        )
        if unknown:
            raise DomainError(
                code="UNKNOWN_SKILL",
                message=f"{field} contains an unknown skill ID.",
                field=field,
                details={"skills": unknown},
            )

    @staticmethod
    def _replace_array(pal, field: str, array_type: str, values) -> None:
        existing = PalObjects.get_ArrayProperty(pal._pal_param.get(field))
        if existing is None:
            pal._pal_param[field] = PalObjects.ArrayProperty(
                array_type, {"values": list(values)}
            )
        else:
            existing[:] = list(values)

    @staticmethod
    def _reject_unknown_fields(values: dict, allowed: set[str]) -> None:
        if not isinstance(values, dict):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="values must be an object.",
                field="values",
                http_status=400,
            )
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The command contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )

    @staticmethod
    def _require_int_range(value, minimum: int, maximum: int, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message=f"{field} must be an integer.",
                field=field,
                http_status=400,
            )
        if not minimum <= value <= maximum:
            raise DomainError(
                code="VALUE_OUT_OF_RANGE",
                message=f"{field} is outside the supported range.",
                field=field,
                details={"minimum": minimum, "maximum": maximum, "actual": value},
            )

    @staticmethod
    def _require_number_range(
        value, minimum: float, maximum: float, field: str
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message=f"{field} must be a finite number.",
                field=field,
                http_status=400,
            )
        if not minimum <= value <= maximum:
            raise DomainError(
                code="VALUE_OUT_OF_RANGE",
                message=f"{field} is outside the supported range.",
                field=field,
                details={"minimum": minimum, "maximum": maximum, "actual": value},
            )

    @staticmethod
    def _empty_command() -> None:
        raise DomainError(
            code="EMPTY_COMMAND",
            message="At least one update field is required.",
            http_status=400,
        )

    @staticmethod
    def _postcondition(message: str) -> None:
        raise DomainError(
            code="COMMAND_POSTCONDITION_FAILED",
            message=message,
            http_status=409,
        )

    @staticmethod
    def _result(entry, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "value": value,
        }

    @staticmethod
    def _player_identity(player) -> dict[str, Any]:
        return {"player_id": str(player.PlayerUId), "name": player.NickName or ""}

    @staticmethod
    def _player_progression(player) -> dict[str, Any]:
        return {
            "level": player.Level if player.Level is not None else 1,
            "experience": player.Exp if player.Exp is not None else 0,
            "technology_points": (
                player.TechnologyPoint if player.TechnologyPoint is not None else 0
            ),
            "boss_technology_points": (
                player.bossTechnologyPoint
                if player.bossTechnologyPoint is not None
                else 0
            ),
        }

    @staticmethod
    def _player_technology(player) -> dict[str, Any]:
        values = sorted(player.UnlockedRecipeTechnologyNames or [])
        return {"unlocked": values, "count": len(values)}

    @staticmethod
    def _pal_identity(pal) -> dict[str, Any]:
        gender = pal.Gender.value if pal.Gender is not None else "none"
        return {
            "pal_id": str(pal.InstanceId),
            "name": pal.NickName or "",
            "gender": {
                PalGender.MALE.value: "male",
                PalGender.FEMALE.value: "female",
            }.get(gender, "none"),
            "variant": pal.CharacterID,
            "boss": bool(pal.IsBOSS),
            "tower": bool(pal.IsTower),
            "rare": bool(pal.IsRarePal),
        }

    @staticmethod
    def _pal_progression(pal) -> dict[str, Any]:
        return {
            "level": pal.Level if pal.Level is not None else 1,
            "experience": pal.Exp if pal.Exp is not None else 0,
            "friendship_level": (
                pal.FriendshipLevel if pal.FriendshipLevel is not None else 0
            ),
            "health": pal.Hp if pal.Hp is not None else 0,
            "satiety": pal.FullStomach if pal.FullStomach is not None else 0,
            "sanity": pal.SanityValue if pal.SanityValue is not None else 0,
            "worker_sick": bool(pal.HasWorkerSick),
            "fainted": bool(pal.IsFaintedPal),
            "hunger_status": pal.HungerType,
            "physical_status": pal.PhysicalHealth,
        }

    @staticmethod
    def _pal_skills(pal) -> dict[str, list[str]]:
        return {
            "active": list(pal.EquipWaza or []),
            "mastered": list(pal.MasteredWaza or []),
            "passive": list(pal.PassiveSkillList or []),
        }

    @staticmethod
    def _pal_enhancement(pal) -> dict[str, Any]:
        return {
            "iv_hp": pal.Talent_HP or 0,
            "iv_melee": pal.Talent_Melee or 0,
            "iv_shot": pal.Talent_Shot or 0,
            "iv_defense": pal.Talent_Defense or 0,
            "soul_hp": pal.Rank_HP or 0,
            "soul_attack": pal.Rank_Attack or 0,
            "soul_defense": pal.Rank_Defence or 0,
            "soul_craft_speed": pal.Rank_CraftSpeed or 0,
            "condensation": pal.Rank or 1,
            "work_suitability": dict(pal.WorkSuitabilities or {}),
            "derived": {
                "max_health": pal.ComputedMaxHP,
                "attack": pal.ComputedAttack,
                "defense": pal.ComputedDefense,
                "craft_speed": pal.ComputedCraftSpeed,
            },
        }
