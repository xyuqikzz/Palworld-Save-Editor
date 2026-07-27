#include <palworld_runtime.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include <Helpers\String.hpp>
#include <Unreal\Core\Containers\Array.hpp>
#include <Unreal\CoreUObject\UObject\FStrProperty.hpp>
#include <Unreal\CoreUObject\UObject\Class.hpp>
#include <Unreal\CoreUObject\UObject\UnrealType.hpp>
#include <Unreal\FField.hpp>
#include <Unreal\Property\FEnumProperty.hpp>
#include <Unreal\UFunctionStructs.hpp>
#include <Unreal\UObject.hpp>
#include <Unreal\UObjectGlobals.hpp>

namespace pal_editor_bridge::ue4ss
{
    namespace
    {
        using namespace RC::Unreal;

        struct PlayerGuid
        {
            std::uint32_t a;
            std::uint32_t b;
            std::uint32_t c;
            std::uint32_t d;
        };

        class Invocation final
        {
          public:
            explicit Invocation(
                UFunction* function,
                bool initialize_parameters = false
            )
                : m_function(function),
                  m_parameters(
                      function
                          ? static_cast<std::size_t>(
                                function->GetParmsSize()
                            )
                          : 0
                  ),
                  m_initialized(initialize_parameters)
            {
                if (!m_function)
                {
                    throw std::runtime_error(
                        "The reflected Palworld function is unavailable."
                    );
                }
                std::ranges::fill(m_parameters, std::uint8_t{0});
                if (m_initialized && !m_parameters.empty())
                {
                    m_function->InitializeStruct(m_parameters.data());
                }
            }

            ~Invocation()
            {
                if (
                    m_initialized && m_function
                    && !m_parameters.empty()
                )
                {
                    m_function->DestroyStruct(m_parameters.data());
                }
            }

            Invocation(const Invocation&) = delete;
            Invocation& operator=(const Invocation&) = delete;

            UFunction* function() const
            {
                return m_function;
            }

            void* data()
            {
                return m_parameters.data();
            }

            void call(UObject* context)
            {
                if (!context || !UObject::IsReal(context))
                {
                    throw std::runtime_error(
                        "The reflected Palworld call context is invalid."
                    );
                }
                context->ProcessEvent(m_function, data());
            }

          private:
            UFunction* m_function;
            std::vector<std::uint8_t> m_parameters;
            bool m_initialized;
        };

        UFunction* find_function(const TCHAR* path)
        {
            return UObjectGlobals::StaticFindObject<UFunction*>(
                nullptr,
                nullptr,
                path
            );
        }

        std::string lowercase_ascii(std::string value)
        {
            std::ranges::transform(
                value,
                value.begin(),
                [](unsigned char character) {
                    return static_cast<char>(std::tolower(character));
                }
            );
            return value;
        }

        nlohmann::json function_description(UFunction* function)
        {
            if (!function || !UObject::IsReal(function))
            {
                return nullptr;
            }

            nlohmann::json parameters = nlohmann::json::array();
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    function,
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                const auto flags = property->GetPropertyFlags();
                if ((flags & CPF_Parm) == 0)
                {
                    continue;
                }
                auto description = nlohmann::json{
                    {"name", RC::to_string(property->GetName())},
                    {
                        "fullName",
                        RC::to_string(property->GetFullName())
                    },
                    {
                        "type",
                        RC::to_string(property->GetClass().GetName())
                    },
                    {"offset", property->GetOffset_Internal()},
                    {"size", property->GetSize()},
                    {"flags", static_cast<std::uint64_t>(flags)},
                    {"return", (flags & CPF_ReturnParm) != 0},
                    {"out", (flags & CPF_OutParm) != 0},
                };
                if (auto* object_property =
                        CastField<FObjectPropertyBase>(property))
                {
                    auto* object_class =
                        object_property->GetPropertyClass().Get();
                    description["objectClass"] = object_class
                        ? RC::to_string(object_class->GetFullName())
                        : std::string{};
                }
                else if (auto* struct_property =
                             CastField<FStructProperty>(property))
                {
                    auto* structure =
                        struct_property->GetStruct().Get();
                    description["struct"] = structure
                        ? RC::to_string(structure->GetFullName())
                        : std::string{};
                }
                else if (auto* array_property =
                             CastField<FArrayProperty>(property))
                {
                    auto* inner = array_property->GetInner();
                    auto inner_description = inner
                        ? nlohmann::json{
                              {
                                  "type",
                                  RC::to_string(
                                      inner->GetClass().GetName()
                                  )
                              },
                              {"size", inner->GetSize()},
                          }
                        : nlohmann::json(nullptr);
                    if (auto* inner_object =
                            CastField<FObjectPropertyBase>(inner))
                    {
                        auto* object_class =
                            inner_object->GetPropertyClass().Get();
                        inner_description["objectClass"] =
                            object_class
                                ? RC::to_string(
                                      object_class->GetFullName()
                                  )
                                : std::string{};
                    }
                    else if (auto* inner_struct =
                                 CastField<FStructProperty>(inner))
                    {
                        auto* structure =
                            inner_struct->GetStruct().Get();
                        inner_description["struct"] =
                            structure
                                ? RC::to_string(
                                      structure->GetFullName()
                                  )
                                : std::string{};
                    }
                    description["inner"] =
                        std::move(inner_description);
                }
                parameters.push_back(std::move(description));
            }

            const auto flags = function->GetFunctionFlags();
            return {
                {"fullName", RC::to_string(function->GetFullName())},
                {"flags", static_cast<std::uint32_t>(flags)},
                {"parameterSize", function->GetParmsSize()},
                {"net", (flags & FUNC_Net) != 0},
                {"netServer", (flags & FUNC_NetServer) != 0},
                {"netClient", (flags & FUNC_NetClient) != 0},
                {"netReliable", (flags & FUNC_NetReliable) != 0},
                {
                    "blueprintAuthorityOnly",
                    (flags & FUNC_BlueprintAuthorityOnly) != 0
                },
                {"native", (flags & FUNC_Native) != 0},
                {"event", (flags & FUNC_Event) != 0},
                {"static", (flags & FUNC_Static) != 0},
                {"parameters", std::move(parameters)},
            };
        }

        nlohmann::json find_experience_functions()
        {
            std::vector<nlohmann::json> matches;
            UObjectGlobals::ForEachUObject(
                [&matches](
                    UObject* object,
                    [[maybe_unused]] std::int32_t chunk_index,
                    [[maybe_unused]] std::int32_t object_index
                ) {
                    auto* function = Cast<UFunction>(object);
                    if (!function)
                    {
                        return RC::LoopAction::Continue;
                    }

                    const auto full_name =
                        RC::to_string(function->GetFullName());
                    const auto normalized = lowercase_ascii(full_name);
                    if (
                        normalized.find("playerexp")
                            == std::string::npos
                        && normalized.find("partyexp")
                            == std::string::npos
                        && normalized.find("addexpforallplayer")
                            == std::string::npos
                    )
                    {
                        return RC::LoopAction::Continue;
                    }
                    matches.push_back(function_description(function));
                    return RC::LoopAction::Continue;
                }
            );
            std::ranges::sort(
                matches,
                [](const auto& left, const auto& right) {
                    return left.value("fullName", "")
                        < right.value("fullName", "");
                }
            );
            return matches;
        }

        nlohmann::json find_functions_containing(
            std::string_view fragment
        )
        {
            std::vector<nlohmann::json> matches;
            UObjectGlobals::ForEachUObject(
                [&matches, fragment](
                    UObject* object,
                    [[maybe_unused]] std::int32_t chunk_index,
                    [[maybe_unused]] std::int32_t object_index
                ) {
                    auto* function = Cast<UFunction>(object);
                    if (!function)
                    {
                        return RC::LoopAction::Continue;
                    }
                    const auto full_name =
                        RC::to_string(function->GetFullName());
                    if (full_name.find(fragment) == std::string::npos)
                    {
                        return RC::LoopAction::Continue;
                    }
                    matches.push_back(function_description(function));
                    return RC::LoopAction::Continue;
                }
            );
            std::ranges::sort(
                matches,
                [](const auto& left, const auto& right) {
                    return left.value("fullName", "")
                        < right.value("fullName", "");
                }
            );
            return matches;
        }

        nlohmann::json object_description(UObject* object)
        {
            if (!object || !UObject::IsReal(object))
            {
                return nullptr;
            }
            auto* object_class = object->GetClassPrivate();
            auto* outer = object->GetOuterPrivate();
            return {
                {"fullName", RC::to_string(object->GetFullName())},
                {
                    "class",
                    object_class
                        ? RC::to_string(object_class->GetFullName())
                        : std::string{}
                },
                {
                    "outer",
                    outer && UObject::IsReal(outer)
                        ? RC::to_string(outer->GetFullName())
                        : std::string{}
                },
            };
        }

        void* property_value(FProperty* property, void* container);

        nlohmann::json property_description(
            FProperty* property,
            UObject* object
        )
        {
            nlohmann::json result{
                {"name", RC::to_string(property->GetName())},
                {
                    "type",
                    RC::to_string(property->GetClass().GetName())
                },
                {"offset", property->GetOffset_Internal()},
                {"size", property->GetSize()},
                {
                    "flags",
                    static_cast<std::uint64_t>(
                        property->GetPropertyFlags()
                    )
                },
            };

            if (auto* object_property =
                    CastField<FObjectPropertyBase>(property))
            {
                result["objectClass"] =
                    object_property->GetPropertyClass()
                        ? RC::to_string(
                              object_property
                                  ->GetPropertyClass()
                                  ->GetFullName()
                          )
                        : std::string{};
            }
            else if (auto* struct_property =
                         CastField<FStructProperty>(property))
            {
                auto* structure =
                    struct_property->GetStruct().Get();
                result["struct"] = structure
                    ? RC::to_string(structure->GetFullName())
                    : std::string{};
            }
            else if (auto* array_property =
                         CastField<FArrayProperty>(property))
            {
                auto* inner = array_property->GetInner();
                result["inner"] = inner
                    ? nlohmann::json{
                          {
                              "name",
                              RC::to_string(inner->GetName())
                          },
                          {
                              "type",
                              RC::to_string(
                                  inner->GetClass().GetName()
                              )
                          },
                          {"size", inner->GetSize()},
                      }
                    : nlohmann::json(nullptr);
            }
            else if (auto* map_property =
                         CastField<FMapProperty>(property))
            {
                auto describe_part = [](FProperty* part) {
                    return part
                        ? nlohmann::json{
                              {
                                  "name",
                                  RC::to_string(part->GetName())
                              },
                              {
                                  "type",
                                  RC::to_string(
                                      part->GetClass().GetName()
                                  )
                              },
                              {"size", part->GetSize()},
                          }
                        : nlohmann::json(nullptr);
                };
                result["key"] =
                    describe_part(map_property->GetKeyProp());
                result["valueType"] =
                    describe_part(map_property->GetValueProp());
            }
            else if (auto* set_property =
                         CastField<FSetProperty>(property))
            {
                auto* element = set_property->GetElementProp();
                result["element"] = element
                    ? nlohmann::json{
                          {
                              "name",
                              RC::to_string(element->GetName())
                          },
                          {
                              "type",
                              RC::to_string(
                                  element->GetClass().GetName()
                              )
                          },
                          {"size", element->GetSize()},
                      }
                    : nlohmann::json(nullptr);
            }
            return result;
        }

        nlohmann::json object_schema(UObject* object)
        {
            if (!object || !UObject::IsReal(object))
            {
                return nullptr;
            }
            nlohmann::json properties = nlohmann::json::array();
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    object->GetClassPrivate(),
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                properties.push_back(
                    property_description(property, object)
                );
            }
            return {
                {"object", object_description(object)},
                {"properties", std::move(properties)},
            };
        }

        nlohmann::json type_schema(UStruct* type)
        {
            if (!type || !UObject::IsReal(type))
            {
                return nullptr;
            }
            nlohmann::json properties = nlohmann::json::array();
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    type,
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                properties.push_back(
                    property_description(property, nullptr)
                );
            }
            return {
                {"fullName", RC::to_string(type->GetFullName())},
                {"properties", std::move(properties)},
            };
        }

        nlohmann::json function_struct_parameter_schemas(
            UFunction* function
        )
        {
            nlohmann::json schemas = nlohmann::json::object();
            if (!function || !UObject::IsReal(function))
            {
                return schemas;
            }
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    function,
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                if ((property->GetPropertyFlags() & CPF_Parm) == 0)
                {
                    continue;
                }
                auto* struct_property =
                    CastField<FStructProperty>(property);
                if (!struct_property)
                {
                    continue;
                }
                schemas[RC::to_string(property->GetName())] =
                    type_schema(struct_property->GetStruct().Get());
            }
            return schemas;
        }

        nlohmann::json class_schema(const TCHAR* path)
        {
            auto* type = UObjectGlobals::StaticFindObject<UStruct*>(
                nullptr,
                nullptr,
                path
            );
            if (!type || !UObject::IsReal(type))
            {
                return nullptr;
            }
            return type_schema(type);
        }

        nlohmann::json class_function_schema(const TCHAR* path)
        {
            auto* type = UObjectGlobals::StaticFindObject<UStruct*>(
                nullptr,
                nullptr,
                path
            );
            std::vector<nlohmann::json> functions;
            if (!type || !UObject::IsReal(type))
            {
                return functions;
            }
            UObjectGlobals::ForEachUObject(
                [type, &functions](
                    UObject* object,
                    [[maybe_unused]] std::int32_t chunk_index,
                    [[maybe_unused]] std::int32_t object_index
                ) {
                    auto* function = Cast<UFunction>(object);
                    if (
                        function
                        && function->GetOuterPrivate() == type
                    )
                    {
                        functions.push_back(
                            function_description(function)
                        );
                    }
                    return RC::LoopAction::Continue;
                }
            );
            std::ranges::sort(
                functions,
                [](const auto& left, const auto& right) {
                    return left.value("fullName", "")
                        < right.value("fullName", "");
                }
            );
            return nlohmann::json(functions);
        }

        FProperty* find_property(
            UStruct* owner,
            std::initializer_list<const TCHAR*> names
        );

        void* property_value(FProperty* property, void* container);

        UObject* object_property(
            UObject* owner,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !UObject::IsReal(owner))
            {
                return nullptr;
            }
            auto* property = find_property(owner->GetClassPrivate(), names);
            auto* typed_property =
                CastField<FObjectPropertyBase>(property);
            if (!typed_property)
            {
                return nullptr;
            }
            return typed_property->GetObjectPropertyValue(
                property_value(property, owner)
            );
        }

        UObject* object_property_assignable_to(
            UObject* owner,
            UClass* target_class
        )
        {
            if (
                !owner || !UObject::IsReal(owner) || !target_class
                || !UObject::IsReal(target_class)
            )
            {
                return nullptr;
            }
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    owner->GetClassPrivate(),
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                auto* typed_property =
                    CastField<FObjectPropertyBase>(property);
                if (!typed_property)
                {
                    continue;
                }
                auto* value = typed_property->GetObjectPropertyValue(
                    property_value(property, owner)
                );
                if (
                    value && UObject::IsReal(value)
                    && value->IsA(target_class)
                )
                {
                    return value;
                }
            }
            return nullptr;
        }

        bool object_is_within(UObject* object, UObject* owner)
        {
            if (!object || !owner)
            {
                return false;
            }
            for (
                auto* outer = object->GetOuterPrivate();
                outer;
                outer = outer->GetOuterPrivate()
            )
            {
                if (outer == owner)
                {
                    return true;
                }
            }
            return false;
        }

        nlohmann::json describe_instances(std::string_view class_name)
        {
            std::vector<UObject*> instances;
            UObjectGlobals::FindAllOf(class_name, instances);
            nlohmann::json result = nlohmann::json::array();
            for (auto* instance : instances)
            {
                result.push_back(object_description(instance));
            }
            return result;
        }

        nlohmann::json describe_player_controllers()
        {
            std::vector<UObject*> controllers;
            UObjectGlobals::FindAllOf(
                std::string_view{"PalPlayerController"},
                controllers
            );
            nlohmann::json result = nlohmann::json::array();
            for (auto* controller : controllers)
            {
                result.push_back({
                    {"controller", object_description(controller)},
                    {
                        "cheatManager",
                        object_description(
                            object_property(
                                controller,
                                {STR("CheatManager")}
                            )
                        )
                    },
                });
            }
            return result;
        }

        FProperty* find_property(
            UStruct* owner,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner)
            {
                return nullptr;
            }
            for (const auto* name : names)
            {
                if (auto* property =
                        owner->FindProperty(FName(name, FNAME_Find)))
                {
                    return property;
                }
            }
            return nullptr;
        }

        FProperty* require_property(
            UStruct* owner,
            std::initializer_list<const TCHAR*> names,
            const char* purpose
        )
        {
            if (auto* property = find_property(owner, names))
            {
                return property;
            }
            throw std::runtime_error(
                std::string("Palworld no longer exposes the reflected ")
                + purpose + " property."
            );
        }

        void* property_value(FProperty* property, void* container)
        {
            return property->ContainerPtrToValuePtr<void>(container);
        }

        void set_object(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            UObject* value,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* object_property =
                CastField<FObjectPropertyBase>(property);
            if (!object_property)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an object."
                );
            }
            object_property->SetObjectPropertyValue(
                property_value(property, container),
                value
            );
        }

        void set_name(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            const std::string& value,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* name_property = CastField<FNameProperty>(property);
            if (!name_property)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an FName."
                );
            }
            name_property->SetPropertyValueInContainer(
                container,
                FName(RC::ensure_str(value))
            );
        }

        void set_name_array(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            const std::vector<std::string>& values,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* array_property = CastField<FArrayProperty>(property);
            auto* name_property = array_property
                ? CastField<FNameProperty>(
                      array_property->GetInner()
                  )
                : nullptr;
            if (!array_property || !name_property)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an FName array."
                );
            }

            auto* array = static_cast<TArray<FName>*>(
                property_value(property, container)
            );
            array->Empty(
                static_cast<TArray<FName>::SizeType>(values.size())
            );
            for (const auto& value : values)
            {
                array->Add(
                    FName(RC::ensure_str(value))
                );
            }
        }

        void set_integer(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            std::int64_t value,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* numeric_property =
                CastField<FNumericProperty>(property);
            if (!numeric_property || !numeric_property->IsInteger())
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an integer."
                );
            }
            numeric_property->SetIntPropertyValue(
                property_value(property, container),
                value
            );
        }

        void set_float(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            double value,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* numeric_property =
                CastField<FNumericProperty>(property);
            if (!numeric_property || !numeric_property->IsFloatingPoint())
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not floating point."
                );
            }
            numeric_property->SetFloatingPointPropertyValue(
                property_value(property, container),
                value
            );
        }

        void set_bool(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            bool value,
            const char* purpose
        )
        {
            auto* property = require_property(
                owner,
                names,
                purpose
            );
            auto* bool_property = CastField<FBoolProperty>(property);
            if (!bool_property)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not a boolean."
                );
            }
            bool_property->SetPropertyValueInContainer(
                container,
                value
            );
        }

        UObject* object_return(Invocation& invocation)
        {
            auto* property = invocation.function()->GetReturnProperty();
            if (!property)
            {
                throw std::runtime_error(
                    "The reflected Palworld function no longer returns an object."
                );
            }
            auto* object_property =
                CastField<FObjectPropertyBase>(property);
            if (!object_property)
            {
                throw std::runtime_error(
                    "The reflected Palworld function no longer returns an object."
                );
            }
            return object_property->GetObjectPropertyValue(
                property_value(property, invocation.data())
            );
        }

        std::uint64_t numeric_return(Invocation& invocation)
        {
            auto* property = invocation.function()->GetReturnProperty();
            if (!property)
            {
                throw std::runtime_error(
                    "The reflected Palworld function has no result code."
                );
            }
            const auto* value = property_value(
                property,
                invocation.data()
            );
            if (auto* numeric = CastField<FNumericProperty>(property))
            {
                return numeric->GetUnsignedIntPropertyValue(value);
            }
            if (auto* enum_property = CastField<FEnumProperty>(property))
            {
                auto* underlying = enum_property->GetUnderlyingProp();
                if (underlying)
                {
                    return underlying->GetUnsignedIntPropertyValue(value);
                }
            }
            std::uint64_t result = 0;
            std::memcpy(
                &result,
                value,
                std::min<std::size_t>(
                    sizeof(result),
                    static_cast<std::size_t>(property->GetSize())
                )
            );
            return result;
        }

        bool bool_return(Invocation& invocation)
        {
            auto* property = invocation.function()->GetReturnProperty();
            auto* bool_property = property
                ? CastField<FBoolProperty>(property)
                : nullptr;
            if (!bool_property)
            {
                throw std::runtime_error(
                    "The reflected Palworld function no longer returns a boolean."
                );
            }
            return bool_property->GetPropertyValueInContainer(
                invocation.data()
            );
        }

        void copy_struct_value(
            UStruct* source_owner,
            void* source_container,
            std::initializer_list<const TCHAR*> source_names,
            UStruct* destination_owner,
            void* destination_container,
            std::initializer_list<const TCHAR*> destination_names,
            const char* purpose
        )
        {
            auto* source_property = require_property(
                source_owner,
                source_names,
                purpose
            );
            auto* destination_property = require_property(
                destination_owner,
                destination_names,
                purpose
            );
            auto* source_struct =
                CastField<FStructProperty>(source_property);
            auto* destination_struct =
                CastField<FStructProperty>(destination_property);
            if (
                !source_struct || !destination_struct
                || !source_struct->GetStruct().Get()
                || source_struct->GetStruct().Get()
                    != destination_struct->GetStruct().Get()
                || source_property->GetSize()
                    != destination_property->GetSize()
            )
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " layouts are incompatible."
                );
            }
            destination_struct->CopyCompleteValue(
                property_value(
                    destination_property,
                    destination_container
                ),
                property_value(source_property, source_container)
            );
        }

        FStructProperty* single_struct_parameter(
            UFunction* function,
            const char* purpose
        )
        {
            FStructProperty* result = nullptr;
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    function,
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                const auto flags = property->GetPropertyFlags();
                if (
                    (flags & CPF_Parm) == 0
                    || (flags & CPF_ReturnParm) != 0
                )
                {
                    continue;
                }
                auto* struct_property =
                    CastField<FStructProperty>(property);
                if (!struct_property || result)
                {
                    throw std::runtime_error(
                        std::string("The reflected ") + purpose
                        + " must have exactly one struct parameter."
                    );
                }
                result = struct_property;
            }
            if (!result || !result->GetStruct().Get())
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " has no struct parameter."
                );
            }
            return result;
        }

        void validate_delegate_callback(
            FDelegateProperty* delegate_property,
            UFunction* callback,
            const char* purpose
        )
        {
            auto* signature = delegate_property
                ? delegate_property->GetSignatureFunction().Get()
                : nullptr;
            if (!signature || !callback)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " delegate callback is unavailable."
                );
            }
            auto* signature_parameter =
                single_struct_parameter(signature, purpose);
            auto* callback_parameter =
                single_struct_parameter(callback, purpose);
            if (
                signature->GetParmsSize()
                    != callback->GetParmsSize()
                || signature_parameter->GetStruct().Get()
                    != callback_parameter->GetStruct().Get()
                || signature_parameter->GetSize()
                    != callback_parameter->GetSize()
            )
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " delegate signature is incompatible."
                );
            }
        }

        void bind_delegate(
            UFunction* function,
            void* parameters,
            std::initializer_list<const TCHAR*> names,
            UObject* target,
            UFunction* callback,
            const char* purpose
        )
        {
            auto* property = require_property(
                function,
                names,
                purpose
            );
            auto* delegate_property =
                CastField<FDelegateProperty>(property);
            validate_delegate_callback(
                delegate_property,
                callback,
                purpose
            );
            if (!target || !UObject::IsReal(target))
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " delegate target is invalid."
                );
            }
            auto* delegate = static_cast<FScriptDelegate*>(
                property_value(property, parameters)
            );
            delegate->BindUFunction(
                target,
                callback->GetNamePrivate()
            );
            if (
                delegate->GetUObject() != target
                || target->GetFunctionByNameInChain(
                       delegate->GetFunctionName()
                   )
                    != callback
            )
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " delegate did not bind."
                );
            }
        }

        PlayerGuid parse_player_guid(const std::string& value)
        {
            std::string digits;
            digits.reserve(32);
            for (const auto character : value)
            {
                if (
                    character == '-' || character == '{'
                    || character == '}'
                )
                {
                    continue;
                }
                if (
                    !std::isxdigit(
                        static_cast<unsigned char>(character)
                    )
                )
                {
                    throw std::runtime_error(
                        "The selected playerId is not a valid Palworld GUID."
                    );
                }
                digits.push_back(character);
            }
            if (digits.size() != 32)
            {
                throw std::runtime_error(
                    "The selected playerId is not a valid Palworld GUID."
                );
            }

            std::array<std::uint32_t, 4> parts{};
            for (std::size_t index = 0; index < parts.size(); ++index)
            {
                const auto part = digits.substr(index * 8, 8);
                std::size_t parsed = 0;
                const auto value_part = std::stoul(part, &parsed, 16);
                if (parsed != part.size())
                {
                    throw std::runtime_error(
                        "The selected playerId is not a valid Palworld GUID."
                    );
                }
                parts[index] = static_cast<std::uint32_t>(value_part);
            }
            return {parts[0], parts[1], parts[2], parts[3]};
        }

        void set_player_guid(
            UFunction* function,
            void* parameters,
            const PlayerGuid& guid
        )
        {
            auto* property = require_property(
                function,
                {
                    STR("PlayerUId"),
                    STR("PlayerUID"),
                    STR("PlayerId"),
                    STR("PlayerID"),
                    STR("OwnerPlayerUId"),
                    STR("OwnerPlayerUID"),
                },
                "player UID"
            );
            auto* struct_property =
                CastField<FStructProperty>(property);
            if (
                !struct_property
                || property->GetSize()
                    < static_cast<std::int32_t>(sizeof(guid))
            )
            {
                throw std::runtime_error(
                    "The reflected player UID is not an FGuid."
                );
            }
            std::memcpy(
                property_value(property, parameters),
                &guid,
                sizeof(guid)
            );
        }

        PlayerGuid read_player_guid(
            UObject* object,
            std::initializer_list<const TCHAR*> names,
            const char* purpose
        )
        {
            auto* property = require_property(
                object ? object->GetClassPrivate() : nullptr,
                names,
                purpose
            );
            auto* struct_property =
                CastField<FStructProperty>(property);
            auto* structure = struct_property
                ? struct_property->GetStruct().Get()
                : nullptr;
            if (
                !object || !UObject::IsReal(object)
                || !structure
                || RC::to_string(structure->GetFullName())
                    != "ScriptStruct /Script/CoreUObject.Guid"
                || property->GetSize()
                    < static_cast<std::int32_t>(
                        sizeof(PlayerGuid)
                    )
            )
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an FGuid."
                );
            }
            PlayerGuid value{};
            std::memcpy(
                &value,
                property_value(property, object),
                sizeof(value)
            );
            return value;
        }

        std::string player_guid_string(const PlayerGuid& value)
        {
            std::array<char, 33> buffer{};
            std::snprintf(
                buffer.data(),
                buffer.size(),
                "%08X%08X%08X%08X",
                value.a,
                value.b,
                value.c,
                value.d
            );
            return buffer.data();
        }

        std::string read_string(
            UObject* object,
            std::initializer_list<const TCHAR*> names,
            const char* purpose
        )
        {
            auto* property = require_property(
                object ? object->GetClassPrivate() : nullptr,
                names,
                purpose
            );
            auto* string_property =
                CastField<FStrProperty>(property);
            if (!object || !UObject::IsReal(object) || !string_property)
            {
                throw std::runtime_error(
                    std::string("The reflected ") + purpose
                    + " property is not an FString."
                );
            }
            const auto& value =
                string_property->GetPropertyValueInContainer(object);
            return RC::to_string(*value);
        }

        std::optional<std::int64_t> optional_integer(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            if (!property)
            {
                return std::nullopt;
            }
            auto* value = property_value(property, container);
            if (auto* numeric = CastField<FNumericProperty>(property))
            {
                if (!numeric->IsInteger())
                {
                    return std::nullopt;
                }
                return numeric->GetSignedIntPropertyValue(value);
            }
            if (auto* enumeration = CastField<FEnumProperty>(property))
            {
                auto* underlying = enumeration->GetUnderlyingProp();
                return underlying
                    ? std::optional<std::int64_t>(
                          underlying->GetSignedIntPropertyValue(value)
                      )
                    : std::nullopt;
            }
            return std::nullopt;
        }

        std::optional<double> optional_number(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            auto* numeric = property
                ? CastField<FNumericProperty>(property)
                : nullptr;
            if (!numeric || !numeric->IsFloatingPoint())
            {
                return std::nullopt;
            }
            return numeric->GetFloatingPointPropertyValue(
                property_value(property, container)
            );
        }

        nlohmann::json vector_return(Invocation& invocation)
        {
            auto* property = invocation.function()->GetReturnProperty();
            auto* structure = property
                ? CastField<FStructProperty>(property)
                : nullptr;
            auto* type = structure ? structure->GetStruct().Get() : nullptr;
            auto* data = property
                ? property_value(property, invocation.data())
                : nullptr;
            const auto x = optional_number(type, data, {STR("X")});
            const auto y = optional_number(type, data, {STR("Y")});
            const auto z = optional_number(type, data, {STR("Z")});
            if (!x || !y || !z)
            {
                throw std::runtime_error(
                    "The reflected actor-location function no longer returns an FVector."
                );
            }
            return {
                {"x", *x},
                {"y", *y},
                {"z", *z},
            };
        }

        std::optional<bool> optional_bool(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            auto* boolean = property
                ? CastField<FBoolProperty>(property)
                : nullptr;
            return boolean
                ? std::optional<bool>(
                      boolean->GetPropertyValue(
                          property_value(property, container)
                      )
                  )
                : std::nullopt;
        }

        std::optional<std::string> optional_text(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            if (auto* string_property =
                    property ? CastField<FStrProperty>(property) : nullptr)
            {
                const auto& value =
                    string_property->GetPropertyValueInContainer(container);
                return RC::to_string(*value);
            }
            if (auto* name_property =
                    property ? CastField<FNameProperty>(property) : nullptr)
            {
                const auto& value =
                    name_property->GetPropertyValueInContainer(container);
                return RC::to_string(value.ToString());
            }
            return std::nullopt;
        }

        std::optional<PlayerGuid> optional_guid(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            auto* structure = property
                ? CastField<FStructProperty>(property)
                : nullptr;
            if (
                !structure
                || property->GetSize()
                    < static_cast<std::int32_t>(sizeof(PlayerGuid))
            )
            {
                return std::nullopt;
            }
            PlayerGuid value{};
            std::memcpy(
                &value,
                property_value(property, container),
                sizeof(value)
            );
            return value;
        }

        struct StructView
        {
            UStruct* type;
            void* data;
        };

        std::optional<StructView> optional_struct(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            if (!owner || !container)
            {
                return std::nullopt;
            }
            auto* property = find_property(owner, names);
            auto* structure = property
                ? CastField<FStructProperty>(property)
                : nullptr;
            auto* type = structure ? structure->GetStruct().Get() : nullptr;
            return type
                ? std::optional<StructView>(
                      StructView{
                          type,
                          property_value(property, container),
                      }
                  )
                : std::nullopt;
        }

        std::vector<UObject*> optional_object_array(
            UObject* owner,
            std::initializer_list<const TCHAR*> names,
            std::int32_t maximum_count
        )
        {
            if (!owner || !UObject::IsReal(owner))
            {
                return {};
            }
            auto* property = find_property(owner->GetClassPrivate(), names);
            auto* array_property = property
                ? CastField<FArrayProperty>(property)
                : nullptr;
            auto* object_property = array_property
                ? CastField<FObjectPropertyBase>(
                      array_property->GetInner()
                  )
                : nullptr;
            if (!array_property || !object_property)
            {
                return {};
            }
            FScriptArrayHelper array(
                array_property,
                property_value(property, owner)
            );
            const auto count = array.Num();
            if (count < 0 || count > maximum_count)
            {
                throw std::runtime_error(
                    "A reflected Palworld object array has an invalid size."
                );
            }
            std::vector<UObject*> result;
            result.reserve(static_cast<std::size_t>(count));
            for (std::int32_t index = 0; index < count; ++index)
            {
                auto* value = object_property->GetObjectPropertyValue(
                    array.GetElementPtr(index)
                );
                result.push_back(
                    value && UObject::IsReal(value) ? value : nullptr
                );
            }
            return result;
        }

        std::vector<std::string> optional_name_array(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names,
            std::int32_t maximum_count = 128
        )
        {
            if (!owner || !container)
            {
                return {};
            }
            auto* property = find_property(owner, names);
            auto* array_property = property
                ? CastField<FArrayProperty>(property)
                : nullptr;
            auto* name_property = array_property
                ? CastField<FNameProperty>(array_property->GetInner())
                : nullptr;
            if (!array_property || !name_property)
            {
                return {};
            }
            FScriptArrayHelper array(
                array_property,
                property_value(property, container)
            );
            const auto count = array.Num();
            if (count < 0 || count > maximum_count)
            {
                throw std::runtime_error(
                    "A reflected Palworld name array has an invalid size."
                );
            }
            std::vector<std::string> result;
            result.reserve(static_cast<std::size_t>(count));
            for (std::int32_t index = 0; index < count; ++index)
            {
                result.push_back(
                    RC::to_string(
                        name_property
                            ->GetPropertyValue(array.GetElementPtr(index))
                            .ToString()
                    )
                );
            }
            return result;
        }

        void assign_optional(
            nlohmann::json& target,
            const char* key,
            const auto& value
        )
        {
            target[key] = value
                ? nlohmann::json(*value)
                : nlohmann::json(nullptr);
        }

        struct EnumChoice
        {
            std::int64_t value;
            std::string name;
        };

        std::vector<EnumChoice> enum_choices(
            UFunction* function,
            std::initializer_list<const TCHAR*> names
        )
        {
            auto* property = find_property(function, names);
            UEnum* enumeration = nullptr;
            if (auto* enum_property =
                    property ? CastField<FEnumProperty>(property) : nullptr)
            {
                enumeration = enum_property->GetEnum().Get();
            }
            else if (auto* numeric =
                         property
                             ? CastField<FNumericProperty>(property)
                             : nullptr)
            {
                enumeration = numeric->GetIntPropertyEnum();
            }
            if (!enumeration || !UObject::IsReal(enumeration))
            {
                throw std::runtime_error(
                    "The reflected Palworld inventory type enum is unavailable."
                );
            }

            std::vector<std::pair<FName, std::int64_t>> raw;
            enumeration->GetEnumNamesAsVector(raw);
            std::vector<EnumChoice> result;
            std::unordered_set<std::int64_t> seen;
            for (const auto& [name, value] : raw)
            {
                auto label = RC::to_string(name.ToString());
                const auto separator = label.rfind("::");
                if (separator != std::string::npos)
                {
                    label = label.substr(separator + 2);
                }
                const auto lower = lowercase_ascii(label);
                if (
                    label.empty() || lower.ends_with("_max")
                    || lower == "max" || value < 0
                    || !seen.insert(value).second
                )
                {
                    continue;
                }
                result.push_back({value, std::move(label)});
            }
            if (result.empty() || result.size() > 64)
            {
                throw std::runtime_error(
                    "The reflected Palworld inventory type enum is invalid."
                );
            }
            return result;
        }

        void set_enum_value(
            UFunction* function,
            void* parameters,
            std::initializer_list<const TCHAR*> names,
            std::int64_t value
        )
        {
            auto* property = require_property(
                function,
                names,
                "inventory type"
            );
            auto* data = property_value(property, parameters);
            if (auto* enumeration = CastField<FEnumProperty>(property))
            {
                auto* underlying = enumeration->GetUnderlyingProp();
                if (!underlying)
                {
                    throw std::runtime_error(
                        "The reflected inventory type has no underlying integer."
                    );
                }
                underlying->SetIntPropertyValue(data, value);
                return;
            }
            if (auto* numeric = CastField<FNumericProperty>(property))
            {
                numeric->SetIntPropertyValue(data, value);
                return;
            }
            throw std::runtime_error(
                "The reflected inventory type is not an enum."
            );
        }

        UObject* object_parameter(
            UFunction* function,
            void* parameters,
            std::initializer_list<const TCHAR*> names
        )
        {
            auto* property = find_property(function, names);
            auto* object_property = property
                ? CastField<FObjectPropertyBase>(property)
                : nullptr;
            return object_property
                ? object_property->GetObjectPropertyValue(
                      property_value(property, parameters)
                  )
                : nullptr;
        }

        constexpr double runtime_fixed_point_scale{1000.0};

        std::optional<std::int64_t> optional_fixed_point_raw(
            UStruct* owner,
            void* container,
            std::initializer_list<const TCHAR*> names
        )
        {
            const auto structure = optional_struct(owner, container, names);
            return structure
                ? optional_integer(
                      structure->type,
                      structure->data,
                      {STR("Value")}
                  )
                : std::nullopt;
        }

        std::optional<double> fixed_point_display_value(
            const std::optional<std::int64_t>& raw_value
        )
        {
            return raw_value
                ? std::optional<double>{
                      static_cast<double>(*raw_value)
                      / runtime_fixed_point_scale
                  }
                : std::nullopt;
        }

        std::optional<double> positive_fixed_point_display_value(
            const std::optional<std::int64_t>& raw_value
        )
        {
            return raw_value && *raw_value > 0
                ? fixed_point_display_value(raw_value)
                : std::nullopt;
        }

        bool getter_has_no_inputs(UFunction* function)
        {
            if (!function || !UObject::IsReal(function))
            {
                return false;
            }
            for (
                FProperty* property :
                TFieldRange<FProperty>(
                    function,
                    EFieldIterationFlags::IncludeDeprecated
                )
            )
            {
                const auto flags = property->GetPropertyFlags();
                if (
                    (flags & CPF_Parm) != 0
                    && (flags & CPF_ReturnParm) == 0
                )
                {
                    return false;
                }
            }
            return function->GetReturnProperty() != nullptr;
        }

        bool integer_getter_signature(UFunction* function)
        {
            auto* property = getter_has_no_inputs(function)
                ? function->GetReturnProperty()
                : nullptr;
            auto* numeric = property
                ? CastField<FNumericProperty>(property)
                : nullptr;
            return numeric && numeric->IsInteger();
        }

        bool fixed_point_getter_signature(UFunction* function)
        {
            auto* property = getter_has_no_inputs(function)
                ? function->GetReturnProperty()
                : nullptr;
            auto* structure = property
                ? CastField<FStructProperty>(property)
                : nullptr;
            auto* type = structure ? structure->GetStruct().Get() : nullptr;
            auto* value_property = type
                ? find_property(type, {STR("Value")})
                : nullptr;
            auto* numeric = value_property
                ? CastField<FNumericProperty>(value_property)
                : nullptr;
            return numeric && numeric->IsInteger();
        }

        std::optional<std::int64_t> integer_getter_value(
            UObject* context,
            UFunction* function
        )
        {
            auto* property = integer_getter_signature(function)
                ? function->GetReturnProperty()
                : nullptr;
            auto* numeric = property
                ? CastField<FNumericProperty>(property)
                : nullptr;
            if (
                !context || !UObject::IsReal(context) || !numeric
            )
            {
                return std::nullopt;
            }
            Invocation invocation(function);
            invocation.call(context);
            return numeric->GetSignedIntPropertyValue(
                property_value(property, invocation.data())
            );
        }

        std::optional<std::int64_t> fixed_point_getter_raw_value(
            UObject* context,
            UFunction* function
        )
        {
            auto* property = fixed_point_getter_signature(function)
                ? function->GetReturnProperty()
                : nullptr;
            auto* structure = property
                ? CastField<FStructProperty>(property)
                : nullptr;
            auto* type = structure ? structure->GetStruct().Get() : nullptr;
            if (!context || !UObject::IsReal(context) || !type)
            {
                return std::nullopt;
            }
            auto* value_property = find_property(type, {STR("Value")});
            auto* numeric = value_property
                ? CastField<FNumericProperty>(value_property)
                : nullptr;
            if (!numeric)
            {
                return std::nullopt;
            }
            Invocation invocation(function);
            invocation.call(context);
            return numeric->GetSignedIntPropertyValue(
                property_value(
                    value_property,
                    property_value(property, invocation.data())
                )
            );
        }

        std::string string_return(Invocation& invocation)
        {
            auto* property =
                invocation.function()->GetReturnProperty();
            auto* string_property =
                property ? CastField<FStrProperty>(property) : nullptr;
            if (!string_property)
            {
                throw std::runtime_error(
                    "The reflected Palworld function no longer returns an FString."
                );
            }
            const auto& value =
                string_property->GetPropertyValueInContainer(
                    invocation.data()
                );
            auto result = RC::to_string(*value);
            string_property->DestroyValue_InContainer(
                invocation.data()
            );
            return result;
        }

        void set_pal_info(
            UFunction* function,
            void* parameters,
            const std::string& character_id,
            std::int32_t level
        )
        {
            auto* info_property = require_property(
                function,
                {STR("Info")},
                "Pal debug info"
            );
            auto* info_struct_property =
                CastField<FStructProperty>(info_property);
            if (!info_struct_property)
            {
                throw std::runtime_error(
                    "The reflected Pal debug info is not a struct."
                );
            }
            auto* info_data =
                property_value(info_property, parameters);
            auto* info_struct =
                info_struct_property->GetStruct().Get();

            auto* pal_name_property = require_property(
                info_struct,
                {STR("PalName")},
                "Pal name"
            );
            auto* pal_name_struct_property =
                CastField<FStructProperty>(pal_name_property);
            if (!pal_name_struct_property)
            {
                throw std::runtime_error(
                    "The reflected Pal name is not a data-table row name."
                );
            }
            auto* pal_name_data =
                property_value(pal_name_property, info_data);
            set_name(
                pal_name_struct_property->GetStruct().Get(),
                pal_name_data,
                {STR("Key"), STR("RowName")},
                character_id,
                "Pal character ID"
            );
            set_integer(
                info_struct,
                info_data,
                {STR("Level")},
                level,
                "Pal level"
            );
            set_integer(
                info_struct,
                info_data,
                {STR("Rank")},
                0,
                "Pal rank"
            );
        }

    } // namespace

    class PalworldRuntime::Impl
    {
      public:
        ~Impl()
        {
            uninstall_pal_grant_callback_probe();
        }

        void initialize()
        {
            using namespace RC::Unreal;

            utility_cdo = UObjectGlobals::StaticFindObject<UObject*>(
                nullptr,
                nullptr,
                STR("/Script/Pal.Default__PalUtility")
            );
            kismet_system_cdo =
                UObjectGlobals::StaticFindObject<UObject*>(
                    nullptr,
                    nullptr,
                    STR("/Script/Engine.Default__KismetSystemLibrary")
                );
            is_server = find_function(
                STR("/Script/Engine.KismetSystemLibrary:IsServer")
            );
            is_dedicated_server = find_function(
                STR(
                    "/Script/Engine.KismetSystemLibrary:"
                    "IsDedicatedServer"
                )
            );
            is_standalone = find_function(
                STR("/Script/Engine.KismetSystemLibrary:IsStandalone")
            );
            get_player_controller = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetPlayerControllerByPlayerUId"
                )
            );
            get_actor_location = find_function(
                STR("/Script/Engine.Actor:K2_GetActorLocation")
            );
            get_character_hp = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetHP")
            );
            get_character_max_hp = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetMaxHP")
            );
            get_individual_max_hp_with_buff = find_function(
                STR("/Script/Pal.PalIndividualCharacterParameter:GetMaxHP_withBuff")
            );
            get_individual_max_hp = find_function(
                STR(
                    "/Script/Pal.PalIndividualCharacterParameter:GetMaxHP"
                )
            );
            get_character_max_sp = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetMaxSP")
            );
            get_character_attack = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetShotAttack")
            );
            get_character_defense = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetDefense")
            );
            get_character_craft_speed = find_function(
                STR("/Script/Pal.PalCharacterParameterComponent:GetCraftSpeed")
            );
            get_character_manager = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetCharacterManager"
                )
            );
            get_all_player_states = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetAllPlayerStates"
                )
            );
            get_guild_name = find_function(
                STR(
                    "/Script/Pal.PalGroupGuildBase:"
                    "GetGuildName"
                )
            );
            get_inventory = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetInventoryDataByPlayerUID"
                )
            );
            get_guild = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetGuildByPlayerUId"
                )
            );
            get_pal_storage = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetPalStorageDataByPlayerUID"
                )
            );
            try_get_inventory_container = find_function(
                STR(
                    "/Script/Pal.PalPlayerInventoryData:"
                    "TryGetContainerFromInventoryType"
                )
            );
            try_get_individual_parameter = find_function(
                STR(
                    "/Script/Pal.PalIndividualCharacterHandle:"
                    "TryGetIndividualParameter"
                )
            );
            get_all_party_handles = find_function(
                STR(
                    "/Script/Pal.PalOtomoHolderComponentBase:"
                    "GetAllIndividualHandle"
                )
            );
            get_individual_parameter_by_actor = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetIndividualCharacterParameterByActor"
                )
            );
            add_item = find_function(
                STR(
                    "/Script/Pal.PalPlayerInventoryData:"
                    "AddItem_ServerInternal"
                )
            );
            add_experience = find_function(
                STR(
                    "/Script/Pal.PalPlayerController:"
                    "Debug_AddPlayerExp_ToServer"
                )
            );
            enable_cheats = find_function(
                STR("/Script/Engine.PlayerController:EnableCheats")
            );
            init_cheat_manager = find_function(
                STR("/Script/Engine.CheatManager:InitCheatManager")
            );
            local_player_setup_complete = find_function(
                STR(
                    "/Script/Pal.PalCheatManager:"
                    "OnLocalPlayerSetupComplete"
                )
            );
            cheat_add_experience = find_function(
                STR("/Script/Pal.PalCheatManager:AddPlayerExp")
            );
            database_add_experience = find_function(
                STR(
                    "/Script/Pal.PalExpDatabase:"
                    "AddExpValue_forPlayerParty_Server"
                )
            );
            capture_pal = find_function(
                STR(
                    "/Script/Pal.PalPlayerState:"
                    "Debug_CaptureNewMonsterByDebugOtomoInfo_ToServer"
                )
            );
            cheat_capture_pal = find_function(
                STR(
                    "/Script/Pal.PalCheatManager:"
                    "CaptureNewMonster"
                )
            );
            spawn_pal = find_function(
                STR(
                    "/Script/Pal.PalPlayerState:"
                    "RequestSpawnMonsterForPlayer"
                )
            );
            initialize_character = find_function(
                STR(
                    "/Script/Pal.PalUtility:"
                    "GetInitializedCharacterSaveParemter"
                )
            );
            create_individual = find_function(
                STR(
                    "/Script/Pal.PalCharacterManager:"
                    "CreateIndividual"
                )
            );
            get_individual_id = find_function(
                STR(
                    "/Script/Pal.PalIndividualCharacterHandle:"
                    "GetIndividualID"
                )
            );
            attach_granted_individual = find_function(
                STR(
                    "/Script/Pal.PalPlayerState:"
                    "OnCreatedGrantedIndividualHandle_ServerInternal"
                )
            );
            install_pal_grant_callback_probe();
            find_empty_pal_slot = find_function(
                STR(
                    "/Script/Pal.PalIndividualCharacterContainer:"
                    "FindEmptySlot"
                )
            );
            find_pal_slot_by_handle = find_function(
                STR(
                    "/Script/Pal.PalIndividualCharacterContainer:"
                    "FindByHandle"
                )
            );
            inventory_available = validate_inventory();
            experience_available = validate_database_experience();
            player_list_available = validate_player_list();
            pal_available = validate_pal();
            guild_list_available =
                player_list_available && get_guild_name;
            player_details_available =
                player_list_available && validate_player_lookup();
            player_runtime_stats_available =
                fixed_point_getter_signature(get_character_hp)
                && (
                    fixed_point_getter_signature(get_character_max_hp)
                    || fixed_point_getter_signature(
                        get_individual_max_hp_with_buff
                    )
                    || integer_getter_signature(get_individual_max_hp)
                )
                && fixed_point_getter_signature(get_character_max_sp)
                && integer_getter_signature(get_character_attack)
                && integer_getter_signature(get_character_defense)
                && integer_getter_signature(get_character_craft_speed);
            player_location_available =
                player_details_available && get_actor_location;
            inventory_read_available =
                player_details_available && get_inventory
                && try_get_inventory_container;
            pal_list_available =
                player_details_available && get_pal_storage
                && try_get_individual_parameter;
            party_list_available =
                player_details_available && validate_party_list();
            map_read_available =
                player_location_available && guild_list_available;

            auto current_status = nlohmann::json{
                {"inventoryGrant", inventory_available},
                {"playerExperienceAdd", experience_available},
                {"palGrant", pal_available},
                {
                    "palGrantValidationError",
                    pal_validation_error.empty()
                        ? nlohmann::json(nullptr)
                        : nlohmann::json(pal_validation_error)
                },
                {"playerList", player_list_available},
                {"guildList", guild_list_available},
                {"playerDetails", player_details_available},
                {"playerRuntimeStats", player_runtime_stats_available},
                {"inventoryRead", inventory_read_available},
                {"palList", pal_list_available},
                {"partyList", party_list_available},
                {"playerLocation", player_location_available},
                {"mapRead", map_read_available},
                {
                    "playerRuntimeStatReflection",
                    {
                        {"getHp", function_description(get_character_hp)},
                        {
                            "getMaxHp",
                            function_description(get_character_max_hp)
                        },
                        {
                            "getIndividualMaxHpWithBuff",
                            function_description(
                                get_individual_max_hp_with_buff
                            )
                        },
                        {
                            "getIndividualMaxHp",
                            function_description(get_individual_max_hp)
                        },
                        {
                            "getMaxSp",
                            function_description(get_character_max_sp)
                        },
                        {
                            "getAttack",
                            function_description(get_character_attack)
                        },
                        {
                            "getDefense",
                            function_description(get_character_defense)
                        },
                        {
                            "getCraftSpeed",
                            function_description(get_character_craft_speed)
                        },
                    },
                },
                {
                    "palGrantReflection",
                    {
                        {"function", function_description(capture_pal)},
                        {
                            "getCharacterManager",
                            function_description(get_character_manager)
                        },
                        {
                            "structParameters",
                            function_struct_parameter_schemas(capture_pal)
                        },
                        {
                            "captureMatches",
                            find_functions_containing(
                                "CaptureNewMonster"
                            )
                        },
                        {
                            "createHandleMatches",
                            find_functions_containing(
                                "CreatePlayerIndividualHandle_InServer"
                            )
                        },
                        {
                            "grantedHandleMatches",
                            find_functions_containing(
                                "GrantedIndividualHandle"
                            )
                        },
                        {
                            "addHandleMatches",
                            find_functions_containing(
                                "AddIndividualHandle"
                            )
                        },
                        {
                            "createIndividualMatches",
                            find_functions_containing(
                                "CreateIndividual"
                            )
                        },
                        {
                            "captureHandleMatches",
                            find_functions_containing(
                                "CaptureCharacterHandle"
                            )
                        },
                        {
                            "temporaryHandleMatches",
                            find_functions_containing(
                                "TryCreateIndividualHandleTemporarily"
                            )
                        },
                        {
                            "palStorageMatches",
                            find_functions_containing(
                                "GetPalStorage"
                            )
                        },
                        {
                            "storageClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalPlayerDataPalStorage"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalPlayerDataPalStorage"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "containerClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterContainer"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterContainer"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "slotClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterSlot"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterSlot"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "managerClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalCharacterManager"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalCharacterManager"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "containerManagerClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalCharacterContainerManager"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalCharacterContainerManager"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "networkContainerClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalNetworkCharacterContainerComponent"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalNetworkCharacterContainerComponent"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "individualSaveParameter",
                            class_schema(
                                STR(
                                    "/Script/Pal."
                                    "PalIndividualCharacterSaveParameter"
                                )
                            )
                        },
                        {
                            "containerUpdateInfo",
                            class_schema(
                                STR(
                                    "/Script/Pal."
                                    "PalCharacterContainerUpdateInfo"
                                )
                            )
                        },
                        {
                            "slotUpdateInfo",
                            class_schema(
                                STR(
                                    "/Script/Pal."
                                    "PalIndividualCharacterSlotUpdateInfo"
                                )
                            )
                        },
                        {
                            "individualHandleClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterHandle"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterHandle"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "individualParameterClass",
                            {
                                {
                                    "properties",
                                    class_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterParameter"
                                        )
                                    )
                                },
                                {
                                    "functions",
                                    class_function_schema(
                                        STR(
                                            "/Script/Pal."
                                            "PalIndividualCharacterParameter"
                                        )
                                    )
                                },
                            },
                        },
                        {
                            "instanceIdType",
                            class_schema(
                                STR("/Script/Pal.PalInstanceID")
                            )
                        },
                        {
                            "characterSlotIdType",
                            class_schema(
                                STR("/Script/Pal.PalCharacterSlotId")
                            )
                        },
                        {
                            "containerIdType",
                            class_schema(
                                STR("/Script/Pal.PalContainerId")
                            )
                        },
                        {
                            "initializedOtomoMatches",
                            find_functions_containing(
                                "GetInitializedOtomoSaveParameter"
                            )
                        },
                        {
                            "initializedCharacterMatches",
                            find_functions_containing(
                                "GetInitializedCharacterSaveParemter"
                            )
                        },
                    },
                },
            };
            std::lock_guard lock(status_mutex);
            runtime_status = std::move(current_status);
        }

        void refresh_instance_mode(bool dedicated_process)
        {
            using namespace RC::Unreal;

            if (dedicated_process)
            {
                set_instance_mode("dedicated_server", true, {});
                return;
            }

            auto* context = world_context(true);
            if (!context)
            {
                set_instance_mode(
                    "loading",
                    false,
                    "No active PalPlayerController is available."
                );
                return;
            }

            try
            {
                auto invoke_mode_query = [this, context](
                    UFunction* function
                ) -> std::optional<bool> {
                    if (
                        !function || !kismet_system_cdo
                        || !UObject::IsReal(kismet_system_cdo)
                    )
                    {
                        return std::nullopt;
                    }
                    Invocation invocation(function);
                    set_object(
                        function,
                        invocation.data(),
                        {STR("WorldContextObject")},
                        context,
                        "world context"
                    );
                    invocation.call(kismet_system_cdo);
                    return bool_return(invocation);
                };

                const auto dedicated =
                    invoke_mode_query(is_dedicated_server);
                const auto standalone =
                    invoke_mode_query(is_standalone);
                auto server = invoke_mode_query(is_server);

                if (!server)
                {
                    auto* role = find_property(
                        context->GetClassPrivate(),
                        {STR("Role"), STR("LocalRole")}
                    );
                    const auto* role_value = role
                        ? property_value(role, context)
                        : nullptr;
                    if (
                        auto* numeric =
                            role ? CastField<FNumericProperty>(role) : nullptr
                    )
                    {
                        server =
                            numeric->GetUnsignedIntPropertyValue(role_value)
                            == 3;
                    }
                    else if (
                        auto* enumeration =
                            role ? CastField<FEnumProperty>(role) : nullptr
                    )
                    {
                        auto* underlying = enumeration->GetUnderlyingProp();
                        if (underlying)
                        {
                            server =
                                underlying
                                    ->GetUnsignedIntPropertyValue(role_value)
                                == 3;
                        }
                    }
                }

                if (dedicated.value_or(false))
                {
                    set_instance_mode("dedicated_server", true, {});
                }
                else if (!server)
                {
                    set_instance_mode(
                        "unknown",
                        false,
                        "Palworld authority could not be determined."
                    );
                }
                else if (!*server)
                {
                    set_instance_mode(
                        "client",
                        false,
                        "Only a single-player world or the multiplayer host can use live management."
                    );
                }
                else if (standalone.value_or(false))
                {
                    set_instance_mode("single_player", true, {});
                }
                else if (standalone)
                {
                    set_instance_mode("listen_server", true, {});
                }
                else
                {
                    set_instance_mode("host_or_single", true, {});
                }
            }
            catch (const std::exception& error)
            {
                set_instance_mode("unknown", false, error.what());
            }
            catch (...)
            {
                set_instance_mode(
                    "unknown",
                    false,
                    "Palworld authority detection failed unexpectedly."
                );
            }
        }

        bool inventory_ready() const
        {
            return inventory_available;
        }

        bool experience_ready() const
        {
            return experience_available;
        }

        bool pal_ready() const
        {
            return pal_available;
        }

        bool player_list_ready() const
        {
            return player_list_available;
        }

        bool guild_list_ready() const
        {
            return guild_list_available;
        }

        bool player_details_ready() const
        {
            return player_details_available;
        }

        bool inventory_read_ready() const
        {
            return inventory_read_available;
        }

        bool pal_list_ready() const
        {
            return pal_list_available;
        }

        bool map_read_ready() const
        {
            return map_read_available;
        }

        bool authoritative() const
        {
            return instance_authoritative.load();
        }

        std::string instance_mode() const
        {
            std::lock_guard lock(instance_mutex);
            return current_instance_mode;
        }

        nlohmann::json status() const
        {
            std::lock_guard lock(status_mutex);
            auto result = runtime_status;
            result["palGrantCallbackDiagnostics"] =
                pal_grant_callback_diagnostics();
            {
                std::lock_guard instance_lock(instance_mutex);
                result["instanceMode"] = current_instance_mode;
                result["authoritative"] =
                    instance_authoritative.load();
                result["authorityError"] =
                    instance_error.empty()
                        ? nlohmann::json(nullptr)
                        : nlohmann::json(instance_error);
            }
            return result;
        }

        void install_pal_grant_callback_probe()
        {
            using namespace RC::Unreal;

            if (!attach_granted_individual)
            {
                return;
            }
            {
                std::lock_guard lock(pal_grant_diagnostics_mutex);
                if (
                    pal_grant_callback_hook_id
                    && pal_grant_callback_hook_target
                        == attach_granted_individual
                )
                {
                    return;
                }
            }
            uninstall_pal_grant_callback_probe();

            try
            {
                const auto callback_id =
                    attach_granted_individual->RegisterPreHook(
                        [this](
                            UnrealScriptFunctionCallableContext& context,
                            void*
                        ) {
                            observe_pal_grant_callback(context.Context);
                        }
                    );
                std::lock_guard lock(pal_grant_diagnostics_mutex);
                pal_grant_callback_hook_target =
                    attach_granted_individual;
                pal_grant_callback_hook_id = callback_id;
                pal_grant_callback_hook_error.clear();
            }
            catch (const std::exception& error)
            {
                std::lock_guard lock(pal_grant_diagnostics_mutex);
                pal_grant_callback_hook_target = nullptr;
                pal_grant_callback_hook_id.reset();
                pal_grant_callback_hook_error = error.what();
            }
        }

        void uninstall_pal_grant_callback_probe()
        {
            RC::Unreal::UFunction* target = nullptr;
            std::optional<RC::Unreal::CallbackId> callback_id;
            {
                std::lock_guard lock(pal_grant_diagnostics_mutex);
                target = pal_grant_callback_hook_target;
                callback_id = pal_grant_callback_hook_id;
                pal_grant_callback_hook_target = nullptr;
                pal_grant_callback_hook_id.reset();
            }
            if (target && callback_id)
            {
                target->UnregisterHook(*callback_id);
            }
        }

        std::uint64_t begin_pal_grant_callback_probe(
            RC::Unreal::UObject* expected_player_state,
            const std::string& player_id
        )
        {
            std::lock_guard lock(pal_grant_diagnostics_mutex);
            const auto sequence = ++pal_grant_sequence;
            pal_grant_expected_player_state = expected_player_state;
            pal_grant_expected_player_state_name =
                expected_player_state
                    ? RC::to_string(expected_player_state->GetFullName())
                    : std::string{};
            pal_grant_player_id = player_id;
            return sequence;
        }

        void observe_pal_grant_callback(
            RC::Unreal::UObject* callback_context
        )
        {
            std::lock_guard lock(pal_grant_diagnostics_mutex);
            ++pal_grant_callback_count;
            pal_grant_last_callback_sequence = pal_grant_sequence;
            pal_grant_last_callback_context_matches =
                callback_context == pal_grant_expected_player_state;
            pal_grant_last_callback_context_name =
                callback_context
                    ? RC::to_string(callback_context->GetFullName())
                    : std::string{};
        }

        nlohmann::json pal_grant_callback_diagnostics(
            std::optional<std::uint64_t> sequence = std::nullopt
        ) const
        {
            std::lock_guard lock(pal_grant_diagnostics_mutex);
            const auto inspected_sequence =
                sequence.value_or(pal_grant_sequence);
            const auto observed =
                inspected_sequence != 0
                && pal_grant_last_callback_sequence
                    == inspected_sequence;
            return {
                {
                    "hookInstalled",
                    pal_grant_callback_hook_id.has_value()
                },
                {
                    "hookError",
                    pal_grant_callback_hook_error.empty()
                        ? nlohmann::json(nullptr)
                        : nlohmann::json(
                              pal_grant_callback_hook_error
                          )
                },
                {"totalCallbacks", pal_grant_callback_count},
                {"grantSequence", inspected_sequence},
                {"playerId", pal_grant_player_id},
                {
                    "expectedPlayerState",
                    pal_grant_expected_player_state_name.empty()
                        ? nlohmann::json(nullptr)
                        : nlohmann::json(
                              pal_grant_expected_player_state_name
                          )
                },
                {"callbackObserved", observed},
                {
                    "callbackContext",
                    observed
                        && !pal_grant_last_callback_context_name.empty()
                        ? nlohmann::json(
                              pal_grant_last_callback_context_name
                          )
                        : nlohmann::json(nullptr)
                },
                {
                    "callbackContextMatchedTarget",
                    observed
                        ? nlohmann::json(
                              pal_grant_last_callback_context_matches
                          )
                        : nlohmann::json(nullptr)
                },
            };
        }

        nlohmann::json players()
        {
            using namespace RC::Unreal;

            if (!player_list_available)
            {
                throw std::runtime_error(
                    "The live player-list capability is unavailable for this game build."
                );
            }
            auto* context = world_context();
            if (!context)
            {
                return nlohmann::json::array();
            }

            Invocation invocation(get_all_player_states);
            set_object(
                get_all_player_states,
                invocation.data(),
                {STR("WorldContextObject")},
                context,
                "world context"
            );
            auto* states_property = require_property(
                get_all_player_states,
                {STR("OutPlayerStates")},
                "player-state list"
            );
            auto* array_property =
                CastField<FArrayProperty>(states_property);
            auto* inner_object_property = array_property
                ? CastField<FObjectPropertyBase>(
                      array_property->GetInner()
                  )
                : nullptr;
            auto* player_state_class = inner_object_property
                ? inner_object_property->GetPropertyClass().Get()
                : nullptr;
            if (!array_property || !player_state_class)
            {
                throw std::runtime_error(
                    "The reflected player-state list is not an object array."
                );
            }

            invocation.call(utility_cdo);
            auto* states = static_cast<TArray<UObject*>*>(
                property_value(states_property, invocation.data())
            );
            const auto state_count = states->Num();
            if (state_count < 0 || state_count > 1024)
            {
                states_property->DestroyValue_InContainer(
                    invocation.data()
                );
                throw std::runtime_error(
                    "The reflected player-state list has an invalid size."
                );
            }

            nlohmann::json result = nlohmann::json::array();
            try
            {
                for (
                    TArray<UObject*>::SizeType index = 0;
                    index < state_count;
                    ++index
                )
                {
                    auto* state = (*states)[index];
                    if (
                        !state || !UObject::IsReal(state)
                        || !state->IsA(player_state_class)
                    )
                    {
                        continue;
                    }
                    const auto uid = player_guid_string(
                        read_player_guid(
                            state,
                            {STR("PlayerUId")},
                            "player UID"
                        )
                    );
                    auto name = read_string(
                        state,
                        {STR("AccountName")},
                        "account name"
                    );
                    if (name.empty())
                    {
                        name = uid;
                    }
                    nlohmann::json player{
                        {"playerId", uid},
                        {"player_uid", uid},
                        {"name", std::move(name)},
                        {"online", true},
                        {"source", "runtime"},
                    };

                    auto* guild = object_property(
                        state,
                        {STR("GuildBelongTo")}
                    );
                    if (guild && UObject::IsReal(guild))
                    {
                        try
                        {
                            const auto guild_uid =
                                player_guid_string(
                                    read_player_guid(
                                        guild,
                                        {
                                            STR("GroupId"),
                                            STR("GroupID"),
                                            STR("ID"),
                                            STR("Id"),
                                        },
                                        "guild ID"
                                    )
                                );
                            player["guildId"] = guild_uid;
                            player["guild_id"] = guild_uid;
                        }
                        catch (...)
                        {
                        }
                        if (get_guild_name)
                        {
                            try
                            {
                                Invocation guild_name(
                                    get_guild_name
                                );
                                guild_name.call(guild);
                                player["guildName"] =
                                    string_return(guild_name);
                            }
                            catch (...)
                            {
                            }
                        }
                    }
                    assign_optional(
                        player,
                        "level",
                        optional_integer(
                            state->GetClassPrivate(),
                            state,
                            {STR("Level"), STR("PlayerLevel")}
                        )
                    );
                    if (player_location_available)
                    {
                        try
                        {
                            auto* controller = player_controller(uid);
                            auto* pawn = object_property(
                                controller,
                                {
                                    STR("Pawn"),
                                    STR("AcknowledgedPawn"),
                                    STR("Character"),
                                }
                            );
                            if (!pawn || !UObject::IsReal(pawn))
                            {
                                throw std::runtime_error(
                                    "The online player has no live pawn."
                                );
                            }
                            Invocation location(get_actor_location);
                            location.call(pawn);
                            auto position = vector_return(location);
                            player["position"] = position;
                            player["x"] = position["x"];
                            player["y"] = position["y"];
                            player["z"] = position["z"];
                            player["positionStatus"] = "available";
                            player["positionSource"] = "pawn";
                        }
                        catch (const std::exception& error)
                        {
                            player["positionStatus"] = "unavailable";
                            player["positionError"] = error.what();
                        }
                        catch (...)
                        {
                            player["positionStatus"] = "unavailable";
                            player["positionError"] =
                                "The live player position could not be read.";
                        }
                    }
                    result.push_back(std::move(player));
                }
            }
            catch (...)
            {
                states_property->DestroyValue_InContainer(
                    invocation.data()
                );
                throw;
            }
            states_property->DestroyValue_InContainer(
                invocation.data()
            );
            return result;
        }

        nlohmann::json guilds()
        {
            if (!guild_list_available)
            {
                throw std::runtime_error(
                    "The live guild-list capability is unavailable for this game build."
                );
            }

            std::unordered_map<std::string, nlohmann::json> guild_by_id;
            std::vector<UObject*> loaded_guilds;
            UObjectGlobals::FindAllOf(
                std::string_view{"PalGroupGuildBase"},
                loaded_guilds
            );
            constexpr std::string_view zero_guid{
                "00000000000000000000000000000000"
            };
            for (auto* guild : loaded_guilds)
            {
                if (!guild || !UObject::IsReal(guild))
                {
                    continue;
                }
                const auto guild_id = optional_guid(
                    guild->GetClassPrivate(),
                    guild,
                    {
                        STR("ID"),
                        STR("Id"),
                        STR("GroupId"),
                        STR("GroupID"),
                    }
                );
                if (!guild_id)
                {
                    continue;
                }
                const auto id = player_guid_string(*guild_id);
                if (id == zero_guid)
                {
                    continue;
                }

                auto name = optional_text(
                    guild->GetClassPrivate(),
                    guild,
                    {STR("GuildName"), STR("GroupName")}
                ).value_or(std::string{});
                if (name.empty() && get_guild_name)
                {
                    try
                    {
                        Invocation invocation(get_guild_name);
                        invocation.call(guild);
                        name = string_return(invocation);
                    }
                    catch (...)
                    {
                    }
                }
                guild_by_id.insert_or_assign(
                    id,
                    nlohmann::json{
                        {"guildId", id},
                        {"guild_id", id},
                        {"name", std::move(name)},
                        {"onlineMemberCount", 0},
                        {"onlineMembers", nlohmann::json::array()},
                        {"source", "runtime"},
                    }
                );
            }

            const auto online_players = players();
            for (const auto& player : online_players)
            {
                const auto guild_id = player.value("guildId", "");
                if (guild_id.empty())
                {
                    continue;
                }
                auto [match, inserted] = guild_by_id.try_emplace(
                    guild_id,
                    nlohmann::json{
                        {"guildId", guild_id},
                        {"guild_id", guild_id},
                        {"name", player.value("guildName", "")},
                        {"onlineMemberCount", 0},
                        {"onlineMembers", nlohmann::json::array()},
                        {"source", "runtime"},
                    }
                );
                auto& guild = match->second;
                if (
                    guild.value("name", "").empty()
                    && player.contains("guildName")
                )
                {
                    guild["name"] = player["guildName"];
                }
                guild["onlineMembers"].push_back({
                    {"playerId", player.value("playerId", "")},
                    {"name", player.value("name", "")},
                });
                guild["onlineMemberCount"] =
                    guild["onlineMembers"].size();
            }

            std::vector<nlohmann::json> result;
            result.reserve(guild_by_id.size());
            for (auto& [id, guild] : guild_by_id)
            {
                result.emplace_back(std::move(guild));
            }
            std::ranges::sort(
                result,
                [](const auto& left, const auto& right) {
                    const auto left_name = left.value("name", "");
                    const auto right_name = right.value("name", "");
                    return left_name == right_name
                        ? left.value("guildId", "")
                            < right.value("guildId", "")
                        : left_name < right_name;
                }
            );
            return nlohmann::json(result);
        }

        nlohmann::json map_snapshot()
        {
            if (!map_read_available)
            {
                throw std::runtime_error(
                    "The live map capability is unavailable for this game build."
                );
            }
            return {
                {"live", true},
                {"authoritative", instance_authoritative.load()},
                {"instanceMode", instance_mode()},
                {"coordinateSystem", "UnrealWorld"},
                {"players", players()},
                {"guilds", guilds()},
                {
                    "source",
                    {
                        {"players", "runtime"},
                        {"positions", "playerPawn"},
                        {"guilds", "runtime"},
                    }
                },
            };
        }

        nlohmann::json player_details(const std::string& player_id)
        {
            if (!player_details_available)
            {
                throw std::runtime_error(
                    "The live player-detail capability is unavailable for this game build."
                );
            }

            nlohmann::json player = nullptr;
            for (const auto& candidate : players())
            {
                if (candidate.value("playerId", "") == player_id)
                {
                    player = candidate;
                    break;
                }
            }
            if (player.is_null())
            {
                throw std::runtime_error(
                    "The selected player is not online in this game instance."
                );
            }

            auto* controller = player_controller(player_id);
            auto* player_state = object_property(
                controller,
                {STR("PlayerState")}
            );
            auto* pawn = object_property(
                controller,
                {
                    STR("Pawn"),
                    STR("AcknowledgedPawn"),
                    STR("Character"),
                }
            );
            auto* parameter = individual_parameter_for_actor(pawn);
            if (parameter)
            {
                const auto character = character_snapshot(parameter);
                for (
                    const auto* key :
                    {
                        "characterId",
                        "nickname",
                        "level",
                        "experience",
                        "rank",
                        "hp",
                        "maxHp",
                        "hpRaw",
                        "maxHpRaw",
                        "unusedStatusPoints",
                    }
                )
                {
                    if (character.contains(key))
                    {
                        player[key] = character[key];
                    }
                }
            }
            else
            {
                player["detailsStatus"] = "partial";
            }
            const auto runtime_stats = runtime_player_stats(pawn, parameter);
            for (
                const auto* key :
                {"hp", "maxHp", "hpRaw", "maxHpRaw"}
            )
            {
                if (
                    runtime_stats.contains(key)
                    && !runtime_stats[key].is_null()
                )
                {
                    player[key] = runtime_stats[key];
                }
            }
            player["attributes"] = runtime_stats["attributes"];
            player["attributesStatus"] = runtime_stats["status"];
            if (runtime_stats["status"] != "available")
            {
                player["detailsStatus"] = "partial";
            }
            if (player_state && UObject::IsReal(player_state))
            {
                assign_optional(
                    player,
                    "startPlayTimeRaw",
                    optional_integer(
                        player_state->GetClassPrivate(),
                        player_state,
                        {STR("StartPlayTime")}
                    )
                );
            }

            return {
                {"player", std::move(player)},
                {
                    "source",
                    {
                        {"kind", "runtime"},
                        {"authoritative", authoritative()},
                        {"instanceMode", instance_mode()},
                    },
                },
            };
        }

        std::optional<std::int64_t> individual_max_hp_raw_value(
            UObject* individual_parameter
        )
        {
            const auto max_hp_with_buff_raw =
                fixed_point_getter_raw_value(
                    individual_parameter,
                    get_individual_max_hp_with_buff
                );
            if (max_hp_with_buff_raw && *max_hp_with_buff_raw > 0)
            {
                return max_hp_with_buff_raw;
            }

            const auto max_hp = integer_getter_value(
                individual_parameter,
                get_individual_max_hp
            );
            if (!max_hp || *max_hp <= 0)
            {
                return std::nullopt;
            }
            return *max_hp
                * static_cast<std::int64_t>(runtime_fixed_point_scale);
        }

        nlohmann::json runtime_player_stats(
            UObject* pawn,
            UObject* individual_parameter
        )
        {
            auto attributes = nlohmann::json{
                {"stamina", nullptr},
                {"attack", nullptr},
                {"defense", nullptr},
                {"craftSpeed", nullptr},
            };
            auto result = nlohmann::json{
                {"status", "partial"},
                {"attributes", attributes},
            };
            auto* parameter_component = object_property(
                pawn,
                {
                    STR("CharacterParameterComponent"),
                    STR("ParameterComponent"),
                }
            );
            if (
                !parameter_component
                || !UObject::IsReal(parameter_component)
            )
            {
                return result;
            }

            const auto hp_raw = fixed_point_getter_raw_value(
                parameter_component,
                get_character_hp
            );
            auto max_hp_raw = fixed_point_getter_raw_value(
                parameter_component,
                get_character_max_hp
            );
            if (!max_hp_raw || *max_hp_raw <= 0)
            {
                max_hp_raw = individual_max_hp_raw_value(
                    individual_parameter
                );
            }
            const auto max_sp_raw = fixed_point_getter_raw_value(
                parameter_component,
                get_character_max_sp
            );
            const auto attack = integer_getter_value(
                parameter_component,
                get_character_attack
            );
            const auto defense = integer_getter_value(
                parameter_component,
                get_character_defense
            );
            const auto craft_speed = integer_getter_value(
                parameter_component,
                get_character_craft_speed
            );

            assign_optional(result, "hpRaw", hp_raw);
            assign_optional(
                result,
                "hp",
                fixed_point_display_value(hp_raw)
            );
            assign_optional(result, "maxHpRaw", max_hp_raw);
            assign_optional(
                result,
                "maxHp",
                positive_fixed_point_display_value(max_hp_raw)
            );
            assign_optional(
                attributes,
                "stamina",
                positive_fixed_point_display_value(max_sp_raw)
            );
            assign_optional(attributes, "attack", attack);
            assign_optional(attributes, "defense", defense);
            assign_optional(attributes, "craftSpeed", craft_speed);
            result["attributes"] = std::move(attributes);
            if (
                hp_raw && max_hp_raw && *max_hp_raw > 0
                && max_sp_raw && *max_sp_raw > 0
                && attack && defense && craft_speed
            )
            {
                result["status"] = "available";
            }
            return result;
        }

        UObject* individual_parameter_for_actor(UObject* actor)
        {
            if (!actor || !UObject::IsReal(actor))
            {
                return nullptr;
            }
            if (
                get_individual_parameter_by_actor && utility_cdo
                && UObject::IsReal(utility_cdo)
            )
            {
                try
                {
                    Invocation invocation(
                        get_individual_parameter_by_actor
                    );
                    set_object(
                        get_individual_parameter_by_actor,
                        invocation.data(),
                        {
                            STR("Actor"),
                            STR("Character"),
                            STR("Player"),
                        },
                        actor,
                        "player actor"
                    );
                    invocation.call(utility_cdo);
                    auto* result = object_return(invocation);
                    if (result && UObject::IsReal(result))
                    {
                        return result;
                    }
                }
                catch (...)
                {
                }
            }
            auto* direct = object_property(
                actor,
                {
                    STR("IndividualParameter"),
                    STR("Parameter"),
                }
            );
            return direct && UObject::IsReal(direct) ? direct : nullptr;
        }

        nlohmann::json character_snapshot(UObject* parameter)
        {
            if (!parameter || !UObject::IsReal(parameter))
            {
                return nlohmann::json::object();
            }
            UStruct* source_type = parameter->GetClassPrivate();
            void* source_data = parameter;
            if (
                const auto save = optional_struct(
                    source_type,
                    source_data,
                    {
                        STR("SaveParameter"),
                        STR("SaveParameterMirror"),
                    }
                )
            )
            {
                source_type = save->type;
                source_data = save->data;
            }

            nlohmann::json result;
            assign_optional(
                result,
                "characterId",
                optional_text(
                    source_type,
                    source_data,
                    {STR("CharacterID"), STR("CharacterId")}
                )
            );
            assign_optional(
                result,
                "nickname",
                optional_text(
                    source_type,
                    source_data,
                    {STR("NickName"), STR("Nickname")}
                )
            );
            assign_optional(
                result,
                "level",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Level")}
                )
            );
            assign_optional(
                result,
                "experience",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Exp"), STR("Experience")}
                )
            );
            assign_optional(
                result,
                "rank",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Rank")}
                )
            );
            const auto hp_raw = optional_fixed_point_raw(
                source_type,
                source_data,
                {STR("HP")}
            );
            auto max_hp_raw = optional_fixed_point_raw(
                source_type,
                source_data,
                {STR("MaxHP")}
            );
            if (!max_hp_raw || *max_hp_raw <= 0)
            {
                max_hp_raw = individual_max_hp_raw_value(parameter);
            }
            assign_optional(result, "hpRaw", hp_raw);
            assign_optional(
                result,
                "hp",
                fixed_point_display_value(hp_raw)
            );
            assign_optional(result, "maxHpRaw", max_hp_raw);
            assign_optional(
                result,
                "maxHp",
                positive_fixed_point_display_value(max_hp_raw)
            );
            assign_optional(
                result,
                "unusedStatusPoints",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("UnusedStatusPoint")}
                )
            );
            assign_optional(
                result,
                "rare",
                optional_bool(
                    source_type,
                    source_data,
                    {STR("IsRarePal"), STR("RarePal")}
                )
            );
            result["passiveSkills"] = optional_name_array(
                source_type,
                source_data,
                {STR("PassiveSkillList")},
                64
            );

            auto ivs = nlohmann::json::object();
            assign_optional(
                ivs,
                "hp",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Talent_HP")}
                )
            );
            assign_optional(
                ivs,
                "melee",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Talent_Melee")}
                )
            );
            assign_optional(
                ivs,
                "shot",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Talent_Shot")}
                )
            );
            assign_optional(
                ivs,
                "defense",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Talent_Defense"), STR("Talent_Defence")}
                )
            );
            result["ivs"] = std::move(ivs);

            auto enhancements = nlohmann::json::object();
            assign_optional(
                enhancements,
                "hp",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Rank_HP")}
                )
            );
            assign_optional(
                enhancements,
                "attack",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Rank_Attack")}
                )
            );
            assign_optional(
                enhancements,
                "defense",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Rank_Defence"), STR("Rank_Defense")}
                )
            );
            assign_optional(
                enhancements,
                "craftSpeed",
                optional_integer(
                    source_type,
                    source_data,
                    {STR("Rank_CraftSpeed")}
                )
            );
            result["enhancements"] = std::move(enhancements);
            return result;
        }

        nlohmann::json inventory_snapshot(const std::string& player_id)
        {
            auto* inventory_data = inventory(player_id);
            auto result = nlohmann::json{
                {"status", "available"},
                {"containers", nlohmann::json::array()},
                {"occupiedSlotCount", 0},
                {"totalQuantity", 0},
            };
            assign_optional(
                result,
                "currentWeight",
                optional_number(
                    inventory_data->GetClassPrivate(),
                    inventory_data,
                    {STR("NowItemWeight"), STR("CurrentItemWeight")}
                )
            );
            assign_optional(
                result,
                "maximumWeight",
                optional_number(
                    inventory_data->GetClassPrivate(),
                    inventory_data,
                    {
                        STR("maxInventoryWeight"),
                        STR("MaxInventoryWeight"),
                    }
                )
            );

            std::unordered_set<UObject*> visited;
            for (
                const auto& choice :
                enum_choices(
                    try_get_inventory_container,
                    {
                        STR("inventoryType"),
                        STR("InventoryType"),
                    }
                )
            )
            {
                Invocation lookup(try_get_inventory_container);
                set_enum_value(
                    try_get_inventory_container,
                    lookup.data(),
                    {
                        STR("inventoryType"),
                        STR("InventoryType"),
                    },
                    choice.value
                );
                lookup.call(inventory_data);
                if (!bool_return(lookup))
                {
                    continue;
                }
                auto* container = object_parameter(
                    try_get_inventory_container,
                    lookup.data(),
                    {
                        STR("OutContainer"),
                        STR("outContainer"),
                        STR("Container"),
                    }
                );
                if (
                    !container || !UObject::IsReal(container)
                    || !visited.insert(container).second
                )
                {
                    continue;
                }

                const auto slots = optional_object_array(
                    container,
                    {STR("ItemSlotArray"), STR("SlotArray")},
                    8192
                );
                auto container_json = nlohmann::json{
                    {"type", choice.name},
                    {"slotCount", slots.size()},
                    {"occupiedSlotCount", 0},
                    {"items", nlohmann::json::array()},
                };
                for (std::size_t index = 0; index < slots.size(); ++index)
                {
                    auto* slot = slots[index];
                    if (!slot)
                    {
                        continue;
                    }
                    const auto quantity = optional_integer(
                        slot->GetClassPrivate(),
                        slot,
                        {STR("StackCount"), STR("Count")}
                    ).value_or(0);
                    const auto item_id = optional_struct(
                        slot->GetClassPrivate(),
                        slot,
                        {STR("ItemId"), STR("ItemID")}
                    );
                    const auto static_id = item_id
                        ? optional_text(
                              item_id->type,
                              item_id->data,
                              {
                                  STR("StaticId"),
                                  STR("StaticID"),
                                  STR("StaticItemId"),
                              }
                          ).value_or(std::string{})
                        : std::string{};
                    if (
                        quantity <= 0 || static_id.empty()
                        || static_id == "None"
                    )
                    {
                        continue;
                    }
                    const auto slot_index = optional_integer(
                        slot->GetClassPrivate(),
                        slot,
                        {STR("SlotIndex"), STR("Index")}
                    ).value_or(static_cast<std::int64_t>(index));
                    container_json["items"].push_back({
                        {"slotIndex", slot_index},
                        {"itemId", static_id},
                        {"quantity", quantity},
                    });
                    container_json["occupiedSlotCount"] =
                        container_json["occupiedSlotCount"]
                            .get<std::size_t>()
                        + 1;
                    result["occupiedSlotCount"] =
                        result["occupiedSlotCount"].get<std::size_t>()
                        + 1;
                    result["totalQuantity"] =
                        result["totalQuantity"].get<std::int64_t>()
                        + quantity;
                }
                result["containers"].push_back(
                    std::move(container_json)
                );
            }
            return result;
        }

        nlohmann::json party_snapshot(
            const std::string& player_id,
            std::size_t page_index,
            std::size_t page_size
        )
        {
            if (page_size == 0 || page_size > 30)
            {
                throw std::runtime_error(
                    "Party Pal page size must be between 1 and 30."
                );
            }

            std::vector<RC::Unreal::UObject*> handles;
            try
            {
                handles = party_handles(player_id);
            }
            catch (const std::exception& error)
            {
                return {
                    {"status", "unavailable"},
                    {"collection", "party"},
                    {"pageCount", 0},
                    {"pageIndex", page_index},
                    {"pageSize", page_size},
                    {"capacity", 0},
                    {"count", 0},
                    {"loadedCount", 0},
                    {"partialCount", 0},
                    {"hasPrevious", false},
                    {"hasNext", false},
                    {"entries", nlohmann::json::array()},
                    {"error", error.what()},
                };
            }

            const auto page_count = handles.empty()
                ? std::size_t{0}
                : ((handles.size() - 1) / page_size) + 1;
            const auto start_index = page_index < page_count
                ? page_index * page_size
                : handles.size();
            const auto end_index = std::min(
                start_index + page_size,
                handles.size()
            );
            auto result = nlohmann::json{
                {"status", "available"},
                {"collection", "party"},
                {"pageCount", page_count},
                {"pageIndex", page_index},
                {"pageSize", page_size},
                {"capacity", handles.size()},
                {"count", handles.size()},
                {"loadedCount", 0},
                {"partialCount", 0},
                {"hasPrevious", page_index > 0 && page_count > 0},
                {"hasNext", page_index + 1 < page_count},
                {"entries", nlohmann::json::array()},
            };
            for (
                std::size_t index = start_index;
                index < end_index;
                ++index
            )
            {
                auto* handle = handles[index];
                auto entry = nlohmann::json{
                    {"slotIndex", index},
                    {"pageIndex", 0},
                    {"indexInPage", index},
                };
                if (
                    const auto id = optional_struct(
                        handle->GetClassPrivate(),
                        handle,
                        {STR("ID"), STR("Id")}
                    )
                )
                {
                    if (
                        const auto instance = optional_guid(
                            id->type,
                            id->data,
                            {
                                STR("InstanceId"),
                                STR("InstanceID"),
                            }
                        )
                    )
                    {
                        entry["instanceId"] =
                            player_guid_string(*instance);
                    }
                }

                RC::Unreal::UObject* parameter = nullptr;
                try
                {
                    Invocation lookup(try_get_individual_parameter);
                    lookup.call(handle);
                    parameter = object_return(lookup);
                }
                catch (...)
                {
                }
                if (parameter && RC::Unreal::UObject::IsReal(parameter))
                {
                    auto snapshot = character_snapshot(parameter);
                    for (auto& [key, value] : snapshot.items())
                    {
                        entry[key] = std::move(value);
                    }
                    entry["status"] = "available";
                }
                else
                {
                    entry["status"] = "partial";
                    result["partialCount"] =
                        result["partialCount"].get<std::size_t>() + 1;
                }
                result["entries"].push_back(std::move(entry));
            }
            result["loadedCount"] = result["entries"].size();
            return result;
        }

        nlohmann::json pal_snapshot(
            const std::string& player_id,
            const std::string& collection,
            std::size_t page_index,
            std::size_t page_size
        )
        {
            if (collection == "party")
            {
                return party_snapshot(player_id, page_index, page_size);
            }
            if (collection != "palbox")
            {
                throw std::runtime_error("Unknown Pal collection.");
            }
            if (page_size == 0 || page_size > 30)
            {
                throw std::runtime_error(
                    "Palbox page size must be between 1 and 30."
                );
            }
            auto* storage = pal_storage(
                player_id,
                player_controller(player_id)
            );
            auto* container = pal_container(storage);
            const auto slots = optional_object_array(
                container,
                {STR("SlotArray")},
                100000
            );
            const auto slots_per_page = optional_integer(
                storage->GetClassPrivate(),
                storage,
                {STR("SlotNumInPage"), STR("SlotsPerPage")}
            ).value_or(0);
            const auto storage_page_count = optional_integer(
                storage->GetClassPrivate(),
                storage,
                {STR("PageNum"), STR("PageCount")}
            ).value_or(0);
            const auto page_count = slots.empty()
                ? std::size_t{0}
                : ((slots.size() - 1) / page_size) + 1;
            const auto start_index = page_index < page_count
                ? page_index * page_size
                : slots.size();
            const auto end_index = std::min(
                start_index + page_size,
                slots.size()
            );

            auto result = nlohmann::json{
                {"status", "available"},
                {"collection", "palbox"},
                {"pageCount", page_count},
                {"storagePageCount", storage_page_count},
                {"slotsPerPage", slots_per_page},
                {"pageIndex", page_index},
                {"pageSize", page_size},
                {"capacity", slots.size()},
                {"count", nullptr},
                {"loadedCount", 0},
                {"partialCount", 0},
                {"hasPrevious", page_index > 0 && page_count > 0},
                {"hasNext", page_index + 1 < page_count},
                {"entries", nlohmann::json::array()},
            };
            for (
                std::size_t index = start_index;
                index < end_index;
                ++index
            )
            {
                auto* slot = slots[index];
                auto* handle = slot
                    ? object_property(slot, {STR("Handle")})
                    : nullptr;
                if (!handle || !UObject::IsReal(handle))
                {
                    continue;
                }
                auto entry = nlohmann::json{
                    {"slotIndex", index},
                    {
                        "pageIndex",
                        slots_per_page > 0
                            ? static_cast<std::int64_t>(index)
                                / slots_per_page
                            : 0
                    },
                    {
                        "indexInPage",
                        slots_per_page > 0
                            ? static_cast<std::int64_t>(index)
                                % slots_per_page
                            : static_cast<std::int64_t>(index)
                    },
                };
                if (
                    const auto id = optional_struct(
                        handle->GetClassPrivate(),
                        handle,
                        {STR("ID"), STR("Id")}
                    )
                )
                {
                    if (
                        const auto instance = optional_guid(
                            id->type,
                            id->data,
                            {
                                STR("InstanceId"),
                                STR("InstanceID"),
                            }
                        )
                    )
                    {
                        entry["instanceId"] =
                            player_guid_string(*instance);
                    }
                }

                UObject* parameter = nullptr;
                try
                {
                    Invocation lookup(try_get_individual_parameter);
                    lookup.call(handle);
                    parameter = object_return(lookup);
                }
                catch (...)
                {
                }
                if (parameter && UObject::IsReal(parameter))
                {
                    auto snapshot = character_snapshot(parameter);
                    for (auto& [key, value] : snapshot.items())
                    {
                        entry[key] = std::move(value);
                    }
                    entry["status"] = "available";
                }
                else
                {
                    entry["status"] = "partial";
                    result["partialCount"] =
                        result["partialCount"].get<std::size_t>() + 1;
                }
                result["entries"].push_back(std::move(entry));
            }
            result["loadedCount"] = result["entries"].size();
            return result;
        }

        nlohmann::json live_diagnostics() const
        {
            return {
                {
                    "experience",
                    {
                        {
                            "enableCheats",
                            function_description(enable_cheats)
                        },
                        {
                            "cheatAddPlayerExperience",
                            function_description(cheat_add_experience)
                        },
                        {
                            "initCheatManager",
                            function_description(init_cheat_manager)
                        },
                        {
                            "localPlayerSetupComplete",
                            function_description(
                                local_player_setup_complete
                            )
                        },
                        {
                            "playerControllers",
                            describe_player_controllers()
                        },
                        {
                            "cheatManagerInstances",
                            describe_instances(
                                std::string_view{"PalCheatManager"}
                            )
                        },
                    },
                },
            };
        }

        bool validate_player_lookup() const
        {
            if (!utility_cdo || !get_player_controller)
            {
                return false;
            }
            try
            {
                Invocation invocation(get_player_controller);
                set_object(
                    get_player_controller,
                    invocation.data(),
                    {STR("WorldContextObject")},
                    nullptr,
                    "world context"
                );
                set_player_guid(
                    get_player_controller,
                    invocation.data(),
                    PlayerGuid{}
                );
                static_cast<void>(object_return(invocation));
                return true;
            }
            catch (...)
            {
                return false;
            }
        }

        bool validate_player_list() const
        {
            using namespace RC::Unreal;

            if (!utility_cdo || !get_all_player_states)
            {
                return false;
            }
            try
            {
                Invocation invocation(get_all_player_states);
                set_object(
                    get_all_player_states,
                    invocation.data(),
                    {STR("WorldContextObject")},
                    nullptr,
                    "world context"
                );
                auto* states_property = require_property(
                    get_all_player_states,
                    {STR("OutPlayerStates")},
                    "player-state list"
                );
                auto* array_property =
                    CastField<FArrayProperty>(states_property);
                auto* inner_object_property = array_property
                    ? CastField<FObjectPropertyBase>(
                          array_property->GetInner()
                      )
                    : nullptr;
                auto* player_state_class = inner_object_property
                    ? inner_object_property
                          ->GetPropertyClass()
                          .Get()
                    : nullptr;
                if (
                    !array_property || !player_state_class
                    || states_property->GetSize()
                        < static_cast<std::int32_t>(
                            sizeof(TArray<UObject*>)
                        )
                )
                {
                    return false;
                }
                auto* uid_property = find_property(
                    player_state_class,
                    {STR("PlayerUId")}
                );
                auto* name_property = find_property(
                    player_state_class,
                    {STR("AccountName")}
                );
                return (
                    uid_property
                    && CastField<FStructProperty>(uid_property)
                    && uid_property->GetSize()
                        >= static_cast<std::int32_t>(
                            sizeof(PlayerGuid)
                        )
                    && CastField<FStrProperty>(name_property)
                );
            }
            catch (...)
            {
                return false;
            }
        }

        bool validate_party_list() const
        {
            using namespace RC::Unreal;

            if (!get_all_party_handles)
            {
                return false;
            }
            try
            {
                auto* handles_property = require_property(
                    get_all_party_handles,
                    {STR("OutArray")},
                    "party Pal handle list"
                );
                auto* array_property =
                    CastField<FArrayProperty>(handles_property);
                auto* inner_object_property = array_property
                    ? CastField<FObjectPropertyBase>(
                          array_property->GetInner()
                      )
                    : nullptr;
                auto* holder_class = Cast<UClass>(
                    get_all_party_handles->GetOuterPrivate()
                );
                return (
                    array_property && inner_object_property
                    && inner_object_property->GetPropertyClass().Get()
                    && holder_class
                    && handles_property->GetSize()
                        >= static_cast<std::int32_t>(
                            sizeof(TArray<UObject*>)
                        )
                );
            }
            catch (...)
            {
                return false;
            }
        }

        bool validate_inventory() const
        {
            if (
                !validate_player_lookup() || !get_inventory
                || !add_item
            )
            {
                return false;
            }
            try
            {
                Invocation lookup(get_inventory);
                set_object(
                    get_inventory,
                    lookup.data(),
                    {STR("WorldContextObject")},
                    nullptr,
                    "world context"
                );
                set_player_guid(
                    get_inventory,
                    lookup.data(),
                    PlayerGuid{}
                );
                static_cast<void>(object_return(lookup));

                Invocation add(add_item);
                set_name(
                    add_item,
                    add.data(),
                    {STR("StaticItemId"), STR("StaticItemID")},
                    "None",
                    "item ID"
                );
                set_integer(
                    add_item,
                    add.data(),
                    {STR("Count"), STR("Num")},
                    1,
                    "item quantity"
                );
                set_bool(
                    add_item,
                    add.data(),
                    {
                        STR("IsAssignPassive"),
                        STR("isAssignPassive"),
                    },
                    false,
                    "assign-passive flag"
                );
                set_float(
                    add_item,
                    add.data(),
                    {STR("LogDelay")},
                    0.0,
                    "item log delay"
                );
                set_bool(
                    add_item,
                    add.data(),
                    {STR("bNotifyLog"), STR("NotifyLog")},
                    true,
                    "item notification flag"
                );
                static_cast<void>(numeric_return(add));
                return true;
            }
            catch (...)
            {
                return false;
            }
        }

        bool validate_database_experience() const
        {
            using namespace RC::Unreal;

            if (
                !validate_player_lookup()
                || !database_add_experience
            )
            {
                return false;
            }
            try
            {
                Invocation invocation(database_add_experience);
                set_integer(
                    database_add_experience,
                    invocation.data(),
                    {STR("ExpValue")},
                    1,
                    "experience amount"
                );
                set_bool(
                    database_add_experience,
                    invocation.data(),
                    {STR("isCallDelegate"), STR("IsCallDelegate")},
                    true,
                    "experience notification flag"
                );
                auto* list_property = require_property(
                    database_add_experience,
                    {STR("GiftPlayerList")},
                    "experience player list"
                );
                auto* array_property =
                    CastField<FArrayProperty>(list_property);
                auto* inner_object_property = array_property
                    ? CastField<FObjectPropertyBase>(
                          array_property->GetInner()
                      )
                    : nullptr;
                return (
                    array_property
                    && inner_object_property
                    && inner_object_property
                           ->GetPropertyClass()
                           .Get()
                    && list_property->GetSize()
                        >= static_cast<std::int32_t>(
                            sizeof(TArray<UObject*>)
                        )
                );
            }
            catch (...)
            {
                return false;
            }
        }

        bool validate_pal()
        {
            pal_validation_error.clear();
            if (
                !validate_player_lookup()
                || !get_pal_storage
                || !initialize_character
                || !get_character_manager
                || !create_individual
                || !get_individual_id
                || !attach_granted_individual
                || !find_empty_pal_slot
                || !find_pal_slot_by_handle
            )
            {
                pal_validation_error =
                    "One or more required reflected functions are unavailable.";
                return false;
            }
            try
            {
                Invocation manager(get_character_manager);
                set_object(
                    get_character_manager,
                    manager.data(),
                    {STR("WorldContextObject")},
                    nullptr,
                    "world context"
                );
                static_cast<void>(object_return(manager));

                Invocation initialize(initialize_character, true);
                set_object(
                    initialize_character,
                    initialize.data(),
                    {STR("WorldContextObject")},
                    nullptr,
                    "world context"
                );
                set_name(
                    initialize_character,
                    initialize.data(),
                    {STR("CharacterID"), STR("CharacterId")},
                    "None",
                    "Pal character ID"
                );
                set_name(
                    initialize_character,
                    initialize.data(),
                    {STR("UniqueNPCID"), STR("UniqueNPCId")},
                    "None",
                    "Pal unique NPC ID"
                );
                set_integer(
                    initialize_character,
                    initialize.data(),
                    {STR("Level")},
                    1,
                    "Pal level"
                );
                set_player_guid(
                    initialize_character,
                    initialize.data(),
                    PlayerGuid{}
                );
                set_bool(
                    initialize_character,
                    initialize.data(),
                    {STR("DisableRandomPassiveSkill")},
                    false,
                    "disable-random-passive flag"
                );
                set_bool(
                    initialize_character,
                    initialize.data(),
                    {STR("RarePalAble")},
                    false,
                    "rare-Pal flag"
                );
                static_cast<void>(bool_return(initialize));

                auto* initialized_property = require_property(
                    initialize_character,
                    {STR("outParameter")},
                    "Pal initialization parameter"
                );
                auto* initialized_struct =
                    CastField<FStructProperty>(
                        initialized_property
                    );
                auto* initialized_type = initialized_struct
                    ? initialized_struct->GetStruct().Get()
                    : nullptr;
                if (!initialized_type)
                {
                    throw std::runtime_error(
                        "The reflected Pal initialization result is not a struct."
                    );
                }
                auto* initialized_value = property_value(
                    initialized_property,
                    initialize.data()
                );
                set_name_array(
                    initialized_type,
                    initialized_value,
                    {STR("PassiveSkillList")},
                    {},
                    "Pal passive skills"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Talent_HP")},
                    0,
                    "Pal HP individual value"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Talent_Melee")},
                    0,
                    "Pal melee individual value"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Talent_Shot")},
                    0,
                    "Pal shot individual value"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Talent_Defense")},
                    0,
                    "Pal defense individual value"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Rank")},
                    1,
                    "Pal condensation rank"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Rank_HP")},
                    0,
                    "Pal HP soul enhancement"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Rank_Attack")},
                    0,
                    "Pal attack soul enhancement"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Rank_Defence")},
                    0,
                    "Pal defense soul enhancement"
                );
                set_integer(
                    initialized_type,
                    initialized_value,
                    {STR("Rank_CraftSpeed")},
                    0,
                    "Pal work-speed soul enhancement"
                );

                Invocation create(create_individual, true);
                copy_struct_value(
                    initialize_character,
                    initialize.data(),
                    {STR("outParameter")},
                    create_individual,
                    create.data(),
                    {STR("InitParameter")},
                    "Pal initialization parameter"
                );
                auto* spawn_callback = CastField<FDelegateProperty>(
                    require_property(
                        create_individual,
                        {STR("spawnCallback"), STR("SpawnCallback")},
                        "Pal creation callback"
                    )
                );
                validate_delegate_callback(
                    spawn_callback,
                    attach_granted_individual,
                    "Pal creation callback"
                );
                static_cast<void>(object_return(create));

                Invocation empty(find_empty_pal_slot);
                static_cast<void>(object_return(empty));
                Invocation find(find_pal_slot_by_handle);
                set_object(
                    find_pal_slot_by_handle,
                    find.data(),
                    {STR("Handle")},
                    nullptr,
                    "Pal handle"
                );
                static_cast<void>(object_return(find));
                return true;
            }
            catch (const std::exception& error)
            {
                pal_validation_error = error.what();
                return false;
            }
            catch (...)
            {
                pal_validation_error =
                    "The reflected Pal-grant validation failed with an unknown error.";
                return false;
            }
        }

        RC::Unreal::UObject* player_controller(
            const std::string& player_id
        )
        {
            using namespace RC::Unreal;

            if (!utility_cdo || !get_player_controller)
            {
                throw std::runtime_error(
                    "The Palworld player lookup capability is unavailable."
                );
            }
            auto* context = world_context();
            if (!context)
            {
                throw std::runtime_error(
                    "No online Palworld player is available."
                );
            }

            Invocation invocation(get_player_controller);
            set_object(
                get_player_controller,
                invocation.data(),
                {STR("WorldContextObject")},
                context,
                "world context"
            );
            set_player_guid(
                get_player_controller,
                invocation.data(),
                parse_player_guid(player_id)
            );
            invocation.call(utility_cdo);
            auto* controller = object_return(invocation);
            if (!controller || !UObject::IsReal(controller))
            {
                throw std::runtime_error(
                    "The selected player is no longer online."
                );
            }
            return controller;
        }

        RC::Unreal::UObject* world_context(bool refresh = false)
        {
            using namespace RC::Unreal;

            if (
                !refresh
                &&
                cached_world_context
                && UObject::IsReal(cached_world_context)
            )
            {
                return cached_world_context;
            }
            cached_world_context = nullptr;
            std::vector<UObject*> controllers;
            UObjectGlobals::FindAllOf(
                std::string_view{"PalPlayerController"},
                controllers
            );
            for (auto iterator = controllers.rbegin();
                 iterator != controllers.rend();
                 ++iterator)
            {
                auto* controller = *iterator;
                if (!controller || !UObject::IsReal(controller))
                {
                    continue;
                }
                auto* player_state = object_property(
                    controller,
                    {STR("PlayerState")}
                );
                if (player_state && UObject::IsReal(player_state))
                {
                    cached_world_context = controller;
                    break;
                }
            }
            return (
                cached_world_context
                && UObject::IsReal(cached_world_context)
            )
                ? cached_world_context
                : nullptr;
        }

        void set_instance_mode(
            std::string mode,
            bool authoritative,
            std::string error
        )
        {
            std::lock_guard lock(instance_mutex);
            current_instance_mode = std::move(mode);
            instance_error = std::move(error);
            instance_authoritative.store(authoritative);
        }

        RC::Unreal::UObject* inventory(
            const std::string& player_id
        )
        {
            using namespace RC::Unreal;

            if (!utility_cdo || !get_inventory)
            {
                throw std::runtime_error(
                    "The Palworld inventory lookup capability is unavailable."
                );
            }
            auto* controller = player_controller(player_id);
            Invocation invocation(get_inventory);
            set_object(
                get_inventory,
                invocation.data(),
                {STR("WorldContextObject")},
                controller,
                "world context"
            );
            set_player_guid(
                get_inventory,
                invocation.data(),
                parse_player_guid(player_id)
            );
            invocation.call(utility_cdo);
            auto* result = object_return(invocation);
            if (!result || !UObject::IsReal(result))
            {
                throw std::runtime_error(
                    "The selected player's inventory is unavailable."
                );
            }
            return result;
        }

        RC::Unreal::UObject* pal_storage(
            const std::string& player_id,
            RC::Unreal::UObject* controller
        )
        {
            using namespace RC::Unreal;

            if (!utility_cdo || !get_pal_storage)
            {
                throw std::runtime_error(
                    "The Palworld Pal-storage lookup capability is unavailable."
                );
            }
            Invocation invocation(get_pal_storage);
            set_object(
                get_pal_storage,
                invocation.data(),
                {STR("WorldContextObject")},
                controller,
                "world context"
            );
            set_player_guid(
                get_pal_storage,
                invocation.data(),
                parse_player_guid(player_id)
            );
            invocation.call(utility_cdo);
            auto* storage = object_return(invocation);
            if (!storage || !UObject::IsReal(storage))
            {
                throw std::runtime_error(
                    "The selected player's Pal storage is unavailable."
                );
            }
            return storage;
        }

        RC::Unreal::UObject* pal_container(
            RC::Unreal::UObject* storage
        ) const
        {
            using namespace RC::Unreal;

            auto* container = object_property(
                storage,
                {STR("TargetContainer")}
            );
            if (!container || !UObject::IsReal(container))
            {
                throw std::runtime_error(
                    "The selected player's authoritative Palbox container is unavailable."
                );
            }
            return container;
        }

        RC::Unreal::UObject* party_holder(
            const std::string& player_id
        )
        {
            using namespace RC::Unreal;

            if (!party_list_available || !get_all_party_handles)
            {
                throw std::runtime_error(
                    "The Palworld Party Pal lookup capability is unavailable."
                );
            }

            auto* holder_class = Cast<UClass>(
                get_all_party_handles->GetOuterPrivate()
            );
            if (!holder_class)
            {
                throw std::runtime_error(
                    "The Palworld Party Pal holder class is unavailable."
                );
            }

            auto* controller = player_controller(player_id);
            auto* player_state = object_property(
                controller,
                {STR("PlayerState")}
            );
            auto* pawn = object_property(
                controller,
                {STR("Pawn"), STR("AcknowledgedPawn"), STR("Character")}
            );
            for (auto* owner : {pawn, controller, player_state})
            {
                if (!owner || !UObject::IsReal(owner))
                {
                    continue;
                }
                auto* holder = object_property_assignable_to(
                    owner,
                    holder_class
                );
                if (holder && UObject::IsReal(holder))
                {
                    return holder;
                }
            }

            std::vector<UObject*> holders;
            UObjectGlobals::FindAllOf(
                std::string_view{"PalOtomoHolderComponentBase"},
                holders
            );
            for (auto* holder : holders)
            {
                if (!holder || !UObject::IsReal(holder))
                {
                    continue;
                }
                if ((pawn && object_is_within(holder, pawn))
                    || object_is_within(holder, controller)
                    || (player_state
                        && object_is_within(holder, player_state)))
                {
                    return holder;
                }
            }

            throw std::runtime_error(
                "The selected player's authoritative Party Pal holder is unavailable."
            );
        }

        std::vector<RC::Unreal::UObject*> party_handles(
            const std::string& player_id
        )
        {
            using namespace RC::Unreal;

            auto* holder = party_holder(player_id);
            Invocation invocation(get_all_party_handles);
            auto* handles_property = require_property(
                get_all_party_handles,
                {STR("OutArray")},
                "OutArray"
            );
            auto* handles_array = CastField<FArrayProperty>(handles_property);
            auto* inner_object = handles_array
                ? CastField<FObjectPropertyBase>(handles_array->GetInner())
                : nullptr;
            auto* handle_class = inner_object
                ? inner_object->GetPropertyClass().Get()
                : nullptr;
            if (!handles_array || !inner_object || !handle_class
                || handles_property->GetSize() < sizeof(TArray<UObject*>))
            {
                throw std::runtime_error(
                    "GetAllIndividualHandle.OutArray has an unsupported layout."
                );
            }

            auto destroy_handles = [&]() {
                handles_property->DestroyValue_InContainer(invocation.data());
            };
            try
            {
                invocation.call(holder);
                auto* handles = static_cast<TArray<UObject*>*>(
                    property_value(handles_property, invocation.data())
                );
                const auto count = handles ? handles->Num() : 0;
                if (count < 0 || count > 30)
                {
                    throw std::runtime_error(
                        "GetAllIndividualHandle.OutArray returned an invalid count."
                    );
                }

                std::vector<UObject*> result;
                result.reserve(static_cast<std::size_t>(count));
                for (std::int32_t index = 0; index < count; ++index)
                {
                    auto* handle = (*handles)[index];
                    if (handle && UObject::IsReal(handle)
                        && handle->IsA(handle_class))
                    {
                        result.push_back(handle);
                    }
                }
                destroy_handles();
                return result;
            }
            catch (...)
            {
                destroy_handles();
                throw;
            }
        }



        RC::Unreal::UObject* character_manager(
            RC::Unreal::UObject* world_context
        ) const
        {
            using namespace RC::Unreal;

            if (!utility_cdo || !get_character_manager)
            {
                throw std::runtime_error(
                    "The Palworld character-manager lookup capability is unavailable."
                );
            }
            Invocation invocation(get_character_manager);
            set_object(
                get_character_manager,
                invocation.data(),
                {STR("WorldContextObject")},
                world_context,
                "world context"
            );
            invocation.call(utility_cdo);
            auto* manager = object_return(invocation);
            auto* manager_class = create_individual
                ? Cast<UClass>(create_individual->GetOuterPrivate())
                : nullptr;
            if (
                !manager || !UObject::IsReal(manager)
                || !manager_class || !manager->IsA(manager_class)
            )
            {
                throw std::runtime_error(
                    "No authoritative Palworld character manager is available."
                );
            }
            return manager;
        }

        RC::Unreal::UObject* experience_cheat_manager(
            RC::Unreal::UObject* controller,
            bool& created,
            bool& initialized
        )
        {
            using namespace RC::Unreal;

            created = false;
            initialized = false;
            auto* manager = object_property(
                controller,
                {STR("CheatManager")}
            );
            if (manager && UObject::IsReal(manager))
            {
                return manager;
            }
            if (!enable_cheats)
            {
                throw std::runtime_error(
                    "Palworld does not expose PlayerController.EnableCheats."
                );
            }

            Invocation enable(enable_cheats);
            enable.call(controller);
            manager = object_property(
                controller,
                {STR("CheatManager")}
            );
            if (!manager || !UObject::IsReal(manager))
            {
                if (!cheat_add_experience)
                {
                    throw std::runtime_error(
                        "Palworld does not expose the cheat experience function."
                    );
                }
                auto* manager_class = Cast<UClass>(
                    cheat_add_experience->GetOuterPrivate()
                );
                if (
                    !manager_class
                    || lowercase_ascii(
                        RC::to_string(manager_class->GetFullName())
                    ).find("palcheatmanager") == std::string::npos
                )
                {
                    throw std::runtime_error(
                        "The reflected experience function has an unexpected owner class."
                    );
                }
                manager = UObjectGlobals::NewObject<UObject>(
                    controller,
                    manager_class
                );
                if (!manager || !UObject::IsReal(manager))
                {
                    throw std::runtime_error(
                        "Palworld did not construct a cheat manager for the selected player."
                    );
                }
                set_object(
                    controller->GetClassPrivate(),
                    controller,
                    {STR("CheatManager")},
                    manager,
                    "cheat manager"
                );
                if (init_cheat_manager)
                {
                    try
                    {
                        Invocation initialize(init_cheat_manager);
                        initialize.call(manager);
                        initialized = true;
                    }
                    catch (...)
                    {
                        set_object(
                            controller->GetClassPrivate(),
                            controller,
                            {STR("CheatManager")},
                            nullptr,
                            "cheat manager"
                        );
                        throw;
                    }
                }
                if (!local_player_setup_complete)
                {
                    set_object(
                        controller->GetClassPrivate(),
                        controller,
                        {STR("CheatManager")},
                        nullptr,
                        "cheat manager"
                    );
                    throw std::runtime_error(
                        "Palworld does not expose the local-player cheat manager setup hook."
                    );
                }
                auto* player_state = object_property(
                    controller,
                    {STR("PlayerState")}
                );
                if (!player_state || !UObject::IsReal(player_state))
                {
                    set_object(
                        controller->GetClassPrivate(),
                        controller,
                        {STR("CheatManager")},
                        nullptr,
                        "cheat manager"
                    );
                    throw std::runtime_error(
                        "The selected player has no authoritative PlayerState."
                    );
                }
                try
                {
                    Invocation setup(local_player_setup_complete);
                    set_object(
                        local_player_setup_complete,
                        setup.data(),
                        {STR("PlayerState")},
                        player_state,
                        "player state"
                    );
                    setup.call(manager);
                    initialized = true;
                }
                catch (...)
                {
                    set_object(
                        controller->GetClassPrivate(),
                        controller,
                        {STR("CheatManager")},
                        nullptr,
                        "cheat manager"
                    );
                    throw;
                }
            }
            const auto manager_class =
                RC::to_string(manager->GetClassPrivate()->GetFullName());
            if (
                lowercase_ascii(manager_class).find("palcheatmanager")
                == std::string::npos
            )
            {
                throw std::runtime_error(
                    "The selected player received an unexpected cheat manager type."
                );
            }
            created = true;
            return manager;
        }

        RC::Unreal::UObject* utility_cdo{nullptr};
        RC::Unreal::UObject* kismet_system_cdo{nullptr};
        RC::Unreal::UObject* cached_world_context{nullptr};
        RC::Unreal::UFunction* is_server{nullptr};
        RC::Unreal::UFunction* is_dedicated_server{nullptr};
        RC::Unreal::UFunction* is_standalone{nullptr};
        RC::Unreal::UFunction* get_player_controller{nullptr};
        RC::Unreal::UFunction* get_actor_location{nullptr};
        RC::Unreal::UFunction* get_character_hp{nullptr};
        RC::Unreal::UFunction* get_character_max_hp{nullptr};
        RC::Unreal::UFunction* get_individual_max_hp_with_buff{nullptr};
        RC::Unreal::UFunction* get_individual_max_hp{nullptr};
        RC::Unreal::UFunction* get_character_max_sp{nullptr};
        RC::Unreal::UFunction* get_character_attack{nullptr};
        RC::Unreal::UFunction* get_character_defense{nullptr};
        RC::Unreal::UFunction* get_character_craft_speed{nullptr};
        RC::Unreal::UFunction* get_character_manager{nullptr};
        RC::Unreal::UFunction* get_all_player_states{nullptr};
        RC::Unreal::UFunction* get_guild_name{nullptr};
        RC::Unreal::UFunction* get_inventory{nullptr};
        RC::Unreal::UFunction* get_guild{nullptr};
        RC::Unreal::UFunction* get_pal_storage{nullptr};
        RC::Unreal::UFunction* try_get_inventory_container{nullptr};
        RC::Unreal::UFunction* try_get_individual_parameter{nullptr};
        RC::Unreal::UFunction* get_all_party_handles{nullptr};
        RC::Unreal::UFunction* get_individual_parameter_by_actor{nullptr};
        RC::Unreal::UFunction* add_item{nullptr};
        RC::Unreal::UFunction* add_experience{nullptr};
        RC::Unreal::UFunction* enable_cheats{nullptr};
        RC::Unreal::UFunction* init_cheat_manager{nullptr};
        RC::Unreal::UFunction* local_player_setup_complete{nullptr};
        RC::Unreal::UFunction* cheat_add_experience{nullptr};
        RC::Unreal::UFunction* database_add_experience{nullptr};
        RC::Unreal::UFunction* capture_pal{nullptr};
        RC::Unreal::UFunction* cheat_capture_pal{nullptr};
        RC::Unreal::UFunction* spawn_pal{nullptr};
        RC::Unreal::UFunction* initialize_character{nullptr};
        RC::Unreal::UFunction* create_individual{nullptr};
        RC::Unreal::UFunction* get_individual_id{nullptr};
        RC::Unreal::UFunction* attach_granted_individual{nullptr};
        RC::Unreal::UFunction* find_empty_pal_slot{nullptr};
        RC::Unreal::UFunction* find_pal_slot_by_handle{nullptr};
        mutable std::mutex pal_grant_diagnostics_mutex;
        RC::Unreal::UFunction* pal_grant_callback_hook_target{nullptr};
        std::optional<RC::Unreal::CallbackId>
            pal_grant_callback_hook_id;
        RC::Unreal::UObject* pal_grant_expected_player_state{nullptr};
        std::uint64_t pal_grant_sequence{0};
        std::uint64_t pal_grant_callback_count{0};
        std::uint64_t pal_grant_last_callback_sequence{0};
        bool pal_grant_last_callback_context_matches{false};
        std::string pal_grant_player_id;
        std::string pal_grant_expected_player_state_name;
        std::string pal_grant_last_callback_context_name;
        std::string pal_grant_callback_hook_error;
        bool inventory_available{false};
        bool experience_available{false};
        bool pal_available{false};
        bool player_list_available{false};
        bool guild_list_available{false};
        bool player_details_available{false};
        bool player_runtime_stats_available{false};
        bool inventory_read_available{false};
        bool pal_list_available{false};
        bool party_list_available{false};
        bool player_location_available{false};
        bool map_read_available{false};
        std::string pal_validation_error;
        mutable std::mutex status_mutex;
        mutable std::mutex instance_mutex;
        std::atomic_bool instance_authoritative{false};
        std::string current_instance_mode{"loading"};
        std::string instance_error;
        nlohmann::json runtime_status{
            {"inventoryGrant", false},
            {"playerExperienceAdd", false},
            {"palGrant", false},
            {"playerList", false},
            {"guildList", false},
            {"playerDetails", false},
            {"inventoryRead", false},
            {"palList", false},
            {"partyList", false},
            {"playerLocation", false},
            {"mapRead", false},
        };
    };

    PalworldRuntime::PalworldRuntime()
        : m_impl(std::make_unique<Impl>())
    {
    }

    PalworldRuntime::~PalworldRuntime() = default;

    void PalworldRuntime::initialize()
    {
        m_impl->initialize();
    }

    void PalworldRuntime::refresh_instance_mode(bool dedicated_process)
    {
        m_impl->refresh_instance_mode(dedicated_process);
    }

    bool PalworldRuntime::inventory_ready() const
    {
        return m_impl->inventory_ready();
    }

    bool PalworldRuntime::experience_ready() const
    {
        return m_impl->experience_ready();
    }

    bool PalworldRuntime::pal_ready() const
    {
        return m_impl->pal_ready();
    }

    bool PalworldRuntime::player_list_ready() const
    {
        return m_impl->player_list_ready();
    }

    bool PalworldRuntime::guild_list_ready() const
    {
        return m_impl->guild_list_ready();
    }

    bool PalworldRuntime::player_details_ready() const
    {
        return m_impl->player_details_ready();
    }

    bool PalworldRuntime::inventory_read_ready() const
    {
        return m_impl->inventory_read_ready();
    }

    bool PalworldRuntime::pal_list_ready() const
    {
        return m_impl->pal_list_ready();
    }

    bool PalworldRuntime::map_read_ready() const
    {
        return m_impl->map_read_ready();
    }

    bool PalworldRuntime::authoritative() const
    {
        return m_impl->authoritative();
    }

    std::string PalworldRuntime::instance_mode() const
    {
        return m_impl->instance_mode();
    }

    nlohmann::json PalworldRuntime::status() const
    {
        return m_impl->status();
    }

    nlohmann::json PalworldRuntime::players()
    {
        return m_impl->players();
    }

    nlohmann::json PalworldRuntime::guilds()
    {
        return m_impl->guilds();
    }

    nlohmann::json PalworldRuntime::map_snapshot()
    {
        return m_impl->map_snapshot();
    }

    nlohmann::json PalworldRuntime::player_details(
        const std::string& player_id
    )
    {
        return m_impl->player_details(player_id);
    }

    nlohmann::json PalworldRuntime::inventory_snapshot(
        const std::string& player_id
    )
    {
        if (!inventory_read_ready())
        {
            throw std::runtime_error(
                "The inventory read capability is unavailable for this game build."
            );
        }
        return m_impl->inventory_snapshot(player_id);
    }

    nlohmann::json PalworldRuntime::pal_snapshot(
        const std::string& player_id,
        const std::string& collection,
        std::size_t page_index,
        std::size_t page_size
    )
    {
        if (!pal_list_ready())
        {
            throw std::runtime_error(
                "The Pal list capability is unavailable for this game build."
            );
        }
        return m_impl->pal_snapshot(player_id, collection, page_index, page_size);
    }

    nlohmann::json PalworldRuntime::live_diagnostics() const
    {
        return m_impl->live_diagnostics();
    }

    nlohmann::json PalworldRuntime::reflect_functions(
        const std::string& fragment
    ) const
    {
        if (fragment.empty() || fragment.size() > 128)
        {
            throw std::runtime_error(
                "A reflection function-name fragment is required."
            );
        }
        auto matches = find_functions_containing(fragment);
        constexpr std::size_t maximum_matches = 512;
        if (matches.size() > maximum_matches)
        {
            matches.erase(
                matches.begin()
                    + static_cast<nlohmann::json::difference_type>(
                        maximum_matches
                    ),
                matches.end()
            );
        }
        return {
            {"fragment", fragment},
            {"functions", std::move(matches)},
        };
    }

    nlohmann::json PalworldRuntime::probe_player_experience(
        const std::string& player_id,
        std::int32_t amount,
        bool apply
    )
    {
        if (
            !m_impl->enable_cheats
            || !m_impl->local_player_setup_complete
            || !m_impl->cheat_add_experience
        )
        {
            throw std::runtime_error(
                "The authoritative experience diagnostic path is unavailable for this game build."
            );
        }

        auto* controller = m_impl->player_controller(player_id);
        bool manager_created = false;
        bool manager_initialized = false;
        auto* manager = m_impl->experience_cheat_manager(
            controller,
            manager_created,
            manager_initialized
        );
        const auto manager_details = object_description(manager);
        try
        {
            if (apply)
            {
                Invocation invocation(m_impl->cheat_add_experience);
                set_integer(
                    m_impl->cheat_add_experience,
                    invocation.data(),
                    {STR("addExp"), STR("AddExp"), STR("Exp")},
                    amount,
                    "experience amount"
                );
                invocation.call(manager);
            }
        }
        catch (...)
        {
            if (manager_created)
            {
                set_object(
                    controller->GetClassPrivate(),
                    controller,
                    {STR("CheatManager")},
                    nullptr,
                    "cheat manager"
                );
            }
            throw;
        }
        if (manager_created)
        {
            set_object(
                controller->GetClassPrivate(),
                controller,
                {STR("CheatManager")},
                nullptr,
                "cheat manager"
            );
        }
        return {
            {"state", "completed"},
            {
                "result",
                {
                    {"playerId", player_id},
                    {"amount", amount},
                    {"applied", apply},
                    {"managerCreated", manager_created},
                    {"managerInitialized", manager_initialized},
                    {"managerReleased", manager_created},
                    {"cheatManager", manager_details},
                    {
                        "effectVerified",
                        false
                    },
                },
            },
        };
    }

    nlohmann::json PalworldRuntime::probe_experience_database(
        const std::string& player_id,
        std::int32_t amount,
        bool apply
    )
    {
        using namespace RC::Unreal;

        if (!m_impl->database_add_experience)
        {
            throw std::runtime_error(
                "The authoritative experience database path is unavailable for this game build."
            );
        }
        auto* database = UObjectGlobals::FindFirstOf(
            std::string_view{"PalExpDatabase"}
        );
        if (!database || !UObject::IsReal(database))
        {
            database = UObjectGlobals::StaticFindObject<UObject*>(
                nullptr,
                nullptr,
                STR("/Script/Pal.Default__PalExpDatabase")
            );
        }
        if (!database || !UObject::IsReal(database))
        {
            throw std::runtime_error(
                "No Palworld experience database context is available."
            );
        }

        auto* controller = m_impl->player_controller(player_id);
        auto* player_state = object_property(
            controller,
            {STR("PlayerState")}
        );
        if (!player_state || !UObject::IsReal(player_state))
        {
            throw std::runtime_error(
                "The selected player has no authoritative PlayerState."
            );
        }

        Invocation invocation(m_impl->database_add_experience);
        set_integer(
            m_impl->database_add_experience,
            invocation.data(),
            {STR("ExpValue")},
            amount,
            "experience amount"
        );
        set_bool(
            m_impl->database_add_experience,
            invocation.data(),
            {STR("isCallDelegate"), STR("IsCallDelegate")},
            true,
            "experience notification flag"
        );
        auto* list_property = require_property(
            m_impl->database_add_experience,
            {STR("GiftPlayerList")},
            "experience player list"
        );
        auto* array_property = CastField<FArrayProperty>(list_property);
        auto* inner_object_property = array_property
            ? CastField<FObjectPropertyBase>(
                  array_property->GetInner()
              )
            : nullptr;
        if (!array_property || !inner_object_property)
        {
            throw std::runtime_error(
                "The reflected experience player list is not an object array."
            );
        }
        auto* required_player_class =
            inner_object_property->GetPropertyClass().Get();
        if (!required_player_class)
        {
            throw std::runtime_error(
                "The reflected experience player-list class is unavailable."
            );
        }
        auto* gift_player = player_state->IsA(required_player_class)
            ? player_state
            : nullptr;
        for (
            const auto* name :
            {
                STR("Pawn"),
                STR("AcknowledgedPawn"),
                STR("Character"),
            }
        )
        {
            if (gift_player)
            {
                break;
            }
            auto* candidate = object_property(controller, {name});
            if (
                candidate && UObject::IsReal(candidate)
                && candidate->IsA(required_player_class)
            )
            {
                gift_player = candidate;
            }
        }
        if (!gift_player)
        {
            throw std::runtime_error(
                "The selected controller has no object matching the experience player-list class "
                + RC::to_string(required_player_class->GetFullName())
                + "."
            );
        }

        TArray<UObject*> players;
        players.Add(gift_player);
        if (
            list_property->GetSize()
                < static_cast<std::int32_t>(sizeof(players))
        )
        {
            throw std::runtime_error(
                "The reflected experience player-list layout is too small."
            );
        }
        auto* player_list_parameters =
            property_value(list_property, invocation.data());
        std::memcpy(
            player_list_parameters,
            &players,
            sizeof(players)
        );
        try
        {
            if (apply)
            {
                invocation.call(database);
            }
        }
        catch (...)
        {
            std::memset(
                player_list_parameters,
                0,
                sizeof(players)
            );
            throw;
        }
        std::memset(
            player_list_parameters,
            0,
            sizeof(players)
        );

        return {
            {"state", "completed"},
            {
                "result",
                {
                    {"playerId", player_id},
                    {"amount", amount},
                    {"applied", apply},
                    {"database", object_description(database)},
                    {"playerState", object_description(player_state)},
                    {"giftPlayer", object_description(gift_player)},
                    {
                        "playerStateClass",
                        RC::to_string(
                            required_player_class->GetFullName()
                        )
                    },
                    {"notificationRequested", true},
                    {"effectVerified", false},
                },
            },
        };
    }

    nlohmann::json PalworldRuntime::probe_runtime_data(
        const std::string& player_id
    )
    {
        RC::Unreal::UObject* controller = nullptr;
        const std::string controller_error =
            "Schema-only diagnostics do not access live player objects.";
        auto* player_state = object_property(
            controller,
            {STR("PlayerState")}
        );
        auto* pawn = object_property(
            controller,
            {
                STR("Pawn"),
                STR("AcknowledgedPawn"),
                STR("Character"),
            }
        );

        auto lookup = [](
            RC::Unreal::UFunction* function,
            const char* purpose
        ) -> nlohmann::json {
            if (!function)
            {
                return {
                    {"available", false},
                    {
                        "error",
                        std::string("The reflected ")
                            + purpose
                            + " function is unavailable."
                    },
                };
            }
            return {
                {"available", false},
                {
                    "error",
                    std::string("Schema-only diagnostics skipped the ")
                        + purpose + " call."
                },
                {
                    "function",
                    function_description(function)
                },
            };
        };

        return {
            {"state", "completed"},
            {
                "result",
                {
                    {"playerId", player_id},
                    {
                        "controller",
                        {
                            {
                                "available",
                                controller
                                    && RC::Unreal::UObject::IsReal(
                                        controller
                                    )
                            },
                            {"schema", object_schema(controller)},
                            {
                                "error",
                                controller_error.empty()
                                    ? nlohmann::json(nullptr)
                                    : nlohmann::json(controller_error)
                            },
                        },
                    },
                    {"playerState", object_schema(player_state)},
                    {"pawn", object_schema(pawn)},
                    {
                        "inventory",
                        lookup(m_impl->get_inventory, "inventory lookup")
                    },
                    {
                        "guild",
                        lookup(m_impl->get_guild, "guild lookup")
                    },
                    {
                        "palStorage",
                        lookup(
                            m_impl->get_pal_storage,
                            "Pal storage lookup"
                        )
                    },
                    {
                        "functions",
                        {
                            {
                                "playerStates",
                                find_functions_containing(
                                    "GetAllPlayerStates"
                                )
                            },
                            {
                                "inventoryContainers",
                                find_functions_containing(
                                    "GetInventoryContainers"
                                )
                            },
                            {
                                "inventoryContainer",
                                find_functions_containing(
                                    "GetInventoryContainer"
                                )
                            },
                            {
                                "guild",
                                find_functions_containing(
                                    "GetGuildByPlayerUId"
                                )
                            },
                            {
                                "guildMembers",
                                find_functions_containing(
                                    "GetGuildMemberInfo"
                                )
                            },
                            {
                                "palCharacters",
                                find_functions_containing(
                                    "GetPalCharacters"
                                )
                            },
                            {
                                "individualHandles",
                                find_functions_containing(
                                    "GetAllIndividualHandle"
                                )
                            },
                            {
                                "playerLookup",
                                find_functions_containing(
                                    "GetPlayerStateByPlayerUid"
                                )
                            },
                            {
                                "inventoryLookup",
                                find_functions_containing(
                                    "GetInventoryDataByPlayerUID"
                                )
                            },
                            {
                                "inventoryType",
                                find_functions_containing(
                                    "GetContainerIDFromInventoryType"
                                )
                            },
                            {
                                "guildDetails",
                                find_functions_containing(
                                    "GetGuildName"
                                )
                            },
                            {
                                "guildAdmin",
                                find_functions_containing(
                                    "GetGuildAdminPlayerUid"
                                )
                            },
                            {
                                "guildRole",
                                find_functions_containing(
                                    "GetGuildRole"
                                )
                            },
                            {
                                "guildPermissions",
                                find_functions_containing(
                                    "GetGuildPermissions"
                                )
                            },
                            {
                                "palStorageLookup",
                                find_functions_containing(
                                    "GetPalStorageDataByPlayerUID"
                                )
                            },
                            {
                                "palBoxCount",
                                find_functions_containing(
                                    "GetRegisteredPalBoxCount"
                                )
                            },
                            {
                                "createPalHandle",
                                find_functions_containing(
                                    "CreatePlayerIndividualHandle_InServer"
                                )
                            },
                            {
                                "spawnPal",
                                find_functions_containing(
                                    "RequestSpawnMonsterForPlayer"
                                )
                            },
                        },
                    },
                    {
                        "classes",
                        {
                            {
                                "playerState",
                                class_schema(
                                    STR("/Script/Pal.PalPlayerState")
                                )
                            },
                            {
                                "inventory",
                                class_schema(
                                    STR(
                                        "/Script/Pal."
                                        "PalPlayerInventoryData"
                                    )
                                )
                            },
                            {
                                "playerDataStorage",
                                class_schema(
                                    STR(
                                        "/Script/Pal."
                                        "PalPlayerDataStorage"
                                    )
                                )
                            },
                            {
                                "guild",
                                class_schema(
                                    STR("/Script/Pal.PalGuildInfo")
                                )
                            },
                            {
                                "palStorage",
                                class_schema(
                                    STR(
                                        "/Script/Pal."
                                        "PalPlayerDataCharacterMakeInfo"
                                    )
                                )
                            },
                            {
                                "individualHandle",
                                class_schema(
                                    STR(
                                        "/Script/Pal."
                                        "PalIndividualCharacterHandle"
                                    )
                                )
                            },
                        },
                    },
                },
            },
        };
    }

    nlohmann::json PalworldRuntime::grant_item(
        const std::string& player_id,
        const std::string& item_id,
        std::int32_t quantity
    )
    {
        if (!inventory_ready())
        {
            throw std::runtime_error(
                "The live inventory capability is unavailable for this game build."
            );
        }
        auto* inventory = m_impl->inventory(player_id);
        Invocation invocation(m_impl->add_item);
        set_name(
            m_impl->add_item,
            invocation.data(),
            {STR("StaticItemId"), STR("StaticItemID")},
            item_id,
            "item ID"
        );
        set_integer(
            m_impl->add_item,
            invocation.data(),
            {STR("Count"), STR("Num")},
            quantity,
            "item quantity"
        );
        set_bool(
            m_impl->add_item,
            invocation.data(),
            {STR("IsAssignPassive"), STR("isAssignPassive")},
            false,
            "assign-passive flag"
        );
        set_float(
            m_impl->add_item,
            invocation.data(),
            {STR("LogDelay")},
            0.0,
            "item log delay"
        );
        set_bool(
            m_impl->add_item,
            invocation.data(),
            {STR("bNotifyLog"), STR("NotifyLog")},
            true,
            "item notification flag"
        );
        invocation.call(inventory);

        const auto operation_result = numeric_return(invocation);
        if (operation_result > 1)
        {
            throw std::runtime_error(
                "Palworld rejected the inventory operation with result code "
                + std::to_string(operation_result) + "."
            );
        }
        return {
            {"state", "completed"},
            {
                "result",
                {
                    {"playerId", player_id},
                    {"itemId", item_id},
                    {"quantity", quantity},
                    {"operationResult", operation_result},
                },
            },
        };
    }

    nlohmann::json PalworldRuntime::add_player_experience(
        const std::string& player_id,
        std::int32_t amount
    )
    {
        if (!experience_ready())
        {
            throw std::runtime_error(
                "The live player experience capability is unavailable for this game build."
            );
        }
        static_cast<void>(
            probe_experience_database(player_id, amount, true)
        );
        return {
            {"state", "completed"},
            {
                "result",
                {
                    {"playerId", player_id},
                    {"amount", amount},
                },
            },
        };
    }

    nlohmann::json PalworldRuntime::grant_pal(
        const std::string& player_id,
        const std::string& character_id,
        std::int32_t level,
        PalGrantOptions options
    )
    {
        if (!pal_ready())
        {
            throw std::runtime_error(
                "The live Pal grant capability is unavailable for this game build."
            );
        }
        if (options.iv_melee)
        {
            throw std::runtime_error(
                "Talent_Melee is transient in this Palworld build and cannot be persisted; omit ivs.melee."
            );
        }
        const auto started_at = std::chrono::steady_clock::now();
        auto* controller = m_impl->player_controller(player_id);
        auto* player_state = object_property(
            controller,
            {STR("PlayerState")}
        );
        if (!player_state || !UObject::IsReal(player_state))
        {
            throw std::runtime_error(
                "The selected player has no authoritative PlayerState."
            );
        }
        const auto player_lookup_completed_at =
            std::chrono::steady_clock::now();
        auto* storage = m_impl->pal_storage(player_id, controller);
        auto* container = m_impl->pal_container(storage);
        const auto storage_lookup_completed_at =
            std::chrono::steady_clock::now();

        Invocation empty(m_impl->find_empty_pal_slot);
        empty.call(container);
        auto* empty_slot = object_return(empty);
        if (!empty_slot || !UObject::IsReal(empty_slot))
        {
            throw std::runtime_error(
                "The selected player's Palbox has no empty slot."
            );
        }
        const auto slot_inspection_completed_at =
            std::chrono::steady_clock::now();

        Invocation initialize(m_impl->initialize_character, true);
        set_object(
            m_impl->initialize_character,
            initialize.data(),
            {STR("WorldContextObject")},
            controller,
            "world context"
        );
        set_name(
            m_impl->initialize_character,
            initialize.data(),
            {STR("CharacterID"), STR("CharacterId")},
            character_id,
            "Pal character ID"
        );
        set_name(
            m_impl->initialize_character,
            initialize.data(),
            {STR("UniqueNPCID"), STR("UniqueNPCId")},
            "None",
            "Pal unique NPC ID"
        );
        set_integer(
            m_impl->initialize_character,
            initialize.data(),
            {STR("Level")},
            level,
            "Pal level"
        );
        set_player_guid(
            m_impl->initialize_character,
            initialize.data(),
            parse_player_guid(player_id)
        );
        set_bool(
            m_impl->initialize_character,
            initialize.data(),
            {STR("DisableRandomPassiveSkill")},
            options.passive_skills.has_value(),
            "disable-random-passive flag"
        );
        set_bool(
            m_impl->initialize_character,
            initialize.data(),
            {STR("RarePalAble")},
            false,
            "rare-Pal flag"
        );
        initialize.call(m_impl->utility_cdo);
        if (!bool_return(initialize))
        {
            throw std::runtime_error(
                "Palworld rejected the requested Pal initialization."
            );
        }

        auto* initialized_property = require_property(
            m_impl->initialize_character,
            {STR("outParameter")},
            "Pal initialization parameter"
        );
        auto* initialized_struct =
            CastField<FStructProperty>(initialized_property);
        auto* initialized_type = initialized_struct
            ? initialized_struct->GetStruct().Get()
            : nullptr;
        if (!initialized_type)
        {
            throw std::runtime_error(
                "The reflected Pal initialization result is not a struct."
            );
        }
        auto* initialized_value = property_value(
            initialized_property,
            initialize.data()
        );
        if (options.passive_skills)
        {
            set_name_array(
                initialized_type,
                initialized_value,
                {STR("PassiveSkillList")},
                *options.passive_skills,
                "Pal passive skills"
            );
        }
        if (options.iv_hp)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Talent_HP")},
                *options.iv_hp,
                "Pal HP individual value"
            );
        }
        if (options.iv_melee)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Talent_Melee")},
                *options.iv_melee,
                "Pal melee individual value"
            );
        }
        if (options.iv_shot)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Talent_Shot")},
                *options.iv_shot,
                "Pal shot individual value"
            );
        }
        if (options.iv_defense)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Talent_Defense")},
                *options.iv_defense,
                "Pal defense individual value"
            );
        }
        if (options.condensation)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Rank")},
                *options.condensation,
                "Pal condensation rank"
            );
        }
        if (options.soul_hp)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Rank_HP")},
                *options.soul_hp,
                "Pal HP soul enhancement"
            );
        }
        if (options.soul_attack)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Rank_Attack")},
                *options.soul_attack,
                "Pal attack soul enhancement"
            );
        }
        if (options.soul_defense)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Rank_Defence")},
                *options.soul_defense,
                "Pal defense soul enhancement"
            );
        }
        if (options.soul_craft_speed)
        {
            set_integer(
                initialized_type,
                initialized_value,
                {STR("Rank_CraftSpeed")},
                *options.soul_craft_speed,
                "Pal work-speed soul enhancement"
            );
        }
        const auto parameter_initialization_completed_at =
            std::chrono::steady_clock::now();

        auto* manager = m_impl->character_manager(controller);
        const auto manager_lookup_completed_at =
            std::chrono::steady_clock::now();
        const auto callback_probe_sequence =
            m_impl->begin_pal_grant_callback_probe(
                player_state,
                player_id
            );
        Invocation create(m_impl->create_individual, true);
        copy_struct_value(
            m_impl->initialize_character,
            initialize.data(),
            {STR("outParameter")},
            m_impl->create_individual,
            create.data(),
            {STR("InitParameter")},
            "Pal initialization parameter"
        );
        bind_delegate(
            m_impl->create_individual,
            create.data(),
            {STR("spawnCallback"), STR("SpawnCallback")},
            player_state,
            m_impl->attach_granted_individual,
            "Pal creation callback"
        );
        create.call(manager);
        auto* handle = object_return(create);
        if (!handle || !UObject::IsReal(handle))
        {
            throw std::runtime_error(
                "Palworld did not create an authoritative Pal handle."
            );
        }
        const auto create_individual_completed_at =
            std::chrono::steady_clock::now();
        const auto callback_diagnostics =
            m_impl->pal_grant_callback_diagnostics(
                callback_probe_sequence
            );

        auto ivs = nlohmann::json::object();
        if (options.iv_hp)
        {
            ivs["hp"] = *options.iv_hp;
        }
        if (options.iv_shot)
        {
            ivs["shot"] = *options.iv_shot;
        }
        if (options.iv_defense)
        {
            ivs["defense"] = *options.iv_defense;
        }
        auto response_result = nlohmann::json{
            {"playerId", player_id},
            {"characterId", character_id},
            {"level", level},
            {"count", 1},
            {
                "runtimeFunction",
                "PalUtility:GetInitializedCharacterSaveParemter"
                " -> PalCharacterManager:CreateIndividual"
                "(spawnCallback=PalPlayerState:"
                "OnCreatedGrantedIndividualHandle_ServerInternal"
                ")"
            },
            {"requestedLevel", level},
            {"levelControlled", false},
            {"accepted", true},
            {"handleCreated", true},
            {"effectVerified", false},
            {"verificationScope", "create-individual-return"},
            {"persistenceVerified", false},
            {"retrySafe", false},
            {"callbackDiagnostics", callback_diagnostics},
            {"ivs", std::move(ivs)},
            {
                "timingsMs",
                {
                    {
                        "playerLookup",
                        std::chrono::duration<double, std::milli>(
                            player_lookup_completed_at - started_at
                        ).count()
                    },
                    {
                        "storageLookup",
                        std::chrono::duration<double, std::milli>(
                            storage_lookup_completed_at
                            - player_lookup_completed_at
                        ).count()
                    },
                    {
                        "slotInspection",
                        std::chrono::duration<double, std::milli>(
                            slot_inspection_completed_at
                            - storage_lookup_completed_at
                        ).count()
                    },
                    {
                        "parameterInitialization",
                        std::chrono::duration<double, std::milli>(
                            parameter_initialization_completed_at
                            - slot_inspection_completed_at
                        ).count()
                    },
                    {
                        "managerLookup",
                        std::chrono::duration<double, std::milli>(
                            manager_lookup_completed_at
                            - parameter_initialization_completed_at
                        ).count()
                    },
                    {
                        "createIndividual",
                        std::chrono::duration<double, std::milli>(
                            create_individual_completed_at
                            - manager_lookup_completed_at
                        ).count()
                    },
                    {
                        "total",
                        std::chrono::duration<double, std::milli>(
                            create_individual_completed_at - started_at
                        ).count()
                    },
                }
            },
        };
        response_result["unrestricted"] = options.unrestricted;
        if (options.passive_skills)
        {
            response_result["passiveSkills"] =
                *options.passive_skills;
        }
        auto enhancements = nlohmann::json::object();
        if (options.condensation)
        {
            enhancements["condensation"] = *options.condensation;
        }
        if (options.soul_hp)
        {
            enhancements["soulHp"] = *options.soul_hp;
        }
        if (options.soul_attack)
        {
            enhancements["soulAttack"] = *options.soul_attack;
        }
        if (options.soul_defense)
        {
            enhancements["soulDefense"] = *options.soul_defense;
        }
        if (options.soul_craft_speed)
        {
            enhancements["soulCraftSpeed"] =
                *options.soul_craft_speed;
        }
        response_result["enhancements"] = std::move(enhancements);
        return {
            {"state", "completed"},
            {"result", std::move(response_result)},
        };
    }
} // namespace pal_editor_bridge::ue4ss
