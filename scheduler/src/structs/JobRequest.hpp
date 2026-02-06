#ifndef JOB_REQUEST
#define JOB_REQUEST
#pragma once

#include "exceptions/ValidationException.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <drogon/HttpRequest.h>
#include <string>

/**
 * @class JobRequest
 * @brief Scheduler input parameters as per API definition.
 */
struct JobRequest {
    std::string job_type;
    double workload_amount;
    std::chrono::system_clock::time_point earliest_start;
    std::chrono::system_clock::time_point latest_finish;
};

namespace drogon {
template <> inline auto fromRequest(const HttpRequest &req) -> JobRequest {
    const auto &json_ptr = req.getJsonObject();
    if (!json_ptr)
        throw ValidationException("JSON body is required");
    const auto &json = *json_ptr;
    for (const auto &field :
         {"job_type", "workload_amount", "earliest_start", "latest_finish"}) {
        if (json[field].isNull())
            throw ValidationException("Field '" + std::string(field) +
                                      "' cannot be null");
    }
    if (!json["job_type"].isString())
        throw ValidationException("Field 'job_type' must be a string");
    if (!json["workload_amount"].isNumeric())
        throw ValidationException("Field 'workload_amount' must be a number");
    if (!json["earliest_start"].isString())
        throw ValidationException("Field 'earliest_start' must be a string");
    if (!json["latest_finish"].isString())
        throw ValidationException("Field 'latest_finish' must be a string");
    const auto earliest_start_opt =
        scheduler::utils::parseIso8601(json["earliest_start"].asString());
    if (!earliest_start_opt)
        throw ValidationException("Invalid earliest_start time format: " +
                                  earliest_start_opt.error());
    const auto latest_finish_opt =
        scheduler::utils::parseIso8601(json["latest_finish"].asString());
    if (!latest_finish_opt)
        throw ValidationException("Invalid latest_finish time format: " +
                                  latest_finish_opt.error());
    try {
        const auto workload_amount = json["workload_amount"].asDouble();
        if (workload_amount < 0.)
            throw ValidationException("workload_amount must be non-negative");
        return JobRequest{.job_type = json["job_type"].asString(),
                          .workload_amount = workload_amount,
                          .earliest_start = earliest_start_opt.value(),
                          .latest_finish = latest_finish_opt.value()};
    } catch (const std::exception &e) {
        throw ValidationException("Invalid body");
    }
}
} // namespace drogon

#endif
