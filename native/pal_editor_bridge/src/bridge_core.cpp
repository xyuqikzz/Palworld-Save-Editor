#include <pal_editor_bridge/bridge_core.hpp>

#include <algorithm>
#include <array>
#include <deque>
#include <format>
#include <random>
#include <ranges>
#include <stdexcept>
#include <unordered_map>

#include <httplib.h>

#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")
#endif

namespace pal_editor_bridge
{
    namespace
    {
        using json = nlohmann::json;

        void json_response(httplib::Response& response, int status, const json& body)
        {
            response.status = status;
            response.set_content(body.dump(), "application/json");
        }

        void error_response(
            httplib::Response& response,
            int status,
            std::string code,
            std::string message,
            json details = json::object()
        )
        {
            json_response(
                response,
                status,
                {
                    {"message", std::move(message)},
                    {
                        "error",
                        {
                            {"code", std::move(code)},
                            {"details", std::move(details)},
                        },
                    },
                }
            );
        }

        std::optional<json> parse_object(
            const httplib::Request& request,
            httplib::Response& response
        )
        {
            try
            {
                auto value = json::parse(request.body);
                if (!value.is_object())
                {
                    error_response(
                        response,
                        400,
                        "INVALID_REQUEST",
                        "A JSON object is required."
                    );
                    return std::nullopt;
                }
                return value;
            }
            catch (const json::parse_error&)
            {
                error_response(
                    response,
                    400,
                    "INVALID_JSON",
                    "The request body is not valid JSON."
                );
                return std::nullopt;
            }
        }

        std::optional<std::string> bearer_token(const httplib::Request& request)
        {
            const auto authorization = request.get_header_value("Authorization");
            constexpr std::string_view prefix{"Bearer "};
            if (!authorization.starts_with(prefix))
            {
                return std::nullopt;
            }
            auto token = authorization.substr(prefix.size());
            if (token.empty())
            {
                return std::nullopt;
            }
            return token;
        }

        template <typename Port>
        bool has_capability(
            const Port& port,
            const std::string& operation
        )
        {
            const auto capabilities = port.capabilities();
            return std::ranges::find(capabilities, operation) != capabilities.end();
        }

        std::optional<std::size_t> parse_bounded_size(
            const std::string& value,
            std::size_t maximum
        )
        {
            if (
                value.empty()
                || !std::ranges::all_of(
                    value,
                    [](char character) {
                        return character >= '0' && character <= '9';
                    }
                )
            )
            {
                return std::nullopt;
            }
            try
            {
                const auto parsed = std::stoull(value);
                if (parsed > maximum)
                {
                    return std::nullopt;
                }
                return static_cast<std::size_t>(parsed);
            }
            catch (...)
            {
                return std::nullopt;
            }
        }

        std::vector<std::string> combined_capabilities(
            const CredentialVerifier& administrator,
            const GameCommandPort& game
        )
        {
            auto capabilities = administrator.capabilities();
            for (const auto& capability : game.capabilities())
            {
                if (
                    std::ranges::find(capabilities, capability)
                    == capabilities.end()
                )
                {
                    capabilities.push_back(capability);
                }
            }
            std::ranges::sort(capabilities);
            return capabilities;
        }

        bool constant_time_equal(
            std::string_view left,
            std::string_view right
        )
        {
            auto difference = left.size() ^ right.size();
            const auto length = std::max(left.size(), right.size());
            for (std::size_t index = 0; index < length; ++index)
            {
                const auto left_value = index < left.size()
                    ? static_cast<unsigned char>(left[index])
                    : 0;
                const auto right_value = index < right.size()
                    ? static_cast<unsigned char>(right[index])
                    : 0;
                difference |= left_value ^ right_value;
            }
            return difference == 0;
        }
    } // namespace

    std::optional<ServerDescriptor> CredentialVerifier::server_descriptor(
        const AdminCredentials&
    )
    {
        return std::nullopt;
    }

    std::vector<std::string> CredentialVerifier::capabilities() const
    {
        return {};
    }

    nlohmann::json CredentialVerifier::players(const AdminCredentials&)
    {
        throw std::runtime_error(
            "The administrator API does not provide a player list."
        );
    }

    nlohmann::json CredentialVerifier::execute(
        const AdminCredentials&,
        const nlohmann::json&
    )
    {
        return {
            {"state", "failed"},
            {"message", "The administrator command is not supported."},
        };
    }

    PalworldRestCredentialVerifier::PalworldRestCredentialVerifier(
        BridgeConfig config
    )
        : m_config(std::move(config))
    {
    }

    bool PalworldRestCredentialVerifier::verify_credentials(
        const std::string& username,
        const std::string& admin_password
    )
    {
        if (
            username.empty() || admin_password.empty()
            || username != m_config.rest_username
        )
        {
            return false;
        }
        httplib::Client client(m_config.rest_host, m_config.rest_port);
        client.set_connection_timeout(3, 0);
        client.set_read_timeout(5, 0);
        client.set_basic_auth(username, admin_password);
        const auto response = client.Get("/v1/api/info");
        return response && response->status == 200;
    }

    std::optional<ServerDescriptor>
    PalworldRestCredentialVerifier::server_descriptor(
        const AdminCredentials& credentials
    )
    {
        httplib::Client client(m_config.rest_host, m_config.rest_port);
        client.set_connection_timeout(3, 0);
        client.set_read_timeout(5, 0);
        client.set_basic_auth(
            credentials.username,
            credentials.admin_password
        );
        const auto response = client.Get("/v1/api/info");
        if (!response || response->status != 200)
        {
            return std::nullopt;
        }
        try
        {
            const auto body = json::parse(response->body);
            if (!body.is_object())
            {
                return std::nullopt;
            }
            ServerDescriptor descriptor;
            descriptor.name = body.value("servername", "");
            descriptor.game_version = body.value("version", "");
            descriptor.world_guid = body.value("worldguid", "");
            descriptor.platform = "Win64";
            return descriptor;
        }
        catch (const json::parse_error&)
        {
            return std::nullopt;
        }
    }

    std::vector<std::string>
    PalworldRestCredentialVerifier::capabilities() const
    {
        return {"world.save"};
    }

    nlohmann::json PalworldRestCredentialVerifier::players(
        const AdminCredentials& credentials
    )
    {
        httplib::Client client(m_config.rest_host, m_config.rest_port);
        client.set_connection_timeout(3, 0);
        client.set_read_timeout(5, 0);
        client.set_basic_auth(
            credentials.username,
            credentials.admin_password
        );
        const auto response = client.Get("/v1/api/players");
        if (!response || response->status != 200)
        {
            throw std::runtime_error(
                "The Palworld REST API player request failed."
            );
        }
        try
        {
            const auto body = json::parse(response->body);
            if (
                !body.is_object() || !body.contains("players")
                || !body["players"].is_array()
            )
            {
                throw std::runtime_error(
                    "The Palworld REST API returned an invalid player list."
                );
            }
            return body["players"];
        }
        catch (const json::parse_error&)
        {
            throw std::runtime_error(
                "The Palworld REST API returned an invalid player list."
            );
        }
    }

    nlohmann::json PalworldRestCredentialVerifier::execute(
        const AdminCredentials& credentials,
        const nlohmann::json& command
    )
    {
        if (command.value("operation", "") != "world.save")
        {
            return {
                {"state", "failed"},
                {"message", "The administrator command is not supported."},
            };
        }
        httplib::Client client(m_config.rest_host, m_config.rest_port);
        client.set_connection_timeout(3, 0);
        client.set_read_timeout(10, 0);
        client.set_basic_auth(
            credentials.username,
            credentials.admin_password
        );
        const auto response = client.Post(
            "/v1/api/save",
            "",
            "application/json"
        );
        if (!response || response->status != 200)
        {
            return {
                {"state", "failed"},
                {"message", "The Palworld REST API world save request failed."},
            };
        }
        return {
            {"state", "completed"},
            {"result", {{"saved", true}}},
        };
    }

    LocalCredentialVerifier::LocalCredentialVerifier(
        std::string bootstrap_secret,
        ServerDescriptor descriptor
    )
        : m_bootstrap_secret(std::move(bootstrap_secret)),
          m_descriptor(std::move(descriptor))
    {
        if (m_bootstrap_secret.size() < 32)
        {
            throw std::invalid_argument(
                "The local bridge bootstrap secret must contain at least 32 characters."
            );
        }
    }

    bool LocalCredentialVerifier::verify_credentials(
        const std::string& username,
        const std::string& admin_password
    )
    {
        return constant_time_equal(username, "local")
            && constant_time_equal(
                admin_password,
                m_bootstrap_secret
            );
    }

    std::optional<ServerDescriptor>
    LocalCredentialVerifier::server_descriptor(
        const AdminCredentials&
    )
    {
        return m_descriptor;
    }

    SessionRegistry::SessionRegistry(std::chrono::seconds token_ttl)
        : m_token_ttl(token_ttl)
    {
        if (m_token_ttl <= std::chrono::seconds::zero())
        {
            throw std::invalid_argument("token_ttl must be positive");
        }
    }

    std::string SessionRegistry::issue(
        const std::string& username,
        const std::string& admin_password
    )
    {
        const auto token = secure_token();
        const auto expires_at = clock::now() + m_token_ttl;
        std::scoped_lock lock(m_mutex);
        remove_expired(clock::now());
        m_tokens.insert_or_assign(
            token,
            SessionRecord{
                expires_at,
                AdminCredentials{username, admin_password},
            }
        );
        return token;
    }

    bool SessionRegistry::valid(const std::string& token)
    {
        if (token.empty())
        {
            return false;
        }
        const auto now = clock::now();
        std::scoped_lock lock(m_mutex);
        remove_expired(now);
        const auto match = m_tokens.find(token);
        return (
            match != m_tokens.end()
            && match->second.expires_at > now
        );
    }

    std::optional<AdminCredentials> SessionRegistry::credentials(
        const std::string& token
    )
    {
        if (token.empty())
        {
            return std::nullopt;
        }
        const auto now = clock::now();
        std::scoped_lock lock(m_mutex);
        remove_expired(now);
        const auto match = m_tokens.find(token);
        if (
            match == m_tokens.end()
            || match->second.expires_at <= now
        )
        {
            return std::nullopt;
        }
        return match->second.credentials;
    }

    void SessionRegistry::revoke(const std::string& token)
    {
        std::scoped_lock lock(m_mutex);
        m_tokens.erase(token);
    }

    void SessionRegistry::clear()
    {
        std::scoped_lock lock(m_mutex);
        m_tokens.clear();
    }

    void SessionRegistry::remove_expired(clock::time_point now)
    {
        std::erase_if(
            m_tokens,
            [now](const auto& entry) {
                return entry.second.expires_at <= now;
            }
        );
    }

    std::string SessionRegistry::secure_token()
    {
        std::array<unsigned char, 32> bytes{};
#ifdef _WIN32
        const auto status = BCryptGenRandom(
            nullptr,
            bytes.data(),
            static_cast<ULONG>(bytes.size()),
            BCRYPT_USE_SYSTEM_PREFERRED_RNG
        );
        if (status < 0)
        {
            throw std::runtime_error("BCryptGenRandom failed");
        }
#else
        std::random_device random;
        std::ranges::generate(bytes, [&random]() {
            return static_cast<unsigned char>(random());
        });
#endif
        std::string token;
        token.reserve(bytes.size() * 2);
        for (const auto value : bytes)
        {
            token += std::format("{:02x}", value);
        }
        return token;
    }

    class BridgeHost::Impl
    {
      public:
        Impl(
            BridgeConfig config,
            ServerDescriptor server,
            std::unique_ptr<CredentialVerifier> credential_verifier,
            GameCommandPort& game
        )
            : m_config(std::move(config)),
              m_server(std::move(server)),
              m_credential_verifier(std::move(credential_verifier)),
              m_game(game),
              m_sessions(m_config.token_ttl)
        {
            if (!m_credential_verifier)
            {
                throw std::invalid_argument(
                    "credential_verifier must not be null"
                );
            }
            m_server_impl.set_payload_max_length(64 * 1024);
            configure_routes();
        }

        ~Impl()
        {
            stop();
        }

        std::uint16_t start()
        {
            if (m_thread.joinable())
            {
                return m_bound_port;
            }
            if (m_config.bind_host != "127.0.0.1" && m_config.bind_host != "::1")
            {
                throw std::runtime_error(
                    "The non-TLS bridge build may only bind to a loopback address"
                );
            }
            const auto bound = m_config.bridge_port == 0
                ? m_server_impl.bind_to_any_port(m_config.bind_host)
                : (
                    m_server_impl.bind_to_port(
                        m_config.bind_host,
                        m_config.bridge_port
                    )
                        ? static_cast<int>(m_config.bridge_port)
                        : -1
                );
            if (bound <= 0 || bound > 65535)
            {
                throw std::runtime_error(
                    "The bridge could not bind its loopback port."
                );
            }
            m_bound_port = static_cast<std::uint16_t>(bound);
            m_thread = std::thread([this]() {
                m_server_impl.listen_after_bind();
            });
            m_server_impl.wait_until_ready();
            return m_bound_port;
        }

        void stop()
        {
            m_server_impl.stop();
            if (m_thread.joinable())
            {
                m_thread.join();
            }
            m_sessions.clear();
        }

        bool running() const
        {
            return m_server_impl.is_running();
        }

      private:
        bool authorize(
            const httplib::Request& request,
            httplib::Response& response
        )
        {
            const auto token = bearer_token(request);
            if (!token || !m_sessions.valid(*token))
            {
                error_response(
                    response,
                    401,
                    "REMOTE_AUTH_REQUIRED",
                    "A valid bridge session token is required."
                );
                return false;
            }
            return true;
        }

        void configure_routes()
        {
            m_server_impl.Get(
                "/v1/health",
                [this](const httplib::Request&, httplib::Response& response) {
                    const auto status = m_game.status();
                    json_response(
                        response,
                        200,
                        {
                            {"protocolVersion", protocol_version},
                            {"bridgeVersion", bridge_version},
                            {"gameReady", m_game.ready()},
                            {
                                "instanceMode",
                                status.value("instanceMode", "unknown")
                            },
                            {
                                "authoritative",
                                status.value("authoritative", false)
                            },
                        }
                    );
                }
            );

            m_server_impl.Post(
                "/v1/auth/login",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    const auto body = parse_object(request, response);
                    if (!body)
                    {
                        return;
                    }
                    if (
                        !body->contains("protocolVersion")
                        || !(*body)["protocolVersion"].is_number_integer()
                        || (*body)["protocolVersion"].get<std::int32_t>()
                            != protocol_version
                        || !body->contains("username")
                        || !(*body)["username"].is_string()
                        || !body->contains("adminPassword")
                        || !(*body)["adminPassword"].is_string()
                    )
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_LOGIN_INVALID",
                            "The bridge login request is incomplete."
                        );
                        return;
                    }
                    const auto username =
                        (*body)["username"].get<std::string>();
                    const auto password =
                        (*body)["adminPassword"].get<std::string>();
                    if (!m_credential_verifier->verify_credentials(username, password))
                    {
                        error_response(
                            response,
                            401,
                            "REMOTE_AUTH_FAILED",
                            "The Palworld administrator credentials were rejected."
                        );
                        return;
                    }
                    const AdminCredentials credentials{username, password};
                    const auto token = m_sessions.issue(username, password);
                    auto server = m_server;
                    if (const auto current =
                            m_credential_verifier->server_descriptor(credentials))
                    {
                        server = *current;
                    }
                    std::uint64_t revision = 0;
                    {
                        std::lock_guard command_lock(m_command_mutex);
                        revision = m_revision;
                    }
                    json_response(
                        response,
                        200,
                        {
                            {"protocolVersion", protocol_version},
                            {"bridgeVersion", bridge_version},
                            {"token", token},
                            {"revision", revision},
                            {
                                "server",
                                {
                                    {"name", server.name},
                                    {"gameVersion", server.game_version},
                                    {"worldGuid", server.world_guid},
                                    {"platform", server.platform},
                                    {"instanceKind", server.instance_kind},
                                },
                            },
                            {
                                "capabilities",
                                combined_capabilities(
                                    *m_credential_verifier,
                                    m_game
                                ),
                            },
                        }
                    );
                }
            );

            m_server_impl.Post(
                "/v1/auth/logout",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    const auto token = bearer_token(request);
                    if (token)
                    {
                        m_sessions.revoke(*token);
                    }
                    json_response(response, 200, {{"disconnected", true}});
                }
            );

            m_server_impl.Get(
                "/v1/status",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    auto result = m_game.status();
                    result["ready"] = m_game.ready();
                    result["protocolVersion"] = protocol_version;
                    result["bridgeVersion"] = bridge_version;
                    result["capabilities"] = combined_capabilities(
                        *m_credential_verifier,
                        m_game
                    );
                    json_response(response, 200, result);
                }
            );

            m_server_impl.Get(
                "/v1/players",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "player.list"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The player list capability is not available."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            {
                                {
                                    "players",
                                    m_game.players(),
                                },
                            }
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                "/v1/guilds",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "guild.list"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The guild list capability is not available."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            {{"guilds", m_game.guilds()}}
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                "/v1/map",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "map.read"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The live map capability is not available."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            m_game.map_snapshot()
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                "/v1/player-details",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "player.details"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The player detail capability is not available."
                        );
                        return;
                    }
                    if (!request.has_param("playerId"))
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_REQUIRED",
                            "A player ID is required."
                        );
                        return;
                    }
                    const auto player_id =
                        request.get_param_value("playerId");
                    if (player_id.empty() || player_id.size() > 128)
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_INVALID",
                            "The player ID is invalid."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            m_game.player_details(player_id)
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                "/v1/player-inventory",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "inventory.read"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The inventory read capability is not available."
                        );
                        return;
                    }
                    if (!request.has_param("playerId"))
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_REQUIRED",
                            "A player ID is required."
                        );
                        return;
                    }
                    const auto player_id =
                        request.get_param_value("playerId");
                    if (player_id.empty() || player_id.size() > 128)
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_INVALID",
                            "The player ID is invalid."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            m_game.inventory(player_id)
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                "/v1/player-pals",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!has_capability(m_game, "pal.list"))
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The Pal list capability is not available."
                        );
                        return;
                    }
                    if (!request.has_param("playerId"))
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_REQUIRED",
                            "A player ID is required."
                        );
                        return;
                    }
                    const auto player_id =
                        request.get_param_value("playerId");
                    if (player_id.empty() || player_id.size() > 128)
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PLAYER_ID_INVALID",
                            "The player ID is invalid."
                        );
                        return;
                    }
                    const auto collection = request.has_param("collection")
                        ? request.get_param_value("collection")
                        : "palbox";
                    if (collection != "party" && collection != "palbox")
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PAL_COLLECTION_INVALID",
                            "The Pal collection must be party or palbox."
                        );
                        return;
                    }
                    const auto page = parse_bounded_size(
                        request.has_param("page")
                            ? request.get_param_value("page")
                            : "0",
                        100000
                    );
                    const auto page_size = parse_bounded_size(
                        request.has_param("pageSize")
                            ? request.get_param_value("pageSize")
                            : "12",
                        30
                    );
                    if (!page || !page_size || *page_size == 0)
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_PAL_PAGE_INVALID",
                            "The Palbox page parameters are invalid."
                        );
                        return;
                    }
                    try
                    {
                        json_response(
                            response,
                            200,
                            m_game.pals(
                                player_id,
                                collection,
                                *page,
                                *page_size
                            )
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            502,
                            "PALWORLD_RUNTIME_REQUEST_FAILED",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Post(
                "/v1/commands",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    const auto body = parse_object(request, response);
                    if (!body)
                    {
                        return;
                    }
                    if (
                        !body->contains("protocolVersion")
                        || !(*body)["protocolVersion"].is_number_integer()
                        || (*body)["protocolVersion"].get<std::int32_t>()
                            != protocol_version
                        || !body->contains("operation")
                        || !(*body)["operation"].is_string()
                        || !body->contains("commandId")
                        || !(*body)["commandId"].is_string()
                        || !body->contains("expectedRevision")
                        || !(*body)["expectedRevision"].is_number_unsigned()
                        || !body->contains("target")
                        || !(*body)["target"].is_object()
                        || !body->contains("payload")
                        || !(*body)["payload"].is_object()
                    )
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_COMMAND_INVALID",
                            "The bridge command is incomplete."
                        );
                        return;
                    }
                    const auto operation =
                        (*body)["operation"].get<std::string>();
                    const auto command_id =
                        (*body)["commandId"].get<std::string>();
                    if (
                        operation.empty() || operation.size() > 64
                        || command_id.empty() || command_id.size() > 128
                    )
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_COMMAND_INVALID",
                            "The bridge command is incomplete."
                        );
                        return;
                    }
                    if (
                        !has_capability(m_game, operation)
                        && !has_capability(
                            *m_credential_verifier,
                            operation
                        )
                    )
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "The requested operation is not available.",
                            {{"operation", operation}}
                        );
                        return;
                    }
                    std::lock_guard command_lock(m_command_mutex);
                    const auto cached = m_completed_commands.find(command_id);
                    if (cached != m_completed_commands.end())
                    {
                        if (cached->second.request != *body)
                        {
                            error_response(
                                response,
                                409,
                                "REMOTE_COMMAND_ID_REUSED",
                                "The command ID was already used for another operation."
                            );
                            return;
                        }
                        json_response(response, 200, cached->second.response);
                        return;
                    }
                    const auto expected_revision =
                        (*body)["expectedRevision"].get<std::uint64_t>();
                    if (expected_revision != m_revision)
                    {
                        error_response(
                            response,
                            409,
                            "STALE_REVISION",
                            "The remote session revision is stale.",
                            {
                                {"expected", expected_revision},
                                {"actual", m_revision},
                            }
                        );
                        return;
                    }

                    json result;
                    if (
                        has_capability(
                            *m_credential_verifier,
                            operation
                        )
                    )
                    {
                        const auto token = bearer_token(request);
                        const auto credentials = token
                            ? m_sessions.credentials(*token)
                            : std::nullopt;
                        if (!credentials)
                        {
                            error_response(
                                response,
                                401,
                                "REMOTE_AUTH_REQUIRED",
                                "A valid bridge session token is required."
                            );
                            return;
                        }
                        result = m_credential_verifier->execute(
                            *credentials,
                            *body
                        );
                    }
                    else
                    {
                        result = m_game.execute(*body);
                    }
                    result["commandId"] = command_id;
                    if (result.value("state", "") == "completed")
                    {
                        ++m_revision;
                    }
                    result["revision"] = m_revision;
                    remember_command(command_id, *body, result);
                    json_response(response, 200, result);
                }
            );
        }

        void remember_command(
            const std::string& command_id,
            const json& request,
            const json& response
        )
        {
            constexpr std::size_t max_completed_commands = 1024;
            if (m_completed_commands.size() >= max_completed_commands)
            {
                m_completed_commands.erase(m_command_order.front());
                m_command_order.pop_front();
            }
            m_command_order.push_back(command_id);
            m_completed_commands.emplace(
                command_id,
                CachedCommand{request, response}
            );
        }

        struct CachedCommand
        {
            json request;
            json response;
        };

        BridgeConfig m_config;
        ServerDescriptor m_server;
        std::unique_ptr<CredentialVerifier> m_credential_verifier;
        GameCommandPort& m_game;
        SessionRegistry m_sessions;
        httplib::Server m_server_impl;
        std::thread m_thread;
        std::uint16_t m_bound_port{0};
        std::mutex m_command_mutex;
        std::uint64_t m_revision{0};
        std::deque<std::string> m_command_order;
        std::unordered_map<std::string, CachedCommand> m_completed_commands;
    };

    BridgeHost::BridgeHost(
        BridgeConfig config,
        ServerDescriptor server,
        std::unique_ptr<CredentialVerifier> credential_verifier,
        GameCommandPort& game
    )
        : m_impl(std::make_unique<Impl>(
              std::move(config),
              std::move(server),
              std::move(credential_verifier),
              game
          ))
    {
    }

    BridgeHost::~BridgeHost() = default;

    std::uint16_t BridgeHost::start()
    {
        return m_impl->start();
    }

    void BridgeHost::stop()
    {
        m_impl->stop();
    }

    bool BridgeHost::running() const
    {
        return m_impl->running();
    }
} // namespace pal_editor_bridge
