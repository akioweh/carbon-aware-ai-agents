#ifndef SCHEDULER_SCHEDULE_RESULT_HPP
#define SCHEDULER_SCHEDULE_RESULT_HPP
#pragma once

#include "Serializable.hpp"
#include "structs/ScheduleBlock.hpp"
#include <optional>

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
 * @brief API DTO representing a pure, single schedule's data.
 */
struct ScheduleResult {
    std::string scheduleId;
    std::vector<ScheduleBlock> schedule;
    ScheduleImpact impact{};
};

inline auto f_toJson(const ScheduleResult &obj) -> Json::Value {
    auto res = Json::Value{};
    res["schedule_id"] = obj.scheduleId;
    res["scheduled_blocks"] = Json::Value(Json::arrayValue);
    res["impact"] = toJson(obj.impact);
    for (const auto &block : obj.schedule)
        res["scheduled_blocks"].append(toJson(block));
    return res;
}

static_assert(Serializable<ScheduleResult>);

/**
 * @class JobScheduleResponse
 * @brief API DTO for the complete result of a job placement.
 *        Includes the optimized schedule and optionally the unoptimized
 * baseline.
 */
struct JobScheduleResponse {
    std::string scheduleId;
    std::vector<ScheduleBlock> schedule;
    ScheduleImpact impact{};
    std::optional<ScheduleResult> unoptimizedResult;
};

inline auto f_toJson(const JobScheduleResponse &obj) -> Json::Value {
    auto res = Json::Value{};
    res["schedule_id"] = obj.scheduleId;
    res["message"] = "Success";
    res["scheduled_blocks"] = Json::Value(Json::arrayValue);
    res["impact"] = toJson(obj.impact);
    for (const auto &block : obj.schedule)
        res["scheduled_blocks"].append(toJson(block));

    if (obj.unoptimizedResult.has_value()) {
        res["unoptimizedResult"] = toJson(obj.unoptimizedResult.value());
    }

    return res;
}

static_assert(Serializable<JobScheduleResponse>);

/**
 * @class ScheduleCreatedResponse
 * @brief API DTO for the response of a successful job placement.
 */
struct ScheduleCreatedResponse {
    std::string scheduleId;
};

inline auto f_toJson(const ScheduleCreatedResponse &obj) -> Json::Value {
    auto res = Json::Value{};
    res["schedule_id"] = obj.scheduleId;
    res["message"] = "Success";
    return res;
}

static_assert(Serializable<ScheduleCreatedResponse>);

/**
 * @class ScheduleSummary
 * @brief API DTO for the summary of a scheduling operation.
 */
struct ScheduleSummary {
    std::string scheduleId;
    ScheduleImpact impact{};
    std::optional<ScheduleImpact> trivialImpact;
    std::string startTime;
    std::string endTime;
    std::vector<std::string> locations;
    double totalLoad{};
    int blockCount{};
};

inline auto f_toJson(const ScheduleSummary &obj) -> Json::Value {
    auto res = Json::Value{};
    res["schedule_id"] = obj.scheduleId;
    res["message"] = "Success";
    res["impact"] = toJson(obj.impact);
    if (obj.trivialImpact.has_value()) {
        res["trivialImpact"] = toJson(obj.trivialImpact.value());
    }
    if (!obj.startTime.empty()) {
        res["start_time"] = obj.startTime;
        res["end_time"] = obj.endTime;
    }

    auto locArray = Json::Value(Json::arrayValue);
    for (const auto &loc : obj.locations) {
        locArray.append(loc);
    }
    res["locations"] = locArray;
    res["total_load"] = obj.totalLoad;
    res["block_count"] = obj.blockCount;

    return res;
}

static_assert(Serializable<ScheduleSummary>);

} // namespace scheduler

#endif // SCHEDULER_SCHEDULE_RESULT_HPP
