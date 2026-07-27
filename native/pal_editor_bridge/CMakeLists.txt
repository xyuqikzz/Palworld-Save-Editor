cmake_minimum_required(VERSION 3.22)

project(PalEditorBridgeCore LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_Declare(
    cpp_httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG 62d899feac3cf9215a55f2b43da250fdd98d2156
    GIT_SHALLOW TRUE
)

set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(nlohmann_json cpp_httplib)

add_library(PalEditorBridgeCore STATIC
    src/bridge_core.cpp
)
target_include_directories(PalEditorBridgeCore PUBLIC include)
target_link_libraries(PalEditorBridgeCore
    PUBLIC
        nlohmann_json::nlohmann_json
        httplib::httplib
)
target_compile_definitions(PalEditorBridgeCore PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)

if(WIN32)
    target_link_libraries(PalEditorBridgeCore PRIVATE bcrypt)
endif()

option(PAL_EDITOR_BRIDGE_BUILD_TESTS "Build bridge core tests" ON)
if(PAL_EDITOR_BRIDGE_BUILD_TESTS)
    enable_testing()
    add_executable(PalEditorBridgeCoreTests tests/bridge_core_tests.cpp)
    target_link_libraries(PalEditorBridgeCoreTests PRIVATE PalEditorBridgeCore)
    add_test(NAME PalEditorBridgeCoreTests COMMAND PalEditorBridgeCoreTests)
endif()

set(
    PAL_EDITOR_BRIDGE_UE4SS_ROOT
    ""
    CACHE PATH
    "Optional path to an RE-UE4SS checkout for building the C++ mod"
)
if(PAL_EDITOR_BRIDGE_UE4SS_ROOT)
    if(NOT EXISTS "${PAL_EDITOR_BRIDGE_UE4SS_ROOT}/CMakeLists.txt")
        message(FATAL_ERROR "PAL_EDITOR_BRIDGE_UE4SS_ROOT is not an RE-UE4SS checkout")
    endif()
    add_subdirectory(
        "${PAL_EDITOR_BRIDGE_UE4SS_ROOT}"
        "${CMAKE_CURRENT_BINARY_DIR}/RE-UE4SS"
        EXCLUDE_FROM_ALL
    )
    add_subdirectory(ue4ss)
endif()
