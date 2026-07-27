#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

namespace pal_editor_bridge
{
    inline constexpr std::int32_t protocol_version = 1;
    inline constexpr const char* bridge_version = "0.6.0";

    struct BridgeConfig
    {
        std::string bind_host{"127.0.0.1"};
        std::uint16_t bridge_port{8213};
        std::string rest_host{"127.0.0.1"};
        std::uint16_t rest_port{8212};
        std::string rest_username{"admin"};
        std::chrono::seconds token_ttl{std::chrono::minutes(30)};
    };

    struct ServerDescriptor
    {
        std::string name;
        std::string game_version;
        std::string world_guid;
        std::string platform{"Win64"};
        std::string instance_kind{"dedicated_server"};
    };

    struct AdminCredentials
    {
        std::string username;
        std::string admin_password;
    };

    class CredentialVerifier
    {
      public:
        virtual ~CredentialVerifier() = default;
        virtual bool verify_credentials(
            const std::string& username,
            const std::string& admin_password
        ) = 0;
        virtual std::optional<ServerDescriptor> server_descriptor(
            const AdminCredentials&
        );
        virtual std::vector<std::string> capabilities() const;
        virtual nlohmann::json players(const AdminCredentials&);
        virtual nlohmann::json execute(
            const AdminCredentials&,
            const nlohmann::json& command
        );
    };

    class PalworldRestCredentialVerifier final : public CredentialVerifier
    {
      public:
        explicit PalworldRestCredentialVerifier(BridgeConfig config);
        bool verify_credentials(
            const std::string& username,
            const std::string& admin_password
        ) override;
        std::optional<ServerDescriptor> server_descriptor(
            const AdminCredentials& credentials
        ) override;
        std::vector<std::string> capabilities() const override;
        nlohmann::json players(
            const AdminCredentials& credentials
        ) override;
        nlohmann::json execute(
            const AdminCredentials& credentials,
            const nlohmann::json& command
        ) override;

      private:
        BridgeConfig m_config;
    };

    class LocalCredentialVerifier final : public CredentialVerifier
    {
      public:
        LocalCredentialVerifier(
            std::string bootstrap_secret,
            ServerDescriptor descriptor
        );
        bool verify_credentials(
            const std::string& username,
            const std::string& admin_password
        ) override;
        std::optional<ServerDescriptor> server_descriptor(
            const AdminCredentials& credentials
        ) override;

      private:
        std::string m_bootstrap_secret;
        ServerDescriptor m_descriptor;
    };

    class GameCommandPort
    {
      public:
        virtual ~GameCommandPort() = default;
        virtual bool ready() const = 0;
        virtual std::vector<std::string> capabilities() const = 0;
        virtual nlohmann::json status() = 0;
        virtual nlohmann::json players() = 0;
        virtual nlohmann::json guilds() = 0;
        virtual nlohmann::json map_snapshot() = 0;
        virtual nlohmann::json player_details(
            const std::string& player_id
        ) = 0;
        virtual nlohmann::json inventory(
            const std::string& player_id
        ) = 0;
        virtual nlohmann::json pals(
            const std::string& player_id,
            const std::string& collection,
            std::size_t page_index,
            std::size_t page_size
        ) = 0;
        virtual nlohmann::json execute(const nlohmann::json& command) = 0;
    };

    class SessionRegistry
    {
      public:
        explicit SessionRegistry(std::chrono::seconds token_ttl);

        std::string issue(
            const std::string& username,
            const std::string& admin_password
        );
        bool valid(const std::string& token);
        std::optional<AdminCredentials> credentials(
            const std::string& token
        );
        void revoke(const std::string& token);
        void clear();

      private:
        using clock = std::chrono::steady_clock;

        void remove_expired(clock::time_point now);
        static std::string secure_token();

        struct SessionRecord
        {
            clock::time_point expires_at;
            AdminCredentials credentials;
        };

        std::chrono::seconds m_token_ttl;
        std::mutex m_mutex;
        std::unordered_map<std::string, SessionRecord> m_tokens;
    };

    class BridgeHost
    {
      public:
        BridgeHost(
            BridgeConfig config,
            ServerDescriptor server,
            std::unique_ptr<CredentialVerifier> credential_verifier,
            GameCommandPort& game
        );
        ~BridgeHost();

        BridgeHost(const BridgeHost&) = delete;
        BridgeHost& operator=(const BridgeHost&) = delete;

        std::uint16_t start();
        void stop();
        bool running() const;

      private:
        class Impl;
        std::unique_ptr<Impl> m_impl;
    };
} // namespace pal_editor_bridge
