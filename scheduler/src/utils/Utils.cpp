#include "Utils.hpp"
#include "exceptions/NetworkException.hpp"
#include "exceptions/ValidationException.hpp"

namespace scheduler::utils {
using namespace std;
using namespace drogon;

auto makeGetRequest(const string &host, const string &path, double timeout)
    -> Task<shared_ptr<Json::Value>> {
    auto client = HttpClient::newHttpClient(host);

    auto request = HttpRequest::newHttpRequest();
    request->setMethod(Get);
    request->setPath(path);

    HttpResponsePtr response;
    try {
        response = co_await client->sendRequestCoro(request, timeout);

    } catch (const exception &e) {
        LOG_ERROR << "something is not yes, maybe run python API? XD "
                  << e.what();
        throw exceptions::NetworkException(
            "Request to the greeness API timed out!");
    }

    if (!response || response->getStatusCode() != drogon::k200OK) {
        LOG_ERROR << "response is null or has a code different than 200";
        throw exceptions::NetworkException("Third party API failed");
    }

    auto jsonResponsePtr = response->jsonObject();
    if (!jsonResponsePtr) {
        LOG_ERROR << "couldnt transform to JSON the response";
        throw exceptions::NetworkException("Third party API failed");
    }

    co_return make_shared<Json::Value>(*jsonResponsePtr);
}
auto trantorToChrono(const trantor::Date &tDate)
    -> std::chrono::system_clock::time_point {
    return std::chrono::system_clock::time_point(
        std::chrono::microseconds{tDate.microSecondsSinceEpoch()});
}
auto chronoToTrantor(const std::chrono::system_clock::time_point &timestamp)
    -> trantor::Date {
    auto micro_since_epoch =
        std::chrono::duration_cast<std::chrono::microseconds>(
            timestamp.time_since_epoch())
            .count();
    return trantor::Date(micro_since_epoch);
}

auto parseStringIDtoInt(const std::string &jobId) -> int {
    auto pos = jobId.find('-');
    if (pos == std::string::npos) {
        throw exceptions::ValidationException(
            "Invalid ID format: missing prefix separator");
    }
    int value = 0;
    auto res = std::from_chars(jobId.data() + pos + 1,
                               jobId.data() + jobId.size(), value);
    if (res.ec != std::errc()) {
        throw exceptions::ValidationException(
            "Invalid ID format: invalid number");
    }
    return value;
}

auto parseIntToStringID(int jobId) -> std::string {
    return "sched-" + std::to_string(jobId);
}

} // namespace scheduler::utils
