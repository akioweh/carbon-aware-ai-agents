#ifndef SCHEDULER
#define SCHEDULER
#pragma once

#include <Serializable.hpp>
#include <StatsAPIClient.hpp>
#include <structs/Datacenter.hpp>
#include <structs/JobRequest.hpp>
#include <structs/ScheduleBlock.hpp>

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
 * @class InternalBlock
 * @brief The scheduler's output block — a unit of scheduled work with no
 * persistence or API concerns.
 *
 * Unlike ScheduleBlock (the API DTO), this carries no jobId because the
 * scheduler doesn't know it — the DB assigns it on persistence.
 */
struct InternalBlock {
    std::chrono::system_clock::time_point timestamp;
    std::string location;
    double additionalLoad{};
};

/**
 * @class SchedulerOutput
 * @brief The complete output of the scheduling optimization engine.
 *
 * Contains the raw optimization results (scheduled blocks without job IDs)
 * and the computed environmental impact. The controller layer is responsible
 * for persisting this and constructing the API DTO (ScheduleResult) with
 * the DB-assigned job ID.
 */
struct SchedulerOutput {
    std::vector<InternalBlock> blocks;
    ScheduleImpact impact{};
};

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
        res["schedule"].append(toJson(block));
    return res;
}

static_assert(Serializable<ScheduleResult>);

/**
 * @class Scheduler
 * @brief The main schedule optimization engine.
 *
 * The scheduler itself is stateless. It produces a SchedulerOutput
 * containing the optimal allocation and impact metrics. It has no
 * knowledge of persistence or API concerns.
 */
class Scheduler {
  private:
    static constexpr unsigned int KWH = 1000 * 60 * 60;

    StatsAPIClient stats_api;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;
};

#endif
