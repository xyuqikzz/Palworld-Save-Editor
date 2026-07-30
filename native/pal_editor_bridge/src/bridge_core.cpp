#include <pal_editor_bridge/bridge_core.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <format>
#include <fstream>
#include <iomanip>
#include <random>
#include <ranges>
#include <sstream>
#include <stdexcept>
#include <unordered_set>
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

        std::string string_field(
            const json& value,
            std::initializer_list<const char*> names
        )
        {
            if (!value.is_object())
            {
                return {};
            }
            for (const auto* name : names)
            {
                const auto match = value.find(name);
                if (match != value.end() && match->is_string())
                {
                    return match->get<std::string>();
                }
            }
            return {};
        }

        std::string normalize_player_id(std::string value)
        {
            value.erase(
                std::remove_if(
                    value.begin(),
                    value.end(),
                    [](unsigned char character) {
                        return character == '-'
                            || character == '{'
                            || character == '}'
                            || std::isspace(character);
                    }
                ),
                value.end()
            );
            std::ranges::transform(
                value,
                value.begin(),
                [](unsigned char character) {
                    return static_cast<char>(std::tolower(character));
                }
            );
            return value;
        }

        void merge_administrator_player_metadata(
            json& runtime_players,
            const json& administrator_players
        )
        {
            if (
                !runtime_players.is_array()
                || !administrator_players.is_array()
            )
            {
                return;
            }
            std::unordered_map<std::string, const json*> administrator_by_id;
            for (const auto& player : administrator_players)
            {
                const auto player_id = normalize_player_id(
                    string_field(
                        player,
                        {"playerId", "playerid", "player_uid"}
                    )
                );
                if (!player_id.empty())
                {
                    administrator_by_id.emplace(player_id, &player);
                }
            }
            for (auto& player : runtime_players)
            {
                const auto player_id = normalize_player_id(
                    string_field(
                        player,
                        {"playerId", "player_uid", "playerUid"}
                    )
                );
                const auto match = administrator_by_id.find(player_id);
                if (match == administrator_by_id.end())
                {
                    continue;
                }
                const auto& administrator = *match->second;
                const auto user_id = string_field(
                    administrator,
                    {"userId", "userid", "user_id"}
                );
                if (!user_id.empty())
                {
                    player["userId"] = user_id;
                    player["user_id"] = user_id;
                }
                const auto account_name = string_field(
                    administrator,
                    {"accountName", "accountname", "account_name"}
                );
                if (!account_name.empty())
                {
                    player["accountName"] = account_name;
                }
                if (
                    const auto ping = administrator.find("ping");
                    ping != administrator.end() && ping->is_number()
                )
                {
                    player["ping"] = *ping;
                }
                if (
                    const auto buildings =
                        administrator.find("building_count");
                    buildings != administrator.end()
                    && buildings->is_number_integer()
                )
                {
                    player["buildingCount"] = *buildings;
                }
                player["administratorMetadata"] = "available";
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

        std::string utc_timestamp(
            std::chrono::system_clock::time_point value
        )
        {
            const auto timestamp =
                std::chrono::system_clock::to_time_t(value);
            std::tm utc{};
#ifdef _WIN32
            gmtime_s(&utc, &timestamp);
#else
            gmtime_r(&timestamp, &utc);
#endif
            std::ostringstream stream;
            stream << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
            return stream.str();
        }

        std::string random_identifier()
        {
            std::array<unsigned char, 16> bytes{};
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
            std::string value;
            value.reserve(bytes.size() * 2);
            for (const auto byte : bytes)
            {
                value += std::format("{:02x}", byte);
            }
            return value;
        }

        std::string sha256_file(const std::filesystem::path& path)
        {
#ifdef _WIN32
            BCRYPT_ALG_HANDLE algorithm = nullptr;
            BCRYPT_HASH_HANDLE hash = nullptr;
            DWORD object_size = 0;
            DWORD hash_size = 0;
            DWORD result_size = 0;
            std::vector<unsigned char> object;
            std::vector<unsigned char> digest;
            const auto close = [&]() {
                if (hash)
                {
                    BCryptDestroyHash(hash);
                    hash = nullptr;
                }
                if (algorithm)
                {
                    BCryptCloseAlgorithmProvider(algorithm, 0);
                    algorithm = nullptr;
                }
            };
            try
            {
                if (
                    BCryptOpenAlgorithmProvider(
                        &algorithm,
                        BCRYPT_SHA256_ALGORITHM,
                        nullptr,
                        0
                    ) < 0
                    || BCryptGetProperty(
                        algorithm,
                        BCRYPT_OBJECT_LENGTH,
                        reinterpret_cast<PUCHAR>(&object_size),
                        sizeof(object_size),
                        &result_size,
                        0
                    ) < 0
                    || BCryptGetProperty(
                        algorithm,
                        BCRYPT_HASH_LENGTH,
                        reinterpret_cast<PUCHAR>(&hash_size),
                        sizeof(hash_size),
                        &result_size,
                        0
                    ) < 0
                )
                {
                    throw std::runtime_error(
                        "The snapshot SHA-256 provider is unavailable."
                    );
                }
                object.resize(object_size);
                digest.resize(hash_size);
                if (
                    BCryptCreateHash(
                        algorithm,
                        &hash,
                        object.data(),
                        static_cast<ULONG>(object.size()),
                        nullptr,
                        0,
                        0
                    ) < 0
                )
                {
                    throw std::runtime_error(
                        "The snapshot SHA-256 state could not be created."
                    );
                }
                std::ifstream input(path, std::ios::binary);
                if (!input)
                {
                    throw std::runtime_error(
                        "A snapshot source file could not be opened."
                    );
                }
                std::vector<char> buffer(1024 * 1024);
                while (input)
                {
                    input.read(buffer.data(), buffer.size());
                    const auto count = input.gcount();
                    if (
                        count > 0
                        && BCryptHashData(
                            hash,
                            reinterpret_cast<PUCHAR>(buffer.data()),
                            static_cast<ULONG>(count),
                            0
                        ) < 0
                    )
                    {
                        throw std::runtime_error(
                            "A snapshot file could not be hashed."
                        );
                    }
                }
                if (
                    !input.eof()
                    || BCryptFinishHash(
                        hash,
                        digest.data(),
                        static_cast<ULONG>(digest.size()),
                        0
                    ) < 0
                )
                {
                    throw std::runtime_error(
                        "A snapshot file could not be hashed."
                    );
                }
                close();
                std::string value;
                value.reserve(digest.size() * 2);
                for (const auto byte : digest)
                {
                    value += std::format("{:02x}", byte);
                }
                return value;
            }
            catch (...)
            {
                close();
                throw;
            }
#else
            throw std::runtime_error(
                "Save snapshots are supported only on Windows."
            );
#endif
        }

        std::string normalized_world_guid(std::string value)
        {
            value.erase(
                std::remove_if(
                    value.begin(),
                    value.end(),
                    [](unsigned char character) {
                        return character == '-'
                            || character == '{'
                            || character == '}';
                    }
                ),
                value.end()
            );
            if (
                value.size() != 32
                || !std::ranges::all_of(
                    value,
                    [](unsigned char character) {
                        return std::isxdigit(character) != 0;
                    }
                )
            )
            {
                return {};
            }
            std::ranges::transform(
                value,
                value.begin(),
                [](unsigned char character) {
                    return static_cast<char>(std::tolower(character));
                }
            );
            return value;
        }

        class SnapshotBusyError final : public std::runtime_error
        {
          public:
            SnapshotBusyError()
                : std::runtime_error(
                      "Another save snapshot is already being captured."
                  )
            {
            }
        };

        class SnapshotManager final
        {
          public:
            SnapshotManager(
                std::filesystem::path cache_root,
                std::chrono::minutes ttl
            )
                : m_cache_root(
                      (
                          cache_root.empty()
                          ? std::filesystem::temp_directory_path()
                              / "PalEditorBridge"
                              / "snapshots"
                          : std::move(cache_root)
                      ) / random_identifier()
                  ),
                  m_ttl(ttl)
            {
            }

            ~SnapshotManager()
            {
                if (m_worker.joinable())
                {
                    m_worker.request_stop();
                    m_worker.join();
                }
                std::error_code error;
                std::filesystem::remove_all(m_cache_root, error);
            }

            json create(
                const std::filesystem::path& save_games_root,
                const std::string& world_guid
            )
            {
                const auto save_directory = resolve_save_directory(
                    save_games_root,
                    world_guid
                );
                std::lock_guard lock(m_mutex);
                cleanup_locked();
                if (m_capture_in_progress)
                {
                    throw SnapshotBusyError{};
                }
                while (m_order.size() >= 2)
                {
                    erase_locked(m_order.front());
                }
                auto record = std::make_shared<SnapshotRecord>();
                record->id = random_identifier();
                record->state = "capturing";
                record->created_at = std::chrono::system_clock::now();
                m_records.emplace(record->id, record);
                m_order.push_back(record->id);
                m_capture_in_progress = true;
                const auto record_id = record->id;
                m_worker = std::jthread(
                    [this, record_id, save_directory](
                        std::stop_token stop_token
                    ) {
                        capture(record_id, save_directory, stop_token);
                    }
                );
                return serialize(*record);
            }

            std::optional<json> get(const std::string& snapshot_id)
            {
                std::lock_guard lock(m_mutex);
                cleanup_locked();
                const auto match = m_records.find(snapshot_id);
                if (match == m_records.end())
                {
                    return std::nullopt;
                }
                return serialize(*match->second);
            }

            struct DownloadFile
            {
                std::filesystem::path path;
                std::uintmax_t size{0};
                std::string sha256;
                std::string name;
            };

            std::optional<DownloadFile> file(
                const std::string& snapshot_id,
                const std::string& file_id
            )
            {
                std::lock_guard lock(m_mutex);
                cleanup_locked();
                const auto match = m_records.find(snapshot_id);
                if (
                    match == m_records.end()
                    || match->second->state != "ready"
                )
                {
                    return std::nullopt;
                }
                const auto file_match = std::ranges::find_if(
                    match->second->files,
                    [&file_id](const SnapshotFile& file) {
                        return file.id == file_id;
                    }
                );
                if (file_match == match->second->files.end())
                {
                    return std::nullopt;
                }
                return DownloadFile{
                    file_match->path,
                    file_match->size,
                    file_match->sha256,
                    file_match->name,
                };
            }

          private:
            struct SnapshotFile
            {
                std::string id;
                std::string name;
                std::filesystem::path path;
                std::uintmax_t size{0};
                std::string sha256;
            };

            struct SnapshotRecord
            {
                std::string id;
                std::string state;
                std::chrono::system_clock::time_point created_at;
                std::optional<
                    std::chrono::system_clock::time_point
                > captured_at;
                std::vector<SnapshotFile> files;
                std::string error;
            };

            struct SourceMetadata
            {
                std::uintmax_t size;
                std::filesystem::file_time_type modified_at;
                std::string sha256;
            };

            static std::filesystem::path resolve_save_directory(
                const std::filesystem::path& save_games_root,
                const std::string& world_guid
            )
            {
                const auto normalized = normalized_world_guid(world_guid);
                if (normalized.empty())
                {
                    throw std::runtime_error(
                        "The server did not report a valid world GUID."
                    );
                }
                std::error_code error;
                const auto root = std::filesystem::weakly_canonical(
                    save_games_root,
                    error
                );
                if (
                    error || root.empty()
                    || !std::filesystem::is_directory(root)
                )
                {
                    throw std::runtime_error(
                        "The dedicated-server save root is unavailable."
                    );
                }
                std::vector<std::filesystem::path> matches;
                for (const auto& entry :
                     std::filesystem::directory_iterator(root))
                {
                    if (
                        entry.is_directory()
                        && normalized_world_guid(
                               entry.path().filename().string()
                           ) == normalized
                    )
                    {
                        matches.push_back(
                            std::filesystem::weakly_canonical(entry.path())
                        );
                    }
                }
                if (matches.size() != 1)
                {
                    throw std::runtime_error(
                        matches.empty()
                            ? "The active world save directory was not found."
                            : "The active world save directory is ambiguous."
                    );
                }
                const auto relative = matches.front().lexically_relative(root);
                if (
                    relative.empty() || relative.is_absolute()
                    || *relative.begin() == ".."
                )
                {
                    throw std::runtime_error(
                        "The active world save directory escaped the configured root."
                    );
                }
                return matches.front();
            }

            static SourceMetadata inspect_source(
                const std::filesystem::path& path
            )
            {
                return {
                    std::filesystem::file_size(path),
                    std::filesystem::last_write_time(path),
                    sha256_file(path),
                };
            }

            static SnapshotFile copy_stable_file(
                const std::filesystem::path& source,
                const std::filesystem::path& destination,
                std::string name
            )
            {
                std::filesystem::create_directories(
                    destination.parent_path()
                );
                for (auto attempt = 0; attempt < 3; ++attempt)
                {
                    const auto before = inspect_source(source);
                    std::filesystem::copy_file(
                        source,
                        destination,
                        std::filesystem::copy_options::overwrite_existing
                    );
                    const auto after = inspect_source(source);
                    const auto copied_hash = sha256_file(destination);
                    if (
                        before.size == after.size
                        && before.modified_at == after.modified_at
                        && before.sha256 == after.sha256
                        && copied_hash == after.sha256
                        && std::filesystem::file_size(destination)
                            == after.size
                    )
                    {
                        return {
                            random_identifier(),
                            std::move(name),
                            destination,
                            after.size,
                            after.sha256,
                        };
                    }
                }
                throw std::runtime_error(
                    "The save changed while the snapshot was captured."
                );
            }

            void capture(
                const std::string& record_id,
                const std::filesystem::path& save_directory,
                std::stop_token stop_token
            )
            {
                const auto snapshot_directory =
                    m_cache_root / record_id;
                try
                {
                    if (stop_token.stop_requested())
                    {
                        throw std::runtime_error(
                            "The snapshot capture was stopped."
                        );
                    }
                    const auto level = save_directory / "Level.sav";
                    if (!std::filesystem::is_regular_file(level))
                    {
                        throw std::runtime_error(
                            "The active Level.sav file was not found."
                        );
                    }
                    std::vector<
                        std::pair<std::filesystem::path, std::string>
                    > sources{{level, "Level.sav"}};
                    const auto players_directory =
                        save_directory / "Players";
                    if (
                        std::filesystem::is_directory(players_directory)
                    )
                    {
                        for (const auto& entry :
                             std::filesystem::directory_iterator(
                                 players_directory
                             ))
                        {
                            if (
                                entry.is_regular_file()
                                && entry.path().extension() == ".sav"
                                && !normalized_world_guid(
                                        entry.path().stem().string()
                                    ).empty()
                            )
                            {
                                sources.emplace_back(
                                    entry.path(),
                                    "Players/"
                                        + entry.path().filename().string()
                                );
                                if (sources.size() > 10000)
                                {
                                    throw std::runtime_error(
                                        "The player snapshot contains too many files."
                                    );
                                }
                            }
                        }
                    }
                    std::ranges::sort(
                        sources,
                        {},
                        [](const auto& source) {
                            return source.second;
                        }
                    );
                    std::vector<SnapshotFile> files;
                    files.reserve(sources.size());
                    for (const auto& [source, name] : sources)
                    {
                        if (stop_token.stop_requested())
                        {
                            throw std::runtime_error(
                                "The snapshot capture was stopped."
                            );
                        }
                        files.push_back(
                            copy_stable_file(
                                source,
                                snapshot_directory
                                    / std::filesystem::path(name),
                                name
                            )
                        );
                    }
                    std::lock_guard lock(m_mutex);
                    const auto match = m_records.find(record_id);
                    if (match != m_records.end())
                    {
                        match->second->files = std::move(files);
                        match->second->captured_at =
                            std::chrono::system_clock::now();
                        match->second->state = "ready";
                    }
                    m_capture_in_progress = false;
                }
                catch (const std::exception& error)
                {
                    std::error_code remove_error;
                    std::filesystem::remove_all(
                        snapshot_directory,
                        remove_error
                    );
                    std::lock_guard lock(m_mutex);
                    const auto match = m_records.find(record_id);
                    if (match != m_records.end())
                    {
                        match->second->state = "failed";
                        match->second->error = error.what();
                    }
                    m_capture_in_progress = false;
                }
            }

            static json serialize(const SnapshotRecord& record)
            {
                json files = json::array();
                for (const auto& file : record.files)
                {
                    files.push_back(
                        {
                            {"fileId", file.id},
                            {"name", file.name},
                            {"size", file.size},
                            {"sha256", file.sha256},
                        }
                    );
                }
                json value{
                    {"id", record.id},
                    {"scope", "players"},
                    {"state", record.state},
                    {"createdAt", utc_timestamp(record.created_at)},
                    {"files", std::move(files)},
                };
                value["capturedAt"] = record.captured_at
                    ? json(utc_timestamp(*record.captured_at))
                    : json(nullptr);
                value["error"] = record.error.empty()
                    ? json(nullptr)
                    : json(record.error);
                return value;
            }

            void cleanup_locked()
            {
                const auto cutoff =
                    std::chrono::system_clock::now() - m_ttl;
                for (auto iterator = m_order.begin();
                     iterator != m_order.end();)
                {
                    const auto match = m_records.find(*iterator);
                    if (
                        match != m_records.end()
                        && match->second->state != "capturing"
                        && match->second->created_at < cutoff
                    )
                    {
                        const auto id = *iterator;
                        iterator = m_order.erase(iterator);
                        erase_record_locked(id);
                    }
                    else
                    {
                        ++iterator;
                    }
                }
            }

            void erase_locked(const std::string& id)
            {
                std::erase(m_order, id);
                erase_record_locked(id);
            }

            void erase_record_locked(const std::string& id)
            {
                m_records.erase(id);
                std::error_code error;
                std::filesystem::remove_all(m_cache_root / id, error);
            }

            std::filesystem::path m_cache_root;
            std::chrono::minutes m_ttl;
            std::mutex m_mutex;
            std::unordered_map<
                std::string,
                std::shared_ptr<SnapshotRecord>
            > m_records;
            std::deque<std::string> m_order;
            bool m_capture_in_progress{false};
            std::jthread m_worker;
        };

        bool operation_requires_persistence(std::string_view operation)
        {
            static const std::unordered_set<std::string> operations{
                "inventory.grant",
                "inventory.item.count.update",
                "inventory.item.put",
                "inventory.item.dynamic.update",
                "pal.grant",
                "pal.identity.update",
                "pal.progression.update",
                "pal.skills.update",
                "pal.enhancement.update",
                "player.attributes.update",
                "player.experience.add",
                "player.fast_travel.update",
                "player.identity.update",
                "player.missions.update",
                "player.progression.update",
                "player.technology.update",
            };
            return operations.contains(std::string(operation));
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
        return {
            "player.ban",
            "player.kick",
            "player.unban",
            "server.announce",
            "world.save",
            "world.shutdown",
        };
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
        try
        {
            const auto operation = command.value("operation", "");
            const auto& payload = command.at("payload");
            const auto& target = command.at("target");
            const auto required_string =
                [](const json& object,
                   std::initializer_list<const char*> names,
                   std::size_t maximum,
                   const char* message)
            {
                const auto value = string_field(object, names);
                if (value.empty() || value.size() > maximum)
                {
                    throw std::runtime_error(message);
                }
                return value;
            };
            const auto optional_message = [](const json& object)
            {
                if (!object.contains("message") || object["message"].is_null())
                {
                    return std::string{};
                }
                if (!object["message"].is_string())
                {
                    throw std::runtime_error(
                        "The administrator message must be a string.");
                }
                const auto value = object["message"].get<std::string>();
                if (value.size() > 512)
                {
                    throw std::runtime_error("The administrator message must "
                                             "not exceed 512 characters.");
                }
                return value;
            };
            const auto post = [this, &credentials](const char* path,
                                                   const json& body,
                                                   const char* failure)
            {
                httplib::Client client(m_config.rest_host, m_config.rest_port);
                client.set_connection_timeout(3, 0);
                client.set_read_timeout(10, 0);
                client.set_basic_auth(credentials.username,
                                      credentials.admin_password);
                const auto response =
                    client.Post(path,
                                body.is_null() ? std::string{} : body.dump(),
                                "application/json");
                if (!response || response->status != 200)
                {
                    throw std::runtime_error(failure);
                }
            };

            if (operation == "world.save")
            {
                post("/v1/api/save",
                     nullptr,
                     "The Palworld REST API world save request failed.");
                return {
                    {"state", "completed"},
                    {"result", {{"saved", true}}},
                };
            }
            if (operation == "server.announce")
            {
                const auto message =
                    required_string(payload,
                                    {"message"},
                                    512,
                                    "An announcement between 1 and 512 "
                                    "characters is required.");
                post("/v1/api/announce",
                     {{"message", message}},
                     "The Palworld REST API announcement request failed.");
                return {
                    {"state", "completed"},
                    {"result", {{"announced", true}}},
                };
            }
            if (operation == "player.unban")
            {
                const auto user_id = required_string(
                    target,
                    {"user_id", "userId"},
                    128,
                    "A valid administrator user ID is required.");
                post("/v1/api/unban",
                     {{"userid", user_id}},
                     "The Palworld REST API unban request failed.");
                return {
                    {"state", "completed"},
                    {"result",
                     {
                         {"unbanned", true},
                         {"userId", user_id},
                     }},
                };
            }
            if (operation == "player.kick" || operation == "player.ban")
            {
                const auto user_id = required_string(
                    target,
                    {"user_id", "userId"},
                    128,
                    "A valid administrator user ID is required.");
                const auto administrator_players = players(credentials);
                const auto online = std::ranges::any_of(
                    administrator_players,
                    [&user_id](const auto& player)
                    {
                        return string_field(player,
                                            {"userId", "userid", "user_id"}) ==
                               user_id;
                    });
                if (!online)
                {
                    throw std::runtime_error(
                        "The selected administrator user ID is not online.");
                }
                const auto message = optional_message(payload);
                const auto path =
                    operation == "player.kick" ? "/v1/api/kick" : "/v1/api/ban";
                const auto failure =
                    operation == "player.kick"
                        ? "The Palworld REST API kick request failed."
                        : "The Palworld REST API ban request failed.";
                json body = {{"userid", user_id}};
                if (!message.empty())
                {
                    body["message"] = message;
                }
                post(path, body, failure);
                return {
                    {"state", "completed"},
                    {"result",
                     {
                         {operation == "player.kick" ? "kicked" : "banned",
                          true},
                         {"userId", user_id},
                     }},
                };
            }
            if (operation == "world.shutdown")
            {
                const auto wait_time_match = payload.find("wait_time");
                if (wait_time_match == payload.end() ||
                    !wait_time_match->is_number_integer())
                {
                    throw std::runtime_error(
                        "A shutdown wait time is required.");
                }
                const auto wait_time = wait_time_match->get<std::int64_t>();
                if (wait_time < 5 || wait_time > 3600)
                {
                    throw std::runtime_error("The shutdown wait time must be "
                                             "between 5 and 3600 seconds.");
                }
                const auto message = optional_message(payload);
                post("/v1/api/save",
                     nullptr,
                     "The Palworld REST API world save request failed; "
                     "shutdown was "
                     "not scheduled.");
                post("/v1/api/shutdown",
                     {
                         {"waittime", wait_time},
                         {"message", message},
                     },
                     "The Palworld REST API shutdown request failed.");
                return {
                    {"state", "completed"},
                    {"result",
                     {
                         {"saved", true},
                         {"shutdownScheduled", true},
                         {"waitTime", wait_time},
                     }},
                };
            }
            return {
                {"state", "failed"},
                {"message", "The administrator command is not supported."},
            };
        }
        catch (const std::exception& error)
        {
            return {
                {"state", "failed"},
                {"message", error.what()},
            };
        }
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
              m_sessions(m_config.token_ttl),
              m_snapshots(
                  m_config.snapshot_cache_root,
                  m_config.snapshot_ttl
              )
        {
            if (!m_credential_verifier)
            {
                throw std::invalid_argument(
                    "credential_verifier must not be null"
                );
            }
            if (
                m_config.save_debounce <= std::chrono::milliseconds::zero()
                || m_config.save_max_delay < m_config.save_debounce
            )
            {
                throw std::invalid_argument(
                    "The save timing configuration is invalid."
                );
            }
            m_server_impl.set_payload_max_length(64 * 1024);
            configure_routes();
            m_persistence_thread = std::thread([this]() {
                persistence_loop();
            });
        }

        ~Impl()
        {
            stop();
            stop_persistence();
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
            stop_persistence();
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

        ServerDescriptor current_server()
        {
            std::lock_guard lock(m_server_mutex);
            return m_server;
        }

        bool snapshot_available()
        {
            const auto server = current_server();
            return (
                server.instance_kind == "dedicated_server"
                && !m_config.save_games_root.empty()
            );
        }

        std::vector<std::string> capabilities()
        {
            auto result = combined_capabilities(
                *m_credential_verifier,
                m_game
            );
            if (snapshot_available())
            {
                for (const auto* capability : {
                         "inventory.saved.read",
                         "pal.saved.list",
                         "player.directory.read",
                         "player.saved.details",
                         "save.snapshot.read",
                     })
                {
                    if (
                        std::ranges::find(result, capability)
                        == result.end()
                    )
                    {
                        result.emplace_back(capability);
                    }
                }
                std::ranges::sort(result);
            }
            return result;
        }

        json persistence_status()
        {
            std::lock_guard lock(m_persistence_mutex);
            json value{
                {"state", m_persistence.state},
                {"dirtyRevision", m_persistence.dirty_revision},
                {"savedRevision", m_persistence.saved_revision},
                {"lastError", m_persistence.last_error.empty()
                    ? json(nullptr)
                    : json(m_persistence.last_error)},
            };
            value["dueAt"] = m_persistence.due_at_system
                ? json(utc_timestamp(*m_persistence.due_at_system))
                : json(nullptr);
            value["lastSavedAt"] = m_persistence.last_saved_at
                ? json(utc_timestamp(*m_persistence.last_saved_at))
                : json(nullptr);
            return value;
        }

        void mark_dirty(
            std::uint64_t revision,
            const AdminCredentials& credentials
        )
        {
            const auto now = std::chrono::steady_clock::now();
            const auto now_system = std::chrono::system_clock::now();
            std::lock_guard lock(m_persistence_mutex);
            if (
                m_persistence.state == "clean"
                || m_persistence.state == "failed"
            )
            {
                m_persistence.dirty_since = now;
            }
            m_persistence.state = "dirty";
            m_persistence.dirty_revision = revision;
            m_persistence.last_error.clear();
            m_persistence.credentials = credentials;
            const auto due = std::min(
                now + m_config.save_debounce,
                m_persistence.dirty_since
                    + m_config.save_max_delay
            );
            m_persistence.due_at = due;
            m_persistence.due_at_system =
                now_system
                + std::chrono::duration_cast<
                    std::chrono::system_clock::duration
                >(due - now);
            m_persistence_condition.notify_all();
        }

        void mark_saved(std::uint64_t revision)
        {
            std::lock_guard lock(m_persistence_mutex);
            m_persistence.state = "clean";
            m_persistence.saved_revision = std::max(
                m_persistence.saved_revision,
                revision
            );
            m_persistence.dirty_revision = revision;
            m_persistence.due_at.reset();
            m_persistence.due_at_system.reset();
            m_persistence.last_saved_at =
                std::chrono::system_clock::now();
            m_persistence.last_error.clear();
            m_persistence.credentials.reset();
            m_persistence_condition.notify_all();
        }

        void persistence_loop()
        {
            std::unique_lock lock(m_persistence_mutex);
            while (!m_persistence_stop)
            {
                if (
                    m_persistence.state != "dirty"
                    || !m_persistence.due_at
                    || !m_persistence.credentials
                )
                {
                    m_persistence_condition.wait(
                        lock,
                        [this]() {
                            return m_persistence_stop
                                || (
                                    m_persistence.state == "dirty"
                                    && m_persistence.due_at.has_value()
                                    && m_persistence.credentials.has_value()
                                );
                        }
                    );
                    continue;
                }
                const auto due = *m_persistence.due_at;
                if (
                    m_persistence_condition.wait_until(
                        lock,
                        due,
                        [this, due]() {
                            return m_persistence_stop
                                || m_persistence.state != "dirty"
                                || !m_persistence.due_at
                                || *m_persistence.due_at != due;
                        }
                    )
                )
                {
                    continue;
                }
                const auto credentials = *m_persistence.credentials;
                const auto saving_revision =
                    m_persistence.dirty_revision;
                m_persistence.state = "saving";
                m_persistence.due_at.reset();
                m_persistence.due_at_system.reset();
                lock.unlock();
                json save_result;
                try
                {
                    save_result = m_credential_verifier->execute(
                        credentials,
                        {
                            {"operation", "world.save"},
                            {"target", json::object()},
                            {"payload", json::object()},
                        }
                    );
                }
                catch (const std::exception& error)
                {
                    save_result = {
                        {"state", "failed"},
                        {"message", error.what()},
                    };
                }
                lock.lock();
                if (
                    save_result.value("state", "") == "completed"
                    && m_persistence.dirty_revision == saving_revision
                )
                {
                    m_persistence.state = "clean";
                    m_persistence.saved_revision = saving_revision;
                    m_persistence.last_saved_at =
                        std::chrono::system_clock::now();
                    m_persistence.last_error.clear();
                    m_persistence.credentials.reset();
                }
                else if (
                    save_result.value("state", "") == "completed"
                    && m_persistence.dirty_revision > saving_revision
                )
                {
                    m_persistence.state = "dirty";
                    m_persistence.saved_revision = saving_revision;
                    const auto now = std::chrono::steady_clock::now();
                    const auto due_next = std::min(
                        now + m_config.save_debounce,
                        m_persistence.dirty_since
                            + m_config.save_max_delay
                    );
                    m_persistence.due_at = due_next;
                    m_persistence.due_at_system =
                        std::chrono::system_clock::now()
                        + std::chrono::duration_cast<
                            std::chrono::system_clock::duration
                        >(due_next - now);
                }
                else
                {
                    m_persistence.state = "failed";
                    m_persistence.last_error = save_result.value(
                        "message",
                        "The Palworld world save request failed."
                    );
                    m_persistence.due_at.reset();
                    m_persistence.due_at_system.reset();
                }
            }
        }

        void stop_persistence()
        {
            {
                std::lock_guard lock(m_persistence_mutex);
                if (m_persistence_stop)
                {
                    return;
                }
                m_persistence_stop = true;
            }
            m_persistence_condition.notify_all();
            if (m_persistence_thread.joinable())
            {
                m_persistence_thread.join();
            }
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
                        std::lock_guard server_lock(m_server_mutex);
                        m_server = server;
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
                                capabilities(),
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
                    result["capabilities"] = capabilities();
                    result["persistence"] = persistence_status();
                    json_response(response, 200, result);
                }
            );

            m_server_impl.Post(
                "/v1/snapshots",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    if (!snapshot_available())
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_CAPABILITY_UNSUPPORTED",
                            "Read-only save snapshots are unavailable."
                        );
                        return;
                    }
                    const auto body = parse_object(request, response);
                    if (!body)
                    {
                        return;
                    }
                    if (
                        body->size() != 1
                        || body->value("scope", "") != "players"
                    )
                    {
                        error_response(
                            response,
                            400,
                            "REMOTE_SNAPSHOT_SCOPE_INVALID",
                            "The snapshot scope must be players."
                        );
                        return;
                    }
                    try
                    {
                        const auto server = current_server();
                        json_response(
                            response,
                            202,
                            m_snapshots.create(
                                m_config.save_games_root,
                                server.world_guid
                            )
                        );
                    }
                    catch (const SnapshotBusyError& error)
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_SNAPSHOT_BUSY",
                            error.what()
                        );
                    }
                    catch (const std::exception& error)
                    {
                        error_response(
                            response,
                            409,
                            "REMOTE_SNAPSHOT_UNAVAILABLE",
                            error.what()
                        );
                    }
                }
            );

            m_server_impl.Get(
                R"(/v1/snapshots/([0-9a-f]{32}))",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    const auto snapshot =
                        m_snapshots.get(request.matches[1].str());
                    if (!snapshot)
                    {
                        error_response(
                            response,
                            404,
                            "REMOTE_SNAPSHOT_NOT_FOUND",
                            "The requested snapshot was not found."
                        );
                        return;
                    }
                    json_response(response, 200, *snapshot);
                }
            );

            m_server_impl.Get(
                R"(/v1/snapshots/([0-9a-f]{32})/files/([0-9a-f]{32}))",
                [this](
                    const httplib::Request& request,
                    httplib::Response& response
                ) {
                    if (!authorize(request, response))
                    {
                        return;
                    }
                    const auto file = m_snapshots.file(
                        request.matches[1].str(),
                        request.matches[2].str()
                    );
                    if (!file)
                    {
                        error_response(
                            response,
                            404,
                            "REMOTE_SNAPSHOT_FILE_NOT_FOUND",
                            "The requested snapshot file was not found."
                        );
                        return;
                    }
                    response.set_header(
                        "X-Content-SHA256",
                        file->sha256
                    );
                    response.set_header(
                        "Content-Disposition",
                        "attachment; filename=\""
                            + std::filesystem::path(file->name)
                                  .filename()
                                  .string()
                            + "\""
                    );
                    response.set_file_content(
                        file->path.string(),
                        "application/octet-stream"
                    );
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
                        auto runtime_players = m_game.players();
                        if (
                            has_capability(
                                *m_credential_verifier,
                                "player.kick"
                            )
                            || has_capability(
                                *m_credential_verifier,
                                "player.ban"
                            )
                        )
                        {
                            const auto token = bearer_token(request);
                            const auto credentials = token
                                ? m_sessions.credentials(*token)
                                : std::nullopt;
                            if (credentials)
                            {
                                try
                                {
                                    merge_administrator_player_metadata(
                                        runtime_players,
                                        m_credential_verifier->players(
                                            *credentials
                                        )
                                    );
                                }
                                catch (...)
                                {
                                    for (auto& player : runtime_players)
                                    {
                                        player["administratorMetadata"] =
                                            "unavailable";
                                    }
                                }
                            }
                        }
                        json_response(
                            response,
                            200,
                            {
                                {
                                    "players",
                                    std::move(runtime_players),
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
                    const auto result_state =
                        result.value("state", "");
                    if (
                        result_state == "completed"
                        || result_state == "partial"
                    )
                    {
                        ++m_revision;
                    }
                    result["revision"] = m_revision;
                    if (
                        (
                            result_state == "completed"
                            || result_state == "partial"
                        )
                        && operation_requires_persistence(operation)
                    )
                    {
                        const auto token = bearer_token(request);
                        const auto credentials = token
                            ? m_sessions.credentials(*token)
                            : std::nullopt;
                        if (credentials)
                        {
                            mark_dirty(m_revision, *credentials);
                        }
                    }
                    else if (
                        result_state == "completed"
                        && operation == "world.save"
                    )
                    {
                        mark_saved(m_revision);
                    }
                    result["persistence"] = persistence_status();
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

        struct PersistenceRecord
        {
            std::string state{"clean"};
            std::uint64_t dirty_revision{0};
            std::uint64_t saved_revision{0};
            std::chrono::steady_clock::time_point dirty_since{
                std::chrono::steady_clock::now()
            };
            std::optional<std::chrono::steady_clock::time_point> due_at;
            std::optional<
                std::chrono::system_clock::time_point
            > due_at_system;
            std::optional<
                std::chrono::system_clock::time_point
            > last_saved_at;
            std::string last_error;
            std::optional<AdminCredentials> credentials;
        };

        BridgeConfig m_config;
        ServerDescriptor m_server;
        std::mutex m_server_mutex;
        std::unique_ptr<CredentialVerifier> m_credential_verifier;
        GameCommandPort& m_game;
        SessionRegistry m_sessions;
        SnapshotManager m_snapshots;
        httplib::Server m_server_impl;
        std::thread m_thread;
        std::uint16_t m_bound_port{0};
        std::mutex m_command_mutex;
        std::uint64_t m_revision{0};
        std::deque<std::string> m_command_order;
        std::unordered_map<std::string, CachedCommand> m_completed_commands;
        std::mutex m_persistence_mutex;
        std::condition_variable m_persistence_condition;
        PersistenceRecord m_persistence;
        bool m_persistence_stop{false};
        std::thread m_persistence_thread;
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
