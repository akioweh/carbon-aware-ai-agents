#define BOOST_TEST_MODULE CoroTest

#include "exceptions/ExceptionHandler.hpp"
#include "utils/Coro.hpp"
#include <boost/test/unit_test.hpp>
#include <chrono>
#include <drogon/HttpController.h>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <filesystem>
#include <ranges>
#include <thread>

using namespace scheduler::coro;

drogon::Task<int> successTask(int val) { co_return val; }
drogon::Task<void> voidTask() { co_return; }
drogon::Task<int> failingTask() {
    throw std::runtime_error("Task Failed");
    co_return 0;
}

struct SchedulerGlobalFixture {
    SchedulerGlobalFixture() {
        // Ensure clean state
        if (std::filesystem::exists("scheduler_test.db")) {
            std::filesystem::remove("scheduler_test.db");
        }

        // Load test config
        drogon::app().loadConfigFile("config.test.json");

        // Register Exception Handler
        scheduler::exceptions::registerExceptionHandler();

        // Start the app in a thread
        t = std::jthread([]() -> void { drogon::app().run(); });

        // Wait for server to start
        using namespace std::chrono_literals;
        auto start = std::chrono::steady_clock::now();
        while (!drogon::app().isRunning()) {
            if (std::chrono::steady_clock::now() - start > 10s) {
                throw std::runtime_error("Timeout waiting for Drogon to start");
            }
            std::this_thread::sleep_for(10ms);
        }
    }

    ~SchedulerGlobalFixture() { drogon::app().quit(); }

    std::jthread t;
};

BOOST_TEST_GLOBAL_FIXTURE(SchedulerGlobalFixture);

BOOST_AUTO_TEST_SUITE(CoroLogicTests)

BOOST_AUTO_TEST_CASE(test_when_all_variadic_success) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        auto [a, b] = co_await when_all(successTask(10), successTask(20));
        BOOST_CHECK_EQUAL(a, 10);
        BOOST_CHECK_EQUAL(b, 20);
    }());
}

BOOST_AUTO_TEST_CASE(test_when_all_mixed_types_with_void) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        // void tasks should result in std::monostate in the tuple[cite: 7]
        auto [val, empty] = co_await when_all(successTask(100), voidTask());
        BOOST_CHECK_EQUAL(val, 100);
        static_assert(std::is_same_v<decltype(empty), std::monostate>);

        BOOST_CHECK_EQUAL(sizeof(empty), 1);
    }());
}

BOOST_AUTO_TEST_CASE(test_when_all_exception_propagation) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        // By default, when_all should rethrow the captured exception[cite: 7]
        BOOST_CHECK_THROW(co_await when_all(successTask(1), failingTask()),
                          std::runtime_error);
    }());
}

BOOST_AUTO_TEST_CASE(test_when_all_return_exceptions_flag) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        // With return_exceptions = true, we get std::expected objects[cite: 7]
        auto [res1, res2] = co_await scheduler::coro::when_all<true>(
            successTask(1), failingTask());

        BOOST_CHECK(res1.has_value());
        BOOST_CHECK_EQUAL(res1.value(), 1);
        BOOST_CHECK(!res2.has_value()); // res2 contains the exception_ptr
    }());
}

BOOST_AUTO_TEST_SUITE_END()
