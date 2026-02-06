project(scheduler_tests)

find_package(Boost REQUIRED CONFIG COMPONENTS unit_test_framework)

add_executable(api_client_test StatsAPIClientTest.cpp)
target_link_libraries(api_client_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME api_client_test COMMAND api_client_test)

add_executable(scheduler_algo_test SchedulerAlgoTest.cpp)
target_link_libraries(scheduler_algo_test PRIVATE scheduler_core Boost::unit_test_framework)
add_test(NAME scheduler_algo_test COMMAND scheduler_algo_test)
