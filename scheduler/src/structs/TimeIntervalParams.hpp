#ifndef TIME_INTERVAL_PARAMS_HPP
#define TIME_INTERVAL_PARAMS_HPP
#pragma once

#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>

struct TimeIntervalParams {
    std::chrono::system_clock::time_point start;
    std::chrono::system_clock::time_point end;
};

namespace drogon {
template <>
inline auto fromRequest(const HttpRequest &req)
    -> std::optional<TimeIntervalParams> {
    const auto &json_ptr = req.getJsonObject();
    if (!json_ptr)
        return {};
    const auto &json = *json_ptr;
    if (!json.isMember("start") || !json.isMember("end"))
        return {};
    try {
        return TimeIntervalParams{
            .start = scheduler::utils::parseIso8601(json["start"].asString())
                         .value(),
            .end =
                scheduler::utils::parseIso8601(json["end"].asString()).value()};
    } catch (const std::exception &e) {
        return {};
    }
}
} // namespace drogon

#endif
