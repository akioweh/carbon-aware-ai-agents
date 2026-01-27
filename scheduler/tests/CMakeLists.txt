project(scheduler_tests)

find_package(Boost REQUIRED CONFIG COMPONENTS unit_test_framework)

add_executable(prediction_api_test PredictionApiTest.cpp)

target_link_libraries(prediction_api_test PRIVATE scheduler_core Boost::unit_test_framework)

add_test(NAME prediction_api_test COMMAND prediction_api_test)
