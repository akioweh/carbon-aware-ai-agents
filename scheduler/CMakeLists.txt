cmake_minimum_required(VERSION 4.2)
project(scheduler)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON CACHE INTERNAL "") # force c++23 in cache
set(CMAKE_CXX_SCAN_FOR_MODULES OFF) # disable modules to use ccache

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# machine arch control: defaults to native for auto-optimization on dev machines
# Can be overridden via presets or -DSCHEDULER_ARCH=x86-64|x86-64-v3|x86-64-v4|native
set(SCHEDULER_ARCH "native" CACHE STRING "Target microarchitecture level")

add_library(scheduler_options INTERFACE)
target_compile_options(scheduler_options INTERFACE
  -Wall -Wextra -Wpedantic -Wno-unknown-pragmas)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(scheduler_options INTERFACE -march=${SCHEDULER_ARCH})
elseif(MSVC)
  if(SCHEDULER_ARCH STREQUAL "x86-64-v4")
    target_compile_options(scheduler_options INTERFACE /arch:AVX512)
  elseif(SCHEDULER_ARCH STREQUAL "x86-64-v3")
    target_compile_options(scheduler_options INTERFACE /arch:AVX2)
  endif()
endif()

find_package(Drogon CONFIG REQUIRED)

add_subdirectory(src)

add_executable(scheduler main.cpp)
target_link_libraries(scheduler PRIVATE scheduler_core scheduler_options)

configure_file(config.json ${CMAKE_CURRENT_BINARY_DIR}/config.json COPYONLY)

option(BUILD_TESTING "Build tests" ON)

if(BUILD_TESTING)
  enable_testing()
  add_subdirectory(tests)
endif()

# copy compile_commands.json to root for clangd
if(CMAKE_EXPORT_COMPILE_COMMANDS)
  add_custom_target(CopyCompileCommands ALL
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${CMAKE_BINARY_DIR}/compile_commands.json"
    "${CMAKE_SOURCE_DIR}/compile_commands.json"
    COMMENT "Copy compile_commands.json to root for clangd"
    VERBATIM
  )
endif()
