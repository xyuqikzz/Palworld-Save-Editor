from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_PORT_SOURCE = (
    PROJECT_ROOT
    / "native"
    / "pal_editor_bridge"
    / "ue4ss"
    / "src"
    / "pal_editor_bridge_mod.cpp"
)
RUNTIME_SOURCE = (
    PROJECT_ROOT
    / "native"
    / "pal_editor_bridge"
    / "ue4ss"
    / "src"
    / "palworld_runtime.cpp"
)


def function_body(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


class PalEditorBridgePerformanceTests(unittest.TestCase):
    def test_command_queue_precedes_idle_capability_refresh(self) -> None:
        source = GAME_PORT_SOURCE.read_text(encoding="utf-8")
        body = function_body(
            source,
            "void GamePort::drain_game_thread()",
            "void GamePort::stop_accepting()",
        )

        self.assertLess(
            body.index("pending.swap(m_queue)"),
            body.index("refresh_runtime_capabilities()"),
        )
        self.assertIn("if (!pending.empty())", body)
        self.assertIn("runtime_signatures_ready()", body)
        self.assertIn("refresh_authority_capabilities()", body)

    def test_pal_grant_avoids_repeated_manager_scan_and_reports_timings(
        self,
    ) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        grant_body = function_body(
            source,
            "nlohmann::json PalworldRuntime::grant_pal(",
            "} // namespace pal_editor_bridge::ue4ss",
        )

        self.assertIn("GetCharacterManager", source)
        self.assertIn("cached_world_context", source)
        self.assertNotIn(
            'FindFirstOf(\n                std::string_view{"PalCharacterManager"}',
            grant_body,
        )
        self.assertNotIn(
            "occupied_pal_slots",
            grant_body,
            "Pal grant must not validate capacity by scanning every Palbox slot "
            "on the game thread; FindEmptySlot is the authoritative constant-time check.",
        )
        self.assertIn("find_empty_pal_slot", grant_body)
        self.assertIn('"timingsMs"', grant_body)
        self.assertIn('"playerLookup"', grant_body)
        self.assertIn('"createIndividual"', grant_body)
        self.assertIn('"total"', grant_body)
        self.assertIn(
            "begin_pal_grant_callback_probe(",
            grant_body,
        )
        self.assertIn(
            '"callbackDiagnostics"',
            grant_body,
        )

    def test_pal_grant_callback_probe_is_function_scoped(self) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")

        self.assertIn(
            "attach_granted_individual->RegisterPreHook(",
            source,
        )
        self.assertIn(
            '"palGrantCallbackDiagnostics"',
            source,
        )
        self.assertNotIn(
            "RegisterProcessEventPreCallback",
            source,
            "Pal grant diagnostics must not add a global ProcessEvent hook.",
        )

    def test_runtime_health_exposes_display_units_without_losing_raw_values(
        self,
    ) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")

        self.assertIn("runtime_fixed_point_scale", source)
        self.assertIn('"hpRaw"', source)
        self.assertIn('"maxHpRaw"', source)
        self.assertIn('"hp"', source)
        self.assertIn('"maxHp"', source)
        self.assertIn("fixed_point_display_value(hp_raw)", source)
        self.assertIn("positive_fixed_point_display_value(max_hp_raw)", source)

    def test_pal_grant_cheat_limits_are_explicit_and_bounded(self) -> None:
        source = GAME_PORT_SOURCE.read_text(encoding="utf-8")

        self.assertIn('payload.find("unrestricted")', source)
        self.assertIn("const auto iv_maximum = unrestricted ? 255 : 100", source)
        self.assertIn(
            "const auto condensation_maximum = unrestricted ? 255 : 5",
            source,
        )
        self.assertIn(
            "const auto soul_maximum = unrestricted ? 255 : 20",
            source,
        )

    def test_pal_grant_level_is_bounded_to_current_game_maximum(self) -> None:
        source = GAME_PORT_SOURCE.read_text(encoding="utf-8")

        self.assertRegex(
            source,
            r'"Pal level",\s*1,\s*80',
        )

    def test_player_details_does_not_eagerly_read_inventory_or_pals(
        self,
    ) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        details_body = function_body(
            source,
            "nlohmann::json player_details(const std::string& player_id)",
            "UObject* individual_parameter_for_actor",
        )

        self.assertNotIn(
            "inventory_snapshot(",
            details_body,
            "Player profile reads must not scan inventory containers.",
        )
        self.assertNotIn(
            "pal_snapshot(",
            details_body,
            "Player profile reads must not scan every Palbox slot.",
        )

    def test_pal_snapshot_only_inspects_the_requested_page(self) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        snapshot_body = function_body(
            source,
            "nlohmann::json pal_snapshot(",
            "nlohmann::json live_diagnostics() const",
        )

        self.assertIn("page_index", snapshot_body)
        self.assertIn("page_size", snapshot_body)
        self.assertIn("start_index", snapshot_body)
        self.assertIn("end_index", snapshot_body)
        self.assertNotIn(
            "index < slots.size()",
            snapshot_body,
            "Palbox reads must be bounded to one requested page.",
        )


if __name__ == "__main__":
    unittest.main()
