#ifndef SCHEDULER
#define SCHEDULER
#pragma once

#include <Serializable.hpp>
#include <StatsAPIClient.hpp>
#include <structs/Datacenter.hpp>
#include <structs/JobRequest.hpp>
#include <structs/ScheduleBlock.hpp>

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

class Scheduler {
  private:
    static constexpr unsigned int KWH = 1000 * 60 * 60;

    StatsAPIClient stats_api;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<ScheduleResult>;
};

#endif
