#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace pal_editor_bridge::ue4ss
{
    struct PalGrantOptions
    {
        bool unrestricted{false};
        std::optional<std::vector<std::string>> passive_skills;
        std::optional<std::int32_t> iv_hp;
        std::optional<std::int32_t> iv_melee;
        std::optional<std::int32_t> iv_shot;
        std::optional<std::int32_t> iv_defense;
        std::optional<std::int32_t> condensation;
        std::optional<std::int32_t> soul_hp;
        std::optional<std::int32_t> soul_attack;
        std::optional<std::int32_t> soul_defense;
        std::optional<std::int32_t> soul_craft_speed;
    };

    class PalworldRuntime final
    {
      public:
        PalworldRuntime();
        ~PalworldRuntime();

        PalworldRuntime(const PalworldRuntime&) = delete;
        PalworldRuntime& operator=(const PalworldRuntime&) = delete;

        void initialize();
        void refresh_instance_mode(bool dedicated_process);

        bool inventory_ready() const;
        bool experience_ready() const;
        bool pal_ready() const;
        bool player_list_ready() const;
        bool guild_list_ready() const;
        bool player_details_ready() const;
        bool inventory_read_ready() const;
        bool pal_list_ready() const;
        bool map_read_ready() const;
        bool authoritative() const;
        std::string instance_mode() const;
        nlohmann::json status() const;
        nlohmann::json players();
        nlohmann::json guilds();
        nlohmann::json map_snapshot();
        nlohmann::json player_details(const std::string& player_id);
        nlohmann::json inventory_snapshot(const std::string& player_id);
        nlohmann::json pal_snapshot(
            const std::string& player_id,
            const std::string& collection,
            std::size_t page_index,
            std::size_t page_size
        );
        nlohmann::json live_diagnostics() const;
        nlohmann::json reflect_functions(
            const std::string& fragment
        ) const;
        nlohmann::json probe_runtime_data(
            const std::string& player_id
        );
        nlohmann::json probe_player_experience(
            const std::string& player_id,
            std::int32_t amount,
            bool apply
        );
        nlohmann::json probe_experience_database(
            const std::string& player_id,
            std::int32_t amount,
            bool apply
        );
        nlohmann::json grant_item(
            const std::string& player_id,
            const std::string& item_id,
            std::int32_t quantity
        );
        nlohmann::json add_player_experience(
            const std::string& player_id,
            std::int32_t amount
        );
        nlohmann::json grant_pal(
            const std::string& player_id,
            const std::string& character_id,
            std::int32_t level,
            PalGrantOptions options
        );

      private:
        class Impl;
        std::unique_ptr<Impl> m_impl;
    };
} // namespace pal_editor_bridge::ue4ss
