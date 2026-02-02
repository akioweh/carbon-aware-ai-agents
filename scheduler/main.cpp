#include "Scheduler.hpp"
#include "SchedulingQueue.hpp"
#include "controllers/ScheduleController.hpp"
#include <JobRequest.hpp>
#include <chrono>
#include <drogon/drogon.h>
#include <iostream>

#ifdef _WIN32
#include <windows.h>
#endif // _WIN32

using namespace drogon;

constexpr auto PORT = 6969;
constexpr auto N_THREADS = 8;

auto main() -> int {
    drogon::app().setLogPath(".");
    drogon::app().loadConfigFile("config.json");
    drogon::app().addListener("0.0.0.0", PORT);
    drogon::app().run();

#ifdef _WIN32
    TerminateProcess(GetCurrentProcess(), 0);
#endif // _WIN32
}
