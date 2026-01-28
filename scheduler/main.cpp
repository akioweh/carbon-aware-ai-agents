#include "Scheduler.hpp"
#include "SchedulingQueue.hpp"
#include "controllers/ScheduleController.hpp"
#include <JobRequest.hpp>
#include <PredictionApi.hpp>
#include <chrono>
#include <drogon/drogon.h>
#include <iostream>

#ifdef _WIN32
#include <windows.h>
#endif // _WIN32

using namespace drogon;

constexpr auto PORT = 6969;
constexpr auto N_THREADS = 8;

auto generateJobRequest(int seed) -> JobRequest {
    // using arbitrary timestamps
    auto now = std::chrono::system_clock::now();
    auto later = now + std::chrono::hours(24);
    return {"training", 1469000.0, now, later, "job-" + std::to_string(seed)};
}

auto main() -> int {
    drogon::app().setLogPath(".");

    /*
    drogon::async_run([&]() -> drogon::Task<> {
        auto [impact, dummy] =
            co_await schedulingQueue->computeSchedule(generateJobRequest(1));
        std::cout << "Expected carbon emmissions: " << impact.total_emissions
                  << '\n';
        std::cout << "Expected carbon intensity: " << impact.carbon_intensity
                  << '\n';
        std::cout << "SCI: " << impact.sci << '\n';

        for (auto i : dummy) {
            i.show();
        }
        drogon::app().quit();
        co_return;
    });
    */
    drogon::app().addListener("0.0.0.0", PORT);
    drogon::app().run();
#ifdef _WIN32
    TerminateProcess(GetCurrentProcess(), 0);
#endif // _WIN32
}
