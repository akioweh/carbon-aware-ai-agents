#ifndef SCHEDULER_JOB_REQUEST_HPP
#define SCHEDULER_JOB_REQUEST_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>
#include <string>

namespace scheduler {
/**
 * @class JobRequest
 * @brief Scheduler input parameters as per API definition.
 */
struct JobRequest {
    using time_t = std::chrono::sys_time<std::chrono::minutes>;

    std::string job_type;
    double workload_amount;
    time_t earliest_start;
    time_t latest_finish;
};
} // namespace scheduler

namespace drogon {
template <>
inline auto fromRequest(const HttpRequest &req) -> scheduler::JobRequest {
    const auto &json_ptr = req.getJsonObject();
    if (!json_ptr)
        throw scheduler::exceptions::ValidationException(
            "JSON body is required");
    const auto &json = *json_ptr;
    for (const auto &field :
         {"job_type", "workload_amount", "earliest_start", "latest_finish"}) {
        if (json[field].isNull())
            throw scheduler::exceptions::ValidationException(
                "Field '" + std::string(field) + "' cannot be null");
    }
    if (!json["job_type"].isString())
        throw scheduler::exceptions::ValidationException(
            "Field 'job_type' must be a string");
    if (!json["workload_amount"].isNumeric())
        throw scheduler::exceptions::ValidationException(
            "Field 'workload_amount' must be a number");
    if (!json["earliest_start"].isString())
        throw scheduler::exceptions::ValidationException(
            "Field 'earliest_start' must be a string");
    if (!json["latest_finish"].isString())
        throw scheduler::exceptions::ValidationException(
            "Field 'latest_finish' must be a string");
    const auto earliest_start_opt =
        scheduler::utils::parseIso8601(json["earliest_start"].asString());
    if (!earliest_start_opt)
        throw scheduler::exceptions::ValidationException(
            "Invalid earliest_start time format: " +
            earliest_start_opt.error());
    const auto latest_finish_opt =
        scheduler::utils::parseIso8601(json["latest_finish"].asString());
    if (!latest_finish_opt)
        throw scheduler::exceptions::ValidationException(
            "Invalid latest_finish time format: " + latest_finish_opt.error());
    if (latest_finish_opt.value() < earliest_start_opt.value())
        throw scheduler::exceptions::ValidationException(
            "latest_finish must be after earliest_start");
    if (latest_finish_opt.value() < std::chrono::system_clock::now()) {
        throw scheduler::exceptions::ValidationException(
            "End time must be in the future!");
    }
    try {
        const auto workload_amount = json["workload_amount"].asDouble();
        if (workload_amount < 0.)
            throw scheduler::exceptions::ValidationException(
                "workload_amount must be non-negative");
        return scheduler::JobRequest{
            .job_type = json["job_type"].asString(),
            .workload_amount = workload_amount,
            .earliest_start = earliest_start_opt.value(),
            .latest_finish = latest_finish_opt.value()};
    } catch (const std::exception &e) {
        throw scheduler::exceptions::ValidationException("Invalid body");
    }
}
} // namespace drogon

#endif // SCHEDULER_JOB_REQUEST_HPP
