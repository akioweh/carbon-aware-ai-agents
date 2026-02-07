project(scheduler_tests)

find_package(Boost REQUIRED CONFIG COMPONENTS unit_test_framework)

add_executable(api_client_test StatsAPIClientTest.cpp)
target_link_libraries(api_client_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME api_client_test COMMAND api_client_test)

add_executable(scheduler_algo_test SchedulerAlgoTest.cpp)
target_link_libraries(scheduler_algo_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME scheduler_algo_test COMMAND scheduler_algo_test)

add_executable(new_algo_test NewAlgoTest.cpp)
target_link_libraries(new_algo_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME new_algo_test COMMAND new_algo_test)

# Integration test with Mock Calendar
# We cannot link scheduler_core because we want to replace Calendar.cpp
# So we glob sources from src/ and exclude Calendar.cpp
file(GLOB_RECURSE SCHEDULER_SRC_FILES
    "${CMAKE_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_SOURCE_DIR}/src/*.cc"
)
list(FILTER SCHEDULER_SRC_FILES EXCLUDE REGEX ".*/Calendar.cpp$")

add_executable(scheduler_integration_test
    SchedulerIntegrationTest.cpp
    mocks/MockCalendar.cpp
    ${SCHEDULER_SRC_FILES}
)

# Include directories similar to scheduler_core
target_include_directories(scheduler_integration_test PRIVATE "${CMAKE_SOURCE_DIR}/src")

# Link dependencies (exclude PostgreSQL if not used by other parts, but Drogon might need it)
# We use Drogon::Drogon and Boost
target_link_libraries(scheduler_integration_test PRIVATE
    Drogon::Drogon
    Boost::unit_test_framework
    stdc++exp
)

add_test(NAME scheduler_integration_test COMMAND scheduler_integration_test)

# Copy config.test.json to the test directory
add_custom_command(TARGET scheduler_integration_test POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
    "${CMAKE_CURRENT_SOURCE_DIR}/config.test.json"
    "$<TARGET_FILE_DIR:scheduler_integration_test>/config.test.json"
)
