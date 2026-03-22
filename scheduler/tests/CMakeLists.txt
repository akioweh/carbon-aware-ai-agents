project(scheduler_tests)

find_package(Boost REQUIRED CONFIG COMPONENTS unit_test_framework)

add_executable(api_client_test StatsAPIClientTest.cpp)
target_link_libraries(api_client_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME api_client_test COMMAND api_client_test)

add_executable(scheduler_algo_test SchedulerAlgoTest.cpp)
target_link_libraries(scheduler_algo_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME scheduler_algo_test COMMAND scheduler_algo_test)

add_executable(controller_deserialization_test ControllerDeserializationTest.cpp)
target_link_libraries(controller_deserialization_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME controller_deserialization_test COMMAND controller_deserialization_test)

add_executable(utils_test UtilsTest.cpp)
target_link_libraries(utils_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME utils_test COMMAND utils_test)

add_executable(coro_test CoroTests.cpp)
target_link_libraries(coro_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME coro_test COMMAND coro_test)

# Integration test with Mock Calendar
# We cannot link scheduler_core because we want to replace Calendar.cpp
# So we glob sources from src/ and exclude Calendar.cpp
file(GLOB_RECURSE SCHEDULER_SRC_FILES
    "${CMAKE_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_SOURCE_DIR}/src/*.cc"
)
list(FILTER SCHEDULER_SRC_FILES EXCLUDE REGEX ".*/Calendar.cpp$")

# Scheduling Queue tests
add_executable(queue_test 
    SchedulingQueueTests.cpp 
    mocks/MockCalendar.cpp
    ${SCHEDULER_SRC_FILES}
)
target_include_directories(queue_test PRIVATE "${CMAKE_SOURCE_DIR}/src")
target_link_libraries(queue_test PRIVATE 
    Drogon::Drogon 
    Boost::unit_test_framework 
    stdc++exp
)
add_test(NAME queue_test COMMAND queue_test)
# scheduling queue test end

#time gridder tests
add_executable(time_gridder 
    TimeGridderTest.cpp 
    mocks/MockCalendar.cpp
    ${SCHEDULER_SRC_FILES}
)
target_include_directories(time_gridder PRIVATE "${CMAKE_SOURCE_DIR}/src")
target_link_libraries(time_gridder PRIVATE 
    Drogon::Drogon 
    Boost::unit_test_framework 
    stdc++exp
)
add_test(NAME time_gridder COMMAND time_gridder)
# time gridder end

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
