#include <drogon/drogon.h>

using namespace drogon;

constexpr auto PORT = 80;
constexpr auto N_THREADS = 8;

auto main() -> int {
    app()
        .setLogPath("./")
        .setLogLevel(trantor::Logger::kWarn)
        .addListener("0.0.0.0", PORT)
        .setThreadNum(N_THREADS)
        .run();
}
