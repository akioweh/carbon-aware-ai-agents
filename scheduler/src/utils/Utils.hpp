#ifndef SCHEDULER_UTILS_HPP
#define SCHEDULER_UTILS_HPP
#pragma once

#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <expected>
#include <json/value.h>
#include <string>
#include <trantor/utils/Date.h>

namespace scheduler::utils {
template <typename precision = std::chrono::seconds>
auto toIso8601(const auto &timePoint) -> std::string {
    auto tp_sec = std::chrono::floor<precision>(timePoint);
    // %F = YYYY-MM-DD
    // %T = HH:MM:SS
    // Z  = Literal Z suffix
    return format("{:%FT%TZ}", tp_sec);
}

// time_t determines precision
template <typename time_t = std::chrono::sys_time<std::chrono::minutes>>
auto parseIso8601(const std::string &timestamp)
    -> std::expected<time_t, std::string> {

    constexpr auto formats = std::array{
        "%FT%TZ",   // with literal Z
        "%FT%T%Ez", // with explicit +hhmm offset
        "%FT%T%z",  // with explicit +hh:mm offset
        "%FT%T",    // no offset, assume UTC
        "%c",       "%Ec",
    };

    std::chrono::sys_time<std::chrono::nanoseconds>
        res; // nano to parse decimals
    std::istringstream iss(timestamp);

    for (const auto &fmt : formats) {
        iss.clear();
        iss.str(timestamp);
        if (iss >> std::chrono::parse(fmt, res))
            return std::chrono::floor<typename time_t::duration>(res);
    }

    return std::unexpected("Failed to parse ISO8601 string: " + timestamp);
}

auto makeGetRequest(const std::string &host, const std::string &path)
    -> drogon::Task<std::shared_ptr<Json::Value>>;

inline auto trantorToChrono(const trantor::Date &tDate)
    -> std::chrono::system_clock::time_point {
    return std::chrono::system_clock::time_point(
        std::chrono::microseconds{tDate.microSecondsSinceEpoch()});
}

inline auto
chronoToTrantor(const std::chrono::system_clock::time_point &timestamp)
    -> trantor::Date {
    auto micro_since_epoch =
        std::chrono::duration_cast<std::chrono::microseconds>(
            timestamp.time_since_epoch())
            .count();
    return trantor::Date(micro_since_epoch);
}

auto parseStringIDtoInt(const std::string &jobId) -> int;
auto parseIntToStringID(int jobId) -> std::string;

}; // namespace scheduler::utils

#endif // SCHEDULER_UTILS_HPP
