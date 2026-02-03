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
 * @brief API DTO for the environmental impact of a schedule.
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
        res["schedule"].append(toJson(block));
    return res;
}

static_assert(Serializable<ScheduleResult>);

/**
 * @class Scheduler
 * @brief The main schedule optimization engine.
 *
 * The scheduler itself is stateless.
 */
class Scheduler {
  private:
    static constexpr unsigned int KWH = 1000 * 60 * 60;

    StatsAPIClient stats_api;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<ScheduleResult>;
};

#endif
