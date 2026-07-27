#include <pal_editor_bridge/bridge_core.hpp>

#include <cassert>
#include <chrono>
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
        bool verify_credentials(
            const std::string& username,
            const std::string& admin_password
        ) override
        {
            return username == "admin" && admin_password == "correct";
        }

        std::vector<std::string> capabilities() const override
        {
            return {"world.save"};
        }

        nlohmann::json players(
            const pal_editor_bridge::AdminCredentials&
        ) override
        {
            throw std::runtime_error(
                "The player route must not use the credential verifier."
            );
        }

        nlohmann::json execute(
            const pal_editor_bridge::AdminCredentials& credentials,
            const nlohmann::json& command
        ) override
        {
            assert(credentials.admin_password == "correct");
            assert(command["operation"] == "world.save");
            return {
                {"state", "completed"},
                {"result", {{"saved", true}}},
            };
        }
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

        nlohmann::json execute(const nlohmann::json&) override
        {
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
    assert(login_body["capabilities"].size() == 9);
    const auto session_token = login_body["token"].get<std::string>();
    const httplib::Headers authorization{
        {"Authorization", "Bearer " + session_token},
    };

    const auto status = client.Get("/v1/status", authorization);
    assert(status && status->status == 200);
    assert(nlohmann::json::parse(status->body)["ready"] == true);
    assert(
        nlohmann::json::parse(status->body)["capabilities"].size()
        == 9
    );

    const auto players = client.Get("/v1/players", authorization);
    assert(players && players->status == 200);
    assert(
        nlohmann::json::parse(players->body)["players"][0]["name"]
        == "Protocol Player"
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
        nlohmann::json::parse(save_response->body)["result"]["saved"]
        == true
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

    std::cout << "PalEditorBridgeCoreTests passed\n";
    return 0;
}
