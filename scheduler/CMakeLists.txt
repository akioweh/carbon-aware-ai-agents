cmake_minimum_required(VERSION 4.2)
project(scheduler)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-mavx512f -mavx512bw -mavx512vl -mavx512dq)
elseif(MSVC)
    add_compile_options(/arch:AVX512)
endif()

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON CACHE INTERNAL "") # force c++23 in cache

add_compile_options(-Wall -Wextra -Wpedantic -Wno-unknown-pragmas)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Drogon CONFIG REQUIRED)

add_subdirectory(src)

add_executable(scheduler main.cpp)
target_link_libraries(scheduler PRIVATE scheduler_core)

enable_testing()
add_subdirectory(tests)

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