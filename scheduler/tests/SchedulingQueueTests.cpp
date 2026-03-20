#include <boost/test/tools/old/interface.hpp>
#include <drogon/utils/coroutine.h>
#include <trantor/utils/Logger.h>
#define BOOST_TEST_MODULE SchedulingQueueTest
#include "Scheduler.hpp"
#include "SchedulingQueue.hpp"
#include "exceptions/ExceptionHandler.hpp"
#include "utils/Coro.hpp"
#include <boost/test/unit_test.hpp>
#include <chrono>
#include <drogon/HttpController.h>
#include <drogon/drogon.h>
#include <filesystem>
#include <ranges>
#include <thread>
#include <vector>

using namespace scheduler::coro;

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

BOOST_AUTO_TEST_SUITE(QueueLogicTests)

// Test 1: High-Volume Success Stress Test
BOOST_AUTO_TEST_CASE(test_queue_concurrency_success) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        scheduler::JobRequest req;
        auto now = std::chrono::time_point_cast<std::chrono::minutes>(
            std::chrono::system_clock::now());

        req.job_type = "batch";
        req.workload_amount = 1000000.0;
        req.earliest_start = now + std::chrono::hours(1);
        req.latest_finish = now + std::chrono::hours(5);
        req.startup_overhead = 100.0;
        req.max_load = 5000.0;
        req.kwh_per_flo = 0.00001;

        // Prepare a vector of tasks without awaiting them yet
        std::vector<drogon::Task<scheduler::SchedulerOutput>> tasks;
        for (auto i : std::views::iota(0, 5)) {
            tasks.push_back(scheduler::schedulingQueue
                                .computeSchedule<scheduler::Scheduler>(req));
        }

        // Fire all 300 requests into the queue and wait for the aggregate
        // result
        auto results = co_await when_all(std::move(tasks));

        BOOST_CHECK_EQUAL(results.size(), 5);
        for (const auto &res : results) {
            BOOST_CHECK(!res.blocks.empty());
        }
    }());
}

// Test 2: High-Volume Exception Stress Test
BOOST_AUTO_TEST_CASE(test_queue_concurrency_exceptions) {
    drogon::sync_wait([]() -> drogon::Task<void> {
        scheduler::JobRequest invalidReq;
        auto now = std::chrono::time_point_cast<std::chrono::minutes>(
            std::chrono::system_clock::now());

        // Logic error to trigger Scheduler exceptions
        invalidReq.earliest_start = now + std::chrono::minutes(20);
        invalidReq.latest_finish = now + std::chrono::minutes(2);

        std::vector<drogon::Task<scheduler::SchedulerOutput>> tasks;
        for (auto i : std::views::iota(0, 30000)) {
            invalidReq.workload_amount = static_cast<double>(i + 1);
            tasks.push_back(
                scheduler::schedulingQueue
                    .computeSchedule<scheduler::Scheduler>(invalidReq));
        }

        // Use the 'return_exceptions' template parameter to capture errors
        // individually rather than rethrowing on the first failure.
        auto results = co_await when_all<true>(std::move(tasks));

        BOOST_CHECK_EQUAL(results.size(), 30000);
        int exception_count = 0;
        for (const auto &res : results) {
            if (!res.has_value()) {
                exception_count++;
            }
        }
        BOOST_CHECK_EQUAL(exception_count, 30000);
    }());
}

BOOST_AUTO_TEST_SUITE_END()