cmake_minimum_required(VERSION 4.2)
project(scheduler)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON CACHE INTERNAL "") # force c++23 in cache

add_compile_options(-Wall -Wextra -Wpedantic -Wno-unknown-pragmas)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

file(GLOB_RECURSE SRC_FILES CONFIGURE_DEPENDS "src/*.cpp")
add_executable(scheduler main.cpp ${SRC_FILES})
target_include_directories(scheduler PRIVATE src)

target_link_libraries(scheduler PRIVATE stdc++exp) # g++ std23 stuff

find_package(Drogon CONFIG REQUIRED)
target_link_libraries(scheduler PRIVATE Drogon::Drogon)

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
