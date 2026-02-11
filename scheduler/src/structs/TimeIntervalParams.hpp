#ifndef SCHEDULER_TIME_INTERVAL_PARAMS_HPP
#define SCHEDULER_TIME_INTERVAL_PARAMS_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>

namespace scheduler {

/**
 * @class TimeIntervalParams
 * @brief DTO for time interval parameters in API requests.
 *
 */
struct TimeIntervalParams {
    std::optional<std::chrono::system_clock::time_point> start;
    std::optional<std::chrono::system_clock::time_point> end;
};

} // namespace scheduler

namespace drogon {
template <>
inline auto fromRequest(const HttpRequest &req)
    -> scheduler::TimeIntervalParams {
    const auto &params = req.getParameters();
    auto start = std::optional<std::chrono::system_clock::time_point>{};
    auto end = std::optional<std::chrono::system_clock::time_point>{};
    if (params.contains("start_time")) {
        const auto parse_res =
            scheduler::utils::parseIso8601(params.at("start_time"));
        if (!parse_res)
            throw scheduler::exceptions::ValidationException(
                "Invalid start time format: " + parse_res.error());
        start = parse_res.value();
    }
    if (params.contains("end_time")) {
        const auto parse_res =
            scheduler::utils::parseIso8601(params.at("end_time"));
        if (!parse_res)
            throw scheduler::exceptions::ValidationException(
                "Invalid end time format: " + parse_res.error());
        end = parse_res.value();
    }
    // if both start and end are provided, validate that start <= end
    if (start && end && *start > *end)
        throw scheduler::exceptions::ValidationException(
            "Start time must be before end time");
    return scheduler::TimeIntervalParams{.start = start, .end = end};
}
} // namespace drogon

#endif // SCHEDULER_TIME_INTERVAL_PARAMS_HPP
