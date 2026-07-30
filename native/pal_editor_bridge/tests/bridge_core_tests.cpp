#include <pal_editor_bridge/bridge_core.hpp>

#include <algorithm>
#include <cassert>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <thread>

#include <httplib.h>

using namespace std::chrono_literals;

namespace
{
    class FakeCredentialVerifier final
        : public pal_editor_bridge::CredentialVerifier
    {
      public:
        struct SaveState
        {
            std::atomic_int calls{0};
            std::atomic_bool fail{false};
        };

        explicit FakeCredentialVerifier(
            std::shared_ptr<SaveState> save_state = nullptr
        )
            : m_save_state(std::move(save_state))
        {
        }

        bool verify_credentials(
            const std::string& username,
            const std::string& admin_password
        ) override
        {
            return username == "admin" && admin_password == "correct";
        }

        std::vector<std::string> capabilities() const override
        {
            return {
                "player.ban",
                "player.kick",
                "player.unban",
                "server.announce",
                "world.save",
                "world.shutdown",
            };
        }

        nlohmann::json players(
            const pal_editor_bridge::AdminCredentials&
        ) override
        {
            return nlohmann::json::array(
                {
                    {
                        {"accountName", "protocol-account"},
                        {"building_count", 12},
                        {"ping", 2.5},
                        {"playerId", "{PLAYER-1}"},
                        {"userId", "steam_test"},
                    },
                }
            );
        }

        nlohmann::json execute(
            const pal_editor_bridge::AdminCredentials& credentials,
            const nlohmann::json& command
        ) override
        {
            assert(credentials.admin_password == "correct");
            const auto operation = command["operation"].get<std::string>();
            if (operation == "world.save" && m_save_state)
            {
                ++m_save_state->calls;
                if (m_save_state->fail.load())
                {
                    return {
                        {"state", "failed"},
                        {"message", "Synthetic save failure."},
                    };
                }
            }
            if (
                operation == "player.kick"
                || operation == "player.ban"
                || operation == "player.unban"
            )
            {
                assert(command["target"]["user_id"] == "steam_test");
            }
            return {
                {"state", "completed"},
                {"result", {{"operation", operation}}},
            };
        }

      private:
        std::shared_ptr<SaveState> m_save_state;
    };

    class FakeGame final : public pal_editor_bridge::GameCommandPort
    {
      public:
        bool ready() const override
        {
            return true;
        }

        std::vector<std::string> capabilities() const override
        {
            return {
                "server.status",
                "inventory.grant",
                "player.list",
                "guild.list",
                "player.details",
                "inventory.read",
                "pal.list",
                "map.read",
            };
        }

        nlohmann::json status() override
        {
            return {{"onlinePlayerCount", 1}};
        }

        nlohmann::json players() override
        {
            return nlohmann::json::array(
                {{{"name", "Protocol Player"}, {"playerId", "player-1"}}}
            );
        }

        nlohmann::json guilds() override
        {
            return nlohmann::json::array(
                {{{"name", "Protocol Guild"}, {"guildId", "guild-1"}}}
            );
        }

        nlohmann::json map_snapshot() override
        {
            return {
                {"live", true},
                {
                    "players",
                    nlohmann::json::array({
                        {
                            {"name", "Protocol Player"},
                            {"playerId", "player-1"},
                            {
                                "position",
                                {{"x", 1.0}, {"y", 2.0}, {"z", 3.0}}
                            },
                        },
                    })
                },
                {"guilds", guilds()},
            };
        }

        nlohmann::json player_details(
            const std::string& player_id
        ) override
        {
            assert(player_id == "player-1");
            return {
                {
                    "player",
                    {
                        {"name", "Protocol Player"},
                        {"playerId", player_id},
                        {"level", 25},
                    }
                },
            };
        }

        nlohmann::json inventory(
            const std::string& player_id
        ) override
        {
            assert(player_id == "player-1");
            return {
                {"status", "available"},
                {"containers", nlohmann::json::array()},
            };
        }

        nlohmann::json pals(
            const std::string& player_id,
            const std::string& collection,
            std::size_t page_index,
            std::size_t page_size
        ) override
        {
            assert(player_id == "player-1");
            assert(page_index == 1);
            assert(page_size == 12);
            return {
                {"status", "available"},
                {"collection", collection},
                {"pageIndex", page_index},
                {"pageSize", page_size},
                {"pageCount", 3},
                {"entries", nlohmann::json::array()},
            };
        }

        nlohmann::json execute(const nlohmann::json& command) override
        {
            if (
                command.contains("payload")
                && command["payload"].value("forcePartial", false)
            )
            {
                return {
                    {"state", "partial"},
                    {"message", "One field changed before validation stopped."},
                    {"result", {{"changed", 1}, {"failed", 1}}},
                };
            }
            return {
                {"state", "completed"},
                {"result", {{"granted", 1}}},
            };
        }
    };
}

int main()
{
    pal_editor_bridge::SessionRegistry registry(30s);
    const auto token = registry.issue("admin", "correct");
    assert(token.size() == 64);
    assert(registry.valid(token));
    assert(registry.credentials(token)->admin_password == "correct");
    registry.revoke(token);
    assert(!registry.valid(token));

    pal_editor_bridge::SessionRegistry expiring_registry(1s);
    const auto expiring_token =
        expiring_registry.issue("admin", "correct");
    assert(expiring_registry.valid(expiring_token));
    std::this_thread::sleep_for(1100ms);
    assert(!expiring_registry.valid(expiring_token));

    FakeCredentialVerifier verifier;
    assert(verifier.verify_credentials("admin", "correct"));
    assert(!verifier.verify_credentials("admin", "wrong"));

    pal_editor_bridge::ServerDescriptor local_descriptor;
    local_descriptor.name = "Local Palworld";
    local_descriptor.instance_kind = "local_game";
    pal_editor_bridge::LocalCredentialVerifier local_verifier(
        std::string(64, 'a'),
        local_descriptor
    );
    assert(local_verifier.verify_credentials("local", std::string(64, 'a')));
    assert(!local_verifier.verify_credentials("admin", std::string(64, 'a')));
    assert(!local_verifier.verify_credentials("local", std::string(64, 'b')));
    assert(
        local_verifier
            .server_descriptor({"local", std::string(64, 'a')})
            ->instance_kind
        == "local_game"
    );

    httplib::Server rest_server;
    std::atomic_bool fail_rest_save{false};
    std::mutex rest_requests_mutex;
    std::vector<std::pair<std::string, nlohmann::json>> rest_requests;
    rest_server.Get(
        "/v1/api/players",
        [](const httplib::Request&, httplib::Response& response) {
            response.set_content(
                R"({"players":[{"name":"Online","playerId":"player-1","userId":"steam_test"}]})",
                "application/json"
            );
        }
    );
    const auto record_rest_request = [&rest_requests, &rest_requests_mutex](
        const httplib::Request& request,
        httplib::Response& response
    ) {
        std::scoped_lock lock(rest_requests_mutex);
        rest_requests.emplace_back(
            request.path,
            request.body.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json::parse(request.body)
        );
        response.set_content("{}", "application/json");
    };
    rest_server.Post(
        "/v1/api/save",
        [&record_rest_request, &fail_rest_save](
            const httplib::Request& request,
            httplib::Response& response
        ) {
            record_rest_request(request, response);
            if (fail_rest_save.load())
            {
                response.status = 500;
            }
        }
    );
    rest_server.Post("/v1/api/announce", record_rest_request);
    rest_server.Post("/v1/api/kick", record_rest_request);
    rest_server.Post("/v1/api/ban", record_rest_request);
    rest_server.Post("/v1/api/unban", record_rest_request);
    rest_server.Post("/v1/api/shutdown", record_rest_request);
    const auto rest_port = rest_server.bind_to_any_port("127.0.0.1");
    assert(rest_port > 0);
    std::thread rest_thread([&rest_server]() {
        rest_server.listen_after_bind();
    });

    pal_editor_bridge::BridgeConfig rest_config;
    rest_config.rest_port = static_cast<std::uint16_t>(rest_port);
    pal_editor_bridge::PalworldRestCredentialVerifier rest_verifier(
        rest_config
    );
    const pal_editor_bridge::AdminCredentials rest_credentials{
        "admin",
        "correct",
    };
    const auto rest_capabilities = rest_verifier.capabilities();
    assert(rest_capabilities.size() == 6);
    assert(
        std::ranges::find(rest_capabilities, "server.announce")
        != rest_capabilities.end()
    );
    assert(
        std::ranges::find(rest_capabilities, "player.unban")
        != rest_capabilities.end()
    );
    assert(
        rest_verifier.execute(
            rest_credentials,
            {
                {"operation", "server.announce"},
                {"target", nlohmann::json::object()},
                {"payload", {{"message", "Maintenance soon"}}},
            }
        )["state"] == "completed"
    );
    assert(
        rest_verifier.execute(
            rest_credentials,
            {
                {"operation", "player.kick"},
                {"target", {{"user_id", "steam_test"}}},
                {"payload", {{"message", "Administrator action"}}},
            }
        )["state"] == "completed"
    );
    const auto invalid_ban = rest_verifier.execute(
        rest_credentials,
        {
            {"operation", "player.ban"},
            {"target", {{"user_id", "steam_not_online"}}},
            {"payload", nlohmann::json::object()},
        }
    );
    assert(invalid_ban["state"] == "failed");
    assert(
        rest_verifier.execute(
            rest_credentials,
            {
                {"operation", "player.unban"},
                {"target", {{"user_id", "steam_banned"}}},
                {"payload", nlohmann::json::object()},
            }
        )["state"] == "completed"
    );
    assert(
        rest_verifier.execute(
            rest_credentials,
            {
                {"operation", "world.shutdown"},
                {"target", nlohmann::json::object()},
                {
                    "payload",
                    {
                        {"wait_time", 30},
                        {"message", "Restarting"},
                    }
                },
            }
        )["state"] == "completed"
    );
    {
        std::scoped_lock lock(rest_requests_mutex);
        assert(rest_requests.size() == 5);
        assert(rest_requests[0].first == "/v1/api/announce");
        assert(rest_requests[0].second["message"] == "Maintenance soon");
        assert(rest_requests[1].first == "/v1/api/kick");
        assert(rest_requests[1].second["userid"] == "steam_test");
        assert(rest_requests[2].first == "/v1/api/unban");
        assert(rest_requests[2].second["userid"] == "steam_banned");
        assert(rest_requests[2].second.size() == 1);
        assert(rest_requests[3].first == "/v1/api/save");
        assert(rest_requests[4].first == "/v1/api/shutdown");
        assert(rest_requests[4].second["waittime"] == 30);
    }
    fail_rest_save.store(true);
    assert(
        rest_verifier.execute(
            rest_credentials,
            {
                {"operation", "world.shutdown"},
                {"target", nlohmann::json::object()},
                {
                    "payload",
                    {
                        {"wait_time", 30},
                        {"message", "Must not be scheduled"},
                    }
                },
            }
        )["state"] == "failed"
    );
    {
        std::scoped_lock lock(rest_requests_mutex);
        assert(rest_requests.size() == 5);
        assert(rest_requests.back().first == "/v1/api/save");
    }
    rest_server.stop();
    rest_thread.join();

    FakeGame game;
    assert(game.ready());
    assert(game.capabilities().size() == 8);
    assert(game.status()["onlinePlayerCount"] == 1);
    assert(game.execute({})["state"] == "completed");

    pal_editor_bridge::BridgeConfig config;
    config.bridge_port = 48213;
    pal_editor_bridge::ServerDescriptor server;
    server.name = "Protocol Test Server";
    server.game_version = "test";
    server.world_guid = "test-world";
    pal_editor_bridge::BridgeHost host(
        config,
        server,
        std::make_unique<FakeCredentialVerifier>(),
        game
    );
    const auto bound_port = host.start();
    assert(bound_port == config.bridge_port);
    for (auto attempt = 0; attempt < 100 && !host.running(); ++attempt)
    {
        std::this_thread::sleep_for(10ms);
    }
    assert(host.running());

    httplib::Client client("127.0.0.1", config.bridge_port);
    const auto bad_login = client.Post(
        "/v1/auth/login",
        R"({"protocolVersion":1,"username":"admin","adminPassword":"wrong"})",
        "application/json"
    );
    assert(bad_login && bad_login->status == 401);

    const auto login = client.Post(
        "/v1/auth/login",
        R"({"protocolVersion":1,"username":"admin","adminPassword":"correct"})",
        "application/json"
    );
    assert(login && login->status == 200);
    const auto login_body = nlohmann::json::parse(login->body);
    assert(login_body["protocolVersion"] == 1);
    assert(login_body["revision"] == 0);
    assert(login_body["server"]["name"] == "Protocol Test Server");
    assert(login_body["server"]["instanceKind"] == "dedicated_server");
    assert(login_body["capabilities"].size() == 13);
    const auto session_token = login_body["token"].get<std::string>();
    const httplib::Headers authorization{
        {"Authorization", "Bearer " + session_token},
    };

    const auto status = client.Get("/v1/status", authorization);
    assert(status && status->status == 200);
    assert(nlohmann::json::parse(status->body)["ready"] == true);
    assert(
        nlohmann::json::parse(status->body)["capabilities"].size()
        == 13
    );

    const auto players = client.Get("/v1/players", authorization);
    assert(players && players->status == 200);
    assert(
        nlohmann::json::parse(players->body)["players"][0]["name"]
        == "Protocol Player"
    );
    assert(
        nlohmann::json::parse(players->body)["players"][0]["userId"]
        == "steam_test"
    );
    assert(
        nlohmann::json::parse(players->body)["players"][0]["buildingCount"]
        == 12
    );

    const auto guilds = client.Get("/v1/guilds", authorization);
    assert(guilds && guilds->status == 200);
    assert(
        nlohmann::json::parse(guilds->body)["guilds"][0]["name"]
        == "Protocol Guild"
    );

    const auto map = client.Get("/v1/map", authorization);
    assert(map && map->status == 200);
    assert(
        nlohmann::json::parse(map->body)["players"][0]["position"]["z"]
        == 3.0
    );

    const auto player_details = client.Get(
        "/v1/player-details?playerId=player-1",
        authorization
    );
    assert(player_details && player_details->status == 200);
    assert(
        nlohmann::json::parse(player_details->body)["player"]["level"]
        == 25
    );

    const auto inventory = client.Get(
        "/v1/player-inventory?playerId=player-1",
        authorization
    );
    assert(inventory && inventory->status == 200);
    assert(
        nlohmann::json::parse(inventory->body)["status"]
        == "available"
    );

    const auto pals = client.Get(
        "/v1/player-pals?playerId=player-1&page=1&pageSize=12",
        authorization
    );
    assert(pals && pals->status == 200);
    assert(nlohmann::json::parse(pals->body)["pageIndex"] == 1);
    assert(
        nlohmann::json::parse(pals->body)["collection"] == "palbox"
    );

    const auto party_pals = client.Get(
        "/v1/player-pals?playerId=player-1&collection=party&page=1&pageSize=12",
        authorization
    );
    assert(party_pals && party_pals->status == 200);
    assert(
        nlohmann::json::parse(party_pals->body)["collection"] == "party"
    );

    const auto invalid_pal_collection = client.Get(
        "/v1/player-pals?playerId=player-1&collection=unknown",
        authorization
    );
    assert(
        invalid_pal_collection && invalid_pal_collection->status == 400
    );

    const auto invalid_pal_page = client.Get(
        "/v1/player-pals?playerId=player-1&page=0&pageSize=31",
        authorization
    );
    assert(invalid_pal_page && invalid_pal_page->status == 400);

    nlohmann::json command{
        {"protocolVersion", 1},
        {"commandId", "command-1"},
        {"operation", "inventory.grant"},
        {"expectedRevision", 0},
        {"target", {{"playerUid", "player-1"}}},
        {"payload", {{"itemId", "TestItem"}, {"quantity", 1}}},
    };
    const auto command_response = client.Post(
        "/v1/commands",
        authorization,
        command.dump(),
        "application/json"
    );
    assert(command_response && command_response->status == 200);
    const auto command_body =
        nlohmann::json::parse(command_response->body);
    assert(command_body["state"] == "completed");
    assert(command_body["revision"] == 1);

    nlohmann::json save_command{
        {"protocolVersion", 1},
        {"commandId", "command-save"},
        {"operation", "world.save"},
        {"expectedRevision", 1},
        {"target", nlohmann::json::object()},
        {"payload", nlohmann::json::object()},
    };
    const auto save_response = client.Post(
        "/v1/commands",
        authorization,
        save_command.dump(),
        "application/json"
    );
    assert(save_response && save_response->status == 200);
    assert(
        nlohmann::json::parse(save_response->body)["result"]["operation"]
        == "world.save"
    );

    nlohmann::json announcement_command{
        {"protocolVersion", 1},
        {"commandId", "command-announce"},
        {"operation", "server.announce"},
        {"expectedRevision", 2},
        {"target", nlohmann::json::object()},
        {"payload", {{"message", "Maintenance soon"}}},
    };
    const auto announcement_response = client.Post(
        "/v1/commands",
        authorization,
        announcement_command.dump(),
        "application/json"
    );
    assert(announcement_response && announcement_response->status == 200);
    assert(
        nlohmann::json::parse(announcement_response->body)["revision"]
        == 3
    );

    nlohmann::json kick_command{
        {"protocolVersion", 1},
        {"commandId", "command-kick"},
        {"operation", "player.kick"},
        {"expectedRevision", 3},
        {
            "target",
            {
                {"player_uid", "player-1"},
                {"user_id", "steam_test"},
            }
        },
        {"payload", {{"message", "Removed by an administrator"}}},
    };
    const auto kick_response = client.Post(
        "/v1/commands",
        authorization,
        kick_command.dump(),
        "application/json"
    );
    assert(kick_response && kick_response->status == 200);
    assert(nlohmann::json::parse(kick_response->body)["revision"] == 4);

    nlohmann::json shutdown_command{
        {"protocolVersion", 1},
        {"commandId", "command-shutdown"},
        {"operation", "world.shutdown"},
        {"expectedRevision", 4},
        {"target", nlohmann::json::object()},
        {
            "payload",
            {
                {"message", "Server restarting"},
                {"wait_time", 30},
            }
        },
    };
    const auto shutdown_response = client.Post(
        "/v1/commands",
        authorization,
        shutdown_command.dump(),
        "application/json"
    );
    assert(shutdown_response && shutdown_response->status == 200);
    assert(
        nlohmann::json::parse(shutdown_response->body)["revision"]
        == 5
    );

    const auto repeated_response = client.Post(
        "/v1/commands",
        authorization,
        command.dump(),
        "application/json"
    );
    assert(repeated_response && repeated_response->status == 200);
    assert(nlohmann::json::parse(repeated_response->body) == command_body);

    command["payload"]["quantity"] = 2;
    const auto reused_id = client.Post(
        "/v1/commands",
        authorization,
        command.dump(),
        "application/json"
    );
    assert(reused_id && reused_id->status == 409);
    assert(
        nlohmann::json::parse(reused_id->body)["error"]["code"]
        == "REMOTE_COMMAND_ID_REUSED"
    );

    command["commandId"] = "command-2";
    const auto stale_revision = client.Post(
        "/v1/commands",
        authorization,
        command.dump(),
        "application/json"
    );
    assert(stale_revision && stale_revision->status == 409);
    assert(
        nlohmann::json::parse(stale_revision->body)["error"]["code"]
        == "STALE_REVISION"
    );

    nlohmann::json partial_command{
        {"protocolVersion", 1},
        {"commandId", "command-partial"},
        {"operation", "inventory.grant"},
        {"expectedRevision", 5},
        {"target", {{"playerUid", "player-1"}}},
        {"payload", {{"forcePartial", true}}},
    };
    const auto partial_response = client.Post(
        "/v1/commands",
        authorization,
        partial_command.dump(),
        "application/json"
    );
    assert(partial_response && partial_response->status == 200);
    const auto partial_body =
        nlohmann::json::parse(partial_response->body);
    assert(partial_body["state"] == "partial");
    assert(partial_body["revision"] == 6);
    assert(partial_body["persistence"]["state"] == "dirty");
    assert(partial_body["persistence"]["dirtyRevision"] == 6);

    const auto dirty_status = client.Get("/v1/status", authorization);
    assert(dirty_status && dirty_status->status == 200);
    assert(
        nlohmann::json::parse(dirty_status->body)
            ["persistence"]["state"] == "dirty"
    );

    const auto logout = client.Post(
        "/v1/auth/logout",
        authorization,
        "",
        "application/json"
    );
    assert(logout && logout->status == 200);
    const auto logged_out_status = client.Get("/v1/status", authorization);
    assert(logged_out_status && logged_out_status->status == 401);
    host.stop();

    auto invalid_config = config;
    invalid_config.bind_host = "0.0.0.0";
    pal_editor_bridge::BridgeHost public_host(
        invalid_config,
        server,
        std::make_unique<FakeCredentialVerifier>(),
        game
    );
    auto rejected_public_bind = false;
    try
    {
        public_host.start();
    }
    catch (const std::runtime_error&)
    {
        rejected_public_bind = true;
    }
    assert(rejected_public_bind);

    auto dynamic_config = config;
    dynamic_config.bridge_port = 0;
    pal_editor_bridge::BridgeHost dynamic_host(
        dynamic_config,
        server,
        std::make_unique<FakeCredentialVerifier>(),
        game
    );
    const auto dynamic_port = dynamic_host.start();
    assert(dynamic_port > 0);
    assert(dynamic_port != config.bridge_port);
    dynamic_host.stop();

    const auto snapshot_test_root =
        std::filesystem::temp_directory_path()
        / (
            "PalEditorBridgeCoreTests-"
            + std::to_string(
                std::chrono::steady_clock::now()
                    .time_since_epoch()
                    .count()
            )
        );
    const auto world_guid = std::string(
        "00112233445566778899aabbccddeeff"
    );
    const auto save_directory =
        snapshot_test_root / "saves" / world_guid;
    std::filesystem::create_directories(
        save_directory / "Players"
    );
    {
        std::ofstream(save_directory / "Level.sav", std::ios::binary)
            << "level-fixture";
        std::ofstream(
            save_directory / "Players" / "player-fixture.sav",
            std::ios::binary
        ) << "player-fixture";
    }
    auto snapshot_config = config;
    snapshot_config.bridge_port = 0;
    snapshot_config.save_games_root =
        snapshot_test_root / "saves";
    snapshot_config.snapshot_cache_root =
        snapshot_test_root / "cache";
    pal_editor_bridge::ServerDescriptor snapshot_server = server;
    snapshot_server.world_guid = world_guid;
    pal_editor_bridge::BridgeHost snapshot_host(
        snapshot_config,
        snapshot_server,
        std::make_unique<FakeCredentialVerifier>(),
        game
    );
    const auto snapshot_port = snapshot_host.start();
    httplib::Client snapshot_client("127.0.0.1", snapshot_port);
    const auto snapshot_login = snapshot_client.Post(
        "/v1/auth/login",
        R"({"protocolVersion":1,"username":"admin","adminPassword":"correct"})",
        "application/json"
    );
    assert(snapshot_login && snapshot_login->status == 200);
    const auto snapshot_login_body =
        nlohmann::json::parse(snapshot_login->body);
    assert(snapshot_login_body["capabilities"].size() == 18);
    const httplib::Headers snapshot_authorization{
        {
            "Authorization",
            "Bearer "
                + snapshot_login_body["token"].get<std::string>(),
        },
    };
    const auto invalid_scope = snapshot_client.Post(
        "/v1/snapshots",
        snapshot_authorization,
        R"({"scope":"world"})",
        "application/json"
    );
    assert(invalid_scope && invalid_scope->status == 400);
    const auto create_snapshot = snapshot_client.Post(
        "/v1/snapshots",
        snapshot_authorization,
        R"({"scope":"players"})",
        "application/json"
    );
    assert(create_snapshot && create_snapshot->status == 202);
    auto snapshot_body =
        nlohmann::json::parse(create_snapshot->body);
    const auto snapshot_id = snapshot_body["id"].get<std::string>();
    for (
        auto attempt = 0;
        attempt < 200 && snapshot_body["state"] == "capturing";
        ++attempt
    )
    {
        std::this_thread::sleep_for(10ms);
        const auto snapshot_status = snapshot_client.Get(
            "/v1/snapshots/" + snapshot_id,
            snapshot_authorization
        );
        assert(snapshot_status && snapshot_status->status == 200);
        snapshot_body =
            nlohmann::json::parse(snapshot_status->body);
    }
    assert(snapshot_body["state"] == "ready");
    assert(snapshot_body["files"].size() == 2);
    for (const auto& file : snapshot_body["files"])
    {
        const auto download = snapshot_client.Get(
            "/v1/snapshots/" + snapshot_id + "/files/"
                + file["fileId"].get<std::string>(),
            snapshot_authorization
        );
        assert(download && download->status == 200);
        assert(download->body.size() == file["size"]);
        assert(
            download->get_header_value("X-Content-SHA256")
            == file["sha256"]
        );
    }
    const auto unknown_file = snapshot_client.Get(
        "/v1/snapshots/" + snapshot_id
            + "/files/00000000000000000000000000000000",
        snapshot_authorization
    );
    assert(unknown_file && unknown_file->status == 404);
    snapshot_host.stop();
    std::filesystem::remove_all(snapshot_test_root);

    auto save_state =
        std::make_shared<FakeCredentialVerifier::SaveState>();
    auto persistence_config = config;
    persistence_config.bridge_port = 0;
    persistence_config.save_debounce = 25ms;
    persistence_config.save_max_delay = 100ms;
    pal_editor_bridge::BridgeHost persistence_host(
        persistence_config,
        server,
        std::make_unique<FakeCredentialVerifier>(save_state),
        game
    );
    const auto persistence_port = persistence_host.start();
    httplib::Client persistence_client(
        "127.0.0.1",
        persistence_port
    );
    const auto persistence_login = persistence_client.Post(
        "/v1/auth/login",
        R"({"protocolVersion":1,"username":"admin","adminPassword":"correct"})",
        "application/json"
    );
    assert(persistence_login && persistence_login->status == 200);
    const httplib::Headers persistence_authorization{
        {
            "Authorization",
            "Bearer "
                + nlohmann::json::parse(persistence_login->body)
                      ["token"].get<std::string>(),
        },
    };
    for (auto revision = 0; revision < 2; ++revision)
    {
        const auto persistence_command = nlohmann::json{
            {"protocolVersion", 1},
            {
                "commandId",
                "persistence-" + std::to_string(revision)
            },
            {"operation", "inventory.grant"},
            {"expectedRevision", revision},
            {"target", {{"playerUid", "player-1"}}},
            {"payload", {{"itemId", "TestItem"}, {"quantity", 1}}},
        };
        const auto response = persistence_client.Post(
            "/v1/commands",
            persistence_authorization,
            persistence_command.dump(),
            "application/json"
        );
        assert(response && response->status == 200);
        assert(
            nlohmann::json::parse(response->body)
                ["persistence"]["state"] == "dirty"
        );
    }
    nlohmann::json persisted_status;
    for (auto attempt = 0; attempt < 100; ++attempt)
    {
        const auto response = persistence_client.Get(
            "/v1/status",
            persistence_authorization
        );
        assert(response && response->status == 200);
        persisted_status = nlohmann::json::parse(response->body);
        if (persisted_status["persistence"]["state"] == "clean")
        {
            break;
        }
        std::this_thread::sleep_for(5ms);
    }
    assert(persisted_status["persistence"]["state"] == "clean");
    assert(persisted_status["persistence"]["savedRevision"] == 2);
    assert(save_state->calls.load() == 1);

    save_state->fail.store(true);
    const auto failing_command = nlohmann::json{
        {"protocolVersion", 1},
        {"commandId", "persistence-failure"},
        {"operation", "inventory.grant"},
        {"expectedRevision", 2},
        {"target", {{"playerUid", "player-1"}}},
        {"payload", {{"itemId", "TestItem"}, {"quantity", 1}}},
    };
    const auto failing_response = persistence_client.Post(
        "/v1/commands",
        persistence_authorization,
        failing_command.dump(),
        "application/json"
    );
    assert(failing_response && failing_response->status == 200);
    for (auto attempt = 0; attempt < 100; ++attempt)
    {
        const auto response = persistence_client.Get(
            "/v1/status",
            persistence_authorization
        );
        assert(response && response->status == 200);
        persisted_status = nlohmann::json::parse(response->body);
        if (persisted_status["persistence"]["state"] == "failed")
        {
            break;
        }
        std::this_thread::sleep_for(5ms);
    }
    assert(persisted_status["persistence"]["state"] == "failed");
    assert(
        persisted_status["persistence"]["dirtyRevision"] == 3
    );
    assert(
        persisted_status["persistence"]["savedRevision"] == 2
    );
    persistence_host.stop();

    std::cout << "PalEditorBridgeCoreTests passed\n";
    return 0;
}
