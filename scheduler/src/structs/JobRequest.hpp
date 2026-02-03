#ifndef JOB_REQUEST
#define JOB_REQUEST
#pragma once

#include "utils/Utils.hpp"
#include <Serializable.hpp>
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
template <>
inline auto fromRequest(const HttpRequest &req) -> std::optional<JobRequest> {
    const auto &json_ptr = req.getJsonObject();
    if (!json_ptr)
        return {};
    const auto &json = *json_ptr;
    if (!json.isMember("job_type") || !json.isMember("workload_amount") ||
        !json.isMember("earliest_start") || !json.isMember("latest_finish"))
        return {};
    try {
        return JobRequest{
            .job_type = json["job_type"].asString(),
            .workload_amount = json["workload_amount"].asDouble(),
            .earliest_start = scheduler::utils::parseIso8601(
                                  json["earliest_start"].asString())
                                  .value(),
            .latest_finish =
                scheduler::utils::parseIso8601(json["latest_finish"].asString())
                    .value()};
    } catch (const std::exception &e) {
        return {};
    }
}
} // namespace drogon

#endif
