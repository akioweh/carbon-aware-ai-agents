#ifndef SCHEDULE_BLOCK
#define SCHEDULE_BLOCK
#pragma once

#include "Serializable.hpp"
#include <chrono>
#include <string>
#include <utils/Utils.hpp>

namespace scheduler {

/**
 * @class ScheduleBlock
 * @brief The atomic unit of a schedule, representing an amount of load at a
 * given location and time. Aligns with API definition.
 */
class ScheduleBlock {
  public:
    std::chrono::system_clock::time_point timestamp;
    std::string jobId;
    std::string location;
    double additionalLoad{}; /// thats what we scheduled
};

inline auto operator<=>(const ScheduleBlock &lhs, const ScheduleBlock &rhs)
    -> auto {
    return lhs.timestamp <=> rhs.timestamp;
}

inline auto f_toJson(const ScheduleBlock &obj) -> Json::Value {
    auto res = Json::Value{};
    res["timestamp"] = scheduler::utils::toIso8601(obj.timestamp);
    res["job_id"] = obj.jobId;
    res["additional_load"] = obj.additionalLoad;
    res["location"] = obj.location;
    return res;
}

static_assert(Serializable<ScheduleBlock>);

} // namespace scheduler

#endif // SCHEDULE_BLOCK
