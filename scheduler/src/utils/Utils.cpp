#include "Utils.hpp"
#include "exceptions/ValidationException.hpp"
#include <expected>
#include <array>
#include <sstream>
#include <string_view>

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

    constexpr auto formats = array{
        "%FT%TZ"sv,
        "%FT%T%Ez"sv,
        "%FT%T%z"sv,
        "%FT%T"sv,
    };

    // with literal Z
    if (iss >> chrono::parse("%FT%TZ", res))
        return res;
    // explicit +hhmm offset
    iss.clear();
    iss.str(timestamp);
    if (iss >> chrono::parse("%FT%T%Ez", res))
        return res;
    // explicit +hh:mm offset
    iss.clear();
    iss.str(timestamp);
    if (iss >> chrono::parse("%FT%T%z", res))
        return res;
    // no offset, assume UTC
    iss.clear();
    iss.str(timestamp);
    if (iss >> chrono::parse("%FT%T", res))
        return res;

    return unexpected("Failed to parse ISO8601 string: " + timestamp);
}

auto trantorToChrono(const trantor::Date &tDate)
    -> std::chrono::system_clock::time_point {
    auto microseconds =
        std::chrono::microseconds(tDate.microSecondsSinceEpoch());
    return std::chrono::system_clock::time_point(microseconds);
}

auto chronoToTrantor(const std::chrono::system_clock::time_point &timestamp)
    -> trantor::Date {
    auto micro_since_epoch =
        std::chrono::duration_cast<std::chrono::microseconds>(
            timestamp.time_since_epoch())
            .count();
    return trantor::Date(micro_since_epoch);
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
