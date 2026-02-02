#ifndef UTILS
#define UTILS

#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <expected>
#include <json/value.h>
#include <string>
#include <trantor/utils/Date.h>

namespace scheduler::utils {
auto parseIso8601(const std::string &timestamp)
    -> std::expected<std::chrono::system_clock::time_point, std::string>;
auto toIso8601(const std::chrono::system_clock::time_point &timePoint)
    -> std::string;

auto makeGetRequest(const std::string &host, const std::string &path)
    -> drogon::Task<std::shared_ptr<Json::Value>>;

auto getPostGreDateFormat(
    const std::chrono::system_clock::time_point &timestamp) -> trantor::Date;
}; // namespace scheduler::utils

#endif
