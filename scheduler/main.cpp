#include "Scheduler.hpp"
#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <Scheduler.hpp>
#include <drogon/drogon.h>
using namespace drogon;

constexpr auto PORT = 80;
constexpr auto N_THREADS = 8;

auto generateJobRequest(int seed) -> JobRequest {
    return JobRequest(1967344654, "NOT DEFINED", 1469000.0, seed);
}

auto main() -> int {
    drogon::app().setLogPath(".");

    Scheduler scheduler;

    drogon::async_run([&]() -> drogon::Task<> {
        std::cout << "Expected carbon emmissions: "
                  << co_await scheduler.calculateSchedule(generateJobRequest(1))
                  << std::endl;
        scheduler.show();
        drogon::app().quit();
        co_return;
    });

    drogon::app().run();
}
