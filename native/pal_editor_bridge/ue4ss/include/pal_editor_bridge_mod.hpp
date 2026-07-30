#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <deque>
#include <future>
#include <memory>
#include <mutex>

#include <Mod/CppUserModBase.hpp>
#include <pal_editor_bridge/bridge_core.hpp>
#include <palworld_runtime.hpp>

namespace pal_editor_bridge::ue4ss
{
    class LocalBridgeInstance;

    class GamePort final : public GameCommandPort
    {
      public:
        explicit GamePort(bool dedicated_process);
        ~GamePort() override;

        void mark_ready();
        void drain_game_thread();
        void stop_accepting();

        bool ready() const override;
        std::vector<std::string> capabilities() const override;
        nlohmann::json status() override;
        nlohmann::json players() override;
        nlohmann::json guilds() override;
        nlohmann::json map_snapshot() override;
        nlohmann::json player_details(
            const std::string& player_id
        ) override;
        nlohmann::json inventory(
            const std::string& player_id
        ) override;
        nlohmann::json pals(
            const std::string& player_id,
            const std::string& collection,
            std::size_t page_index,
            std::size_t page_size
        ) override;
        nlohmann::json execute(const nlohmann::json& command) override;

      private:
        enum class PendingState : std::uint8_t
        {
            queued,
            executing,
            completed,
            cancelled,
        };

        struct PendingCommand
        {
            nlohmann::json command;
            std::promise<nlohmann::json> completion;
            std::atomic<PendingState> state{PendingState::queued};
            std::chrono::steady_clock::time_point queued_at{
                std::chrono::steady_clock::now()
            };
        };

        static constexpr std::size_t max_pending_commands = 64;
        static constexpr std::size_t max_commands_per_tick = 4;
        static constexpr std::chrono::milliseconds game_thread_budget{2};

        nlohmann::json execute_on_game_thread(
            const nlohmann::json& command
        );
        void refresh_runtime_capabilities();
        void refresh_authority_capabilities();
        bool runtime_signatures_ready() const;

        bool m_dedicated_process;
        std::atomic_bool m_ready{false};
        std::atomic_bool m_accepting{true};
        std::atomic_bool m_inventory_ready{false};
        std::atomic_bool m_experience_ready{false};
        std::atomic_bool m_pal_ready{false};
        std::atomic_bool m_player_list_ready{false};
        std::atomic_bool m_guild_list_ready{false};
        std::atomic_bool m_player_details_ready{false};
        std::atomic_bool m_inventory_read_ready{false};
        std::atomic_bool m_pal_list_ready{false};
        std::atomic_bool m_map_read_ready{false};
        std::uint32_t m_ticks_until_runtime_refresh{0};
        std::uint32_t m_ticks_until_authority_refresh{0};
        std::mutex m_queue_mutex;
        std::deque<std::shared_ptr<PendingCommand>> m_queue;
        PalworldRuntime m_runtime;
    };

    class PalEditorBridgeMod final : public RC::CppUserModBase
    {
      public:
        PalEditorBridgeMod();
        ~PalEditorBridgeMod() override;

        void on_unreal_init() override;

      private:
        bool m_dedicated_process;
        GamePort m_game;
        std::unique_ptr<BridgeHost> m_host;
        std::unique_ptr<LocalBridgeInstance> m_local_instance;
        std::uint64_t m_tick_callback_id{0};
    };
} // namespace pal_editor_bridge::ue4ss
