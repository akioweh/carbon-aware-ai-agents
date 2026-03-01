#include "exceptions/ExceptionHandler.hpp"
#include <drogon/drogon.h>

#ifdef _WIN32
#include <windows.h>
#endif // _WIN32

constexpr auto PORT = 6969;

auto main() -> int {
    drogon::app().loadConfigFile("config.json");
    drogon::app().addListener("0.0.0.0", PORT);
    scheduler::exceptions::registerExceptionHandler();

    drogon::app().run();

#ifdef _WIN32
    TerminateProcess(GetCurrentProcess(), 0);
#endif // _WIN32
}
