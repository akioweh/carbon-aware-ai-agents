#ifndef TIME_INTERVAL_PARAMS_HPP
#define TIME_INTERVAL_PARAMS_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>

/**
 * @class TimeIntervalParams
 * @brief DTO for time interval parameters in API requests.
 *
 */
struct TimeIntervalParams {
    std::optional<std::chrono::system_clock::time_point> start;
    std::optional<std::chrono::system_clock::time_point> end;
};

namespace drogon {
template <>
inline auto fromRequest(const HttpRequest &req) -> TimeIntervalParams {
    auto params = req.getParameters();
    auto start = std::optional<std::chrono::system_clock::time_point>{};
    auto end = std::optional<std::chrono::system_clock::time_point>{};
    if (params.contains("start")) {
        const auto parse_res =
            scheduler::utils::parseIso8601(params.at("start"));
        if (!parse_res)
            throw ValidationException("Invalid start time format: " +
                                      parse_res.error());
        start = parse_res.value();
    }
    if (params.contains("end")) {
        const auto parse_res = scheduler::utils::parseIso8601(params.at("end"));
        if (!parse_res)
            throw ValidationException("Invalid end time format: " +
                                      parse_res.error());
        end = parse_res.value();
    }
    // if both start and end are provided, validate that start <= end
    if (start && end && *start > *end)
        throw ValidationException("Start time must be before end time");
    return TimeIntervalParams{.start = start, .end = end};
}
} // namespace drogon

#endif
