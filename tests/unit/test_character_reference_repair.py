from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from palworld_pal_editor.application.character_reference_repair import (
    CharacterReferenceRepairer,
    MISSING_GUILD_HANDLES_REPAIR_KIND,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.domain.commands import RepairMissingGuildHandles
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.core.pal_objects import toUUID
from tests.unit.test_structural_pal_editor import GROUP_ID, PAL_ID, make_manager


def _broken_session():
    manager, _player, pal = make_manager()
    group = manager.group_data.get_group(GROUP_ID)
    group.del_pal(PAL_ID)
    session = SaveSession.from_loaded_manager(
        manager, Path("synthetic-character-reference-repair")
    )
    return session, manager, pal, group


def test_save_failure_offers_only_the_proven_missing_guild_handle_repair() -> None:
    session, _manager, _pal, _group = _broken_session()

    with pytest.raises(DomainError) as raised:
        SaveWriter()._validate_global_invariants(session)

    assert raised.value.code == "CHARACTER_INDEX_INVARIANT_FAILED"
    assert raised.value.retryable is True
    assert raised.value.details["repair"] == {
        "available": True,
        "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
        "repair_count": 1,
        "guild_count": 1,
    }
    assert [
        issue["code"] for issue in raised.value.details["issues"]
    ] == ["PAL_GROUP_REFERENCE_MISMATCH"]


def test_repair_adds_the_missing_handle_and_records_a_level_change() -> None:
    session, manager, _pal, group = _broken_session()

    result = CharacterReferenceRepairer(session).execute(
        RepairMissingGuildHandles(
            session_id=session.session_id,
            expected_revision=0,
        )
    )

    assert result["revision"] == 1
    assert result["repair"] == {
        "kind": MISSING_GUILD_HANDLES_REPAIR_KIND,
        "repair_count": 1,
        "guild_count": 1,
        "remaining_hard_issue_count": 0,
    }
    assert group.has_pal(PAL_ID)
    assert CharacterIndex(manager).hard_issues() == []
    assert session.changes()[0]["command"] == "RepairMissingGuildHandles"
    assert session.changes()[0]["affected_records"] == [
        "level:GroupSaveDataMap"
    ]
    assert (
        session.compatibility()
        .capabilities["pal.structural_edit"]
        .writable
        is True
    )


def test_repair_rejects_an_unknown_declared_guild() -> None:
    session, _manager, pal, group = _broken_session()
    unknown_group = toUUID("77777777-7777-7777-7777-777777777777")
    pal.group_id = unknown_group

    preview = CharacterReferenceRepairer(session).preview()
    assert preview["available"] is False

    with pytest.raises(DomainError) as raised:
        CharacterReferenceRepairer(session).execute(
            RepairMissingGuildHandles(
                session_id=session.session_id,
                expected_revision=0,
            )
        )

    assert raised.value.code == "CHARACTER_REFERENCE_REPAIR_UNAVAILABLE"
    assert not group.has_pal(PAL_ID)


def test_repair_rejects_mixed_or_ambiguous_character_damage() -> None:
    session, manager, pal, group = _broken_session()
    manager._entities_list.append(deepcopy(pal._pal_obj))

    preview = CharacterReferenceRepairer(session).preview()
    assert preview["available"] is False

    with pytest.raises(DomainError) as raised:
        SaveWriter()._validate_global_invariants(session)

    assert raised.value.code == "CHARACTER_INDEX_INVARIANT_FAILED"
    assert raised.value.retryable is False
    assert raised.value.details["repair"]["available"] is False
    assert not group.has_pal(PAL_ID)
