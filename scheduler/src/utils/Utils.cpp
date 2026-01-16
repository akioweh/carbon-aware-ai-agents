#include "Utils.hpp"

namespace scheduler::utils {
using namespace std;
using namespace drogon;
auto parseTimestampSeconds(const string &timestamp) -> long long {
    // chatgpted - later i can try importing Howard Hinnant’s date library
    // also i will probably move this to a utils package
    string datetime = timestamp.substr(0, 19);
    tm tm = {};
    istringstream ss(datetime);
    ss >> get_time(&tm, "%Y-%m-%dT%H:%M:%S");
    time_t tt = timegm(&tm);
    return static_cast<long long>(tt);
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
