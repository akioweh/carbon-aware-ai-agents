#ifndef SCHEDULER_JOB_REQUEST_HPP
#define SCHEDULER_JOB_REQUEST_HPP
#include "utils/HardwareConversion.hpp"
#pragma once

#include "exceptions/ValidationException.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>
#include <optional>
#include <string>

namespace scheduler {

/**
 * This is not actually used, but it represents what request as a json is
 * submitted to the endpoint. We then transform it to our format.
 *
 * NOTE: i think this is useful for saving user job input to redisplay in UI?
 */
struct RawJobRequest {
    using time_t = std::chrono::sys_time<std::chrono::minutes>;

    std::string job_type;
    time_t earliest_start;
    time_t latest_finish;
    std::optional<std::string> preferred_datacenter;
    std::string gpu_type;
    int length; // length of computation in minutes
    int gpu_count;
    int model_size;
};

/**
 * @class JobRequest
 * @brief Scheduler input parameters.
 */
struct JobRequest {
    using time_t = std::chrono::sys_time<std::chrono::minutes>;

    // TODO: make job_type do something or remove it.
    std::string job_type;
    double workload_amount; // FLO (floating point operations)
    time_t earliest_start;
    time_t latest_finish;
    // TODO: this is actually hardware-specific (so should depend on DC)
    double startup_overhead; // same unit as workload_amount
    double max_load;         // parallelization limit: max FLO-per-5-minutes
    std::optional<std::string> preferred_datacenter;
    // API: ignore the additional_constraints field (for forwards compatibility)
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
         {"job_type", "earliest_start", "latest_finish", "gpu_type",
          "gpu_count", "model_size", "length"}) {
        if (json[field].isNull())
            throw scheduler::exceptions::ValidationException(
                "Field '" + std::string(field) + "' cannot be null");
    }
    if (!json["job_type"].isString())
        throw scheduler::exceptions::ValidationException(
            "Field 'job_type' must be a string");
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
    const auto jobHardwareSpecific =
        scheduler::utils::convertRawJobRequest(json);

    try {
        std::optional<std::string> pref_dc = std::nullopt;
        if (!json["preferred_datacenter"].isNull()) {
            if (!json["preferred_datacenter"].isString()) {
                throw scheduler::exceptions::ValidationException(
                    "Field 'preferred_datacenter' must be a string");
            }
            pref_dc = json["preferred_datacenter"].asString();
        }

        return scheduler::JobRequest{
            .job_type = json["job_type"].asString(),
            .workload_amount = jobHardwareSpecific.workload_amount,
            .earliest_start = earliest_start_opt.value(),
            .latest_finish = latest_finish_opt.value(),
            .startup_overhead = jobHardwareSpecific.startup_overhead,
            .max_load = jobHardwareSpecific.max_load,
            .preferred_datacenter = std::move(pref_dc),
        };
    } catch (const std::exception &e) {
        throw scheduler::exceptions::ValidationException("Invalid body");
    }
}
} // namespace drogon

#endif // SCHEDULER_JOB_REQUEST_HPP
