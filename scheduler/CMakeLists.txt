cmake_minimum_required(VERSION 4.2)
project(scheduler)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON CACHE INTERNAL "") # force c++23 in cache

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_compile_options(-Wall -Wextra -Wpedantic -Wno-unknown-pragmas)

option(USE_NATIVE_ARCH "Optimize for this specific machine" ON)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  if(USE_NATIVE_ARCH)
    add_compile_options(-march=native)
  else()
    add_compile_options(-march=x86-64-v4)
  endif()
elseif(MSVC)
  add_compile_options(/arch:AVX512)
endif()

find_package(Drogon CONFIG REQUIRED)

add_subdirectory(src)

add_executable(scheduler main.cpp)
target_link_libraries(scheduler PRIVATE scheduler_core)

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
