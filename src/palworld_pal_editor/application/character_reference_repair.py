from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.domain.commands import RepairMissingGuildHandles
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


MISSING_GUILD_HANDLES_REPAIR_KIND = "missing_guild_handles"


@dataclass(frozen=True)
class _MissingGuildHandle:
    pal_id: str
    guild_id: str
    group: Any


class CharacterReferenceRepairer:
    """Repair narrowly proven, one-sided guild handles in a loaded save."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def preview(self, *, index: CharacterIndex | None = None) -> dict[str, Any]:
        active_index = index or CharacterIndex(self._session.manager)
        candidates = self._repair_candidates(active_index)
        if candidates is None:
            return {
                "available": False,
                "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
                "repair_count": 0,
            }
        return {
            "available": True,
            "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
            "repair_count": len(candidates),
            "guild_count": len({candidate.guild_id for candidate in candidates}),
        }

    def execute(self, command: RepairMissingGuildHandles) -> dict[str, Any]:
        self._session.require_command(
            command.session_id,
            command.expected_revision,
            allow_raw_json=True,
        )
        index = CharacterIndex(self._session.manager)
        candidates = self._repair_candidates(index)
        if not candidates:
            raise DomainError(
                code="CHARACTER_REFERENCE_REPAIR_UNAVAILABLE",
                message=(
                    "The character reference problems cannot be repaired "
                    "automatically without risking save corruption."
                ),
                details={
                    "issues": [
                        issue.to_dict() for issue in index.hard_issues()
                    ]
                },
                http_status=409,
            )

        groups = {
            candidate.guild_id: candidate.group for candidate in candidates
        }

        def snapshot() -> dict[str, dict]:
            return {
                guild_id: group.snapshot()
                for guild_id, group in groups.items()
            }

        def restore(state: dict[str, dict]) -> None:
            for guild_id, group_state in state.items():
                groups[guild_id].restore(group_state)

        def summary(*, remaining: int) -> dict[str, Any]:
            return {
                "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
                "repair_count": len(candidates),
                "guild_count": len(groups),
                "remaining_hard_issue_count": remaining,
            }

        def mutate() -> None:
            for candidate in candidates:
                if not candidate.group.add_pal(candidate.pal_id):
                    raise DomainError(
                        code="CHARACTER_REFERENCE_REPAIR_FAILED",
                        message="A missing guild handle could not be added safely.",
                        details={
                            "repair_kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
                        },
                        http_status=409,
                    )

        def validate() -> None:
            remaining = CharacterIndex(self._session.manager).hard_issues()
            if remaining:
                raise DomainError(
                    code="CHARACTER_REFERENCE_REPAIR_FAILED",
                    message=(
                        "Character references remained inconsistent after "
                        "the attempted repair."
                    ),
                    details={
                        "issues": [issue.to_dict() for issue in remaining]
                    },
                    http_status=409,
                )

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="RepairMissingGuildHandles",
                target={
                    "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
                    "repair_count": len(candidates),
                },
                snapshot=snapshot,
                restore=restore,
                before=lambda: summary(
                    remaining=len(index.hard_issues())
                ),
                mutate=mutate,
                validate=validate,
                after=lambda: summary(remaining=0),
                affected_records=("level:GroupSaveDataMap",),
                allow_raw_json=True,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="CHARACTER_REFERENCE_REPAIR_FAILED",
                message="Character references could not be repaired safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error

        self._session.refresh_compatibility()
        return {
            "revision": entry.revision_after,
            "change": entry.to_dict(),
            "repair": summary(remaining=0),
            "saveCapabilities": self._session.save_capabilities,
        }

    def _repair_candidates(
        self, index: CharacterIndex
    ) -> tuple[_MissingGuildHandle, ...] | None:
        hard_issues = index.hard_issues()
        if not hard_issues:
            return None

        candidates: list[_MissingGuildHandle] = []
        seen: set[str] = set()
        for issue in hard_issues:
            candidate = self._candidate_for_issue(index, issue)
            if candidate is None or candidate.pal_id in seen:
                return None
            seen.add(candidate.pal_id)
            candidates.append(candidate)
        return tuple(candidates)

    def _candidate_for_issue(
        self, index: CharacterIndex, issue
    ) -> _MissingGuildHandle | None:
        if (
            issue.code != "PAL_GROUP_REFERENCE_MISMATCH"
            or issue.pal_id is None
            or issue.details.get("indexed_group_ids") != []
        ):
            return None

        pal_id = str(issue.pal_id)
        pal = index.pals.get(pal_id)
        if pal is None:
            return None
        declared_group_id = (
            None if pal.group_id is None else str(pal.group_id)
        )
        if (
            declared_group_id is None
            or issue.details.get("declared_group_id") != declared_group_id
            or index.group_references.get(pal_id, []) != []
        ):
            return None

        group_data = getattr(self._session.manager, "group_data", None)
        group = (
            group_data.get_group(declared_group_id)
            if group_data is not None
            else None
        )
        if (
            group is None
            or group.guild_format == "raw"
            or group.has_pal(pal_id)
        ):
            return None

        records = index.raw_records.get(pal_id, [])
        container_references = index.container_references.get(pal_id, [])
        if (
            len(records) != 1
            or records[0] is not pal._pal_obj
            or len(container_references) != 1
            or index._declared_slot(pal)
            != container_references[0].to_dict()
        ):
            return None

        owner_id = index._normalized_owner(pal)
        owner_references = index.owner_references.get(pal_id, [])
        player = (
            self._session.manager.player_mapping.get(owner_id)
            if owner_id is not None
            else None
        )
        player_group_id = (
            None
            if player is None or player.group_id is None
            else str(player.group_id)
        )
        if (
            owner_id is None
            or owner_references != [owner_id]
            or player_group_id != declared_group_id
            or not group.has_player(owner_id)
        ):
            return None

        return _MissingGuildHandle(
            pal_id=pal_id,
            guild_id=declared_group_id,
            group=group,
        )
