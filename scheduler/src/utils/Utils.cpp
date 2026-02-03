#include "Utils.hpp"
#include <expected>
#include <sstream>

namespace scheduler::utils {
using namespace std;
using namespace drogon;

using SysTime = chrono::system_clock::time_point;

auto toIso8601(const SysTime &timePoint) -> string {
    // remove sub-second precision
    auto tp_sec = chrono::floor<chrono::seconds>(timePoint);
    // %F = YYYY-MM-DD
    // %T = HH:MM:SS
    // Z  = Literal Z suffix
    return format("{:%FT%TZ}", tp_sec);
}

auto parseIso8601(const string &timestamp) -> expected<SysTime, string> {

    chrono::sys_seconds res;
    istringstream iss(timestamp);

    if (iss >> chrono::parse("%FT%TZ", res))
        return res;
    // try with explicit offset
    iss.clear();
    iss.str(timestamp);
    if (iss >> chrono::parse("%FT%T%Ez", res))
        return res;
    iss.clear();
    iss.str(timestamp);
    if (iss >> chrono::parse("%FT%T%z", res))
        return res;

    return unexpected("Failed to parse ISO8601 string: " + timestamp);
}

auto makeGetRequest(const string &host, const string &path)
    -> Task<shared_ptr<Json::Value>> {
    auto client = HttpClient::newHttpClient(host);
    auto request = HttpRequest::newHttpRequest();
    request->setMethod(Get);
    request->setPath(path);

    HttpResponsePtr response;
    try {
        response = co_await client->sendRequestCoro(request);

    } catch (const exception &e) {
        LOG_ERROR << "something is not yes, maybe run python API? XD "
                  << e.what();
        co_return nullptr;
    }

    if (!response || response->getStatusCode() != drogon::k200OK) {
        LOG_ERROR << "response is null or has a code different than 200";
        co_return nullptr;
    }

    auto jsonResponsePtr = response->jsonObject();
    if (!jsonResponsePtr) {
        LOG_ERROR << "couldnt transform to JSON the response";
        co_return nullptr;
    }

    co_return make_shared<Json::Value>(*jsonResponsePtr);
}
} // namespace scheduler::utils
