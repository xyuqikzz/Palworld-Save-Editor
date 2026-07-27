#include <pal_editor_bridge_mod.hpp>

#include <array>
#include <chrono>
#include <cstdlib>
#include <cwctype>
#include <filesystem>
#include <format>
#include <fstream>
#include <random>
#include <string_view>
#include <unordered_set>
#include <utility>

#include <Unreal/Hooks/Hooks.hpp>

#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#include <wincrypt.h>
#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")
#endif

using namespace std::chrono_literals;

namespace pal_editor_bridge::ue4ss
{
    namespace
    {
        std::filesystem::path executable_path()
        {
#ifdef _WIN32
            std::wstring buffer(32768, L'\0');
            const auto length = GetModuleFileNameW(
                nullptr,
                buffer.data(),
                static_cast<DWORD>(buffer.size())
            );
            if (length == 0 || length >= buffer.size())
            {
                throw std::runtime_error(
                    "The Palworld executable path could not be determined."
                );
            }
            buffer.resize(length);
            return std::filesystem::path(buffer);
#else
            return {};
#endif
        }

        std::string utf8(const std::wstring& value)
        {
#ifdef _WIN32
            if (value.empty())
            {
                return {};
            }
            const auto length = WideCharToMultiByte(
                CP_UTF8,
                WC_ERR_INVALID_CHARS,
                value.data(),
                static_cast<int>(value.size()),
                nullptr,
                0,
                nullptr,
                nullptr
            );
            if (length <= 0)
            {
                throw std::runtime_error(
                    "A Windows path could not be encoded as UTF-8."
                );
            }
            std::string result(static_cast<std::size_t>(length), '\0');
            if (
                WideCharToMultiByte(
                    CP_UTF8,
                    WC_ERR_INVALID_CHARS,
                    value.data(),
                    static_cast<int>(value.size()),
                    result.data(),
                    length,
                    nullptr,
                    nullptr
                )
                != length
            )
            {
                throw std::runtime_error(
                    "A Windows path could not be encoded as UTF-8."
                );
            }
            return result;
#else
            return {};
#endif
        }

        bool dedicated_server_process()
        {
            auto name = executable_path().filename().wstring();
            std::ranges::transform(
                name,
                name.begin(),
                [](wchar_t value) {
                    return static_cast<wchar_t>(std::towlower(value));
                }
            );
            return name.find(L"palserver") != std::wstring::npos;
        }

        std::string secure_bootstrap_secret()
        {
            std::array<unsigned char, 32> bytes{};
#ifdef _WIN32
            if (
                BCryptGenRandom(
                    nullptr,
                    bytes.data(),
                    static_cast<ULONG>(bytes.size()),
                    BCRYPT_USE_SYSTEM_PREFERRED_RNG
                )
                < 0
            )
            {
                throw std::runtime_error(
                    "The local bridge secret could not be generated."
                );
            }
#else
            std::random_device random;
            std::ranges::generate(bytes, [&random]() {
                return static_cast<unsigned char>(random());
            });
#endif
            std::string result;
            result.reserve(bytes.size() * 2);
            for (const auto value : bytes)
            {
                result += std::format("{:02x}", value);
            }
            return result;
        }

        std::string base64_encode(
            const unsigned char* data,
            std::size_t size
        )
        {
            constexpr std::string_view alphabet{
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "abcdefghijklmnopqrstuvwxyz"
                "0123456789+/"
            };
            std::string result;
            result.reserve(((size + 2) / 3) * 4);
            for (std::size_t offset = 0; offset < size; offset += 3)
            {
                const auto remaining = size - offset;
                const auto value =
                    (static_cast<std::uint32_t>(data[offset]) << 16)
                    | (
                        remaining > 1
                            ? static_cast<std::uint32_t>(data[offset + 1])
                                << 8
                            : 0
                    )
                    | (
                        remaining > 2
                            ? static_cast<std::uint32_t>(data[offset + 2])
                            : 0
                    );
                result.push_back(alphabet[(value >> 18) & 0x3f]);
                result.push_back(alphabet[(value >> 12) & 0x3f]);
                result.push_back(
                    remaining > 1
                        ? alphabet[(value >> 6) & 0x3f]
                        : '='
                );
                result.push_back(
                    remaining > 2 ? alphabet[value & 0x3f] : '='
                );
            }
            return result;
        }

        std::string protect_local_secret(const std::string& secret)
        {
#ifdef _WIN32
            constexpr std::string_view entropy_value{
                "Palworld-Pal-Editor/local-bridge/v1"
            };
            DATA_BLOB input{
                static_cast<DWORD>(secret.size()),
                reinterpret_cast<BYTE*>(
                    const_cast<char*>(secret.data())
                ),
            };
            DATA_BLOB entropy{
                static_cast<DWORD>(entropy_value.size()),
                reinterpret_cast<BYTE*>(
                    const_cast<char*>(entropy_value.data())
                ),
            };
            DATA_BLOB output{};
            if (
                !CryptProtectData(
                    &input,
                    L"Palworld Pal Editor local bridge credential",
                    &entropy,
                    nullptr,
                    nullptr,
                    CRYPTPROTECT_UI_FORBIDDEN,
                    &output
                )
            )
            {
                throw std::runtime_error(
                    "The local bridge secret could not be protected with Windows DPAPI."
                );
            }
            try
            {
                const auto result =
                    base64_encode(output.pbData, output.cbData);
                LocalFree(output.pbData);
                return result;
            }
            catch (...)
            {
                LocalFree(output.pbData);
                throw;
            }
#else
            throw std::runtime_error(
                "Local bridge discovery requires Windows DPAPI."
            );
#endif
        }

        std::uint64_t process_start_time()
        {
#ifdef _WIN32
            FILETIME created{};
            FILETIME exited{};
            FILETIME kernel{};
            FILETIME user{};
            if (
                !GetProcessTimes(
                    GetCurrentProcess(),
                    &created,
                    &exited,
                    &kernel,
                    &user
                )
            )
            {
                throw std::runtime_error(
                    "The Palworld process start time could not be read."
                );
            }
            ULARGE_INTEGER value{};
            value.LowPart = created.dwLowDateTime;
            value.HighPart = created.dwHighDateTime;
            return value.QuadPart;
#else
            return 0;
#endif
        }

        std::filesystem::path local_instance_directory()
        {
#ifdef _WIN32
            wchar_t* value = nullptr;
            std::size_t length = 0;
            if (
                _wdupenv_s(&value, &length, L"LOCALAPPDATA") != 0
                || !value || length <= 1
            )
            {
                if (value)
                {
                    std::free(value);
                }
                throw std::runtime_error(
                    "LOCALAPPDATA is unavailable for local bridge discovery."
                );
            }
            const std::filesystem::path root(value);
            std::free(value);
            return root / "Palworld-Pal-Editor" / "bridge-instances";
#else
            return {};
#endif
        }

        std::string player_id(const nlohmann::json& command)
        {
            const auto& target = command.at("target");
            for (
                const auto* name :
                {"player_uid", "playerId", "playerUid", "uid"}
            )
            {
                const auto match = target.find(name);
                if (
                    match != target.end() && match->is_string()
                    && !match->get_ref<const std::string&>().empty()
                )
                {
                    return match->get<std::string>();
                }
            }
            throw std::runtime_error(
                "A target playerId is required."
            );
        }

        std::string payload_string(
            const nlohmann::json& command,
            std::initializer_list<const char*> names,
            const char* description,
            std::size_t maximum_length
        )
        {
            const auto& payload = command.at("payload");
            for (const auto* name : names)
            {
                const auto match = payload.find(name);
                if (
                    match != payload.end() && match->is_string()
                    && !match->get_ref<const std::string&>().empty()
                    && match->get_ref<const std::string&>().size()
                        <= maximum_length
                )
                {
                    return match->get<std::string>();
                }
            }
            throw std::runtime_error(
                std::string(description) + " is required."
            );
        }

        std::int32_t payload_integer(
            const nlohmann::json& command,
            const char* name,
            const char* description,
            std::int32_t minimum,
            std::int32_t maximum
        )
        {
            const auto& payload = command.at("payload");
            const auto match = payload.find(name);
            if (
                match == payload.end() || !match->is_number_integer()
            )
            {
                throw std::runtime_error(
                    std::string(description) + " must be an integer."
                );
            }
            const auto value = match->get<std::int64_t>();
            if (value < minimum || value > maximum)
            {
                throw std::runtime_error(
                    std::string(description)
                    + " is outside the supported range."
                );
            }
            return static_cast<std::int32_t>(value);
        }

        PalGrantOptions pal_grant_options(
            const nlohmann::json& command
        )
        {
            const auto& payload = command.at("payload");
            PalGrantOptions result;

            const auto unrestricted_value = payload.find("unrestricted");
            bool unrestricted = false;
            if (unrestricted_value != payload.end())
            {
                if (!unrestricted_value->is_boolean())
                {
                    throw std::runtime_error(
                        "unrestricted must be a boolean."
                    );
                }
                unrestricted = unrestricted_value->get<bool>();
            }
            result.unrestricted = unrestricted;
            const auto iv_maximum = unrestricted ? 255 : 100;
            const auto condensation_maximum = unrestricted ? 255 : 5;
            const auto soul_maximum = unrestricted ? 255 : 60;

            auto passives = payload.find("passiveSkills");
            if (passives == payload.end())
            {
                passives = payload.find("passive_skills");
            }
            if (passives != payload.end())
            {
                if (!passives->is_array() || passives->size() > 4)
                {
                    throw std::runtime_error(
                        "passiveSkills must be an array with at most four entries."
                    );
                }
                std::vector<std::string> values;
                std::unordered_set<std::string> unique;
                for (const auto& passive : *passives)
                {
                    if (
                        !passive.is_string()
                        || passive.get_ref<const std::string&>().empty()
                        || passive.get_ref<const std::string&>().size()
                            > 128
                    )
                    {
                        throw std::runtime_error(
                            "Each passive skill ID must be a non-empty string."
                        );
                    }
                    auto value = passive.get<std::string>();
                    if (!unique.emplace(value).second)
                    {
                        throw std::runtime_error(
                            "passiveSkills must not contain duplicates."
                        );
                    }
                    values.push_back(std::move(value));
                }
            result.passive_skills = std::move(values);
            }

            const auto ivs = payload.find("ivs");
            if (ivs != payload.end())
            {
                if (!ivs->is_object())
                {
                    throw std::runtime_error(
                        "ivs must be an object."
                    );
                }
                auto read_iv = [&ivs, iv_maximum](
                    const char* name
                ) -> std::optional<std::int32_t> {
                    const auto value = ivs->find(name);
                    if (value == ivs->end())
                    {
                        return std::nullopt;
                    }
                    if (!value->is_number_integer())
                    {
                        throw std::runtime_error(
                            std::string("ivs.") + name
                            + " must be an integer."
                        );
                    }
                    const auto integer = value->get<std::int64_t>();
                    if (integer < 0 || integer > iv_maximum)
                    {
                        throw std::runtime_error(
                            std::string("ivs.") + name
                            + " is outside the supported range."
                        );
                    }
                    return static_cast<std::int32_t>(integer);
                };
                result.iv_hp = read_iv("hp");
                result.iv_melee = read_iv("melee");
                result.iv_shot = read_iv("shot");
                result.iv_defense = read_iv("defense");
            }

            const auto enhancements = payload.find("enhancements");
            if (enhancements != payload.end())
            {
                if (!enhancements->is_object())
                {
                    throw std::runtime_error(
                        "enhancements must be an object."
                    );
                }
                auto read_enhancement = [&enhancements](
                    std::initializer_list<const char*> names,
                    const char* description,
                    std::int32_t minimum,
                    std::int32_t maximum
                ) -> std::optional<std::int32_t> {
                    auto value = enhancements->end();
                    for (const auto* name : names)
                    {
                        value = enhancements->find(name);
                        if (value != enhancements->end())
                        {
                            break;
                        }
                    }
                    if (value == enhancements->end())
                    {
                        return std::nullopt;
                    }
                    if (!value->is_number_integer())
                    {
                        throw std::runtime_error(
                            std::string(description)
                            + " must be an integer."
                        );
                    }
                    const auto integer = value->get<std::int64_t>();
                    if (integer < minimum || integer > maximum)
                    {
                        throw std::runtime_error(
                            std::string(description)
                            + " is outside the supported range."
                        );
                    }
                    return static_cast<std::int32_t>(integer);
                };
                result.condensation = read_enhancement(
                    {"condensation"},
                    "enhancements.condensation",
                    1,
                    condensation_maximum
                );
                result.soul_hp = read_enhancement(
                    {"soulHp", "soul_hp"},
                    "enhancements.soulHp",
                    0,
                    soul_maximum
                );
                result.soul_attack = read_enhancement(
                    {"soulAttack", "soul_attack"},
                    "enhancements.soulAttack",
                    0,
                    soul_maximum
                );
                result.soul_defense = read_enhancement(
                    {"soulDefense", "soul_defense"},
                    "enhancements.soulDefense",
                    0,
                    soul_maximum
                );
                result.soul_craft_speed = read_enhancement(
                    {"soulCraftSpeed", "soul_craft_speed"},
                    "enhancements.soulCraftSpeed",
                    0,
                    soul_maximum
                );
            }
            return result;
        }

    } // namespace

    class LocalBridgeInstance final
    {
      public:
        LocalBridgeInstance(
            std::uint16_t port,
            const std::string& bootstrap_secret
        )
        {
#ifdef _WIN32
            const auto directory = local_instance_directory();
            std::filesystem::create_directories(directory);
            const auto process_id = GetCurrentProcessId();
            m_path = directory
                / std::format(L"client-{}.json", process_id);
            const auto temporary = m_path.wstring() + L".tmp";
            const auto process_path = executable_path();
            const auto registration = nlohmann::json{
                {"version", 1},
                {"protocolVersion", protocol_version},
                {"bridgeVersion", bridge_version},
                {
                    "address",
                    std::format("http://127.0.0.1:{}", port)
                },
                {"username", "local"},
                {
                    "protectedSecret",
                    protect_local_secret(bootstrap_secret)
                },
                {"pid", process_id},
                {
                    "processStartTime",
                    std::to_string(process_start_time())
                },
                {
                    "executablePath",
                    utf8(process_path.wstring())
                },
                {"instanceKind", "local_game"},
            };
            {
                std::ofstream output(
                    std::filesystem::path(temporary),
                    std::ios::binary | std::ios::trunc
                );
                if (!output)
                {
                    throw std::runtime_error(
                        "The local bridge registration file could not be created."
                    );
                }
                output << registration.dump(2);
                output.flush();
                if (!output)
                {
                    throw std::runtime_error(
                        "The local bridge registration file could not be written."
                    );
                }
            }
            if (
                !MoveFileExW(
                    temporary.c_str(),
                    m_path.c_str(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
                )
            )
            {
                DeleteFileW(temporary.c_str());
                throw std::runtime_error(
                    "The local bridge registration file could not be published."
                );
            }
#endif
        }

        ~LocalBridgeInstance()
        {
            std::error_code ignored;
            std::filesystem::remove(m_path, ignored);
        }

      private:
        std::filesystem::path m_path;
    };

    GamePort::GamePort(bool dedicated_process)
        : m_dedicated_process(dedicated_process)
    {
    }
    GamePort::~GamePort() = default;

    void GamePort::mark_ready()
    {
        m_ready.store(true);
        refresh_runtime_capabilities();
    }

    bool GamePort::ready() const
    {
        return m_ready.load();
    }

    std::vector<std::string> GamePort::capabilities() const
    {
        std::vector<std::string> capabilities{
            "server.status",
        };
        if (m_player_list_ready.load())
        {
            capabilities.emplace_back("player.list");
        }
        if (m_guild_list_ready.load())
        {
            capabilities.emplace_back("guild.list");
        }
        if (m_player_details_ready.load())
        {
            capabilities.emplace_back("player.details");
        }
        if (m_inventory_read_ready.load())
        {
            capabilities.emplace_back("inventory.read");
        }
        if (m_pal_list_ready.load())
        {
            capabilities.emplace_back("pal.list");
        }
        if (m_map_read_ready.load())
        {
            capabilities.emplace_back("map.read");
        }
        if (m_inventory_ready.load())
        {
            capabilities.emplace_back("inventory.grant");
        }
        if (m_experience_ready.load())
        {
            capabilities.emplace_back("player.experience.add");
        }
        if (m_pal_ready.load())
        {
            capabilities.emplace_back("pal.grant");
        }
        return capabilities;
    }

    nlohmann::json GamePort::status()
    {
        const auto runtime_status = m_runtime.status();
        return {
            {"gameReady", ready()},
            {"instanceMode", m_runtime.instance_mode()},
            {"authoritative", m_runtime.authoritative()},
            {
                "managementSupported",
                m_runtime.authoritative()
            },
            {
                "runtimeCommandsReady",
                m_inventory_ready.load()
                    || m_experience_ready.load()
                    || m_pal_ready.load()
            },
            {
                "runtimeDataReady",
                m_guild_list_ready.load()
                    || m_player_details_ready.load()
                    || m_inventory_read_ready.load()
                    || m_pal_list_ready.load()
                    || m_map_read_ready.load()
            },
            {
                "runtime",
                runtime_status,
            },
        };
    }

    nlohmann::json GamePort::players()
    {
        const auto response = execute({
            {"operation", "player.list"},
            {"target", nlohmann::json::object()},
            {"payload", nlohmann::json::object()},
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
            || !response["result"].contains("players")
            || !response["result"]["players"].is_array()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime player list is unavailable."
                )
            );
        }
        return response["result"]["players"];
    }

    nlohmann::json GamePort::guilds()
    {
        const auto response = execute({
            {"operation", "guild.list"},
            {"target", nlohmann::json::object()},
            {"payload", nlohmann::json::object()},
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
            || !response["result"].contains("guilds")
            || !response["result"]["guilds"].is_array()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime guild list is unavailable."
                )
            );
        }
        return response["result"]["guilds"];
    }

    nlohmann::json GamePort::map_snapshot()
    {
        const auto response = execute({
            {"operation", "map.read"},
            {"target", nlohmann::json::object()},
            {"payload", nlohmann::json::object()},
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
            || !response["result"].contains("players")
            || !response["result"]["players"].is_array()
            || !response["result"].contains("guilds")
            || !response["result"]["guilds"].is_array()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime map snapshot is unavailable."
                )
            );
        }
        return response["result"];
    }

    nlohmann::json GamePort::player_details(
        const std::string& player_id
    )
    {
        const auto response = execute({
            {"operation", "player.details"},
            { "target", {{"player_uid", player_id}} },
            {"payload", nlohmann::json::object()},
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime player details are unavailable."
                )
            );
        }
        return response["result"];
    }

    nlohmann::json GamePort::inventory(const std::string& player_id)
    {
        const auto response = execute({
            {"operation", "inventory.read"},
            { "target", {{"player_uid", player_id}} },
            {"payload", nlohmann::json::object()},
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime inventory is unavailable."
                )
            );
        }
        return response["result"];
    }

    nlohmann::json GamePort::pals(
        const std::string& player_id,
        const std::string& collection,
        std::size_t page_index,
        std::size_t page_size
    )
    {
        const auto response = execute({
            {"operation", "pal.list"},
            { "target", {{"player_uid", player_id}} },
            {
                "payload",
                {
                    {"collection", collection},
                    {"page", page_index},
                    {"page_size", page_size},
                }
            },
        });
        if (
            response.value("state", "") != "completed"
            || !response.contains("result")
            || !response["result"].is_object()
        )
        {
            throw std::runtime_error(
                response.value(
                    "message",
                    "The runtime Palbox page is unavailable."
                )
            );
        }
        return response["result"];
    }

    nlohmann::json GamePort::execute(const nlohmann::json& command)
    {
        if (!ready() || !m_accepting.load())
        {
            return {
                {"state", "failed"},
                {"message", "The Palworld game thread is not ready."},
            };
        }

        auto pending = std::make_shared<PendingCommand>();
        pending->command = command;
        auto result = pending->completion.get_future();
        {
            std::lock_guard lock(m_queue_mutex);
            if (!m_accepting.load())
            {
                return {
                    {"state", "failed"},
                    {"message", "The bridge is shutting down."},
                };
            }
            m_queue.push_back(pending);
        }
        if (result.wait_for(5s) != std::future_status::ready)
        {
            auto expected = PendingState::queued;
            if (pending->state.compare_exchange_strong(
                    expected,
                    PendingState::cancelled
                ))
            {
                return {
                    {"state", "failed"},
                    {"message", "The Palworld game thread did not process the command in time."},
                };
            }

            // Once ProcessEvent has started the mutation can no longer be
            // cancelled safely. Wait for its authoritative result instead of
            // reporting a failure that could make a retry duplicate it.
            result.wait();
        }
        return result.get();
    }

    void GamePort::drain_game_thread()
    {
        std::deque<std::shared_ptr<PendingCommand>> pending;
        {
            std::lock_guard lock(m_queue_mutex);
            pending.swap(m_queue);
        }
        for (const auto& item : pending)
        {
            auto expected = PendingState::queued;
            if (!item->state.compare_exchange_strong(
                    expected,
                    PendingState::executing
                ))
            {
                if (expected == PendingState::cancelled)
                {
                    item->completion.set_value({
                        {"state", "failed"},
                        {"message", "The Palworld game thread command was cancelled before execution."},
                    });
                }
                continue;
            }
            const auto started_at = std::chrono::steady_clock::now();
            try
            {
                auto response = execute_on_game_thread(item->command);
                const auto completed_at =
                    std::chrono::steady_clock::now();
                response["bridgeTimingsMs"] = {
                    {
                        "queueWait",
                        std::chrono::duration<double, std::milli>(
                            started_at - item->queued_at
                        ).count()
                    },
                    {
                        "gameThreadExecution",
                        std::chrono::duration<double, std::milli>(
                            completed_at - started_at
                        ).count()
                    },
                };
                item->state.store(PendingState::completed);
                item->completion.set_value(std::move(response));
            }
            catch (const std::exception& error)
            {
                item->state.store(PendingState::completed);
                item->completion.set_value({
                    {"state", "failed"},
                    {"message", error.what()},
                });
            }
            catch (...)
            {
                item->state.store(PendingState::completed);
                item->completion.set_value({
                    {"state", "failed"},
                    {"message", "The game command failed unexpectedly."},
                });
            }
        }

        if (!pending.empty())
        {
            return;
        }
        if (
            ready()
            && !runtime_signatures_ready()
            && ++m_ticks_until_runtime_refresh >= 300
        )
        {
            refresh_runtime_capabilities();
            m_ticks_until_runtime_refresh = 0;
        }
        if (
            ready()
            && ++m_ticks_until_authority_refresh >= 60
        )
        {
            refresh_authority_capabilities();
            m_ticks_until_authority_refresh = 0;
        }
    }

    void GamePort::stop_accepting()
    {
        m_accepting.store(false);
        m_ready.store(false);
        std::deque<std::shared_ptr<PendingCommand>> pending;
        {
            std::lock_guard lock(m_queue_mutex);
            pending.swap(m_queue);
        }
        for (const auto& item : pending)
        {
            item->state.store(PendingState::cancelled);
            item->completion.set_value({
                {"state", "failed"},
                {"message", "The bridge is shutting down."},
            });
        }
    }

    nlohmann::json GamePort::execute_on_game_thread(
        const nlohmann::json& command
    )
    {
        const auto operation = command.value("operation", "");
        if (operation == "server.status")
        {
            return {
                {"state", "completed"},
                {"result", status()},
            };
        }
        if (operation == "player.list")
        {
            return {
                {"state", "completed"},
                {"result", {{"players", m_runtime.players()}}},
            };
        }
        if (operation == "guild.list")
        {
            return {
                {"state", "completed"},
                {"result", {{"guilds", m_runtime.guilds()}}},
            };
        }
        if (operation == "map.read")
        {
            return {
                {"state", "completed"},
                {"result", m_runtime.map_snapshot()},
            };
        }
        if (operation == "player.details")
        {
            return {
                {"state", "completed"},
                {"result", m_runtime.player_details(player_id(command))},
            };
        }
        if (operation == "inventory.read")
        {
            return {
                {"state", "completed"},
                {
                    "result",
                    m_runtime.inventory_snapshot(player_id(command))
                },
            };
        }
        if (operation == "pal.list")
        {
            const auto collection = command.at("payload").value(
                "collection",
                "palbox"
            );
            if (collection != "party" && collection != "palbox")
            {
                throw std::runtime_error(
                    "The Pal collection must be party or palbox."
                );
            }
            return {
                {"state", "completed"},
                {
                    "result",
                    m_runtime.pal_snapshot(
                        player_id(command),
                        collection,
                        static_cast<std::size_t>(
                            payload_integer(
                                command,
                                "page",
                                "Palbox page",
                                0,
                                100000
                            )
                        ),
                        static_cast<std::size_t>(
                            payload_integer(
                                command,
                                "page_size",
                                "Palbox page size",
                                1,
                                30
                            )
                        )
                    )
                },
            };
        }
        if (operation == "inventory.grant")
        {
            return m_runtime.grant_item(
                player_id(command),
                payload_string(
                    command,
                    {"item_id", "itemId"},
                    "An item ID",
                    128
                ),
                payload_integer(
                    command,
                    "quantity",
                    "Item quantity",
                    1,
                    999999
                )
            );
        }
        if (operation == "player.experience.add")
        {
            return m_runtime.add_player_experience(
                player_id(command),
                payload_integer(
                    command,
                    "amount",
                    "Experience amount",
                    1,
                    2'000'000'000
                )
            );
        }
        if (operation == "pal.grant")
        {
            return m_runtime.grant_pal(
                player_id(command),
                payload_string(
                    command,
                    {"character_id", "characterId"},
                    "A Pal character ID",
                    128
                ),
                payload_integer(
                    command,
                    "level",
                    "Pal level",
                    1,
                    80
                ),
                pal_grant_options(command)
            );
        }
        return {
            {"state", "failed"},
            {"message", "The gameplay command is not implemented yet."},
        };
    }

    void GamePort::refresh_runtime_capabilities()
    {
        m_runtime.initialize();
        refresh_authority_capabilities();
    }

    void GamePort::refresh_authority_capabilities()
    {
        m_runtime.refresh_instance_mode(m_dedicated_process);
        const auto authoritative = m_runtime.authoritative();
        m_inventory_ready.store(
            authoritative && m_runtime.inventory_ready()
        );
        m_experience_ready.store(
            authoritative && m_runtime.experience_ready()
        );
        m_pal_ready.store(
            authoritative && m_runtime.pal_ready()
        );
        m_player_list_ready.store(
            authoritative && m_runtime.player_list_ready()
        );
        m_guild_list_ready.store(
            authoritative && m_runtime.guild_list_ready()
        );
        m_player_details_ready.store(
            authoritative && m_runtime.player_details_ready()
        );
        m_inventory_read_ready.store(
            authoritative && m_runtime.inventory_read_ready()
        );
        m_pal_list_ready.store(
            authoritative && m_runtime.pal_list_ready()
        );
        m_map_read_ready.store(
            authoritative && m_runtime.map_read_ready()
        );
    }

    bool GamePort::runtime_signatures_ready() const
    {
        return m_runtime.inventory_ready()
            && m_runtime.experience_ready()
            && m_runtime.pal_ready()
            && m_runtime.player_list_ready()
            && m_runtime.guild_list_ready()
            && m_runtime.player_details_ready()
            && m_runtime.inventory_read_ready()
            && m_runtime.pal_list_ready()
            && m_runtime.map_read_ready();
    }

    PalEditorBridgeMod::PalEditorBridgeMod()
        : m_dedicated_process(dedicated_server_process()),
          m_game(m_dedicated_process)
    {
        ModName = STR("PalEditorBridge");
        ModVersion = STR("0.6.0");
        ModDescription =
            STR("Headless bridge for Palworld Pal Editor live management.");
        ModAuthors = STR("Palworld-Pal-Editor");

        BridgeConfig config;
        ServerDescriptor server;
        server.platform = "Win64";
        std::unique_ptr<CredentialVerifier> verifier;
        std::string local_secret;
        if (m_dedicated_process)
        {
            server.name = "Palworld Dedicated Server";
            server.instance_kind = "dedicated_server";
            verifier =
                std::make_unique<PalworldRestCredentialVerifier>(config);
        }
        else
        {
            config.bridge_port = 0;
            server.name = "Palworld Local Game";
            server.instance_kind = "local_game";
            local_secret = secure_bootstrap_secret();
            verifier = std::make_unique<LocalCredentialVerifier>(
                local_secret,
                server
            );
        }
        m_host = std::make_unique<BridgeHost>(
            std::move(config),
            std::move(server),
            std::move(verifier),
            m_game
        );
        const auto port = m_host->start();
        if (!m_dedicated_process)
        {
            try
            {
                m_local_instance =
                    std::make_unique<LocalBridgeInstance>(
                        port,
                        local_secret
                    );
            }
            catch (...)
            {
                m_host->stop();
                throw;
            }
        }
    }

    PalEditorBridgeMod::~PalEditorBridgeMod()
    {
        m_game.stop_accepting();
        if (m_tick_callback_id != 0)
        {
            RC::Unreal::Hook::UnregisterCallback(m_tick_callback_id);
            m_tick_callback_id = 0;
        }
        if (m_host)
        {
            m_host->stop();
        }
        m_local_instance.reset();
    }

    void PalEditorBridgeMod::on_unreal_init()
    {
        m_game.mark_ready();
        m_tick_callback_id =
            RC::Unreal::Hook::RegisterEngineTickPreCallback(
                [this](auto&, RC::Unreal::UEngine*, float, bool) {
                    m_game.drain_game_thread();
                },
                {
                    false,
                    true,
                    STR("PalEditorBridge"),
                    STR("DrainCommandQueue"),
                }
            );
    }
} // namespace pal_editor_bridge::ue4ss
