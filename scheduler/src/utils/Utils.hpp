#ifndef UTILS
#define UTILS

#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <expected>
#include <json/value.h>
#include <string>

class Utils {
  public:
    static auto parseIso8601(const std::string &timestamp)
        -> std::expected<std::chrono::system_clock::time_point, std::string>;
    static auto
    toIso8601(const std::chrono::system_clock::time_point &timePoint)
        -> std::string;

    static auto makeGetRequest(const std::string &host, const std::string &path)
        -> drogon::Task<std::shared_ptr<Json::Value>>;
};

#endif
