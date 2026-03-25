#define BOOST_TEST_MODULE CoroTest

#include "utils/Coro.hpp"
#include <boost/test/unit_test.hpp>
#include <drogon/HttpController.h>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <ranges>

using namespace scheduler::coro;

auto successTask(int val) -> drogon::Task<int> { co_return val; }
auto voidTask() -> drogon::Task<void> { co_return; }
auto failingTask() -> drogon::Task<int> {
    throw std::runtime_error("Task Failed");
    co_return 0;
}

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
        auto [val, empty] = co_await when_all(successTask(100), voidTask());
        BOOST_CHECK_EQUAL(val, 100);
        static_assert(std::is_same_v<decltype(empty), std::monostate>);

        BOOST_CHECK_EQUAL(sizeof(empty), 1);
    }());
}

BOOST_AUTO_TEST_CASE(test_when_all_exception_propagation) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        BOOST_CHECK_THROW(co_await when_all(successTask(1), failingTask()),
                          std::runtime_error);
    }());
}

BOOST_AUTO_TEST_CASE(test_when_all_return_exceptions_flag) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        auto [res1, res2] = co_await scheduler::coro::when_all<true>(
            successTask(1), failingTask());

        BOOST_CHECK(res1.has_value());
        BOOST_CHECK_EQUAL(res1.value(), 1);
        BOOST_CHECK(!res2.has_value()); // res2 contains the exception_ptr
    }());
}

BOOST_AUTO_TEST_SUITE_END()
