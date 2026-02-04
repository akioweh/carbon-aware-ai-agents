#include "exceptions/ValidationException.hpp"
#include <drogon/HttpAppFramework.h>
#include <drogon/drogon.h>

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

    auto default_exception_handler = drogon::app().getExceptionHandler();
    drogon::app().setExceptionHandler(
        [&default_exception_handler](
            const std::exception &e, const HttpRequestPtr &req,
            std::function<void(const HttpResponsePtr &)> &&callback) -> void {
            if (const auto *valEx =
                    dynamic_cast<const ValidationException *>(&e)) {
                auto resp = HttpResponse::newHttpResponse();
                resp->setStatusCode(k422UnprocessableEntity);
                Json::Value err;
                err["error"] = valEx->what();
                resp->setBody(err.toStyledString());
                resp->setContentTypeCode(CT_APPLICATION_JSON);
                callback(resp);
                return;
            }
            default_exception_handler(e, req, std::move(callback));
        });

    drogon::app().run();

#ifdef _WIN32
    TerminateProcess(GetCurrentProcess(), 0);
#endif // _WIN32
}
