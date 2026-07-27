cmake_minimum_required(VERSION 3.22)

if(NOT TARGET UE4SS)
    message(FATAL_ERROR "PalEditorBridge must be added from an RE-UE4SS build.")
endif()

if(NOT TARGET PalEditorBridgeCore)
    add_subdirectory(
        "${CMAKE_CURRENT_LIST_DIR}/.."
        "${CMAKE_CURRENT_BINARY_DIR}/PalEditorBridgeCore"
    )
endif()

add_library(PalEditorBridge SHARED
    src/dllmain.cpp
    src/pal_editor_bridge_mod.cpp
    src/palworld_runtime.cpp
)
target_include_directories(PalEditorBridge PRIVATE include)
target_link_libraries(PalEditorBridge PRIVATE PalEditorBridgeCore UE4SS)
target_compile_definitions(PalEditorBridge PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
if(WIN32)
    target_link_libraries(PalEditorBridge PRIVATE bcrypt crypt32)
endif()
