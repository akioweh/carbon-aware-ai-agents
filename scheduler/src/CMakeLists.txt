file(GLOB_RECURSE SRC_FILES CONFIGURE_DEPENDS "*.cpp")

add_library(scheduler_core OBJECT ${SRC_FILES})

target_include_directories(scheduler_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(scheduler_core PUBLIC Drogon::Drogon)
target_link_libraries(scheduler_core PUBLIC stdc++exp)
