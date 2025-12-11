#include <drogon/drogon.h>

using namespace drogon;

auto main() -> int {
    app()
        .setLogPath("./")
        .setLogLevel(trantor::Logger::kWarn)
        .addListener("0.0.0.0", 80)
        .setThreadNum(16)
        .run();
}
