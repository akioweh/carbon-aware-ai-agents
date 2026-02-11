#ifndef SCHEDULER_SCHEDULE_RESULT_HPP
#define SCHEDULER_SCHEDULE_RESULT_HPP
#pragma once

#include "Serializable.hpp"
#include "structs/ScheduleBlock.hpp"

namespace scheduler {

/**
 * @class ScheduleImpact
 * @brief Environmental impact metrics for a schedule.
 *
 * Used by both internal scheduler output and API responses.
 */
struct ScheduleImpact {
    double carbon_intensity{};
    double total_emissions{};
    double sci{};
};

inline auto f_toJson(const ScheduleImpact &obj) -> Json::Value {
    auto res = Json::Value{};
    res["carbon_intensity"] = obj.carbon_intensity;
    res["total_emissions"] = obj.total_emissions;
    res["sci"] = obj.sci;
    return res;
}

static_assert(Serializable<ScheduleImpact>);

/**
 * @class ScheduleResult
 * @brief API DTO for the result of a scheduling operation.
 */
struct ScheduleResult {
    std::string jobId;
    std::vector<ScheduleBlock> schedule;
    ScheduleImpact impact{};
};

inline auto f_toJson(const ScheduleResult &obj) -> Json::Value {
    auto res = Json::Value{};
    res["schedule_id"] = obj.jobId;
    res["scheduled_blocks"] = Json::Value(Json::arrayValue);
    res["impact"] = toJson(obj.impact);
    for (const auto &block : obj.schedule)
        res["scheduled_blocks"].append(toJson(block));
    return res;
}

static_assert(Serializable<ScheduleResult>);

} // namespace scheduler

#endif // SCHEDULER_SCHEDULE_RESULT_HPP
