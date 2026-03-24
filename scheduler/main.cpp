#include "exceptions/ExceptionHandler.hpp"
#include "utils/Config.hpp"
#include <drogon/drogon.h>

#ifdef _WIN32
#include <windows.h>
#endif // _WIN32

auto main() -> int {
    auto config = scheduler::utils::loadConfig("config.json");
    drogon::app().loadConfigJson(config);
    scheduler::exceptions::registerExceptionHandler();
    drogon::app().run();

#ifdef _WIN32
    // hangs on windows due to threading model issues
    TerminateProcess(GetCurrentProcess(), 0);
#endif // _WIN32
}
